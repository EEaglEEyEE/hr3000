"""Schalter: Mitarbeiter dürfen Abwesenheiten/Urlaub selbst beantragen

Revision ID: 0074_absence_requests_switch
Revises: 0073_errand_buttons_default_off
Create Date: 2026-10-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0074_absence_requests_switch"
down_revision: Union[str, None] = "0073_errand_buttons_default_off"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Standard an – bisheriges Verhalten bleibt erhalten.
    op.add_column(
        "app_settings", sa.Column("absence_requests_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
    )


def downgrade() -> None:
    op.drop_column("app_settings", "absence_requests_enabled")
