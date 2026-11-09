"""Sonderfälle: außerplanmäßig, trotz Abwesenheit, an Feiertagen, außerhalb Beschäftigung – zählen,
erscheinen aber unter "Zu klären", bis HR sie als geklärt markiert. Plus Abteilungs-Filter im Team-Kalender."""
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, EmployeeDefaultShift, Holiday, HrRole, Account, Location, ShiftTemplate
from app.services.auth_service import hash_password
from org_helpers import department


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1", termination_date=date(2025, 3, 31))
    template = ShiftTemplate(name="Normal", target_minutes=480)
    db_session.add_all([employee, template, Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)])
    await db_session.commit()
    db_session.add(EmployeeDefaultShift(employee_id=employee.id, shift_template_id=template.id, valid_from=date(2025, 1, 1), weekdays_mask=0b0011111))
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]
    return employee, {"Authorization": f"Bearer {token}"}


async def _work(client, headers, employee_id, day):
    for punch_type, hour in (("COME", "08"), ("GO", "12")):
        r = await client.post("/punches", headers=headers, json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{day}T{hour}:00:00Z", "idempotency_key": str(uuid.uuid4())})
        assert r.status_code == 201, r.text


async def _day(client, headers, employee_id, day):
    return (await client.get(f"/employees/{employee_id}/timesheet", headers=headers, params={"from": day, "to": day})).json()[0]


async def test_unplanned_work_counts_and_is_to_be_clarified_until_reviewed(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    await _work(client, headers, employee.id, "2025-03-03")  # Mo, damit das Konto startet
    await _work(client, headers, employee.id, "2025-03-08")  # Samstag = laut Plan frei

    saturday = await _day(client, headers, employee.id, "2025-03-08")
    assert saturday["status"] == "COMPLETE" and saturday["actual_minutes"] == 240 and saturday["target_minutes"] == 0
    assert saturday["flags"] == ["UNPLANNED_WORK"] and saturday["reviewed"] is False

    open_days = {d["work_date"]: d for d in (await client.get("/timesheet/open-days", headers=headers)).json()}
    assert open_days["2025-03-08"]["flags"] == ["UNPLANNED_WORK"]

    r = await client.put(f"/employees/{employee.id}/day-reviews/2025-03-08", headers=headers, json={"note": "Inventur, genehmigt"})
    assert r.status_code == 204
    assert "2025-03-08" not in {d["work_date"] for d in (await client.get("/timesheet/open-days", headers=headers)).json()}
    assert (await _day(client, headers, employee.id, "2025-03-08"))["reviewed"] is True


async def test_work_during_absence_holiday_and_outside_employment(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    db_session.add(Holiday(date=date(2025, 3, 5), name="Testfeiertag"))
    await db_session.commit()
    await client.post("/absences", headers=headers, json={"employee_id": employee.id, "type": "VACATION", "date_from": "2025-03-04", "date_to": "2025-03-04"})

    await _work(client, headers, employee.id, "2025-03-04")  # trotz Urlaub
    await _work(client, headers, employee.id, "2025-03-05")  # Feiertag
    await _work(client, headers, employee.id, "2025-04-01")  # nach Austritt

    vacation_day = await _day(client, headers, employee.id, "2025-03-04")
    assert vacation_day["flags"] == ["WORK_DURING_ABSENCE"] and vacation_day["actual_minutes"] == 240
    holiday = await _day(client, headers, employee.id, "2025-03-05")
    assert holiday["status"] == "HOLIDAY" and holiday["flags"] == ["HOLIDAY_WORK"] and holiday["actual_minutes"] == 480 + 240
    after = await _day(client, headers, employee.id, "2025-04-01")
    assert "OUTSIDE_EMPLOYMENT" in after["flags"]


async def test_team_calendar_filters_by_department(client: AsyncClient, db_session: AsyncSession) -> None:
    location = Location(name="A", timezone="UTC")
    db_session.add_all([location, Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)])
    await db_session.commit()
    a, b, c, d = (
        Employee(location_id=location.id, first_name=n, last_name=n, employee_number=str(i))
        for i, n in enumerate("ABCD", start=1)
    )
    db_session.add_all([a, b, c, d])
    await db_session.commit()
    # A in der A-Abteilung, D in deren Unterabteilung, B in der B-Abteilung, C ohne Abteilung
    dep_a = await department(db_session, "A-Abteilung", a)
    dep_b = await department(db_session, "B-Abteilung", b)
    sub_a = await department(db_session, "A-Unterabteilung", d, parent=dep_a)
    headers = {"Authorization": "Bearer " + (await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]}
    params = {"from": "2025-03-01", "to": "2025-03-31"}

    def names(r):
        return sorted(e["last_name"] for e in r.json())

    everyone = await client.get("/team-calendar", headers=headers, params=params)
    assert names(everyone) == ["A", "B", "C", "D"]
    assert {e["last_name"]: e["department_id"] for e in everyone.json()} == {"A": dep_a.id, "B": dep_b.id, "C": None, "D": sub_a.id}
    # Eine Abteilung umfasst ihre Unterabteilungen; 0 = ohne Abteilung; mehrere Angaben werden vereinigt
    assert names(await client.get("/team-calendar", headers=headers, params={**params, "department_id": dep_a.id})) == ["A", "D"]
    assert names(await client.get("/team-calendar", headers=headers, params={**params, "department_id": sub_a.id})) == ["D"]
    assert names(await client.get("/team-calendar", headers=headers, params={**params, "department_id": [dep_a.id, 0]})) == ["A", "C", "D"]
    assert names(await client.get("/team-calendar", headers=headers, params={**params, "department_id": [dep_b.id, sub_a.id]})) == ["B", "D"]
    assert names(await client.get("/team-calendar", headers=headers, params={**params, "department_id": 0})) == ["C"]
