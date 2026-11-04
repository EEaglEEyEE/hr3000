"""Monatsabschluss: period_closures + Benachrichtigungstypen

Revision ID: 0050_period_closures
Revises: 0049_employee_documents_and_audit_actions
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0050_period_closures"
down_revision: Union[str, None] = "0049_employee_documents_and_audit_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_ENUM = sa.Enum("ABSENCE_REQUESTED", "ABSENCE_DECIDED", "OPEN_DAYS_DIGEST", name="notificationtype")
_NEW_ENUM = sa.Enum(
    "ABSENCE_REQUESTED", "ABSENCE_DECIDED", "OPEN_DAYS_DIGEST", "PERIOD_SUBMITTED", "PERIOD_DISPUTED",
    name="notificationtype",
)


def upgrade() -> None:
    op.create_table(
        "period_closures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("SUBMITTED", "CONFIRMED", "DISPUTED", "CLOSED", name="periodstatus"),
            nullable=False,
        ),
        sa.Column("target_minutes", sa.Integer(), nullable=False),
        sa.Column("actual_minutes", sa.Integer(), nullable=False),
        sa.Column("delta_minutes", sa.Integer(), nullable=False),
        sa.Column("balance_end_minutes", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("employee_documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_sha256", sa.String(64), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_by_hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("submitted_by_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("disputed_at", sa.DateTime(), nullable=True),
        sa.Column("dispute_reason", sa.String(500), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("closed_without_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("employee_id", "year", "month", name="uq_period_closures_employee_month"),
    )
    op.create_index("ix_period_closures_tenant_month", "period_closures", ["tenant_id", "year", "month"])
    op.alter_column(
        "notifications", "type", existing_type=_OLD_ENUM, type_=_NEW_ENUM, existing_nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "notifications", "type", existing_type=_NEW_ENUM, type_=_OLD_ENUM, existing_nullable=False
    )
    op.drop_index("ix_period_closures_tenant_month", table_name="period_closures")
    op.drop_table("period_closures")
