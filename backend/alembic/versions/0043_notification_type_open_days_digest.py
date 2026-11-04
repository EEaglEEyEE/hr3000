"""notifications.type: OPEN_DAYS_DIGEST

Revision ID: 0043_notification_type_open_days_digest
Revises: 0042_audit_action_anonymized
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0043_notification_type_open_days_digest"
down_revision: Union[str, None] = "0042_audit_action_anonymized"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_ENUM = sa.Enum("ABSENCE_REQUESTED", "ABSENCE_DECIDED", name="notificationtype")
_NEW_ENUM = sa.Enum("ABSENCE_REQUESTED", "ABSENCE_DECIDED", "OPEN_DAYS_DIGEST", name="notificationtype")


def upgrade() -> None:
    op.alter_column(
        "notifications",
        "type",
        existing_type=_OLD_ENUM,
        type_=_NEW_ENUM,
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "notifications",
        "type",
        existing_type=_NEW_ENUM,
        type_=_OLD_ENUM,
        existing_nullable=False,
    )
