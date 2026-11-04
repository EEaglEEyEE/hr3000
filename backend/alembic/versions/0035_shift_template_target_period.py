"""shift_templates.target_period

Revision ID: 0035_shift_template_target_period
Revises: 0034_employee_birthday_calendar_marker
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0035_shift_template_target_period"
down_revision: Union[str, None] = "0034_employee_birthday_calendar_marker"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shift_templates",
        sa.Column(
            "target_period",
            sa.Enum("DAILY", "WEEKLY", "MONTHLY", name="targetperiod"),
            nullable=False,
            server_default="DAILY",
        ),
    )


def downgrade() -> None:
    op.drop_column("shift_templates", "target_period")
