"""add self-service login fields to employees

Revision ID: 0005_employee_self_service_login
Revises: 0004_daily_summary_absence_status
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_employee_self_service_login"
down_revision: Union[str, None] = "0004_daily_summary_absence_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("login_email", sa.String(255), nullable=True))
    op.add_column("employees", sa.Column("password_hash", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_employees_login_email", "employees", ["login_email"])


def downgrade() -> None:
    op.drop_constraint("uq_employees_login_email", "employees", type_="unique")
    op.drop_column("employees", "password_hash")
    op.drop_column("employees", "login_email")
