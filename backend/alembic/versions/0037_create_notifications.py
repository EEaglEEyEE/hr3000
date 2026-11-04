"""notifications

Revision ID: 0037_create_notifications
Revises: 0036_create_audit_log_entries
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0037_create_notifications"
down_revision: Union[str, None] = "0036_create_audit_log_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("recipient_hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("recipient_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column(
            "type",
            sa.Enum("ABSENCE_REQUESTED", "ABSENCE_DECIDED", name="notificationtype"),
            nullable=False,
        ),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("related_absence_id", sa.Integer(), sa.ForeignKey("absences.id"), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_notifications_recipient_hr_user", "notifications", ["tenant_id", "recipient_hr_user_id"]
    )
    op.create_index(
        "ix_notifications_recipient_employee", "notifications", ["tenant_id", "recipient_employee_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_employee", table_name="notifications")
    op.drop_index("ix_notifications_recipient_hr_user", table_name="notifications")
    op.drop_table("notifications")
