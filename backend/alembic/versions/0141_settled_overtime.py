"""Monatlich mit dem Gehalt abgegoltene Überstunden: settled_overtime_minutes an der Fassung der
Arbeitszeit und an der Fassung eines Arbeitszeitmodells (NULL = aus), settled_minutes im
Überstundenkonto (abgegoltene Minuten des Monats bis zu diesem Tag) und im Schnappschuss des
Monatsabschlusses. Bestehende Fassungen haben keine Grenze, das Konto bleibt unverändert.

Revision ID: 0141_settled_overtime
Revises: 0140_rotation_model
Create Date: 2026-11-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0141_settled_overtime"
down_revision: Union[str, None] = "0140_rotation_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VERSION_TABLES = ("employee_default_shifts", "work_time_profile_versions")
SNAPSHOT_TABLES = ("overtime_balances", "period_closures")


def upgrade() -> None:
    for table in VERSION_TABLES:
        op.add_column(table, sa.Column("settled_overtime_minutes", sa.Integer(), nullable=True))
    for table in SNAPSHOT_TABLES:
        op.add_column(table, sa.Column("settled_minutes", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    # Ohne Grenze rechnet das Konto beim nächsten Lesen nicht neu: wer zurückgeht, setzt die Konten
    # der Betroffenen per invalidate_balance zurück.
    for table in SNAPSHOT_TABLES:
        op.drop_column(table, "settled_minutes")
    for table in VERSION_TABLES:
        op.drop_column(table, "settled_overtime_minutes")
