"""Bildschirmzeiten am Kiosk-Tablet (Mandant + Abweichung je Gerät)

Revision ID: 0080_kiosk_screen_hours
Revises: 0079_tenant_plan
Create Date: 2026-11-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0080_kiosk_screen_hours"
down_revision: Union[str, None] = "0079_tenant_plan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alles NULL = Bildschirm immer an (bisheriges Verhalten).
    op.add_column("app_settings", sa.Column("kiosk_screen_on_from", sa.Time(), nullable=True))
    op.add_column("app_settings", sa.Column("kiosk_screen_on_until", sa.Time(), nullable=True))
    op.add_column("devices", sa.Column("screen_hours_mode", sa.String(7), nullable=True))
    op.add_column("devices", sa.Column("screen_on_from", sa.Time(), nullable=True))
    op.add_column("devices", sa.Column("screen_on_until", sa.Time(), nullable=True))


def downgrade() -> None:
    for column in ("screen_on_until", "screen_on_from", "screen_hours_mode"):
        op.drop_column("devices", column)
    op.drop_column("app_settings", "kiosk_screen_on_until")
    op.drop_column("app_settings", "kiosk_screen_on_from")
