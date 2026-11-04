"""Standort-Bundesland, standortbezogene Feiertage, Eintritt/Austritt,
Arbeitszeitmodell-Vorlagen

Revision ID: 0015_locations_holidays_employees_templates
Revises: 0014_employee_nfc_uid
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_locations_holidays_employees_templates"
down_revision: Union[str, None] = "0014_employee_nfc_uid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("locations", sa.Column("bundesland", sa.String(2), nullable=True))

    op.add_column("holidays", sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True))
    op.create_index("ix_holidays_date_location", "holidays", ["date", "location_id"])

    op.add_column("employees", sa.Column("hire_date", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("termination_date", sa.Date(), nullable=True))

    op.create_table(
        "work_time_model_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("weekly_hours", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("work_days_per_week", sa.Integer(), nullable=False, server_default="5"),
    )
    op.bulk_insert(
        sa.table(
            "work_time_model_templates",
            sa.column("name", sa.String()),
            sa.column("weekly_hours", sa.Numeric()),
            sa.column("work_days_per_week", sa.Integer()),
        ),
        [
            {"name": "Vollzeit Mo-Fr (40h)", "weekly_hours": 40, "work_days_per_week": 5},
            {"name": "Vollzeit Mo-Sa, 1 Tag frei (40h)", "weekly_hours": 40, "work_days_per_week": 5},
            {"name": "Teilzeit 50% (20h)", "weekly_hours": 20, "work_days_per_week": 5},
        ],
    )


def downgrade() -> None:
    op.drop_table("work_time_model_templates")
    op.drop_column("employees", "termination_date")
    op.drop_column("employees", "hire_date")
    op.drop_index("ix_holidays_date_location", table_name="holidays")
    op.drop_column("holidays", "location_id")
    op.drop_column("locations", "bundesland")
