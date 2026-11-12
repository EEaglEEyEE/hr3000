"""Recruiting: „Als Mitarbeiter übernehmen“ – Anlage über den üblichen Weg, Dokumente, Checkliste."""
from datetime import date

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import (
    AuditAction,
    AuditLogEntry,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Employee,
    EmployeeChecklist,
    EmployeeDocument,
    RecruitingApplication,
)
from app.models.checklist import ChecklistKind
from app.services import document_service, personal_data_service
from tests.recruiting_helpers import PDF, PNG, company, create_application, create_job, other_company


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


async def _hired(client, db_session, *, stage="HIRED", attachments=True, **company_args):
    ctx = await company(db_session, client, **company_args)
    job = await create_job(client, ctx.headers["admin"], member_account_ids=[ctx.accounts["lead"].id])
    app = await create_application(client, ctx.headers["admin"], job["id"], phone="0151 222")
    ids = []
    if attachments:
        for name, data, kind in (("lebenslauf.pdf", PDF, "CV"), ("zeugnis.png", PNG, "OTHER")):
            body = (await client.post(
                f"/recruiting/applications/{app['id']}/attachments", files={"file": (name, data)}, data={"kind": kind},
                headers=ctx.headers["admin"],
            )).json()
            ids.append(body["attachments"][-1]["id"])
    if stage:
        await client.post(f"/recruiting/applications/{app['id']}/stage", json={"stage": stage}, headers=ctx.headers["admin"])
    return ctx, job, app, ids


def _payload(ctx, **overrides) -> dict:
    payload = {
        "employee_number": "P-100",
        "location_id": ctx.location.id,
        "department_id": ctx.department.id,
        "hire_date": "2026-12-01",
        "position": "Sachbearbeitung",
    }
    payload.update(overrides)
    return payload


