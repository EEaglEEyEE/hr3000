"""Schalter: Arbeitstage ganz ohne Stempelung als "Stempelung fehlt" melden

Revision ID: 0083_days_without_punches_switch
Revises: 0082_account_lifecycle
Create Date: 2026-11-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0083_days_without_punches_switch"
down_revision: Union[str, None] = "0082_account_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Standard an – bisheriges Verhalten bleibt erhalten.
    op.add_column(
        "app_settings",
        sa.Column("report_days_without_punches", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "report_days_without_punches")
