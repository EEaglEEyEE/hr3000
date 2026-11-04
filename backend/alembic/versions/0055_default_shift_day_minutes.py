"""Arbeitszeitmodell: Soll je Wochentag (Teilzeit mit ungleich verteilten Stunden)

Revision ID: 0055_default_shift_day_minutes
Revises: 0054_effective_dated_rules_and_locations
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0055_default_shift_day_minutes"
down_revision: Union[str, None] = "0054_effective_dated_rules_and_locations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employee_default_shifts", sa.Column("day_minutes", sa.String(60), nullable=True))


def downgrade() -> None:
    op.drop_column("employee_default_shifts", "day_minutes")
