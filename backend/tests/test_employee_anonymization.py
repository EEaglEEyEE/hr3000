from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_hr_user(db_session: AsyncSession, role: HrRole = HrRole.ADMIN) -> HrUser:
    user = HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})
    return response.json()["access_token"]


async def _create_departed_employee(client: AsyncClient, token: str, location: Location) -> int:
    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-42",
            "login_email": "erika@example.com",
            "password": "secret123",
            "pin": "1234",
            "nfc_uid": "04:AA:BB:CC",
            "birth_date": "1990-05-20",
            "termination_date": "2026-01-01",
        },
    )
    return create_response.json()["id"]


async def test_anonymize_overwrites_pii_and_keeps_employee_number(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _token(client)
    employee_id = await _create_departed_employee(client, token, location)

    response = await client.post(
        f"/employees/{employee_id}/anonymize", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["first_name"] == "Anonymisiert"
    assert body["last_name"] == f"Mitarbeiter {employee_id}"
    assert body["employee_number"] == "EMP-42"
    assert body["login_email"] is None
    assert body["has_pin"] is False
    assert body["nfc_uid"] is None
    assert body["birth_date"] is None
    assert body["active"] is False
    assert body["anonymized_at"] is not None


async def test_anonymize_twice_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _token(client)
    employee_id = await _create_departed_employee(client, token, location)

    await client.post(f"/employees/{employee_id}/anonymize", headers={"Authorization": f"Bearer {token}"})
    response = await client.post(
        f"/employees/{employee_id}/anonymize", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "ALREADY_ANONYMIZED"


async def test_anonymize_requires_termination_date(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _token(client)

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Max",
            "last_name": "Mustermann",
            "employee_number": "EMP-1",
        },
    )
    employee_id = create_response.json()["id"]

    response = await client.post(
        f"/employees/{employee_id}/anonymize", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "EMPLOYEE_NOT_TERMINATED"


async def test_hr_role_cannot_anonymize(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)

    hr_user = HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(hr_user)
    await db_session.commit()

    admin_token = await _token(client)
    employee_id = await _create_departed_employee(client, admin_token, location)

    hr_login = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    hr_token = hr_login.json()["access_token"]

    response = await client.post(
        f"/employees/{employee_id}/anonymize", headers={"Authorization": f"Bearer {hr_token}"}
    )

    assert response.status_code == 403


async def test_anonymization_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _token(client)
    employee_id = await _create_departed_employee(client, token, location)

    await client.post(f"/employees/{employee_id}/anonymize", headers={"Authorization": f"Bearer {token}"})

    log_response = await client.get("/audit-log", headers={"Authorization": f"Bearer {token}"})
    entries = log_response.json()
    entry = next(e for e in entries if e["action"] == "EMPLOYEE_ANONYMIZED")
    assert entry["entity_type"] == "employee"
    assert entry["entity_id"] == employee_id
    assert "Erika Musterfrau (EMP-42)" in entry["detail"]
