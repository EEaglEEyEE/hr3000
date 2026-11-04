"""app_settings.open_days_digest_sent_at

Revision ID: 0044_app_settings_open_days_digest_sent_at
Revises: 0043_notification_type_open_days_digest
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0044_app_settings_open_days_digest_sent_at"
down_revision: Union[str, None] = "0043_notification_type_open_days_digest"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("open_days_digest_sent_at", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("app_settings", "open_days_digest_sent_at")
