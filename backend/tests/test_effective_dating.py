"""Gültig-ab-Datierung: Pausenregeln, Schichtvorlagen-Soll, Standortwechsel; Arbeitszeitmodell beim Anlegen/Import."""
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BreakRule,
    Employee,
    EmployeeDefaultShift,
    Holiday,
    HrRole,
    HrUser,
    Location,
    PeriodClosure,
    PeriodStatus,
    ShiftTemplate,
)
from app.services.auth_service import hash_password


async def _admin(db_session: AsyncSession, client: AsyncClient) -> dict:
    db_session.add(HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    token = (await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _employee(db_session: AsyncSession, **kwargs) -> tuple[Employee, Location]:
    location = Location(name="A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1", **kwargs)
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee, location


async def _punch(client, headers, employee_id, punch_type, ts):
    r = await client.post("/punches", headers=headers, json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text


async def _day(client, headers, employee_id, day: str) -> dict:
    return (await client.get(f"/employees/{employee_id}/timesheet", headers=headers, params={"from": day, "to": day})).json()[0]


async def test_break_rule_change_applies_from_date_only(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin(db_session, client)
    employee, _ = await _employee(db_session)
    rule = (await client.post("/break-rules", headers=headers, json={"min_work_minutes": 360, "deduct_minutes": 30, "valid_from": "2025-01-01"})).json()
    for day in ("2025-03-03", "2025-06-02"):
        await _punch(client, headers, employee.id, "COME", f"{day}T08:00:00Z")
        await _punch(client, headers, employee.id, "GO", f"{day}T16:00:00Z")

    changed = await client.patch(f"/break-rules/{rule['id']}", headers=headers, json={"deduct_minutes": 45, "valid_from": "2025-05-01"})
    assert changed.status_code == 200 and changed.json()["valid_from"] == "2025-05-01"
    assert (await _day(client, headers, employee.id, "2025-03-03"))["actual_minutes"] == 450  # alte Staffel
    assert (await _day(client, headers, employee.id, "2025-06-02"))["actual_minutes"] == 435  # neue Staffel

    history = (await client.get("/break-rules", headers=headers, params={"include_history": True})).json()
    assert [(r["deduct_minutes"], r["valid_to"]) for r in history] == [(30, "2025-04-30"), (45, None)]
    duplicate = await client.post("/break-rules", headers=headers, json={"min_work_minutes": 360, "deduct_minutes": 20})
    assert duplicate.status_code == 409


async def test_break_rule_change_into_locked_month_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin(db_session, client)
    employee, _ = await _employee(db_session)
    db_session.add(PeriodClosure(tenant_id=1, employee_id=employee.id, year=2025, month=5, status=PeriodStatus.CLOSED,
                                 target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=date(2025, 6, 1)))
    await db_session.commit()
    blocked = await client.post("/break-rules", headers=headers, json={"min_work_minutes": 540, "deduct_minutes": 45, "valid_from": "2025-04-01"})
    assert blocked.status_code == 409 and blocked.json()["code"] == "PERIOD_LOCKED"
    assert (await client.post("/break-rules", headers=headers, json={"min_work_minutes": 540, "deduct_minutes": 45, "valid_from": "2025-06-01"})).status_code == 201


async def test_template_target_change_keeps_history(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin(db_session, client)
    employee, _ = await _employee(db_session)
    template = ShiftTemplate(name="Normal", target_minutes=480)
    db_session.add(template)
    await db_session.commit()
    db_session.add(EmployeeDefaultShift(employee_id=employee.id, shift_template_id=template.id, valid_from=date(2025, 1, 1), weekdays_mask=0b0011111))
    await db_session.commit()

    r = await client.patch(f"/shift-templates/{template.id}", headers=headers, json={"target_minutes": 420, "valid_from": "2025-05-01"})
    assert r.status_code == 200 and r.json()["name"] == "Normal" and r.json()["id"] != template.id
    assert (await _day(client, headers, employee.id, "2025-03-03"))["target_minutes"] == 480
    assert (await _day(client, headers, employee.id, "2025-06-02"))["target_minutes"] == 420
    names = [t["name"] for t in (await client.get("/shift-templates", headers=headers)).json()]
    assert names == ["Normal"]  # alte Fassung archiviert


async def test_location_change_keeps_old_holidays_for_the_past(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin(db_session, client)
    employee, location_a = await _employee(db_session)
    location_b = Location(name="B", timezone="UTC")
    db_session.add(location_b)
    await db_session.commit()
    await db_session.refresh(location_b)
    holiday_a = Holiday(date=date(2025, 3, 3), name="Nur A", locations=[location_a])
    holiday_b = Holiday(date=date(2025, 6, 2), name="Nur B", locations=[location_b])
    db_session.add_all([holiday_a, holiday_b])
    await db_session.commit()

    r = await client.patch(f"/employees/{employee.id}", headers=headers, json={"location_id": location_b.id, "location_valid_from": "2025-05-01"})
    assert r.status_code == 200, r.text
    assert (await _day(client, headers, employee.id, "2025-03-03"))["status"] == "HOLIDAY"  # damals Standort A
    assert (await _day(client, headers, employee.id, "2025-06-02"))["status"] == "HOLIDAY"  # jetzt Standort B


async def test_work_time_model_on_create_and_csv_import(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin(db_session, client)
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    too_much = await client.post("/employees", headers=headers, json={
        "location_id": location.id, "first_name": "A", "last_name": "B", "employee_number": "X1",
        "work_time_model": {"weekly_hours": 60, "weekdays": [0, 1, 2, 3, 4]},
    })
    assert too_much.status_code == 400 and too_much.json()["code"] == "MAX_DAILY_WORKING_TIME_EXCEEDED"
    created = await client.post("/employees", headers=headers, json={
        "location_id": location.id, "first_name": "A", "last_name": "B", "employee_number": "X1", "hire_date": "2025-01-01",
        "work_time_model": {"weekly_hours": 20, "weekdays": [0, 1, 2, 3, 4]},
    })
    assert created.status_code == 201
    model = (await client.get(f"/employees/{created.json()['id']}/work-time-model", headers=headers)).json()
    assert model["configured"] and model["weekly_minutes"] == 1200

    csv_text = "vorname;nachname;personalnummer;standort;wochenstunden;arbeitstage\nC;D;X2;Zentrale;30;Mo-Mi\nE;F;X3;Zentrale;30;Mo-Xy\n"
    result = await client.post("/employees/bulk-import", headers=headers, files={"file": ("m.csv", csv_text.encode(), "text/csv")})
    body = result.json()
    assert body["created"] == 1 and body["errors"][0]["row"] == 3
    imported = (await db_session.execute(select(Employee).where(Employee.employee_number == "X2"))).scalar_one()
    model = (await client.get(f"/employees/{imported.id}/work-time-model", headers=headers)).json()
    assert model["weekly_minutes"] == 1800 and model["weekdays"] == [0, 1, 2]
