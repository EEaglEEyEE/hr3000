"""Abwesenheiten mit genauer Stundenzahl (z.B. 3 Std. Homeoffice)

Revision ID: 0077_absence_duration
Revises: 0076_core_time_and_punctuality
Create Date: 2026-10-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0077_absence_duration"
down_revision: Union[str, None] = "0076_core_time_and_punctuality"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("absences", sa.Column("duration_minutes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("absences", "duration_minutes")
