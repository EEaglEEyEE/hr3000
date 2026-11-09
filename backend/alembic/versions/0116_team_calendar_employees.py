"""Teamkalender für Mitarbeiter: Einstellung und Sichtbarkeit je Abwesenheitsart (grau/farbig).

Revision ID: 0116_team_calendar_employees
Revises: 0115_leave_adjustments
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0116_team_calendar_employees"
down_revision: Union[str, None] = "0115_leave_adjustments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("team_calendar_for_employees", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("absence_type_definitions", sa.Column("calendar_visibility", sa.String(10), nullable=False, server_default="GREY"))


def downgrade() -> None:
    op.drop_column("absence_type_definitions", "calendar_visibility")
    op.drop_column("app_settings", "team_calendar_for_employees")
