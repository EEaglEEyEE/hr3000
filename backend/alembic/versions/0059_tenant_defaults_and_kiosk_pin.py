"""Mandanten-Standardwerte/Regeln und Kiosk-Admin-PIN

Revision ID: 0059_tenant_defaults_and_kiosk_pin
Revises: 0058_auto_break_default_on
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0059_tenant_defaults_and_kiosk_pin"
down_revision: Union[str, None] = "0058_auto_break_default_on"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("default_auto_break", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("app_settings", sa.Column("default_show_birthday", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("app_settings", sa.Column("default_day_minutes", sa.String(60), nullable=True))
    op.add_column("app_settings", sa.Column("prorate_part_time_vacation", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("app_settings", sa.Column("disabled_day_flags", sa.String(200), nullable=True))
    op.add_column("app_settings", sa.Column("max_shift_span_hours", sa.Integer(), nullable=False, server_default="16"))
    op.add_column("app_settings", sa.Column("kiosk_admin_pin_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    for column in (
        "kiosk_admin_pin_hash", "max_shift_span_hours", "disabled_day_flags", "prorate_part_time_vacation",
        "default_day_minutes", "default_show_birthday", "default_auto_break",
    ):
        op.drop_column("app_settings", column)
