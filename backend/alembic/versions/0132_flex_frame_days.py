"""Gleitzeit-Rahmen je Wochentag: flex_frame_days an der Fassung der Arbeitszeit und an der Fassung
eines Arbeitszeitmodells (Format wie core_time_days, siehe app/schemas/core_time.py). NULL = jeden Tag
derselbe Rahmen aus flex_frame_start/-end – bestehende Einträge bleiben also unverändert.

Revision ID: 0132_flex_frame_days
Revises: 0131_two_factor_roles
Create Date: 2026-11-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0132_flex_frame_days"
down_revision: Union[str, None] = "0131_two_factor_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("employee_default_shifts", "work_time_profile_versions")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("flex_frame_days", sa.String(100), nullable=True))


def downgrade() -> None:
    # Ein Rahmen je Wochentag lässt sich nicht als ein Rahmen darstellen: solche Fassungen gelten
    # danach wieder wie in den Einstellungen.
    for table in TABLES:
        op.execute(
            f"UPDATE {table} SET flex_frame_mode = 'TENANT', flex_frame_start = NULL, flex_frame_end = NULL "
            "WHERE flex_frame_days IS NOT NULL"
        )
        op.drop_column(table, "flex_frame_days")
