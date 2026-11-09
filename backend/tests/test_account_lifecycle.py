"""Kündigung und endgültige Löschung von Firmen (services/tenant_lifecycle.py, api/plan.py,
api/tenants.py, tools/purge_tenants.py) – so, wie es Nutzungsbedingungen und AV-Vertrag zusagen."""

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, update

from app.config import settings
from app.models import Base, EmployeeDocument, HrRole, Account, Tenant
from app.services.auth_service import hash_password
from app.services.tenant_lifecycle import (
    PLATFORM_TABLES,
    cancellation_dates,
    purge_plan,
    purge_tenant,
    tenant_row_counts,
    tenants_due_for_purge,
)
from app.services.tenant_provisioning import provision_tenant
from app.tools import purge_tenants as purge_tool

A_HOST = {"Host": "musterfirma.hr3000.de"}
B_HOST = {"Host": "zweite.hr3000.de"}


@pytest.fixture(autouse=True)
def _platform(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "tenant_base_domain", "hr3000.de")
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


async def _admin_token(client, host: dict, email: str, password: str = "sehr-geheim-123") -> dict:
    response = await client.post("/auth/login", json={"email": email, "password": password}, headers=host)
    assert response.status_code == 200, response.text
    return {**host, "Authorization": f"Bearer {response.json()['access_token']}"}


async def _setup_two_tenants(client, db_session) -> tuple[dict, dict, int]:
    db_session.add(Account(email="a@musterfirma.example", password_hash=hash_password("sehr-geheim-123"), role=HrRole.ADMIN))
    await db_session.commit()
    b = await provision_tenant(
        db_session, subdomain="zweite", name="Zweite GmbH", admin_email="b@zweite.example", admin_password="sehr-geheim-123"
    )
    return (
        await _admin_token(client, A_HOST, "a@musterfirma.example"),
        await _admin_token(client, B_HOST, "b@zweite.example"),
        b.id,
    )


