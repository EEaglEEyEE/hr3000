"""Weitere Abwesenheitskategorien: Arbeitszeit, Feiertag, Kind krank

Revision ID: 0078_more_absence_categories
Revises: 0077_absence_duration
Create Date: 2026-10-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0078_more_absence_categories"
down_revision: Union[str, None] = "0077_absence_duration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BASE = ["VACATION", "SICK", "SPECIAL_LEAVE", "UNPAID", "TIME_OFF_IN_LIEU"]
_OLD = sa.Enum(*_BASE, name="absencetype")
_NEW = sa.Enum(*_BASE, "WORK_TIME", "PUBLIC_HOLIDAY", "CHILD_SICK", name="absencetype")


def upgrade() -> None:
    op.alter_column("absences", "type", existing_type=_OLD, type_=_NEW, existing_nullable=False)
    op.alter_column("absence_type_definitions", "category", existing_type=_OLD, type_=_NEW, existing_nullable=False)


def downgrade() -> None:
    op.alter_column("absence_type_definitions", "category", existing_type=_NEW, type_=_OLD, existing_nullable=False)
    op.alter_column("absences", "type", existing_type=_NEW, type_=_OLD, existing_nullable=False)
