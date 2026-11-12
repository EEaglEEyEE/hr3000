"""Projektzeiterfassung: Kunden, Projekte, Projekt und Tätigkeitsnotiz an der Stempelung, zwei
Schalter je Firma und die Audit-Aktion PROJECT_CHANGED.

Der neue Audit-Wert wird an die Liste angehängt, die gerade in der Datenbank steht (nur MySQL kennt
echte Enums) – so gehen keine Werte anderer, parallel entstandener Migrationen verloren.

Revision ID: 0158_project_times
Revises: 0157_self_time_entry
Create Date: 2026-11-11

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0158_project_times"
down_revision: Union[str, None] = "0157_self_time_entry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_VALUES = ("PROJECT_CHANGED",)
_SETTINGS_COLUMNS = ("project_times_enabled", "project_required")


def parse_enum_values(column_type: str) -> list[str]:
    """Werte aus der MySQL-Typangabe ``enum('A','B')``."""
    return re.findall(r"'((?:[^']|'')*)'", column_type)


def merged_values(current: list[str], added: Sequence[str]) -> list[str]:
    return current + [value for value in added if value not in current]


def _current_audit_values(conn) -> list[str]:
    row = conn.execute(
        sa.text(
            "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'audit_log_entries' AND COLUMN_NAME = 'action'"
        )
    ).first()
    return parse_enum_values(row[0]) if row else []


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "customers" not in tables:
        op.create_table(
            "customers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "name", name="uq_customers_tenant_name"),
        )
    if "projects" not in tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("number", sa.String(40), nullable=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
            sa.Column("cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.id"), nullable=True),
            sa.Column("billable", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("valid_from", sa.Date(), nullable=True),
            sa.Column("valid_to", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "number", name="uq_projects_tenant_number"),
        )
    punch_columns = _columns(conn, "punches")
    if "project_id" not in punch_columns:
        with op.batch_alter_table("punches") as batch:
            batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_punches_project_id", "projects", ["project_id"], ["id"])
            batch.create_index("ix_punches_project_id", ["project_id"])
    if "activity_note" not in punch_columns:
        op.add_column("punches", sa.Column("activity_note", sa.String(200), nullable=True))
    settings_columns = _columns(conn, "app_settings")
    for name in _SETTINGS_COLUMNS:
        if name not in settings_columns:
            op.add_column("app_settings", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))
    if conn.dialect.name != "mysql":
        return
    current = _current_audit_values(conn)
    target = merged_values(current, _AUDIT_VALUES)
    if current and target != current:
        op.alter_column(
            "audit_log_entries", "action", existing_type=sa.Enum(*current, name="auditaction"),
            type_=sa.Enum(*target, name="auditaction"), existing_nullable=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "mysql":
        current = _current_audit_values(conn)
        target = [value for value in current if value not in _AUDIT_VALUES]
        if current and target != current:
            op.execute("DELETE FROM audit_log_entries WHERE action = 'PROJECT_CHANGED'")
            op.alter_column(
                "audit_log_entries", "action", existing_type=sa.Enum(*current, name="auditaction"),
                type_=sa.Enum(*target, name="auditaction"), existing_nullable=False,
            )
    settings_columns = _columns(conn, "app_settings")
    with op.batch_alter_table("app_settings") as batch:
        for name in _SETTINGS_COLUMNS:
            if name in settings_columns:
                batch.drop_column(name)
    punch_columns = _columns(conn, "punches")
    if "project_id" in punch_columns or "activity_note" in punch_columns:
        foreign_keys = {fk["name"] for fk in sa.inspect(conn).get_foreign_keys("punches")}
        indexes = {ix["name"] for ix in sa.inspect(conn).get_indexes("punches")}
        with op.batch_alter_table("punches") as batch:
            if "fk_punches_project_id" in foreign_keys:
                batch.drop_constraint("fk_punches_project_id", type_="foreignkey")
            if "ix_punches_project_id" in indexes:
                batch.drop_index("ix_punches_project_id")
            if "project_id" in punch_columns:
                batch.drop_column("project_id")
            if "activity_note" in punch_columns:
                batch.drop_column("activity_note")
    tables = _tables(conn)
    if "projects" in tables:
        op.drop_table("projects")
    if "customers" in tables:
        op.drop_table("customers")
