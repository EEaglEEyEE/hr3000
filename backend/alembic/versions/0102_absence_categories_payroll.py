"""Weitere Abwesenheitskategorien für die Lohnabrechnung: Mutterschutz/Elternzeit, Kurzarbeit,
Unentschuldigtes Fehlen, Pflege von Angehörigen (rechnen wie „Unbezahlt“, Soll entfällt).

Revision ID: 0102_absence_categories_payroll
Revises: 0101_work_time_profiles
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0102_absence_categories_payroll"
down_revision: Union[str, None] = "0101_work_time_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BASE = ["VACATION", "SICK", "SPECIAL_LEAVE", "UNPAID", "TIME_OFF_IN_LIEU", "WORK_TIME", "PUBLIC_HOLIDAY", "CHILD_SICK"]
_NEW_VALUES = ["PARENTAL_LEAVE", "SHORT_TIME_WORK", "UNEXCUSED", "CARE_LEAVE"]
_OLD = sa.Enum(*_BASE, name="absencetype")
_NEW = sa.Enum(*_BASE, *_NEW_VALUES, name="absencetype")


def upgrade() -> None:
    op.alter_column("absences", "type", existing_type=_OLD, type_=_NEW, existing_nullable=False)
    op.alter_column("absence_type_definitions", "category", existing_type=_OLD, type_=_NEW, existing_nullable=False)


def downgrade() -> None:
    # Einträge mit den neuen Kategorien zuvor auf „Unbezahlt“ setzen (gleiche Berechnung).
    values = ", ".join(f"'{v}'" for v in _NEW_VALUES)
    op.execute(f"UPDATE absences SET type = 'UNPAID' WHERE type IN ({values})")
    op.execute(f"UPDATE absence_type_definitions SET category = 'UNPAID' WHERE category IN ({values})")
    op.alter_column("absence_type_definitions", "category", existing_type=_NEW, type_=_OLD, existing_nullable=False)
    op.alter_column("absences", "type", existing_type=_NEW, type_=_OLD, existing_nullable=False)
