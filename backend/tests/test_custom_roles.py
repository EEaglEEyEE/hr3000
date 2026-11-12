"""Eigene Rollen: Verwaltung (/roles), Zuweisung (Mitarbeiter-Zugang, Verwaltungskonten), zentrale
Durchsetzung in app/api/deps.py, Token-Claims und Benachrichtigungen."""
import base64
import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AuditAction, AuditLogEntry, Employee, HrRole, Location, Role, Tenant
from app.services.auth_service import hash_password
from app.services.notification_service import full_hr_recipients
from app.services.role_permissions import Area, dump_permissions

PW = "pw123456"


async def _location(db: AsyncSession) -> Location:
    location = Location(name="Zentrale", timezone="UTC")
    db.add(location)
    await db.commit()
    return location


async def _account(db: AsyncSession, email: str, role: HrRole | None, custom: Role | None = None, payroll=False) -> Account:
    account = Account(email=email, password_hash=hash_password(PW), role=role, payroll_access=payroll, custom_role=custom)
    db.add(account)
    await db.commit()
    return account


async def _role(db: AsyncSession, name: str = "Zeiten", tenant_id: int = 1, **perms: str) -> Role:
    role = Role(tenant_id=tenant_id, name=name, permissions=dump_permissions({Area(k): v for k, v in perms.items()}))
    db.add(role)
    await db.commit()
    return role


async def _employee(db: AsyncSession, location: Location, number: str, email: str | None = None,
                    role: HrRole | None = None, custom: Role | None = None) -> Employee:
    employee = Employee(
        location_id=location.id, first_name="Erika", last_name=f"Muster{number}", employee_number=number, active=True,
        login_email=email, password_hash=hash_password(PW) if email else None, hr_role=role,
    )
    db.add(employee)
    await db.flush()
    if custom is not None:
        employee.account.custom_role = custom
    await db.commit()
    return employee


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": PW})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _claims(headers: dict[str, str]) -> dict:
    token = headers["Authorization"].split(" ", 1)[1]
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


async def _audit(db: AsyncSession) -> list[AuditLogEntry]:
    return list((await db.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.ROLE_CHANGED))).scalars())


@pytest.fixture
async def admin(client: AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    await _account(db_session, "admin@example.com", HrRole.ADMIN)
    return await _login(client, "admin@example.com")


# --- Verwaltung der Rollen --------------------------------------------------------------------------


async def test_meta_lists_areas_and_template(client: AsyncClient, admin) -> None:
    body = (await client.get("/roles/meta", headers=admin)).json()
    assert [a["key"] for a in body["areas"]][0] == "EMPLOYEES"
    assert len(body["areas"]) == len(Area)
    template = body["templates"][0]
    assert template["name"] == "Lohnbüro (nur lesen)"
    assert template["permissions"]["PAYROLL"] == "VIEW"
    assert template["permissions"]["EMPLOYEES"] == "NONE"


async def test_create_list_update_delete_role(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    created = await client.post(
        "/roles", headers=admin,
        json={"name": "  Lohnbüro  ", "description": "Steuerberatung", "permissions": {"PAYROLL": "VIEW"}},
    )
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["name"] == "Lohnbüro"
    assert role["permissions"]["PAYROLL"] == "VIEW"
    assert role["permissions"]["TIME"] == "NONE"
    assert role["account_count"] == 0

    listed = (await client.get("/roles", headers=admin)).json()
    assert [r["name"] for r in listed] == ["Lohnbüro"]

    updated = await client.patch(
        f"/roles/{role['id']}", headers=admin, json={"name": "Lohnbüro extern", "permissions": {"PAYROLL": "EDIT"}}
    )
    assert updated.status_code == 200
    assert updated.json()["permissions"]["PAYROLL"] == "EDIT"
    assert updated.json()["description"] == "Steuerberatung"

    cleared = await client.patch(f"/roles/{role['id']}", headers=admin, json={"description": None})
    assert cleared.json()["description"] is None

    assert (await client.delete(f"/roles/{role['id']}", headers=admin)).status_code == 204
    assert (await client.get("/roles", headers=admin)).json() == []

    details = [e.detail for e in await _audit(db_session)]
    assert any("angelegt" in d and "Vergütung & Lohn: ansehen" in d for d in details)
    assert any("geändert" in d and "Lohnbüro extern" in d for d in details)
    assert any("Beschreibung geändert" in d for d in details)
    assert any("gelöscht" in d for d in details)


async def test_update_without_changes_writes_no_audit(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    role = await _role(db_session, TIME="VIEW")
    response = await client.patch(f"/roles/{role.id}", headers=admin, json={"name": "Zeiten", "permissions": {"TIME": "VIEW"}})
    assert response.status_code == 200
    assert await _audit(db_session) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "permissions": {"TIME": "VIEW"}},
        {"name": "   ", "permissions": {"TIME": "VIEW"}},
        {"name": "x" * 81, "permissions": {"TIME": "VIEW"}},
        {"name": "R", "description": "x" * 501, "permissions": {"TIME": "VIEW"}},
        {"name": "R", "permissions": {"UNKNOWN": "VIEW"}},
        {"name": "R", "permissions": {"TIME": "SUGGEST"}},
        {"name": "R", "permissions": {}},
        {"name": "R", "permissions": {"TIME": "NONE"}},
        {"name": "R"},
    ],
)
async def test_create_role_validation(client: AsyncClient, admin, payload) -> None:
    assert (await client.post("/roles", headers=admin, json=payload)).status_code == 422


