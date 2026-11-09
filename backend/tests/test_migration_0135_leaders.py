"""Migration 0135 (mehrere Leitungen und Stellvertretungen): transfer_leaders und upgrade() gegen ein
minimales Schema in SQLite – echtes SQL, wiederholbar nach einem Abbruch."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0135_department_leaders.py"
_spec = importlib.util.spec_from_file_location("migration_0135", _PATH)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)

LEADERS_TABLE = (
    "CREATE TABLE department_leaders (id INTEGER PRIMARY KEY, department_id INTEGER NOT NULL, "
    "employee_id INTEGER NOT NULL, role TEXT NOT NULL, deputy_rights TEXT NOT NULL DEFAULT 'STANDBY', "
    "position INTEGER NOT NULL DEFAULT 0, UNIQUE (department_id, employee_id))"
)
SCHEMA = (
    "CREATE TABLE departments (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, name TEXT NOT NULL, "
    "parent_id INTEGER, head_employee_id INTEGER)",
    "CREATE TABLE employees (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, department_id INTEGER, "
    "supervisor_id INTEGER, approval_delegate_id INTEGER)",
)


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in SCHEMA:
            connection.execute(sa.text(statement))
        yield connection
    engine.dispose()


def insert(conn, table: str, *rows: dict) -> None:
    for row in rows:
        columns = ", ".join(row)
        values = ", ".join(f":{key}" for key in row)
        conn.execute(sa.text(f"INSERT INTO {table} ({columns}) VALUES ({values})"), row)


def leaders(conn) -> list[tuple]:
    return [
        tuple(row)
        for row in conn.execute(
            sa.text("SELECT department_id, employee_id, role, deputy_rights, position FROM department_leaders ORDER BY department_id, position")
        ).all()
    ]


def company(conn) -> None:
    """Vertrieb (Leitung 1, Vertretung 2), Lager (Leitung 3, ohne Vertretung), IT (ohne Leitung).
    4 hat eine Vertretung (5), leitet aber nichts; 6 hat sich selbst als Vertretung."""
    insert(
        conn, "departments",
        {"id": 10, "tenant_id": 1, "name": "Vertrieb", "head_employee_id": 1},
        {"id": 11, "tenant_id": 1, "name": "Lager", "head_employee_id": 3},
        {"id": 12, "tenant_id": 1, "name": "IT"},
    )
    insert(
        conn, "employees",
        {"id": 1, "tenant_id": 1, "department_id": 10, "approval_delegate_id": 2},
        {"id": 2, "tenant_id": 1, "department_id": 10},
        {"id": 3, "tenant_id": 1, "department_id": 11},
        {"id": 4, "tenant_id": 1, "approval_delegate_id": 5},
        {"id": 5, "tenant_id": 1},
        {"id": 6, "tenant_id": 1, "approval_delegate_id": 6},
    )


def test_head_becomes_head_and_delegate_becomes_standby_deputy(conn):
    conn.execute(sa.text(LEADERS_TABLE))
    company(conn)
    notes: list[str] = []
    migration.transfer_leaders(conn, log=notes.append)
    assert leaders(conn) == [
        (10, 1, "HEAD", "STANDBY", 0),
        (10, 2, "DEPUTY", "STANDBY", 1),
        (11, 3, "HEAD", "STANDBY", 0),
    ]
    assert notes == ["Hinweis: Mitarbeiter 4 hatte eine Vertretung bei Genehmigungen (5), leitet aber keine Abteilung – sie entfällt."]


def test_delegate_who_already_leads_there_is_not_added_twice(conn):
    conn.execute(sa.text(LEADERS_TABLE))
    insert(conn, "departments", {"id": 10, "tenant_id": 1, "name": "Vertrieb", "head_employee_id": 1})
    insert(conn, "employees", {"id": 1, "tenant_id": 1, "approval_delegate_id": 2}, {"id": 2, "tenant_id": 1})
    insert(conn, "department_leaders", {"department_id": 10, "employee_id": 2, "role": "HEAD", "position": 0})
    migration.transfer_leaders(conn)
    assert leaders(conn) == [(10, 2, "HEAD", "STANDBY", 0), (10, 1, "HEAD", "STANDBY", 1)]


def test_delegate_of_a_head_of_several_departments_deputises_everywhere(conn):
    conn.execute(sa.text(LEADERS_TABLE))
    insert(conn, "departments", {"id": 10, "tenant_id": 1, "name": "A", "head_employee_id": 1}, {"id": 11, "tenant_id": 1, "name": "B", "head_employee_id": 1})
    insert(conn, "employees", {"id": 1, "tenant_id": 1, "approval_delegate_id": 2}, {"id": 2, "tenant_id": 1})
    migration.transfer_leaders(conn)
    assert [(d, e, r) for d, e, r, _, _ in leaders(conn)] == [(10, 1, "HEAD"), (10, 2, "DEPUTY"), (11, 1, "HEAD"), (11, 2, "DEPUTY")]


def test_running_twice_adds_nothing(conn):
    conn.execute(sa.text(LEADERS_TABLE))
    company(conn)
    migration.transfer_leaders(conn, log=lambda _: None)
    first = leaders(conn)
    migration.transfer_leaders(conn, log=lambda _: None)
    assert leaders(conn) == first


def test_after_dropped_columns_nothing_happens(conn):
    conn.execute(sa.text(LEADERS_TABLE))
    company(conn)
    conn.execute(sa.text("ALTER TABLE departments DROP COLUMN head_employee_id"))
    conn.execute(sa.text("ALTER TABLE employees DROP COLUMN approval_delegate_id"))
    migration.transfer_leaders(conn)
    assert leaders(conn) == []


def test_without_delegate_column_heads_are_still_taken(conn):
    conn.execute(sa.text(LEADERS_TABLE))
    company(conn)
    conn.execute(sa.text("ALTER TABLE employees DROP COLUMN approval_delegate_id"))
    migration.transfer_leaders(conn)
    assert [(d, e, r) for d, e, r, _, _ in leaders(conn)] == [(10, 1, "HEAD"), (11, 3, "HEAD")]


def test_schema_checks(conn):
    assert migration._has_table(conn, "departments")
    assert not migration._has_table(conn, "department_leaders")
    assert migration._has_column(conn, "departments", "head_employee_id")
    assert not migration._has_column(conn, "departments", "nope")
    assert not migration._has_column(conn, "nope", "id")  # fehlende Tabelle: keine Spalte


class FakeOp:
    """Ersatz für alembic.op auf SQLite: führt die DDL aus und merkt sich die Aufrufe."""

    def __init__(self, conn):
        self.conn = conn
        self.calls: list[tuple] = []
        self.columns: list[str] = []

    def get_bind(self):
        return self.conn

    def create_table(self, name, *columns):
        self.calls.append(("create_table", name))
        self.columns = [c.name for c in columns if isinstance(c, sa.Column)]
        self.conn.execute(sa.text(LEADERS_TABLE))

    def create_index(self, name, table, columns):
        self.calls.append(("create_index", name))
        self.conn.execute(sa.text(f"CREATE INDEX {name} ON {table} ({', '.join(columns)})"))


@pytest.fixture
def fake_op(conn, monkeypatch):
    fake = FakeOp(conn)

    def drop_column(connection, table, column):  # MySQL-Variante liest information_schema
        fake.calls.append(("drop_column", table, column))
        connection.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {column}"))

    monkeypatch.setattr(migration, "op", fake)
    monkeypatch.setattr(migration, "_drop_column", drop_column)
    return fake


def test_upgrade_creates_table_transfers_and_drops_old_columns(conn, fake_op, capsys):
    company(conn)
    migration.upgrade()
    assert fake_op.calls == [
        ("create_table", "department_leaders"),
        ("create_index", "ix_department_leaders_department_id"),
        ("create_index", "ix_department_leaders_employee_id"),
        ("drop_column", "departments", "head_employee_id"),
        ("drop_column", "employees", "approval_delegate_id"),
    ]
    assert fake_op.columns == ["id", "department_id", "employee_id", "role", "deputy_rights", "position"]
    assert [(d, e, r) for d, e, r, _, _ in leaders(conn)] == [(10, 1, "HEAD"), (10, 2, "DEPUTY"), (11, 3, "HEAD")]
    assert not migration._has_column(conn, "departments", "head_employee_id")
    assert "leitet aber keine Abteilung" in capsys.readouterr().out


def test_upgrade_after_aborted_run_continues(conn, fake_op):
    """Erster Lauf brach nach dem Anlegen der Tabelle und dem Löschen der Leitungsspalte ab."""
    conn.execute(sa.text(LEADERS_TABLE))
    company(conn)
    migration.transfer_leaders(conn, log=lambda _: None)
    conn.execute(sa.text("ALTER TABLE departments DROP COLUMN head_employee_id"))
    migration.upgrade()
    assert fake_op.calls == [("drop_column", "employees", "approval_delegate_id")]
    assert len(leaders(conn)) == 3


def test_upgrade_when_everything_is_done_changes_nothing(conn, fake_op):
    conn.execute(sa.text(LEADERS_TABLE))
    conn.execute(sa.text("ALTER TABLE departments DROP COLUMN head_employee_id"))
    conn.execute(sa.text("ALTER TABLE employees DROP COLUMN approval_delegate_id"))
    migration.upgrade()
    assert fake_op.calls == []


def test_downgrade_is_refused():
    with pytest.raises(NotImplementedError, match="Sicherung"):
        migration.downgrade()
