"""Einstellung: Mitarbeiter sehen beim Antrag, wer im Team gleichzeitig abwesend ist (Standard aus).

Revision ID: 0105_absence_overlaps_setting
Revises: 0104_absence_substitutes
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0105_absence_overlaps_setting"
down_revision: Union[str, None] = "0104_absence_substitutes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("absence_overlaps_for_employees", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "absence_overlaps_for_employees")