async def test_hire_creates_employee_documents_and_checklist(client, db_session) -> None:
    ctx, job, app, ids = await _hired(client, db_session)
    template = ChecklistTemplate(tenant_id=1, kind=ChecklistKind.ONBOARDING, name="Onboarding Büro")
    db_session.add(template)
    await db_session.flush()
    db_session.add(ChecklistTemplateItem(template_id=template.id, position=0, title="Laptop bestellen", due_offset_days=-3))
    await db_session.commit()

    response = await client.post(
        f"/recruiting/applications/{app['id']}/hire",
        json=_payload(ctx, attachment_ids=ids, document_category="CERTIFICATE", checklist_template_id=template.id,
                      private_email="privat@example.com"),
        headers=ctx.headers["hr"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["documents_copied"] == 2 and body["checklist_started"] is True
    employee = await db_session.get(Employee, body["employee_id"])
    assert (employee.first_name, employee.last_name, employee.employee_number) == ("Bea", "Bewerber", "P-100")
    assert employee.hire_date == date(2026, 12, 1) and employee.department_id == ctx.department.id
    assert employee.position == "Sachbearbeitung" and employee.location_id == ctx.location.id
    personal = await personal_data_service.load(db_session, employee.id)
    assert personal == {"private_email": "privat@example.com", "phone": "0151 222"}
    documents = (await db_session.execute(select(EmployeeDocument).where(EmployeeDocument.employee_id == employee.id).order_by(EmployeeDocument.id))).scalars().all()
    assert [d.title for d in documents] == ["Lebenslauf", "Bewerbung: zeugnis.png"]
    assert all(d.category.value == "CERTIFICATE" and not d.employee_visible and not d.confidential for d in documents)
    assert await document_service.read_document_bytes(documents[0].storage_key) == PDF
    checklist = (await db_session.execute(select(EmployeeChecklist).where(EmployeeChecklist.employee_id == employee.id))).scalar_one()
    assert checklist.name == "Onboarding Büro" and checklist.anchor_date == date(2026, 12, 1)

    application = await db_session.get(RecruitingApplication, app["id"])
    assert application.employee_id == employee.id and application.hired_at is not None
    detail = (await client.get(f"/recruiting/applications/{app['id']}", headers=ctx.headers["admin"])).json()
    assert detail["employee_id"] == employee.id
    actions = {e.action for e in (await db_session.execute(select(AuditLogEntry))).scalars().all()}
    assert {AuditAction.EMPLOYEE_CREATED, AuditAction.DOCUMENT_UPLOADED, AuditAction.CHECKLIST_STARTED} <= actions


async def test_hire_defaults_to_application_data(client, db_session) -> None:
    ctx, _, app, _ = await _hired(client, db_session, attachments=False)
    body = (await client.post(f"/recruiting/applications/{app['id']}/hire", json=_payload(ctx, first_name="Beate"), headers=ctx.headers["admin"])).json()
    assert body == {"employee_id": body["employee_id"], "documents_copied": 0, "checklist_started": False}
    employee = await db_session.get(Employee, body["employee_id"])
    assert employee.first_name == "Beate" and employee.last_name == "Bewerber"
    assert (await personal_data_service.load(db_session, employee.id))["private_email"] == "bea@example.com"


async def test_double_hire_is_prevented(client, db_session) -> None:
    ctx, _, app, _ = await _hired(client, db_session, attachments=False)
    url = f"/recruiting/applications/{app['id']}/hire"
    assert (await client.post(url, json=_payload(ctx), headers=ctx.headers["admin"])).status_code == 201
    again = await client.post(url, json=_payload(ctx, employee_number="P-101"), headers=ctx.headers["admin"])
    assert again.status_code == 409 and again.json()["code"] == "RECRUITING_ALREADY_HIRED"
    assert len((await db_session.execute(select(Employee).where(Employee.employee_number.in_(["P-100", "P-101"])))).scalars().all()) == 1
    stage = await client.post(f"/recruiting/applications/{app['id']}/stage", json={"stage": "REJECTED", "rejection_reason": "OTHER"}, headers=ctx.headers["admin"])
    assert stage.status_code == 409


async def test_hire_needs_stage_hired(client, db_session) -> None:
    ctx, _, app, _ = await _hired(client, db_session, stage="OFFER", attachments=False)
    response = await client.post(f"/recruiting/applications/{app['id']}/hire", json=_payload(ctx), headers=ctx.headers["admin"])
    assert response.status_code == 409 and response.json()["code"] == "RECRUITING_NOT_HIRED"


@pytest.mark.parametrize("role", ["lead", "staff"])
async def test_only_full_hr_can_hire(client, db_session, role) -> None:
    ctx, _, app, _ = await _hired(client, db_session, attachments=False)
    response = await client.post(f"/recruiting/applications/{app['id']}/hire", json=_payload(ctx), headers=ctx.headers[role])
    assert response.status_code in (403, 404)


async def test_foreign_company_cannot_hire(client, db_session) -> None:
    ctx, _, app, _ = await _hired(client, db_session, attachments=False)
    acme = await other_company(db_session, client)
    assert (await client.post(f"/recruiting/applications/{app['id']}/hire", json=_payload(ctx), headers=acme)).status_code == 404


async def test_hire_checks_before_creating_anything(client, db_session) -> None:
    ctx, job, app, ids = await _hired(client, db_session)
    other = await create_application(client, ctx.headers["admin"], job["id"], email="o@example.com")
    foreign_attachment = (await client.post(
        f"/recruiting/applications/{other['id']}/attachments", files={"file": ("x.pdf", PDF)}, headers=ctx.headers["admin"]
    )).json()["attachments"][0]["id"]
    offboarding = ChecklistTemplate(tenant_id=1, kind=ChecklistKind.OFFBOARDING, name="Austritt")
    db_session.add(offboarding)
    await db_session.commit()
    url = f"/recruiting/applications/{app['id']}/hire"
    before = len((await db_session.execute(select(Employee))).scalars().all())
    for payload, status in (
        (_payload(ctx, attachment_ids=[foreign_attachment]), 404),
        (_payload(ctx, checklist_template_id=offboarding.id), 404),
        (_payload(ctx, checklist_template_id=999), 404),
        (_payload(ctx, location_id=999), 404),
        (_payload(ctx, department_id=999), 404),
    ):
        response = await client.post(url, json=payload, headers=ctx.headers["admin"])
        assert response.status_code == status, payload
    assert len((await db_session.execute(select(Employee))).scalars().all()) == before
    assert (await db_session.get(RecruitingApplication, app["id"])).employee_id is None


async def test_hire_missing_file_is_410_before_creating(client, db_session) -> None:
    ctx, _, app, ids = await _hired(client, db_session)
    from app.models import RecruitingAttachment

    row = await db_session.get(RecruitingAttachment, ids[0])
    document_service._path_for(row.storage_key).unlink()
    before = len((await db_session.execute(select(Employee))).scalars().all())
    response = await client.post(f"/recruiting/applications/{app['id']}/hire", json=_payload(ctx, attachment_ids=ids), headers=ctx.headers["admin"])
    assert response.status_code == 410
    assert len((await db_session.execute(select(Employee))).scalars().all()) == before


async def test_hire_duplicate_employee_number_is_409_and_not_linked(client, db_session) -> None:
    ctx, _, app, _ = await _hired(client, db_session, attachments=False)
    response = await client.post(f"/recruiting/applications/{app['id']}/hire", json=_payload(ctx, employee_number="N-admin"), headers=ctx.headers["admin"])
    assert response.status_code == 409 and response.json()["code"] == "EMPLOYEE_NUMBER_TAKEN"
    application = (await db_session.execute(select(RecruitingApplication).where(RecruitingApplication.id == app["id"]))).scalar_one()
    await db_session.refresh(application)
    assert application.employee_id is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"employee_number": ""},
        {"hire_date": "1999-01-01"},
        {"hire_date": None},
        {"location_id": 0},
        {"attachment_ids": [1, 1]},
        {"attachment_ids": [0]},
        {"document_category": "GEHEIM"},
        {"private_email": "kaputt"},
        {"position": "x" * 151},
    ],
)
async def test_hire_validation(client, db_session, overrides) -> None:
    ctx, _, app, _ = await _hired(client, db_session, attachments=False)
    response = await client.post(f"/recruiting/applications/{app['id']}/hire", json=_payload(ctx, **overrides), headers=ctx.headers["admin"])
    assert response.status_code == 422


