"""Darstellung am Kiosk-Tablet (dunkel/hell)

Revision ID: 0067_kiosk_theme
Revises: 0066_kiosk_rfid_enabled
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0067_kiosk_theme"
down_revision: Union[str, None] = "0066_kiosk_rfid_enabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("kiosk_theme", sa.String(5), nullable=False, server_default="DARK"))


def downgrade() -> None:
    op.drop_column("app_settings", "kiosk_theme")
