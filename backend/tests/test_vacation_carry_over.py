"""Automatischer Urlaubsübertrag mit Obergrenze und Verfall zum Stichtag."""
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSettings, Employee, HrRole, Account, Location
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Uwe", last_name="Urlaub", employee_number="U1")
    db_session.add_all([employee, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    await db_session.refresh(employee)
    await db_session.execute(update(AppSettings).where(AppSettings.tenant_id == 1).values(default_annual_vacation_days=30))
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=headers,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2024-01-01"},
    )
    assert r.status_code == 200, r.text
    return employee, headers


async def _entitlement(client: AsyncClient, headers: dict, employee_id: int, year: int) -> dict:
    r = await client.get(f"/employees/{employee_id}/leave-entitlement", headers=headers, params={"year": year})
    assert r.status_code == 200, r.text
    return r.json()


async def test_carry_over_is_capped_and_expires(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    r = await client.patch(
        "/settings",
        headers=headers,
        json={"vacation_carry_over_auto": True, "vacation_carry_over_max_days": 5, "vacation_carry_over_expiry": "03-31"},
    )
    assert r.status_code == 200, r.text
    assert (await client.patch("/settings", headers=headers, json={"vacation_carry_over_expiry": "02-30"})).status_code == 400
    assert (await client.patch("/settings", headers=headers, json={"vacation_carry_over_expiry": "13-01"})).status_code == 422

    # 2024: 30 Tage Anspruch, 20 genommen -> 10 Rest.
    await _entitlement(client, headers, employee.id, 2024)
    await client.post("/absences", headers=headers, json={"employee_id": employee.id, "type": "VACATION", "date_from": "2024-07-01", "date_to": "2024-07-26"})
    assert (await _entitlement(client, headers, employee.id, 2024))["remaining_days"] == 10

    # 2025: Übertrag auf 5 begrenzt, 2 Tage bis 31.03. genommen -> 3 verfallen.
    await client.post("/absences", headers=headers, json={"employee_id": employee.id, "type": "VACATION", "date_from": "2025-02-03", "date_to": "2025-02-04"})
    year_2025 = await _entitlement(client, headers, employee.id, 2025)
    assert year_2025["carried_over_auto"] is True
    assert year_2025["carried_over_days"] == 5
    assert year_2025["expired_days"] == 3
    assert year_2025["expiry_date"] == "2025-03-31"
    assert year_2025["remaining_days"] == 30 + 5 - 3 - 2

    # HR trägt den Übertrag fest ein – und schaltet wieder auf automatisch.
    manual = (
        await client.patch(f"/employees/{employee.id}/leave-entitlement", headers=headers, params={"year": 2025}, json={"carried_over_days": 8})
    ).json()
    assert manual["carried_over_auto"] is False and manual["carried_over_days"] == 8
    auto = (
        await client.patch(f"/employees/{employee.id}/leave-entitlement", headers=headers, params={"year": 2025}, json={"carried_over_auto": True})
    ).json()
    assert auto["carried_over_auto"] is True and auto["carried_over_days"] == 5


async def test_without_auto_carry_over_manual_value_counts(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    await _entitlement(client, headers, employee.id, 2024)
    year_2025 = (
        await client.patch(f"/employees/{employee.id}/leave-entitlement", headers=headers, params={"year": 2025}, json={"carried_over_days": 4})
    ).json()
    assert year_2025["carried_over_days"] == 4 and year_2025["expired_days"] == 0 and year_2025["remaining_days"] == 34
