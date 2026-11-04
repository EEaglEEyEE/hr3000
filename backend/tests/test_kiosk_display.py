"""Kiosk-Anzeige: Saldo/Resturlaub ausblendbar, Pausen-Buttons abschaltbar, Konfiguration abrufbar."""
import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Kai", last_name="Kiosk", employee_number="K1")
    device = Device(name="Tablet", location_id=location.id, device_token="tok-kiosk-display")
    db_session.add_all([employee, device, HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    await db_session.refresh(employee)
    admin = (await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    return employee, {"Authorization": f"Bearer {admin}"}


async def _device_headers(client: AsyncClient) -> tuple[dict, dict]:
    body = (await client.post("/auth/device/login", json={"device_token": "tok-kiosk-display"})).json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


async def test_kiosk_display_settings_are_enforced(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    login, device = await _device_headers(client)
    assert login["show_balance"] is True and login["break_buttons"] is True and login["sort"] == "LAST_NAME"
    assert (await client.get(f"/employees/{employee.id}/overtime-balance", headers=device)).status_code == 200

    r = await client.patch(
        "/settings",
        headers=admin,
        json={
            "kiosk_show_balance": False,
            "kiosk_show_vacation": False,
            "kiosk_break_buttons": False,
            "kiosk_greeting": "  Guten Morgen!  ",
            "kiosk_sort": "FIRST_NAME",
        },
    )
    assert r.status_code == 200, r.text
    assert (await client.patch("/settings", headers=admin, json={"kiosk_sort": "AGE"})).status_code == 422

    config = (await client.get("/device/config", headers=device)).json()
    assert config == {
        "require_pin": False,
        "rfid_required": False,
        "rfid_enabled": True,
        "card_self_registration": True,
        "pin_self_setup": True,
        "show_balance": False,
        "show_vacation": False,
        "break_buttons": False,
        "errand_buttons": False,
        "greeting": "Guten Morgen!",
        "sort": "FIRST_NAME",
        "theme": "DARK",
        "screen_on_from": None,
        "screen_on_until": None,
        "timezone": "UTC",
    }
    assert (await client.get("/device/config", headers=admin)).status_code == 403

    balance = await client.get(f"/employees/{employee.id}/overtime-balance", headers=device)
    assert balance.status_code == 403 and balance.json()["code"] == "KIOSK_BALANCE_HIDDEN"
    leave = await client.get(f"/employees/{employee.id}/leave-entitlement", headers=device, params={"year": 2025})
    assert leave.status_code == 403 and leave.json()["code"] == "KIOSK_VACATION_HIDDEN"
    # HR sieht beides weiterhin.
    assert (await client.get(f"/employees/{employee.id}/overtime-balance", headers=admin)).status_code == 200

    now = datetime.now(UTC).isoformat()
    come = await client.post("/punches", headers=device, json={"employee_id": employee.id, "punch_type": "COME", "timestamp_utc": now, "idempotency_key": str(uuid.uuid4())})
    assert come.status_code == 201, come.text
    pause = await client.post("/punches", headers=device, json={"employee_id": employee.id, "punch_type": "BREAK_START", "timestamp_utc": now, "idempotency_key": str(uuid.uuid4())})
    assert pause.status_code == 400 and pause.json()["code"] == "PUNCH_TYPE_DISABLED"


async def test_rfid_can_be_switched_off(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    employee.nfc_uid = "04a1b2c3"
    await db_session.commit()
    assert (await client.patch("/settings", headers=admin, json={"rfid_required": True, "require_pin_for_punch": True})).status_code == 200

    # Ausschalten nimmt die RFID-Pflicht mit; Pflicht ohne Chip-Funktion ist nicht möglich.
    body = (await client.patch("/settings", headers=admin, json={"kiosk_rfid_enabled": False})).json()
    assert body["kiosk_rfid_enabled"] is False and body["rfid_required"] is False
    r = await client.patch("/settings", headers=admin, json={"rfid_required": True})
    assert r.status_code == 400 and r.json()["code"] == "RFID_DISABLED"

    _, device = await _device_headers(client)
    assert (await client.get("/device/config", headers=device)).json()["rfid_enabled"] is False
    # Ein Chip ersetzt den PIN dann nicht mehr.
    now = datetime.now(UTC).isoformat()
    r = await client.post(
        "/punches",
        headers=device,
        json={"employee_id": employee.id, "punch_type": "COME", "timestamp_utc": now, "idempotency_key": str(uuid.uuid4()), "nfc_uid": "04a1b2c3"},
    )
    assert r.status_code == 400 and r.json()["code"] == "PIN_NOT_CONFIGURED"


async def test_kiosk_config_resolves_screen_hours_and_timezone(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    location = (await client.get("/locations", headers=admin)).json()[0]
    await client.patch(f"/locations/{location['id']}", headers=admin, json={"timezone": "Europe/Berlin"})
    login, device = await _device_headers(client)
    assert (login["screen_on_from"], login["screen_on_until"]) == (None, None)  # Standard: immer an
    assert login["timezone"] == "Europe/Berlin"

    await client.patch("/settings", headers=admin, json={"kiosk_screen_on_from": "06:00", "kiosk_screen_on_until": "21:00"})
    config = (await client.get("/device/config", headers=device)).json()
    assert (config["screen_on_from"], config["screen_on_until"], config["timezone"]) == ("06:00", "21:00", "Europe/Berlin")

    device_id = (await client.get("/devices", headers=admin)).json()[0]["id"]
    await client.patch(f"/devices/{device_id}", headers=admin, json={"screen_hours_mode": "ALWAYS"})
    config = (await client.get("/device/config", headers=device)).json()
    assert (config["screen_on_from"], config["screen_on_until"]) == (None, None)  # Gerät "immer an" schlägt Mandant

    await client.patch(f"/devices/{device_id}", headers=admin, json={"screen_hours_mode": "CUSTOM", "screen_on_from": "22:00", "screen_on_until": "06:00"})
    config = (await client.get("/device/config", headers=device)).json()
    assert (config["screen_on_from"], config["screen_on_until"]) == ("22:00", "06:00")

    await client.patch(f"/devices/{device_id}", headers=admin, json={"screen_hours_mode": "DEFAULT"})
    await client.patch("/settings", headers=admin, json={"clear_kiosk_screen_hours": True})
    config = (await client.get("/device/config", headers=device)).json()
    assert (config["screen_on_from"], config["screen_on_until"]) == (None, None)
