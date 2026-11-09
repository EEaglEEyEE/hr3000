"""Einmalzahlungen in Prozent des Monatsgehalts und jährlich wiederkehrend (Urlaubsgeld,
Weihnachtsgeld, 13./14. Monatsgehalt).

Revision ID: 0112_percent_yearly_payments
Revises: 0111_notification_emails
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0112_percent_yearly_payments"
down_revision: Union[str, None] = "0111_notification_emails"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pay_components", sa.Column("percent_of_salary", sa.Numeric(5, 2), nullable=True))
    op.add_column("pay_components", sa.Column("recurs_yearly", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("pay_components", "recurs_yearly")
    op.drop_column("pay_components", "percent_of_salary")
