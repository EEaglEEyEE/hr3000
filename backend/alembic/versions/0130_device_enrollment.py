"""Tablets per MDM verteilen: Registrierungsschlüssel je Standort, offene Registrierungen und
Gerätename im MDM je Tablet-Eintrag.

Revision ID: 0130_device_enrollment
Revises: 0129_api_webhooks
Create Date: 2026-11-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0130_device_enrollment"
down_revision: Union[str, None] = "0129_api_webhooks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = ['PUNCH_CORRECTED', 'PUNCH_DELETED', 'EMPLOYEE_HR_ROLE_CHANGED', 'ABSENCE_DECIDED', 'EMPLOYEE_CREATED', 'SETTINGS_CHANGED', 'HR_USER_CREATED', 'HR_USER_DELETED', 'TEAM_CREATED', 'TEAM_UPDATED', 'TEAM_DELETED', 'TENANT_ADMIN_EMAIL_CHANGED', 'EMPLOYEES_BULK_IMPORTED', 'EMPLOYEE_DATA_EXPORTED', 'EMPLOYEE_ANONYMIZED', 'EMPLOYEE_WORK_TIME_MODEL_SET', 'EMPLOYEE_PASSWORD_RESET', 'CONTRACT_CHANGED', 'COMPENSATION_CHANGED', 'COMPENSATION_VIEWED', 'DOCUMENT_UPLOADED', 'DOCUMENT_UPDATED', 'DOCUMENT_DELETED', 'DOCUMENT_ACCESSED', 'PERIOD_SUBMITTED', 'PERIOD_CONFIRMED', 'PERIOD_DISPUTED', 'PERIOD_CLOSED', 'PERIOD_REOPENED', 'CHECKLIST_STARTED', 'SURCHARGE_RULES_CHANGED', 'BALANCE_ADJUSTED', 'PUNCH_CORRECTION_DECIDED', 'EMPLOYEE_CARD_REGISTERED', 'EMPLOYEE_PIN_SET_AT_KIOSK', 'LOGIN', 'LEAVE_ADJUSTED', 'DEVICE_LOGIN_REJECTED', 'TWO_FACTOR_CHANGED', 'DEPARTMENT_CHANGED', 'PERSONAL_DATA_CHANGED', 'COST_CENTERS_CHANGED', 'ATTRIBUTE_CHANGED']
_AUDIT_OLD = sa.Enum(*_AUDIT_BASE, name="auditaction")
_AUDIT_NEW = sa.Enum(*_AUDIT_BASE, "DEVICE_ENROLLMENT", name="auditaction")


def upgrade() -> None:
    op.add_column("devices", sa.Column("mdm_name", sa.String(100), nullable=True))
    op.create_table(
        "device_enrollment_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "device_enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("reported_name", sa.String(100), nullable=True),
        sa.Column("verify_code", sa.String(7), nullable=False),
        sa.Column("installation_hash", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "installation_hash", name="uq_device_enrollments_installation"),
    )
    op.create_index("ix_device_enrollments_token_hash", "device_enrollments", ["token_hash"])
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_OLD, type_=_AUDIT_NEW, existing_nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM audit_log_entries WHERE action = 'DEVICE_ENROLLMENT'")
    op.alter_column("audit_log_entries", "action", existing_type=_AUDIT_NEW, type_=_AUDIT_OLD, existing_nullable=False)
    op.drop_index("ix_device_enrollments_token_hash", table_name="device_enrollments")
    op.drop_table("device_enrollments")
    op.drop_table("device_enrollment_keys")
    op.drop_column("devices", "mdm_name")
