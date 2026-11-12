"""Vorbereitende Lohnbuchhaltung: Tabelle payroll_releases, Schalter
app_settings.payroll_accounting_enabled (Standard aus), Audit-Aktionen.

Wiederholbar (MySQL führt DDL ohne Transaktion aus): jeder Schritt prüft erst den Stand.

Revision ID: 0137_payroll_accounting
Revises: 0136_custom_roles
Create Date: 2026-11-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision: str = "0137_payroll_accounting"
down_revision: Union[str, None] = "0136_custom_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = ['PUNCH_CORRECTED', 'PUNCH_DELETED', 'EMPLOYEE_HR_ROLE_CHANGED', 'ABSENCE_DECIDED', 'EMPLOYEE_CREATED', 'SETTINGS_CHANGED', 'HR_USER_CREATED', 'HR_USER_DELETED', 'TEAM_CREATED', 'TEAM_UPDATED', 'TEAM_DELETED', 'TENANT_ADMIN_EMAIL_CHANGED', 'EMPLOYEES_BULK_IMPORTED', 'EMPLOYEE_DATA_EXPORTED', 'EMPLOYEE_ANONYMIZED', 'EMPLOYEE_WORK_TIME_MODEL_SET', 'EMPLOYEE_PASSWORD_RESET', 'CONTRACT_CHANGED', 'COMPENSATION_CHANGED', 'COMPENSATION_VIEWED', 'DOCUMENT_UPLOADED', 'DOCUMENT_UPDATED', 'DOCUMENT_DELETED', 'DOCUMENT_ACCESSED', 'PERIOD_SUBMITTED', 'PERIOD_CONFIRMED', 'PERIOD_DISPUTED', 'PERIOD_CLOSED', 'PERIOD_REOPENED', 'CHECKLIST_STARTED', 'SURCHARGE_RULES_CHANGED', 'BALANCE_ADJUSTED', 'PUNCH_CORRECTION_DECIDED', 'EMPLOYEE_CARD_REGISTERED', 'EMPLOYEE_PIN_SET_AT_KIOSK', 'LOGIN', 'LEAVE_ADJUSTED', 'DEVICE_LOGIN_REJECTED', 'TWO_FACTOR_CHANGED', 'DEPARTMENT_CHANGED', 'PERSONAL_DATA_CHANGED', 'COST_CENTERS_CHANGED', 'ATTRIBUTE_CHANGED', 'DEVICE_ENROLLMENT', 'ROLE_CHANGED']
_AUDIT_OLD = sa.Enum(*_AUDIT_BASE, name="auditaction")
_AUDIT_NEW = sa.Enum(
    *_AUDIT_BASE, "PAYROLL_RELEASED", "PAYROLL_RELEASE_REVOKED", "PAYROLL_ACCOUNTING_ACCESSED", name="auditaction"
)
_LARGE_TEXT = sa.Text().with_variant(MEDIUMTEXT(), "mysql")


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table)


def _has_column(conn, table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(conn).get_columns(table))


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn, "payroll_releases"):
        op.create_table(
            "payroll_releases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("released_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("released_by_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=True),
            sa.Column("employee_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("open_closures", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("snapshot", _LARGE_TEXT, nullable=False),
            sa.Column("csv_file", _LARGE_TEXT, nullable=False),
            sa.Column("datev_file", _LARGE_TEXT, nullable=True),
            sa.UniqueConstraint("tenant_id", "year", "month", name="uq_payroll_releases_month"),
        )
    if not _has_column(conn, "app_settings", "payroll_accounting_enabled"):
        op.add_column(
            "app_settings",
            sa.Column("payroll_accounting_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_OLD, type_=_AUDIT_NEW, existing_nullable=False)


def downgrade() -> None:
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_NEW, type_=_AUDIT_OLD, existing_nullable=False)
    op.drop_column("app_settings", "payroll_accounting_enabled")
    op.drop_table("payroll_releases")
