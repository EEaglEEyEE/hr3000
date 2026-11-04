"""Sonderfälle je Tag (außerplanmäßig gestempelt usw.) und deren Klärung

Revision ID: 0056_day_flags_and_reviews
Revises: 0055_default_shift_day_minutes
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0056_day_flags_and_reviews"
down_revision: Union[str, None] = "0055_default_shift_day_minutes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("daily_summaries", sa.Column("flags", sa.String(200), nullable=True))
    op.create_table(
        "day_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("reviewed_by_hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("reviewed_by_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("employee_id", "work_date", name="uq_day_reviews_employee_date"),
    )
    # Tages-Cache neu aufbauen lassen, damit bestehende Sonderfälle erkannt werden.
    op.execute("UPDATE employees SET balance_through = NULL")


def downgrade() -> None:
    op.drop_table("day_reviews")
    op.drop_column("daily_summaries", "flags")
