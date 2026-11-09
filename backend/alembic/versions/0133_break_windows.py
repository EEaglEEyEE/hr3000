"""Mehrere feste Pausenzeiten je Arbeitszeitmodell: fixed_break_windows an der Fassung der Arbeitszeit
und an der Fassung eines Arbeitszeitmodells ("09:00-09:15,12:00-12:30"). NULL = höchstens eine feste
Pausenzeit aus fixed_break_start/-end – bestehende Einträge bleiben also unverändert.

Revision ID: 0133_break_windows
Revises: 0132_flex_frame_days
Create Date: 2026-11-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0133_break_windows"
down_revision: Union[str, None] = "0132_flex_frame_days"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("employee_default_shifts", "work_time_profile_versions")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("fixed_break_windows", sa.String(100), nullable=True))


def downgrade() -> None:
    # Zurück bleibt die erste Pausenzeit (fixed_break_start/-end ist immer die erste).
    for table in TABLES:
        op.drop_column(table, "fixed_break_windows")
