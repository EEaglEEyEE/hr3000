"""work_time_models: per-weekday hours -> weekly_hours + work_days_per_week

Revision ID: 0007_work_time_model_weekly
Revises: 0006_employee_hr_role_and_audit
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_work_time_model_weekly"
down_revision: Union[str, None] = "0006_employee_hr_role_and_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WEEKDAY_COLUMNS = [
    "hours_monday",
    "hours_tuesday",
    "hours_wednesday",
    "hours_thursday",
    "hours_friday",
    "hours_saturday",
    "hours_sunday",
]


def upgrade() -> None:
    op.add_column(
        "work_time_models", sa.Column("weekly_hours", sa.Numeric(5, 2), nullable=False, server_default="0")
    )
    op.add_column(
        "work_time_models",
        sa.Column("work_days_per_week", sa.Integer(), nullable=False, server_default="6"),
    )
    for column in _WEEKDAY_COLUMNS:
        op.drop_column("work_time_models", column)


def downgrade() -> None:
    for column in _WEEKDAY_COLUMNS:
        op.add_column("work_time_models", sa.Column(column, sa.Numeric(4, 2), nullable=False, server_default="0"))
    op.drop_column("work_time_models", "work_days_per_week")
    op.drop_column("work_time_models", "weekly_hours")
