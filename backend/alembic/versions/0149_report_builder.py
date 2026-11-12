"""Berichts-Builder: gespeicherte eigene Berichte, Schalter in den Einstellungen, Audit-Werte.

- Neue Tabelle saved_reports (Firma, Besitzer-Konto, Name, Beschreibung, Definition als JSON, geteilt).
- app_settings.custom_reports_enabled (Standard aus).
- auditaction um REPORT_CHANGED, REPORT_RUN, REPORT_EXPORTED erweitert. Die vorhandenen Werte werden
  aus der Datenbank gelesen statt hier aufgezählt: so gehen Werte nicht verloren, die parallel
  entwickelte Migrationen (0136–0148) ergänzen, egal in welcher Reihenfolge sie zusammengeführt werden.

Wiederholbar (MySQL führt DDL ohne Transaktion aus): jeder Schritt prüft erst den Stand.

Revision ID: 0149_report_builder
Revises: 0141_settled_overtime
Create Date: 2026-11-10

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0149_report_builder"
down_revision: Union[str, None] = "0141_settled_overtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_AUDIT_ACTIONS = ("REPORT_CHANGED", "REPORT_RUN", "REPORT_EXPORTED")


def parse_enum_values(column_type: str) -> list[str]:
    """Werte aus MySQLs COLUMN_TYPE, z. B. "enum('A','B')" -> ["A", "B"]."""
    return re.findall(r"'((?:[^']|'')*)'", column_type)


def enum_with(values: list[str], extra: Sequence[str]) -> list[str]:
    """Vorhandene Werte in ihrer Reihenfolge, fehlende neue hinten angehängt."""
    return values + [value for value in extra if value not in values]


def enum_without(values: list[str], removed: Sequence[str]) -> list[str]:
    return [value for value in values if value not in removed]


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table)


def _has_column(conn, table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(conn).get_columns(table))


def _audit_values(conn) -> list[str] | None:
    """Aktuelle Werte der Spalte audit_log_entries.action; None außerhalb von MySQL (dort ist das
    Enum keine eigene Typdefinition der Spalte, z. B. SQLite in Tests)."""
    if conn.dialect.name != "mysql":
        return None
    column_type = conn.execute(sa.text(
        "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'audit_log_entries' AND COLUMN_NAME = 'action'"
    )).scalar()
    return parse_enum_values(column_type or "")


def _set_audit_values(old: list[str], new: list[str]) -> None:
    if old == new:
        return
    op.alter_column(
        "audit_log_entries", "action",
        existing_type=sa.Enum(*old, name="auditaction"), type_=sa.Enum(*new, name="auditaction"), existing_nullable=False,
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn, "saved_reports"):
        op.create_table(
            "saved_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("owner_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column("definition", sa.Text(), nullable=False),
            sa.Column("shared", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_saved_reports_tenant_id", "saved_reports", ["tenant_id"])
    if not _has_column(conn, "app_settings", "custom_reports_enabled"):
        op.add_column("app_settings", sa.Column("custom_reports_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    values = _audit_values(conn)
    if values is not None:
        _set_audit_values(values, enum_with(values, NEW_AUDIT_ACTIONS))


def downgrade() -> None:
    conn = op.get_bind()
    quoted = ", ".join(f"'{value}'" for value in NEW_AUDIT_ACTIONS)
    op.execute(f"DELETE FROM audit_log_entries WHERE action IN ({quoted})")
    values = _audit_values(conn)
    if values is not None:
        _set_audit_values(values, enum_without(values, NEW_AUDIT_ACTIONS))
    if _has_column(conn, "app_settings", "custom_reports_enabled"):
        op.drop_column("app_settings", "custom_reports_enabled")
    if _has_table(conn, "saved_reports"):
        op.drop_index("ix_saved_reports_tenant_id", table_name="saved_reports")
        op.drop_table("saved_reports")
