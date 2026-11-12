"""Zeiten selbst eintragen (Stundenzettel): Schalter je Firma, Antragsart an den Korrekturanträgen,
Quelle "selbst eingetragen" an den Stempelungen und zwei Audit-Aktionen.

Neue Enum-Werte (punches.source, audit_log_entries.action) werden an die Liste angehängt, die gerade
in der Datenbank steht (statt eine feste Liste zu setzen) – so gehen keine Werte anderer, parallel
entstandener Migrationen verloren. Nur MySQL kennt echte Enums; andere Datenbanken brauchen nichts.

Revision ID: 0157_self_time_entry
Revises: 0156_recruiting_enums
Create Date: 2026-11-11

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0157_self_time_entry"
down_revision: Union[str, None] = "0156_recruiting_enums"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOURCE_VALUES = ("SELF_ENTRY",)
_AUDIT_VALUES = ("TIME_ENTRY_CREATED", "TIME_ENTRY_DELETED")
# (Tabelle, Spalte, Enum-Name, neue Werte)
_TARGETS = (
    ("punches", "source", "punchsource", _SOURCE_VALUES),
    ("audit_log_entries", "action", "auditaction", _AUDIT_VALUES),
)
_SETTINGS_COLUMNS = (
    ("self_time_entry_enabled", sa.Boolean(), sa.false()),
    ("self_time_entry_approval", sa.Boolean(), sa.true()),
    ("self_time_entry_backdate_days", sa.Integer(), sa.text("7")),
)


def parse_enum_values(column_type: str) -> list[str]:
    """Werte aus der MySQL-Typangabe ``enum('A','B')``."""
    return re.findall(r"'((?:[^']|'')*)'", column_type)


def merged_values(current: list[str], added: Sequence[str]) -> list[str]:
    return current + [value for value in added if value not in current]


def _current_values(conn, table: str, column: str) -> list[str]:
    row = conn.execute(
        sa.text(
            "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return parse_enum_values(row[0]) if row else []


def _columns(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    existing = _columns(conn, "app_settings")
    for name, type_, default in _SETTINGS_COLUMNS:
        if name not in existing:
            op.add_column("app_settings", sa.Column(name, type_, nullable=False, server_default=default))
    if "kind" not in _columns(conn, "punch_correction_requests"):
        op.add_column(
            "punch_correction_requests",
            sa.Column(
                "kind", sa.Enum("CORRECTION", "TIME_ENTRY", name="correctionrequestkind"),
                nullable=False, server_default="CORRECTION",
            ),
        )
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
    # Selbst eingetragene Stempelungen bleiben erhalten – sie gelten danach als HR-Buchung.
    op.execute("UPDATE punches SET source = 'MANUAL_HR' WHERE source = 'SELF_ENTRY'")
    if conn.dialect.name == "mysql":
        for table, column, name, added in _TARGETS:
            current = _current_values(conn, table, column)
            target = [value for value in current if value not in added]
            if not current or target == current:
                continue
            if table == "audit_log_entries":
                placeholders = ", ".join(f"'{value}'" for value in added)
                op.execute(f"DELETE FROM `{table}` WHERE `{column}` IN ({placeholders})")
            op.alter_column(
                table, column, existing_type=sa.Enum(*current, name=name), type_=sa.Enum(*target, name=name),
                existing_nullable=False,
            )
    if "kind" in _columns(conn, "punch_correction_requests"):
        with op.batch_alter_table("punch_correction_requests") as batch:
            batch.drop_column("kind")
    existing = _columns(conn, "app_settings")
    with op.batch_alter_table("app_settings") as batch:
        for name, _, _ in _SETTINGS_COLUMNS:
            if name in existing:
                batch.drop_column(name)
