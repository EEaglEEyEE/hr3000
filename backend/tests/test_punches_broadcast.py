from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BreakRule, Device, Employee, EmployeeDefaultShift, Location, ShiftTemplate
from app.services import ws_manager
from app.services.pairing_service import token_hash

_WEEKDAYS_MO_FR = 0b0011111


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
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


async def _assign_default_shift(db_session: AsyncSession, employee: Employee, target_minutes: int) -> None:
    template = ShiftTemplate(name="Normalschicht", target_minutes=target_minutes)
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    db_session.add(
        EmployeeDefaultShift(
            employee_id=employee.id,
            shift_template_id=template.id,
            valid_from=date(2026, 1, 1),
            weekdays_mask=_WEEKDAYS_MO_FR,
        )
    )
    await db_session.commit()


async def _device_token(client: AsyncClient, raw_token: str) -> str:
    response = await client.post("/auth/device/login", json={"device_token": raw_token})
    return response.json()["access_token"]


async def test_creating_punch_broadcasts_balance_to_location(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    db_session.add_all(
        [
            BreakRule(min_work_minutes=360, deduct_minutes=30),
            BreakRule(min_work_minutes=540, deduct_minutes=45),
        ]
    )
    await db_session.commit()
    # 2026-08-10 ist ein Montag -> mit target_minutes=480 (8 Std.) pro Tag.
    await _assign_default_shift(db_session, employee, target_minutes=480)
    # Das Überstundenkonto zählt jeden Soll-Tag bis heute – damit der Test nicht vom Datum
    # abhängt, endet das Beschäftigungsverhältnis am Testtag.
    employee.termination_date = date(2026, 8, 10)
    await db_session.commit()
    token = await _device_token(client, "device-1")

    broadcasts: list[tuple[int, dict]] = []

    async def fake_broadcast(location_id: int, message: dict) -> None:
        broadcasts.append((location_id, message))

    monkeypatch.setattr(ws_manager.manager, "broadcast", fake_broadcast)

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
            "timestamp_utc": "2026-08-10T14:00:00Z",
            "idempotency_key": "22222222-2222-2222-2222-222222222222",
        },
    )
    assert response.status_code == 201

    assert len(broadcasts) == 2
    location_id, message = broadcasts[-1]
    assert location_id == location.id
    assert message["type"] == "OVERTIME_BALANCE_UPDATED"
    assert message["employee_id"] == employee.id
    assert message["status"] == "COMPLETE"
    assert message["actual_minutes"] == 480 - 30
    assert message["running_balance_minutes"] == (480 - 30) - 480
