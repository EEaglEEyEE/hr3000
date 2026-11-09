import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.tenant_provisioning as tenant_provisioning
from app.config import settings
from app.main import _ensure_production_secrets
from app.models import Employee, HrRole, Account, Location, ShiftTemplate, Tenant
from app.services.auth_service import hash_password


async def _admin(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    db_session.add(Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    await db_session.refresh(location)
    login = await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})
    return location, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _super(db_session: AsyncSession, client: AsyncClient) -> dict:
    db_session.add(Account(tenant_id=None, email="super@example.com", password_hash=hash_password("sp"), role=HrRole.SUPER_ADMIN))
    await db_session.commit()
    host = {"Host": settings.super_admin_hostname}
    login = await client.post("/auth/login", headers=host, json={"email": "super@example.com", "password": "sp"})
    return {**host, "Authorization": f"Bearer {login.json()['access_token']}"}


async def test_timesheet_and_weekly_balance_have_a_range_cap(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    employee = Employee(location_id=location.id, first_name="A", last_name="B", employee_number="E1")
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)

    huge = await client.get(f"/employees/{employee.id}/timesheet?from=0001-01-01&to=9999-12-31", headers=headers)
    huge_week = await client.get(f"/employees/{employee.id}/weekly-balance?from=2000-01-01&to=2030-01-01", headers=headers)
    ok = await client.get(f"/employees/{employee.id}/timesheet?from=2026-01-01&to=2026-12-31", headers=headers)

    assert huge.status_code == 400 and huge.json()["code"] == "RANGE_TOO_LARGE"
    assert huge_week.status_code == 400
    assert ok.status_code == 200


