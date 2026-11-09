"""Halbe Feiertage (z. B. Heiligabend, Silvester): halbes Soll, Abwesenheiten zählen halb.

Revision ID: 0103_half_holidays
Revises: 0102_absence_categories_payroll
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0103_half_holidays"
down_revision: Union[str, None] = "0102_absence_categories_payroll"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("holidays", sa.Column("half_day", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("holidays", "half_day")
