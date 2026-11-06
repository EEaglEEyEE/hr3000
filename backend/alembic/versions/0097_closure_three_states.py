"""Monatsabschluss mit drei Zuständen: Vorgelegt → Abgeschlossen (bzw. Widerspruch)

"Vom Mitarbeiter bestätigt" wirkte wie "abgeschlossen" (gesperrt, Wieder öffnen nur Admin) –
die Bestätigung schließt jetzt direkt ab. Bestehende bestätigte Monate werden abgeschlossen
(mit Zeitpunkt der Bestätigung), danach entfällt der Wert CONFIRMED.

Revision ID: 0097_closure_three_states
Revises: 0096_day_review_fingerprint
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0097_closure_three_states"
down_revision: Union[str, None] = "0096_day_review_fingerprint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = sa.Enum("SUBMITTED", "CONFIRMED", "DISPUTED", "CLOSED", name="periodstatus")
_NEW = sa.Enum("SUBMITTED", "DISPUTED", "CLOSED", name="periodstatus")


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE period_closures SET status = 'CLOSED', closed_at = COALESCE(closed_at, confirmed_at), "
            "closed_without_confirmation = 0 WHERE status = 'CONFIRMED'"
        )
    )
    with op.batch_alter_table("period_closures") as batch:
        batch.alter_column("status", existing_type=_OLD, type_=_NEW, existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("period_closures") as batch:
        batch.alter_column("status", existing_type=_NEW, type_=_OLD, existing_nullable=False)
