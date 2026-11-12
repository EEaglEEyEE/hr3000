"""Recruiting: neue Werte in den Enums für Audit-Log und Benachrichtigungen.

Die Werte werden an die Liste angehängt, die gerade in der Datenbank steht (statt eine feste Liste
zu setzen): So gehen Werte nicht verloren, die eine andere, parallel entstandene Migration ergänzt
hat – unabhängig von der Reihenfolge. Nur MySQL kennt hier echte Enums; andere Datenbanken speichern
die Werte als Text und brauchen nichts.

Revision ID: 0156_recruiting_enums
Revises: 0155_recruiting_applications
Create Date: 2026-11-10

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0156_recruiting_enums"
down_revision: Union[str, None] = "0155_recruiting_applications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_VALUES = (
    "RECRUITING_JOB_CHANGED",
    "RECRUITING_APPLICATION_CHANGED",
    "RECRUITING_ATTACHMENT_ACCESSED",
    "RECRUITING_DELETED",
)
_NOTIFICATION_VALUES = ("RECRUITING_APPLICATION",)
# (Tabelle, Spalte, Enum-Name, neue Werte)
_TARGETS = (
    ("audit_log_entries", "action", "auditaction", _AUDIT_VALUES),
    ("notifications", "type", "notificationtype", _NOTIFICATION_VALUES),
)


def parse_enum_values(column_type: str) -> list[str]:
    """Werte aus der MySQL-Typangabe ``enum('A','B')``."""
    return re.findall(r"'((?:[^']|'')*)'", column_type)


def _current_values(conn, table: str, column: str) -> list[str]:
    row = conn.execute(
        sa.text(
            "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return parse_enum_values(row[0]) if row else []


def merged_values(current: list[str], added: Sequence[str]) -> list[str]:
    return current + [value for value in added if value not in current]


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "mysql":
        return
    for table, column, name, added in _TARGETS:
        current = _current_values(conn, table, column)
        target = merged_values(current, added)
        if not current or target == current:
            continue
        op.alter_column(
            table, column, existing_type=sa.Enum(*current, name=name), type_=sa.Enum(*target, name=name),
            existing_nullable=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "mysql":
        return
    for table, column, name, added in _TARGETS:
        current = _current_values(conn, table, column)
        target = [value for value in current if value not in added]
        if not current or target == current:
            continue
        placeholders = ", ".join(f"'{value}'" for value in added)
        op.execute(f"DELETE FROM `{table}` WHERE `{column}` IN ({placeholders})")
        op.alter_column(
            table, column, existing_type=sa.Enum(*current, name=name), type_=sa.Enum(*target, name=name),
            existing_nullable=False,
        )
