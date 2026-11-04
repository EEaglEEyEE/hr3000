"""Dienstgang (zählt als Arbeitszeit) und Stempeln über den Web-Login (Standard aus)."""
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(
        location_id=location.id,
        first_name="Dora",
        last_name="Dienst",
        employee_number="D1",
        login_email="dora@example.com",
        password_hash=hash_password("pw123456"),
    )
    device = Device(name="Tablet", location_id=location.id, device_token="tok-errand")
    db_session.add_all([employee, device, HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    admin = {"Authorization": "Bearer " + (await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]}
    me = {"Authorization": "Bearer " + (await client.post("/auth/employee/login", json={"email": "dora@example.com", "password": "pw123456"})).json()["access_token"]}
    device_headers = {"Authorization": "Bearer " + (await client.post("/auth/device/login", json={"device_token": "tok-errand"})).json()["access_token"]}
    return employee, admin, me, device_headers


async def _punch(client, headers, employee_id, punch_type, ts) -> int:
    r = await client.post("/punches", headers=headers, json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())})
    return r.status_code


async def test_errand_counts_as_work_and_shows_status(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(datetime(2026, 8, 11, 10, 0))  # Schicht läuft noch (innerhalb der maximalen Schichtlänge)
    employee, admin, _, device = await _setup(db_session, client)
    # Standard aus: Dienstgang wird abgewiesen, bis der Mandant ihn einschaltet.
    assert (await client.post("/auth/device/login", json={"device_token": "tok-errand"})).json()["errand_buttons"] is False
    assert await _punch(client, device, employee.id, "COME", "2026-08-09T08:00:00Z") == 201
    assert await _punch(client, device, employee.id, "ERRAND_START", "2026-08-09T09:00:00Z") == 400
    await client.patch("/settings", headers=admin, json={"kiosk_errand_buttons": True})
    for punch_type, hour in (("COME", "08"), ("ERRAND_START", "10"), ("ERRAND_END", "12"), ("GO", "16")):
        assert await _punch(client, device, employee.id, punch_type, f"2026-08-10T{hour}:00:00Z") == 201
    day = (await client.get(f"/employees/{employee.id}/timesheet", headers=admin, params={"from": "2026-08-10", "to": "2026-08-10"})).json()[0]
    # 08–16 Uhr inkl. 2 Std. Dienstgang = volle 8 Std. (Test-Mandant ohne Pausenregeln)
    assert day["status"] == "COMPLETE" and day["actual_minutes"] == 8 * 60

    assert await _punch(client, device, employee.id, "COME", "2026-08-11T08:00:00Z") == 201
    assert await _punch(client, device, employee.id, "ERRAND_START", "2026-08-11T09:00:00Z") == 201
    day = (await client.get(f"/employees/{employee.id}/timesheet", headers=admin, params={"from": "2026-08-11", "to": "2026-08-11"})).json()[0]
    assert day["status"] == "ON_ERRAND"

    await client.patch("/settings", headers=admin, json={"kiosk_errand_buttons": False})
    assert await _punch(client, device, employee.id, "ERRAND_END", "2026-08-11T10:00:00Z") == 400
    login = (await client.post("/auth/device/login", json={"device_token": "tok-errand"})).json()
    assert login["errand_buttons"] is False


async def test_portal_punching_is_off_by_default_and_uses_server_time(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, me, _ = await _setup(db_session, client)
    r = await client.post("/me/punches", headers=me, json={"punch_type": "COME"})
    assert r.status_code == 403 and r.json()["code"] == "PORTAL_PUNCHING_DISABLED"
    assert (await client.get("/dashboard", headers=me)).json()["me"]["portal_punching"] is False

    await client.patch("/settings", headers=admin, json={"portal_punching_enabled": True})
    before = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=5)
    r = await client.post("/me/punches", headers=me, json={"punch_type": "COME", "timestamp_utc": "2020-01-01T00:00:00Z"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source"] == "PORTAL" and body["employee_id"] == employee.id
    assert datetime.fromisoformat(body["timestamp_utc"]).replace(tzinfo=None) >= before  # Serverzeit, nicht 2020
    assert (await client.post("/me/punches", headers=me, json={"punch_type": "COME"})).status_code == 409
    assert (await client.get("/dashboard", headers=me)).json()["me"]["portal_punching"] is True

    # Nur Mitarbeiter-Logins, nicht HR-Konten.
    assert (await client.post("/me/punches", headers=admin, json={"punch_type": "GO"})).status_code == 403
