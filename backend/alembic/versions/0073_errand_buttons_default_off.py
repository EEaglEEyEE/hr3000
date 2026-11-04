"""Dienstgang-Buttons standardmäßig aus

Revision ID: 0073_errand_buttons_default_off
Revises: 0072_errand_and_portal_punching
Create Date: 2026-10-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0073_errand_buttons_default_off"
down_revision: Union[str, None] = "0072_errand_and_portal_punching"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "app_settings", "kiosk_errand_buttons", existing_type=sa.Boolean(), existing_nullable=False, server_default=sa.false()
    )
    # Mandanten, die bereits Dienstgänge gestempelt haben, behalten die Buttons – sonst ließe sich ein
    # offener Dienstgang nicht mehr beenden.
    op.execute(
        "UPDATE app_settings SET kiosk_errand_buttons = false WHERE tenant_id NOT IN "
        "(SELECT DISTINCT tenant_id FROM punches WHERE punch_type IN ('ERRAND_START', 'ERRAND_END'))"
    )


def downgrade() -> None:
    op.alter_column(
        "app_settings", "kiosk_errand_buttons", existing_type=sa.Boolean(), existing_nullable=False, server_default=sa.true()
    )
