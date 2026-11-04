"""work_time_models + work_time_model_templates droppen

Revision ID: 0031_drop_work_time_models
Revises: 0030_migrate_work_time_models_to_shift_templates
Create Date: 2026-08-12

Nur auszuführen NACH verifiziertem Lauf von 0030 (siehe deren Report-Ausgabe)
– vollständig ersetzt durch shift_templates/employee_default_shifts/
shift_plan_entries, siehe Migrationsplan Abschnitt C.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0031_drop_work_time_models"
down_revision: Union[str, None] = "0030_migrate_work_time_models_to_shift_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("work_time_models")
    op.drop_table("work_time_model_templates")


def downgrade() -> None:
    op.create_table(
        "work_time_model_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("weekly_hours", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("work_days_per_week", sa.Integer(), nullable=False, server_default="5"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_work_time_model_templates_tenant_name"),
    )
    op.create_table(
        "work_time_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("weekly_hours", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("work_days_per_week", sa.Integer(), nullable=False, server_default="6"),
    )
