"""Mehrere Leitungen und Stellvertretungen je Abteilung (Entscheidung 09.11.2026).

- Neue Tabelle department_leaders (Abteilung, Mitarbeiter, Rolle HEAD/DEPUTY, Rechte einer
  Stellvertretung STANDBY/FULL/ABSENCE, Reihenfolge).
- Die bisherige Leitung (departments.head_employee_id) wird HEAD.
- Die persönliche „Vertretung bei Genehmigungen“ (employees.approval_delegate_id) geht in den
  Stellvertretungen auf: Wer eine Abteilung leitet und eine Vertretung hatte, bekommt diese dort als
  Stellvertretung mit STANDBY (sieht immer, entscheidet bei Abwesenheit) – so verhielt sich die
  Vertretung bisher beim Entscheiden.
- Danach entfallen departments.head_employee_id und employees.approval_delegate_id.

Wiederholbar (MySQL führt DDL ohne Transaktion aus): jeder Schritt prüft erst den Stand.
Zurück nur über die Sicherung vor dem Rollout.

Revision ID: 0135_department_leaders
Revises: 0134_departments_replace_teams
Create Date: 2026-11-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0135_department_leaders"
down_revision: Union[str, None] = "0134_departments_replace_teams"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table)


def _has_column(conn, table: str, column: str) -> bool:
    return _has_table(conn, table) and any(c["name"] == column for c in sa.inspect(conn).get_columns(table))


def _drop_column(conn, table: str, column: str) -> None:
    """MySQL: erst Fremdschlüssel und eindeutige Indizes der Spalte entfernen, dann die Spalte (Namen
    aus information_schema, wie in 0119_accounts und 0134)."""
    params = {"t": table, "c": column}
    for (name,) in conn.execute(sa.text(
        "SELECT DISTINCT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = :t AND COLUMN_NAME = :c AND REFERENCED_TABLE_NAME IS NOT NULL"), params).all():
        op.execute(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{name}`")
    for (name,) in conn.execute(sa.text(
        "SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = :t AND COLUMN_NAME = :c AND INDEX_NAME <> 'PRIMARY' AND NON_UNIQUE = 0"), params).all():
        op.execute(f"ALTER TABLE `{table}` DROP INDEX `{name}`")
    op.execute(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")


def _add_leader(conn, department_id: int, employee_id: int, role: str) -> bool:
    """Trägt die Person ein, wenn sie in der Abteilung noch nicht steht; True = neu eingetragen."""
    exists = conn.execute(
        sa.text("SELECT 1 FROM department_leaders WHERE department_id = :d AND employee_id = :e"),
        {"d": department_id, "e": employee_id},
    ).first()
    if exists is not None:
        return False
    position = conn.execute(
        sa.text("SELECT COUNT(*) FROM department_leaders WHERE department_id = :d"), {"d": department_id}
    ).scalar()
    conn.execute(
        sa.text(
            "INSERT INTO department_leaders (department_id, employee_id, role, deputy_rights, position) "
            "VALUES (:d, :e, :r, 'STANDBY', :p)"
        ),
        {"d": department_id, "e": employee_id, "r": role, "p": position},
    )
    return True


def transfer_leaders(conn, log=print) -> None:
    """Leitung → HEAD, persönliche Vertretung einer Leitung → DEPUTY (STANDBY). Nur portables SQL,
    damit Tests es mit SQLite prüfen können; ein zweiter Lauf trägt nichts doppelt ein."""
    if _has_column(conn, "departments", "head_employee_id"):
        for department_id, head in conn.execute(
            sa.text("SELECT id, head_employee_id FROM departments WHERE head_employee_id IS NOT NULL ORDER BY id")
        ).all():
            _add_leader(conn, department_id, head, "HEAD")
    if not _has_column(conn, "employees", "approval_delegate_id"):
        return
    pairs = conn.execute(
        sa.text(
            "SELECT id, approval_delegate_id FROM employees WHERE approval_delegate_id IS NOT NULL "
            "AND approval_delegate_id <> id ORDER BY id"
        )
    ).all()
    for head, delegate in pairs:
        departments = conn.execute(
            sa.text("SELECT department_id FROM department_leaders WHERE employee_id = :e AND role = 'HEAD' ORDER BY department_id"),
            {"e": head},
        ).scalars().all()
        if not departments:
            log(f"Hinweis: Mitarbeiter {head} hatte eine Vertretung bei Genehmigungen ({delegate}), leitet aber keine "
                "Abteilung – sie entfällt.")
        for department_id in departments:
            _add_leader(conn, department_id, delegate, "DEPUTY")


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn, "department_leaders"):
        op.create_table(
            "department_leaders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="CASCADE"), nullable=False),
            sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(10), nullable=False),
            sa.Column("deputy_rights", sa.String(10), nullable=False, server_default="STANDBY"),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("department_id", "employee_id", name="uq_department_leaders"),
        )
        op.create_index("ix_department_leaders_department_id", "department_leaders", ["department_id"])
        op.create_index("ix_department_leaders_employee_id", "department_leaders", ["employee_id"])

    transfer_leaders(conn)

    if _has_column(conn, "departments", "head_employee_id"):
        _drop_column(conn, "departments", "head_employee_id")
    if _has_column(conn, "employees", "approval_delegate_id"):
        _drop_column(conn, "employees", "approval_delegate_id")


def downgrade() -> None:
    raise NotImplementedError("Zurück nur über die Sicherung vor dem Rollout (scripts/backup_db.sh).")
