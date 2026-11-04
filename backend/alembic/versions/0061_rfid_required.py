"""RFID-Pflicht am Kiosk + vereinheitlichte Karten-UIDs

Revision ID: 0061_rfid_required
Revises: 0060_flexible_work_time_model
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0061_rfid_required"
down_revision: Union[str, None] = "0060_flexible_work_time_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("rfid_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Bestehende Karten-UIDs in das einheitliche Format bringen (klein, ohne Trennzeichen).
    op.execute(
        "UPDATE employees SET nfc_uid = LOWER(REPLACE(REPLACE(REPLACE(nfc_uid, ':', ''), '-', ''), ' ', '')) "
        "WHERE nfc_uid IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("app_settings", "rfid_required")
