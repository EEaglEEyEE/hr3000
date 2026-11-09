from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HrRole, Account, Location
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_hr_user(db_session: AsyncSession, role: HrRole = HrRole.HR) -> Account:
    user = Account(email="hr@example.com", password_hash=hash_password("pw"), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_data_export_bundles_all_employee_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-42",
        },
    )
    employee_id = create_response.json()["id"]

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee_id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "aaaaaaaa-2222-2222-2222-222222222222",
        },
    )
    await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee_id,
            "type": "VACATION",
            "date_from": "2026-09-01",
            "date_to": "2026-09-05",
        },
    )
    await client.patch(
        f"/employees/{employee_id}/leave-entitlement?year=2026",
        headers={"Authorization": f"Bearer {token}"},
        json={"entitled_days": 30},
    )

    response = await client.get(
        f"/employees/{employee_id}/data-export", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]

    body = response.json()
    assert body["employee"]["id"] == employee_id
    assert body["employee"]["first_name"] == "Erika"
    assert len(body["punches"]) == 1
    assert body["punches"][0]["punch_type"] == "COME"
    assert len(body["absences"]) == 1
    assert body["absences"][0]["type"] == "VACATION"
    assert len(body["leave_entitlements"]) == 1
    assert body["leave_entitlements"][0]["entitled_days"] == 30
    assert body["default_shifts"] == []
    assert body["shift_plan_entries"] == []
    assert body["notifications"] == []
    assert "exported_at" in body


async def test_data_export_unknown_employee(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.get("/employees/999/data-export", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert response.json()["code"] == "EMPLOYEE_NOT_FOUND"


async def test_data_export_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-42",
        },
    )
    employee_id = create_response.json()["id"]

    await client.get(f"/employees/{employee_id}/data-export", headers={"Authorization": f"Bearer {token}"})

    log_response = await client.get("/audit-log", headers={"Authorization": f"Bearer {token}"})
    entries = log_response.json()
    entry = next(e for e in entries if e["action"] == "EMPLOYEE_DATA_EXPORTED")
    assert entry["entity_type"] == "employee"
    assert entry["entity_id"] == employee_id
    assert "Erika Musterfrau" in entry["detail"]


async def test_supervisor_cannot_export_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.models import Employee, Team

    location = await _create_location(db_session)
    other_team = Team(name="Anderes Team")
    db_session.add(other_team)
    await db_session.commit()
    await db_session.refresh(other_team)

    employee = Employee(
        location_id=location.id,
        team_id=other_team.id,
        first_name="Fremd",
        last_name="Mitarbeiter",
        employee_number="EMP-99",
    )
    db_session.add(employee)
    await _create_hr_user(db_session, role=HrRole.SUPERVISOR)
    await db_session.commit()
    await db_session.refresh(employee)
    token = await _hr_token(client)

    response = await client.get(
        f"/employees/{employee.id}/data-export", headers={"Authorization": f"Bearer {token}"}
    )

    # Der Export enthält die Personalakte -> nur Admin/HR, Supervisor generell nicht.
    assert response.status_code == 403
