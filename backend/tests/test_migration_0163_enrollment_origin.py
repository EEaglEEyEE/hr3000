"""Migration 0163 (Herkunft offener Tablet-Registrierungen): upgrade() und downgrade() gegen ein
minimales Schema in SQLite – bestehende Anfragen bleiben erhalten und ohne Angabe."""
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


m0163 = _load("0163_enrollment_origin")


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text("CREATE TABLE device_enrollments (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, verify_code VARCHAR(7) NOT NULL)")
        )
        connection.execute(sa.text("INSERT INTO device_enrollments (id, tenant_id, verify_code) VALUES (4, 1, 'K7Q-4XZ')"))
        yield connection
    engine.dispose()


def _columns(conn) -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(conn).get_columns("device_enrollments")}


def _run(conn, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_chain() -> None:
    assert (m0163.revision, m0163.down_revision) == ("0163_enrollment_origin", "0162_flexible_open_days")


def test_upgrade_adds_nullable_origin_columns(conn) -> None:
    _run(conn, m0163.upgrade)
    columns = _columns(conn)
    assert columns["user_agent"]["nullable"] and columns["client_ip"]["nullable"]
    assert columns["user_agent"]["type"].length == 300 and columns["client_ip"]["type"].length == 45
    row = conn.execute(sa.text("SELECT verify_code, user_agent, client_ip FROM device_enrollments")).one()
    assert tuple(row) == ("K7Q-4XZ", None, None)


def test_downgrade_removes_columns(conn) -> None:
    _run(conn, m0163.upgrade)
    _run(conn, m0163.downgrade)
    assert set(_columns(conn)) == {"id", "tenant_id", "verify_code"}
    assert conn.execute(sa.text("SELECT COUNT(*) FROM device_enrollments")).scalar_one() == 1
