"""Korrekturen am Urlaubskonto (± Tage, optional mit Verfallsdatum) und Audit-Aktion dazu.

Revision ID: 0115_leave_adjustments
Revises: 0114_seniority_leave
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0115_leave_adjustments"
down_revision: Union[str, None] = "0114_seniority_leave"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = ['PUNCH_CORRECTED', 'PUNCH_DELETED', 'EMPLOYEE_HR_ROLE_CHANGED', 'ABSENCE_DECIDED', 'EMPLOYEE_CREATED', 'SETTINGS_CHANGED', 'HR_USER_CREATED', 'HR_USER_DELETED', 'TEAM_CREATED', 'TEAM_UPDATED', 'TEAM_DELETED', 'TENANT_ADMIN_EMAIL_CHANGED', 'EMPLOYEES_BULK_IMPORTED', 'EMPLOYEE_DATA_EXPORTED', 'EMPLOYEE_ANONYMIZED', 'EMPLOYEE_WORK_TIME_MODEL_SET', 'EMPLOYEE_PASSWORD_RESET', 'CONTRACT_CHANGED', 'COMPENSATION_CHANGED', 'COMPENSATION_VIEWED', 'DOCUMENT_UPLOADED', 'DOCUMENT_UPDATED', 'DOCUMENT_DELETED', 'DOCUMENT_ACCESSED', 'PERIOD_SUBMITTED', 'PERIOD_CONFIRMED', 'PERIOD_DISPUTED', 'PERIOD_CLOSED', 'PERIOD_REOPENED', 'CHECKLIST_STARTED', 'SURCHARGE_RULES_CHANGED', 'BALANCE_ADJUSTED', 'PUNCH_CORRECTION_DECIDED', 'EMPLOYEE_CARD_REGISTERED', 'EMPLOYEE_PIN_SET_AT_KIOSK', 'LOGIN']
_AUDIT_OLD = sa.Enum(*_AUDIT_BASE, name="auditaction")
_AUDIT_NEW = sa.Enum(*_AUDIT_BASE, "LEAVE_ADJUSTED", name="auditaction")


def upgrade() -> None:
    op.create_table(
        "leave_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("days", sa.Numeric(5, 1), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("note", sa.String(300), nullable=False),
        sa.Column("created_by_hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("created_by_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_leave_adjustments_employee_year", "leave_adjustments", ["employee_id", "year"])
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_OLD, type_=_AUDIT_NEW, existing_nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM audit_log_entries WHERE action = 'LEAVE_ADJUSTED'")
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_NEW, type_=_AUDIT_OLD, existing_nullable=False)
    op.drop_index("ix_leave_adjustments_employee_year", table_name="leave_adjustments")
    op.drop_table("leave_adjustments")
