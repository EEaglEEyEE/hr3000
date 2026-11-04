"""app_settings: default_bundesland (Vorbelegung für Feiertags-Autoimport)

Revision ID: 0013_app_settings_bundesland
Revises: 0012_holidays_and_leave_entitlements
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_app_settings_bundesland"
down_revision: Union[str, None] = "0012_holidays_and_leave_entitlements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("default_bundesland", sa.String(2), nullable=True))


def downgrade() -> None:
    op.drop_column("app_settings", "default_bundesland")