async def test_name_limits_accepted(client: AsyncClient, admin) -> None:
    response = await client.post("/roles", headers=admin, json={"name": "x" * 80, "description": "d" * 500, "permissions": {"TIME": "EDIT"}})
    assert response.status_code == 201


async def test_update_rejects_all_none(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    role = await _role(db_session, TIME="VIEW")
    response = await client.patch(f"/roles/{role.id}", headers=admin, json={"permissions": {"TIME": "NONE"}})
    assert response.status_code == 422


async def test_duplicate_names_conflict(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    await _role(db_session, "A", TIME="VIEW")
    other_id = (await _role(db_session, "B", TIME="VIEW")).id
    dup = await client.post("/roles", headers=admin, json={"name": "A", "permissions": {"TIME": "VIEW"}})
    assert dup.status_code == 409
    assert dup.json()["code"] == "ROLE_NAME_TAKEN"
    rename = await client.patch(f"/roles/{other_id}", headers=admin, json={"name": "A"})
    assert rename.status_code == 409


async def test_same_name_in_other_tenant_is_fine(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.flush()
    await _role(db_session, "A", tenant_id=2, TIME="VIEW")
    assert (await client.post("/roles", headers=admin, json={"name": "A", "permissions": {"TIME": "VIEW"}})).status_code == 201
    assert [r["name"] for r in (await client.get("/roles", headers=admin)).json()] == ["A"]


async def test_foreign_tenant_role_is_not_found(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.flush()
    foreign = await _role(db_session, "Fremd", tenant_id=2, TIME="VIEW")
    assert (await client.patch(f"/roles/{foreign.id}", headers=admin, json={"name": "X"})).status_code == 404
    assert (await client.delete(f"/roles/{foreign.id}", headers=admin)).status_code == 404
    assert (await client.delete("/roles/999", headers=admin)).status_code == 404


async def test_delete_role_in_use_conflicts(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    role = await _role(db_session, PAYROLL="VIEW")
    await _account(db_session, "lohn@example.com", HrRole.HR, role)
    response = await client.delete(f"/roles/{role.id}", headers=admin)
    assert response.status_code == 409
    assert response.json()["code"] == "ROLE_IN_USE"
    assert (await client.get("/roles", headers=admin)).json()[0]["account_count"] == 1


@pytest.mark.parametrize("role", [HrRole.HR, HrRole.SUPERVISOR])
async def test_roles_admin_only(client: AsyncClient, db_session: AsyncSession, role: HrRole) -> None:
    await _account(db_session, "hr@example.com", role)
    headers = await _login(client, "hr@example.com")
    assert (await client.get("/roles", headers=headers)).status_code == 403
    assert (await client.get("/roles/meta", headers=headers)).status_code == 403
    assert (await client.post("/roles", headers=headers, json={"name": "R", "permissions": {"TIME": "VIEW"}})).status_code == 403


async def test_employee_without_role_cannot_manage_roles(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _location(db_session)
    await _employee(db_session, location, "E1", "ma@example.com")
    headers = await _login(client, "ma@example.com")
    assert (await client.get("/roles", headers=headers)).status_code == 403


async def test_unauthenticated_is_rejected(client: AsyncClient) -> None:
    assert (await client.get("/roles")).status_code in (401, 403)


# --- Zuweisung am Mitarbeiter-Zugang ---------------------------------------------------------------


async def test_assign_role_to_employee_access(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    location = await _location(db_session)
    role = await _role(db_session, TIME="EDIT")
    employee = await _employee(db_session, location, "E1", "hr@example.com", HrRole.HR)

    response = await client.patch(
        f"/employees/{employee.id}/hr-role", headers=admin, json={"hr_role": "HR", "custom_role_id": role.id}
    )
    assert response.status_code == 200, response.text
    assert response.json()["hr_custom_role"] == {"id": role.id, "name": "Zeiten"}

    # weggelassen = unverändert
    kept = await client.patch(f"/employees/{employee.id}/hr-role", headers=admin, json={"hr_role": "HR", "payroll_access": True})
    assert kept.json()["hr_custom_role"]["id"] == role.id

    # null = entziehen
    cleared = await client.patch(f"/employees/{employee.id}/hr-role", headers=admin, json={"hr_role": "HR", "custom_role_id": None})
    assert cleared.json()["hr_custom_role"] is None

    details = [e.detail for e in await _audit(db_session)]
    assert any("„keine“ → „Zeiten“" in d for d in details)
    assert any("„Zeiten“ → „keine“" in d for d in details)


async def test_changing_to_admin_drops_custom_role(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    location = await _location(db_session)
    role = await _role(db_session, TIME="EDIT")
    employee = await _employee(db_session, location, "E1", "hr@example.com", HrRole.HR, role)
    response = await client.patch(f"/employees/{employee.id}/hr-role", headers=admin, json={"hr_role": "ADMIN"})
    assert response.json()["hr_role"] == "ADMIN"
    assert response.json()["hr_custom_role"] is None


@pytest.mark.parametrize("hr_role", ["ADMIN", "SUPERVISOR", None])
async def test_custom_role_only_for_hr(client: AsyncClient, db_session: AsyncSession, admin, hr_role) -> None:
    location = await _location(db_session)
    role = await _role(db_session, TIME="EDIT")
    employee = await _employee(db_session, location, "E1", "x@example.com")
    response = await client.patch(
        f"/employees/{employee.id}/hr-role", headers=admin, json={"hr_role": hr_role, "custom_role_id": role.id}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CUSTOM_ROLE_REQUIRES_HR"


async def test_custom_role_without_login_rejected(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    location = await _location(db_session)
    role = await _role(db_session, TIME="EDIT")
    employee = await _employee(db_session, location, "E1")
    response = await client.patch(f"/employees/{employee.id}/hr-role", headers=admin, json={"hr_role": None, "custom_role_id": role.id})
    assert response.status_code == 400


async def test_foreign_role_cannot_be_assigned(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.flush()
    foreign = await _role(db_session, "Fremd", tenant_id=2, TIME="VIEW")
    location = await _location(db_session)
    employee = await _employee(db_session, location, "E1", "hr@example.com", HrRole.HR)
    response = await client.patch(f"/employees/{employee.id}/hr-role", headers=admin, json={"hr_role": "HR", "custom_role_id": foreign.id})
    assert response.status_code == 404
    assert response.json()["code"] == "ROLE_NOT_FOUND"


@pytest.mark.parametrize("value", [0, -1, "abc"])
async def test_custom_role_id_validation(client: AsyncClient, db_session: AsyncSession, admin, value) -> None:
    location = await _location(db_session)
    employee = await _employee(db_session, location, "E1", "hr@example.com", HrRole.HR)
    response = await client.patch(f"/employees/{employee.id}/hr-role", headers=admin, json={"hr_role": "HR", "custom_role_id": value})
    assert response.status_code == 422


async def test_anonymize_drops_custom_role(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    from datetime import date

    location = await _location(db_session)
    role = await _role(db_session, TIME="EDIT")
    employee = await _employee(db_session, location, "E1", "hr@example.com", HrRole.HR, role)
    employee.termination_date = date(2025, 1, 31)
    await db_session.commit()
    assert (await client.post(f"/employees/{employee.id}/anonymize", headers=admin)).status_code == 200
    assert (await client.delete(f"/roles/{role.id}", headers=admin)).status_code == 204


# --- Verwaltungskonten ----------------------------------------------------------------------------


async def test_hr_user_with_custom_role(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    role = await _role(db_session, "Lohnbüro", PAYROLL="VIEW")
    created = await client.post(
        "/hr-users", headers=admin,
        json={"email": "stb@example.com", "password": PW, "role": "HR", "custom_role_id": role.id},
    )
    assert created.status_code == 201, created.text
    assert created.json()["custom_role"] == {"id": role.id, "name": "Lohnbüro"}
    assert created.json()["two_factor_enabled"] is False

    listed = (await client.get("/hr-users", headers=admin)).json()
    assert {u["email"]: u["custom_role"] for u in listed}["stb@example.com"]["name"] == "Lohnbüro"
    assert any("stb@example.com" in e.detail for e in await _audit(db_session))


async def test_hr_user_custom_role_requires_hr(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    role = await _role(db_session, PAYROLL="VIEW")
    response = await client.post(
        "/hr-users", headers=admin, json={"email": "x@example.com", "password": PW, "role": "ADMIN", "custom_role_id": role.id}
    )
    assert response.status_code == 400
    assert (await client.get("/hr-users", headers=admin)).json()[0]["email"] == "admin@example.com"


async def test_hr_user_foreign_role_rejected(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.flush()
    foreign = await _role(db_session, "Fremd", tenant_id=2, TIME="VIEW")
    response = await client.post(
        "/hr-users", headers=admin, json={"email": "x@example.com", "password": PW, "role": "HR", "custom_role_id": foreign.id}
    )
    assert response.status_code == 404


async def test_update_hr_user(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    role = await _role(db_session, PAYROLL="VIEW")
    user = await _account(db_session, "stb@example.com", HrRole.HR)

    assigned = await client.patch(f"/hr-users/{user.id}", headers=admin, json={"custom_role_id": role.id})
    assert assigned.status_code == 200
    assert assigned.json()["custom_role"]["id"] == role.id

    payroll = await client.patch(f"/hr-users/{user.id}", headers=admin, json={"payroll_access": True})
    assert payroll.json()["payroll_access"] is True
    assert payroll.json()["custom_role"]["id"] == role.id

    promoted = await client.patch(f"/hr-users/{user.id}", headers=admin, json={"role": "ADMIN"})
    assert promoted.json()["role"] == "ADMIN"
    assert promoted.json()["custom_role"] is None
    assert promoted.json()["payroll_access"] is False

    demoted = await client.patch(f"/hr-users/{user.id}", headers=admin, json={"role": "HR", "custom_role_id": role.id})
    assert demoted.json()["custom_role"]["id"] == role.id

    actions = [e.action for e in (await db_session.execute(select(AuditLogEntry))).scalars()]
    assert AuditAction.EMPLOYEE_HR_ROLE_CHANGED in actions
    assert AuditAction.ROLE_CHANGED in actions


async def test_update_hr_user_errors(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    me = (await db_session.execute(select(Account).where(Account.email == "admin@example.com"))).scalar_one()
    assert (await client.patch(f"/hr-users/{me.id}", headers=admin, json={"role": "HR"})).status_code == 400
    assert (await client.patch(f"/hr-users/{me.id}", headers=admin, json={"role": "SUPER_ADMIN"})).status_code == 403
    assert (await client.patch("/hr-users/999", headers=admin, json={"role": "HR"})).status_code == 404
    other = await _account(db_session, "other@example.com", HrRole.HR)
    assert (await client.patch(f"/hr-users/{other.id}", headers=admin, json={"role": "WIZARD"})).status_code == 422
    assert (await client.patch(f"/hr-users/{other.id}", headers=admin, json={"custom_role_id": 0})).status_code == 422


async def test_update_hr_user_rejects_employee_accounts(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    location = await _location(db_session)
    employee = await _employee(db_session, location, "E1", "hr@example.com", HrRole.HR)
    assert (await client.patch(f"/hr-users/{employee.account.id}", headers=admin, json={"role": "ADMIN"})).status_code == 404


async def test_last_admin_cannot_be_demoted(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    other_admin = await _account(db_session, "admin2@example.com", HrRole.ADMIN)
    headers = await _login(client, "admin2@example.com")
    me = (await db_session.execute(select(Account).where(Account.email == "admin@example.com"))).scalar_one()
    me.role = HrRole.HR
    await db_session.commit()
    response = await client.patch(f"/hr-users/{other_admin.id}", headers=headers, json={"role": "HR"})
    assert response.status_code == 400


async def test_hr_user_patch_foreign_tenant(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.flush()
    foreign = Account(tenant_id=2, email="f@example.com", password_hash=hash_password(PW), role=HrRole.HR)
    db_session.add(foreign)
    await db_session.commit()
    assert (await client.patch(f"/hr-users/{foreign.id}", headers=admin, json={"payroll_access": True})).status_code == 404


async def test_delete_hr_user_frees_role(client: AsyncClient, db_session: AsyncSession, admin) -> None:
    role = await _role(db_session, PAYROLL="VIEW")
    user = await _account(db_session, "stb@example.com", HrRole.HR, role)
    assert (await client.delete(f"/hr-users/{user.id}", headers=admin)).status_code == 204
    assert (await client.delete(f"/roles/{role.id}", headers=admin)).status_code == 204


async def test_hr_user_endpoints_admin_only(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _account(db_session, "hr@example.com", HrRole.HR)
    headers = await _login(client, "hr@example.com")
    assert (await client.patch(f"/hr-users/{user.id}", headers=headers, json={"role": "ADMIN"})).status_code == 403


# --- Durchsetzung -----------------------------------------------------------------------------------


async def _limited(client: AsyncClient, db_session: AsyncSession, **perms: str) -> dict[str, str]:
    role = await _role(db_session, "Eingeschränkt", **perms)
    await _account(db_session, "limited@example.com", HrRole.HR, role, payroll=True)
    return await _login(client, "limited@example.com")


async def test_payroll_office_sees_only_payroll_reading(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _limited(client, db_session, PAYROLL="VIEW")
    assert (await client.get("/wage-types", headers=headers)).status_code == 200
    assert (await client.get("/pay-component-types", headers=headers)).status_code == 200
    for path in ["/employees", "/payroll-export?date_from=2026-01-01&date_to=2026-01-31", "/timesheet/open-days",
                 "/absences/pending", "/audit-log", "/departments", "/reports/vacation?year=2026"]:
        response = await client.get(path, headers=headers)
        assert response.status_code == 403, path
        assert response.json()["code"] == "ROLE_PERMISSION_REQUIRED", path
    put = await client.put("/wage-types", headers=headers, json=[])
    assert put.status_code == 403


async def test_admin_only_routes_stay_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _limited(client, db_session, **{area.value: "EDIT" for area in Area})
    for path in ["/settings", "/hr-users", "/roles"]:
        assert (await client.get(path, headers=headers)).status_code == 403, path


async def test_always_routes_work_for_limited_accounts(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _limited(client, db_session, PAYROLL="VIEW")
    for path in ["/notifications", "/features", "/absence-types", "/holidays", "/auth/2fa", "/dashboard"]:
        assert (await client.get(path, headers=headers)).status_code == 200, path


async def test_time_role_can_use_time_but_not_absences(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _location(db_session)
    employee = await _employee(db_session, location, "E1")
    headers = await _limited(client, db_session, TIME="VIEW")
    assert (await client.get("/timesheet/open-days", headers=headers)).status_code == 200
    assert (await client.get("/employees", headers=headers)).status_code == 200  # Nachschlageliste
    assert (await client.get(f"/employees/{employee.id}/timesheet?from=2026-01-01&to=2026-01-31", headers=headers)).status_code == 200
    assert (await client.get(f"/employees/{employee.id}/absences", headers=headers)).status_code == 403
    # Nur ansehen: Buchung korrigieren verlangt Bearbeiten
    assert (await client.delete("/punches/1", headers=headers)).status_code == 403
    # Nicht freigegebene Bereiche
    assert (await client.get("/checklists/open-items", headers=headers)).status_code == 403


async def test_edit_level_allows_writes(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _location(db_session)
    headers = await _limited(client, db_session, EMPLOYEES="EDIT")
    response = await client.post(
        "/employees", headers=headers,
        json={"first_name": "Neu", "last_name": "Person", "employee_number": "N1", "location_id": location.id},
    )
    assert response.status_code == 201, response.text
    view_only = await _role(db_session, "Nur lesen", EMPLOYEES="VIEW")
    await _account(db_session, "viewer@example.com", HrRole.HR, view_only)
    viewer = await _login(client, "viewer@example.com")
    blocked = await client.post(
        "/employees", headers=viewer,
        json={"first_name": "Neu", "last_name": "Zwei", "employee_number": "N2", "location_id": location.id},
    )
    assert blocked.status_code == 403


async def test_linked_employee_keeps_own_data(client: AsyncClient, db_session: AsyncSession) -> None:
    """Mixed-Routen: ohne Bereichsrecht nur die eigenen Daten (wie ein Mitarbeiter)."""
    location = await _location(db_session)
    role = await _role(db_session, "Lohnbüro", PAYROLL="VIEW")
    me = await _employee(db_session, location, "E1", "me@example.com", HrRole.HR, role)
    other = await _employee(db_session, location, "E2")
    headers = await _login(client, "me@example.com")
    assert (await client.get(f"/employees/{me.id}/absences", headers=headers)).status_code == 200
    assert (await client.get(f"/employees/{other.id}/absences", headers=headers)).status_code == 403
    assert (await client.get(f"/employees/{me.id}", headers=headers)).status_code == 200
    assert (await client.get(f"/employees/{other.id}", headers=headers)).status_code == 403
    assert (await client.get("/me/personal-data", headers=headers)).status_code == 200


async def test_payroll_view_needs_employees_for_compensation(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _location(db_session)
    employee = await _employee(db_session, location, "E1")
    only_payroll = await _limited(client, db_session, PAYROLL="EDIT")
    assert (await client.get(f"/employees/{employee.id}/compensation", headers=only_payroll)).status_code == 403
    role = await _role(db_session, "Lohn+MA", PAYROLL="VIEW", EMPLOYEES="VIEW")
    await _account(db_session, "both@example.com", HrRole.HR, role)
    both = await _login(client, "both@example.com")
    assert (await client.get(f"/employees/{employee.id}/compensation", headers=both)).status_code == 200
    assert (await client.post(f"/employees/{employee.id}/compensation", headers=both, json={})).status_code == 403


async def test_payroll_fields_need_payroll_edit(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _location(db_session)
    employee = await _employee(db_session, location, "E1")
    headers = await _limited(client, db_session, EMPLOYEES="EDIT", PAYROLL="VIEW")
    response = await client.patch(f"/employees/{employee.id}/personal-data", headers=headers, json={"iban": "DE89370400440532013000"})
    assert response.status_code == 403
    assert response.json()["code"] == "PAYROLL_PERMISSION_REQUIRED"
    ok = await client.patch(f"/employees/{employee.id}/personal-data", headers=headers, json={"street": "Hauptstr. 1"})
    assert ok.status_code == 200, ok.text


async def test_payroll_export_needs_edit(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _limited(client, db_session, PAYROLL="EDIT")
    response = await client.get("/payroll-export/status", headers=headers)
    assert response.status_code != 403


async def test_role_change_takes_effect_immediately(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _limited(client, db_session, PAYROLL="VIEW")
    assert (await client.get("/timesheet/open-days", headers=headers)).status_code == 403
    role = (await db_session.execute(select(Role))).scalar_one()
    role.permissions = dump_permissions({Area.TIME: "VIEW"})
    await db_session.commit()
    assert (await client.get("/timesheet/open-days", headers=headers)).status_code == 200


async def test_hr_without_custom_role_unchanged(client: AsyncClient, db_session: AsyncSession) -> None:
    await _account(db_session, "hr@example.com", HrRole.HR)
    headers = await _login(client, "hr@example.com")
    assert (await client.get("/employees", headers=headers)).status_code == 200
    assert (await client.get("/audit-log", headers=headers)).status_code == 200
    assert (await client.get("/wage-types", headers=headers)).status_code == 403  # ohne „Vergütung & Lohn-Export“


async def test_supervisor_and_employee_unaffected(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _location(db_session)
    await _employee(db_session, location, "S1", "lead@example.com", HrRole.SUPERVISOR)
    await _employee(db_session, location, "E1", "ma@example.com")
    lead = await _login(client, "lead@example.com")
    assert (await client.get("/employees", headers=lead)).status_code == 200
    ma = await _login(client, "ma@example.com")
    assert (await client.get("/me/personal-data", headers=ma)).status_code == 200


# --- Token-Claims -----------------------------------------------------------------------------------


async def test_token_claims(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _limited(client, db_session, PAYROLL="VIEW")
    claims = _claims(headers)
    assert claims["role"] == "HR"
    assert claims["payroll"] is True
    assert claims["perms"]["PAYROLL"] == "VIEW"
    assert claims["perms"]["EMPLOYEES"] == "NONE"


async def test_token_claims_without_custom_role(client: AsyncClient, db_session: AsyncSession) -> None:
    await _account(db_session, "hr@example.com", HrRole.HR)
    claims = _claims(await _login(client, "hr@example.com"))
    assert claims["perms"] is None
    assert claims["payroll"] is False


# --- Benachrichtigungen -----------------------------------------------------------------------------


async def test_notification_recipients_respect_custom_roles(db_session: AsyncSession) -> None:
    absences = await _role(db_session, "Urlaub", ABSENCES="VIEW")
    payroll = await _role(db_session, "Lohn", PAYROLL="VIEW")
    admin = await _account(db_session, "admin@example.com", HrRole.ADMIN, None)
    hr = await _account(db_session, "hr@example.com", HrRole.HR)
    urlaub = await _account(db_session, "urlaub@example.com", HrRole.HR, absences)
    await _account(db_session, "lohn@example.com", HrRole.HR, payroll)

    ids = [a for a, _ in await full_hr_recipients(db_session, 1, area=Area.ABSENCES)]
    assert ids == [admin.id, hr.id, urlaub.id]
    ids = [a for a, _ in await full_hr_recipients(db_session, 1)]
    assert ids == [admin.id, hr.id]
    ids = [a for a, _ in await full_hr_recipients(db_session, 1, area=Area.TIME)]
    assert ids == [admin.id, hr.id]


# --- Mandant löschen --------------------------------------------------------------------------------


async def test_role_fk_set_null_on_delete(db_session: AsyncSession) -> None:
    role = await _role(db_session, PAYROLL="VIEW")
    account = await _account(db_session, "lohn@example.com", HrRole.HR, role)
    await db_session.delete(role)
    await db_session.commit()
    await db_session.refresh(account)
    assert account.custom_role_id is None
