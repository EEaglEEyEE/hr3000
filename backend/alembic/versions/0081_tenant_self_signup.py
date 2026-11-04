"""Selbstregistrierung über hr3000.de/registrieren: Herkunft und Zustimmung je Mandant

Revision ID: 0081_tenant_self_signup
Revises: 0080_kiosk_screen_hours
Create Date: 2026-11-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0081_tenant_self_signup"
down_revision: Union[str, None] = "0080_kiosk_screen_hours"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bestehende Mandanten hat der Super-Admin angelegt -> false.
    op.add_column("tenants", sa.Column("self_signup", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Nachweis der Zustimmung zu Nutzungsbedingungen + AV-Vertrag (Zeitpunkt UTC, Fassung).
    op.add_column("tenants", sa.Column("terms_accepted_at", sa.DateTime(), nullable=True))
    op.add_column("tenants", sa.Column("terms_version", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "terms_version")
    op.drop_column("tenants", "terms_accepted_at")
    op.drop_column("tenants", "self_signup")
