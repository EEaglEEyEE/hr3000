"""SummaryStatus: add ON_BREAK (Pause) and ERROR (Fehlerhaft)

Revision ID: 0011_summary_status_break_error
Revises: 0010_app_settings
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_summary_status_break_error"
down_revision: Union[str, None] = "0010_app_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_VALUES = ("COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", "PRESENT")
_NEW_VALUES = ("COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", "PRESENT", "ON_BREAK", "ERROR")


def upgrade() -> None:
    op.alter_column(
        "daily_summaries",
        "status",
        existing_type=sa.Enum(*_OLD_VALUES, name="summarystatus"),
        type_=sa.Enum(*_NEW_VALUES, name="summarystatus"),
    )


def downgrade() -> None:
    op.alter_column(
        "daily_summaries",
        "status",
        existing_type=sa.Enum(*_NEW_VALUES, name="summarystatus"),
        type_=sa.Enum(*_OLD_VALUES, name="summarystatus"),
    )
