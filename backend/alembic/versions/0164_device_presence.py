"""Live-Status der Tablets und Warnung bei längerem Ausfall.

Die Kiosk-App meldet sich regelmäßig (POST /device/heartbeat). Der Zeitpunkt steht wie bisher in
devices.last_seen; neu sind die Zahl der Stempelungen, die am Tablet noch auf die Übertragung warten, wie
viele davon der Server abgelehnt hat und wann zuletzt „länger als eine Stunde offline“ gewarnt wurde.
Bestehende Tablets bleiben ohne Angabe, bis sie sich melden.

Die Warnung ist je Mandant abschaltbar (app_settings.device_offline_alert) und bei allen Mandanten
eingeschaltet – von Johannes am 14.11.2026 so gewünscht („deaktivierbar“). Gewarnt wird nur für Tablets,
deren Kiosk-App sich schon einmal gemeldet hat.

Revision ID: 0164_device_presence
Revises: 0163_enrollment_origin
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0164_device_presence"
down_revision: Union[str, None] = "0163_enrollment_origin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("queued_punches", sa.Integer(), nullable=True))
    op.add_column("devices", sa.Column("failed_punches", sa.Integer(), nullable=True))
    op.add_column("devices", sa.Column("offline_alerted_at", sa.DateTime(), nullable=True))
    op.add_column(
        "app_settings", sa.Column("device_offline_alert", sa.Boolean(), nullable=False, server_default=sa.true())
    )


def downgrade() -> None:
    op.drop_column("app_settings", "device_offline_alert")
    op.drop_column("devices", "offline_alerted_at")
    op.drop_column("devices", "failed_punches")
    op.drop_column("devices", "queued_punches")