async def test_hired_employee_keeps_link_when_application_is_deleted(client, db_session) -> None:
    ctx, _, app, _ = await _hired(client, db_session, attachments=False)
    employee_id = (await client.post(f"/recruiting/applications/{app['id']}/hire", json=_payload(ctx), headers=ctx.headers["admin"])).json()["employee_id"]
    assert (await client.delete(f"/recruiting/applications/{app['id']}", headers=ctx.headers["admin"])).status_code == 204
    assert await db_session.get(Employee, employee_id) is not None


async def test_hire_respects_plan_limit(client, db_session) -> None:
    from app.models import TenantPlan

    ctx, _, app, _ = await _hired(client, db_session, attachments=False, plan=TenantPlan.FREE)
    response = await client.post(f"/recruiting/applications/{app['id']}/hire", json=_payload(ctx), headers=ctx.headers["admin"])
    assert response.status_code == 402
    assert (await db_session.get(RecruitingApplication, app["id"])).employee_id is None


async def test_link_survives_failure_after_employee_creation(client, db_session, monkeypatch) -> None:
    from app.errors import AppError

    ctx, _, app, ids = await _hired(client, db_session)

    async def full_quota(*args, **kwargs):
        raise AppError(413, "TENANT_STORAGE_FULL", "Speicher voll.")

    monkeypatch.setattr(document_service, "store_document", full_quota)
    url = f"/recruiting/applications/{app['id']}/hire"
    failed = await client.post(url, json=_payload(ctx, attachment_ids=ids), headers=ctx.headers["admin"])
    assert failed.status_code == 413
    application = await db_session.get(RecruitingApplication, app["id"])
    await db_session.refresh(application)
    assert application.employee_id is not None
    assert await db_session.get(Employee, application.employee_id) is not None
    again = await client.post(url, json=_payload(ctx, employee_number="P-101"), headers=ctx.headers["admin"])
    assert again.status_code == 409 and again.json()["code"] == "RECRUITING_ALREADY_HIRED"
