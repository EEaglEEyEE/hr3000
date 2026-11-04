"""Arbeitszeitmodell "nach Aufwand" (ohne Soll) mit optionaler Monatsgrenze

Revision ID: 0070_on_demand_work_time_model
Revises: 0069_card_self_registration
Create Date: 2026-10-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0070_on_demand_work_time_model"
down_revision: Union[str, None] = "0069_card_self_registration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employee_default_shifts", sa.Column("on_demand", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("employee_default_shifts", sa.Column("monthly_cap_minutes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("employee_default_shifts", "monthly_cap_minutes")
    op.drop_column("employee_default_shifts", "on_demand")
