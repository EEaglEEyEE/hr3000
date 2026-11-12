"""Eigene Rollen je Firma: Tabelle roles, accounts.custom_role_id, Audit-Aktion ROLE_CHANGED.

Wiederholbar (MySQL führt DDL ohne Transaktion aus): jeder Schritt prüft erst den Stand.

Revision ID: 0136_custom_roles
Revises: 0135_department_leaders
Create Date: 2026-11-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0136_custom_roles"
down_revision: Union[str, None] = "0135_department_leaders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = ['PUNCH_CORRECTED', 'PUNCH_DELETED', 'EMPLOYEE_HR_ROLE_CHANGED', 'ABSENCE_DECIDED', 'EMPLOYEE_CREATED', 'SETTINGS_CHANGED', 'HR_USER_CREATED', 'HR_USER_DELETED', 'TEAM_CREATED', 'TEAM_UPDATED', 'TEAM_DELETED', 'TENANT_ADMIN_EMAIL_CHANGED', 'EMPLOYEES_BULK_IMPORTED', 'EMPLOYEE_DATA_EXPORTED', 'EMPLOYEE_ANONYMIZED', 'EMPLOYEE_WORK_TIME_MODEL_SET', 'EMPLOYEE_PASSWORD_RESET', 'CONTRACT_CHANGED', 'COMPENSATION_CHANGED', 'COMPENSATION_VIEWED', 'DOCUMENT_UPLOADED', 'DOCUMENT_UPDATED', 'DOCUMENT_DELETED', 'DOCUMENT_ACCESSED', 'PERIOD_SUBMITTED', 'PERIOD_CONFIRMED', 'PERIOD_DISPUTED', 'PERIOD_CLOSED', 'PERIOD_REOPENED', 'CHECKLIST_STARTED', 'SURCHARGE_RULES_CHANGED', 'BALANCE_ADJUSTED', 'PUNCH_CORRECTION_DECIDED', 'EMPLOYEE_CARD_REGISTERED', 'EMPLOYEE_PIN_SET_AT_KIOSK', 'LOGIN', 'LEAVE_ADJUSTED', 'DEVICE_LOGIN_REJECTED', 'TWO_FACTOR_CHANGED', 'DEPARTMENT_CHANGED', 'PERSONAL_DATA_CHANGED', 'COST_CENTERS_CHANGED', 'ATTRIBUTE_CHANGED', 'DEVICE_ENROLLMENT']
_AUDIT_OLD = sa.Enum(*_AUDIT_BASE, name="auditaction")
_AUDIT_NEW = sa.Enum(*_AUDIT_BASE, "ROLE_CHANGED", name="auditaction")


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table)


def _has_column(conn, table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(conn).get_columns(table))


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn, "roles"):
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column("permissions", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
        )
    if not _has_column(conn, "accounts", "custom_role_id"):
        op.add_column("accounts", sa.Column("custom_role_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_accounts_custom_role_id", "accounts", "roles", ["custom_role_id"], ["id"], ondelete="SET NULL"
        )
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_OLD, type_=_AUDIT_NEW, existing_nullable=False)


def downgrade() -> None:
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_NEW, type_=_AUDIT_OLD, existing_nullable=False)
    op.drop_constraint("fk_accounts_custom_role_id", "accounts", type_="foreignkey")
    op.drop_column("accounts", "custom_role_id")
    op.drop_table("roles")
