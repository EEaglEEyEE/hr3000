from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession, name: str = "Standort A") -> Location:
    location = Location(name=name, timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee_with_role(
    db_session: AsyncSession,
    location: Location,
    email: str,
    hr_role: HrRole | None,
    number: str = "EMP-HR",
) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Petra",
        last_name="Personal",
        employee_number=number,
        active=True,
        login_email=email,
        password_hash=hash_password("pw123456"),
        hr_role=hr_role,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_plain_employee(db_session: AsyncSession, location: Location, number: str) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Mustermann",
        employee_number=number,
        active=True,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_admin_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _employee_token(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": "pw123456"})
    return response.json()["access_token"]


async def _hr_token(client: AsyncClient, email: str, password: str = "pw") -> str:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    return response.json()["access_token"]


async def test_employee_with_hr_role_can_list_and_create_employees(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_employee_with_role(db_session, location, "petra@example.com", HrRole.HR)
    token = await _employee_token(client, "petra@example.com")

    list_response = await client.get("/employees", headers={"Authorization": f"Bearer {token}"})
    assert list_response.status_code == 200

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Neu",
            "last_name": "Angelegt",
            "employee_number": "EMP-NEW",
        },
    )
    assert create_response.status_code == 201


async def test_employee_with_hr_role_can_view_other_employees_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_employee_with_role(db_session, location, "petra@example.com", HrRole.HR)
    other = await _create_plain_employee(db_session, location, "EMP-OTHER")
    token = await _employee_token(client, "petra@example.com")

    response = await client.get(
        f"/employees/{other.id}/punches", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200


async def test_plain_employee_without_hr_role_still_restricted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_employee_with_role(db_session, location, "erika@example.com", None)
    other = await _create_plain_employee(db_session, location, "EMP-OTHER")
    token = await _employee_token(client, "erika@example.com")

    response = await client.get(
        f"/employees/{other.id}/punches", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"

    list_response = await client.get("/employees", headers={"Authorization": f"Bearer {token}"})
    assert list_response.status_code == 403
    assert list_response.json()["code"] == "HR_PERMISSION_REQUIRED"


async def test_only_admin_can_grant_hr_role(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    hr_employee = await _create_employee_with_role(db_session, location, "petra@example.com", HrRole.HR)
    target = await _create_plain_employee(db_session, location, "EMP-TARGET")
    hr_token = await _employee_token(client, "petra@example.com")

    response = await client.patch(
        f"/employees/{target.id}/hr-role",
        headers={"Authorization": f"Bearer {hr_token}"},
        json={"hr_role": "HR"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ADMIN_PERMISSION_REQUIRED"

    await _create_employee_with_role(
        db_session, location, "admin-emp@example.com", HrRole.ADMIN, number="EMP-ADMIN"
    )
    admin_token = await _employee_token(client, "admin-emp@example.com")

    grant_response = await client.patch(
        f"/employees/{target.id}/hr-role",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hr_role": "HR"},
    )
    assert grant_response.status_code == 200
    assert grant_response.json()["hr_role"] == "HR"

    revoke_response = await client.patch(
        f"/employees/{target.id}/hr-role",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hr_role": None},
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json()["hr_role"] is None


async def test_admin_hr_role_employee_can_manage_hr_users(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_employee_with_role(db_session, location, "admin-emp@example.com", HrRole.ADMIN)
    token = await _employee_token(client, "admin-emp@example.com")

    response = await client.post(
        "/hr-users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "extra@example.com", "password": "pw123456"},
    )

    assert response.status_code == 201


async def test_punch_correction_records_created_by_employee_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    hr_employee = await _create_employee_with_role(db_session, location, "petra@example.com", HrRole.HR)
    target = await _create_plain_employee(db_session, location, "EMP-TARGET")
    token = await _employee_token(client, "petra@example.com")

    create_response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": target.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "aaaaaaaa-1111-1111-1111-111111111111",
        },
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["created_by_account_id"] == hr_employee.account.id

    correct_response = await client.patch(
        f"/punches/{body['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"correction_reason": "Testkorrektur durch HR-Mitarbeiter"},
    )
    assert correct_response.status_code == 200
    corrected = correct_response.json()
    assert corrected["created_by_account_id"] == hr_employee.account.id


async def test_absence_created_by_employee_id_for_hr_role_employee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    hr_employee = await _create_employee_with_role(db_session, location, "petra@example.com", HrRole.HR)
    target = await _create_plain_employee(db_session, location, "EMP-TARGET")
    token = await _employee_token(client, "petra@example.com")

    response = await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": target.id,
            "type": "VACATION",
            "date_from": "2026-08-10",
            "date_to": "2026-08-10",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["created_by_account_id"] == hr_employee.account.id


async def test_legacy_hr_user_login_still_works_alongside_hr_role(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reine Verwaltungskonten (ohne Mitarbeiter) bleiben unverändert funktionsfähig, auch
    nachdem Mitarbeiter jetzt ebenfalls hr_role haben können."""
    await _create_admin_hr_user(db_session)
    token = await _hr_token(client, "admin@example.com")

    response = await client.get("/employees", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
