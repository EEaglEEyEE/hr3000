"""Hinweisgebersystem (interne Meldestelle): Schalter in den Einstellungen, Beauftragte, Meldungen,
Nachrichten und Anhänge; dazu neue Werte im Audit-Protokoll und bei den Benachrichtigungen.

Die Enum-Spalten werden aus dem Stand der Datenbank erweitert (vorhandene Werte lesen, fehlende
anhängen) statt aus einer festen Liste – so überschreibt diese Migration keine Werte, die eine
parallel entstandene Migration ergänzt hat, gleich in welcher Reihenfolge beide laufen.

Wiederholbar (MySQL führt DDL ohne Transaktion aus): jeder Schritt prüft erst den Stand.

Revision ID: 0151_whistleblowing
Revises: 0149_report_builder
Create Date: 2026-11-10

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0151_whistleblowing"
down_revision: Union[str, None] = "0149_report_builder"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUDIT_VALUES = ["WHISTLE_OFFICER_CHANGED", "WHISTLE_CASE_VIEWED", "WHISTLE_CASE_CHANGED", "WHISTLE_CASE_DELETED"]
NOTIFICATION_VALUES = ["WHISTLEBLOWING"]
_TABLES = ["whistle_attachments", "whistle_messages", "whistle_cases", "whistle_officers"]


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table)


def _has_column(conn, table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(conn).get_columns(table))


def parse_enum_values(column_type: str) -> list[str]:
    """Werte aus der MySQL-Typangabe, z. B. "enum('A','B')" -> ["A", "B"]."""
    return re.findall(r"'([^']*)'", column_type)


def _change_enum(conn, table: str, column: str, name: str, add: list[str], remove: list[str]) -> None:
    if conn.dialect.name != "mysql":
        return  # SQLite (Tests) speichert Enums als Text ohne feste Werteliste
    row = conn.execute(
        sa.text(
            "SELECT COLUMN_TYPE, IS_NULLABLE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
        ),
        {"t": table, "c": column},
    ).first()
    current = parse_enum_values(row[0])
    target = [v for v in current if v not in remove] + [v for v in add if v not in current]
    if target == current:
        return
    op.alter_column(
        table,
        column,
        existing_type=sa.Enum(*current, name=name),
        type_=sa.Enum(*target, name=name),
        existing_nullable=row[1] == "YES",
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_column(conn, "app_settings", "whistleblowing_enabled"):
        op.add_column(
            "app_settings",
            sa.Column("whistleblowing_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if not _has_table(conn, "whistle_officers"):
        op.create_table(
            "whistle_officers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "created_by_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("tenant_id", "account_id", name="uq_whistle_officers_account"),
        )
    if not _has_table(conn, "whistle_cases"):
        op.create_table(
            "whistle_cases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("case_number", sa.String(12), nullable=False),
            sa.Column("access_code_hash", sa.String(64), nullable=False),
            sa.Column("category", sa.String(20), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("description_encrypted", sa.Text(), nullable=False),
            sa.Column("details_encrypted", sa.Text(), nullable=True),
            sa.Column("anonymous", sa.Boolean(), nullable=False),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
            sa.Column("feedback_at", sa.DateTime(), nullable=True),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("closing_note_encrypted", sa.Text(), nullable=True),
            sa.Column("delete_after", sa.Date(), nullable=True),
            sa.Column("unread_for_office", sa.Boolean(), nullable=False),
            sa.Column("ack_reminder_stage", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("feedback_reminder_stage", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("deletion_reminded", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("tenant_id", "case_number", name="uq_whistle_cases_number"),
        )
    if not _has_table(conn, "whistle_messages"):
        op.create_table(
            "whistle_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("case_id", sa.Integer(), sa.ForeignKey("whistle_cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("body_encrypted", sa.Text(), nullable=False),
            sa.Column("mark", sa.String(20), nullable=True),
            sa.Column(
                "author_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_whistle_messages_case", "whistle_messages", ["case_id"])
    if not _has_table(conn, "whistle_attachments"):
        op.create_table(
            "whistle_attachments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("case_id", sa.Integer(), sa.ForeignKey("whistle_cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("filename_encrypted", sa.Text(), nullable=False),
            sa.Column("content_type", sa.String(100), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("storage_key", sa.String(100), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_whistle_attachments_case", "whistle_attachments", ["case_id"])
    _change_enum(conn, "audit_log_entries", "action", "auditaction", add=AUDIT_VALUES, remove=[])
    _change_enum(conn, "notifications", "type", "notificationtype", add=NOTIFICATION_VALUES, remove=[])


def downgrade() -> None:
    """Entfernt auch alle Meldungen. Die verschlüsselten Anhang-Dateien im Dokumentenspeicher bleiben
    liegen (ohne Tabelle nicht mehr zuzuordnen und ohne Schlüssel nicht lesbar)."""
    conn = op.get_bind()
    quoted = ", ".join(f"'{v}'" for v in AUDIT_VALUES)
    op.execute(f"DELETE FROM audit_log_entries WHERE action IN ({quoted})")
    op.execute("DELETE FROM notifications WHERE type = 'WHISTLEBLOWING'")
    _change_enum(conn, "audit_log_entries", "action", "auditaction", add=[], remove=AUDIT_VALUES)
    _change_enum(conn, "notifications", "type", "notificationtype", add=[], remove=NOTIFICATION_VALUES)
    for table in _TABLES:
        if _has_table(conn, table):
            op.drop_table(table)
    if _has_column(conn, "app_settings", "whistleblowing_enabled"):
        op.drop_column("app_settings", "whistleblowing_enabled")
