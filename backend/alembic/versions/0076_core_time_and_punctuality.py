"""Kernarbeitszeit, Gleitzeit-Rahmen und Pünktlichkeitsprüfung (Mandant + je Mitarbeiter)

Revision ID: 0076_core_time_and_punctuality
Revises: 0075_absence_half_day
Create Date: 2026-10-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0076_core_time_and_punctuality"
down_revision: Union[str, None] = "0075_absence_half_day"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("core_time_start", sa.Time(), nullable=True))
    op.add_column("app_settings", sa.Column("core_time_end", sa.Time(), nullable=True))
    op.add_column("app_settings", sa.Column("punctuality_check", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("app_settings", sa.Column("late_tolerance_minutes", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("app_settings", sa.Column("flex_frame_start", sa.Time(), nullable=True))
    op.add_column("app_settings", sa.Column("flex_frame_end", sa.Time(), nullable=True))
    op.add_column("employees", sa.Column("core_time_mode", sa.String(10), nullable=False, server_default="TENANT"))
    op.add_column("employees", sa.Column("core_time_start", sa.Time(), nullable=True))
    op.add_column("employees", sa.Column("core_time_end", sa.Time(), nullable=True))


def downgrade() -> None:
    for column in ("core_time_end", "core_time_start", "core_time_mode"):
        op.drop_column("employees", column)
    for column in ("flex_frame_end", "flex_frame_start", "late_tolerance_minutes", "punctuality_check", "core_time_end", "core_time_start"):
        op.drop_column("app_settings", column)
