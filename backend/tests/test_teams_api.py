from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location, SupervisorTeamAssignment, Team
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession, name: str = "Standort A") -> Location:
    location = Location(name=name, timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


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


async def _token(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": "pw"})
    return response.json()["access_token"]


async def test_admin_can_create_and_list_teams(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_admin_hr_user(db_session)
    token = await _token(client, "admin@example.com")

    create_response = await client.post(
        "/teams",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Team Nord", "location_id": location.id},
    )
    assert create_response.status_code == 201

    list_response = await client.get("/teams", headers={"Authorization": f"Bearer {token}"})
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


async def test_team_can_be_created_and_updated_without_location(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    await _create_admin_hr_user(db_session)
    token = await _token(client, "admin@example.com")

    create_response = await client.post(
        "/teams",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Standortübergreifendes Team"},
    )
    assert create_response.status_code == 201
    assert create_response.json()["location_id"] is None
    team_id = create_response.json()["id"]

    assign_location = await client.patch(
        f"/teams/{team_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": location.id},
    )
    assert assign_location.json()["location_id"] == location.id

    clear_location = await client.patch(
        f"/teams/{team_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"clear_location_id": True},
    )
    assert clear_location.json()["location_id"] is None


async def test_supervisor_cannot_create_team(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_supervisor_hr_user(db_session)
    token = await _token(client, "supervisor@example.com")

    response = await client.post(
        "/teams",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Team Nord", "location_id": location.id},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "HR_PERMISSION_REQUIRED"


async def test_supervisor_only_sees_own_team_and_its_employees(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    admin = await _create_admin_hr_user(db_session)
    supervisor = await _create_supervisor_hr_user(db_session)
    admin_token = await _token(client, "admin@example.com")

    own_team = Team(name="Team Nord", location_id=location.id)
    other_team = Team(name="Team Sued", location_id=location.id)
    db_session.add_all([own_team, other_team])
    await db_session.commit()
    await db_session.refresh(own_team)
    await db_session.refresh(other_team)

    db_session.add(SupervisorTeamAssignment(team_id=own_team.id, account_id=supervisor.id))
    own_employee = Employee(
        location_id=location.id,
        first_name="Erika",
        last_name="Muster",
        employee_number="EMP-OWN",
        active=True,
        team_id=own_team.id,
    )
    other_employee = Employee(
        location_id=location.id,
        first_name="Otto",
        last_name="Fremd",
        employee_number="EMP-OTHER",
        active=True,
        team_id=other_team.id,
    )
    db_session.add_all([own_employee, other_employee])
    await db_session.commit()
    await db_session.refresh(own_employee)
    await db_session.refresh(other_employee)

    supervisor_token = await _token(client, "supervisor@example.com")

    teams_response = await client.get("/teams", headers={"Authorization": f"Bearer {supervisor_token}"})
    assert [t["id"] for t in teams_response.json()] == [own_team.id]

    employees_response = await client.get(
        "/employees", headers={"Authorization": f"Bearer {supervisor_token}"}
    )
    assert {e["id"] for e in employees_response.json()} == {own_employee.id}

    own_get = await client.get(
        f"/employees/{own_employee.id}", headers={"Authorization": f"Bearer {supervisor_token}"}
    )
    assert own_get.status_code == 200

    other_get = await client.get(
        f"/employees/{other_employee.id}", headers={"Authorization": f"Bearer {supervisor_token}"}
    )
    assert other_get.status_code == 404
    assert other_get.json()["code"] == "EMPLOYEE_NOT_FOUND"

    # Admin sieht weiterhin alles, unabhaengig von Team-Zuordnung.
    admin_employees = await client.get("/employees", headers={"Authorization": f"Bearer {admin_token}"})
    assert {e["id"] for e in admin_employees.json()} == {own_employee.id, other_employee.id}
