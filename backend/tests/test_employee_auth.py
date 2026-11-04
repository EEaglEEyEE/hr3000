from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee_with_login(
    db_session: AsyncSession, location: Location, email: str = "erika@example.com"
) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Erika",
        last_name="Musterfrau",
        employee_number="EMP-1",
        active=True,
        login_email=email,
        password_hash=hash_password("pw123456"),
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_other_employee(db_session: AsyncSession, location: Location) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Mustermann",
        employee_number="EMP-2",
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


async def test_employee_login_success(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_employee_with_login(db_session, location)

    response = await client.post(
        "/auth/employee/login", json={"email": "erika@example.com", "password": "pw123456"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_employee_login_wrong_password(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_employee_with_login(db_session, location)

    response = await client.post(
        "/auth/employee/login", json={"email": "erika@example.com", "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


async def test_employee_login_without_login_enabled(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_other_employee(db_session, location)  # kein login_email gesetzt

    response = await client.post(
        "/auth/employee/login", json={"email": "max@example.com", "password": "whatever"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


async def test_employee_refresh_flow(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_employee_with_login(db_session, location)
    login_response = await client.post(
        "/auth/employee/login", json={"email": "erika@example.com", "password": "pw123456"}
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await client.post("/auth/employee/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert "access_token" in response.json()


async def test_employee_refresh_rejects_hr_refresh_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ein HR-Refresh-Token darf nicht am Mitarbeiter-Refresh-Endpoint funktionieren,
    da sub=HrUser.id sonst als Employee.id fehlinterpretiert werden könnte."""
    await _create_hr_user(db_session)
    login_response = await client.post(
        "/auth/hr/login", json={"email": "hr@example.com", "password": "pw"}
    )
    hr_refresh_token = login_response.json()["refresh_token"]

    response = await client.post("/auth/employee/refresh", json={"refresh_token": hr_refresh_token})

    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"


async def _employee_token(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/auth/employee/login", json={"email": email, "password": password})
    return response.json()["access_token"]


async def test_employee_can_read_own_punches_timesheet_and_absences(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee_with_login(db_session, location)
    token = await _employee_token(client, "erika@example.com", "pw123456")

    punches_response = await client.get(
        f"/employees/{employee.id}/punches", headers={"Authorization": f"Bearer {token}"}
    )
    timesheet_response = await client.get(
        f"/employees/{employee.id}/timesheet?from=2026-08-01&to=2026-08-10",
        headers={"Authorization": f"Bearer {token}"},
    )
    absences_response = await client.get(
        f"/employees/{employee.id}/absences", headers={"Authorization": f"Bearer {token}"}
    )
    detail_response = await client.get(
        f"/employees/{employee.id}", headers={"Authorization": f"Bearer {token}"}
    )
    balance_response = await client.get(
        f"/employees/{employee.id}/overtime-balance", headers={"Authorization": f"Bearer {token}"}
    )

    assert punches_response.status_code == 200
    assert timesheet_response.status_code == 200
    assert absences_response.status_code == 200
    assert detail_response.status_code == 200
    assert balance_response.status_code == 200


async def test_employee_cannot_read_other_employees_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_employee_with_login(db_session, location)
    other = await _create_other_employee(db_session, location)
    token = await _employee_token(client, "erika@example.com", "pw123456")

    response = await client.get(
        f"/employees/{other.id}/punches", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_employee_cannot_create_punch(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee_with_login(db_session, location)
    token = await _employee_token(client, "erika@example.com", "pw123456")

    response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "77777777-7777-7777-7777-777777777777",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_employee_cannot_update_other_employee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Self-Service ist rein lesend – auch für die eigenen Daten kein PATCH."""
    location = await _create_location(db_session)
    employee = await _create_employee_with_login(db_session, location)
    token = await _employee_token(client, "erika@example.com", "pw123456")

    response = await client.patch(
        f"/employees/{employee.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"first_name": "Neu"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "HR_PERMISSION_REQUIRED"


async def test_hr_can_create_employee_with_login(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    hr_token = await _hr_token(client)

    response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {hr_token}"},
        json={
            "location_id": location.id,
            "first_name": "Neu",
            "last_name": "Angelegt",
            "employee_number": "EMP-99",
            "login_email": "neu@example.com",
            "password": "startpasswort",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["login_email"] == "neu@example.com"
    assert "password" not in body
    assert "password_hash" not in body

    login_response = await client.post(
        "/auth/employee/login", json={"email": "neu@example.com", "password": "startpasswort"}
    )
    assert login_response.status_code == 200


async def test_create_employee_duplicate_login_email_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_employee_with_login(db_session, location, email="dup@example.com")
    await _create_hr_user(db_session)
    hr_token = await _hr_token(client)

    response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {hr_token}"},
        json={
            "location_id": location.id,
            "first_name": "B",
            "last_name": "C",
            "employee_number": "EMP-77",
            "login_email": "dup@example.com",
            "password": "irgendwas",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "LOGIN_EMAIL_TAKEN"
