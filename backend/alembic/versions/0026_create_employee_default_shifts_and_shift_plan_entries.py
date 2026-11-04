"""employee_default_shifts + shift_plan_entries

Revision ID: 0026_create_employee_default_shifts_and_shift_plan_entries
Revises: 0025_create_shift_templates
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026_create_employee_default_shifts_and_shift_plan_entries"
down_revision: Union[str, None] = "0025_create_shift_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employee_default_shifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_templates.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("weekdays_mask", sa.Integer(), nullable=False),
    )

    op.create_table(
        "shift_plan_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_templates.id"), nullable=True),
        sa.Column("is_workday", sa.Boolean(), nullable=False),
        sa.Column("target_minutes", sa.Integer(), nullable=True),
        sa.Column("planned_by_hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("planned_by_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("employee_id", "date", name="uq_shift_plan_entries_employee_date"),
    )


def downgrade() -> None:
    op.drop_table("shift_plan_entries")
    op.drop_table("employee_default_shifts")
