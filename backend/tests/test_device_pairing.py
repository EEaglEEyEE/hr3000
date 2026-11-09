"""Tablet koppeln per Kurzcode und Darstellung je Tablet."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, HrRole, Account, Location
from app.services.auth_service import hash_password
from app.services.pairing_service import token_hash


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    device = Device(name="Tablet", location_id=location.id, token_hash=token_hash("long-device-token-123456"))
    db_session.add_all([device, Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)])
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]
    return device, {"Authorization": f"Bearer {token}"}


async def test_pairing_code_is_single_use(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)
    r = await client.post(f"/devices/{device.id}/pairing-code", headers=hr)
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert len(code) == 9 and code[4] == "-"

    # Kleinschreibung/ohne Bindestrich wird akzeptiert.
    r = await client.post("/auth/device/pair", json={"code": code.replace("-", "").lower(), "installation_id": "tablet-a-0123456789"})
    # Koppeln erzeugt ein neues Token (das alte gilt nicht mehr) und bindet es an dieses Tablet
    assert r.status_code == 200 and r.json()["device_token"] != "long-device-token-123456"
    assert (await client.post("/auth/device/login", json={"device_token": "long-device-token-123456"})).status_code == 401
    again = await client.post("/auth/device/pair", json={"code": code, "installation_id": "tablet-a-0123456789"})
    assert again.status_code == 401 and again.json()["code"] == "PAIRING_CODE_INVALID"
    assert (await client.post(f"/devices/{device.id}/pairing-code")).status_code in (401, 403)


async def test_device_theme_overrides_tenant_default(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)
    login = (await client.post("/auth/device/login", json={"device_token": "long-device-token-123456"})).json()
    assert login["theme"] == "DARK"
    device_headers = {"Authorization": f"Bearer {login['access_token']}"}

    r = await client.patch(f"/devices/{device.id}", headers=hr, json={"theme": "LIGHT"})
    assert r.status_code == 200 and r.json()["theme"] == "LIGHT"
    assert (await client.get("/device/config", headers=device_headers)).json()["theme"] == "LIGHT"
    r = await client.patch(f"/devices/{device.id}", headers=hr, json={"theme": "DEFAULT"})
    assert r.json()["theme"] is None
    assert (await client.get("/device/config", headers=device_headers)).json()["theme"] == "DARK"
    assert (await client.patch(f"/devices/{device.id}", headers=hr, json={"theme": "PINK"})).status_code == 422
