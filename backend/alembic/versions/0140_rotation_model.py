"""Mehrwöchiges Arbeitszeitmodell (Turnus über 2–4 Wochen): rotation_minutes (Soll-Minuten je Woche
und Wochentag, Wochen durch ";" getrennt) und rotation_start (Montag der Woche 1) an der Fassung der
Arbeitszeit und an der Fassung eines Arbeitszeitmodells. NULL = kein Turnus – bestehende Einträge
bleiben also unverändert.

Revision ID: 0140_rotation_model
Revises: 0137_payroll_accounting
Create Date: 2026-11-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0140_rotation_model"
down_revision: Union[str, None] = "0137_payroll_accounting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("employee_default_shifts", "work_time_profile_versions")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("rotation_minutes", sa.String(160), nullable=True))
        op.add_column(table, sa.Column("rotation_start", sa.Date(), nullable=True))


def downgrade() -> None:
    # Ohne die Spalten gilt für solche Fassungen das durchschnittliche Wochensoll (target_minutes),
    # gleichmäßig verteilt auf alle Tage, die in irgendeiner Turnus-Woche Arbeitstag waren.
    for table in TABLES:
        op.drop_column(table, "rotation_start")
        op.drop_column(table, "rotation_minutes")
