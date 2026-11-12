"""Migrationen 0154–0156 (Recruiting): echtes DDL gegen SQLite, wiederholbar; Enum-Erweiterung
für MySQL mit den Werten, die gerade in der Datenbank stehen."""
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


m0154 = _load("0154_recruiting_jobs")
m0155 = _load("0155_recruiting_applications")
m0156 = _load("0156_recruiting_enums")

SCHEMA = (
    "CREATE TABLE tenants (id INTEGER PRIMARY KEY)",
    "CREATE TABLE departments (id INTEGER PRIMARY KEY)",
    "CREATE TABLE locations (id INTEGER PRIMARY KEY)",
    "CREATE TABLE accounts (id INTEGER PRIMARY KEY)",
    "CREATE TABLE employees (id INTEGER PRIMARY KEY)",
    "CREATE TABLE app_settings (id INTEGER PRIMARY KEY, tenant_id INTEGER)",
)


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in SCHEMA:
            connection.execute(sa.text(statement))
        connection.execute(sa.text("INSERT INTO app_settings (id, tenant_id) VALUES (1, 1)"))
        yield connection
    engine.dispose()


def run(conn, fn) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        fn()


def tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def columns(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def test_revision_chain() -> None:
    assert m0154.down_revision == "0151_whistleblowing"
    assert m0155.down_revision == m0154.revision == "0154_recruiting_jobs"
    assert m0156.down_revision == m0155.revision == "0155_recruiting_applications"
    assert m0156.revision == "0156_recruiting_enums"


def test_upgrade_creates_everything_and_is_repeatable(conn) -> None:
    for module in (m0154, m0155, m0156):
        run(conn, module.upgrade)
    expected = {
        "recruiting_jobs", "recruiting_job_members", "recruiting_applications", "recruiting_attachments",
        "recruiting_notes", "recruiting_ratings", "recruiting_stage_events", "recruiting_stats",
    }
    assert expected <= tables(conn)
    assert {"recruiting_enabled", "recruiting_privacy_text", "recruiting_privacy_url", "recruiting_retention_months",
            "recruiting_talent_pool_months"} <= columns(conn, "app_settings")
    row = conn.execute(sa.text(
        "SELECT recruiting_enabled, recruiting_retention_months, recruiting_talent_pool_months FROM app_settings"
    )).one()
    assert tuple(row) == (0, 6, 12)
    for table in expected:
        assert "tenant_id" in columns(conn, table), table
    # zweiter Lauf (z. B. nach einem Abbruch auf MySQL) ändert nichts und scheitert nicht
    for module in (m0154, m0155, m0156):
        run(conn, module.upgrade)


def test_foreign_keys_have_sensible_ondelete(conn) -> None:
    run(conn, m0154.upgrade)
    run(conn, m0155.upgrade)
    inspector = sa.inspect(conn)

    def ondelete(table: str, column: str) -> str | None:
        fk = next(f for f in inspector.get_foreign_keys(table) if f["constrained_columns"] == [column])
        return (fk.get("options") or {}).get("ondelete")

    assert ondelete("recruiting_jobs", "department_id") == "SET NULL"
    assert ondelete("recruiting_job_members", "job_id") == "CASCADE"
    assert ondelete("recruiting_applications", "job_id") == "CASCADE"
    assert ondelete("recruiting_applications", "employee_id") == "SET NULL"
    assert ondelete("recruiting_attachments", "application_id") == "CASCADE"
    assert ondelete("recruiting_notes", "author_account_id") == "SET NULL"


def test_downgrade_removes_everything(conn) -> None:
    for module in (m0154, m0155, m0156):
        run(conn, module.upgrade)
    for module in (m0156, m0155, m0154):
        run(conn, module.downgrade)
    assert not any(t.startswith("recruiting_") for t in tables(conn))
    assert not any(c.startswith("recruiting_") for c in columns(conn, "app_settings"))
    for module in (m0156, m0155, m0154):
        run(conn, module.downgrade)  # wiederholbar


@pytest.mark.parametrize(
    "column_type, values",
    [
        ("enum('A','B','C')", ["A", "B", "C"]),
        ("enum('LOGIN')", ["LOGIN"]),
        ("varchar(20)", []),
    ],
)
def test_parse_enum_values(column_type, values) -> None:
    assert m0156.parse_enum_values(column_type) == values


def test_merged_values_keep_existing_order_and_skip_known() -> None:
    assert m0156.merged_values(["A", "X"], ("X", "Y")) == ["A", "X", "Y"]
    assert m0156.merged_values([], ("Y",)) == ["Y"]


class _FakeMySql:
    """op-Ersatz für den MySQL-Zweig: liefert die aktuellen Enum-Werte und merkt sich alter_column/execute."""

    def __init__(self, current: dict[tuple[str, str], str]):
        self.current = current
        self.calls: list = []
        outer = self

        class Conn:
            dialect = type("D", (), {"name": "mysql"})()

            def execute(self, statement, params):
                value = outer.current.get((params["t"], params["c"]))
                return type("R", (), {"first": lambda self: (value,) if value else None})()

        self.conn = Conn()

    def get_bind(self):
        return self.conn

    def alter_column(self, table, column, *, existing_type, type_, existing_nullable):
        self.calls.append(("alter", table, list(existing_type.enums), list(type_.enums)))

    def execute(self, sql):
        self.calls.append(("execute", sql))


def test_mysql_upgrade_appends_to_current_values(monkeypatch) -> None:
    fake = _FakeMySql({
        ("audit_log_entries", "action"): "enum('LOGIN','FOREIGN_FEATURE')",
        ("notifications", "type"): "enum('REMINDER')",
    })
    monkeypatch.setattr(m0156, "op", fake)
    m0156.upgrade()
    assert fake.calls == [
        ("alter", "audit_log_entries", ["LOGIN", "FOREIGN_FEATURE"], ["LOGIN", "FOREIGN_FEATURE", *m0156._AUDIT_VALUES]),
        ("alter", "notifications", ["REMINDER"], ["REMINDER", "RECRUITING_APPLICATION"]),
    ]


def test_mysql_upgrade_when_values_exist_changes_nothing(monkeypatch) -> None:
    audit = ",".join(f"'{v}'" for v in ("LOGIN", *m0156._AUDIT_VALUES))
    fake = _FakeMySql({
        ("audit_log_entries", "action"): f"enum({audit})",
        ("notifications", "type"): "enum('REMINDER','RECRUITING_APPLICATION')",
    })
    monkeypatch.setattr(m0156, "op", fake)
    m0156.upgrade()
    assert fake.calls == []


def test_mysql_downgrade_removes_rows_and_values(monkeypatch) -> None:
    audit = ",".join(f"'{v}'" for v in ("LOGIN", *m0156._AUDIT_VALUES))
    fake = _FakeMySql({
        ("audit_log_entries", "action"): f"enum({audit})",
        ("notifications", "type"): "enum('REMINDER','RECRUITING_APPLICATION')",
    })
    monkeypatch.setattr(m0156, "op", fake)
    m0156.downgrade()
    assert fake.calls[0][0] == "execute" and "DELETE FROM `audit_log_entries`" in fake.calls[0][1]
    assert fake.calls[1] == ("alter", "audit_log_entries", ["LOGIN", *m0156._AUDIT_VALUES], ["LOGIN"])
    assert fake.calls[3] == ("alter", "notifications", ["REMINDER", "RECRUITING_APPLICATION"], ["REMINDER"])


def test_mysql_without_column_info_does_nothing(monkeypatch) -> None:
    fake = _FakeMySql({})
    monkeypatch.setattr(m0156, "op", fake)
    m0156.upgrade()
    m0156.downgrade()
    assert fake.calls == []


def test_model_enums_contain_the_migrated_values() -> None:
    from app.models import AuditAction, NotificationType

    assert set(m0156._AUDIT_VALUES) <= {a.value for a in AuditAction}
    assert set(m0156._NOTIFICATION_VALUES) <= {n.value for n in NotificationType}
