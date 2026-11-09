"""Stammdaten: Kostenstellen (mit Aufteilung je Mitarbeiter in Prozent) und persönliche Daten
(Adresse, Familie, Bank, Steuer, SV – verschlüsseltes JSON); Audit-Aktionen.

Revision ID: 0122_personal_data
Revises: 0121_departments
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0122_personal_data"
down_revision: Union[str, None] = "0121_departments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = ['PUNCH_CORRECTED', 'PUNCH_DELETED', 'EMPLOYEE_HR_ROLE_CHANGED', 'ABSENCE_DECIDED', 'EMPLOYEE_CREATED', 'SETTINGS_CHANGED', 'HR_USER_CREATED', 'HR_USER_DELETED', 'TEAM_CREATED', 'TEAM_UPDATED', 'TEAM_DELETED', 'TENANT_ADMIN_EMAIL_CHANGED', 'EMPLOYEES_BULK_IMPORTED', 'EMPLOYEE_DATA_EXPORTED', 'EMPLOYEE_ANONYMIZED', 'EMPLOYEE_WORK_TIME_MODEL_SET', 'EMPLOYEE_PASSWORD_RESET', 'CONTRACT_CHANGED', 'COMPENSATION_CHANGED', 'COMPENSATION_VIEWED', 'DOCUMENT_UPLOADED', 'DOCUMENT_UPDATED', 'DOCUMENT_DELETED', 'DOCUMENT_ACCESSED', 'PERIOD_SUBMITTED', 'PERIOD_CONFIRMED', 'PERIOD_DISPUTED', 'PERIOD_CLOSED', 'PERIOD_REOPENED', 'CHECKLIST_STARTED', 'SURCHARGE_RULES_CHANGED', 'BALANCE_ADJUSTED', 'PUNCH_CORRECTION_DECIDED', 'EMPLOYEE_CARD_REGISTERED', 'EMPLOYEE_PIN_SET_AT_KIOSK', 'LOGIN', 'LEAVE_ADJUSTED', 'DEVICE_LOGIN_REJECTED', 'TWO_FACTOR_CHANGED', 'DEPARTMENT_CHANGED']
_AUDIT_OLD = sa.Enum(*_AUDIT_BASE, name="auditaction")
_AUDIT_NEW = sa.Enum(*_AUDIT_BASE, "PERSONAL_DATA_CHANGED", "COST_CENTERS_CHANGED", name="auditaction")


def upgrade() -> None:
    op.create_table(
        "cost_centers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_cost_centers_tenant_code"),
    )
    op.create_table(
        "employee_cost_centers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.id"), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.UniqueConstraint("employee_id", "cost_center_id", name="uq_employee_cost_centers"),
    )
    op.create_index("ix_employee_cost_centers_employee_id", "employee_cost_centers", ["employee_id"])
    op.create_table(
        "employee_personal_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_OLD, type_=_AUDIT_NEW, existing_nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM audit_log_entries WHERE action IN ('PERSONAL_DATA_CHANGED', 'COST_CENTERS_CHANGED')")
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_NEW, type_=_AUDIT_OLD, existing_nullable=False)
    op.drop_table("employee_personal_data")
    op.drop_table("employee_cost_centers")
    op.drop_table("cost_centers")
