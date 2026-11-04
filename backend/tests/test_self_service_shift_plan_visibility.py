from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, Location
from app.services.auth_service import hash_password


async def _create_self_service_employee(db_session: AsyncSession) -> Employee:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    employee = Employee(
        location_id=location.id,
        first_name="Erika",
        last_name="Muster",
        employee_number="EMP-1",
        active=True,
        login_email="erika@example.com",
        password_hash=hash_password("pw123456"),
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _employee_token(client: AsyncClient) -> str:
    response = await client.post(
        "/auth/employee/login", json={"email": "erika@example.com", "password": "pw123456"}
    )
    return response.json()["access_token"]


async def test_self_service_employee_can_view_own_default_shifts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_self_service_employee(db_session)
    token = await _employee_token(client)

    response = await client.get(
        f"/employees/{employee.id}/default-shifts", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_self_service_employee_can_view_own_shift_plan_entries(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_self_service_employee(db_session)
    token = await _employee_token(client)

    response = await client.get(
        f"/employees/{employee.id}/shift-plan-entries",
        params={"from": "2026-08-01", "to": "2026-08-31"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_self_service_employee_cannot_view_other_employees_default_shifts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_self_service_employee(db_session)
    other = Employee(
        location_id=employee.location_id, first_name="Max", last_name="Mustermann", employee_number="EMP-2"
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    token = await _employee_token(client)
    response = await client.get(
        f"/employees/{other.id}/default-shifts", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
