"""Persönliche Einstellung: Benachrichtigungen zusätzlich per E-Mail (Standard an).

Revision ID: 0111_notification_emails
Revises: 0110_reminders
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0111_notification_emails"
down_revision: Union[str, None] = "0110_reminders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("hr_users", "employees"):
        op.add_column(table, sa.Column("notification_emails", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    for table in ("employees", "hr_users"):
        op.drop_column(table, "notification_emails")
