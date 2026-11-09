import os
import sys
from datetime import time

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location, ShiftTemplate, SupervisorTeamAssignment, Team
from app.services.auth_service import hash_password

# WeasyPrint dlopen't Pango/GObject als native Libs (siehe
# shift_plan_pdf_service.py) – auf diesem Entwicklungsrechner (macOS/Homebrew)
# liegen sie nicht auf dem Standard-Ladepfad. Nur für diese Testdatei nötig,
# betrifft die Linux/Docker-Deployment-Umgebung nicht.
if sys.platform == "darwin":
    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")


async def _create_location(db_session: AsyncSession, name: str = "Standort A") -> Location:
    location = Location(name=name, timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(db_session: AsyncSession, location: Location, **kwargs) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name=kwargs.pop("first_name", "Max"),
        last_name=kwargs.pop("last_name", "Mustermann"),
        employee_number=kwargs.pop("employee_number", "EMP-1"),
        active=True,
        **kwargs,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_template(db_session: AsyncSession) -> ShiftTemplate:
    template = ShiftTemplate(name="Frueh", start_time=time(6, 0), end_time=time(14, 0), target_minutes=480)
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


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


async def test_admin_can_export_shift_plan_pdf(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    template = await _create_template(db_session)
    await _create_admin_hr_user(db_session)
    token = await _token(client, "admin@example.com")

    await client.put(
        f"/employees/{employee.id}/shift-plan-entries/2026-08-15",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_workday": True, "shift_template_id": template.id},
    )

    response = await client.get(
        "/shift-plan/pdf",
        params={"employee_ids": [employee.id], "from": "2026-08-14", "to": "2026-08-16"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 0
    assert response.content.startswith(b"%PDF")


async def test_export_rejects_empty_employee_list(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_admin_hr_user(db_session)
    token = await _token(client, "admin@example.com")

    response = await client.get(
        "/shift-plan/pdf",
        params={"from": "2026-08-14", "to": "2026-08-16"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "NO_EMPLOYEES"


async def test_export_unknown_employee_returns_404(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_admin_hr_user(db_session)
    token = await _token(client, "admin@example.com")

    response = await client.get(
        "/shift-plan/pdf",
        params={"employee_ids": [999], "from": "2026-08-14", "to": "2026-08-16"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "EMPLOYEE_NOT_FOUND"


async def test_supervisor_cannot_export_employee_outside_own_team(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    supervisor = await _create_supervisor_hr_user(db_session)

    own_team = Team(name="Team Nord", location_id=location.id)
    other_team = Team(name="Team Sued", location_id=location.id)
    db_session.add_all([own_team, other_team])
    await db_session.commit()
    await db_session.refresh(own_team)
    await db_session.refresh(other_team)

    db_session.add(SupervisorTeamAssignment(team_id=own_team.id, account_id=supervisor.id))
    await db_session.commit()

    own_employee = await _create_employee(
        db_session, location, first_name="Erika", employee_number="EMP-OWN", team_id=own_team.id
    )
    other_employee = await _create_employee(
        db_session, location, first_name="Otto", employee_number="EMP-OTHER", team_id=other_team.id
    )

    token = await _token(client, "supervisor@example.com")

    own_export = await client.get(
        "/shift-plan/pdf",
        params={"employee_ids": [own_employee.id], "from": "2026-08-14", "to": "2026-08-16"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert own_export.status_code == 200

    other_export = await client.get(
        "/shift-plan/pdf",
        params={"employee_ids": [other_employee.id], "from": "2026-08-14", "to": "2026-08-16"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert other_export.status_code == 404
    assert other_export.json()["code"] == "EMPLOYEE_NOT_FOUND"


async def test_export_rejects_oversized_range(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_admin_hr_user(db_session)
    token = await _token(client, "admin@example.com")

    response = await client.get(
        "/shift-plan/pdf",
        params={"employee_ids": [employee.id], "from": "2026-01-01", "to": "2026-12-31"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "RANGE_TOO_LARGE"
