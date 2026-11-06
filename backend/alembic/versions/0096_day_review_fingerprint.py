"""„Erledigt“ mit Fingerabdruck: ändert sich der Tag danach, ist er wieder offen

DayReview.fingerprint = Status|Soll|Ist|Hinweise des Tages beim Abhaken. Bestehende Einträge
bleiben ohne Fingerabdruck gültig (wie bisher).

Revision ID: 0096_day_review_fingerprint
Revises: 0095_surcharge_history
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0096_day_review_fingerprint"
down_revision: Union[str, None] = "0095_surcharge_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("day_reviews", sa.Column("fingerprint", sa.String(250), nullable=True))


def downgrade() -> None:
    op.drop_column("day_reviews", "fingerprint")
