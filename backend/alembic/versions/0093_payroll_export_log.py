"""Protokoll der Lohn-Exporte (CSV und DATEV): wer hat welchen Zeitraum wann exportiert

Revision ID: 0093_payroll_export_log
Revises: 0092_wage_types
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0093_payroll_export_log"
down_revision: Union[str, None] = "0092_wage_types"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payroll_export_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("employee_count", sa.Integer(), nullable=False),
        sa.Column("created_by_hr_user_id", sa.Integer(), sa.ForeignKey("hr_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_payroll_export_logs_tenant", "payroll_export_logs", ["tenant_id", "date_from"])


def downgrade() -> None:
    op.drop_index("ix_payroll_export_logs_tenant", table_name="payroll_export_logs")
    op.drop_table("payroll_export_logs")
