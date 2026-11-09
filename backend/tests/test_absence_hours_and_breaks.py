"""Abwesenheiten mit genauer Stundenzahl (Homeoffice 1 oder 3 Std., "Feiertag (GfB)", zusätzliche
Stunden) und Pausen im Monatsbericht."""
import csv
import io
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BreakRule, Employee, HrRole, Account, Location
from app.services.auth_service import hash_password
from app.services.period_service import build_month_report

MONDAY = "2026-10-05"
TUESDAY = "2026-10-06"
WEDNESDAY = "2026-10-07"


async def _setup(db_session: AsyncSession, client: AsyncClient, model: dict | None = None):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Hanna", last_name="Home", employee_number="H1")
    db_session.add_all([employee, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    if model is not False:
        r = await client.put(
            f"/employees/{employee.id}/work-time-model",
            headers=admin,
            json={"valid_from": "2026-10-01", **(model or {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4]})},
        )
        assert r.status_code == 200, r.text
    types = {}
    for name, category in (("Homeoffice", "SPECIAL_LEAVE"), ("Feiertag (GfB)", "SPECIAL_LEAVE"), ("Zusätzliche Stunden", "SPECIAL_LEAVE")):
        r = await client.post("/absence-types", headers=admin, json={"name": name, "category": category})
        assert r.status_code == 201, r.text
        types[name] = r.json()["id"]
    return employee, admin, types


async def _hours(client, admin, employee_id, day, type_id, minutes, **extra):
    return await client.post(
        "/absences",
        headers=admin,
        json={"employee_id": employee_id, "absence_type_id": type_id, "date_from": day, "date_to": extra.pop("day_to", day), "duration_minutes": minutes, **extra},
    )


async def _work(client, admin, employee_id, day, come, go):
    for punch_type, clock in (("COME", come), ("GO", go)):
        r = await client.post(
            "/punches",
            headers=admin,
            json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{day}T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text


async def _day(client, admin, employee_id, day):
    return (await client.get(f"/employees/{employee_id}/timesheet", headers=admin, params={"from": day, "to": day})).json()[0]


# --- Stundenangaben ------------------------------------------------------------------------


async def test_homeoffice_hours_without_office_work(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, types = await _setup(db_session, client)
    r = await _hours(client, admin, employee.id, MONDAY, types["Homeoffice"], 180)
    assert r.status_code == 201 and r.json()["duration_minutes"] == 180

    day = await _day(client, admin, employee.id, MONDAY)
    # Genau 3 Std. gutgeschrieben, der Rest des Solls belastet das Konto; HR hat den Tag erfasst -> nicht "zu klären".
    assert day["status"] == "ABSENCE" and day["actual_minutes"] == 180 and day["target_minutes"] == 480
    assert day["absence_label"] == "Homeoffice 3:00 Std."
    open_days = [d["work_date"] for d in (await client.get("/timesheet/open-days", headers=admin)).json()]
    assert MONDAY not in open_days


async def test_homeoffice_hour_plus_office_and_extra_hours(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, types = await _setup(db_session, client)
    assert (await _hours(client, admin, employee.id, MONDAY, types["Homeoffice"], 60)).status_code == 201
    assert (await _hours(client, admin, employee.id, MONDAY, types["Zusätzliche Stunden"], 90)).status_code == 201
    await _work(client, admin, employee.id, MONDAY, "09:00", "14:30")  # 5,5 Std. im Büro
    day = await _day(client, admin, employee.id, MONDAY)
    assert day["status"] == "COMPLETE"
    assert day["actual_minutes"] == 330 + 60 + 90
    assert day["absence_label"] == "Homeoffice 1:00 Std. + Zusätzliche Stunden 1:30 Std."
    assert "WORK_DURING_ABSENCE" not in day["flags"]


async def test_holiday_hours_for_part_timer_without_target(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, types = await _setup(db_session, client, model={"on_demand": True, "monthly_cap_hours": 43})
    r = await client.post("/holidays", headers=admin, json={"date": TUESDAY, "name": "Feiertag"})
    assert r.status_code == 201, r.text
    assert (await _day(client, admin, employee.id, TUESDAY))["actual_minutes"] in (0, None)
    assert (await _hours(client, admin, employee.id, TUESDAY, types["Feiertag (GfB)"], 150)).status_code == 201
    day = await _day(client, admin, employee.id, TUESDAY)
    assert day["status"] == "HOLIDAY" and day["actual_minutes"] == 150
    assert day["absence_label"] == "Feiertag (GfB) 2:30 Std."


async def test_unpaid_hours_lower_the_target(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    r = await client.post(
        "/absences",
        headers=admin,
        json={"employee_id": employee.id, "type": "UNPAID", "date_from": MONDAY, "date_to": MONDAY, "duration_minutes": 120},
    )
    assert r.status_code == 201, r.text
    await _work(client, admin, employee.id, MONDAY, "08:00", "14:00")
    day = await _day(client, admin, employee.id, MONDAY)
    assert day["target_minutes"] == 360 and day["actual_minutes"] == 360


async def test_hour_entries_validation_and_combinations(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, types = await _setup(db_session, client)
    home = types["Homeoffice"]
    # Pydantic: Bereich, mehrere Tage, zusammen mit halbem Tag
    for minutes in (0, -30, 961, "drei"):
        assert (await _hours(client, admin, employee.id, MONDAY, home, minutes)).status_code == 422, minutes
    assert (await _hours(client, admin, employee.id, MONDAY, home, 60, day_to=TUESDAY)).status_code == 422
    assert (await _hours(client, admin, employee.id, MONDAY, home, 60, half_day=True)).status_code == 422
    # Urlaub zählt in Tagen
    r = await client.post(
        "/absences",
        headers=admin,
        json={"employee_id": employee.id, "type": "VACATION", "date_from": MONDAY, "date_to": MONDAY, "duration_minutes": 120},
    )
    assert r.status_code == 400 and r.json()["code"] == "DURATION_NOT_FOR_VACATION"

    # Stunden + halber Tag gehen, Stunden neben ganzem Tag nicht (in beide Richtungen)
    assert (await _hours(client, admin, employee.id, MONDAY, home, 60)).status_code == 201
    r = await client.post(
        "/absences",
        headers=admin,
        json={"employee_id": employee.id, "type": "VACATION", "date_from": MONDAY, "date_to": MONDAY, "half_day": True},
    )
    assert r.status_code == 201
    full = await client.post(
        "/absences", headers=admin, json={"employee_id": employee.id, "type": "SICK", "date_from": "2026-10-02", "date_to": MONDAY}
    )
    assert full.status_code == 409
    await client.post("/absences", headers=admin, json={"employee_id": employee.id, "type": "SICK", "date_from": TUESDAY, "date_to": TUESDAY})
    on_full = await _hours(client, admin, employee.id, TUESDAY, home, 60)
    assert on_full.status_code == 409 and "ganztägige" in on_full.json()["detail"]


async def test_change_hours_or_back_to_full_day(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, types = await _setup(db_session, client)
    absence = (await _hours(client, admin, employee.id, MONDAY, types["Homeoffice"], 60)).json()
    r = await client.patch(f"/absences/{absence['id']}", headers=admin, json={"duration_minutes": 240})
    assert r.status_code == 200 and r.json()["duration_minutes"] == 240
    assert (await _day(client, admin, employee.id, MONDAY))["actual_minutes"] == 240
    r = await client.patch(f"/absences/{absence['id']}", headers=admin, json={"clear_duration": True})
    assert r.status_code == 200 and r.json()["duration_minutes"] is None
    assert (await _day(client, admin, employee.id, MONDAY))["actual_minutes"] == 480
    r = await client.patch(f"/absences/{absence['id']}", headers=admin, json={"duration_minutes": 60, "date_to": TUESDAY})
    assert r.status_code == 400 and r.json()["code"] == "HALF_DAY_SINGLE_DAY"


async def test_hours_in_payroll_calendar_dashboard_and_report(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, types = await _setup(db_session, client)
    await _hours(client, admin, employee.id, MONDAY, types["Homeoffice"], 180)
    r = await client.get("/payroll-export", headers=admin, params={"employee_ids": [employee.id], "from": MONDAY, "to": MONDAY})
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿")), delimiter=";"))
    values = dict(zip(rows[0], rows[1]))
    assert values[next(h for h in rows[0] if h.startswith("Sonderurlaub"))] == "0"  # keine Abwesenheitstage …
    assert values[next(h for h in rows[0] if h.startswith("Ist"))] == "3,00"  # … aber die Stunden

    cell = (await client.get("/team-calendar", headers=admin, params={"from": MONDAY, "to": MONDAY})).json()[0]["days"][0]
    assert cell["status"] == "ABSENCE" and cell["absence_label"] == "Homeoffice 3:00 Std." and cell["half_day"] is False

    report = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 10)
    monday = next(d for d in report.days if d.day == date(2026, 10, 5))
    assert monday.label == "Homeoffice 3:00 Std." and monday.actual_minutes == 180
    assert report.special_leave_days == 0


async def test_dashboard_title_with_hours(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, types = await _setup(db_session, client)
    await _hours(client, admin, employee.id, date.today().isoformat(), types["Homeoffice"], 90)
    titles = [e["title"] for e in (await client.get("/dashboard", headers=admin)).json()["events"] if e["kind"] == "ABSENCE"]
    assert titles == ["Homeoffice (1:30 Std.)"]


# --- Pausen im Monatsbericht ---------------------------------------------------------------


async def test_month_report_lists_breaks(client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(BreakRule(tenant_id=1, min_work_minutes=360, deduct_minutes=30))
    employee, admin, _ = await _setup(db_session, client)
    # Montag: gestempelte Pause 45 Min.
    await _work(client, admin, employee.id, MONDAY, "08:00", "12:00")
    for punch_type, clock in (("BREAK_START", "10:00"), ("BREAK_END", "10:45")):
        r = await client.post(
            "/punches", headers=admin,
            json={"employee_id": employee.id, "punch_type": punch_type, "timestamp_utc": f"{MONDAY}T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201
    # Dienstag: Unterbrechung 12–13 Uhr (Gehen/Kommen) = 60 Min.
    await _work(client, admin, employee.id, TUESDAY, "08:00", "12:00")
    await _work(client, admin, employee.id, TUESDAY, "13:00", "17:00")
    # Mittwoch: 7 Std. ohne Pause -> gesetzlich 30 Min. abgezogen
    await _work(client, admin, employee.id, WEDNESDAY, "08:00", "15:00")

    report = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 10)
    breaks = {d.day.isoformat(): d.break_minutes for d in report.days if d.day.isoformat() in (MONDAY, TUESDAY, WEDNESDAY)}
    assert breaks == {MONDAY: 45, TUESDAY: 60, WEDNESDAY: 30}
    assert report.break_minutes == 135
    wednesday = next(d for d in report.days if d.day == date(2026, 10, 7))
    assert wednesday.actual_minutes == 390  # Pause wird nicht doppelt abgezogen

    r = await client.get(f"/employees/{employee.id}/month-report", headers=admin, params={"year": 2026, "month": 10})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")
