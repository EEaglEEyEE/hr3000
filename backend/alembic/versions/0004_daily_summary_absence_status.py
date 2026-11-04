"""add ABSENCE to daily_summaries.status

Revision ID: 0004_daily_summary_absence_status
Revises: 0003_seed_break_rules
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_daily_summary_absence_status"
down_revision: Union[str, None] = "0003_seed_break_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "daily_summaries",
        "status",
        existing_type=sa.Enum("COMPLETE", "OPEN_MISSING_PUNCH", name="summarystatus"),
        type_=sa.Enum("COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", name="summarystatus"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "daily_summaries",
        "status",
        existing_type=sa.Enum("COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", name="summarystatus"),
        type_=sa.Enum("COMPLETE", "OPEN_MISSING_PUNCH", name="summarystatus"),
        existing_nullable=False,
    )
