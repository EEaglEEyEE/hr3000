"""Arbeitszeitmodell: app_settings.shift_planning_enabled + shift_templates.is_work_time_model

Revision ID: 0045_work_time_model_and_shift_planning_toggle
Revises: 0044_app_settings_open_days_digest_sent_at
Create Date: 2026-10-12

Bestehende Mandanten behalten die Schichtplanung (server_default true beim
Backfill); neue Mandanten bekommen den Wert vom ORM-Default (false).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0045_work_time_model_and_shift_planning_toggle"
down_revision: Union[str, None] = "0044_app_settings_open_days_digest_sent_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AUDIT_BASE = [
    "PUNCH_CORRECTED", "PUNCH_DELETED", "EMPLOYEE_HR_ROLE_CHANGED", "ABSENCE_DECIDED",
    "EMPLOYEE_CREATED", "SETTINGS_CHANGED", "HR_USER_CREATED", "HR_USER_DELETED",
    "TEAM_CREATED", "TEAM_UPDATED", "TEAM_DELETED", "TENANT_ADMIN_EMAIL_CHANGED",
    "EMPLOYEES_BULK_IMPORTED", "EMPLOYEE_DATA_EXPORTED", "EMPLOYEE_ANONYMIZED",
]
_OLD_ENUM = sa.Enum(*_AUDIT_BASE, name="auditaction")
_NEW_ENUM = sa.Enum(*_AUDIT_BASE, "EMPLOYEE_WORK_TIME_MODEL_SET", name="auditaction")


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("shift_planning_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "shift_templates",
        sa.Column("is_work_time_model", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


    op.alter_column(
        "audit_log_entries", "action", existing_type=_OLD_ENUM, type_=_NEW_ENUM, existing_nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "audit_log_entries", "action", existing_type=_NEW_ENUM, type_=_OLD_ENUM, existing_nullable=False
    )
    op.drop_column("shift_templates", "is_work_time_model")
    op.drop_column("app_settings", "shift_planning_enabled")
