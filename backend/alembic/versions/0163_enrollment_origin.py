"""Offene Tablet-Registrierungen: Herkunft der Anfrage (Browser-Kennung, IP-Adresse) für die Freigabeliste.

Bestehende Anfragen bleiben ohne Angabe. Die Werte verschwinden mit der Anfrage (Freigabe, Ablehnung,
Verfall nach 24 Stunden ohne Meldung).

Revision ID: 0163_enrollment_origin
Revises: 0162_flexible_open_days
Create Date: 2026-11-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0163_enrollment_origin"
down_revision: Union[str, None] = "0162_flexible_open_days"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("device_enrollments", sa.Column("user_agent", sa.String(300), nullable=True))
    op.add_column("device_enrollments", sa.Column("client_ip", sa.String(45), nullable=True))


def downgrade() -> None:
    op.drop_column("device_enrollments", "client_ip")
    op.drop_column("device_enrollments", "user_agent")
