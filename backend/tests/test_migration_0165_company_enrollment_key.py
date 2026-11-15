"""Migration 0165 (Firmenschlüssel): upgrade() erlaubt Schlüssel und Anfragen ohne Standort, downgrade()
entfernt solche Zeilen und macht den Standort wieder zur Pflicht – gegen ein minimales Schema in SQLite."""
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


m0165 = _load("0165_company_enrollment_key")


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE locations (id INTEGER PRIMARY KEY)"))
        connection.execute(
            sa.text(
                "CREATE TABLE device_enrollment_keys (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, "
                "location_id INTEGER NOT NULL UNIQUE REFERENCES locations(id), key_hash VARCHAR(64) NOT NULL)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE device_enrollments (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, "
                "location_id INTEGER NOT NULL REFERENCES locations(id), verify_code VARCHAR(7) NOT NULL)"
            )
        )
        connection.execute(sa.text("INSERT INTO locations (id) VALUES (1)"))
        connection.execute(sa.text("INSERT INTO device_enrollment_keys VALUES (1, 1, 1, 'hash-standort')"))
        connection.execute(sa.text("INSERT INTO device_enrollments VALUES (1, 1, 1, 'K7Q-4XZ')"))
        yield connection
    engine.dispose()


def _nullable(conn, table: str) -> bool:
    return {c["name"]: c for c in sa.inspect(conn).get_columns(table)}["location_id"]["nullable"]


def _run(conn, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_chain() -> None:
    assert (m0165.revision, m0165.down_revision) == ("0165_company_enrollment_key", "0164_device_presence")


def test_upgrade_allows_rows_without_location_and_keeps_existing(conn) -> None:
    _run(conn, m0165.upgrade)
    assert _nullable(conn, "device_enrollment_keys") and _nullable(conn, "device_enrollments")
    conn.execute(sa.text("INSERT INTO device_enrollment_keys VALUES (2, 1, NULL, 'hash-firma')"))
    conn.execute(sa.text("INSERT INTO device_enrollments VALUES (2, 1, NULL, 'AB2-CD3')"))
    keys = conn.execute(sa.text("SELECT id, location_id FROM device_enrollment_keys ORDER BY id")).all()
    assert [tuple(row) for row in keys] == [(1, 1), (2, None)]
    # Eindeutigkeit je Standort bleibt
    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(sa.text("INSERT INTO device_enrollment_keys VALUES (3, 1, 1, 'hash-doppelt')"))


def test_downgrade_drops_rows_without_location(conn) -> None:
    _run(conn, m0165.upgrade)
    conn.execute(sa.text("INSERT INTO device_enrollment_keys VALUES (2, 1, NULL, 'hash-firma')"))
    conn.execute(sa.text("INSERT INTO device_enrollments VALUES (2, 1, NULL, 'AB2-CD3')"))
    _run(conn, m0165.downgrade)
    assert not _nullable(conn, "device_enrollment_keys") and not _nullable(conn, "device_enrollments")
    assert conn.execute(sa.text("SELECT id FROM device_enrollment_keys")).scalars().all() == [1]
    assert conn.execute(sa.text("SELECT verify_code FROM device_enrollments")).scalars().all() == ["K7Q-4XZ"]
