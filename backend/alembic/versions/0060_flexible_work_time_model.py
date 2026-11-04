"""Flexibles Arbeitszeitmodell: Wochensoll ohne feste Arbeitstage (Aushilfen)

Revision ID: 0060_flexible_work_time_model
Revises: 0059_tenant_defaults_and_kiosk_pin
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0060_flexible_work_time_model"
down_revision: Union[str, None] = "0059_tenant_defaults_and_kiosk_pin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employee_default_shifts", sa.Column("flexible", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("employee_default_shifts", "flexible")
