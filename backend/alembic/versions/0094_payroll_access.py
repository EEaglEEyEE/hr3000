"""Berechtigung „Vergütung & Lohn-Export“ für HR (Admins haben sie immer)

Revision ID: 0094_payroll_access
Revises: 0093_payroll_export_log
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0094_payroll_access"
down_revision: Union[str, None] = "0093_payroll_export_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hr_users", sa.Column("payroll_access", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("employees", sa.Column("hr_payroll_access", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("employees", "hr_payroll_access")
    op.drop_column("hr_users", "payroll_access")
