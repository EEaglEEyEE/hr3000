"""Pausen aufgeräumt: eine Pausenstaffel (feste Minuten = Staffelzeile), Schutz der gesetzlichen
Mindestpause, genaue § 4-Rechnung und Abzug höchstens bis zur Schwelle (je ab Datum), eigene Pause
im Arbeitszeitmodell mit Schwelle, Pünktlichkeits-Hinweise erst ab der letzten Regeländerung."""
import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BreakRule, Employee, HrRole, HrUser, Location, Punch, PunchSource, PunchType
from app.services.auth_service import hash_password
from app.services.timesheet_service import pair_punches_detail

UTC = ZoneInfo("UTC")


async def _setup(db_session: AsyncSession, client: AsyncClient) -> tuple[Employee, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Bea", last_name="Break", employee_number="B1", auto_break_enabled=False)
    db_session.add_all(
        [
            employee,
            HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
            BreakRule(min_work_minutes=360, deduct_minutes=30),
            BreakRule(min_work_minutes=540, deduct_minutes=45),
        ]
    )
    await db_session.commit()
    await db_session.refresh(employee)
    login = await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})
    return employee, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _punches(db_session: AsyncSession, employee: Employee, day: date, *entries: tuple[str, str]) -> None:
    for kind, clock in entries:
        hour, minute = map(int, clock.split(":"))
        db_session.add(
            Punch(
                employee_id=employee.id, location_id=employee.location_id, punch_type=PunchType(kind),
                timestamp_utc=datetime.combine(day, time(hour, minute)), source=PunchSource.KIOSK, idempotency_key=str(uuid.uuid4()),
            )
        )
    await db_session.commit()


async def _actual(db_session: AsyncSession, employee: Employee, day: date) -> int | None:
    actual, _, _ = await pair_punches_detail(db_session, employee, day, UTC)
    return actual


async def test_precise_section4_from_date(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    before, after = date(2026, 10, 5), date(2026, 10, 6)
    for day in (before, after):
        # 6:20 anwesend, 20 Min. gestempelt -> Arbeitszeit 6:00 (nicht "mehr als 6 Std.")
        await _punches(db_session, employee, day, ("COME", "08:00"), ("BREAK_START", "11:00"), ("BREAK_END", "11:20"), ("GO", "14:20"))
    r = await client.patch("/settings", headers=admin, json={"break_precise_from": after.isoformat()})
    assert r.status_code == 200 and r.json()["break_precise_from"] == "2026-10-06"
    assert await _actual(db_session, employee, before) == 350  # bisher: Schwelle nach Anwesenheit -> 10 Min. Rest
    assert await _actual(db_session, employee, after) == 360  # genau: keine Pausenpflicht

    # Kurzpausen unter 15 Min. zählen genau gerechnet nicht zur Mindestpause
    day = date(2026, 10, 7)
    await _punches(
        db_session, employee, day, ("COME", "08:00"), ("BREAK_START", "10:00"), ("BREAK_END", "10:10"),
        ("BREAK_START", "12:00"), ("BREAK_END", "12:10"), ("GO", "15:00"),
    )
    assert await _actual(db_session, employee, day) == 370  # 420 − 20 gestempelt − 30 Mindestpause

    r = await client.patch("/settings", headers=admin, json={"clear_break_precise": True})
    assert r.json()["break_precise_from"] is None
    assert await _actual(db_session, employee, day) == 390  # wieder wie bisher: 20 zählen, 10 fehlen


async def test_capped_deduction(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    day = date(2026, 10, 6)
    await _punches(db_session, employee, day, ("COME", "08:00"), ("GO", "14:10"))
    assert await _actual(db_session, employee, day) == 340  # 6:10 − 30 Min.
    assert (await client.patch("/settings", headers=admin, json={"break_capped_from": "2026-10-01"})).status_code == 200
    assert await _actual(db_session, employee, day) == 360  # nie unter die Schwelle von 6 Std.


async def test_legal_minimum_protects_the_staffel(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    rules = {r["min_work_minutes"]: r for r in (await client.get("/break-rules", headers=admin)).json()}
    r = await client.delete(f"/break-rules/{rules[540]['id']}", headers=admin)
    assert r.status_code == 409 and r.json()["code"] == "STAFFEL_BELOW_LAW"
    r = await client.patch(f"/break-rules/{rules[360]['id']}", headers=admin, json={"deduct_minutes": 20})
    assert r.status_code == 409
    r = await client.patch(f"/break-rules/{rules[360]['id']}", headers=admin, json={"deduct_minutes": 40})
    assert r.status_code == 200  # strenger als das Gesetz geht immer
    # bewusst abschalten (Tarifvertrag), dann darf die Staffel sinken; wieder an nur, wenn sie passt
    assert (await client.patch("/settings", headers=admin, json={"legal_break_minimum": False})).status_code == 200
    assert (await client.delete(f"/break-rules/{rules[540]['id']}", headers=admin)).status_code == 204
    r = await client.patch("/settings", headers=admin, json={"legal_break_minimum": True})
    assert r.status_code == 409 and r.json()["code"] == "STAFFEL_BELOW_LAW"


async def test_model_break_minutes_from_threshold(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "break_minutes": 45, "break_after_hours": 6, "valid_from": "2026-10-01"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["break_after_minutes"] == 360
    assert r.json()["break_minutes"] == 45
    short, long = date(2026, 10, 5), date(2026, 10, 6)
    await _punches(db_session, employee, short, ("COME", "08:00"), ("GO", "12:00"))
    await _punches(db_session, employee, long, ("COME", "08:00"), ("GO", "16:00"))
    assert await _actual(db_session, employee, short) == 240  # unter 6 Std.: keine Pause
    assert await _actual(db_session, employee, long) == 435  # 45 Min. statt gesetzlich 30
    r = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "break_after_hours": 6, "valid_from": "2026-10-01"},
    )
    assert r.status_code == 422  # Schwelle nur mit Minuten


async def test_punctuality_hints_only_from_last_change(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin, json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"}
    )
    assert r.status_code == 200
    await _punches(db_session, employee, date(2026, 10, 5), ("COME", "10:00"), ("GO", "18:00"))
    r = await client.patch("/settings", headers=admin, json={"core_time_start": "09:00", "core_time_end": "15:00", "disabled_day_flags": []})
    assert r.status_code == 200 and r.json()["punctuality_from"] == date.today().isoformat()
    day = (await client.get(f"/employees/{employee.id}/timesheet", headers=admin, params={"from": "2026-10-05", "to": "2026-10-05"})).json()[0]
    assert "LATE_ARRIVAL" not in day["flags"]  # vor der Änderung: keine Flut alter Hinweise
