"""daily_summaries.status: PLANNED_OFF hinzufügen

Revision ID: 0027_summary_status_planned_off
Revises: 0026_create_employee_default_shifts_and_shift_plan_entries
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027_summary_status_planned_off"
down_revision: Union[str, None] = "0026_create_employee_default_shifts_and_shift_plan_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_ENUM = sa.Enum(
    "COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", "PRESENT", "ON_BREAK", "ERROR", "HOLIDAY",
    name="summarystatus",
)
_NEW_ENUM = sa.Enum(
    "COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", "PRESENT", "ON_BREAK", "ERROR", "HOLIDAY",
    "PLANNED_OFF",
    name="summarystatus",
)


def upgrade() -> None:
    op.alter_column(
        "daily_summaries",
        "status",
        existing_type=_OLD_ENUM,
        type_=_NEW_ENUM,
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute("DELETE FROM daily_summaries WHERE status = 'PLANNED_OFF'")
    op.alter_column(
        "daily_summaries",
        "status",
        existing_type=_NEW_ENUM,
        type_=_OLD_ENUM,
        existing_nullable=False,
    )
