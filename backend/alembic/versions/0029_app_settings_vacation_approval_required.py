"""app_settings.vacation_approval_required

Revision ID: 0029_app_settings_vacation_approval_required
Revises: 0028_absence_approval_workflow
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0029_app_settings_vacation_approval_required"
down_revision: Union[str, None] = "0028_absence_approval_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("vacation_approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "vacation_approval_required")
