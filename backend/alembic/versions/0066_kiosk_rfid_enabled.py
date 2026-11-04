"""Chip-/RFID-Funktion am Kiosk je Mandant ein- und ausschaltbar

Revision ID: 0066_kiosk_rfid_enabled
Revises: 0065_punch_correction_requests
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0066_kiosk_rfid_enabled"
down_revision: Union[str, None] = "0065_punch_correction_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("kiosk_rfid_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("app_settings", "kiosk_rfid_enabled")
