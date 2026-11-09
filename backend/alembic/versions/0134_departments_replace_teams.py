"""Abteilungen statt Teams (Entscheidung 09.11.2026): Abteilungen bekommen eine Leitung
(departments.head_employee_id) – sie ist die Führungskraft der Mitarbeiter darin. Teams entfallen.

Übernahme je Team:
1. Abteilung mit dem Namen des Teams (gibt es sie in der Firma schon – Groß/Klein egal –, wird sie
   genutzt, sonst neu als oberste Ebene angelegt).
2. Teamleitung (erste Zuordnung mit Mitarbeiter-Konto) wird Leitung der Abteilung, wenn diese noch
   keine hat.
3. Teammitglieder ohne Abteilung kommen in diese Abteilung.
4. Teammitglieder, die schon in einer anderen Abteilung sind, behalten sie; damit die Teamleitung
   weiter für sie zuständig bleibt, wird sie als abweichende Führungskraft eingetragen (nur, wenn noch
   keine eingetragen ist).
Danach werden supervisor_team_assignments, employees.team_id und teams entfernt.

Wiederholbar: MySQL führt DDL ohne Transaktion aus. Bricht die Migration mittendrin ab, bleiben
schon angelegte Spalten oder gelöschte Tabellen bestehen. Jeder Schritt prüft deshalb erst den Stand.

Zurück nur über die Sicherung vor dem Rollout (die Team-Zuordnungen lassen sich nicht wiederherstellen).

Revision ID: 0134_departments_replace_teams
Revises: 0133_break_windows
Create Date: 2026-11-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0134_departments_replace_teams"
down_revision: Union[str, None] = "0133_break_windows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

HEAD_FK = "fk_departments_head_employee_id"


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table)


def _has_column(conn, table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(conn).get_columns(table))


def _has_foreign_key(conn, table: str, name: str) -> bool:
    return any(fk.get("name") == name for fk in sa.inspect(conn).get_foreign_keys(table))


def _drop_column(conn, table: str, column: str) -> None:
    """MySQL: erst Fremdschlüssel und eindeutige Indizes der Spalte entfernen, dann die Spalte (Namen
    aus information_schema, wie in 0119_accounts)."""
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


def _department_for(conn, tenant_id: int, name: str) -> int:
    """Gleichnamige Abteilung der Firma (Groß/Klein egal) oder eine neue auf oberster Ebene."""
    params = {"t": tenant_id, "n": name}
    find = sa.text("SELECT id FROM departments WHERE tenant_id = :t AND LOWER(name) = LOWER(:n) ORDER BY id")
    existing = conn.execute(find, params).first()
    if existing is not None:
        return existing[0]
    result = conn.execute(sa.text("INSERT INTO departments (tenant_id, name) VALUES (:t, :n)"), params)
    if result.lastrowid:
        return result.lastrowid
    return conn.execute(find, params).first()[0]


def transfer_teams(conn, log=print) -> None:
    """Teams → Abteilungen (Schritte 1–4 oben). Nur portables SQL, damit Tests es mit SQLite prüfen
    können; läuft auch nach einem Abbruch erneut, ohne etwas doppelt anzulegen."""
    if not _has_table(conn, "teams"):
        return
    with_leads = _has_table(conn, "supervisor_team_assignments")
    with_members = _has_column(conn, "employees", "team_id")
    teams = conn.execute(sa.text("SELECT id, tenant_id, name FROM teams ORDER BY id")).all()
    for team_id, tenant_id, name in teams:
        department_id = _department_for(conn, tenant_id, name)
        leads = []
        if with_leads:
            leads = conn.execute(
                sa.text(
                    "SELECT a.employee_id FROM supervisor_team_assignments s JOIN accounts a ON a.id = s.account_id "
                    "WHERE s.team_id = :team AND a.employee_id IS NOT NULL ORDER BY s.id"
                ),
                {"team": team_id},
            ).scalars().all()
        lead = leads[0] if leads else None
        if len(leads) > 1:
            log(f"Hinweis: Team „{name}“ hatte {len(leads)} Leitungen – übernommen wird die erste als Abteilungsleitung.")
        if lead is not None:
            conn.execute(
                sa.text("UPDATE departments SET head_employee_id = :lead WHERE id = :d AND head_employee_id IS NULL"),
                {"lead": lead, "d": department_id},
            )
        if not with_members:
            continue
        conn.execute(
            sa.text("UPDATE employees SET department_id = :d WHERE team_id = :team AND department_id IS NULL"),
            {"d": department_id, "team": team_id},
        )
        if lead is not None:
            conn.execute(
                sa.text(
                    "UPDATE employees SET supervisor_id = :lead WHERE team_id = :team AND department_id <> :d "
                    "AND supervisor_id IS NULL AND id <> :lead"
                ),
                {"lead": lead, "team": team_id, "d": department_id},
            )


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_column(conn, "departments", "head_employee_id"):
        op.add_column("departments", sa.Column("head_employee_id", sa.Integer(), nullable=True))
    if not _has_foreign_key(conn, "departments", HEAD_FK):
        op.create_foreign_key(HEAD_FK, "departments", "employees", ["head_employee_id"], ["id"], ondelete="SET NULL")

    transfer_teams(conn)

    if _has_table(conn, "supervisor_team_assignments"):
        op.drop_table("supervisor_team_assignments")
    if _has_column(conn, "employees", "team_id"):
        _drop_column(conn, "employees", "team_id")
    if _has_table(conn, "teams"):
        op.drop_table("teams")


def downgrade() -> None:
    raise NotImplementedError("Zurück nur über die Sicherung vor dem Rollout (scripts/backup_db.sh).")
