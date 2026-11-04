"""Zuschlagsregeln (Nacht/Sonntag/Feiertag/Mehrarbeit/frei)

Revision ID: 0051_surcharge_rules
Revises: 0050_period_closures
Create Date: 2026-10-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0051_surcharge_rules"
down_revision: Union[str, None] = "0050_period_closures"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "surcharge_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("NIGHT", "SUNDAY", "HOLIDAY", "OVERTIME", "CUSTOM", name="surchargekind"),
            nullable=False,
        ),
        sa.Column("percent", sa.Numeric(6, 2), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("weekdays_mask", sa.Integer(), nullable=False, server_default="127"),
        sa.Column("exclusive_group", sa.String(50), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_surcharge_rules_tenant", "surcharge_rules", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_surcharge_rules_tenant", table_name="surcharge_rules")
    op.drop_table("surcharge_rules")
