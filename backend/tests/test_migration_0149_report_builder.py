"""Migration 0149 (Berichts-Builder): Enum-Helfer, upgrade/downgrade gegen SQLite (echtes DDL über
Alembic-Operations), wiederholbar; Enum-Erweiterung mit den Werten aus der Datenbank (MySQL-Pfad
mit nachgebildeter Verbindung)."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0149_report_builder.py"
_spec = importlib.util.spec_from_file_location("migration_0149", _PATH)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


def test_revision_chain():
    assert migration.revision == "0149_report_builder"
    assert migration.down_revision == "0141_settled_overtime"


@pytest.mark.parametrize(
    "column_type,values",
    [
        ("enum('A','B','C')", ["A", "B", "C"]),
        ("enum('LOGIN')", ["LOGIN"]),
        ("", []),
        ("enum('IT''S','X')", ["IT''S", "X"]),
    ],
)
def test_parse_enum_values(column_type, values):
    assert migration.parse_enum_values(column_type) == values


def test_enum_with_and_without():
    assert migration.enum_with(["A", "B"], ["C", "A", "D"]) == ["A", "B", "C", "D"]
    assert migration.enum_with([], ["C"]) == ["C"]
    assert migration.enum_without(["A", "C", "B", "D"], ["C", "D"]) == ["A", "B"]
    assert migration.enum_without(["A"], ["X"]) == ["A"]


@pytest.fixture
def conn(monkeypatch):
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in (
            "CREATE TABLE tenants (id INTEGER PRIMARY KEY)",
            "CREATE TABLE accounts (id INTEGER PRIMARY KEY)",
            "CREATE TABLE app_settings (id INTEGER PRIMARY KEY, tenant_id INTEGER)",
            "CREATE TABLE audit_log_entries (id INTEGER PRIMARY KEY, action TEXT NOT NULL)",
        ):
            connection.execute(sa.text(statement))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        yield connection
    engine.dispose()


def test_upgrade_creates_table_and_column_and_is_repeatable(conn):
    migration.upgrade()
    assert migration._has_table(conn, "saved_reports")
    assert migration._has_column(conn, "app_settings", "custom_reports_enabled")
    columns = {c["name"] for c in sa.inspect(conn).get_columns("saved_reports")}
    assert columns == {"id", "tenant_id", "owner_account_id", "name", "description", "definition", "shared", "created_at", "updated_at"}
    foreign = {fk["referred_table"]: fk for fk in sa.inspect(conn).get_foreign_keys("saved_reports")}
    assert foreign["accounts"]["options"].get("ondelete") == "SET NULL"
    assert "ix_saved_reports_tenant_id" in {i["name"] for i in sa.inspect(conn).get_indexes("saved_reports")}
    conn.execute(sa.text("INSERT INTO app_settings (id, tenant_id) VALUES (1, 1)"))
    assert conn.execute(sa.text("SELECT custom_reports_enabled FROM app_settings")).scalar() in (0, False)
    migration.upgrade()  # zweiter Lauf ändert nichts und scheitert nicht


def test_downgrade_removes_everything_and_audit_rows(conn):
    migration.upgrade()
    conn.execute(sa.text("INSERT INTO audit_log_entries (action) VALUES ('REPORT_RUN'), ('LOGIN'), ('REPORT_EXPORTED'), ('REPORT_CHANGED')"))
    migration.downgrade()
    assert not migration._has_table(conn, "saved_reports")
    assert not migration._has_column(conn, "app_settings", "custom_reports_enabled")
    assert [r[0] for r in conn.execute(sa.text("SELECT action FROM audit_log_entries"))] == ["LOGIN"]
    migration.downgrade()  # wiederholbar


def test_audit_values_outside_mysql_is_none(conn):
    assert migration._audit_values(conn) is None


class _MysqlConn:
    """Verbindung, die sich als MySQL ausgibt und information_schema beantwortet."""

    def __init__(self, column_type):
        self.dialect = type("D", (), {"name": "mysql"})()
        self.column_type = column_type
        self.sql = []

    def execute(self, statement):
        self.sql.append(str(statement))
        return type("R", (), {"scalar": lambda _self: self.column_type})()


def test_audit_values_on_mysql_reads_column_type():
    conn = _MysqlConn("enum('LOGIN','HIRING_STEP')")
    assert migration._audit_values(conn) == ["LOGIN", "HIRING_STEP"]
    assert "information_schema.COLUMNS" in conn.sql[0]
    assert migration._audit_values(_MysqlConn(None)) == []


def test_set_audit_values_keeps_values_of_parallel_migrations(monkeypatch):
    calls = []

    class FakeOp:
        def alter_column(self, table, column, **kwargs):
            calls.append((table, column, list(kwargs["existing_type"].enums), list(kwargs["type_"].enums)))

    monkeypatch.setattr(migration, "op", FakeOp())
    existing = ["LOGIN", "WHISTLEBLOWER_CASE"]  # Wert einer parallel entwickelten Migration
    migration._set_audit_values(existing, migration.enum_with(existing, migration.NEW_AUDIT_ACTIONS))
    assert calls == [("audit_log_entries", "action", existing, existing + list(migration.NEW_AUDIT_ACTIONS))]
    calls.clear()
    migration._set_audit_values(existing, list(existing))  # nichts zu tun
    assert calls == []


def test_upgrade_and_downgrade_on_mysql_extend_and_shrink_enum(monkeypatch):
    state = {"values": ["LOGIN", "SETTINGS_CHANGED"]}
    changes = []
    monkeypatch.setattr(migration, "_has_table", lambda conn, table: True)
    monkeypatch.setattr(migration, "_has_column", lambda conn, table, column: False)
    monkeypatch.setattr(migration, "_audit_values", lambda conn: list(state["values"]))

    class FakeOp:
        def get_bind(self):
            return None

        def add_column(self, *args, **kwargs):
            changes.append("add_column")

        def execute(self, sql):
            changes.append(sql)

        def alter_column(self, table, column, **kwargs):
            state["values"] = list(kwargs["type_"].enums)

        def drop_index(self, name, table_name):
            changes.append(f"drop_index {name}")

        def drop_table(self, name):
            changes.append(f"drop_table {name}")

    monkeypatch.setattr(migration, "op", FakeOp())
    migration.upgrade()
    assert state["values"] == ["LOGIN", "SETTINGS_CHANGED", "REPORT_CHANGED", "REPORT_RUN", "REPORT_EXPORTED"]
    assert changes == ["add_column"]
    migration.downgrade()
    assert state["values"] == ["LOGIN", "SETTINGS_CHANGED"]
    assert changes[1:] == [
        "DELETE FROM audit_log_entries WHERE action IN ('REPORT_CHANGED', 'REPORT_RUN', 'REPORT_EXPORTED')",
        "drop_index ix_saved_reports_tenant_id",
        "drop_table saved_reports",
    ]
