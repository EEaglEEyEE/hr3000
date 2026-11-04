"""Halbe Abwesenheitstage

Revision ID: 0075_absence_half_day
Revises: 0074_absence_requests_switch
Create Date: 2026-10-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0075_absence_half_day"
down_revision: Union[str, None] = "0074_absence_requests_switch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("absences", sa.Column("half_day", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("absences", "half_day")
