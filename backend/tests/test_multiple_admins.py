from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location
from app.services.auth_service import hash_password


async def _location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _employee(
    db_session: AsyncSession, location: Location, number: str, email: str, role: HrRole | None
) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name=number,
        employee_number=number,
        login_email=email,
        password_hash=hash_password("pw"),
        hr_role=role,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _employee_headers(client: AsyncClient, email: str) -> dict[str, str]:
    login = await client.post("/auth/login", json={"email": email, "password": "pw"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_employee_admin_has_admin_rights_and_can_appoint_more_admins(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _location(db_session)
    await _employee(db_session, location, "EMP-A", "a@example.com", HrRole.ADMIN)
    other = await _employee(db_session, location, "EMP-B", "b@example.com", None)
    headers = await _employee_headers(client, "a@example.com")

    settings_response = await client.patch("/settings", headers=headers, json={"require_pin_for_punch": True})
    assert settings_response.status_code == 200

    appoint = await client.patch(f"/employees/{other.id}/hr-role", headers=headers, json={"hr_role": "ADMIN"})
    assert appoint.status_code == 200
    assert appoint.json()["hr_role"] == "ADMIN"

    # Der neu ernannte Mitarbeiter-Admin darf selbst Admin-Aktionen ausführen.
    second_headers = await _employee_headers(client, "b@example.com")
    assert (await client.get("/settings", headers=second_headers)).status_code == 200


async def test_employee_admin_can_create_hr_user_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _location(db_session)
    await _employee(db_session, location, "EMP-A", "a@example.com", HrRole.ADMIN)
    headers = await _employee_headers(client, "a@example.com")

    response = await client.post(
        "/hr-users",
        headers=headers,
        json={"email": "zweiter-admin@example.com", "password": "pw123456", "role": "ADMIN"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "ADMIN"


async def test_super_admin_role_cannot_be_given_to_employee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _location(db_session)
    await _employee(db_session, location, "EMP-A", "a@example.com", HrRole.ADMIN)
    other = await _employee(db_session, location, "EMP-B", "b@example.com", None)
    headers = await _employee_headers(client, "a@example.com")

    response = await client.patch(
        f"/employees/{other.id}/hr-role", headers=headers, json={"hr_role": "SUPER_ADMIN"}
    )

    assert response.status_code == 403


async def test_last_admin_cannot_demote_self(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _location(db_session)
    only_admin = await _employee(db_session, location, "EMP-A", "a@example.com", HrRole.ADMIN)
    headers = await _employee_headers(client, "a@example.com")

    response = await client.patch(
        f"/employees/{only_admin.id}/hr-role", headers=headers, json={"hr_role": "HR"}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "LAST_ADMIN"


async def test_admin_can_demote_self_when_another_admin_exists(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _location(db_session)
    first = await _employee(db_session, location, "EMP-A", "a@example.com", HrRole.ADMIN)
    db_session.add(Account(email="hr-admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    headers = await _employee_headers(client, "a@example.com")

    response = await client.patch(f"/employees/{first.id}/hr-role", headers=headers, json={"hr_role": "HR"})

    assert response.status_code == 200
    assert response.json()["hr_role"] == "HR"
