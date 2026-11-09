"""Vorschläge von Mitarbeitern zu eigenen Daten (verschlüsselt) und zwei Benachrichtigungsarten.

Revision ID: 0125_change_requests
Revises: 0124_attributes
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0125_change_requests"
down_revision: Union[str, None] = "0124_attributes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOTIFY_BASE = ['ABSENCE_REQUESTED', 'ABSENCE_DECIDED', 'OPEN_DAYS_DIGEST', 'PERIOD_SUBMITTED', 'PERIOD_DISPUTED', 'CORRECTION_REQUESTED', 'CORRECTION_DECIDED', 'SUBSTITUTE_ASSIGNED', 'REMINDER', 'DEVICE_ALERT']
_NOTIFY_OLD = sa.Enum(*_NOTIFY_BASE, name="notificationtype")
_NOTIFY_NEW = sa.Enum(*_NOTIFY_BASE, "DATA_CHANGE_REQUESTED", "DATA_CHANGE_DECIDED", name="notificationtype")


def upgrade() -> None:
    op.create_table(
        "data_change_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("changes", sa.Text(), nullable=False),
        sa.Column("contains_payroll", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_by_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.String(300), nullable=True),
    )
    op.create_index("ix_data_change_requests_employee_id", "data_change_requests", ["employee_id"])
    op.alter_column("notifications", "type", existing_type=_NOTIFY_OLD, type_=_NOTIFY_NEW, existing_nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type IN ('DATA_CHANGE_REQUESTED', 'DATA_CHANGE_DECIDED')")
    op.alter_column("notifications", "type", existing_type=_NOTIFY_NEW, type_=_NOTIFY_OLD, existing_nullable=False)
    op.drop_table("data_change_requests")
