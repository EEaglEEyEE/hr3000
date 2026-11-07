"""Index für Stempelungen je Mitarbeiter und Zeitraum

Die häufigste Abfrage auf `punches` (Tagesberechnung, Stempelliste, Export) filtert nach
`employee_id` und einem Bereich von `timestamp_utc`. Bisher gab es nur den Einzelindex des
Fremdschlüssels auf `employee_id`; der bleibt bestehen (MySQL braucht ihn nicht mehr, Entfernen
bringt aber nichts).

Revision ID: 0100_punch_employee_time_index
Revises: 0099_server_metrics
Create Date: 2026-11-07

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0100_punch_employee_time_index"
down_revision: Union[str, None] = "0099_server_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_punches_employee_time", "punches", ["employee_id", "timestamp_utc"])


def downgrade() -> None:
    op.drop_index("ix_punches_employee_time", table_name="punches")
