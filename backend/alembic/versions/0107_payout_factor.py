"""Auszahlung von Überstunden mit Faktor (z. B. 1,5).

Revision ID: 0107_payout_factor
Revises: 0106_absence_comment_certificate
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0107_payout_factor"
down_revision: Union[str, None] = "0106_absence_comment_certificate"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("balance_adjustments", sa.Column("payout_factor", sa.Numeric(4, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("balance_adjustments", "payout_factor")
