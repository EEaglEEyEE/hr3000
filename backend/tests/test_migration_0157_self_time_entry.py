"""Migration 0157 (Zeiten selbst eintragen): echtes DDL gegen SQLite, wiederholbar; Enum-Werte für
MySQL werden an die vorhandene Liste angehängt."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m0157 = _load("0157_self_time_entry")

SCHEMA = (
    "CREATE TABLE app_settings (id INTEGER PRIMARY KEY, tenant_id INTEGER)",
    "CREATE TABLE punch_correction_requests (id INTEGER PRIMARY KEY, work_date DATE, items TEXT)",
    "CREATE TABLE punches (id INTEGER PRIMARY KEY, source VARCHAR(20))",
)


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in SCHEMA:
            connection.execute(sa.text(statement))
        connection.execute(sa.text("INSERT INTO app_settings (id, tenant_id) VALUES (1, 1)"))
        connection.execute(sa.text("INSERT INTO punch_correction_requests (id, work_date, items) VALUES (1, '2026-03-02', '[]')"))
        connection.execute(sa.text("INSERT INTO punches (id, source) VALUES (1, 'KIOSK'), (2, 'SELF_ENTRY')"))
        yield connection
    engine.dispose()


def run(conn, fn) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        fn()


def columns(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def test_revision_chain() -> None:
    assert m0157.revision == "0157_self_time_entry"
    assert m0157.down_revision == "0156_recruiting_enums"


def test_upgrade_adds_columns_with_defaults_and_is_repeatable(conn) -> None:
    run(conn, m0157.upgrade)
    run(conn, m0157.upgrade)
    assert {"self_time_entry_enabled", "self_time_entry_approval", "self_time_entry_backdate_days"} <= columns(conn, "app_settings")
    row = conn.execute(sa.text(
        "SELECT self_time_entry_enabled, self_time_entry_approval, self_time_entry_backdate_days FROM app_settings"
    )).one()
    assert tuple(row) == (0, 1, 7)
    assert conn.execute(sa.text("SELECT kind FROM punch_correction_requests")).scalar_one() == "CORRECTION"


def test_downgrade_keeps_self_entered_punches_as_hr_bookings(conn) -> None:
    run(conn, m0157.upgrade)
    run(conn, m0157.downgrade)
    assert "kind" not in columns(conn, "punch_correction_requests")
    assert "self_time_entry_enabled" not in columns(conn, "app_settings")
    assert [r[0] for r in conn.execute(sa.text("SELECT source FROM punches ORDER BY id"))] == ["KIOSK", "MANUAL_HR"]
    run(conn, m0157.downgrade)  # wiederholbar


def test_enum_values_are_appended() -> None:
    assert m0157.parse_enum_values("enum('KIOSK','MANUAL_HR','AUTO_BREAK','PORTAL')") == ["KIOSK", "MANUAL_HR", "AUTO_BREAK", "PORTAL"]
    assert m0157.merged_values(["KIOSK", "SELF_ENTRY"], ("SELF_ENTRY",)) == ["KIOSK", "SELF_ENTRY"]
    assert m0157.merged_values(["A", "X_FROM_OTHER_BRANCH"], m0157._AUDIT_VALUES) == [
        "A", "X_FROM_OTHER_BRANCH", "TIME_ENTRY_CREATED", "TIME_ENTRY_DELETED",
    ]
