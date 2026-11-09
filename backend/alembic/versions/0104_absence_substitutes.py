"""Vertretung bei Abwesenheiten: Einstellung je Abwesenheitsart, Vertretung am Eintrag,
Benachrichtigung an die Vertretung.

Revision ID: 0104_absence_substitutes
Revises: 0103_half_holidays
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0104_absence_substitutes"
down_revision: Union[str, None] = "0103_half_holidays"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOTIFY_BASE = [
    "ABSENCE_REQUESTED", "ABSENCE_DECIDED", "OPEN_DAYS_DIGEST", "PERIOD_SUBMITTED", "PERIOD_DISPUTED",
    "CORRECTION_REQUESTED", "CORRECTION_DECIDED",
]
_NOTIFY_OLD = sa.Enum(*_NOTIFY_BASE, name="notificationtype")
_NOTIFY_NEW = sa.Enum(*_NOTIFY_BASE, "SUBSTITUTE_ASSIGNED", name="notificationtype")


def upgrade() -> None:
    op.add_column(
        "absence_type_definitions",
        sa.Column("substitute_mode", sa.String(10), nullable=False, server_default="NONE"),
    )
    op.add_column("absences", sa.Column("substitute_employee_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_absences_substitute_employee_id", "absences", "employees", ["substitute_employee_id"], ["id"]
    )
    op.alter_column("notifications", "type", existing_type=_NOTIFY_OLD, type_=_NOTIFY_NEW, existing_nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'SUBSTITUTE_ASSIGNED'")
    op.alter_column("notifications", "type", existing_type=_NOTIFY_NEW, type_=_NOTIFY_OLD, existing_nullable=False)
    op.drop_constraint("fk_absences_substitute_employee_id", "absences", type_="foreignkey")
    op.drop_column("absences", "substitute_employee_id")
    op.drop_column("absence_type_definitions", "substitute_mode")
