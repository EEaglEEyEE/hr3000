from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Absence, AbsenceApprovalStatus, AbsenceType, Employee, HrRole, Account, Location
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(db_session: AsyncSession, location: Location) -> Employee:
    employee = Employee(
        location_id=location.id, first_name="Max", last_name="Mustermann", employee_number="EMP-1", active=True
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_hr_user(db_session: AsyncSession, role: HrRole = HrRole.ADMIN) -> Account:
    user = Account(email="admin@example.com", password_hash=hash_password("pw"), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _token(client: AsyncClient, email: str = "admin@example.com") -> str:
    response = await client.post("/auth/login", json={"email": email, "password": "pw"})
    return response.json()["access_token"]


async def test_punch_correction_and_deletion_are_audited(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _token(client)

    create_response = await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "aaaaaaaa-1111-1111-1111-111111111111",
        },
    )
    punch_id = create_response.json()["id"]

    await client.patch(
        f"/punches/{punch_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"correction_reason": "Testkorrektur"},
    )
    await client.delete(f"/punches/{punch_id}", headers={"Authorization": f"Bearer {token}"})

    log_response = await client.get("/audit-log", headers={"Authorization": f"Bearer {token}"})
    assert log_response.status_code == 200
    entries = log_response.json()
    actions = [(e["action"], e["entity_type"], e["entity_id"]) for e in entries]
    assert ("PUNCH_CORRECTED", "punch", punch_id) in actions
    assert ("PUNCH_DELETED", "punch", punch_id) in actions

    corrected_entry = next(e for e in entries if e["action"] == "PUNCH_CORRECTED")
    assert corrected_entry["detail"] == "Testkorrektur"
    assert corrected_entry["actor_label"] == "admin@example.com"


async def test_hr_role_change_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _token(client)

    await client.patch(
        f"/employees/{employee.id}/hr-role",
        headers={"Authorization": f"Bearer {token}"},
        json={"hr_role": "HR"},
    )

    log_response = await client.get("/audit-log", headers={"Authorization": f"Bearer {token}"})
    entries = log_response.json()
    entry = next(e for e in entries if e["action"] == "EMPLOYEE_HR_ROLE_CHANGED")
    assert entry["entity_type"] == "employee"
    assert entry["entity_id"] == employee.id
    assert "keine -> HR" in entry["detail"]


async def test_absence_decision_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _token(client)

    # Direkt als PENDING angelegt (statt über POST /absences), da eine von
    # HR/Admin selbst erstellte Absenz immer sofort APPROVED wird (siehe
    # create_absence) – hier interessiert nur der Audit-Hook von decide_absence.
    absence = Absence(
        employee_id=employee.id,
        type=AbsenceType.VACATION,
        date_from=date(2026, 8, 10),
        date_to=date(2026, 8, 10),
        approval_status=AbsenceApprovalStatus.PENDING,
    )
    db_session.add(absence)
    await db_session.commit()
    await db_session.refresh(absence)
    absence_id = absence.id

    await client.patch(
        f"/absences/{absence_id}/decide",
        headers={"Authorization": f"Bearer {token}"},
        json={"approve": True},
    )

    log_response = await client.get("/audit-log", headers={"Authorization": f"Bearer {token}"})
    entries = log_response.json()
    entry = next(e for e in entries if e["action"] == "ABSENCE_DECIDED")
    assert entry["entity_type"] == "absence"
    assert entry["entity_id"] == absence_id
    assert "Genehmigt" in entry["detail"]


async def test_audit_log_filters_by_entity_type(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _token(client)

    await client.patch(
        f"/employees/{employee.id}/hr-role",
        headers={"Authorization": f"Bearer {token}"},
        json={"hr_role": "HR"},
    )

    response = await client.get(
        "/audit-log", params={"entity_type": "punch"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.json() == []

    response = await client.get(
        "/audit-log", params={"entity_type": "employee"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert len(response.json()) == 1


async def test_supervisor_cannot_read_audit_log(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session, role=HrRole.SUPERVISOR)
    token = await _token(client)

    response = await client.get("/audit-log", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["code"] == "HR_PERMISSION_REQUIRED"


async def test_employee_creation_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _token(client)

    create_response = await client.post(
        "/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location.id,
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "employee_number": "EMP-NEW",
        },
    )
    employee_id = create_response.json()["id"]

    log_response = await client.get("/audit-log", headers={"Authorization": f"Bearer {token}"})
    entries = log_response.json()
    entry = next(e for e in entries if e["action"] == "EMPLOYEE_CREATED")
    assert entry["entity_type"] == "employee"
    assert entry["entity_id"] == employee_id
    assert "Erika Musterfrau" in entry["detail"]


async def test_settings_change_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    token = await _token(client)

    await client.patch(
        "/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"require_pin_for_punch": True},
    )

    log_response = await client.get("/audit-log", headers={"Authorization": f"Bearer {token}"})
    entries = log_response.json()
    entry = next(e for e in entries if e["action"] == "SETTINGS_CHANGED")
    assert entry["entity_type"] == "app_settings"
    assert "require_pin_for_punch=True" in entry["detail"]


async def test_hr_user_creation_and_deletion_are_audited(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)
    token = await _token(client)

    create_response = await client.post(
        "/hr-users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "extra@example.com", "password": "pw123456", "role": "HR"},
    )
    new_hr_user_id = create_response.json()["id"]

    await client.delete(f"/hr-users/{new_hr_user_id}", headers={"Authorization": f"Bearer {token}"})

    log_response = await client.get("/audit-log", headers={"Authorization": f"Bearer {token}"})
    entries = log_response.json()
    actions = [(e["action"], e["entity_type"], e["entity_id"]) for e in entries]
    assert ("HR_USER_CREATED", "account", new_hr_user_id) in actions
    assert ("HR_USER_DELETED", "account", new_hr_user_id) in actions


async def test_team_crud_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    token = await _token(client)

    create_response = await client.post(
        "/teams", headers={"Authorization": f"Bearer {token}"}, json={"name": "Team Nord"}
    )
    team_id = create_response.json()["id"]

    await client.patch(
        f"/teams/{team_id}", headers={"Authorization": f"Bearer {token}"}, json={"name": "Team Nord neu"}
    )
    await client.delete(f"/teams/{team_id}", headers={"Authorization": f"Bearer {token}"})

    log_response = await client.get("/audit-log", headers={"Authorization": f"Bearer {token}"})
    entries = log_response.json()
    actions = [(e["action"], e["entity_type"], e["entity_id"]) for e in entries]
    assert ("TEAM_CREATED", "team", team_id) in actions
    assert ("TEAM_UPDATED", "team", team_id) in actions
    assert ("TEAM_DELETED", "team", team_id) in actions


async def test_tenant_admin_email_change_is_audited_for_target_tenant(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)  # tenant_id=1 via Autofill, siehe conftest.py
    admin_token = await _token(client)

    super_admin = Account(
        tenant_id=None, email="super@example.com", password_hash=hash_password("super-pw"), role=HrRole.SUPER_ADMIN
    )
    db_session.add(super_admin)
    await db_session.commit()
    super_login = await client.post(
        "/auth/login",
        headers={"Host": settings.super_admin_hostname},
        json={"email": "super@example.com", "password": "super-pw"},
    )
    super_token = super_login.json()["access_token"]

    response = await client.patch(
        "/tenants/1/admin-email",
        headers={"Authorization": f"Bearer {super_token}", "Host": settings.super_admin_hostname},
        json={"new_email": "new-admin@example.com"},
    )
    assert response.status_code == 200

    new_admin_token = await _token(client, "new-admin@example.com")
    log_response = await client.get(
        "/audit-log", headers={"Authorization": f"Bearer {new_admin_token}"}
    )
    entries = log_response.json()
    entry = next(e for e in entries if e["action"] == "TENANT_ADMIN_EMAIL_CHANGED")
    assert "admin@example.com -> new-admin@example.com" in entry["detail"]
    assert entry["actor_label"] == "super@example.com"
