"""Teilzeit: Stunden je Wochentag, Urlaub nur an Arbeitstagen, anteiliger Anspruch."""
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSettings, Employee, HrRole, Account, Location
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Tina", last_name="Teilzeit", employee_number="T1")
    db_session.add_all([employee, Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)])
    await db_session.commit()
    await db_session.refresh(employee)
    from sqlalchemy import update

    await db_session.execute(update(AppSettings).where(AppSettings.tenant_id == 1).values(default_annual_vacation_days=30))
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]
    return employee, location, {"Authorization": f"Bearer {token}"}


async def test_daily_hours_set_target_per_weekday(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, _, headers = await _setup(db_session, client)
    r = await client.put(f"/employees/{employee.id}/work-time-model", headers=headers, json={
        "daily_hours": [8, 8, 4, 0, 0, 0, 0], "valid_from": "2025-01-01",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["weekly_minutes"] == 1200 and body["weekdays"] == [0, 1, 2] and body["uneven"] is True
    assert body["day_minutes"] == [480, 480, 240, 0, 0, 0, 0]

    days = {d["work_date"]: d for d in (await client.get(f"/employees/{employee.id}/timesheet", headers=headers, params={"from": "2025-03-03", "to": "2025-03-07"})).json()}
    assert days["2025-03-03"]["target_minutes"] == 480  # Mo
    assert days["2025-03-05"]["target_minutes"] == 240  # Mi
    assert days["2025-03-06"]["status"] == "PLANNED_OFF"  # Do frei

    too_long = await client.put(f"/employees/{employee.id}/work-time-model", headers=headers, json={"daily_hours": [11, 0, 0, 0, 0, 0, 0], "valid_from": "2025-01-01"})
    assert too_long.status_code == 400 and too_long.json()["code"] == "MAX_DAILY_WORKING_TIME_EXCEEDED"
    assert (await client.put(f"/employees/{employee.id}/work-time-model", headers=headers, json={"daily_hours": [0] * 7, "valid_from": "2025-01-01"})).status_code == 422


async def test_vacation_counts_only_workdays_and_entitlement_is_prorated(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, _, headers = await _setup(db_session, client)
    await client.put(f"/employees/{employee.id}/work-time-model", headers=headers, json={"daily_hours": [8, 8, 4, 0, 0, 0, 0], "valid_from": "2025-01-01"})

    # Ganze Woche Urlaub -> nur Mo, Di, Mi zählen.
    r = await client.post("/absences", headers=headers, json={"employee_id": employee.id, "type": "VACATION", "date_from": "2025-03-03", "date_to": "2025-03-09"})
    assert r.status_code == 201
    entitlement = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=headers, params={"year": 2025})).json()
    assert entitlement["used_days"] == 3
    assert entitlement["entitled_days"] == 18  # 30 x 3/5
    assert entitlement["suggested_entitled_days"] == 18 and entitlement["workdays_per_week"] == 3

    # Urlaubstag wird mit dem Soll des Tages gutgeschrieben (Mi = 4 Std.).
    wednesday = (await client.get(f"/employees/{employee.id}/timesheet", headers=headers, params={"from": "2025-03-05", "to": "2025-03-05"})).json()[0]
    assert wednesday["status"] == "ABSENCE" and wednesday["actual_minutes"] == 240


async def test_csv_import_with_daily_hours(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, headers = await _setup(db_session, client)
    csv_text = "vorname;nachname;personalnummer;standort;tagesstunden\nP;Q;T2;Zentrale;Mo:8,Di:8,Mi:4:30\n"
    result = (await client.post("/employees/bulk-import", headers=headers, files={"file": ("m.csv", csv_text.encode(), "text/csv")})).json()
    assert result["created"] == 1, result
    from sqlalchemy import select

    imported = (await db_session.execute(select(Employee).where(Employee.employee_number == "T2"))).scalar_one()
    model = (await client.get(f"/employees/{imported.id}/work-time-model", headers=headers)).json()
    assert model["day_minutes"] == [480, 480, 270, 0, 0, 0, 0]
