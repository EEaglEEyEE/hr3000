"""Regressionstests zu den Review-Funden (Personalakte, Aufbewahrung, Lohnkosten, Sperren)."""
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Compensation, ContractType, Employee, EmploymentContract, HrRole, HrUser, Location, PayType, PeriodClosure, PeriodStatus
from app.services.auth_service import hash_password

PDF = b"%PDF-1.4\n%test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


async def _login(client, path, email):
    return {"Authorization": "Bearer " + (await client.post(path, json={"email": email, "password": "pw"})).json()["access_token"]}


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1")
    supervisor_employee = Employee(
        location_id=location.id, first_name="Sven", last_name="Super", employee_number="E2",
        login_email="sven@example.com", password_hash=hash_password("pw"), hr_role=HrRole.SUPERVISOR,
    )
    db_session.add_all([
        employee, supervisor_employee,
        HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
    ])
    await db_session.commit()
    return employee, supervisor_employee, {
        "hr": await _login(client, "/auth/hr/login", "hr@example.com"),
        "admin": await _login(client, "/auth/hr/login", "admin@example.com"),
        "sven": await _login(client, "/auth/employee/login", "sven@example.com"),
    }


async def _upload(client, headers, employee_id, **data):
    form = {"category": "OTHER", "title": "Dok", "employee_visible": "false", "confidential": "false", **data}
    return await client.post(f"/employees/{employee_id}/documents", headers=headers, data=form, files={"file": ("a.pdf", PDF, "application/pdf")})


