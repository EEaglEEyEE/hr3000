from datetime import time

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, HrUser, Location, ShiftTemplate, TargetPeriod
from app.services.auth_service import hash_password


async def _create_employee(db_session: AsyncSession) -> Employee:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    employee = Employee(
        location_id=location.id, first_name="Max", last_name="Mustermann", employee_number="EMP-1", active=True
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_template(
    db_session: AsyncSession, target_period: TargetPeriod = TargetPeriod.DAILY
) -> ShiftTemplate:
    template = ShiftTemplate(
        name="Frueh",
        start_time=time(6, 0),
        end_time=time(14, 0),
        target_minutes=480,
        target_period=target_period,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


async def _create_admin_hr_user(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_upsert_workday_entry_defaults_target_minutes_from_template(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_employee(db_session)
    template = await _create_template(db_session)
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    response = await client.put(
        f"/employees/{employee.id}/shift-plan-entries/2026-08-15",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_workday": True, "shift_template_id": template.id},
    )
    assert response.status_code == 200
    assert response.json()["target_minutes"] == 480


async def test_upsert_workday_without_target_or_template_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_employee(db_session)
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    response = await client.put(
        f"/employees/{employee.id}/shift-plan-entries/2026-08-15",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_workday": True},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "TARGET_MINUTES_REQUIRED"


async def test_upsert_rejects_weekly_or_monthly_template(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_employee(db_session)
    weekly_template = await _create_template(db_session, target_period=TargetPeriod.WEEKLY)
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    response = await client.put(
        f"/employees/{employee.id}/shift-plan-entries/2026-08-15",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_workday": True, "shift_template_id": weekly_template.id},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SHIFT_TEMPLATE_NOT_DAILY"


async def test_upsert_rejects_shift_exceeding_max_daily_working_time(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_employee(db_session)
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    long_template = ShiftTemplate(name="Lang", start_time=time(6, 0), end_time=time(22, 0), target_minutes=960)
    db_session.add(long_template)
    await db_session.commit()
    await db_session.refresh(long_template)

    response = await client.put(
        f"/employees/{employee.id}/shift-plan-entries/2026-08-15",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_workday": True, "shift_template_id": long_template.id},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "MAX_DAILY_WORKING_TIME_EXCEEDED"


async def test_upsert_day_off_entry_and_get_list(client: AsyncClient, db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    response = await client.put(
        f"/employees/{employee.id}/shift-plan-entries/2026-08-15",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_workday": False},
    )
    assert response.status_code == 200
    assert response.json()["target_minutes"] is None
    assert response.json()["shift_template_id"] is None

    list_response = await client.get(
        f"/employees/{employee.id}/shift-plan-entries",
        params={"from": "2026-08-01", "to": "2026-08-31"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(list_response.json()) == 1


async def test_effective_shifts_marks_entry_vs_unconfigured(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_employee(db_session)
    template = await _create_template(db_session)
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    await client.put(
        f"/employees/{employee.id}/shift-plan-entries/2026-08-15",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_workday": True, "shift_template_id": template.id},
    )

    response = await client.get(
        f"/employees/{employee.id}/effective-shifts",
        params={"from": "2026-08-14", "to": "2026-08-16"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    days = {day["date"]: day for day in response.json()}

    assert days["2026-08-14"]["plan_exists"] is False
    assert days["2026-08-14"]["from_entry"] is False
    assert days["2026-08-14"]["is_workday"] is True

    assert days["2026-08-15"]["plan_exists"] is True
    assert days["2026-08-15"]["from_entry"] is True
    assert days["2026-08-15"]["shift_template_id"] == template.id
    assert days["2026-08-15"]["target_minutes"] == 480

    assert days["2026-08-16"]["plan_exists"] is False
    assert days["2026-08-16"]["from_entry"] is False


async def test_effective_shifts_rejects_oversized_range(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_employee(db_session)
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    response = await client.get(
        f"/employees/{employee.id}/effective-shifts",
        params={"from": "2026-01-01", "to": "2026-12-31"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "RANGE_TOO_LARGE"


async def test_delete_shift_plan_entry(client: AsyncClient, db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    await client.put(
        f"/employees/{employee.id}/shift-plan-entries/2026-08-15",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_workday": False},
    )

    delete_response = await client.delete(
        f"/employees/{employee.id}/shift-plan-entries/2026-08-15",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_response.status_code == 204

    second_delete = await client.delete(
        f"/employees/{employee.id}/shift-plan-entries/2026-08-15",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second_delete.status_code == 404
