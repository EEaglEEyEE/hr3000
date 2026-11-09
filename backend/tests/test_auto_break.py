from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BreakRule, Device, Employee, Location, Punch, PunchSource, PunchType
from app.services.pairing_service import token_hash


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(db_session: AsyncSession, location: Location, auto_break: bool) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Mustermann",
        employee_number="EMP-1",
        active=True,
        auto_break_enabled=auto_break,
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


async def _seed_break_rules(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            BreakRule(min_work_minutes=360, deduct_minutes=30),
            BreakRule(min_work_minutes=540, deduct_minutes=45),
        ]
    )
    await db_session.commit()


async def _device_token(client: AsyncClient, raw_token: str) -> str:
    response = await client.post("/auth/device/login", json={"device_token": raw_token})
    return response.json()["access_token"]


async def test_auto_break_inserted_when_enabled_and_no_manual_break(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, auto_break=True)
    await _create_device(db_session, location, "device-1")
    await _seed_break_rules(db_session)
    token = await _device_token(client, "device-1")

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "11111111-1111-1111-1111-111111111111",
        },
    )
    response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T14:00:00Z",  # 480 min gross -> 30 min Pflichtpause
            "idempotency_key": "22222222-2222-2222-2222-222222222222",
        },
    )
    assert response.status_code == 201

    punches = (
        await db_session.execute(
            select(Punch).where(Punch.employee_id == employee.id).order_by(Punch.timestamp_utc.asc())
        )
    ).scalars().all()

    types = [p.punch_type for p in punches]
    assert types == [PunchType.COME, PunchType.BREAK_START, PunchType.BREAK_END, PunchType.GO]
    auto_punches = [p for p in punches if p.punch_type in (PunchType.BREAK_START, PunchType.BREAK_END)]
    assert all(p.source == PunchSource.AUTO_BREAK for p in auto_punches)
    assert (auto_punches[1].timestamp_utc - auto_punches[0].timestamp_utc).total_seconds() == 30 * 60


async def test_auto_break_not_inserted_when_disabled(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, auto_break=False)
    await _create_device(db_session, location, "device-1")
    await _seed_break_rules(db_session)
    token = await _device_token(client, "device-1")

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "33333333-3333-3333-3333-333333333333",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T14:00:00Z",
            "idempotency_key": "44444444-4444-4444-4444-444444444444",
        },
    )

    punches = (
        await db_session.execute(select(Punch).where(Punch.employee_id == employee.id))
    ).scalars().all()
    assert len(punches) == 2


async def test_auto_break_respects_manually_punched_break(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, auto_break=True)
    await _create_device(db_session, location, "device-1")
    await _seed_break_rules(db_session)
    token = await _device_token(client, "device-1")

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "55555555-5555-5555-5555-555555555555",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "BREAK_START",
            "timestamp_utc": "2026-08-10T10:00:00Z",
            "idempotency_key": "66666666-6666-6666-6666-666666666666",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "BREAK_END",
            "timestamp_utc": "2026-08-10T10:50:00Z",  # 50 Min. manuelle Pause
            "idempotency_key": "77777777-7777-7777-7777-777777777777",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T14:00:00Z",
            "idempotency_key": "88888888-8888-8888-8888-888888888888",
        },
    )

    punches = (
        await db_session.execute(select(Punch).where(Punch.employee_id == employee.id))
    ).scalars().all()
    assert len(punches) == 4  # keine zusätzliche automatische Pause
    assert all(p.source != PunchSource.AUTO_BREAK for p in punches)
