"""Zulagen und Einmalzahlungen je Mitarbeiter

Revision ID: 0086_pay_components
Revises: 0085_core_time_by_weekday
Create Date: 2026-11-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0086_pay_components"
down_revision: Union[str, None] = "0085_core_time_by_weekday"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KIND = sa.Enum("ALLOWANCE", "ONE_TIME", name="paycomponentkind")
_UNIT = sa.Enum("PER_MONTH", "PER_HOUR", name="allowanceunit")


def upgrade() -> None:
    op.create_table(
        "pay_components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("kind", _KIND, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit", _UNIT, nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("pay_date", sa.Date(), nullable=True),
        sa.Column("wage_type", sa.String(10), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pay_components_employee", "pay_components", ["employee_id"])


def downgrade() -> None:
    op.drop_index("ix_pay_components_employee", table_name="pay_components")
    op.drop_table("pay_components")
    _UNIT.drop(op.get_bind(), checkfirst=True)
    _KIND.drop(op.get_bind(), checkfirst=True)
