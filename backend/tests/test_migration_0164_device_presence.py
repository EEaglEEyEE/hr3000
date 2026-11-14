"""Migration 0164 (Live-Status der Tablets): upgrade() und downgrade() gegen ein minimales Schema in
SQLite – bestehende Tablets bleiben erhalten und ohne Angabe zur Warteschlange, die Offline-Warnung ist
bei allen Firmen eingeschaltet."""
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


m0164 = _load("0164_device_presence")


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE devices (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, name VARCHAR(255) NOT NULL)"))
        connection.execute(sa.text("INSERT INTO devices (id, tenant_id, name) VALUES (7, 1, 'Eingang')"))
        connection.execute(sa.text("CREATE TABLE app_settings (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL)"))
        connection.execute(sa.text("INSERT INTO app_settings (id, tenant_id) VALUES (1, 1), (2, 2)"))
        yield connection
    engine.dispose()


def _columns(conn, table: str = "devices") -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(conn).get_columns(table)}


def _run(conn, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_chain() -> None:
    assert (m0164.revision, m0164.down_revision) == ("0164_device_presence", "0163_enrollment_origin")


def test_upgrade_adds_nullable_queue_columns(conn) -> None:
    _run(conn, m0164.upgrade)
    columns = _columns(conn)
    assert columns["queued_punches"]["nullable"] and columns["failed_punches"]["nullable"]
    assert isinstance(columns["queued_punches"]["type"], sa.Integer) and isinstance(columns["failed_punches"]["type"], sa.Integer)
    assert columns["offline_alerted_at"]["nullable"] and isinstance(columns["offline_alerted_at"]["type"], sa.DateTime)
    row = conn.execute(sa.text("SELECT name, queued_punches, failed_punches, offline_alerted_at FROM devices")).one()
    assert tuple(row) == ("Eingang", None, None, None)


def test_upgrade_turns_the_offline_alert_on_for_every_company(conn) -> None:
    _run(conn, m0164.upgrade)
    assert _columns(conn, "app_settings")["device_offline_alert"]["nullable"] is False
    rows = conn.execute(sa.text("SELECT device_offline_alert FROM app_settings ORDER BY id")).scalars().all()
    assert rows == [1, 1]


def test_downgrade_removes_columns(conn) -> None:
    _run(conn, m0164.upgrade)
    conn.execute(sa.text("UPDATE devices SET queued_punches = 3, failed_punches = 1"))
    _run(conn, m0164.downgrade)
    assert set(_columns(conn)) == {"id", "tenant_id", "name"}
    assert set(_columns(conn, "app_settings")) == {"id", "tenant_id"}
    assert conn.execute(sa.text("SELECT COUNT(*) FROM devices")).scalar_one() == 1
