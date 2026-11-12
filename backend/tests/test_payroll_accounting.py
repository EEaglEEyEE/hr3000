"""Vorbereitende Lohnbuchhaltung: Monatsübersicht, Freigabe mit Schnappschuss und Dateien, Rücknahme,
Lohnbüro-Sicht (eigene Rolle „Vergütung & Lohn: Ansehen“), Schalter und Audit."""
import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    Account,
    AllowanceUnit,
    AttributeDefinition,
    AttributeSection,
    AttributeValue,
    AuditAction,
    AuditLogEntry,
    Compensation,
    ContractType,
    Employee,
    EmployeeLocationPeriod,
    EmploymentContract,
    HrRole,
    Location,
    PayComponent,
    PayComponentKind,
    PayComponentType,
    PayrollExportLog,
    PayrollRelease,
    PayType,
    PeriodClosure,
    PeriodStatus,
    Role,
    Tenant,
)
from app.services.auth_service import hash_password
from app.services.role_permissions import Area, dump_permissions

MONTH = "2026-10"
PW = "pw123456"


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": PW})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _account(db: AsyncSession, email: str, role: HrRole | None, custom: Role | None = None, payroll=False) -> Account:
    account = Account(email=email, password_hash=hash_password(PW), role=role, payroll_access=payroll, custom_role=custom)
    db.add(account)
    await db.commit()
    return account


async def _office_role(db: AsyncSession) -> Role:
    role = Role(tenant_id=1, name="Lohnbüro (nur lesen)", permissions=dump_permissions({Area.PAYROLL: "VIEW"}))
    db.add(role)
    await db.commit()
    return role


@pytest.fixture
async def setup(client: AsyncClient, db_session: AsyncSession) -> dict:
    """Firma mit Lohnbuchhaltung an, Admin, zwei Mitarbeiter im Oktober (einer tritt ein, einer aus)."""
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    lia = Employee(location_id=location.id, first_name="Lia", last_name="Lohn", employee_number="100",
                   auto_break_enabled=False, hire_date=date(2026, 10, 1))
    max_ = Employee(location_id=location.id, first_name="Max", last_name="Muster", employee_number="101",
                    auto_break_enabled=False, hire_date=date(2020, 1, 1), termination_date=date(2026, 10, 31))
    db_session.add_all([lia, max_])
    await db_session.commit()
    await _account(db_session, "admin@example.com", HrRole.ADMIN)
    admin = await _login(client, "admin@example.com")
    for employee in (lia, max_):
        r = await client.put(
            f"/employees/{employee.id}/work-time-model", headers=admin,
            json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-09-01"},
        )
        assert r.status_code == 200, r.text
    r = await client.patch("/settings", headers=admin, json={"payroll_accounting_enabled": True})
    assert r.status_code == 200, r.text
    return {"admin": admin, "lia": lia, "max": max_, "location": location}


async def _close(db: AsyncSession, *employees: Employee) -> None:
    now = datetime(2026, 11, 2, 8, 0)
    for employee in employees:
        db.add(PeriodClosure(
            tenant_id=1, employee_id=employee.id, year=2026, month=10, status=PeriodStatus.CLOSED,
            target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=now, closed_at=now,
        ))
    await db.commit()


def _row(body: dict, employee: Employee) -> dict:
    return next(row for row in body["employees"] if row["employee_id"] == employee.id)


# --- Schalter ---------------------------------------------------------------------------------------


async def test_disabled_by_default(client: AsyncClient, db_session: AsyncSession) -> None:
    await _account(db_session, "admin@example.com", HrRole.ADMIN)
    admin = await _login(client, "admin@example.com")
    assert (await client.get("/features", headers=admin)).json()["payroll_accounting_enabled"] is False
    for path in ["/payroll-accounting/releases", f"/payroll-accounting/{MONTH}", f"/payroll-accounting/{MONTH}/files/csv"]:
        response = await client.get(path, headers=admin)
        assert response.status_code == 404, path
        assert response.json()["code"] == "PAYROLL_ACCOUNTING_DISABLED"
    assert (await client.post(f"/payroll-accounting/{MONTH}/release", headers=admin, json={})).status_code == 404
    assert (await client.delete(f"/payroll-accounting/{MONTH}/release", headers=admin)).status_code == 404


