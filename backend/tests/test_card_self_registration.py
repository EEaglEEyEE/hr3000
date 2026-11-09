"""Mitarbeiter registriert seinen RFID-Chip selbst am Kiosk (nur mit PIN)."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLogEntry, Device, Employee, HrRole, Account, Location
from app.services.auth_service import hash_password
from app.services.pairing_service import token_hash


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    other_location = Location(name="Filiale", timezone="UTC")
    db_session.add_all([location, other_location])
    await db_session.commit()
    with_pin = Employee(location_id=location.id, first_name="Pia", last_name="Pin", employee_number="P1", pin_hash=hash_password("1234"))
    no_pin = Employee(location_id=location.id, first_name="Nils", last_name="Ohne", employee_number="P2")
    owner = Employee(location_id=location.id, first_name="Olga", last_name="Owner", employee_number="P3", nfc_uid="aabbccdd")
    elsewhere = Employee(location_id=other_location.id, first_name="Fritz", last_name="Fern", employee_number="P4", pin_hash=hash_password("1234"))
    device = Device(name="Tablet Eingang", location_id=location.id, token_hash=token_hash("tok-card-reg"))
    db_session.add_all([with_pin, no_pin, owner, elsewhere, device, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    token = (await client.post("/auth/device/login", json={"device_token": "tok-card-reg"})).json()["access_token"]
    admin = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    return with_pin, no_pin, elsewhere, {"Authorization": f"Bearer {token}"}, {"Authorization": f"Bearer {admin}"}


async def test_employee_registers_own_card_with_pin(client: AsyncClient, db_session: AsyncSession) -> None:
    with_pin, no_pin, elsewhere, device, admin = await _setup(db_session, client)
    url = "/device/register-card"

    r = await client.post(url, headers=device, json={"employee_id": with_pin.id, "pin": "9999", "nfc_uid": "04:A1:B2:C3"})
    assert r.status_code == 401 and r.json()["code"] == "PIN_INVALID"
    r = await client.post(url, headers=device, json={"employee_id": no_pin.id, "pin": "1234", "nfc_uid": "04a1b2c3"})
    assert r.status_code == 400 and r.json()["code"] == "PIN_NOT_CONFIGURED"
    r = await client.post(url, headers=device, json={"employee_id": elsewhere.id, "pin": "1234", "nfc_uid": "04a1b2c3"})
    assert r.status_code == 404  # anderer Standort
    r = await client.post(url, headers=device, json={"employee_id": with_pin.id, "pin": "1234", "nfc_uid": "AA:BB:CC:DD"})
    assert r.status_code == 409 and r.json()["code"] == "CARD_IN_USE"
    assert (await client.post(url, headers=device, json={"employee_id": with_pin.id, "pin": "1234", "nfc_uid": "x!"})).status_code == 422

    r = await client.post(url, headers=device, json={"employee_id": with_pin.id, "pin": "1234", "nfc_uid": "04:A1:B2:C3"})
    assert r.status_code == 204, r.text
    await db_session.refresh(with_pin)
    assert with_pin.nfc_uid == "04a1b2c3"
    entry = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.EMPLOYEE_CARD_REGISTERED))).scalar_one()
    assert entry.entity_id == with_pin.id and "Tablet Eingang" in entry.detail

    # Der neue Chip ersetzt den PIN beim Stempeln.
    r = await client.patch("/settings", headers=admin, json={"require_pin_for_punch": True})
    assert r.status_code == 200
    r = await client.post(
        "/punches",
        headers=device,
        json={"employee_id": with_pin.id, "punch_type": "COME", "timestamp_utc": "2026-08-10T08:00:00Z", "idempotency_key": "card-reg-1", "nfc_uid": "04A1B2C3"},
    )
    assert r.status_code == 201, r.text

    # Abschaltbar in den Einstellungen; nur für Tablets.
    await client.patch("/settings", headers=admin, json={"kiosk_card_self_registration": False})
    r = await client.post(url, headers=device, json={"employee_id": with_pin.id, "pin": "1234", "nfc_uid": "04a1b2c4"})
    assert r.status_code == 403 and r.json()["code"] == "CARD_SELF_REGISTRATION_DISABLED"
    assert (await client.post(url, headers=admin, json={"employee_id": with_pin.id, "pin": "1234", "nfc_uid": "04a1b2c4"})).status_code == 403
