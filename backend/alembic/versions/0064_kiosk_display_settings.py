"""Kiosk-Anzeige je Mandant: Saldo/Resturlaub, Pausen-Buttons, Begrüßungstext, Sortierung

Revision ID: 0064_kiosk_display_settings
Revises: 0063_vacation_carry_over
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0064_kiosk_display_settings"
down_revision: Union[str, None] = "0063_vacation_carry_over"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("kiosk_show_balance", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("app_settings", sa.Column("kiosk_show_vacation", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("app_settings", sa.Column("kiosk_break_buttons", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("app_settings", sa.Column("kiosk_greeting", sa.String(120), nullable=True))
    op.add_column("app_settings", sa.Column("kiosk_sort", sa.String(10), nullable=False, server_default="LAST_NAME"))


def downgrade() -> None:
    for column in ("kiosk_sort", "kiosk_greeting", "kiosk_break_buttons", "kiosk_show_vacation", "kiosk_show_balance"):
        op.drop_column("app_settings", column)
