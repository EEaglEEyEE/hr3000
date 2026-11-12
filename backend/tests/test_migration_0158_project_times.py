"""Migration 0158 (Projektzeiten): echtes DDL gegen SQLite, wiederholbar und rückbaubar; Audit-Wert für
MySQL wird an die vorhandene Liste angehängt."""
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


m0158 = _load("0158_project_times")

SCHEMA = (
    "CREATE TABLE tenants (id INTEGER PRIMARY KEY)",
    "CREATE TABLE cost_centers (id INTEGER PRIMARY KEY)",
    "CREATE TABLE app_settings (id INTEGER PRIMARY KEY, tenant_id INTEGER)",
    "CREATE TABLE punches (id INTEGER PRIMARY KEY, employee_id INTEGER, timestamp_utc DATETIME)",
)


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in SCHEMA:
            connection.execute(sa.text(statement))
        connection.execute(sa.text("INSERT INTO app_settings (id, tenant_id) VALUES (1, 1)"))
        connection.execute(sa.text("INSERT INTO punches (id, employee_id) VALUES (1, 1)"))
        yield connection
    engine.dispose()


def run(conn, fn) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        fn()


def columns(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def test_revision_chain() -> None:
    assert m0158.revision == "0158_project_times"
    assert m0158.down_revision == "0157_self_time_entry"


def test_upgrade_is_repeatable_and_downgrade_removes_everything(conn) -> None:
    run(conn, m0158.upgrade)
    run(conn, m0158.upgrade)
    assert {"customers", "projects"} <= set(sa.inspect(conn).get_table_names())
    assert {"project_id", "activity_note"} <= columns(conn, "punches")
    assert tuple(conn.execute(sa.text("SELECT project_times_enabled, project_required FROM app_settings")).one()) == (0, 0)
    conn.execute(sa.text("INSERT INTO customers (id, tenant_id, name) VALUES (1, 1, 'A')"))
    conn.execute(sa.text("INSERT INTO projects (id, tenant_id, name, customer_id) VALUES (1, 1, 'P', 1)"))
    row = conn.execute(sa.text("SELECT billable, active FROM projects")).one()
    assert tuple(row) == (1, 1)
    run(conn, m0158.downgrade)
    assert not {"customers", "projects"} & set(sa.inspect(conn).get_table_names())
    assert not {"project_id", "activity_note"} & columns(conn, "punches")
    assert "project_times_enabled" not in columns(conn, "app_settings")
    assert conn.execute(sa.text("SELECT count(*) FROM punches")).scalar_one() == 1
    run(conn, m0158.downgrade)


def test_enum_value_is_appended() -> None:
    assert m0158.merged_values(["A", "FROM_OTHER_BRANCH"], m0158._AUDIT_VALUES) == ["A", "FROM_OTHER_BRANCH", "PROJECT_CHANGED"]
    assert m0158.merged_values(["PROJECT_CHANGED"], m0158._AUDIT_VALUES) == ["PROJECT_CHANGED"]
    assert m0158.parse_enum_values("enum('A','B')") == ["A", "B"]