async def test_payroll_export_caps_employees_and_neutralizes_formulas(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    evil = Employee(location_id=location.id, first_name="=HYPERLINK(\"http://x\")", last_name="@SUM(A1)", employee_number="+1")
    db_session.add(evil)
    await db_session.commit()
    await db_session.refresh(evil)

    csv_response = await client.get(f"/payroll-export?employee_ids={evil.id}&from=2026-08-01&to=2026-08-02", headers=headers)
    too_many = await client.get(
        "/payroll-export?" + "&".join(f"employee_ids={i}" for i in range(1, 202)) + "&from=2026-08-01&to=2026-08-02",
        headers=headers,
    )

    text = csv_response.content.decode("utf-8-sig")
    assert "'=HYPERLINK" in text and "'@SUM" in text and "'+1" in text
    assert too_many.status_code == 400 and too_many.json()["code"] == "TOO_MANY_EMPLOYEES"


async def test_year_parameters_are_bounded(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    employee = Employee(location_id=location.id, first_name="A", last_name="B", employee_number="E1")
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)

    assert (await client.get("/holidays?year=0", headers=headers)).status_code == 422
    assert (await client.get("/holidays?year=99999", headers=headers)).status_code == 422
    assert (await client.get(f"/employees/{employee.id}/leave-entitlement?year=0", headers=headers)).status_code == 422
    assert (await client.get(f"/employees/{employee.id}/leave-entitlement?year=2026", headers=headers)).status_code == 200


async def test_reserved_and_malformed_subdomains_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _super(db_session, client)

    for subdomain in ("admin", "www", "-abc", "abc-", "ab_c", "A", "x" * 64):
        response = await client.post(
            "/tenants", headers=headers, json={"subdomain": subdomain, "name": "Kunde", "admin_email": "a@kunde.de"}
        )
        assert response.status_code == 422, subdomain
    ok = await client.post("/tenants", headers=headers, json={"subdomain": "kunde-1", "name": "Kunde", "admin_email": "a@kunde.de"})
    assert ok.status_code == 201


async def test_tenant_provisioning_is_atomic(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    headers = await _super(db_session, client)

    async def boom(*args, **kwargs):
        raise RuntimeError("Fehler mitten im Provisioning")

    # Gemeinsamer Einrichtungs-Service für Super-Admin und Selbstregistrierung.
    monkeypatch.setattr(tenant_provisioning, "seed_default_break_rules", boom)
    with pytest.raises(RuntimeError):
        await client.post("/tenants", headers=headers, json={"subdomain": "kunde", "name": "Kunde", "admin_email": "a@kunde.de"})
    await db_session.rollback()

    count = (await db_session.execute(select(func.count()).select_from(Tenant).where(Tenant.subdomain == "kunde"))).scalar_one()
    assert count == 0  # nichts blieb zurück, die Subdomain ist wieder frei


async def test_self_signup_is_atomic(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(settings, "tenant_base_domain", "hr3000.de")

    async def boom(*args, **kwargs):
        raise RuntimeError("Fehler mitten im Provisioning")

    monkeypatch.setattr(tenant_provisioning, "seed_default_break_rules", boom)
    payload = {
        "company_name": "Kunde GmbH", "subdomain": "kunde", "contact_name": "Kim Kunde", "email": "k@kunde.de",
        "password": "sehr-geheim-123", "is_business": True, "accept_terms": True,
    }
    with pytest.raises(RuntimeError):
        await client.post("/public/signup", json=payload, headers={"Host": "hr3000.de"})
    await db_session.rollback()

    assert (await db_session.execute(select(func.count()).select_from(Tenant).where(Tenant.subdomain == "kunde"))).scalar_one() == 0
    assert (await db_session.execute(select(func.count()).select_from(Account).where(Account.email == "k@kunde.de"))).scalar_one() == 0


async def test_super_admin_cannot_use_tenant_endpoints(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _super(db_session, client)

    response = await client.post("/holidays", headers=headers, json={"date": "2026-12-25", "name": "X"})

    assert response.status_code == 403 and response.json()["code"] == "TENANT_CONTEXT_REQUIRED"


def test_production_start_requires_a_real_jwt_secret(monkeypatch) -> None:
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "jwt_secret_key", "change-me-in-.env")
    with pytest.raises(RuntimeError):
        _ensure_production_secrets()
    monkeypatch.setattr(settings, "jwt_secret_key", "kurz")
    with pytest.raises(RuntimeError):
        _ensure_production_secrets()
    monkeypatch.setattr(settings, "jwt_secret_key", "x" * 48)
    with pytest.raises(RuntimeError):  # ohne gültigen Fernet-Schlüssel ebenfalls kein Start
        _ensure_production_secrets()
    monkeypatch.setattr(settings, "encryption_key", "invalid")
    with pytest.raises(RuntimeError):
        _ensure_production_secrets()
    from cryptography.fernet import Fernet

    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    _ensure_production_secrets()  # kein Fehler
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "jwt_secret_key", "change-me-in-.env")
    _ensure_production_secrets()  # Debug-Modus erlaubt den Platzhalter


async def test_employee_fields_are_length_limited(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    base = {"location_id": location.id, "first_name": "A", "last_name": "B", "employee_number": "N1"}

    for override in ({"first_name": "x" * 101}, {"last_name": ""}, {"employee_number": "x" * 51}, {"pin": "1" * 21}, {"nfc_uid": "x" * 65}):
        response = await client.post("/employees", headers=headers, json={**base, **override})
        assert response.status_code == 422, override


async def test_bulk_import_validates_email_and_lengths(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    csv_text = (
        "vorname;nachname;personalnummer;standort;login_email\n"
        f"Erika;Muster;E1;{location.name};keine-mail\n"
        f"{'x' * 101};Muster;E2;{location.name};\n"
        f"Max;Muster;E3;{location.name};Max@Example.com\n"
    )

    response = await client.post(
        "/employees/bulk-import", headers=headers, files={"file": ("m.csv", csv_text.encode(), "text/csv")}
    )

    body = response.json()
    assert body["created"] == 1 and len(body["errors"]) == 2
    employees = (await client.get("/employees", headers=headers)).json()
    assert [e["login_email"] for e in employees if e["employee_number"] == "E3"] == ["max@example.com"]


async def test_shift_template_in_use_cannot_be_deleted(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    employee = Employee(location_id=location.id, first_name="A", last_name="B", employee_number="E1")
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    template = (await client.post("/shift-templates", headers=headers, json={"name": "Früh", "target_minutes": 480})).json()
    await client.post(
        f"/employees/{employee.id}/default-shifts", headers=headers,
        json={"shift_template_id": template["id"], "valid_from": "2026-01-01", "weekdays_mask": 31},
    )

    response = await client.delete(f"/shift-templates/{template['id']}", headers=headers)

    assert response.status_code == 409 and response.json()["code"] == "SHIFT_TEMPLATE_IN_USE"


async def test_work_time_model_survives_name_collision_with_manual_template(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    employee = Employee(location_id=location.id, first_name="A", last_name="B", employee_number="E1")
    db_session.add(employee)
    db_session.add(ShiftTemplate(name="Arbeitszeitmodell 40 h/Woche", target_minutes=480))  # manuell angelegt, gleicher Name
    await db_session.commit()
    await db_session.refresh(employee)

    response = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=headers,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"},
    )

    assert response.status_code == 200 and response.json()["weekly_minutes"] == 2400
