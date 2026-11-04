"""Darstellung je Tablet und kurzer Kopplungscode zum Einrichten

Revision ID: 0068_device_theme_and_pairing
Revises: 0067_kiosk_theme
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0068_device_theme_and_pairing"
down_revision: Union[str, None] = "0067_kiosk_theme"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("theme", sa.String(5), nullable=True))
    op.add_column("devices", sa.Column("pairing_code_hash", sa.String(64), nullable=True))
    op.add_column("devices", sa.Column("pairing_code_expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_devices_pairing_code_hash", "devices", ["pairing_code_hash"])


def downgrade() -> None:
    op.drop_index("ix_devices_pairing_code_hash", table_name="devices")
    op.drop_column("devices", "pairing_code_expires_at")
    op.drop_column("devices", "pairing_code_hash")
    op.drop_column("devices", "theme")
