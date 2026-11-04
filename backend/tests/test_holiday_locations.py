from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password
from app.services.holiday_import_service import ensure_holidays_imported_for_tenant
from app.services.settings_service import get_or_create_settings
from app.services.timesheet_service import calculate_day, employee_timezone


async def _create_location(db_session: AsyncSession, name: str, bundesland: str | None = None) -> Location:
    location = Location(name=name, timezone="UTC", bundesland=bundesland)
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(db_session: AsyncSession, location: Location, number: str) -> Employee:
    employee = Employee(
        location_id=location.id, first_name="Max", last_name="Mustermann", employee_number=number, active=True
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_hr_user(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_location_specific_holiday_only_affects_that_locations_employees(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    bavaria = await _create_location(db_session, "Bayern-Standort")
    nrw = await _create_location(db_session, "NRW-Standort")
    employee_bavaria = await _create_employee(db_session, bavaria, "EMP-1")
    employee_nrw = await _create_employee(db_session, nrw, "EMP-2")
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    await client.post(
        "/holidays",
        headers={"Authorization": f"Bearer {token}"},
        json={"date": "2026-08-15", "name": "Mariä Himmelfahrt", "location_ids": [bavaria.id]},
    )

    tz = await employee_timezone(db_session, employee_bavaria)
    bavaria_calc = await calculate_day(db_session, employee_bavaria, date(2026, 8, 15), tz)
    nrw_calc = await calculate_day(db_session, employee_nrw, date(2026, 8, 15), tz)

    assert bavaria_calc.status.value == "HOLIDAY"
    assert nrw_calc.status.value == "OPEN_MISSING_PUNCH"


async def test_global_holiday_applies_to_all_locations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location_a = await _create_location(db_session, "Standort A")
    location_b = await _create_location(db_session, "Standort B")
    employee_a = await _create_employee(db_session, location_a, "EMP-1")
    employee_b = await _create_employee(db_session, location_b, "EMP-2")
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    await client.post(
        "/holidays",
        headers={"Authorization": f"Bearer {token}"},
        json={"date": "2026-12-25", "name": "1. Weihnachtstag"},
    )

    tz = await employee_timezone(db_session, employee_a)
    calc_a = await calculate_day(db_session, employee_a, date(2026, 12, 25), tz)
    calc_b = await calculate_day(db_session, employee_b, date(2026, 12, 25), tz)

    assert calc_a.status.value == "HOLIDAY"
    assert calc_b.status.value == "HOLIDAY"


async def test_import_for_two_locations_does_not_duplicate_shared_dates(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    bavaria = await _create_location(db_session, "Bayern-Standort")
    nrw = await _create_location(db_session, "NRW-Standort")
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    first = await client.post(
        "/holidays/import",
        headers={"Authorization": f"Bearer {token}"},
        json={"year": 2026, "location_id": bavaria.id, "bundesland": "BY"},
    )
    assert len(first.json()["imported"]) > 0

    second = await client.post(
        "/holidays/import",
        headers={"Authorization": f"Bearer {token}"},
        json={"year": 2026, "location_id": nrw.id, "bundesland": "NW"},
    )
    # Neujahr, Tag der Arbeit etc. sind in beiden Ländern identisch, wurden aber
    # bereits für Bayern importiert -> für NRW zählen sie als "bereits vorhanden"
    # (standortübergreifend gilt ein location_id=None-Feiertag nicht hier, da
    # Bayern-Import standortgebunden war) - NRW muss trotzdem seine eigenen
    # Feiertage bekommen, ohne Fehler.
    assert second.status_code == 200
    assert len(second.json()["imported"]) > 0

    # Gleiche Feiertage stehen nur einmal da und tragen beide Standorte.
    holidays = (await client.get("/holidays?year=2026", headers={"Authorization": f"Bearer {token}"})).json()
    new_year = [h for h in holidays if h["date"] == "2026-01-01"]
    assert len(new_year) == 1
    assert sorted(new_year[0]["location_ids"]) == sorted([bavaria.id, nrw.id])
    # Fronleichnam gibt es nur in Bayern, nicht in NRW (Stand der Feiertagslogik).
    only_bavaria = [h for h in holidays if h["location_ids"] == [bavaria.id]]
    assert only_bavaria


async def test_ensure_holidays_imported_uses_location_bundesland(db_session: AsyncSession) -> None:
    location = await _create_location(db_session, "Bayern-Standort", bundesland="BY")

    await ensure_holidays_imported_for_tenant(db_session, tenant_id=1)

    from sqlalchemy import select

    from app.models import Holiday

    result = await db_session.execute(select(Holiday).where(Holiday.locations.any(Location.id == location.id)))
    holidays = result.scalars().all()
    assert len(holidays) > 0
    assert any(h.name == "Mariä Himmelfahrt" for h in holidays)


async def test_ensure_holidays_imported_uses_global_default_bundesland(db_session: AsyncSession) -> None:
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    settings_row.default_bundesland = "SN"
    await db_session.commit()

    await ensure_holidays_imported_for_tenant(db_session, tenant_id=1)

    from sqlalchemy import select

    from app.models import Holiday

    result = await db_session.execute(select(Holiday).where(~Holiday.locations.any()))
    holidays = result.scalars().all()
    assert any(h.name == "Reformationstag" for h in holidays)
