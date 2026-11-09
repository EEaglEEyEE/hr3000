"""Zusatzurlaub nach Betriebszugehörigkeit (Stufen "Jahre:Tage").

Revision ID: 0114_seniority_leave
Revises: 0113_parental_leave_reduction
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0114_seniority_leave"
down_revision: Union[str, None] = "0113_parental_leave_reduction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("seniority_leave_rules", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("app_settings", "seniority_leave_rules")
