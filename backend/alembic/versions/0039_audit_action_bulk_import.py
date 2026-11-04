"""audit_log_entries.action: EMPLOYEES_BULK_IMPORTED

Revision ID: 0039_audit_action_bulk_import
Revises: 0038_audit_action_more_types
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0039_audit_action_bulk_import"
down_revision: Union[str, None] = "0038_audit_action_more_types"
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