async def _fill(client, h: dict) -> None:
    """Dieselben Daten in einer Firma: Stammdaten, Zeiten, Abwesenheiten, Dokument, Checklisten …"""
    loc = (await client.post("/locations", json={"name": "Zentrale", "timezone": "Europe/Berlin"}, headers=h)).json()["id"]
    department = (await client.post("/departments", json={"name": "Werkstatt"}, headers=h)).json()["id"]
    assert (await client.post("/devices", json={"name": "Tablet", "location_id": loc}, headers=h)).status_code == 201
    assert (await client.post("/holidays", json={"date": "2026-12-24", "name": "Heiligabend", "location_ids": [loc]}, headers=h)).status_code == 201
    emp = await client.post(
        "/employees",
        json={"location_id": loc, "first_name": "Erika", "last_name": "Muster", "employee_number": "E-1", "department_id": department},
        headers=h,
    )
    assert emp.status_code == 201, emp.text
    eid = emp.json()["id"]
    # Leitung der eigenen Abteilung: Abteilung und Mitarbeiter verweisen gegenseitig aufeinander
    assert (await client.patch(f"/departments/{department}", json={"head_employee_id": eid}, headers=h)).status_code == 200
    for kind, ts, key in (("COME", "2026-10-05T06:00:00Z", "1"), ("GO", "2026-10-05T14:30:00Z", "2")):
        r = await client.post(
            "/punches",
            json={"employee_id": eid, "punch_type": kind, "timestamp_utc": ts, "idempotency_key": f"{h['Host'][:8]}-0000-0000-0000-00000000000{key}"},
            headers=h,
        )
        assert r.status_code in (200, 201), r.text
    assert (await client.post("/absences", json={"employee_id": eid, "type": "VACATION", "date_from": "2026-10-12", "date_to": "2026-10-13"}, headers=h)).status_code == 201
    assert (await client.patch(f"/employees/{eid}/leave-entitlement?year=2026", json={"entitled_days": 30}, headers=h)).status_code == 200
    assert (await client.post(f"/employees/{eid}/balance-adjustments", json={"effective_date": "2026-10-01", "minutes": 60, "kind": "CORRECTION", "note": "Test"}, headers=h)).status_code == 201
    doc = await client.post(
        f"/employees/{eid}/documents",
        data={"category": "CONTRACT", "title": "Vertrag"},
        files={"file": ("vertrag.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers=h,
    )
    assert doc.status_code == 201, doc.text
    templates = (await client.post("/checklist-templates/defaults", headers=h)).json()
    assert (await client.post(f"/employees/{eid}/checklists", json={"template_id": templates[0]["id"]}, headers=h)).status_code == 201
    assert (await client.post("/surcharge-rules/defaults", headers=h)).status_code == 201
    await client.get("/timesheet/open-days", headers=h)  # füllt den Tages-Cache


async def _totals(db_session) -> dict[str, int]:
    return {
        t.name: await db_session.scalar(select(func.count()).select_from(t))
        for t in Base.metadata.sorted_tables
        if t.name not in PLATFORM_TABLES
    }


# --- Löschen -------------------------------------------------------------------------------


def test_every_table_is_covered():
    # Neue Tabelle ohne tenant_id und ohne Bezug zu einer Firmentabelle -> purge_plan scheitert.
    plan = purge_plan(1)
    assert {s.table.name for s in plan} == {t.name for t in Base.metadata.sorted_tables} - PLATFORM_TABLES
    # Plattform-Tabellen bleiben eine kurze, bewusste Liste
    assert PLATFORM_TABLES == {"tenants", "server_metric_samples"}


async def test_purge_removes_everything_of_one_company_and_nothing_else(client, db_session):
    a_headers, b_headers, b_id = await _setup_two_tenants(client, db_session)
    await _fill(client, a_headers)
    await _fill(client, b_headers)

    b_before = await tenant_row_counts(db_session, b_id)
    a_before = await tenant_row_counts(db_session, 1)
    totals_before = await _totals(db_session)
    filled = sorted(t for t, n in b_before.items() if n)
    assert len(filled) >= 15, filled  # der Test soll wirklich viele Tabellen abdecken
    b_files = [
        Path(settings.documents_dir) / k[:2] / k
        for k in (await db_session.scalars(select(EmployeeDocument.storage_key).where(EmployeeDocument.tenant_id == b_id))).all()
    ]
    assert b_files and all(p.exists() for p in b_files)

    await purge_tenant(db_session, b_id)

    assert await db_session.get(Tenant, b_id) is None
    assert all(n == 0 for n in (await tenant_row_counts(db_session, b_id)).values())
    assert await tenant_row_counts(db_session, 1) == a_before  # andere Firma unberührt
    totals_after = await _totals(db_session)
    assert all(totals_after[t] == totals_before[t] - b_before[t] for t in totals_before)
    assert not any(p.exists() for p in b_files)  # verschlüsselte Dateien weg
    # Firma A arbeitet normal weiter.
    assert (await client.get("/employees", headers=a_headers)).status_code == 200
    # Adresse von B ist wieder frei, die alte Anmeldung tot.
    assert (await client.get("/branding", headers=B_HOST)).status_code in (200, 404)
    assert (await client.get("/employees", headers=b_headers)).status_code in (401, 404)


# --- Kündigung durch den Firmen-Admin --------------------------------------------------------


def test_cancellation_dates():
    assert cancellation_dates(date(2026, 11, 4)) == (date(2026, 11, 30), date(2026, 12, 30))
    assert cancellation_dates(date(2026, 12, 31)) == (date(2026, 12, 31), date(2027, 1, 30))
    assert cancellation_dates(date(2028, 2, 1)) == (date(2028, 2, 29), date(2028, 3, 30))  # Schaltjahr


async def test_admin_cancels_and_revokes(client, db_session):
    a_headers, _, _ = await _setup_two_tenants(client, db_session)
    plan = (await client.get("/plan", headers=a_headers)).json()
    assert plan["cancelled_at"] is None

    wrong = await client.post("/account/cancel", json={"confirm_subdomain": "falsch"}, headers=a_headers)
    assert wrong.status_code == 400 and wrong.json()["code"] == "CONFIRMATION_MISMATCH"

    done = await client.post("/account/cancel", json={"confirm_subdomain": " MusterFirma "}, headers=a_headers)
    assert done.status_code == 200, done.text
    body = done.json()
    contract_end, due = cancellation_dates(datetime.utcnow().date())
    assert (body["contract_end"], body["deletion_due_on"]) == (contract_end.isoformat(), due.isoformat())
    # Zweites Kündigen ändert die Daten nicht.
    again = (await client.post("/account/cancel", json={"confirm_subdomain": "musterfirma"}, headers=a_headers)).json()
    assert again["deletion_due_on"] == body["deletion_due_on"]
    # Bis zur Löschung normal nutzbar (Export!).
    assert (await client.get("/employees", headers=a_headers)).status_code == 200
    # Audit-Protokoll vermerkt es.
    audit = (await client.get("/audit-log", headers=a_headers)).json()
    entries = audit["items"] if isinstance(audit, dict) else audit
    assert any("Gekündigt zum" in (e.get("detail") or "") for e in entries)

    revoked = (await client.post("/account/cancel/revoke", headers=a_headers)).json()
    assert revoked["cancelled_at"] is None and revoked["deletion_due_on"] is None


async def test_only_admins_may_cancel(client, db_session):
    await _setup_two_tenants(client, db_session)
    db_session.add(Account(email="hr@musterfirma.example", password_hash=hash_password("sehr-geheim-123"), role=HrRole.HR))
    await db_session.commit()
    hr = await _admin_token(client, A_HOST, "hr@musterfirma.example")
    response = await client.post("/account/cancel", json={"confirm_subdomain": "musterfirma"}, headers=hr)
    assert response.status_code == 403


# --- Fälligkeit, Cron-Werkzeug ---------------------------------------------------------------


async def test_due_tenants_and_purge_tool(client, db_session, capsys):
    _, _, b_id = await _setup_two_tenants(client, db_session)
    today = datetime.utcnow().date()
    await db_session.execute(update(Tenant).where(Tenant.id == b_id).values(deletion_due_on=today + timedelta(days=1)))
    await db_session.commit()
    assert [t.id for t in await tenants_due_for_purge(db_session)] == []  # erst morgen fällig
    await db_session.execute(update(Tenant).where(Tenant.id == b_id).values(deletion_due_on=today))
    await db_session.commit()
    assert [t.id for t in await tenants_due_for_purge(db_session)] == [b_id]


async def test_unverified_self_signups_expire_after_seven_days(client, db_session):
    old = await provision_tenant(
        db_session, subdomain="alt", name="Alt", admin_email="x@alt.example", admin_password="sehr-geheim-123",
        self_signup=True, admin_email_verification_pending=True,
    )
    fresh = await provision_tenant(
        db_session, subdomain="frisch", name="Frisch", admin_email="x@frisch.example", admin_password="sehr-geheim-123",
        self_signup=True, admin_email_verification_pending=True,
    )
    confirmed = await provision_tenant(
        db_session, subdomain="bestaetigt", name="Bestätigt", admin_email="x@b.example", admin_password="sehr-geheim-123",
        self_signup=True,
    )
    eight_days_ago = datetime.utcnow() - timedelta(days=8)
    await db_session.execute(update(Tenant).where(Tenant.id.in_([old.id, confirmed.id])).values(created_at=eight_days_ago))
    await db_session.commit()
    assert [t.subdomain for t in await tenants_due_for_purge(db_session)] == ["alt"]
    assert fresh.id  # noch keine 7 Tage


async def test_purge_tool_dry_run_and_run(client, db_session, monkeypatch, capsys):
    import app.db

    _, _, b_id = await _setup_two_tenants(client, db_session)
    await db_session.execute(update(Tenant).where(Tenant.id == b_id).values(deletion_due_on=date(2020, 1, 1)))
    await db_session.commit()

    class _SessionFactory:  # das Werkzeug öffnet eigene Sessions -> auf die Test-Session lenken
        def __call__(self):
            return self

        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(app.db, "AsyncSessionLocal", _SessionFactory())
    assert await purge_tool._main(dry_run=True) == 0
    assert "würde löschen zweite" in capsys.readouterr().out
    assert await db_session.get(Tenant, b_id) is not None
    assert await purge_tool._main(dry_run=False) == 0
    assert "gelöscht zweite" in capsys.readouterr().out
    db_session.expire_all()
    assert await db_session.get(Tenant, b_id) is None
    assert await purge_tool._main(dry_run=False) == 0
    assert "nichts fällig" in capsys.readouterr().out


# --- Super-Admin ------------------------------------------------------------------------------


async def _super_admin(client, db_session) -> dict:
    db_session.add(Account(tenant_id=None, email="chef@example.com", password_hash=hash_password("sehr-geheim-123"), role=HrRole.SUPER_ADMIN))
    await db_session.commit()
    return await _admin_token(client, {"Host": settings.super_admin_hostname}, "chef@example.com")


async def test_super_admin_cancels_revokes_and_purges(client, db_session):
    _, _, b_id = await _setup_two_tenants(client, db_session)
    sa = await _super_admin(client, db_session)

    cancelled = (await client.post(f"/tenants/{b_id}/cancel", headers=sa)).json()
    assert cancelled["deletion_due_on"] is not None
    listed = {t["subdomain"]: t for t in (await client.get("/tenants", headers=sa)).json()}
    assert listed["zweite"]["deletion_due_on"] == cancelled["deletion_due_on"]
    assert (await client.post(f"/tenants/{b_id}/cancel/revoke", headers=sa)).json()["deletion_due_on"] is None

    wrong = await client.post(f"/tenants/{b_id}/purge", json={"confirm_subdomain": "musterfirma"}, headers=sa)
    assert wrong.status_code == 400
    purged = await client.post(f"/tenants/{b_id}/purge", json={"confirm_subdomain": "zweite"}, headers=sa)
    assert purged.status_code == 200, purged.text
    assert purged.json()["subdomain"] == "zweite" and purged.json()["deleted_rows"] > 0
    assert "zweite" not in {t["subdomain"] for t in (await client.get("/tenants", headers=sa)).json()}
    assert (await client.post("/tenants/999/purge", json={"confirm_subdomain": "x"}, headers=sa)).status_code == 404


async def test_tenant_admin_cannot_use_platform_endpoints(client, db_session):
    a_headers, _, b_id = await _setup_two_tenants(client, db_session)
    for path in (f"/tenants/{b_id}/cancel", f"/tenants/{b_id}/cancel/revoke"):
        assert (await client.post(path, headers=a_headers)).status_code == 403
    assert (await client.post(f"/tenants/{b_id}/purge", json={"confirm_subdomain": "zweite"}, headers=a_headers)).status_code == 403
