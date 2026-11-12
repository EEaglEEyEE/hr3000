"""Migrationen 0140 (mehrwöchiges Modell) und 0141 (abgegoltene Überstunden): upgrade() und
downgrade() gegen ein minimales Schema in SQLite – bestehende Zeilen behalten ihre Werte."""
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


rotation = _load("0140_rotation_model")
settled = _load("0141_settled_overtime")

SCHEMA = (
    "CREATE TABLE employee_default_shifts (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL, day_minutes TEXT)",
    "CREATE TABLE work_time_profile_versions (id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL, day_minutes TEXT)",
    "CREATE TABLE overtime_balances (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL, running_balance_minutes INTEGER NOT NULL)",
    "CREATE TABLE period_closures (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL, balance_end_minutes INTEGER NOT NULL)",
)


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in SCHEMA:
            connection.execute(sa.text(statement))
        connection.execute(sa.text("INSERT INTO employee_default_shifts (id, employee_id, day_minutes) VALUES (1, 7, '480,0,0,0,0,0,0')"))
        connection.execute(sa.text("INSERT INTO work_time_profile_versions (id, profile_id) VALUES (1, 3)"))
        connection.execute(sa.text("INSERT INTO overtime_balances (id, employee_id, running_balance_minutes) VALUES (1, 7, 90)"))
        connection.execute(sa.text("INSERT INTO period_closures (id, employee_id, balance_end_minutes) VALUES (1, 7, 90)"))
        yield connection
    engine.dispose()


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def _run(conn, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_chain() -> None:
    assert (rotation.revision, rotation.down_revision) == ("0140_rotation_model", "0137_payroll_accounting")
    assert (settled.revision, settled.down_revision) == ("0141_settled_overtime", "0140_rotation_model")


def test_upgrade_adds_columns_and_keeps_rows(conn) -> None:
    _run(conn, rotation.upgrade)
    _run(conn, settled.upgrade)
    for table in ("employee_default_shifts", "work_time_profile_versions"):
        assert {"rotation_minutes", "rotation_start", "settled_overtime_minutes"} <= _columns(conn, table)
    for table in ("overtime_balances", "period_closures"):
        assert "settled_minutes" in _columns(conn, table)
    shift = conn.execute(sa.text("SELECT day_minutes, rotation_minutes, rotation_start, settled_overtime_minutes FROM employee_default_shifts")).one()
    assert tuple(shift) == ("480,0,0,0,0,0,0", None, None, None)
    # Bestehende Kontozeilen und Abschlüsse: nichts abgegolten
    assert conn.execute(sa.text("SELECT running_balance_minutes, settled_minutes FROM overtime_balances")).one() == (90, 0)
    assert conn.execute(sa.text("SELECT balance_end_minutes, settled_minutes FROM period_closures")).one() == (90, 0)


def test_downgrade_removes_columns(conn) -> None:
    _run(conn, rotation.upgrade)
    _run(conn, settled.upgrade)
    _run(conn, settled.downgrade)
    assert "settled_overtime_minutes" not in _columns(conn, "employee_default_shifts")
    assert "settled_minutes" not in _columns(conn, "overtime_balances")
    assert "rotation_minutes" in _columns(conn, "employee_default_shifts")
    _run(conn, rotation.downgrade)
    assert _columns(conn, "employee_default_shifts") == {"id", "employee_id", "day_minutes"}
    assert _columns(conn, "work_time_profile_versions") == {"id", "profile_id", "day_minutes"}
