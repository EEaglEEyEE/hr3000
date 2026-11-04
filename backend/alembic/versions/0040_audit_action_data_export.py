"""audit_log_entries.action: EMPLOYEE_DATA_EXPORTED

Revision ID: 0040_audit_action_data_export
Revises: 0039_audit_action_bulk_import
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0040_audit_action_data_export"
down_revision: Union[str, None] = "0039_audit_action_bulk_import"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_ENUM = sa.Enum(
    "PUNCH_CORRECTED",
    "PUNCH_DELETED",
    "EMPLOYEE_HR_ROLE_CHANGED",
    "ABSENCE_DECIDED",
    "EMPLOYEE_CREATED",
    "SETTINGS_CHANGED",
    "HR_USER_CREATED",
    "HR_USER_DELETED",
    "TEAM_CREATED",
    "TEAM_UPDATED",
    "TEAM_DELETED",
    "TENANT_ADMIN_EMAIL_CHANGED",
    "EMPLOYEES_BULK_IMPORTED",
    name="auditaction",
)
_NEW_ENUM = sa.Enum(
    "PUNCH_CORRECTED",
    "PUNCH_DELETED",
    "EMPLOYEE_HR_ROLE_CHANGED",
    "ABSENCE_DECIDED",
    "EMPLOYEE_CREATED",
    "SETTINGS_CHANGED",
    "HR_USER_CREATED",
    "HR_USER_DELETED",
    "TEAM_CREATED",
    "TEAM_UPDATED",
    "TEAM_DELETED",
    "TENANT_ADMIN_EMAIL_CHANGED",
    "EMPLOYEES_BULK_IMPORTED",
    "EMPLOYEE_DATA_EXPORTED",
    name="auditaction",
)


def upgrade() -> None:
    op.alter_column(
        "audit_log_entries",
        "action",
        existing_type=_OLD_ENUM,
        type_=_NEW_ENUM,
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "audit_log_entries",
        "action",
        existing_type=_NEW_ENUM,
        type_=_OLD_ENUM,
        existing_nullable=False,
    )
