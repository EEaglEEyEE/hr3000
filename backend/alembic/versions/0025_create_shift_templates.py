"""shift_templates

Revision ID: 0025_create_shift_templates
Revises: 0024_create_teams_and_supervisor_assignments
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025_create_shift_templates"
down_revision: Union[str, None] = "0024_create_teams_and_supervisor_assignments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shift_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column(
            "break_mode",
            sa.Enum("FIXED", "FLEXIBLE", name="breakmode"),
            nullable=False,
            server_default="FLEXIBLE",
        ),
        sa.Column("fixed_break_start", sa.Time(), nullable=True),
        sa.Column("fixed_break_end", sa.Time(), nullable=True),
        sa.Column("min_break_minutes", sa.Integer(), nullable=True),
        sa.Column("target_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.UniqueConstraint("tenant_id", "name", name="uq_shift_templates_tenant_name"),
    )


def downgrade() -> None:
    op.drop_table("shift_templates")
