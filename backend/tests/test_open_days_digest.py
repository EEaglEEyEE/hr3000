from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, HrRole, Account, Location
from app.services.auth_service import hash_password
from app.services.pairing_service import token_hash


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(db_session: AsyncSession, location: Location) -> Employee:
    employee = Employee(location_id=location.id, first_name="Max", last_name="Mustermann", employee_number="EMP-1")
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


async def _create_hr_user(db_session: AsyncSession, role: HrRole = HrRole.ADMIN) -> Account:
    user = Account(email="admin@example.com", password_hash=hash_password("pw"), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})
    return response.json()["access_token"]


async def _device_token(client: AsyncClient, raw_token: str) -> str:
    response = await client.post("/auth/device/login", json={"device_token": raw_token})
    return response.json()["access_token"]


async def _create_open_day(client: AsyncClient, device_token: str, employee_id: int) -> None:
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee_id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T14:00:00Z",
            "idempotency_key": "88888888-8888-8888-8888-888888888888",
        },
    )


async def test_open_days_view_creates_digest_notification(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    device_token = await _device_token(client, "device-1")
    hr_token = await _hr_token(client)

    await _create_open_day(client, device_token, employee.id)

    open_days_response = await client.get(
        "/timesheet/open-days", headers={"Authorization": f"Bearer {hr_token}"}
    )
    assert len(open_days_response.json()) == 1

    notifications_response = await client.get(
        "/notifications", headers={"Authorization": f"Bearer {hr_token}"}
    )
    notifications = notifications_response.json()
    digest_entries = [n for n in notifications if n["type"] == "OPEN_DAYS_DIGEST"]
    assert len(digest_entries) == 1
    assert "1 Tag(e)" in digest_entries[0]["message"]


async def test_open_days_digest_sent_at_most_once_per_day(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    device_token = await _device_token(client, "device-1")
    hr_token = await _hr_token(client)

    await _create_open_day(client, device_token, employee.id)

    await client.get("/timesheet/open-days", headers={"Authorization": f"Bearer {hr_token}"})
    await client.get("/timesheet/open-days", headers={"Authorization": f"Bearer {hr_token}"})
    await client.get("/timesheet/open-days", headers={"Authorization": f"Bearer {hr_token}"})

    notifications_response = await client.get(
        "/notifications", headers={"Authorization": f"Bearer {hr_token}"}
    )
    digest_entries = [n for n in notifications_response.json() if n["type"] == "OPEN_DAYS_DIGEST"]
    assert len(digest_entries) == 1


async def test_no_digest_when_no_open_days(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    hr_token = await _hr_token(client)

    await client.get("/timesheet/open-days", headers={"Authorization": f"Bearer {hr_token}"})

    notifications_response = await client.get(
        "/notifications", headers={"Authorization": f"Bearer {hr_token}"}
    )
    assert notifications_response.json() == []


async def test_supervisor_view_does_not_trigger_digest(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    device_token = await _device_token(client, "device-1")

    await _create_open_day(client, device_token, employee.id)

    supervisor = Account(email="super@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR)
    db_session.add(supervisor)
    await db_session.commit()
    supervisor_login = await client.post(
        "/auth/login", json={"email": "super@example.com", "password": "pw"}
    )
    supervisor_token = supervisor_login.json()["access_token"]

    await client.get(
        "/timesheet/open-days", headers={"Authorization": f"Bearer {supervisor_token}"}
    )

    admin_token = await _hr_token(client)
    notifications_response = await client.get(
        "/notifications", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert notifications_response.json() == []
