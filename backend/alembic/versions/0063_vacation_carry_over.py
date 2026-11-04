"""Automatischer Urlaubsübertrag mit Obergrenze und Verfallsdatum

Revision ID: 0063_vacation_carry_over
Revises: 0062_absence_type_definitions
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0063_vacation_carry_over"
down_revision: Union[str, None] = "0062_absence_type_definitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("vacation_carry_over_auto", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("app_settings", sa.Column("vacation_carry_over_max_days", sa.Numeric(5, 2), nullable=True))
    op.add_column("app_settings", sa.Column("vacation_carry_over_expiry", sa.String(5), nullable=True))
    op.add_column(
        "leave_entitlements",
        sa.Column("carried_over_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Bereits von HR eingetragene Überträge bleiben fest.
    op.execute("UPDATE leave_entitlements SET carried_over_manual = 1 WHERE carried_over_days <> 0")


def downgrade() -> None:
    op.drop_column("leave_entitlements", "carried_over_manual")
    op.drop_column("app_settings", "vacation_carry_over_expiry")
    op.drop_column("app_settings", "vacation_carry_over_max_days")
    op.drop_column("app_settings", "vacation_carry_over_auto")
