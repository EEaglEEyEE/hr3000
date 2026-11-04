"""SummaryStatus: add PRESENT (Anwesend ab "Kommen", ohne abgeschlossenes GO)

Revision ID: 0009_summary_status_present
Revises: 0008_auto_break
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_summary_status_present"
down_revision: Union[str, None] = "0008_auto_break"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "daily_summaries",
        "status",
        existing_type=sa.Enum("COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", name="summarystatus"),
        type_=sa.Enum("COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", "PRESENT", name="summarystatus"),
    )


def downgrade() -> None:
    op.alter_column(
        "daily_summaries",
        "status",
        existing_type=sa.Enum("COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", "PRESENT", name="summarystatus"),
        type_=sa.Enum("COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", name="summarystatus"),
    )