async def test_supervisor_sees_own_visible_documents_but_not_others(client: AsyncClient, db_session: AsyncSession, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    employee, sven, h = await _setup(db_session, client)
    await _upload(client, h["hr"], sven.id, title="Lohnzettel", employee_visible="true")
    await _upload(client, h["hr"], sven.id, title="Intern")

    own = await client.get(f"/employees/{sven.id}/documents", headers=h["sven"])
    assert own.status_code == 200 and [d["title"] for d in own.json()] == ["Lohnzettel"]
    assert (await client.get(f"/employees/{employee.id}/documents", headers=h["sven"])).status_code == 403
    assert (await client.get(f"/employees/{employee.id}/data-export", headers=h["sven"])).status_code == 403


async def test_only_admin_shortens_retention_and_period_evidence_cannot_be_deleted(client: AsyncClient, db_session: AsyncSession, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    employee, _, h = await _setup(db_session, client)
    doc = (await _upload(client, h["hr"], employee.id, retention_until="2030-01-01")).json()
    url = f"/employees/{employee.id}/documents/{doc['id']}"
    assert (await client.patch(url, headers=h["hr"], json={"clear_retention_until": True})).status_code == 403
    assert (await client.patch(url, headers=h["hr"], json={"retention_until": "2029-01-01"})).status_code == 403
    assert (await client.patch(url, headers=h["hr"], json={"retention_until": "2031-01-01"})).status_code == 200
    assert (await client.patch(url, headers=h["admin"], json={"clear_retention_until": True})).status_code == 200

    db_session.add(PeriodClosure(
        tenant_id=1, employee_id=employee.id, year=2025, month=3, status=PeriodStatus.CLOSED, target_minutes=0,
        actual_minutes=0, delta_minutes=0, balance_end_minutes=0, document_id=doc["id"], submitted_at=date(2025, 4, 1),
    ))
    await db_session.commit()
    blocked = await client.delete(url, headers=h["admin"])
    assert blocked.status_code == 409 and blocked.json()["code"] == "DOCUMENT_PART_OF_PERIOD_CLOSURE"


async def test_labor_costs_split_at_rate_change(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, _, h = await _setup(db_session, client)
    db_session.add_all([
        Compensation(tenant_id=1, employee_id=employee.id, valid_from=date(2025, 1, 1), valid_to=date(2025, 4, 14), pay_type=PayType.HOURLY, amount=15, currency="EUR"),
        Compensation(tenant_id=1, employee_id=employee.id, valid_from=date(2025, 4, 15), pay_type=PayType.HOURLY, amount=20, currency="EUR"),
    ])
    await db_session.commit()
    for punch_type, ts in (("COME", "2025-04-10T08:00:00Z"), ("GO", "2025-04-10T12:00:00Z"), ("COME", "2025-04-16T08:00:00Z"), ("GO", "2025-04-16T12:00:00Z")):
        r = await client.post("/punches", headers=h["hr"], json={"employee_id": employee.id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())})
        assert r.status_code == 201
    report = (await client.get("/reports/labor-costs?from=2025-04-01&to=2025-04-30", headers=h["admin"])).json()
    row = next(r for r in report["rows"] if r["employee_id"] == employee.id)
    assert row["base_cost"] == 4 * 15 + 4 * 20 and "Satzwechsel" in row["note"]


async def test_amount_has_at_most_cents_and_contract_update_cannot_overlap(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, _, h = await _setup(db_session, client)
    bad = await client.post(f"/employees/{employee.id}/compensation", headers=h["admin"], json={"valid_from": "2025-01-01", "pay_type": "HOURLY", "amount": 12.345})
    assert bad.status_code == 422

    db_session.add_all([
        EmploymentContract(tenant_id=1, employee_id=employee.id, valid_from=date(2024, 1, 1), valid_to=date(2024, 12, 31), contract_type=ContractType.PERMANENT),
        EmploymentContract(tenant_id=1, employee_id=employee.id, valid_from=date(2025, 1, 1), contract_type=ContractType.PERMANENT),
    ])
    await db_session.commit()
    contracts = (await client.get(f"/employees/{employee.id}/contracts", headers=h["hr"])).json()
    old = next(c for c in contracts if c["valid_from"] == "2024-01-01")
    reopened = await client.patch(f"/employees/{employee.id}/contracts/{old['id']}", headers=h["hr"], json={"clear_valid_to": True})
    assert reopened.status_code == 400 and reopened.json()["code"] == "OVERLAPPING_PERIOD"


async def test_holiday_in_locked_month_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, _, h = await _setup(db_session, client)
    db_session.add(PeriodClosure(
        tenant_id=1, employee_id=employee.id, year=2025, month=3, status=PeriodStatus.SUBMITTED, target_minutes=0,
        actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=date(2025, 4, 1),
    ))
    await db_session.commit()
    locked = await client.post("/holidays", headers=h["hr"], json={"date": "2025-03-12", "name": "Neu", "location_ids": []})
    assert locked.status_code == 409 and locked.json()["code"] == "PERIOD_LOCKED"
    assert (await client.post("/holidays", headers=h["hr"], json={"date": "2025-04-12", "name": "Neu", "location_ids": []})).status_code == 201


async def test_tenant_logo_upload_validation_and_public_branding(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, h = await _setup(db_session, client)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    assert (await client.put("/settings/logo", headers=h["hr"], files={"file": ("l.png", png, "image/png")})).status_code == 403
    svg = await client.put("/settings/logo", headers=h["admin"], files={"file": ("l.svg", b"<svg onload=alert(1)>", "image/svg+xml")})
    assert svg.status_code == 400
    big = await client.put("/settings/logo", headers=h["admin"], files={"file": ("l.png", png + b"0" * 300_000, "image/png")})
    assert big.status_code == 413
    ok = await client.put("/settings/logo", headers=h["admin"], files={"file": ("l.png", png, "image/png")})
    assert ok.status_code == 200 and ok.json()["logo_data_url"].startswith("data:image/png;base64,")

    public = (await client.get("/branding")).json()  # ohne Anmeldung
    assert public["logo_data_url"] == ok.json()["logo_data_url"] and public["tenant_name"]
    assert (await client.delete("/settings/logo", headers=h["admin"])).status_code == 204
    assert (await client.get("/branding")).json()["logo_data_url"] is None
