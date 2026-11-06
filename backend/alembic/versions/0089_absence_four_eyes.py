"""Vier-Augen-Prinzip für Abwesenheitsanträge (Schalter, Standard aus)

Revision ID: 0089_absence_four_eyes
Revises: 0088_drop_vacation_approval_flag
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0089_absence_four_eyes"
down_revision: Union[str, None] = "0088_drop_vacation_approval_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Aus = bisheriges Verhalten: wer genehmigen darf, bekommt eigene Anträge direkt genehmigt.
    op.add_column("app_settings", sa.Column("absence_four_eyes", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("app_settings", "absence_four_eyes")
