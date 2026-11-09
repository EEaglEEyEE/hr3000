"""Einstellung: Urlaub je vollem Monat Elternzeit um 1/12 kürzen (§ 17 BEEG), Standard aus.

Revision ID: 0113_parental_leave_reduction
Revises: 0112_percent_yearly_payments
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0113_parental_leave_reduction"
down_revision: Union[str, None] = "0112_percent_yearly_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("reduce_vacation_parental_leave", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "reduce_vacation_parental_leave")
