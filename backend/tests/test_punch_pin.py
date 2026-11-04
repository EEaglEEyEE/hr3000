from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(db_session: AsyncSession, location: Location, pin: str | None) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Mustermann",
        employee_number="EMP-1",
        active=True,
        pin_hash=hash_password(pin) if pin else None,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_device(db_session: AsyncSession, location: Location, token: str) -> Device:
    device = Device(location_id=location.id, device_token=token, name="Kiosk A1")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


async def _create_admin(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _admin_token(client: AsyncClient) -> str:
    response = await client.post(
        "/auth/hr/login", json={"email": "admin@example.com", "password": "pw"}
    )
    return response.json()["access_token"]


async def _device_login(client: AsyncClient, raw_token: str) -> str:
    response = await client.post("/auth/device/login", json={"device_token": raw_token})
    return response.json()


async def _enable_pin_requirement(client: AsyncClient, admin_token: str) -> None:
    await client.patch(
        "/settings",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"require_pin_for_punch": True},
    )


async def test_device_login_reports_require_pin_flag(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_device(db_session, location, "device-1")
    await _create_admin(db_session)
    admin_token = await _admin_token(client)
    await _enable_pin_requirement(client, admin_token)

    login = await _device_login(client, "device-1")

    assert login["require_pin"] is True


async def test_punch_with_correct_pin_succeeds_when_required(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, pin="1234")
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
            "pin": "1234",
        },
    )

    assert response.status_code == 201


async def test_punch_with_wrong_pin_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, pin="1234")
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
            "pin": "0000",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "PIN_INVALID"


async def test_punch_without_pin_rejected_when_required(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, pin="1234")
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
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "PIN_INVALID"


async def test_punch_rejected_when_employee_has_no_pin_configured(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, pin=None)
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
            "idempotency_key": "44444444-4444-4444-4444-444444444444",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "PIN_NOT_CONFIGURED"


async def test_punch_without_pin_succeeds_when_not_required(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, pin="1234")
    await _create_device(db_session, location, "device-1")
    device_login = await _device_login(client, "device-1")

    response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_login['access_token']}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "55555555-5555-5555-5555-555555555555",
        },
    )

    assert response.status_code == 201
