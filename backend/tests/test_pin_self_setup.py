"""Mitarbeiter legt seinen PIN beim ersten Stempeln am Kiosk selbst fest; HR setzt ihn zurück."""
import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLogEntry, Device, Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def test_pin_self_setup_and_reset_by_hr(client: AsyncClient, db_session: AsyncSession) -> None:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Paula", last_name="Neu", employee_number="N1")
    device = Device(name="Tablet Halle", location_id=location.id, device_token="tok-pin-setup")
    db_session.add_all([employee, device, HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    admin = {"Authorization": "Bearer " + (await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]}
    await client.patch("/settings", headers=admin, json={"require_pin_for_punch": True})
    login = (await client.post("/auth/device/login", json={"device_token": "tok-pin-setup"})).json()
    assert login["pin_self_setup"] is True and login["require_pin"] is True
    device_headers = {"Authorization": f"Bearer {login['access_token']}"}

    assert (await client.post("/device/setup-pin", headers=device_headers, json={"employee_id": employee.id, "pin": "12"})).status_code == 422
    r = await client.post("/device/setup-pin", headers=device_headers, json={"employee_id": employee.id, "pin": "4711"})
    assert r.status_code == 204, r.text
    entry = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.EMPLOYEE_PIN_SET_AT_KIOSK))).scalar_one()
    assert "Tablet Halle" in entry.detail

    # Ein zweites Festlegen (z.B. durch Kollegen) ist nicht möglich.
    r = await client.post("/device/setup-pin", headers=device_headers, json={"employee_id": employee.id, "pin": "0000"})
    assert r.status_code == 409 and r.json()["code"] == "PIN_ALREADY_SET"

    punch = {"employee_id": employee.id, "punch_type": "COME", "timestamp_utc": datetime.now(UTC).isoformat()}
    r = await client.post("/punches", headers=device_headers, json={**punch, "idempotency_key": str(uuid.uuid4()), "pin": "4711"})
    assert r.status_code == 201, r.text

    # Vergessen: HR setzt zurück -> Festlegen am Tablet geht wieder.
    r = await client.patch(f"/employees/{employee.id}", headers=admin, json={"pin": ""})
    assert r.status_code == 200 and r.json()["has_pin"] is False
    assert (await client.post("/device/setup-pin", headers=device_headers, json={"employee_id": employee.id, "pin": "2580"})).status_code == 204

    # Abschaltbar: dann vergibt nur HR den PIN.
    await client.patch(f"/employees/{employee.id}", headers=admin, json={"pin": ""})
    await client.patch("/settings", headers=admin, json={"kiosk_pin_self_setup": False})
    r = await client.post("/device/setup-pin", headers=device_headers, json={"employee_id": employee.id, "pin": "2580"})
    assert r.status_code == 403 and r.json()["code"] == "PIN_SELF_SETUP_DISABLED"
    assert (await client.post("/device/setup-pin", headers=admin, json={"employee_id": employee.id, "pin": "2580"})).status_code == 403
