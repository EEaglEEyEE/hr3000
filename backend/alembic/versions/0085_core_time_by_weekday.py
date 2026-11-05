"""Kernzeit je Wochentag (Mandant und eigene Kernzeit je Mitarbeiter)

Revision ID: 0085_core_time_by_weekday
Revises: 0084_break_rule_kinds
Create Date: 2026-11-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0085_core_time_by_weekday"
down_revision: Union[str, None] = "0084_break_rule_kinds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL = jeden Tag dieselbe Kernzeit (bisheriges Verhalten), siehe app/schemas/core_time.py.
    op.add_column("app_settings", sa.Column("core_time_days", sa.String(100), nullable=True))
    op.add_column("employees", sa.Column("core_time_days", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "core_time_days")
    op.drop_column("app_settings", "core_time_days")
