"""Halbe Feiertage (z. B. Heiligabend): Arbeitstag mit halbem Soll; ein Urlaubstag zählt dort halb.
Ganze Feiertage verhalten sich unverändert."""
from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Punch, PunchSource, PunchType
from tests.test_absence_types import _day, _setup, _types


async def _half_holiday(client: AsyncClient, headers: dict, day: str = "2025-12-24") -> dict:
    r = await client.post("/holidays", headers=headers, json={"date": day, "name": "Heiligabend", "half_day": True})
    assert r.status_code == 201, r.text
    assert r.json()["half_day"] is True
    return r.json()


async def test_half_holiday_halves_target_and_stays_a_workday(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    await _half_holiday(client, headers)

    day = await _day(client, headers, employee.id, "2025-12-24")
    assert day["target_minutes"] == 240  # 8 Std. / 2
    assert day["status"] == "OPEN_MISSING_PUNCH"  # die andere Hälfte wird gearbeitet

    # 4 Std. gearbeitet -> Tag erledigt, Saldo 0
    for kind, hour in ((PunchType.COME, 8), (PunchType.GO, 12)):
        db_session.add(
            Punch(
                tenant_id=employee.tenant_id, employee_id=employee.id, location_id=employee.location_id,
                punch_type=kind, timestamp_utc=datetime(2025, 12, 24, hour), source=PunchSource.MANUAL_HR,
            )
        )
    await db_session.commit()
    day = await _day(client, headers, employee.id, "2025-12-24")
    assert (day["status"], day["target_minutes"], day["actual_minutes"]) == ("COMPLETE", 240, 240)


async def test_vacation_on_half_holiday_counts_half_a_day(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    await _half_holiday(client, headers)
    types = await _types(client, headers)

    r = await client.post(
        "/absences",
        headers=headers,
        json={"employee_id": employee.id, "absence_type_id": types["Urlaub"]["id"], "date_from": "2025-12-22", "date_to": "2025-12-24"},
    )
    assert r.status_code == 201, r.text

    day = await _day(client, headers, employee.id, "2025-12-24")
    assert (day["target_minutes"], day["actual_minutes"]) == (240, 240)
    entitlement = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=headers, params={"year": 2025})).json()
    assert entitlement["used_days"] == 2.5  # Mo + Di ganz, Heiligabend halb


async def test_half_day_flag_can_be_changed_and_full_holidays_stay_full(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    holiday = await _half_holiday(client, headers)
    r = await client.patch(f"/holidays/{holiday['id']}", headers=headers, json={"half_day": False})
    assert r.status_code == 200 and r.json()["half_day"] is False

    day = await _day(client, headers, employee.id, "2025-12-24")
    assert (day["status"], day["target_minutes"], day["actual_minutes"]) == ("HOLIDAY", 480, 480)
