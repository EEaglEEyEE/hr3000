from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location, SupervisorTeamAssignment, Team
from absence_helpers import require_vacation_approval
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_self_service_employee(
    db_session: AsyncSession, location: Location, team_id: int | None = None
) -> Employee:
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


async def _create_admin_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_supervisor_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="supervisor@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _employee_token(client: AsyncClient) -> str:
    response = await client.post(
        "/auth/login", json={"email": "erika@example.com", "password": "pw123456"}
    )
    return response.json()["access_token"]


async def _hr_token(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": "pw"})
    return response.json()["access_token"]


async def _request_pending_vacation(client: AsyncClient, employee_id: int, day: str = "2026-08-10") -> None:
    token = await _employee_token(client)
    await client.post(
        "/absences",
        headers={"Authorization": f"Bearer {token}"},
        json={"employee_id": employee_id, "type": "VACATION", "date_from": day, "date_to": day},
    )


async def test_absence_request_notifies_teams_supervisor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    team = Team(name="Team Nord", location_id=location.id)
    db_session.add(team)
    await db_session.commit()
    await db_session.refresh(team)

    supervisor = await _create_supervisor_hr_user(db_session)
    db_session.add(SupervisorTeamAssignment(team_id=team.id, account_id=supervisor.id))
    employee = await _create_self_service_employee(db_session, location, team_id=team.id)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()

    await _request_pending_vacation(client, employee.id)

    supervisor_token = await _hr_token(client, "supervisor@example.com")
    response = await client.get("/notifications", headers={"Authorization": f"Bearer {supervisor_token}"})
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 1
    assert entries[0]["type"] == "ABSENCE_REQUESTED"
    assert "Erika Muster" in entries[0]["message"]
    assert entries[0]["read_at"] is None


async def test_absence_request_falls_back_to_admin_without_team(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_self_service_employee(db_session, location)
    await _create_admin_hr_user(db_session)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()

    await _request_pending_vacation(client, employee.id)

    admin_token = await _hr_token(client, "admin@example.com")
    response = await client.get("/notifications", headers={"Authorization": f"Bearer {admin_token}"})
    entries = response.json()
    assert len(entries) == 1
    assert entries[0]["type"] == "ABSENCE_REQUESTED"


async def test_absence_decision_notifies_requesting_employee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
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
    await client.patch(
        f"/absences/{absence_id}/decide",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"approve": True},
    )

    response = await client.get("/notifications", headers={"Authorization": f"Bearer {employee_token}"})
    entries = response.json()
    decided = [e for e in entries if e["type"] == "ABSENCE_DECIDED"]
    assert len(decided) == 1
    assert "genehmigt" in decided[0]["message"]


async def test_notifications_are_scoped_to_recipient(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_self_service_employee(db_session, location)
    await _create_admin_hr_user(db_session)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()

    await _request_pending_vacation(client, employee.id)

    employee_token = await _employee_token(client)
    response = await client.get("/notifications", headers={"Authorization": f"Bearer {employee_token}"})
    assert response.json() == []


async def test_mark_notification_read_and_read_all(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_self_service_employee(db_session, location)
    await _create_admin_hr_user(db_session)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()

    await _request_pending_vacation(client, employee.id)
    await _request_pending_vacation(client, employee.id, "2026-08-11")  # sich überschneidende Anträge sind nicht erlaubt

    admin_token = await _hr_token(client, "admin@example.com")
    list_response = await client.get("/notifications", headers={"Authorization": f"Bearer {admin_token}"})
    entries = list_response.json()
    assert len(entries) == 2

    read_response = await client.patch(
        f"/notifications/{entries[0]['id']}/read", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert read_response.status_code == 200
    assert read_response.json()["read_at"] is not None

    mark_all_response = await client.patch(
        "/notifications/read-all", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert mark_all_response.status_code == 204

    final_list = await client.get("/notifications", headers={"Authorization": f"Bearer {admin_token}"})
    assert all(entry["read_at"] is not None for entry in final_list.json())


async def test_cannot_mark_other_recipients_notification_as_read(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_self_service_employee(db_session, location)
    await _create_admin_hr_user(db_session)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()

    await _request_pending_vacation(client, employee.id)

    admin_token = await _hr_token(client, "admin@example.com")
    notifications = await client.get("/notifications", headers={"Authorization": f"Bearer {admin_token}"})
    notification_id = notifications.json()[0]["id"]

    employee_token = await _employee_token(client)
    response = await client.patch(
        f"/notifications/{notification_id}/read", headers={"Authorization": f"Bearer {employee_token}"}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOTIFICATION_NOT_FOUND"
