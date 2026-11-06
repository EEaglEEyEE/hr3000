"""Kernzeit je Wochentag: in den Einstellungen und als eigene Kernzeit im Arbeitszeitmodell, z.B. freitags
kürzer oder an einzelnen Tagen ohne Kernzeit. Wirkt nur auf die Hinweise "zu spät"/"zu früh"."""
import uuid
from datetime import date

import pytest

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password

@pytest.fixture(autouse=True)
def _rules_changed_before_test_days(monkeypatch):
    """Pünktlichkeits-Hinweise gelten erst ab der letzten Regeländerung ("heute") – die Testtage
    liegen im Oktober 2026, also gilt "heute" hier als 01.10.2026."""
    import app.api.settings as settings_api

    class _Date(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 1)

    monkeypatch.setattr(settings_api, "date", _Date)


FIVE_DAYS = {"start": "09:00", "end": "15:00"}
FRIDAY_SHORT = [FIVE_DAYS, FIVE_DAYS, FIVE_DAYS, FIVE_DAYS, {"start": "09:00", "end": "12:00"}, None, None]


async def _setup(db_session: AsyncSession, client: AsyncClient) -> tuple[Employee, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Kai", last_name="Kern", employee_number="K1", auto_break_enabled=False)
    db_session.add_all([employee, HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    await db_session.refresh(employee)
    login = await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})
    admin = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"weekly_hours": 30, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"},
    )
    assert r.status_code == 200, r.text
    return employee, admin


async def _work(client: AsyncClient, admin: dict, employee: Employee, day: str, come: str, go: str) -> None:
    for punch_type, clock in (("COME", come), ("GO", go)):
        r = await client.post(
            "/punches",
            headers=admin,
            json={
                "employee_id": employee.id,
                "punch_type": punch_type,
                "timestamp_utc": f"{day}T{clock}:00Z",
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 201, r.text


async def _flags(client: AsyncClient, admin: dict, employee: Employee) -> dict[str, list[str]]:
    r = await client.get(f"/employees/{employee.id}/timesheet", headers=admin, params={"from": "2026-10-05", "to": "2026-10-11"})
    assert r.status_code == 200, r.text
    return {d["work_date"]: d["flags"] for d in r.json()}


async def test_tenant_core_time_per_weekday(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.patch(
        "/settings",
        headers=admin,
        json={"core_time_start": "09:00", "core_time_end": "15:00", "disabled_day_flags": [], "late_tolerance_minutes": 0, "core_time_days": FRIDAY_SHORT},
    )
    assert r.status_code == 200, r.text
    days = r.json()["core_time_days"]
    assert days[4] == {"start": "09:00:00", "end": "12:00:00"} and days[5] is None

    await _work(client, admin, employee, "2026-10-08", "09:00", "12:30")  # Do: Kernzeit bis 15:00
    await _work(client, admin, employee, "2026-10-09", "09:00", "12:30")  # Fr: Kernzeit bis 12:00
    await _work(client, admin, employee, "2026-10-05", "09:30", "16:00")  # Mo: zu spät
    flags = await _flags(client, admin, employee)
    assert "EARLY_LEAVE" in flags["2026-10-08"]
    assert "EARLY_LEAVE" not in flags["2026-10-09"]
    assert "LATE_ARRIVAL" in flags["2026-10-05"]

    # wieder jeden Tag gleich: Freitag ist jetzt auch "zu früh"
    r = await client.patch("/settings", headers=admin, json={"core_time_days": None})
    assert r.status_code == 200 and r.json()["core_time_days"] is None
    assert r.json()["core_time_start"] == "09:00:00"
    assert "EARLY_LEAVE" in (await _flags(client, admin, employee))["2026-10-09"]

    # andere Änderungen lassen die Tageszeiten in Ruhe
    await client.patch("/settings", headers=admin, json={"core_time_days": FRIDAY_SHORT})
    r = await client.patch("/settings", headers=admin, json={"late_tolerance_minutes": 5})
    assert r.json()["core_time_days"] is not None
    # "Keine Kernzeit" entfernt auch die Tageszeiten
    r = await client.patch("/settings", headers=admin, json={"clear_core_time": True})
    assert r.json()["core_time_days"] is None and r.json()["core_time_start"] is None


async def test_core_time_days_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    for days in (
        FRIDAY_SHORT[:6],
        [{"start": "15:00", "end": "09:00"}, *FRIDAY_SHORT[1:]],
        [{"start": "09:00"}, *FRIDAY_SHORT[1:]],
    ):
        r = await client.patch("/settings", headers=admin, json={"core_time_days": days})
        assert r.status_code == 422, days
    r = await client.patch("/settings", headers=admin, json={"flex_frame_start": "07:00", "flex_frame_end": "13:00"})
    assert r.status_code == 200
    r = await client.patch("/settings", headers=admin, json={"core_time_days": FRIDAY_SHORT})
    assert r.status_code == 400 and r.json()["code"] == "CORE_TIME_OUTSIDE_FRAME"
    ok = [{"start": "08:00", "end": "12:00"}, None, None, None, None, None, None]
    assert (await client.patch("/settings", headers=admin, json={"core_time_days": ok})).status_code == 200
    # Rahmen nachträglich enger als eine Tageskernzeit: abgelehnt
    r = await client.patch("/settings", headers=admin, json={"flex_frame_start": "09:00", "flex_frame_end": "13:00"})
    assert r.status_code == 400 and r.json()["code"] == "CORE_TIME_OUTSIDE_FRAME"


async def test_employee_custom_core_time_per_weekday(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await client.patch(
        "/settings", headers=admin, json={"core_time_start": "08:00", "core_time_end": "16:00", "disabled_day_flags": [], "late_tolerance_minutes": 0}
    )
    own = [FIVE_DAYS, None, FIVE_DAYS, FIVE_DAYS, FIVE_DAYS, None, None]  # dienstags keine Kernzeit
    url = f"/employees/{employee.id}/work-time-model"
    model = {"weekly_hours": 30, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"}
    r = await client.put(url, headers=admin, json={**model, "core_time_mode": "CUSTOM", "core_time_days": own})
    assert r.status_code == 200, r.text
    assert r.json()["core_time_days"][1] is None and r.json()["core_time_days"][0] == {"start": "09:00:00", "end": "15:00:00"}

    await _work(client, admin, employee, "2026-10-05", "09:00", "15:00")  # Mo: passt zur eigenen Kernzeit
    await _work(client, admin, employee, "2026-10-06", "11:00", "14:00")  # Di: keine Kernzeit
    await _work(client, admin, employee, "2026-10-07", "10:00", "15:00")  # Mi: zu spät
    flags = await _flags(client, admin, employee)
    assert flags["2026-10-05"] == [] and flags["2026-10-06"] == []
    assert "LATE_ARRIVAL" in flags["2026-10-07"]

    # neue Fassung ohne Angabe: Kernzeit bleibt wie bisher
    r = await client.put(url, headers=admin, json={**model, "weekly_hours": 32, "valid_from": "2026-11-01"})
    assert r.json()["core_time_mode"] == "CUSTOM" and r.json()["core_time_days"][1] is None
    # zurück auf "Wie in den Einstellungen": Tageszeiten weg
    r = await client.put(url, headers=admin, json={**model, "core_time_mode": "TENANT"})
    assert r.json()["core_time_days"] is None
    # eigene Kernzeit ohne Zeiten und ohne Tage: abgelehnt
    r = await client.put(url, headers=admin, json={**model, "core_time_mode": "CUSTOM"})
    assert r.status_code == 422
