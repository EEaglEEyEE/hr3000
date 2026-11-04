"""app_settings: globale Einstellungen (u.a. PIN-Pflicht beim Stempeln)

Revision ID: 0010_app_settings
Revises: 0009_summary_status_present
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_app_settings"
down_revision: Union[str, None] = "0009_summary_status_present"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "require_pin_for_punch", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.bulk_insert(
        sa.table(
            "app_settings",
            sa.column("id", sa.Integer()),
            sa.column("require_pin_for_punch", sa.Boolean()),
        ),
        [{"id": 1, "require_pin_for_punch": False}],
    )


def downgrade() -> None:
    op.drop_table("app_settings")