async def test_switch_shows_in_features_and_settings(client: AsyncClient, setup) -> None:
    assert (await client.get("/features", headers=setup["admin"])).json()["payroll_accounting_enabled"] is True
    assert (await client.get("/settings", headers=setup["admin"])).json()["payroll_accounting_enabled"] is True


# --- Aktueller Stand --------------------------------------------------------------------------------


async def test_live_month_overview(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    lia, max_ = setup["lia"], setup["max"]
    vacation_type = PayComponentType(tenant_id=1, kind=PayComponentKind.ALLOWANCE, name="Fahrtkosten")
    section = AttributeSection(tenant_id=1, name="Lohn")
    db_session.add(section)
    await db_session.flush()
    definition = AttributeDefinition(tenant_id=1, section_id=section.id, label="Steuerklasse", field_type="TEXT", dated=True)
    other = Location(name="Filiale", timezone="UTC")
    db_session.add_all([definition, other])
    await db_session.flush()
    db_session.add_all([
        Absence(employee_id=lia.id, type=AbsenceType.VACATION, date_from=date(2026, 10, 5), date_to=date(2026, 10, 6),
                approval_status=AbsenceApprovalStatus.APPROVED),
        Absence(employee_id=lia.id, type=AbsenceType.SICK, date_from=date(2026, 10, 12), date_to=date(2026, 10, 12),
                approval_status=AbsenceApprovalStatus.APPROVED),
        EmploymentContract(tenant_id=1, employee_id=lia.id, valid_from=date(2026, 10, 1), contract_type=ContractType.FIXED_TERM,
                           job_title="Buchhaltung"),
        EmploymentContract(tenant_id=1, employee_id=max_.id, valid_from=date(2020, 1, 1), valid_to=date(2026, 10, 31),
                           contract_type=ContractType.PERMANENT),
        Compensation(tenant_id=1, employee_id=lia.id, valid_from=date(2026, 10, 1), pay_type=PayType.MONTHLY,
                     amount=Decimal("3500.00"), currency="EUR"),
        Compensation(tenant_id=1, employee_id=max_.id, valid_from=date(2020, 1, 1), pay_type=PayType.HOURLY,
                     amount=Decimal("20.50"), currency="EUR"),
        PayComponent(tenant_id=1, employee_id=lia.id, kind=PayComponentKind.ALLOWANCE, amount=Decimal("50"),
                     unit=AllowanceUnit.PER_MONTH, valid_from=date(2026, 10, 1), type=vacation_type),
        AttributeValue(tenant_id=1, employee_id=lia.id, attribute_id=definition.id, value="1", valid_from=date(2026, 10, 15)),
        EmployeeLocationPeriod(employee_id=max_.id, location_id=other.id, valid_from=date(2026, 10, 20)),
        AuditLogEntry(tenant_id=1, actor_account_id=None, action=AuditAction.PERSONAL_DATA_CHANGED, entity_type="employee",
                      entity_id=lia.id, detail="Lia Lohn: IBAN", created_at=datetime(2026, 10, 3, 9, 0)),
        AuditLogEntry(tenant_id=1, actor_account_id=None, action=AuditAction.COST_CENTERS_CHANGED, entity_type="employee",
                      entity_id=lia.id, detail="Lia Lohn: 100 100 %", created_at=datetime(2026, 9, 3, 9, 0)),
    ])
    await db_session.commit()
    await _close(db_session, max_)

    response = await client.get(f"/payroll-accounting/{MONTH}", headers=setup["admin"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["release"] is None
    assert body["includes_pay"] is True
    assert body["summary"] == {"employee_count": 2, "entries": 1, "exits": 1, "open_closures": 1}

    lia_row = _row(body, lia)
    assert lia_row["entry"] is True and lia_row["exit"] is False
    assert lia_row["closure"] == "OPEN"
    assert {a["label"]: a["days"] for a in lia_row["absences"]} == {"Urlaub": 2, "Krank": 1}
    assert lia_row["compensation"] == {"pay_type": "MONTHLY", "amount": "3500.00", "currency": "EUR", "valid_from": "2026-10-01"}
    assert lia_row["pay_components"] == [{"name": "Zulage Fahrtkosten", "amount": "50.00"}]
    texts = [c["text"] for c in lia_row["changes"]]
    assert "Eintritt" in texts
    assert "Vertrag ab: befristet, Buchhaltung" in texts
    assert "Vergütung ab: 3.500,00 € je Monat" in texts
    assert "Zulage Fahrtkosten ab: 50,00 € je Monat" in texts
    assert "Steuerklasse ab: 1" in texts
    assert "Persönliche Daten geändert: IBAN" in texts
    assert not any("Kostenstellen" in t for t in texts)  # September zählt nicht
    assert lia_row["hours"]["target_minutes"] > 0

    max_row = _row(body, max_)
    assert max_row["exit"] is True and max_row["closure"] == "CLOSED"
    max_texts = [c["text"] for c in max_row["changes"]]
    assert "Austritt" in max_texts and "Vertrag endet" in max_texts and "Standort ab: Filiale" in max_texts
    assert max_row["compensation"]["pay_type"] == "HOURLY"
    # Sortiert nach Datum
    dates = [c["date"] for c in lia_row["changes"]]
    assert dates == sorted(dates)


async def test_employees_outside_the_month_are_left_out(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    location = setup["location"]
    db_session.add_all([
        Employee(location_id=location.id, first_name="Neu", last_name="Später", employee_number="200", hire_date=date(2026, 11, 1)),
        Employee(location_id=location.id, first_name="Alt", last_name="Weg", employee_number="201", termination_date=date(2026, 9, 30)),
        Employee(location_id=location.id, first_name="Inaktiv", last_name="Ohne", employee_number="202", active=False),
        Employee(location_id=location.id, first_name="Anonym", last_name="X", employee_number="203", anonymized_at=datetime(2026, 1, 1)),
        Employee(location_id=location.id, first_name="Inaktiv", last_name="Mitdatum", employee_number="204", active=False,
                 termination_date=date(2026, 10, 15)),
    ])
    await db_session.commit()
    body = (await client.get(f"/payroll-accounting/{MONTH}", headers=setup["admin"])).json()
    numbers = sorted(row["employee_number"] for row in body["employees"])
    assert numbers == ["100", "101", "204"]


async def test_live_month_audited(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    await client.get(f"/payroll-accounting/{MONTH}", headers=setup["admin"])
    entries = (await db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.PAYROLL_ACCOUNTING_ACCESSED)
    )).scalars().all()
    assert [e.detail for e in entries] == ["Lohnbuchhaltung 2026-10 (aktueller Stand) angesehen"]
    assert entries[0].entity_type == "payroll_month" and entries[0].entity_id == 202610


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "26-10", "2026-00", "abc"])
async def test_invalid_month(client: AsyncClient, setup, month: str) -> None:
    assert (await client.get(f"/payroll-accounting/{month}", headers=setup["admin"])).status_code == 422


# --- Rechte ------------------------------------------------------------------------------------------


async def test_hr_without_payroll_access_is_rejected(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    await _account(db_session, "hr@example.com", HrRole.HR)
    hr = await _login(client, "hr@example.com")
    for path in ["/payroll-accounting/releases", f"/payroll-accounting/{MONTH}"]:
        response = await client.get(path, headers=hr)
        assert response.status_code == 403
        assert response.json()["code"] == "PAYROLL_PERMISSION_REQUIRED"


async def test_hr_with_payroll_access_can_release_but_not_revoke(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    await _account(db_session, "hr@example.com", HrRole.HR, payroll=True)
    hr = await _login(client, "hr@example.com")
    assert (await client.get(f"/payroll-accounting/{MONTH}", headers=hr)).status_code == 200
    released = await client.post(f"/payroll-accounting/{MONTH}/release", headers=hr, json={"confirm_open_closures": True})
    assert released.status_code == 201, released.text
    revoke = await client.delete(f"/payroll-accounting/{MONTH}/release", headers=hr)
    assert revoke.status_code == 403
    assert revoke.json()["code"] == "ADMIN_PERMISSION_REQUIRED"


@pytest.mark.parametrize("role", [HrRole.SUPERVISOR, None])
async def test_supervisor_and_employee_have_no_access(client: AsyncClient, db_session: AsyncSession, setup, role) -> None:
    employee = Employee(location_id=setup["location"].id, first_name="F", last_name="K", employee_number="300",
                        login_email="lead@example.com", password_hash=hash_password(PW), hr_role=role)
    db_session.add(employee)
    await db_session.commit()
    headers = await _login(client, "lead@example.com")
    assert (await client.get(f"/payroll-accounting/{MONTH}", headers=headers)).status_code == 403
    assert (await client.get("/payroll-accounting/releases", headers=headers)).status_code == 403


# --- Freigabe ----------------------------------------------------------------------------------------


async def test_release_warns_about_open_closures(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    response = await client.post(f"/payroll-accounting/{MONTH}/release", headers=setup["admin"], json={})
    assert response.status_code == 409
    assert response.json()["code"] == "OPEN_CLOSURES"
    assert "2 Mitarbeiter" in response.json()["detail"]
    assert (await db_session.execute(select(PayrollRelease))).scalars().first() is None


async def test_release_without_open_closures_needs_no_confirmation(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    await _close(db_session, setup["lia"], setup["max"])
    response = await client.post(f"/payroll-accounting/{MONTH}/release", headers=setup["admin"], json={})
    assert response.status_code == 201, response.text
    assert response.json()["release"]["open_closures"] == 0


async def test_release_freezes_snapshot_and_files(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    admin, lia = setup["admin"], setup["lia"]
    db_session.add(Compensation(tenant_id=1, employee_id=lia.id, valid_from=date(2026, 10, 1), pay_type=PayType.MONTHLY,
                                amount=Decimal("3500.00"), currency="EUR"))
    await db_session.commit()
    response = await client.post(f"/payroll-accounting/{MONTH}/release", headers=admin, json={"confirm_open_closures": True})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["release"]["month"] == MONTH
    assert body["release"]["released_by"] == "admin@example.com"
    assert body["release"]["employee_count"] == 2
    assert body["release"]["open_closures"] == 2
    assert body["release"]["has_datev"] is False
    assert body["changed_since_release"] == []

    # Verschlüsselt gespeichert: weder Name noch Betrag im Klartext
    release = (await db_session.execute(select(PayrollRelease))).scalar_one()
    for column in (release.snapshot, release.csv_file):
        assert "Lohn" not in column and "3500" not in column

    # Wie ein Export protokolliert (Hinweis „schon exportiert“ im Lohn-Export)
    logs = (await db_session.execute(select(PayrollExportLog))).scalars().all()
    assert [(log.kind, log.date_from, log.date_to, log.employee_count) for log in logs] == [
        ("CSV", date(2026, 10, 1), date(2026, 10, 31), 2)
    ]
    audit = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.PAYROLL_RELEASED))).scalar_one()
    assert "2 ohne abgeschlossenen Monat" in audit.detail

    # Nachträgliche Änderung: Schnappschuss bleibt, Vergleich zeigt die Person
    db_session.add(Absence(employee_id=lia.id, type=AbsenceType.VACATION, date_from=date(2026, 10, 20), date_to=date(2026, 10, 20),
                           approval_status=AbsenceApprovalStatus.APPROVED))
    await db_session.commit()
    frozen = (await client.get(f"/payroll-accounting/{MONTH}", headers=admin)).json()
    assert frozen["release"] is not None
    assert frozen["changed_since_release"] is None
    assert _row(frozen, lia)["absences"] == []
    compared = (await client.get(f"/payroll-accounting/{MONTH}?compare=true", headers=admin)).json()
    assert compared["changed_since_release"] == [lia.id]
    assert _row(compared, lia)["absences"] == []

    # CSV wie bei der Freigabe, gleiche Spalten wie der Lohn-Export
    file = await client.get(f"/payroll-accounting/{MONTH}/files/csv", headers=admin)
    assert file.status_code == 200
    assert file.headers["content-disposition"] == 'attachment; filename="lohnbuchhaltung_2026-10.csv"'
    rows = list(csv.DictReader(io.StringIO(file.content.decode("utf-8").lstrip("﻿")), delimiter=";"))
    assert [row["Personalnummer"] for row in rows] == ["100", "101"]
    assert rows[0]["Urlaubstage"] == "0"
    export = await client.get(
        "/payroll-export", headers=admin,
        params={"employee_ids": [lia.id, setup["max"].id], "from": "2026-10-01", "to": "2026-10-31"},
    )
    assert export.text.splitlines()[0] == file.content.decode("utf-8").splitlines()[0]
    # DATEV war nicht eingerichtet
    datev = await client.get(f"/payroll-accounting/{MONTH}/files/datev", headers=admin)
    assert datev.status_code == 404
    assert datev.json()["code"] == "FILE_NOT_AVAILABLE"


async def test_release_with_datev(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    admin = setup["admin"]
    r = await client.patch("/settings", headers=admin, json={"datev_consultant_number": "1234567", "datev_client_number": "10001"})
    assert r.status_code == 200, r.text
    response = await client.post(f"/payroll-accounting/{MONTH}/release", headers=admin, json={"confirm_open_closures": True})
    assert response.json()["release"]["has_datev"] is True
    datev = await client.get(f"/payroll-accounting/{MONTH}/files/datev", headers=admin)
    assert datev.status_code == 200
    assert datev.headers["content-type"].startswith("text/plain")
    assert "1234567" in datev.content.decode("cp1252")
    kinds = sorted(log.kind for log in (await db_session.execute(select(PayrollExportLog))).scalars())
    assert kinds == ["CSV", "DATEV"]
    listed = (await client.get("/payroll-accounting/releases", headers=admin)).json()
    assert listed[0]["has_datev"] is True


async def test_release_twice_conflicts(client: AsyncClient, setup) -> None:
    admin = setup["admin"]
    assert (await client.post(f"/payroll-accounting/{MONTH}/release", headers=admin, json={"confirm_open_closures": True})).status_code == 201
    second = await client.post(f"/payroll-accounting/{MONTH}/release", headers=admin, json={"confirm_open_closures": True})
    assert second.status_code == 409
    assert second.json()["code"] == "ALREADY_RELEASED"


async def test_future_month_cannot_be_released(client: AsyncClient, setup) -> None:
    response = await client.post("/payroll-accounting/2099-01/release", headers=setup["admin"], json={"confirm_open_closures": True})
    assert response.status_code == 400
    assert response.json()["code"] == "MONTH_IN_FUTURE"


async def test_release_body_validation(client: AsyncClient, setup) -> None:
    response = await client.post(f"/payroll-accounting/{MONTH}/release", headers=setup["admin"], json={"confirm_open_closures": "vielleicht"})
    assert response.status_code == 422


async def test_empty_month_can_be_released(client: AsyncClient, setup) -> None:
    response = await client.post("/payroll-accounting/2019-01/release", headers=setup["admin"], json={})
    assert response.status_code == 201, response.text
    assert response.json()["summary"]["employee_count"] == 0
    file = await client.get("/payroll-accounting/2019-01/files/csv", headers=setup["admin"])
    assert file.content.decode("utf-8").lstrip("﻿").startswith("Personalnummer;")


# --- Rücknahme ---------------------------------------------------------------------------------------


async def test_admin_revokes_release(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    admin = setup["admin"]
    await client.post(f"/payroll-accounting/{MONTH}/release", headers=admin, json={"confirm_open_closures": True})
    assert (await client.delete(f"/payroll-accounting/{MONTH}/release", headers=admin)).status_code == 204
    body = (await client.get(f"/payroll-accounting/{MONTH}", headers=admin)).json()
    assert body["release"] is None
    assert (await client.get("/payroll-accounting/releases", headers=admin)).json() == []
    actions = [e.action for e in (await db_session.execute(select(AuditLogEntry))).scalars()]
    assert AuditAction.PAYROLL_RELEASED in actions and AuditAction.PAYROLL_RELEASE_REVOKED in actions
    # erneut freigeben geht wieder
    assert (await client.post(f"/payroll-accounting/{MONTH}/release", headers=admin, json={"confirm_open_closures": True})).status_code == 201


async def test_revoke_unreleased_month(client: AsyncClient, setup) -> None:
    response = await client.delete(f"/payroll-accounting/{MONTH}/release", headers=setup["admin"])
    assert response.status_code == 404
    assert response.json()["code"] == "MONTH_NOT_RELEASED"


async def test_downloads_need_a_release(client: AsyncClient, setup) -> None:
    response = await client.get(f"/payroll-accounting/{MONTH}/files/csv", headers=setup["admin"])
    assert response.status_code == 404
    assert (await client.get(f"/payroll-accounting/{MONTH}/files/pdf", headers=setup["admin"])).status_code == 422


# --- Lohnbüro (eigene Rolle „Vergütung & Lohn: Ansehen“) -----------------------------------------------


async def test_payroll_office_sees_only_released_months(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    admin = setup["admin"]
    role = await _office_role(db_session)
    await _account(db_session, "stb@example.com", HrRole.HR, role)
    office = await _login(client, "stb@example.com")

    # Noch nichts freigegeben: kein aktueller Stand
    assert (await client.get("/payroll-accounting/releases", headers=office)).json() == []
    live = await client.get(f"/payroll-accounting/{MONTH}", headers=office)
    assert live.status_code == 404
    assert live.json()["code"] == "MONTH_NOT_RELEASED"
    # Freigeben verlangt Bearbeiten
    blocked = await client.post(f"/payroll-accounting/{MONTH}/release", headers=office, json={"confirm_open_closures": True})
    assert blocked.status_code == 403

    await client.post(f"/payroll-accounting/{MONTH}/release", headers=admin, json={"confirm_open_closures": True})
    listed = (await client.get("/payroll-accounting/releases", headers=office)).json()
    assert [r["month"] for r in listed] == [MONTH]
    released = await client.get(f"/payroll-accounting/{MONTH}", headers=office)
    assert released.status_code == 200
    assert released.json()["summary"]["employee_count"] == 2
    # Vergleich mit dem aktuellen Stand nur mit Bearbeiten (Live-Daten)
    assert (await client.get(f"/payroll-accounting/{MONTH}?compare=true", headers=office)).status_code == 403
    assert (await client.get(f"/payroll-accounting/{MONTH}/files/csv", headers=office)).status_code == 200
    assert (await client.delete(f"/payroll-accounting/{MONTH}/release", headers=office)).status_code == 403
    # Alles andere bleibt gesperrt
    assert (await client.get("/employees", headers=office)).status_code == 403
    assert (await client.get("/payroll-export/status?month=2026-10", headers=office)).status_code == 403

    accesses = (await db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.PAYROLL_ACCOUNTING_ACCESSED)
    )).scalars().all()
    office_id = (await db_session.execute(select(Account.id).where(Account.email == "stb@example.com"))).scalar_one()
    office_details = [e.detail for e in accesses if e.actor_account_id == office_id]
    assert "Lohnbuchhaltung 2026-10 (freigegeben) angesehen" in office_details
    assert "Lohnbuchhaltung 2026-10: CSV heruntergeladen" in office_details


async def test_payroll_edit_role_sees_live_month(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    role = Role(tenant_id=1, name="Lohn", permissions=dump_permissions({Area.PAYROLL: "EDIT"}))
    db_session.add(role)
    await db_session.commit()
    await _account(db_session, "lohn@example.com", HrRole.HR, role)
    headers = await _login(client, "lohn@example.com")
    assert (await client.get(f"/payroll-accounting/{MONTH}", headers=headers)).status_code == 200
    assert (await client.post(f"/payroll-accounting/{MONTH}/release", headers=headers, json={"confirm_open_closures": True})).status_code == 201


# --- Mandantentrennung ------------------------------------------------------------------------------


async def test_other_tenant_releases_are_invisible(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.flush()
    db_session.add(PayrollRelease(tenant_id=2, year=2026, month=10, snapshot="x", csv_file="x", employee_count=5))
    await db_session.commit()
    admin = setup["admin"]
    assert (await client.get("/payroll-accounting/releases", headers=admin)).json() == []
    body = (await client.get(f"/payroll-accounting/{MONTH}", headers=admin)).json()
    assert body["release"] is None
    assert (await client.get(f"/payroll-accounting/{MONTH}/files/csv", headers=admin)).status_code == 404


async def test_unreadable_release(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    db_session.add(PayrollRelease(tenant_id=1, year=2026, month=9, snapshot="kaputt", csv_file="kaputt", employee_count=0))
    await db_session.commit()
    response = await client.get("/payroll-accounting/2026-09", headers=setup["admin"])
    assert response.status_code == 500
    assert response.json()["code"] == "RELEASE_UNREADABLE"


async def test_snapshot_is_json_of_the_month(client: AsyncClient, db_session: AsyncSession, setup) -> None:
    from app.services.secret_box import decrypt_secret

    await client.post(f"/payroll-accounting/{MONTH}/release", headers=setup["admin"], json={"confirm_open_closures": True})
    release = (await db_session.execute(select(PayrollRelease))).scalar_one()
    data = json.loads(decrypt_secret(release.snapshot))
    assert data["month"] == MONTH and data["includes_pay"] is True
    assert {row["employee_number"] for row in data["employees"]} == {"100", "101"}
