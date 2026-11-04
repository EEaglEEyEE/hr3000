"""Korrekturanträge von Mitarbeitern (Stempelung vergessen) mit Bestätigung durch HR

Revision ID: 0065_punch_correction_requests
Revises: 0064_kiosk_display_settings
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0065_punch_correction_requests"
down_revision: Union[str, None] = "0064_kiosk_display_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOTIFY_BASE = ["ABSENCE_REQUESTED", "ABSENCE_DECIDED", "OPEN_DAYS_DIGEST", "PERIOD_SUBMITTED", "PERIOD_DISPUTED"]
_NOTIFY_OLD = sa.Enum(*_NOTIFY_BASE, name="notificationtype")
_NOTIFY_NEW = sa.Enum(*_NOTIFY_BASE, "CORRECTION_REQUESTED", "CORRECTION_DECIDED", name="notificationtype")

_AUDIT_BASE = [
    "PUNCH_CORRECTED", "PUNCH_DELETED", "EMPLOYEE_HR_ROLE_CHANGED", "ABSENCE_DECIDED",
    "EMPLOYEE_CREATED", "SETTINGS_CHANGED", "HR_USER_CREATED", "HR_USER_DELETED",
    "TEAM_CREATED", "TEAM_UPDATED", "TEAM_DELETED", "TENANT_ADMIN_EMAIL_CHANGED",
    "EMPLOYEES_BULK_IMPORTED", "EMPLOYEE_DATA_EXPORTED", "EMPLOYEE_ANONYMIZED",
    "EMPLOYEE_WORK_TIME_MODEL_SET", "EMPLOYEE_PASSWORD_RESET",
    "CONTRACT_CHANGED", "COMPENSATION_CHANGED", "COMPENSATION_VIEWED",
    "DOCUMENT_UPLOADED", "DOCUMENT_UPDATED", "DOCUMENT_DELETED", "DOCUMENT_ACCESSED",
    "PERIOD_SUBMITTED", "PERIOD_CONFIRMED", "PERIOD_DISPUTED", "PERIOD_CLOSED", "PERIOD_REOPENED",
    "CHECKLIST_STARTED", "SURCHARGE_RULES_CHANGED", "BALANCE_ADJUSTED",
]
_AUDIT_OLD = sa.Enum(*_AUDIT_BASE, name="auditaction")
_AUDIT_NEW = sa.Enum(*_AUDIT_BASE, "PUNCH_CORRECTION_DECIDED", name="auditaction")


def upgrade() -> None:
    op.create_table(
        "punch_correction_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("items", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "APPROVED", "REJECTED", name="correctionrequeststatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("decided_by_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
    )
    op.create_index("ix_punch_correction_requests_tenant_id", "punch_correction_requests", ["tenant_id"])
    op.create_index("ix_punch_correction_requests_employee_id", "punch_correction_requests", ["employee_id"])
    op.alter_column("notifications", "type", existing_type=_NOTIFY_OLD, type_=_NOTIFY_NEW, existing_nullable=False)
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_OLD, type_=_AUDIT_NEW, existing_nullable=False)


def downgrade() -> None:
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_NEW, type_=_AUDIT_OLD, existing_nullable=False)
    op.alter_column("notifications", "type", existing_type=_NOTIFY_NEW, type_=_NOTIFY_OLD, existing_nullable=False)
    op.drop_index("ix_punch_correction_requests_employee_id", table_name="punch_correction_requests")
    op.drop_index("ix_punch_correction_requests_tenant_id", table_name="punch_correction_requests")
    op.drop_table("punch_correction_requests")
