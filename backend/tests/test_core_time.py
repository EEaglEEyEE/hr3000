"""Kernarbeitszeit, Gleitzeit-Rahmen und Pünktlichkeit: zu spät/zu früh/außerhalb des Rahmens
erscheint unter "Zu klären" – standardmäßig aus, je Mandant und je Mitarbeiter einstellbar,
ohne die Stunden zu verändern."""
import uuid
from datetime import date, time

import pytest

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location, ShiftPlanEntry, ShiftTemplate
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings

MONDAY = "2026-10-05"
TUESDAY = "2026-10-06"
CORE = {"core_time_start": "09:00", "core_time_end": "15:00", "disabled_day_flags": [], "late_tolerance_minutes": 5}


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


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Paula", last_name="Pünktlich", employee_number="P1")
    db_session.add_all([employee, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"},
    )
    assert r.status_code == 200, r.text
    return employee, admin


async def _settings(client: AsyncClient, admin, **values) -> None:
    r = await client.patch("/settings", headers=admin, json=values)
    assert r.status_code == 200, r.text


async def _work(client: AsyncClient, admin, employee_id: int, day: str, come: str, go: str | None) -> None:
    for punch_type, clock in (("COME", come), ("GO", go)):
        if clock is None:
            continue
        r = await client.post(
            "/punches",
            headers=admin,
            json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{day}T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text


async def _day(client: AsyncClient, admin, employee_id: int, day: str) -> dict:
    return (await client.get(f"/employees/{employee_id}/timesheet", headers=admin, params={"from": day, "to": day})).json()[0]


async def _open(client: AsyncClient, admin, day: str) -> list[str]:
    for row in (await client.get("/timesheet/open-days", headers=admin)).json():
        if row["work_date"] == day:
            return row["flags"]
    return []


async def test_off_by_default(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _work(client, admin, employee.id, MONDAY, "10:30", "16:00")
    day = await _day(client, admin, employee.id, MONDAY)
    assert day["flags"] == [] and day["status"] == "COMPLETE"


async def test_late_and_early_against_core_time_with_tolerance(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _settings(client, admin, **CORE)
    await _work(client, admin, employee.id, MONDAY, "09:05", "15:00")  # genau an der Toleranzgrenze
    await _work(client, admin, employee.id, TUESDAY, "09:06", "14:54")  # 6 Min. zu spät, 6 Min. zu früh
    assert (await _day(client, admin, employee.id, MONDAY))["flags"] == []
    tuesday = await _day(client, admin, employee.id, TUESDAY)
    assert set(tuesday["flags"]) == {"LATE_ARRIVAL", "EARLY_LEAVE"}
    # Die Stunden bleiben, wie gestempelt (keine Kürzung/Rundung).
    assert tuesday["actual_minutes"] == 5 * 60 + 48
    assert set(await _open(client, admin, TUESDAY)) == {"LATE_ARRIVAL", "EARLY_LEAVE"}

    # Erledigt -> verschwindet; Toleranz 0 -> Montag bleibt trotzdem unauffällig (09:05 > 09:00 ist dann spät)
    await client.put(f"/employees/{employee.id}/day-reviews/{TUESDAY}", headers=admin)
    assert await _open(client, admin, TUESDAY) == []
    await _settings(client, admin, late_tolerance_minutes=0)
    assert await _open(client, admin, MONDAY) == ["LATE_ARRIVAL"]


async def test_switching_the_check_off_clears_the_list(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _settings(client, admin, **CORE)
    await _work(client, admin, employee.id, MONDAY, "09:30", "17:00")
    assert await _open(client, admin, MONDAY) == ["LATE_ARRIVAL"]
    await _settings(client, admin, disabled_day_flags=["EARLY_LEAVE", "LATE_ARRIVAL"])
    assert await _open(client, admin, MONDAY) == []
    await _settings(client, admin, disabled_day_flags=[], clear_core_time=True)
    assert await _open(client, admin, MONDAY) == []  # ohne Kernzeit und ohne Schicht kein Maßstab


async def test_single_flags_can_be_disabled(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _settings(client, admin, **CORE)
    await _work(client, admin, employee.id, MONDAY, "09:30", "14:00")
    await _settings(client, admin, disabled_day_flags=["EARLY_LEAVE"])
    assert await _open(client, admin, MONDAY) == ["LATE_ARRIVAL"]


MODEL = {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"}


async def test_employee_own_core_time_or_exempt(client: AsyncClient, db_session: AsyncSession) -> None:
    """Kernzeit gehört zur Fassung der Arbeitszeit (wie Einstellungen / eigene / keine Prüfung)."""
    employee, admin = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"
    await _settings(client, admin, **CORE)
    await _work(client, admin, employee.id, MONDAY, "09:30", "16:00")
    assert await _open(client, admin, MONDAY) == ["LATE_ARRIVAL"]

    r = await client.put(url, headers=admin, json={**MODEL, "core_time_mode": "CUSTOM", "core_time_start": "10:00", "core_time_end": "14:00"})
    assert r.status_code == 200 and r.json()["core_time_mode"] == "CUSTOM" and r.json()["core_time_start"] == "10:00:00"
    assert await _open(client, admin, MONDAY) == []

    await client.put(url, headers=admin, json={**MODEL, "core_time_mode": "NONE"})
    await _work(client, admin, employee.id, TUESDAY, "11:00", "12:00")
    assert await _open(client, admin, TUESDAY) == []
    r = await client.put(url, headers=admin, json={**MODEL, "core_time_mode": "TENANT"})
    assert r.json()["core_time_start"] is None and r.json()["core_time_mode"] == "TENANT"
    assert set(await _open(client, admin, TUESDAY)) == {"LATE_ARRIVAL", "EARLY_LEAVE"}


async def test_flex_frame(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _settings(client, admin, flex_frame_start="06:00", flex_frame_end="20:00")
    await _work(client, admin, employee.id, MONDAY, "05:30", "13:30")
    await _work(client, admin, employee.id, TUESDAY, "12:00", "20:30")
    assert await _open(client, admin, MONDAY) == ["OUTSIDE_FLEX_FRAME"]
    assert await _open(client, admin, TUESDAY) == ["OUTSIDE_FLEX_FRAME"]
    await _settings(client, admin, clear_flex_frame=True)
    assert await _open(client, admin, MONDAY) == []


async def test_shift_times_take_precedence_over_core_time(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _settings(client, admin, **CORE, shift_planning_enabled=True)
    late_shift = ShiftTemplate(name="Spät", start_time=time(13, 0), end_time=time(21, 0), target_minutes=480)
    night = ShiftTemplate(name="Nacht", start_time=time(22, 0), end_time=time(6, 0), target_minutes=480)
    db_session.add_all([late_shift, night])
    await db_session.commit()
    db_session.add_all(
        [
            ShiftPlanEntry(employee_id=employee.id, date=date(2026, 10, 5), is_workday=True, shift_template_id=late_shift.id, target_minutes=480),
            ShiftPlanEntry(employee_id=employee.id, date=date(2026, 10, 6), is_workday=True, shift_template_id=night.id, target_minutes=480),
            ShiftPlanEntry(employee_id=employee.id, date=date(2026, 10, 7), is_workday=True, shift_template_id=late_shift.id, target_minutes=480),
        ]
    )
    await db_session.commit()
    await _settings(client, admin, late_tolerance_minutes=5)  # Cache neu aufbauen

    # Spätschicht 13–21 Uhr: um 13:00 gekommen ist pünktlich, obwohl die Kernzeit um 09:00 beginnt
    await _work(client, admin, employee.id, "2026-10-07", "13:00", "21:00")
    assert await _open(client, admin, "2026-10-07") == []

    await _work(client, admin, employee.id, MONDAY, "13:20", "21:00")  # laut Kernzeit "zu spät", laut Schicht 20 Min.
    assert await _open(client, admin, MONDAY) == ["LATE_ARRIVAL"]
    monday = await _day(client, admin, employee.id, MONDAY)
    assert monday["target_minutes"] == 480
    await client.put(f"/employees/{employee.id}/day-reviews/{MONDAY}", headers=admin)
    # Pünktlich zur Spätschicht – obwohl nach Kernzeitbeginn
    await _work(client, admin, employee.id, "2026-10-08", "09:30", "16:00")  # ohne Schicht: Kernzeit gilt
    assert await _open(client, admin, "2026-10-08") == ["LATE_ARRIVAL"]


async def test_night_shift_early_leave(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _settings(client, admin, disabled_day_flags=[], shift_planning_enabled=True)
    night = ShiftTemplate(name="Nacht", start_time=time(22, 0), end_time=time(6, 0), target_minutes=480)
    db_session.add(night)
    await db_session.commit()
    db_session.add(ShiftPlanEntry(employee_id=employee.id, date=date(2026, 10, 6), is_workday=True, shift_template_id=night.id, target_minutes=480))
    await db_session.commit()
    await _settings(client, admin, late_tolerance_minutes=10)
    r = await client.post(
        "/punches", headers=admin,
        json={"employee_id": employee.id, "punch_type": "COME", "timestamp_utc": "2026-10-06T22:00:00Z", "idempotency_key": str(uuid.uuid4())},
    )
    assert r.status_code == 201
    r = await client.post(
        "/punches", headers=admin,
        json={"employee_id": employee.id, "punch_type": "GO", "timestamp_utc": "2026-10-07T05:30:00Z", "idempotency_key": str(uuid.uuid4())},
    )
    assert r.status_code == 201
    day = await _day(client, admin, employee.id, TUESDAY)
    assert day["status"] == "COMPLETE" and day["flags"] == ["EARLY_LEAVE"]


async def test_no_punctuality_flags_on_absence_or_holiday(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _settings(client, admin, **CORE)
    # Halber Urlaubstag am Vormittag, Arbeit ab 13 Uhr: nicht "zu spät"
    r = await client.post(
        "/absences", headers=admin,
        json={"employee_id": employee.id, "type": "VACATION", "date_from": MONDAY, "date_to": MONDAY, "half_day": True},
    )
    assert r.status_code == 201
    await _work(client, admin, employee.id, MONDAY, "13:00", "17:00")
    assert (await _day(client, admin, employee.id, MONDAY))["flags"] == []
    # Feiertagsarbeit meldet nur "Feiertagsarbeit"
    await client.post("/holidays", headers=admin, json={"date": TUESDAY, "name": "Feiertag"})
    await _work(client, admin, employee.id, TUESDAY, "11:00", "12:00")
    assert (await _day(client, admin, employee.id, TUESDAY))["flags"] == ["HOLIDAY_WORK"]


async def test_input_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    for body in (
        {"core_time_start": "09:00"},  # Ende fehlt
        {"core_time_start": "15:00", "core_time_end": "09:00"},  # Beginn nach Ende
        {"core_time_start": "kaputt", "core_time_end": "15:00"},
        {"late_tolerance_minutes": -1},
        {"late_tolerance_minutes": 500},
        {"flex_frame_start": "08:00", "flex_frame_end": "18:00", "core_time_start": "07:00", "core_time_end": "15:00"},
        {"legal_break_minimum": "ja bitte"},
    ):
        assert (await client.patch("/settings", headers=admin, json=body)).status_code == 422, body
    # Kernzeit außerhalb eines bereits gespeicherten Rahmens
    await _settings(client, admin, flex_frame_start="08:00", flex_frame_end="18:00")
    r = await client.patch("/settings", headers=admin, json={"core_time_start": "07:00", "core_time_end": "12:00"})
    assert r.status_code == 400 and r.json()["code"] == "CORE_TIME_OUTSIDE_FRAME"

    for body in (
        {"core_time_mode": "CUSTOM"},
        {"core_time_mode": "CUSTOM", "core_time_start": "12:00", "core_time_end": "10:00"},
        {"core_time_mode": "IRGENDWIE"},
    ):
        r = await client.put(f"/employees/{employee.id}/work-time-model", headers=admin, json={**MODEL, **body})
        assert r.status_code == 422, body

    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await db_session.refresh(settings_row)
    assert settings_row.core_time_start is None and "LATE_ARRIVAL" in (settings_row.disabled_day_flags or "")
