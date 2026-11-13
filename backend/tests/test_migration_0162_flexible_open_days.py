"""Migration 0162 (flexible Modelle unter „Zu klären“): upgrade() und downgrade() gegen ein minimales
Schema in SQLite – bestehende Firmen behalten ihr Verhalten (Tage flexibler Modelle weiter gemeldet,
der neue Hinweis „Wochensoll nicht erreicht“ aus)."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m0162 = _load("0162_flexible_open_days")

SCHEMA = (
    "CREATE TABLE app_settings (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, disabled_day_flags VARCHAR(200))",
    "CREATE TABLE daily_summaries (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL, flags VARCHAR(200))",
)
ROWS = {1: "EARLY_LEAVE,LATE_ARRIVAL", 2: None, 3: "", 4: "UNPLANNED_WORK"}


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in SCHEMA:
            connection.execute(sa.text(statement))
        for row_id, flags in ROWS.items():
            connection.execute(
                sa.text("INSERT INTO app_settings (id, tenant_id, disabled_day_flags) VALUES (:id, :id, :flags)"),
                {"id": row_id, "flags": flags},
            )
        connection.execute(sa.text("INSERT INTO daily_summaries (id, employee_id, flags) VALUES (9, 7, 'HOLIDAY_WORK')"))
        yield connection
    engine.dispose()


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def _run(conn, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def _flags(conn) -> dict[int, str | None]:
    return dict(conn.execute(sa.text("SELECT id, disabled_day_flags FROM app_settings ORDER BY id")).all())


def test_chain() -> None:
    assert (m0162.revision, m0162.down_revision) == ("0162_flexible_open_days", "0161_punch_location")


def test_upgrade_keeps_behaviour_of_existing_companies(conn) -> None:
    _run(conn, m0162.upgrade)
    assert {"report_flexible_days", "weekly_target_from"} <= _columns(conn, "app_settings")
    assert "review_exempt" in _columns(conn, "daily_summaries")
    # Tage flexibler Modelle werden weiter gemeldet, der Stichtag ist leer
    rows = conn.execute(sa.text("SELECT report_flexible_days, weekly_target_from FROM app_settings")).all()
    assert [tuple(row) for row in rows] == [(1, None)] * len(ROWS)
    # Der neue Hinweis ist bei jeder Firma abgeschaltet – auch wo bisher nichts abgeschaltet war
    assert _flags(conn) == {
        1: "EARLY_LEAVE,LATE_ARRIVAL,WEEKLY_TARGET_MISSED",
        2: "WEEKLY_TARGET_MISSED",
        3: "WEEKLY_TARGET_MISSED",
        4: "UNPLANNED_WORK,WEEKLY_TARGET_MISSED",
    }
    assert tuple(conn.execute(sa.text("SELECT flags, review_exempt FROM daily_summaries")).one()) == ("HOLIDAY_WORK", 0)


def test_upgrade_is_idempotent_for_the_flag(conn) -> None:
    conn.execute(sa.text("UPDATE app_settings SET disabled_day_flags = 'WEEKLY_TARGET_MISSED' WHERE id = 2"))
    _run(conn, m0162.upgrade)
    assert _flags(conn)[2] == "WEEKLY_TARGET_MISSED"


def test_downgrade_removes_columns_and_flag(conn) -> None:
    _run(conn, m0162.upgrade)
    _run(conn, m0162.downgrade)
    assert _columns(conn, "app_settings") == {"id", "tenant_id", "disabled_day_flags"}
    assert _columns(conn, "daily_summaries") == {"id", "employee_id", "flags"}
    assert _flags(conn) == {1: "EARLY_LEAVE,LATE_ARRIVAL", 2: None, 3: None, 4: "UNPLANNED_WORK"}
    assert conn.execute(sa.text("SELECT COUNT(*) FROM daily_summaries")).scalar_one() == 1
