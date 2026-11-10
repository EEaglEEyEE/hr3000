from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    BreakRule,
    Device,
    Employee,
    Holiday,
    HrRole,
    Account,
    Location,
    Tenant,
)
from app.services.auth_service import hash_password
from app.services.leave_service import used_vacation_days
from app.services.pairing_service import token_hash


async def _login(client: AsyncClient, email: str) -> dict:
    response = await client.post("/auth/login", json={"email": email, "password": "pw"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _world(db_session: AsyncSession):
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    for email, role in (("admin@example.com", HrRole.ADMIN), ("hr@example.com", HrRole.HR), ("sup@example.com", HrRole.SUPERVISOR)):
        db_session.add(Account(email=email, password_hash=hash_password("pw"), role=role))
    await db_session.commit()
    await db_session.refresh(location)
    boss = Employee(
        location_id=location.id, first_name="Chef", last_name="Admin", employee_number="A1",
        login_email="chef@example.com", password_hash=hash_password("pw"), hr_role=HrRole.ADMIN,
    )
    worker = Employee(location_id=location.id, first_name="Max", last_name="Muster", employee_number="W1")
    db_session.add_all([boss, worker])
    await db_session.commit()
    await db_session.refresh(boss)
    await db_session.refresh(worker)
    return location, boss, worker


async def test_hr_cannot_take_over_an_admin_account_via_employee_patch(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, boss, worker = await _world(db_session)
    hr = await _login(client, "hr@example.com")
    admin = await _login(client, "admin@example.com")

    for payload in ({"password": "neues-passwort-1"}, {"login_email": "evil@example.com"}, {"active": False}):
        forbidden = await client.patch(f"/employees/{boss.id}", headers=hr, json=payload)
        assert forbidden.status_code == 403, payload
    harmless = await client.patch(f"/employees/{boss.id}", headers=hr, json={"first_name": "Chefin"})
    ordinary = await client.patch(f"/employees/{worker.id}", headers=hr, json={"password": "neues-passwort-1"})
    by_admin = await client.patch(f"/employees/{boss.id}", headers=admin, json={"password": "neues-passwort-2"})

    assert harmless.status_code == 200
    assert ordinary.status_code == 200
    assert by_admin.status_code == 200


async def test_supervisor_cannot_create_or_edit_employees_or_config(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, worker = await _world(db_session)
    sup = await _login(client, "sup@example.com")

    assert (await client.post("/employees", headers=sup, json={"location_id": location.id, "first_name": "A", "last_name": "B", "employee_number": "N9"})).status_code == 403
    assert (await client.patch(f"/employees/{worker.id}", headers=sup, json={"first_name": "X"})).status_code == 403
    assert (await client.post("/holidays", headers=sup, json={"date": "2026-12-25", "name": "X"})).status_code == 403
    assert (await client.post("/locations", headers=sup, json={"name": "Neu", "timezone": "UTC"})).status_code == 403
    assert (await client.get("/devices", headers=sup)).status_code == 403  # enthält Geräte-Token
    assert (await client.post("/devices", headers=sup, json={"name": "T", "location_id": location.id})).status_code == 403
    assert (await client.get("/locations", headers=sup)).status_code == 200  # Lesen bleibt erlaubt


async def test_last_admin_cannot_be_deactivated_or_anonymized(client: AsyncClient, db_session: AsyncSession) -> None:
    _, boss, _ = await _world(db_session)
    # Der einzige HR-User-Admin wird entfernt -> der Chef-Mitarbeiter ist der letzte Admin.
    await db_session.delete((await db_session.execute(
        __import__("sqlalchemy").select(Account).where(Account.email == "admin@example.com"))).scalar_one())
    await db_session.commit()
    login = await client.post("/auth/login", json={"email": "chef@example.com", "password": "pw"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    boss.termination_date = date(2026, 1, 1)
    await db_session.commit()

    deactivate = await client.patch(f"/employees/{boss.id}", headers=headers, json={"active": False})
    anonymize = await client.post(f"/employees/{boss.id}/anonymize", headers=headers)

    assert deactivate.status_code == 400 and deactivate.json()["code"] == "LAST_ADMIN"
    assert anonymize.status_code == 400 and anonymize.json()["code"] == "LAST_ADMIN"


async def test_anonymized_employee_cannot_be_edited(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, worker = await _world(db_session)
    worker.termination_date = date(2026, 1, 1)
    await db_session.commit()
    admin = await _login(client, "admin@example.com")
    await client.post(f"/employees/{worker.id}/anonymize", headers=admin)

    response = await client.patch(f"/employees/{worker.id}", headers=admin, json={"first_name": "Zurück"})

    assert response.status_code == 400 and response.json()["code"] == "ALREADY_ANONYMIZED"


async def test_location_employee_list_not_available_to_self_service(client: AsyncClient, db_session: AsyncSession) -> None:
    location, boss, _ = await _world(db_session)
    colleague = Employee(
        location_id=location.id, first_name="Kollege", last_name="K", employee_number="K1",
        login_email="k@example.com", password_hash=hash_password("pw"), nfc_uid="04:AA",
    )
    db_session.add(colleague)
    await db_session.commit()
    login = await client.post("/auth/login", json={"email": "k@example.com", "password": "pw"})
    self_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    hr = await _login(client, "hr@example.com")
    db_session.add(Device(location_id=location.id, token_hash=token_hash("dev-1"), name="Kiosk"))
    await db_session.commit()
    device = (await client.post("/auth/device/login", json={"device_token": "dev-1"})).json()

    assert (await client.get(f"/locations/{location.id}/employees", headers=self_headers)).status_code == 403
    assert (await client.get(f"/locations/{location.id}/employees", headers=hr)).status_code == 200
    kiosk = await client.get(f"/locations/{location.id}/employees", headers={"Authorization": f"Bearer {device['access_token']}"})
    assert kiosk.status_code == 200


async def test_break_rules_of_other_tenants_do_not_affect_calculation(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, worker = await _world(db_session)
    db_session.add(Tenant(id=2, subdomain="other", name="Other"))
    await db_session.commit()
    db_session.add(BreakRule(tenant_id=1, min_work_minutes=360, deduct_minutes=30))
    db_session.add(BreakRule(tenant_id=2, min_work_minutes=1, deduct_minutes=240))  # absurde Regel des anderen Mandanten
    await db_session.commit()
    hr = await _login(client, "hr@example.com")

    for key, kind, ts in (("a", "COME", "2026-08-10T06:00:00Z"), ("b", "GO", "2026-08-10T14:00:00Z")):
        await client.post("/punches", headers=hr, json={
            "employee_id": worker.id, "punch_type": kind, "timestamp_utc": ts,
            "idempotency_key": f"aaaaaaaa-0000-0000-0000-00000000000{'1' if key == 'a' else '2'}"})
    days = (await client.get(f"/employees/{worker.id}/timesheet?from=2026-08-10&to=2026-08-10", headers=hr)).json()

    assert days[0]["actual_minutes"] == 450  # 8 h minus 30 min der EIGENEN Regel


async def test_vacation_days_ignore_holidays_of_other_tenants_and_locations(db_session: AsyncSession) -> None:
    location, _, worker = await _world(db_session)
    db_session.add(Tenant(id=2, subdomain="other", name="Other"))
    await db_session.flush()  # Mandant zuerst – sonst scheitert der Standort am Fremdschlüssel
    other_location = Location(tenant_id=2, name="Fremd", timezone="UTC")
    second_location = Location(name="Standort B", timezone="UTC")
    db_session.add_all([other_location, second_location])
    await db_session.commit()
    await db_session.refresh(second_location)
    db_session.add(Absence(employee_id=worker.id, type=AbsenceType.VACATION, date_from=date(2026, 8, 10),
                           date_to=date(2026, 8, 12), approval_status=AbsenceApprovalStatus.APPROVED))
    db_session.add(Holiday(tenant_id=2, date=date(2026, 8, 11), name="Fremd-Feiertag"))  # anderer Mandant
    db_session.add(Holiday(date=date(2026, 8, 12), name="Nur Standort B", locations=[second_location]))  # anderer Standort
    await db_session.commit()

    assert await used_vacation_days(db_session, worker.id, 2026) == 3.0

    db_session.add(Holiday(date=date(2026, 8, 10), name="Gilt für alle"))
    await db_session.commit()
    assert await used_vacation_days(db_session, worker.id, 2026) == 2.0
