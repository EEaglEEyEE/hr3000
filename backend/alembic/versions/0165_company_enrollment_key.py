"""Firmenschlüssel für die Tablet-Registrierung.

Ein Registrierungsschlüssel kann jetzt für die ganze Firma gelten (device_enrollment_keys.location_id
NULL); Geräte, die sich damit melden, warten ohne Standort auf Freigabe (device_enrollments.location_id
NULL), der Standort wird bei der Freigabe gewählt. Anlass: Endpoint Central setzt die App-Konfiguration
der Android-App nur je App, nicht je Gerät – ein Schlüssel je Standort lässt sich dort nicht verteilen
(Johannes, 15.11.2026). Bestehende Schlüssel und Anfragen behalten ihren Standort.

Revision ID: 0165_company_enrollment_key
Revises: 0164_device_presence
Create Date: 2026-11-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0165_company_enrollment_key"
down_revision: Union[str, None] = "0164_device_presence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch: unter MySQL ein einfaches ALTER TABLE … MODIFY (Fremdschlüssel bleibt), unter SQLite (Tests)
    # baut Alembic die Tabelle neu auf
    with op.batch_alter_table("device_enrollment_keys") as batch:
        batch.alter_column("location_id", existing_type=sa.Integer(), nullable=True)
    with op.batch_alter_table("device_enrollments") as batch:
        batch.alter_column("location_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Ohne Standort ist beides nicht darstellbar: Firmenschlüssel und ihre offenen Anfragen entfallen
    op.execute("DELETE FROM device_enrollments WHERE location_id IS NULL")
    op.execute("DELETE FROM device_enrollment_keys WHERE location_id IS NULL")
    with op.batch_alter_table("device_enrollments") as batch:
        batch.alter_column("location_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("device_enrollment_keys") as batch:
        batch.alter_column("location_id", existing_type=sa.Integer(), nullable=False)
