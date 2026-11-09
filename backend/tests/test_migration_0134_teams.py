"""Migration 0134 (Teams → Abteilungen): die Datenübernahme transfer_teams gegen ein minimales Schema
in SQLite. Auf Staging war sie zuerst an einer leeren inserted_primary_key gescheitert – die Tests
führen deshalb echtes SQL aus, nicht nur die Modelle."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0134_departments_replace_teams.py"
_spec = importlib.util.spec_from_file_location("migration_0134", _PATH)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)

SCHEMA = (
    "CREATE TABLE departments (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, name TEXT NOT NULL, "
    "parent_id INTEGER, head_employee_id INTEGER)",
    "CREATE TABLE teams (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, name TEXT NOT NULL)",
    "CREATE TABLE accounts (id INTEGER PRIMARY KEY, employee_id INTEGER)",
    "CREATE TABLE supervisor_team_assignments (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL, account_id INTEGER NOT NULL)",
    "CREATE TABLE employees (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, team_id INTEGER, "
    "department_id INTEGER, supervisor_id INTEGER)",
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


def departments(conn) -> dict[str, tuple]:
    rows = conn.execute(sa.text("SELECT name, tenant_id, parent_id, head_employee_id FROM departments ORDER BY id")).all()
    return {name: (tenant, parent, head) for name, tenant, parent, head in rows}


def employee(conn, employee_id: int) -> tuple:
    """(Abteilungsname, abweichende Führungskraft)"""
    return tuple(conn.execute(
        sa.text(
            "SELECT d.name, e.supervisor_id FROM employees e LEFT JOIN departments d ON d.id = e.department_id "
            "WHERE e.id = :id"
        ),
        {"id": employee_id},
    ).one())


def nord_with_lead(conn) -> None:
    """Firma 1: Team „Nord“ mit Leitung 1 (Konto 10). 2 ohne Abteilung, 3 in „Lager“, 4 in „Lager“ mit
    eigener Ausnahme 9, die Leitung selbst ist in „Lager“."""
    insert(conn, "departments", {"id": 50, "tenant_id": 1, "name": "Lager"})
    insert(conn, "teams", {"id": 1, "tenant_id": 1, "name": "Nord"})
    insert(conn, "accounts", {"id": 10, "employee_id": 1})
    insert(conn, "supervisor_team_assignments", {"id": 1, "team_id": 1, "account_id": 10})
    insert(
        conn,
        "employees",
        {"id": 1, "tenant_id": 1, "team_id": 1, "department_id": 50},
        {"id": 2, "tenant_id": 1, "team_id": 1},
        {"id": 3, "tenant_id": 1, "team_id": 1, "department_id": 50},
        {"id": 4, "tenant_id": 1, "team_id": 1, "department_id": 50, "supervisor_id": 9},
        {"id": 9, "tenant_id": 1},
    )


def test_team_becomes_department_with_lead_as_head(conn):
    nord_with_lead(conn)
    migration.transfer_teams(conn)
    assert departments(conn)["Nord"] == (1, None, 1)


def test_members_without_department_move_in(conn):
    nord_with_lead(conn)
    migration.transfer_teams(conn)
    assert employee(conn, 2) == ("Nord", None)


def test_members_elsewhere_keep_department_and_get_lead_as_override(conn):
    nord_with_lead(conn)
    migration.transfer_teams(conn)
    assert employee(conn, 3) == ("Lager", 1)


def test_existing_override_is_kept(conn):
    nord_with_lead(conn)
    migration.transfer_teams(conn)
    assert employee(conn, 4) == ("Lager", 9)


def test_lead_never_becomes_own_supervisor(conn):
    nord_with_lead(conn)
    migration.transfer_teams(conn)
    assert employee(conn, 1) == ("Lager", None)


def test_same_named_department_is_reused_ignoring_case_and_keeps_its_head(conn):
    insert(conn, "departments", {"id": 7, "tenant_id": 1, "name": "VERTRIEB", "head_employee_id": 5})
    insert(conn, "teams", {"id": 1, "tenant_id": 1, "name": "Vertrieb"})
    insert(conn, "accounts", {"id": 10, "employee_id": 1})
    insert(conn, "supervisor_team_assignments", {"id": 1, "team_id": 1, "account_id": 10})
    insert(conn, "employees", {"id": 1, "tenant_id": 1, "team_id": 1}, {"id": 2, "tenant_id": 1, "team_id": 1}, {"id": 5, "tenant_id": 1})
    migration.transfer_teams(conn)
    assert departments(conn) == {"VERTRIEB": (1, None, 5)}
    assert employee(conn, 2) == ("VERTRIEB", None)


def test_same_name_in_other_tenant_is_not_reused(conn):
    insert(conn, "departments", {"id": 7, "tenant_id": 2, "name": "Nord"})
    insert(conn, "teams", {"id": 1, "tenant_id": 1, "name": "Nord"})
    insert(conn, "employees", {"id": 1, "tenant_id": 1, "team_id": 1})
    migration.transfer_teams(conn)
    rows = conn.execute(sa.text("SELECT tenant_id FROM departments WHERE name = 'Nord' ORDER BY tenant_id")).scalars().all()
    assert rows == [1, 2]
    assert employee(conn, 1) == ("Nord", None)


def test_team_without_lead_gets_department_without_head(conn):
    insert(conn, "departments", {"id": 50, "tenant_id": 1, "name": "Lager"})
    insert(conn, "teams", {"id": 1, "tenant_id": 1, "name": "Süd"})
    insert(conn, "employees", {"id": 1, "tenant_id": 1, "team_id": 1}, {"id": 2, "tenant_id": 1, "team_id": 1, "department_id": 50})
    migration.transfer_teams(conn)
    assert departments(conn)["Süd"] == (1, None, None)
    assert employee(conn, 1) == ("Süd", None)
    assert employee(conn, 2) == ("Lager", None)


def test_lead_account_without_employee_is_skipped(conn):
    """Reines Verwaltungskonto (ohne Mitarbeiter) als erste Zuordnung: Leitung wird die nächste mit Mitarbeiter."""
    insert(conn, "teams", {"id": 1, "tenant_id": 1, "name": "Nord"})
    insert(conn, "accounts", {"id": 10, "employee_id": None}, {"id": 11, "employee_id": 3})
    insert(conn, "supervisor_team_assignments", {"id": 1, "team_id": 1, "account_id": 10}, {"id": 2, "team_id": 1, "account_id": 11})
    insert(conn, "employees", {"id": 3, "tenant_id": 1})
    migration.transfer_teams(conn)
    assert departments(conn)["Nord"] == (1, None, 3)


def test_several_leads_take_the_first_and_report_it(conn):
    insert(conn, "teams", {"id": 1, "tenant_id": 1, "name": "Nord"})
    insert(conn, "accounts", {"id": 10, "employee_id": 3}, {"id": 11, "employee_id": 4})
    insert(conn, "supervisor_team_assignments", {"id": 1, "team_id": 1, "account_id": 10}, {"id": 2, "team_id": 1, "account_id": 11})
    insert(conn, "employees", {"id": 3, "tenant_id": 1}, {"id": 4, "tenant_id": 1})
    notes: list[str] = []
    migration.transfer_teams(conn, log=notes.append)
    assert departments(conn)["Nord"] == (1, None, 3)
    assert notes == ["Hinweis: Team „Nord“ hatte 2 Leitungen – übernommen wird die erste als Abteilungsleitung."]


def test_running_twice_changes_nothing_more(conn):
    """Nach einem Abbruch läuft die Migration erneut – nichts darf doppelt entstehen."""
    nord_with_lead(conn)
    migration.transfer_teams(conn)
    first = (departments(conn), [employee(conn, i) for i in (1, 2, 3, 4)])
    migration.transfer_teams(conn)
    assert (departments(conn), [employee(conn, i) for i in (1, 2, 3, 4)]) == first
    assert conn.execute(sa.text("SELECT COUNT(*) FROM departments")).scalar() == 2


def test_without_assignment_table_members_still_move(conn):
    """Abbruch nach dem Löschen von supervisor_team_assignments: ohne Leitungen, Mitglieder trotzdem."""
    conn.execute(sa.text("DROP TABLE supervisor_team_assignments"))
    insert(conn, "teams", {"id": 1, "tenant_id": 1, "name": "Nord"})
    insert(conn, "employees", {"id": 1, "tenant_id": 1, "team_id": 1})
    migration.transfer_teams(conn)
    assert departments(conn)["Nord"] == (1, None, None)
    assert employee(conn, 1) == ("Nord", None)


def test_without_team_column_only_departments_and_heads(conn):
    conn.execute(sa.text("ALTER TABLE employees DROP COLUMN team_id"))
    insert(conn, "teams", {"id": 1, "tenant_id": 1, "name": "Nord"})
    insert(conn, "accounts", {"id": 10, "employee_id": 3})
    insert(conn, "supervisor_team_assignments", {"id": 1, "team_id": 1, "account_id": 10})
    insert(conn, "employees", {"id": 3, "tenant_id": 1})
    migration.transfer_teams(conn)
    assert departments(conn)["Nord"] == (1, None, 3)
    assert employee(conn, 3) == (None, None)


def test_without_teams_table_nothing_happens(conn):
    conn.execute(sa.text("DROP TABLE teams"))
    migration.transfer_teams(conn)
    assert departments(conn) == {}


def test_department_for_returns_new_id(conn):
    new_id = migration._department_for(conn, 1, "Nord")
    assert conn.execute(sa.text("SELECT name FROM departments WHERE id = :id"), {"id": new_id}).scalar() == "Nord"
    assert migration._department_for(conn, 1, "nord") == new_id


def test_department_for_falls_back_to_lookup_without_lastrowid(conn):
    """Treiber ohne lastrowid: die neue Abteilung wird über Firma und Namen gefunden."""

    class NoRowId:
        def __init__(self, inner):
            self.inner = inner

        def execute(self, statement, params=None):
            result = self.inner.execute(statement, params)
            if str(statement).startswith("INSERT"):
                return type("Result", (), {"lastrowid": None})()
            return result

    new_id = migration._department_for(NoRowId(conn), 1, "Nord")
    assert new_id == conn.execute(sa.text("SELECT id FROM departments WHERE name = 'Nord'")).scalar()


def test_schema_checks(conn):
    assert migration._has_table(conn, "teams")
    assert not migration._has_table(conn, "nope")
    assert migration._has_column(conn, "employees", "team_id")
    assert not migration._has_column(conn, "employees", "nope")
    assert not migration._has_foreign_key(conn, "departments", migration.HEAD_FK)


class FakeOp:
    """Ersatz für alembic.op auf SQLite: führt einfache DDL aus und merkt sich die Aufrufe."""

    def __init__(self, conn):
        self.conn = conn
        self.calls: list[tuple] = []

    def get_bind(self):
        return self.conn

    def add_column(self, table, column):
        self.calls.append(("add_column", table, column.name))
        self.conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column.name} INTEGER"))

    def create_foreign_key(self, name, *args, **kwargs):
        self.calls.append(("create_foreign_key", name))

    def drop_table(self, table):
        self.calls.append(("drop_table", table))
        self.conn.execute(sa.text(f"DROP TABLE {table}"))


@pytest.fixture
def fake_op(conn, monkeypatch):
    fake = FakeOp(conn)

    def drop_column(connection, table, column):  # MySQL-Variante liest information_schema
        fake.calls.append(("drop_column", table, column))
        connection.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {column}"))

    monkeypatch.setattr(migration, "op", fake)
    monkeypatch.setattr(migration, "_drop_column", drop_column)
    return fake


def departments_without_head(conn, *, with_head_fk: bool = False) -> None:
    conn.execute(sa.text("DROP TABLE departments"))
    if with_head_fk:  # Stand nach einem abgebrochenen ersten Lauf: Spalte und Fremdschlüssel schon da
        conn.execute(sa.text(
            "CREATE TABLE departments (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, name TEXT NOT NULL, "
            f"parent_id INTEGER, head_employee_id INTEGER, CONSTRAINT {migration.HEAD_FK} "
            "FOREIGN KEY (head_employee_id) REFERENCES employees (id) ON DELETE SET NULL)"
        ))
    else:
        conn.execute(sa.text(
            "CREATE TABLE departments (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, name TEXT NOT NULL, parent_id INTEGER)"
        ))


def test_upgrade_adds_head_transfers_and_drops_teams(conn, fake_op):
    departments_without_head(conn)
    insert(conn, "teams", {"id": 1, "tenant_id": 1, "name": "Nord"})
    insert(conn, "accounts", {"id": 10, "employee_id": 1})
    insert(conn, "supervisor_team_assignments", {"id": 1, "team_id": 1, "account_id": 10})
    insert(conn, "employees", {"id": 1, "tenant_id": 1, "team_id": 1}, {"id": 2, "tenant_id": 1, "team_id": 1})
    migration.upgrade()
    assert fake_op.calls == [
        ("add_column", "departments", "head_employee_id"),
        ("create_foreign_key", migration.HEAD_FK),
        ("drop_table", "supervisor_team_assignments"),
        ("drop_column", "employees", "team_id"),
        ("drop_table", "teams"),
    ]
    assert departments(conn) == {"Nord": (1, None, 1)}
    assert employee(conn, 2) == ("Nord", None)
    assert not migration._has_table(conn, "teams")
    assert not migration._has_column(conn, "employees", "team_id")


def test_upgrade_after_aborted_run_skips_what_exists(conn, fake_op):
    """Staging 09.11.2026: erster Lauf brach nach Spalte und Fremdschlüssel ab – der zweite muss durchlaufen."""
    departments_without_head(conn, with_head_fk=True)
    insert(conn, "teams", {"id": 1, "tenant_id": 1, "name": "Verkauf"})
    insert(conn, "employees", {"id": 1, "tenant_id": 1, "team_id": 1})
    migration.upgrade()
    assert ("add_column", "departments", "head_employee_id") not in fake_op.calls
    assert ("create_foreign_key", migration.HEAD_FK) not in fake_op.calls
    assert employee(conn, 1) == ("Verkauf", None)
    assert not migration._has_table(conn, "teams")


def test_upgrade_when_everything_is_done_changes_nothing(conn, fake_op):
    departments_without_head(conn, with_head_fk=True)
    for statement in ("DROP TABLE supervisor_team_assignments", "DROP TABLE teams", "ALTER TABLE employees DROP COLUMN team_id"):
        conn.execute(sa.text(statement))
    migration.upgrade()
    assert fake_op.calls == []


def test_downgrade_is_refused():
    with pytest.raises(NotImplementedError, match="Sicherung"):
        migration.downgrade()
