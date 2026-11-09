"""Zusatzurlaub nach Betriebszugehörigkeit: ab dem Jahr, in dem die Jahre vollendet werden."""
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.leave_service import seniority_extra_days
from tests.test_absence_types import _setup


def test_extra_days_by_completed_years() -> None:
    hired = date(2020, 8, 1)
    assert seniority_extra_days("5:1,10:2", hired, 2024) == 0
    assert seniority_extra_days("5:1,10:2", hired, 2025) == 1
    assert seniority_extra_days("5:1,10:2", hired, 2030) == 2
    assert seniority_extra_days(None, hired, 2030) == 0


async def test_seniority_rules_in_settings_and_entitlement(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    employee.hire_date = date(2015, 3, 1)
    await db_session.commit()
    bad = await client.patch("/settings", headers=headers, json={"seniority_leave_rules": [{"years": 10, "days": 2}, {"years": 5, "days": 1}]})
    assert bad.status_code == 400
    r = await client.patch(
        "/settings", headers=headers,
        json={"default_annual_vacation_days": 30, "seniority_leave_rules": [{"years": 5, "days": 1}, {"years": 10, "days": 2}]},
    )
    assert r.status_code == 200 and r.json()["seniority_leave_rules"] == [{"years": 5, "days": 1}, {"years": 10, "days": 2}]
    entitlement = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=headers, params={"year": 2025})).json()
    assert entitlement["entitled_days"] == 32
