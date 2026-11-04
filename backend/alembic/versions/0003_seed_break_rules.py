"""seed break_rules with §4 ArbZG staffel

Revision ID: 0003_seed_break_rules
Revises: 0002_punch_idempotency_key
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_seed_break_rules"
down_revision: Union[str, None] = "0002_punch_idempotency_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

break_rules_table = sa.table(
    "break_rules",
    sa.column("min_work_minutes", sa.Integer),
    sa.column("deduct_minutes", sa.Integer),
)


def upgrade() -> None:
    op.bulk_insert(
        break_rules_table,
        [
            {"min_work_minutes": 360, "deduct_minutes": 30},
            {"min_work_minutes": 540, "deduct_minutes": 45},
        ],
    )


def downgrade() -> None:
    op.execute(
        break_rules_table.delete().where(
            break_rules_table.c.min_work_minutes.in_([360, 540])
        )
    )
