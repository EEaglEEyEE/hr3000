"""employees.auto_break_enabled + PunchSource.AUTO_BREAK

Revision ID: 0008_auto_break
Revises: 0007_work_time_model_weekly
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_auto_break"
down_revision: Union[str, None] = "0007_work_time_model_weekly"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("auto_break_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column(
        "punches",
        "source",
        existing_type=sa.Enum("KIOSK", "MANUAL_HR", name="punchsource"),
        type_=sa.Enum("KIOSK", "MANUAL_HR", "AUTO_BREAK", name="punchsource"),
    )


def downgrade() -> None:
    op.alter_column(
        "punches",
        "source",
        existing_type=sa.Enum("KIOSK", "MANUAL_HR", "AUTO_BREAK", name="punchsource"),
        type_=sa.Enum("KIOSK", "MANUAL_HR", name="punchsource"),
    )
    op.drop_column("employees", "auto_break_enabled")
