"""Grenzen fürs Überstundenkonto (Ober-/Untergrenze in Stunden, Hinweis unter „Zu klären“).

Revision ID: 0108_overtime_limits
Revises: 0107_payout_factor
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0108_overtime_limits"
down_revision: Union[str, None] = "0107_payout_factor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("overtime_limit_max_hours", sa.Integer(), nullable=True))
    op.add_column("app_settings", sa.Column("overtime_limit_min_hours", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("app_settings", "overtime_limit_min_hours")
    op.drop_column("app_settings", "overtime_limit_max_hours")
