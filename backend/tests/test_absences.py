from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location
from app.services.auth_service import hash_password


async def _create_employee(db_session: AsyncSession) -> Employee:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

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


async def _create_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_hr_can_create_and_list_absence(client: AsyncClient, db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "type": "VACATION",
            "date_from": "2026-08-10",
            "date_to": "2026-08-14",
            "note": "Sommerurlaub",
        },
    )

    assert create_response.status_code == 201
    body = create_response.json()
    assert body["type"] == "VACATION"
    assert body["created_by_account_id"] is not None

    list_response = await client.get(
        f"/employees/{employee.id}/absences", headers={"Authorization": f"Bearer {token}"}
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


async def test_create_absence_rejects_invalid_range(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_employee(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "type": "SICK",
            "date_from": "2026-08-14",
            "date_to": "2026-08-10",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_RANGE"


async def test_create_absence_unknown_employee(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={"employee_id": 999, "type": "SICK", "date_from": "2026-08-10", "date_to": "2026-08-10"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "EMPLOYEE_NOT_FOUND"


async def test_hr_can_correct_absence(client: AsyncClient, db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={"employee_id": employee.id, "type": "SICK", "date_from": "2026-08-10", "date_to": "2026-08-10"},
    )
    absence_id = create_response.json()["id"]

    patch_response = await client.patch(
        f"/absences/{absence_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"date_to": "2026-08-12", "note": "Verlängerte Krankmeldung"},
    )

    assert patch_response.status_code == 200
    body = patch_response.json()
    assert body["date_to"] == "2026-08-12"
    assert body["note"] == "Verlängerte Krankmeldung"
    assert body["type"] == "SICK"


async def test_correct_absence_rejects_invalid_range(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_employee(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={"employee_id": employee.id, "type": "SICK", "date_from": "2026-08-10", "date_to": "2026-08-12"},
    )
    absence_id = create_response.json()["id"]

    patch_response = await client.patch(
        f"/absences/{absence_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"date_to": "2026-08-09"},
    )

    assert patch_response.status_code == 400
    assert patch_response.json()["code"] == "INVALID_RANGE"


async def test_hr_can_delete_absence(client: AsyncClient, db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={"employee_id": employee.id, "type": "VACATION", "date_from": "2026-08-10", "date_to": "2026-08-10"},
    )
    absence_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/absences/{absence_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert delete_response.status_code == 204

    list_response = await client.get(
        f"/employees/{employee.id}/absences", headers={"Authorization": f"Bearer {token}"}
    )
    assert list_response.json() == []


async def test_delete_unknown_absence(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.delete(
        "/absences/999", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "ABSENCE_NOT_FOUND"
