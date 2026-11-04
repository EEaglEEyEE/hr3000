"""Eigener SMTP-Server pro Mandant + Mail-Benachrichtigungen + Audit EMPLOYEE_PASSWORD_RESET

Revision ID: 0046_smtp_settings_and_password_reset_audit
Revises: 0045_work_time_model_and_shift_planning_toggle
Create Date: 2026-10-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0046_smtp_settings_and_password_reset_audit"
down_revision: Union[str, None] = "0045_work_time_model_and_shift_planning_toggle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_BASE = [
    "PUNCH_CORRECTED", "PUNCH_DELETED", "EMPLOYEE_HR_ROLE_CHANGED", "ABSENCE_DECIDED",
    "EMPLOYEE_CREATED", "SETTINGS_CHANGED", "HR_USER_CREATED", "HR_USER_DELETED",
    "TEAM_CREATED", "TEAM_UPDATED", "TEAM_DELETED", "TENANT_ADMIN_EMAIL_CHANGED",
    "EMPLOYEES_BULK_IMPORTED", "EMPLOYEE_DATA_EXPORTED", "EMPLOYEE_ANONYMIZED",
    "EMPLOYEE_WORK_TIME_MODEL_SET",
]
_OLD_ENUM = sa.Enum(*_AUDIT_BASE, name="auditaction")
_NEW_ENUM = sa.Enum(*_AUDIT_BASE, "EMPLOYEE_PASSWORD_RESET", name="auditaction")


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("smtp_host", sa.String(255), nullable=True))
    op.add_column("app_settings", sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"))
    op.add_column("app_settings", sa.Column("smtp_user", sa.String(255), nullable=True))
    op.add_column("app_settings", sa.Column("smtp_password_encrypted", sa.Text(), nullable=True))
    op.add_column("app_settings", sa.Column("smtp_from", sa.String(255), nullable=True))
    op.add_column(
        "app_settings", sa.Column("smtp_security", sa.String(10), nullable=False, server_default="STARTTLS")
    )
    op.add_column(
        "app_settings",
        sa.Column("email_notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column(
        "audit_log_entries", "action", existing_type=_OLD_ENUM, type_=_NEW_ENUM, existing_nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "audit_log_entries", "action", existing_type=_NEW_ENUM, type_=_OLD_ENUM, existing_nullable=False
    )
    for column in (
        "email_notifications_enabled", "smtp_security", "smtp_from",
        "smtp_password_encrypted", "smtp_user", "smtp_port", "smtp_host",
    ):
        op.drop_column("app_settings", column)
