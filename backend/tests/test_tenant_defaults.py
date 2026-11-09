"""Mandanten-Standardwerte/Regeln und Kiosk-Admin-PIN."""
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, EmployeeDefaultShift, HrRole, Account, Location, ShiftTemplate
from app.services.auth_service import hash_password
from app.services.pairing_service import token_hash


async def _admin(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add_all([location, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    await db_session.refresh(location)
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    return location, {"Authorization": f"Bearer {token}"}


async def test_defaults_apply_to_new_employees(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    r = await client.patch("/settings", headers=headers, json={
        "default_auto_break": False, "default_show_birthday": False, "default_day_minutes": [240, 240, 240, 0, 0, 0, 0],
    })
    assert r.status_code == 200 and r.json()["default_day_minutes"] == [240, 240, 240, 0, 0, 0, 0]
    features = (await client.get("/features", headers=headers)).json()
    assert features["default_auto_break"] is False and features["default_day_minutes"][0] == 240

    created = (await client.post("/employees", headers=headers, json={"location_id": location.id, "first_name": "A", "last_name": "B", "employee_number": "1"})).json()
    assert created["auto_break_enabled"] is False and created["show_birthday_in_calendar"] is False
    model = (await client.get(f"/employees/{created['id']}/work-time-model", headers=headers)).json()
    assert model["day_minutes"] == [240, 240, 240, 0, 0, 0, 0]

    # Explizite Angabe gewinnt gegen den Standard.
    explicit = (await client.post("/employees", headers=headers, json={"location_id": location.id, "first_name": "C", "last_name": "D", "employee_number": "2", "auto_break_enabled": True})).json()
    assert explicit["auto_break_enabled"] is True

    # Bewusst ohne Arbeitszeitmodell (z. B. reines HR-Konto): Standard greift nicht.
    none = (await client.post("/employees", headers=headers, json={"location_id": location.id, "first_name": "E", "last_name": "F", "employee_number": "3", "no_work_time_model": True})).json()
    assert (await client.get(f"/employees/{none['id']}/work-time-model", headers=headers)).json()["configured"] is False
    # Nach Aufwand statt Standard
    helper = (await client.post("/employees", headers=headers, json={"location_id": location.id, "first_name": "G", "last_name": "H", "employee_number": "4", "work_time_model": {"on_demand": True}})).json()
    assert (await client.get(f"/employees/{helper['id']}/work-time-model", headers=headers)).json()["on_demand"] is True
    # Beides zugleich ist widersprüchlich.
    both = await client.post("/employees", headers=headers, json={"location_id": location.id, "first_name": "I", "last_name": "J", "employee_number": "5", "no_work_time_model": True, "work_time_model": {"on_demand": True}})
    assert both.status_code == 422

    assert (await client.patch("/settings", headers=headers, json={"default_day_minutes": [700, 0, 0, 0, 0, 0, 0]})).status_code == 400
    assert (await client.patch("/settings", headers=headers, json={"default_day_minutes": []})).json()["default_day_minutes"] is None


async def test_disabled_flag_and_shift_span(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    employee = Employee(location_id=location.id, first_name="E", last_name="F", employee_number="3")
    template = ShiftTemplate(name="N", target_minutes=480)
    db_session.add_all([employee, template])
    await db_session.commit()
    db_session.add(EmployeeDefaultShift(employee_id=employee.id, shift_template_id=template.id, valid_from=date(2025, 1, 1), weekdays_mask=0b0011111))
    await db_session.commit()
    for t, ts in (("COME", "2025-03-08T08:00:00Z"), ("GO", "2025-03-08T12:00:00Z")):
        await client.post("/punches", headers=headers, json={"employee_id": employee.id, "punch_type": t, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())})

    def day(r):
        return r.json()[0]

    params = {"from": "2025-03-08", "to": "2025-03-08"}
    assert day(await client.get(f"/employees/{employee.id}/timesheet", headers=headers, params=params))["flags"] == ["UNPLANNED_WORK"]
    await client.patch("/settings", headers=headers, json={"disabled_day_flags": ["UNPLANNED_WORK"]})
    assert day(await client.get(f"/employees/{employee.id}/timesheet", headers=headers, params=params))["flags"] == []
    assert (await client.patch("/settings", headers=headers, json={"disabled_day_flags": ["NOPE"]})).status_code == 400
    assert (await client.patch("/settings", headers=headers, json={"max_shift_span_hours": 30})).status_code == 422


async def test_kiosk_admin_pin(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    db_session.add(Device(location_id=location.id, name="Tablet", token_hash=token_hash("dev-token")))
    await db_session.commit()
    device = {"Authorization": "Bearer " + (await client.post("/auth/device/login", json={"device_token": "dev-token"})).json()["access_token"]}

    not_set = await client.post("/devices/verify-admin-pin", headers=device, json={"pin": "1234"})
    assert not_set.status_code == 409 and not_set.json()["code"] == "ADMIN_PIN_NOT_SET"
    assert (await client.patch("/settings", headers=headers, json={"kiosk_admin_pin": "12ab"})).status_code == 422
    settings = (await client.patch("/settings", headers=headers, json={"kiosk_admin_pin": "4711"})).json()
    assert settings["kiosk_admin_pin_set"] is True

    assert (await client.post("/devices/verify-admin-pin", headers=device, json={"pin": "0000"})).status_code == 401
    assert (await client.post("/devices/verify-admin-pin", headers=device, json={"pin": "4711"})).status_code == 204
    assert (await client.post("/devices/verify-admin-pin", headers=headers, json={"pin": "4711"})).status_code == 403  # kein Gerät
    for _ in range(5):
        await client.post("/devices/verify-admin-pin", headers=device, json={"pin": "0000"})
    locked = await client.post("/devices/verify-admin-pin", headers=device, json={"pin": "4711"})
    assert locked.status_code == 429


async def test_rfid_required_and_uid_normalization(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    db_session.add(Device(location_id=location.id, name="Tablet", token_hash=token_hash("dev-token")))
    await db_session.commit()
    created = (await client.post("/employees", headers=headers, json={"location_id": location.id, "first_name": "R", "last_name": "F", "employee_number": "9", "nfc_uid": "04:A2:3B:4C"})).json()
    assert created["nfc_uid"] == "04a23b4c"
    await client.patch("/settings", headers=headers, json={"rfid_required": True})
    login = (await client.post("/auth/device/login", json={"device_token": "dev-token"})).json()
    assert login["rfid_required"] is True
    device = {"Authorization": f"Bearer {login['access_token']}"}

    def body(**extra):
        return {"employee_id": created["id"], "punch_type": "COME", "timestamp_utc": "2025-03-04T08:00:00Z", "idempotency_key": str(uuid.uuid4()), **extra}

    without = await client.post("/punches", headers=device, json=body())
    assert without.status_code == 400 and without.json()["code"] == "RFID_REQUIRED"
    wrong = await client.post("/punches", headers=device, json=body(nfc_uid="deadbeef"))
    assert wrong.status_code == 400
    # USB-Leser liefert Großbuchstaben ohne Trennzeichen – passt trotzdem.
    assert (await client.post("/punches", headers=device, json=body(nfc_uid="04A23B4C"))).status_code == 201
