"""Aushilfe "nach Aufwand": kein Soll, kein Saldo, Ist-Stunden je Monat, Monatsgrenze als Warnung."""
from datetime import date

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSettings, Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(
        location_id=location.id,
        first_name="Anton",
        last_name="Aushilfe",
        employee_number="A1",
        login_email="anton@example.com",
        password_hash=hash_password("pw123456"),
    )
    db_session.add_all([employee, HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)])
    await db_session.commit()
    await db_session.execute(update(AppSettings).where(AppSettings.tenant_id == 1).values(default_annual_vacation_days=30))
    await db_session.commit()
    hr = (await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]
    me = (await client.post("/auth/employee/login", json={"email": "anton@example.com", "password": "pw123456"})).json()[
        "access_token"
    ]
    return employee, {"Authorization": f"Bearer {hr}"}, {"Authorization": f"Bearer {me}"}


async def _punch(client: AsyncClient, headers: dict, employee_id: int, punch_type: str, ts: str) -> None:
    r = await client.post(
        "/punches",
        headers=headers,
        json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": f"{ts}{punch_type}"},
    )
    assert r.status_code == 201, r.text


async def test_on_demand_has_no_target_and_warns_over_monthly_cap(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, hr, me = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"
    assert (await client.put(url, headers=hr, json={"on_demand": True, "flexible": True, "valid_from": "2025-01-01"})).status_code == 422
    r = await client.put(url, headers=hr, json={"on_demand": True, "monthly_cap_hours": 10, "valid_from": "2025-01-01"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["on_demand"] is True and body["monthly_cap_minutes"] == 600 and body["weekly_minutes"] is None

    today = date.today().isoformat()
    await _punch(client, hr, employee.id, "COME", f"{today}T00:10:00Z")
    await _punch(client, hr, employee.id, "GO", f"{today}T06:10:00Z")
    await _punch(client, hr, employee.id, "COME", f"{today}T06:30:00Z")
    await _punch(client, hr, employee.id, "GO", f"{today}T11:30:00Z")

    day = (await client.get(f"/employees/{employee.id}/timesheet", headers=hr, params={"from": today, "to": today})).json()[0]
    # Kein Soll, nie "außerplanmäßig" – das 10-Stunden-Limit (§3 ArbZG) gilt aber weiter.
    assert day["target_minutes"] is None and day["flags"] == ["OVER_MAX_DAILY"]
    assert (await client.get(f"/employees/{employee.id}/overtime-balance", headers=hr)).json()["running_balance_minutes"] == 0

    caps = (await client.get("/timesheet/monthly-caps", headers=hr)).json()
    assert len(caps) == 1 and caps[0]["exceeded"] is True and caps[0]["cap_minutes"] == 600
    assert caps[0]["actual_minutes"] >= 600

    dashboard = (await client.get("/dashboard", headers=me)).json()["me"]
    assert dashboard["on_demand"] is True and dashboard["monthly_cap_minutes"] == 600
    assert dashboard["month_actual_minutes"] >= 600

    # Kein anteiliger Urlaubsvorschlag ohne feste Arbeitstage.
    leave = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=hr, params={"year": date.today().year})).json()
    assert leave["suggested_entitled_days"] is None and leave["workdays_per_week"] is None

    history = (await client.get(f"{url}/history", headers=hr)).json()
    assert history[0]["on_demand"] is True and history[0]["monthly_cap_minutes"] == 600
