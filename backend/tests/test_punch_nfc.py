from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, HrRole, Account, Location
from app.services.pairing_service import token_hash


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(
    db_session: AsyncSession,
    location: Location,
    nfc_uid: str | None,
    employee_number: str = "EMP-1",
) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Mustermann",
        employee_number=employee_number,
        active=True,
        nfc_uid=nfc_uid,
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


async def _create_admin(db_session: AsyncSession) -> Account:
    user = Account(email="admin@example.com", password_hash="x", role=HrRole.ADMIN)
    from app.services.auth_service import hash_password

    user.password_hash = hash_password("pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _admin_token(client: AsyncClient) -> str:
    response = await client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "pw"}
    )
    return response.json()["access_token"]


async def _device_login(client: AsyncClient, raw_token: str) -> dict:
    response = await client.post("/auth/device/login", json={"device_token": raw_token})
    return response.json()


async def _enable_pin_requirement(client: AsyncClient, admin_token: str) -> None:
    await client.patch(
        "/settings",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"require_pin_for_punch": True},
    )


async def test_punch_with_matching_nfc_card_succeeds_without_pin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, nfc_uid="04:AA:BB:CC")
    await _create_device(db_session, location, "device-1")
    await _create_admin(db_session)
    admin_token = await _admin_token(client)
    await _enable_pin_requirement(client, admin_token)
    device_login = await _device_login(client, "device-1")

    response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_login['access_token']}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "11111111-1111-1111-1111-111111111111",
            "nfc_uid": "04:AA:BB:CC",
        },
    )

    assert response.status_code == 201


async def test_punch_with_wrong_nfc_card_falls_back_to_pin_check(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, nfc_uid="04:AA:BB:CC")
    await _create_device(db_session, location, "device-1")
    await _create_admin(db_session)
    admin_token = await _admin_token(client)
    await _enable_pin_requirement(client, admin_token)
    device_login = await _device_login(client, "device-1")

    response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_login['access_token']}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "22222222-2222-2222-2222-222222222222",
            "nfc_uid": "04:WRONG",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "PIN_NOT_CONFIGURED"


async def test_punch_with_nfc_card_of_another_employee_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, nfc_uid=None, employee_number="EMP-1")
    await _create_employee(db_session, location, nfc_uid="04:AA:BB:CC", employee_number="EMP-2")
    await _create_device(db_session, location, "device-1")
    await _create_admin(db_session)
    admin_token = await _admin_token(client)
    await _enable_pin_requirement(client, admin_token)
    device_login = await _device_login(client, "device-1")

    response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_login['access_token']}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "33333333-3333-3333-3333-333333333333",
            "nfc_uid": "04:AA:BB:CC",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "PIN_NOT_CONFIGURED"


async def test_location_employees_report_nfc_uid(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_employee(db_session, location, nfc_uid="04:AA:BB:CC")
    await _create_device(db_session, location, "device-1")
    device_login = await _device_login(client, "device-1")

    response = await client.get(
        f"/locations/{location.id}/employees",
        headers={"Authorization": f"Bearer {device_login['access_token']}"},
    )

    assert response.status_code == 200
    row = response.json()[0]
    # Tablets bekommen den Chip nur als Hash: SHA-256(card_salt + normalisierte UID)
    import hashlib

    assert row["nfc_uid"] is None
    assert row["card_hash"] == hashlib.sha256(f"{device_login['card_salt']}04aabbcc".encode()).hexdigest()
