"""Migration 0161 (Standort beim Stempeln, A18): upgrade() und downgrade() gegen ein minimales Schema in
SQLite – bestehende Zeilen behalten ihre Werte, neue Spalten starten mit „aus“ bzw. leer."""
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


m0161 = _load("0161_punch_location")

SCHEMA = (
    "CREATE TABLE app_settings (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL)",
    "CREATE TABLE locations (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, name VARCHAR(255) NOT NULL)",
    "CREATE TABLE punches (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL, location_id INTEGER NOT NULL)",
)
NEW_COLUMNS = {
    "app_settings": {"punch_location_check_enabled", "punch_location_mode"},
    "locations": {"geo_latitude", "geo_longitude", "geo_radius_m"},
    "punches": {"location_check", "location_check_location_id"},
}


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in SCHEMA:
            connection.execute(sa.text(statement))
        connection.execute(sa.text("INSERT INTO app_settings (id, tenant_id) VALUES (1, 1)"))
        connection.execute(sa.text("INSERT INTO locations (id, tenant_id, name) VALUES (3, 1, 'Zentrale')"))
        connection.execute(sa.text("INSERT INTO punches (id, employee_id, location_id) VALUES (5, 7, 3)"))
        yield connection
    engine.dispose()


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def _run(conn, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_chain() -> None:
    assert (m0161.revision, m0161.down_revision) == ("0161_punch_location", "0158_project_times")


def test_upgrade_adds_columns_with_safe_defaults(conn) -> None:
    _run(conn, m0161.upgrade)
    for table, columns in NEW_COLUMNS.items():
        assert columns <= _columns(conn, table)
    # Bestehende Firma: Prüfung aus, Modus „nur vermerken“
    assert tuple(conn.execute(sa.text("SELECT punch_location_check_enabled, punch_location_mode FROM app_settings")).one()) == (0, "RECORD")
    assert tuple(conn.execute(sa.text("SELECT name, geo_latitude, geo_longitude, geo_radius_m FROM locations")).one()) == ("Zentrale", None, None, None)
    assert tuple(conn.execute(sa.text("SELECT location_id, location_check, location_check_location_id FROM punches")).one()) == (3, None, None)
    # Keine Spalte für Koordinaten von Mitarbeitern
    assert not {"latitude", "longitude", "accuracy_m"} & _columns(conn, "punches")


def test_downgrade_removes_columns(conn) -> None:
    _run(conn, m0161.upgrade)
    _run(conn, m0161.downgrade)
    assert _columns(conn, "app_settings") == {"id", "tenant_id"}
    assert _columns(conn, "locations") == {"id", "tenant_id", "name"}
    assert _columns(conn, "punches") == {"id", "employee_id", "location_id"}
    assert conn.execute(sa.text("SELECT COUNT(*) FROM punches")).scalar_one() == 1
