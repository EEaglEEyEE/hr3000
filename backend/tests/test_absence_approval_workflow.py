from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, HrUser, Location, SupervisorTeamAssignment, Team
from absence_helpers import require_vacation_approval
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings
from app.services.timesheet_service import calculate_day, employee_timezone


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_self_service_employee(db_session: AsyncSession, location: Location, team_id: int | None = None) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Erika",
        last_name="Muster",
        employee_number="EMP-SELF",
        active=True,
        login_email="erika@example.com",
        password_hash=hash_password("pw123456"),
        team_id=team_id,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_admin_hr_user(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_supervisor_hr_user(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="supervisor@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _employee_token(client: AsyncClient) -> str:
    response = await client.post(
        "/auth/employee/login", json={"email": "erika@example.com", "password": "pw123456"}
    )
    return response.json()["access_token"]


async def _hr_token(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/hr/login", json={"email": email, "password": "pw"})
    return response.json()["access_token"]


async def test_self_service_request_is_pending_when_approval_required(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_self_service_employee(db_session, location)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()

    token = await _employee_token(client)
    response = await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "type": "VACATION",
            "date_from": "2026-08-10",
            "date_to": "2026-08-14",
        },
    )
    assert response.status_code == 201
    assert response.json()["approval_status"] == "PENDING"


async def test_self_service_request_is_approved_when_approval_not_required(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_self_service_employee(db_session, location)

    token = await _employee_token(client)
    response = await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "type": "VACATION",
            "date_from": "2026-08-10",
            "date_to": "2026-08-14",
        },
    )
    assert response.status_code == 201
    assert response.json()["approval_status"] == "APPROVED"


async def test_pending_vacation_does_not_neutralize_timesheet_day(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_self_service_employee(db_session, location)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()

    token = await _employee_token(client)
    await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={"employee_id": employee.id, "type": "VACATION", "date_from": "2026-08-10", "date_to": "2026-08-10"},
    )

    tz = await employee_timezone(db_session, employee)
    calc = await calculate_day(db_session, employee, date(2026, 8, 10), tz)
    assert calc.status.value == "OPEN_MISSING_PUNCH"


async def test_admin_can_decide_pending_absence(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_self_service_employee(db_session, location)
    await _create_admin_hr_user(db_session)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()

    employee_token = await _employee_token(client)
    create_response = await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {employee_token}"},
        json={"employee_id": employee.id, "type": "VACATION", "date_from": "2026-08-10", "date_to": "2026-08-10"},
    )
    absence_id = create_response.json()["id"]

    admin_token = await _hr_token(client, "admin@example.com")
    decide_response = await client.patch(
        f"/absences/{absence_id}/decide",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"approve": True},
    )
    assert decide_response.status_code == 200
    assert decide_response.json()["approval_status"] == "APPROVED"
    assert decide_response.json()["decided_by"] is not None

    tz = await employee_timezone(db_session, employee)
    calc = await calculate_day(db_session, employee, date(2026, 8, 10), tz)
    assert calc.status.value == "ABSENCE"

    second_decide = await client.patch(
        f"/absences/{absence_id}/decide",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"approve": True},
    )
    assert second_decide.status_code == 400
    assert second_decide.json()["code"] == "NOT_PENDING"


async def test_supervisor_cannot_decide_absence_outside_own_team(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    other_team = Team(name="Team Sued", location_id=location.id)
    db_session.add(other_team)
    await db_session.commit()
    await db_session.refresh(other_team)

    employee = await _create_self_service_employee(db_session, location, team_id=other_team.id)
    supervisor = await _create_supervisor_hr_user(db_session)
    own_team = Team(name="Team Nord", location_id=location.id)
    db_session.add(own_team)
    await db_session.commit()
    await db_session.refresh(own_team)
    db_session.add(SupervisorTeamAssignment(team_id=own_team.id, hr_user_id=supervisor.id))
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()

    employee_token = await _employee_token(client)
    create_response = await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {employee_token}"},
        json={"employee_id": employee.id, "type": "VACATION", "date_from": "2026-08-10", "date_to": "2026-08-10"},
    )
    absence_id = create_response.json()["id"]

    supervisor_token = await _hr_token(client, "supervisor@example.com")
    decide_response = await client.patch(
        f"/absences/{absence_id}/decide",
        headers={"Authorization": f"Bearer {supervisor_token}"},
        json={"approve": True},
    )
    assert decide_response.status_code == 403


async def test_pending_absence_does_not_count_against_leave_entitlement(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_self_service_employee(db_session, location)
    await _create_admin_hr_user(db_session)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()

    employee_token = await _employee_token(client)
    await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {employee_token}"},
        json={"employee_id": employee.id, "type": "VACATION", "date_from": "2026-08-10", "date_to": "2026-08-14"},
    )

    admin_token = await _hr_token(client, "admin@example.com")
    entitlement_response = await client.get(
        f"/employees/{employee.id}/leave-entitlement",
        params={"year": 2026},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert entitlement_response.json()["used_days"] == 0.0


async def test_self_service_requests_can_be_switched_off(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_self_service_employee(db_session, location)
    await _create_admin_hr_user(db_session)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    settings_row.absence_requests_enabled = False
    await db_session.commit()
    body = {"employee_id": employee.id, "type": "VACATION", "date_from": "2026-08-10", "date_to": "2026-08-14"}

    token = await _employee_token(client)
    response = await client.post("/absences", headers={"Authorization": f"Bearer {token}"}, json=body)
    assert response.status_code == 403 and response.json()["code"] == "ABSENCE_REQUESTS_DISABLED"
    dashboard = (await client.get("/dashboard", headers={"Authorization": f"Bearer {token}"})).json()
    assert dashboard["absence_requests_enabled"] is False

    # HR trägt weiterhin direkt ein.
    admin = await _hr_token(client, "admin@example.com")
    response = await client.post("/absences", headers={"Authorization": f"Bearer {admin}"}, json=body)
    assert response.status_code == 201
    features = (await client.get("/features", headers={"Authorization": f"Bearer {admin}"})).json()
    assert features["absence_requests_enabled"] is False
