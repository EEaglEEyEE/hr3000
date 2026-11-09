from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, HrRole, Account, Location
from app.services.auth_service import hash_password
from app.services.pairing_service import token_hash


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="Europe/Berlin")
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


async def _create_device(db_session: AsyncSession, location: Location, token: str) -> Device:
    device = Device(location_id=location.id, token_hash=token_hash(token), name="Kiosk A1")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


async def _create_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _device_token(client: AsyncClient, raw_token: str) -> str:
    response = await client.post("/auth/device/login", json={"device_token": raw_token})
    return response.json()["access_token"]


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_kiosk_can_create_punch(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    token = await _device_token(client, "device-1")

    response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "11111111-1111-1111-1111-111111111111",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "KIOSK"
    assert body["employee_id"] == employee.id
    assert body["location_id"] == location.id
    assert body["corrected"] is False


async def test_duplicate_idempotency_key_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    token = await _device_token(client, "device-1")

    payload = {
        "employee_id": employee.id,
        "punch_type": "COME",
        "timestamp_utc": "2026-08-10T06:00:00Z",
        "idempotency_key": "22222222-2222-2222-2222-222222222222",
    }
    first = await client.post(
        "/punches", headers={"Authorization": f"Bearer {token}"}, json=payload
    )
    second = await client.post(
        "/punches", headers={"Authorization": f"Bearer {token}"}, json=payload
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {"detail": "Diese Stempelung wurde bereits erfasst.", "code": "PUNCH_DUPLICATE"}


async def test_hr_can_backfill_missing_punch(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T15:00:00Z",
            "idempotency_key": "33333333-3333-3333-3333-333333333333",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "MANUAL_HR"
    assert body["device_id"] is None


async def test_create_punch_unknown_employee(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_device(db_session, location, "device-1")
    token = await _device_token(client, "device-1")

    response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": 999,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "44444444-4444-4444-4444-444444444444",
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "EMPLOYEE_NOT_FOUND"


async def test_hr_can_list_and_correct_punch(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    device_token = await _device_token(client, "device-1")
    hr_token = await _hr_token(client)

    create_response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "55555555-5555-5555-5555-555555555555",
        },
    )
    punch_id = create_response.json()["id"]

    list_response = await client.get(
        f"/employees/{employee.id}/punches", headers={"Authorization": f"Bearer {hr_token}"}
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    patch_response = await client.patch(
        f"/punches/{punch_id}",
        headers={"Authorization": f"Bearer {hr_token}"},
        json={"timestamp_utc": "2026-08-10T06:05:00Z", "correction_reason": "Kiosk-Uhr war falsch gestellt"},
    )
    assert patch_response.status_code == 200
    body = patch_response.json()
    assert body["corrected"] is True
    assert body["correction_reason"] == "Kiosk-Uhr war falsch gestellt"
    assert body["timestamp_utc"].startswith("2026-08-10T06:05:00")


async def test_hr_can_delete_duplicate_punch(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    device_token = await _device_token(client, "device-1")
    hr_token = await _hr_token(client)

    # Versehentlich doppelt gestempeltes "Kommen".
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "66666666-6666-6666-6666-666666666666",
        },
    )
    duplicate = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:01:00Z",
            "idempotency_key": "77777777-7777-7777-7777-777777777777",
        },
    )
    duplicate_id = duplicate.json()["id"]

    delete_response = await client.delete(
        f"/punches/{duplicate_id}", headers={"Authorization": f"Bearer {hr_token}"}
    )
    assert delete_response.status_code == 204

    list_response = await client.get(
        f"/employees/{employee.id}/punches", headers={"Authorization": f"Bearer {hr_token}"}
    )
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] != duplicate_id


async def test_delete_unknown_punch_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)
    hr_token = await _hr_token(client)

    response = await client.delete("/punches/999", headers={"Authorization": f"Bearer {hr_token}"})

    assert response.status_code == 404
    assert response.json()["code"] == "PUNCH_NOT_FOUND"


async def test_kiosk_cannot_delete_punch(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    device_token = await _device_token(client, "device-1")

    create_response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "88888888-8888-8888-8888-888888888888",
        },
    )
    punch_id = create_response.json()["id"]

    response = await client.delete(
        f"/punches/{punch_id}", headers={"Authorization": f"Bearer {device_token}"}
    )

    assert response.status_code == 403


async def test_kiosk_cannot_list_punches(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    token = await _device_token(client, "device-1")

    response = await client.get(
        "/employees/1/punches", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"
