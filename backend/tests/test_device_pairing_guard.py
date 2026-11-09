"""QR-Code für ein schon verbundenes Tablet nur mit ausdrücklichem Tausch (Vorfall Staging 09.11.2026:
ein zweites Gerät übernahm per QR-Code den gerade freigegebenen MDM-Eintrag und meldete das MDM-Tablet
unbemerkt ab). Koppeln wird protokolliert, ein Tausch zusätzlich als Warnung gemeldet."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLogEntry, Device, Notification, NotificationType
from tests.test_device_pairing import _setup

TOKEN = "long-device-token-123456"
TABLET_A = "tablet-a-0123456789"
TABLET_B = "tablet-b-9876543210"


async def _login(client: AsyncClient, installation: str, token: str = TOKEN):
    return await client.post("/auth/device/login", json={"device_token": token, "installation_id": installation})


async def _code(client: AsyncClient, hr: dict, device_id: int, **body) -> dict:
    r = await client.post(f"/devices/{device_id}/pairing-code", headers=hr, **({"json": body} if body else {}))
    return {"status": r.status_code, **r.json()}


async def _pair(client: AsyncClient, code: str, installation: str):
    return await client.post("/auth/device/pair", json={"code": code, "installation_id": installation})


async def _audit(db_session: AsyncSession) -> list[str]:
    rows = (await db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.DEVICE_ENROLLMENT).order_by(AuditLogEntry.id)
    )).scalars().all()
    return [row.detail for row in rows]


async def _alerts(db_session: AsyncSession) -> list[Notification]:
    return list((await db_session.execute(select(Notification).where(Notification.type == NotificationType.DEVICE_ALERT))).scalars().all())


async def test_bound_tablet_needs_explicit_replacement(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)
    assert (await _login(client, TABLET_A)).status_code == 200  # verbunden mit Tablet A

    for body in ({}, {"replace_bound": False}):
        refused = await _code(client, hr, device.id, **body)
        assert refused["status"] == 409 and refused["code"] == "DEVICE_BOUND", body
        assert "„Tablet“" in refused["detail"] and "Neues Tablet" in refused["detail"]
    await db_session.refresh(device)
    assert device.pairing_code_hash is None  # kein Code erzeugt
    assert (await _login(client, TABLET_A)).status_code == 200  # Tablet A unberührt

    bad = await client.post(f"/devices/{device.id}/pairing-code", headers=hr, json={"replace": True})
    assert bad.status_code == 422  # unbekanntes Feld

    allowed = await _code(client, hr, device.id, replace_bound=True)
    assert allowed["status"] == 200 and len(allowed["code"]) == 9


async def test_replacing_a_bound_tablet_is_logged_and_reported(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)
    await _login(client, TABLET_A)
    code = (await _code(client, hr, device.id, replace_bound=True))["code"]
    paired = await _pair(client, code, TABLET_B)
    assert paired.status_code == 200, paired.text

    assert (await _login(client, TABLET_A)).status_code == 401  # bisheriges Gerät abgemeldet
    assert await _audit(db_session) == [
        "Tablet „Tablet“ per QR-Code mit einem anderen Gerät gekoppelt – das bisherige Gerät ist abgemeldet"
    ]
    alerts = await _alerts(db_session)
    assert len(alerts) == 1 and "„Tablet“ wurde per QR-Code mit einem anderen Gerät gekoppelt" in alerts[0].message


async def test_first_pairing_is_logged_without_warning(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)  # noch mit keinem Gerät verbunden
    code = await _code(client, hr, device.id)
    assert code["status"] == 200
    assert (await _pair(client, code["code"], TABLET_A)).status_code == 200
    assert await _audit(db_session) == ["Tablet „Tablet“ per QR-Code eingerichtet"]
    assert await _alerts(db_session) == []


async def test_repairing_the_same_tablet_is_no_replacement(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)
    await _login(client, TABLET_A)
    code = (await _code(client, hr, device.id, replace_bound=True))["code"]
    new_token = (await _pair(client, code, TABLET_A)).json()["device_token"]
    assert (await _login(client, TABLET_A, new_token)).status_code == 200
    assert await _audit(db_session) == ["Tablet „Tablet“ per QR-Code eingerichtet"]
    assert await _alerts(db_session) == []


async def test_code_for_an_unbound_tablet_expires_when_it_binds(client: AsyncClient, db_session: AsyncSession) -> None:
    """Code erzeugt, solange das Tablet frei war – meldet sich inzwischen ein Gerät an, darf ein
    zweites es mit diesem Code nicht mehr verdrängen."""
    device, hr = await _setup(db_session, client)
    code = (await _code(client, hr, device.id))["code"]
    assert (await _login(client, TABLET_A)).status_code == 200  # bindet
    late = await _pair(client, code, TABLET_B)
    assert late.status_code == 401 and late.json()["code"] == "PAIRING_CODE_INVALID"
    assert (await _login(client, TABLET_A)).status_code == 200
    await db_session.refresh(device)
    assert device.pairing_code_hash is None and device.pairing_code_expires_at is None


async def test_other_tenants_tablet_is_not_found(client: AsyncClient, db_session: AsyncSession) -> None:
    _, hr = await _setup(db_session, client)
    missing = await client.post("/devices/9999/pairing-code", headers=hr, json={"replace_bound": True})
    assert missing.status_code == 404
    assert (await db_session.execute(select(Device))).scalars().first() is not None
