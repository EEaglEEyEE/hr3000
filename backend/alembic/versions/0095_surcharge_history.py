"""Zuschlagsregeln mit Verlauf: Änderungen an Satz, Zeitfenster und Wochentagen gelten ab einem Tag

- valid_from/valid_to je Fassung (leer = seit jeher bzw. offen); bestehende Regeln bleiben "seit
  jeher" gültig, an der Berechnung ändert sich nichts.
- family_id verbindet die Fassungen einer Regel (leer = die Regel selbst ist die erste Fassung).

Revision ID: 0095_surcharge_history
Revises: 0094_payroll_access
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0095_surcharge_history"
down_revision: Union[str, None] = "0094_payroll_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("surcharge_rules", sa.Column("valid_from", sa.Date(), nullable=True))
    op.add_column("surcharge_rules", sa.Column("valid_to", sa.Date(), nullable=True))
    op.add_column("surcharge_rules", sa.Column("family_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("surcharge_rules", "family_id")
    op.drop_column("surcharge_rules", "valid_to")
    op.drop_column("surcharge_rules", "valid_from")
