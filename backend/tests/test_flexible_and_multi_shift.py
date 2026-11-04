"""Aushilfen ohne feste Tage (Wochensoll), mehrere Kommen/Gehen pro Tag, Auswertungen nur bis heute."""
import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BreakRule, Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient, **employee_kwargs):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Anna", last_name="Aushilfe", employee_number="A1", auto_break_enabled=False, **employee_kwargs)
    db_session.add_all([employee, HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)])
    await db_session.commit()
    await db_session.refresh(employee)
    token = (await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]
    return employee, {"Authorization": f"Bearer {token}"}


async def _punch(client, headers, employee_id, punch_type, ts):
    r = await client.post("/punches", headers=headers, json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text


async def test_flexible_weekly_target_without_fixed_days(client: AsyncClient, db_session: AsyncSession) -> None:
    # Austritt am Sonntag 16.3. -> zwei vollständige Wochen, datumsunabhängig.
    employee, headers = await _setup(db_session, client, termination_date=date(2025, 3, 16))
    r = await client.put(f"/employees/{employee.id}/work-time-model", headers=headers, json={"weekly_hours": 8, "flexible": True, "valid_from": "2025-01-01"})
    assert r.status_code == 200 and r.json()["flexible"] is True and r.json()["weekly_minutes"] == 480

    # Woche 1: Di 3 Std. + Sa 5 Std. = 8 Std. (Samstag ist kein "außerplanmäßig").
    await _punch(client, headers, employee.id, "COME", "2025-03-04T08:00:00Z")
    await _punch(client, headers, employee.id, "GO", "2025-03-04T11:00:00Z")
    await _punch(client, headers, employee.id, "COME", "2025-03-08T08:00:00Z")
    await _punch(client, headers, employee.id, "GO", "2025-03-08T13:00:00Z")
    # Woche 2: Montag Urlaub (Gutschrift 8/5 = 96 Min.), sonst nichts.
    await client.post("/absences", headers=headers, json={"employee_id": employee.id, "type": "VACATION", "date_from": "2025-03-10", "date_to": "2025-03-10"})

    days = {d["work_date"]: d for d in (await client.get(f"/employees/{employee.id}/timesheet", headers=headers, params={"from": "2025-03-03", "to": "2025-03-16"})).json()}
    assert days["2025-03-08"]["flags"] == [] and days["2025-03-05"]["flags"] == []
    assert days["2025-03-10"]["actual_minutes"] == 96

    balance = (await client.get(f"/employees/{employee.id}/overtime-balance", headers=headers)).json()
    # Konto beginnt mit der ersten Stempelung (Di) -> Woche 1 anteilig 6/7 des Wochensolls.
    assert balance["running_balance_minutes"] == (480 - round(480 * 6 / 7)) + (96 - 480)
    assert (await client.get("/timesheet/open-days", headers=headers)).json() == []

    entitlement = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=headers, params={"year": 2025})).json()
    assert entitlement["used_days"] == 1


async def test_multiple_come_go_gaps_count_as_break(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    db_session.add(BreakRule(min_work_minutes=360, deduct_minutes=30))
    await db_session.commit()
    # 08-12 und 12:45-17:00: 8:15 Std. brutto, 45 Min. Unterbrechung >= 30 Min. Pflichtpause -> kein Abzug.
    for t, ts in (("COME", "2025-03-04T08:00:00Z"), ("GO", "2025-03-04T12:00:00Z"), ("COME", "2025-03-04T12:45:00Z"), ("GO", "2025-03-04T17:00:00Z")):
        await _punch(client, headers, employee.id, t, ts)
    day = (await client.get(f"/employees/{employee.id}/timesheet", headers=headers, params={"from": "2025-03-04", "to": "2025-03-04"})).json()[0]
    assert day["actual_minutes"] == 495
    # 10 Minuten Unterbrechung zählt nicht als Pause -> Pflichtpause wird abgezogen.
    for t, ts in (("COME", "2025-03-05T08:00:00Z"), ("GO", "2025-03-05T12:00:00Z"), ("COME", "2025-03-05T12:10:00Z"), ("GO", "2025-03-05T16:10:00Z")):
        await _punch(client, headers, employee.id, t, ts)
    day = (await client.get(f"/employees/{employee.id}/timesheet", headers=headers, params={"from": "2025-03-05", "to": "2025-03-05"})).json()[0]
    assert day["actual_minutes"] == 480 - 30

    report = await client.get(f"/employees/{employee.id}/month-report", headers=headers, params={"year": 2025, "month": 3})
    assert report.status_code == 200


async def test_auto_break_only_books_missing_part_across_pairs(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    employee.auto_break_enabled = True
    db_session.add(BreakRule(min_work_minutes=360, deduct_minutes=30))
    await db_session.commit()
    # 08-11, 11:20-15:30 -> 20 Min. Lücke, es fehlen 10 Min. Pause -> Auto-Pause 10 Min.
    for t, ts in (("COME", "2025-03-04T08:00:00Z"), ("GO", "2025-03-04T11:00:00Z"), ("COME", "2025-03-04T11:20:00Z"), ("GO", "2025-03-04T15:30:00Z")):
        await _punch(client, headers, employee.id, t, ts)
    punches = (await client.get(f"/employees/{employee.id}/punches", headers=headers, params={"from": "2025-03-04", "to": "2025-03-04"})).json()
    breaks = [p for p in punches if p["punch_type"] in ("BREAK_START", "BREAK_END")]
    assert len(breaks) == 2
    day = (await client.get(f"/employees/{employee.id}/timesheet", headers=headers, params={"from": "2025-03-04", "to": "2025-03-04"})).json()[0]
    assert day["actual_minutes"] == 180 + 250 - 10


async def test_reports_stop_at_today(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    await client.put(f"/employees/{employee.id}/work-time-model", headers=headers, json={"daily_hours": [8, 8, 8, 8, 8, 8, 8], "valid_from": "2025-01-01"})
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    weeks = (await client.get(f"/employees/{employee.id}/weekly-balance", headers=headers, params={"from": week_start.isoformat(), "to": (week_start + timedelta(days=6)).isoformat()})).json()
    # Soll nur für die Tage bis heute (inkl.), nicht für die ganze Woche.
    assert weeks[0]["target_minutes"] == 480 * (today.weekday() + 1)
