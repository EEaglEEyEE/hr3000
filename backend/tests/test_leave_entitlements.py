from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Absence, AbsenceType, Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(db_session: AsyncSession, location: Location) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Mustermann",
        employee_number="EMP-1",
        active=True,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_hr_user(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_leave_entitlement_defaults_to_zero(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.get(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "employee_id": employee.id,
        "year": 2026,
        "entitled_days": 0,
        "carried_over_days": 0,
        "used_days": 0,
        "remaining_days": 0,
        "carried_over_auto": False,
        "expired_days": 0,
        "expiring_days": 0,
        "expiry_date": None,
        "suggested_entitled_days": None,
        "workdays_per_week": None,
    }


async def test_new_entitlement_uses_global_default_annual_vacation_days(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    # HR-Rolle darf /settings nicht ändern (siehe test_settings.py) – für
    # diesen Test direkt in der DB vorbelegen, kein zweiter Admin-User nötig.
    settings_row = await get_or_create_settings(db_session, employee.tenant_id)
    settings_row.default_annual_vacation_days = 30
    await db_session.commit()

    response = await client.get(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["entitled_days"] == 30


async def test_hr_can_set_entitlement_and_carry_over(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.patch(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
        json={"entitled_days": 28, "carried_over_days": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["entitled_days"] == 28
    assert body["carried_over_days"] == 3
    assert body["remaining_days"] == 31


async def test_remaining_days_accounts_for_used_vacation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    hr_user = await _create_hr_user(db_session)
    token = await _hr_token(client)

    await client.patch(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
        json={"entitled_days": 28},
    )

    # Mo 10.8. - Fr 14.8.2026: 5 Werktage Urlaub (kein Sonntag dabei).
    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.VACATION,
            date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 14),
            created_by=hr_user.id,
        )
    )
    await db_session.commit()

    response = await client.get(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["used_days"] == 5
    assert body["remaining_days"] == 23


async def test_sick_leave_does_not_count_as_vacation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    hr_user = await _create_hr_user(db_session)
    token = await _hr_token(client)

    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.SICK,
            date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 12),
            created_by=hr_user.id,
        )
    )
    await db_session.commit()

    response = await client.get(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.json()["used_days"] == 0


async def test_vacation_spanning_sunday_excludes_sunday_from_used_days(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    hr_user = await _create_hr_user(db_session)
    token = await _hr_token(client)

    # Sa 8.8. - Mo 10.8.2026 (So 9.8. liegt dazwischen und zählt nicht).
    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.VACATION,
            date_from=date(2026, 8, 8),
            date_to=date(2026, 8, 10),
            created_by=hr_user.id,
        )
    )
    await db_session.commit()

    response = await client.get(
        f"/employees/{employee.id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.json()["used_days"] == 2
