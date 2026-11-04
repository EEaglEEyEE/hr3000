"""Dienstgang (Stempelart + Tagesstatus) und Stempeln im Online-Portal

Revision ID: 0072_errand_and_portal_punching
Revises: 0071_kiosk_pin_self_setup
Create Date: 2026-10-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0072_errand_and_portal_punching"
down_revision: Union[str, None] = "0071_kiosk_pin_self_setup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TYPE_OLD = sa.Enum("COME", "GO", "BREAK_START", "BREAK_END", name="punchtype")
_TYPE_NEW = sa.Enum("COME", "GO", "BREAK_START", "BREAK_END", "ERRAND_START", "ERRAND_END", name="punchtype")
_SOURCE_OLD = sa.Enum("KIOSK", "MANUAL_HR", "AUTO_BREAK", name="punchsource")
_SOURCE_NEW = sa.Enum("KIOSK", "MANUAL_HR", "AUTO_BREAK", "PORTAL", name="punchsource")
_STATUS_BASE = ["COMPLETE", "OPEN_MISSING_PUNCH", "ABSENCE", "PRESENT", "ON_BREAK", "ERROR", "HOLIDAY", "PLANNED_OFF"]
_STATUS_OLD = sa.Enum(*_STATUS_BASE, name="summarystatus")
_STATUS_NEW = sa.Enum(*_STATUS_BASE, "ON_ERRAND", name="summarystatus")


def upgrade() -> None:
    op.alter_column("punches", "punch_type", existing_type=_TYPE_OLD, type_=_TYPE_NEW, existing_nullable=False)
    op.alter_column("punches", "source", existing_type=_SOURCE_OLD, type_=_SOURCE_NEW, existing_nullable=False)
    op.alter_column("daily_summaries", "status", existing_type=_STATUS_OLD, type_=_STATUS_NEW, existing_nullable=False)
    op.add_column("app_settings", sa.Column("kiosk_errand_buttons", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column(
        "app_settings", sa.Column("portal_punching_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("app_settings", "portal_punching_enabled")
    op.drop_column("app_settings", "kiosk_errand_buttons")
    op.alter_column("daily_summaries", "status", existing_type=_STATUS_NEW, type_=_STATUS_OLD, existing_nullable=False)
    op.alter_column("punches", "source", existing_type=_SOURCE_NEW, type_=_SOURCE_OLD, existing_nullable=False)
    op.alter_column("punches", "punch_type", existing_type=_TYPE_NEW, type_=_TYPE_OLD, existing_nullable=False)
