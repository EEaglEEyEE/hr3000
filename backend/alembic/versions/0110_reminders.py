"""Erinnerungen (Probezeit, Befristung, Austritt, verfallender Urlaub): Einstellung, Tagesmarke,
Benachrichtigungsart.

Revision ID: 0110_reminders
Revises: 0109_audit_login
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0110_reminders"
down_revision: Union[str, None] = "0109_audit_login"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOTIFY_BASE = [
    "ABSENCE_REQUESTED", "ABSENCE_DECIDED", "OPEN_DAYS_DIGEST", "PERIOD_SUBMITTED", "PERIOD_DISPUTED",
    "CORRECTION_REQUESTED", "CORRECTION_DECIDED", "SUBSTITUTE_ASSIGNED",
]
_NOTIFY_OLD = sa.Enum(*_NOTIFY_BASE, name="notificationtype")
_NOTIFY_NEW = sa.Enum(*_NOTIFY_BASE, "REMINDER", name="notificationtype")


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("app_settings", sa.Column("reminders_sent_on", sa.Date(), nullable=True))
    op.alter_column("notifications", "type", existing_type=_NOTIFY_OLD, type_=_NOTIFY_NEW, existing_nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'REMINDER'")
    op.alter_column("notifications", "type", existing_type=_NOTIFY_NEW, type_=_NOTIFY_OLD, existing_nullable=False)
    op.drop_column("app_settings", "reminders_sent_on")
    op.drop_column("app_settings", "reminders_enabled")
