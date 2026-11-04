"""Automatische Pausenregelung standardmäßig aktiv (auch für bestehende Mitarbeiter)

Revision ID: 0058_auto_break_default_on
Revises: 0057_tenant_logo
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0058_auto_break_default_on"
down_revision: Union[str, None] = "0057_tenant_logo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "employees", "auto_break_enabled", existing_type=sa.Boolean(), server_default=sa.true(), existing_nullable=False
    )
    op.execute("UPDATE employees SET auto_break_enabled = 1")


def downgrade() -> None:
    op.alter_column(
        "employees", "auto_break_enabled", existing_type=sa.Boolean(), server_default=None, existing_nullable=False
    )
