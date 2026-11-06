"""Server-Auslastung mit Verlauf für den Super-Admin: ein Messwert je Minute (CPU, Last, Speicher,
Datenträger), plattformweit ohne Mandantenbezug.

Revision ID: 0099_server_metrics
Revises: 0098_vacation_entitlement
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0099_server_metrics"
down_revision: Union[str, None] = "0098_vacation_entitlement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "server_metric_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sampled_at", sa.DateTime(), nullable=False),
        sa.Column("cpu_percent", sa.Float(), nullable=True),
        sa.Column("load_1", sa.Float(), nullable=True),
        sa.Column("memory_used_bytes", sa.BigInteger(), nullable=True),
        sa.Column("memory_total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("disk_used_bytes", sa.BigInteger(), nullable=True),
        sa.Column("disk_total_bytes", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_server_metric_samples_sampled_at", "server_metric_samples", ["sampled_at"])


def downgrade() -> None:
    op.drop_index("ix_server_metric_samples_sampled_at", table_name="server_metric_samples")
    op.drop_table("server_metric_samples")
