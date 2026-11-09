"""Ein Tablet-Zugang = ein Gerät: weitere Geräte mit demselben Token werden abgewiesen (Warnung an HR);
Koppeln erzeugt ein neues Token und beendet alte Sitzungen."""
from sqlalchemy import select

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLogEntry, Notification, NotificationType
from tests.test_device_pairing import _setup

TOKEN = "long-device-token-123456"
TABLET_A = "tablet-a-0123456789"
TABLET_B = "tablet-b-9876543210"


async def _login(client: AsyncClient, installation: str | None, token: str = TOKEN):
    body = {"device_token": token} | ({"installation_id": installation} if installation else {})
    return await client.post("/auth/device/login", json=body)


async def test_second_device_is_rejected_with_warning(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)
    assert (await _login(client, TABLET_A)).status_code == 200  # bindet an Tablet A
    devices = (await client.get("/devices", headers=hr)).json()
    assert devices[0]["bound_at"] is not None

    second = await _login(client, TABLET_B)
    assert second.status_code == 401 and second.json()["code"] == "DEVICE_IN_USE"
    assert (await _login(client, None)).status_code == 401  # alte Tablet-Version ohne ID: abgewiesen
    assert (await _login(client, TABLET_A)).status_code == 200  # das gebundene Tablet weiter ok

    alerts = (await db_session.execute(select(Notification).where(Notification.type == NotificationType.DEVICE_ALERT))).scalars().all()
    assert len(alerts) == 1 and "Tablet" in alerts[0].message  # nur eine Warnung pro Stunde
    audit = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.DEVICE_LOGIN_REJECTED))).scalars().all()
    assert len(audit) == 1
    assert (await client.get("/devices", headers=hr)).json()[0]["rejected_at"] is not None


async def test_pairing_moves_the_access_to_the_new_tablet(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)
    old_session = (await _login(client, TABLET_A)).json()["access_token"]
    old_headers = {"Authorization": f"Bearer {old_session}"}
    assert (await client.get("/device/config", headers=old_headers)).status_code == 200

    # Das Tablet ist verbunden: ein QR-Code nur mit ausdrücklichem Tausch
    refused = await client.post(f"/devices/{device.id}/pairing-code", headers=hr)
    assert refused.status_code == 409 and refused.json()["code"] == "DEVICE_BOUND"
    code = (await client.post(f"/devices/{device.id}/pairing-code", headers=hr, json={"replace_bound": True})).json()["code"]
    paired = await client.post("/auth/device/pair", json={"code": code, "installation_id": TABLET_B})
    new_token = paired.json()["device_token"]

    assert (await client.get("/device/config", headers=old_headers)).status_code == 401  # alte Sitzung endet
    assert (await _login(client, TABLET_A)).status_code == 401  # altes Token gilt nicht mehr
    assert (await _login(client, TABLET_B, new_token)).status_code == 200
    assert (await _login(client, TABLET_A, new_token)).json()["code"] == "DEVICE_IN_USE"
