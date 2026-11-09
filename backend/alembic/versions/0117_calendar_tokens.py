"""Kalender-Abo (iCal): Hash des geheimen Tokens an Mitarbeitern und HR-Konten.

Revision ID: 0117_calendar_tokens
Revises: 0116_team_calendar_employees
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0117_calendar_tokens"
down_revision: Union[str, None] = "0116_team_calendar_employees"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("employees", "hr_users"):
        op.add_column(table, sa.Column("calendar_token_hash", sa.String(64), nullable=True))
        op.create_unique_constraint(f"uq_{table}_calendar_token_hash", table, ["calendar_token_hash"])


def downgrade() -> None:
    for table in ("hr_users", "employees"):
        op.drop_constraint(f"uq_{table}_calendar_token_hash", table, type_="unique")
        op.drop_column(table, "calendar_token_hash")
