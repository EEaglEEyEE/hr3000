"""add idempotency_key to punches

Revision ID: 0002_punch_idempotency_key
Revises: 0001_initial_schema
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_punch_idempotency_key"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("punches", sa.Column("idempotency_key", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_punches_idempotency_key", "punches", ["idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_punches_idempotency_key", "punches", type_="unique")
    op.drop_column("punches", "idempotency_key")
