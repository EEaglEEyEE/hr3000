"""Recruiting: öffentliche Karriereseite und Bewerbung ohne Anmeldung."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import (
    AuditAction,
    AuditLogEntry,
    Notification,
    NotificationType,
    RecruitingApplication,
    RecruitingAttachment,
)
from app.services import document_service, recruiting_service
from tests.recruiting_helpers import (
    HTML,
    JPEG,
    PDF,
    PNG,
    apply,
    apply_form,
    company,
    create_job,
    enable,
    other_company,
)


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


async def test_careers_page_lists_only_public_jobs(client, db_session) -> None:
    ctx = await company(db_session, client)
    await enable(db_session, recruiting_privacy_text="Wir verarbeiten Ihre Daten …", recruiting_privacy_url="https://example.com/datenschutz")
    await create_job(client, ctx.headers["admin"], title="Öffentlich", department_id=ctx.department.id, location_id=ctx.location.id)
    await create_job(client, ctx.headers["admin"], title="Entwurf", status="DRAFT")
    await create_job(client, ctx.headers["admin"], title="Geschlossen", status="CLOSED")
    await create_job(client, ctx.headers["admin"], title="Abgelaufen", application_deadline=str(date.today() - timedelta(days=1)))
    response = await client.get("/public/careers")
    assert response.status_code == 200
    body = response.json()
    assert body["company_name"] == "Musterfirma"
    assert body["privacy_url"] == "https://example.com/datenschutz" and body["privacy_text"].startswith("Wir verarbeiten")
    assert [j["title"] for j in body["jobs"]] == ["Öffentlich"]
    job = body["jobs"][0]
    assert job["slug"] == "oeffentlich" and job["department"] == "Vertrieb" and job["location"] == "Zentrale"
    assert "description" not in job and "members" not in job


async def test_job_detail_only_for_public_jobs(client, db_session) -> None:
    ctx = await company(db_session, client)
    public = await create_job(client, ctx.headers["admin"])
    draft = await create_job(client, ctx.headers["admin"], status="DRAFT")
    detail = (await client.get(f"/public/careers/jobs/{public['id']}")).json()
    assert detail["description"].startswith("Wir suchen") and detail["max_files"] == recruiting_service.MAX_ATTACHMENTS
    assert detail["max_file_mb"] == 10 and detail["company_name"] == "Musterfirma"
    for job_id in (draft["id"], 999):
        response = await client.get(f"/public/careers/jobs/{job_id}")
        assert response.status_code == 404 and response.json()["code"] == "RECRUITING_JOB_NOT_FOUND"
    assert (await apply(client, draft["id"])).status_code == 404


async def test_switch_off_hides_careers_page(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    row = await enable(db_session)
    row.recruiting_enabled = False
    await db_session.commit()
    for response in (
        await client.get("/public/careers"),
        await client.get(f"/public/careers/jobs/{job['id']}"),
        await apply(client, job["id"]),
    ):
        assert response.status_code == 404 and response.json()["code"] == "CAREERS_NOT_FOUND"


async def test_other_subdomain_sees_only_its_own_jobs(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    acme_admin = await other_company(db_session, client)
    acme_job = await create_job(client, acme_admin, title="Acme-Stelle")
    acme = {"X-Tenant-Subdomain": "acme"}
    body = (await client.get("/public/careers", headers=acme)).json()
    assert body["company_name"] == "Acme GmbH" and [j["title"] for j in body["jobs"]] == ["Acme-Stelle"]
    assert (await client.get(f"/public/careers/jobs/{job['id']}", headers=acme)).status_code == 404
    assert (await apply(client, job["id"], headers=acme)).status_code == 404
    assert (await client.get(f"/public/careers/jobs/{acme_job['id']}")).status_code == 404


async def test_unknown_subdomain_is_404(client, db_session, monkeypatch) -> None:
    await company(db_session, client)
    monkeypatch.setattr(settings, "dev_default_tenant_subdomain", "gibt-es-nicht")
    response = await client.get("/public/careers", headers={"X-Tenant-Subdomain": "unbekannt"})
    assert response.status_code == 404


async def test_apply_stores_encrypted_application_with_attachments(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"], member_account_ids=[ctx.accounts["staff"].id])
    files = [
        ("cv", ("Lebenslauf.pdf", PDF, "application/pdf")),
        ("attachments", ("zeugnis.png", PNG, "image/png")),
        ("attachments", ("foto.jpg", JPEG, "image/jpeg")),
    ]
    data = apply_form(phone="+49 30 123", cover_letter="Hallo!", salary_expectation="45k", talent_pool="true")
    response = await apply(client, job["id"], data=data, files=files)
    assert response.status_code == 201 and response.json() == {"received": True}
    application = (await db_session.execute(select(RecruitingApplication))).scalar_one()
    assert application.source == "CAREER_PAGE" and application.stage == "NEW" and application.talent_pool is True
    assert application.privacy_acknowledged_at is not None and application.created_by_account_id is None
    assert "Hallo" not in application.cover_letter_encrypted and "45k" not in application.salary_expectation_encrypted
    attachments = (await db_session.execute(select(RecruitingAttachment).order_by(RecruitingAttachment.id))).scalars().all()
    assert [(a.kind, a.content_type) for a in attachments] == [
        ("CV", "application/pdf"), ("OTHER", "image/png"), ("OTHER", "image/jpeg"),
    ]
    for attachment in attachments:
        raw = document_service._path_for(attachment.storage_key).read_bytes()
        assert raw not in (PDF, PNG, JPEG) and await document_service.read_document_bytes(attachment.storage_key) in (PDF, PNG, JPEG)
    entry = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.RECRUITING_APPLICATION_CHANGED))).scalars().all()[-1]
    assert "Karriereseite" in entry.detail and "Clara" not in entry.detail and entry.actor_account_id is None

    detail = (await client.get(f"/recruiting/applications/{application.id}", headers=ctx.headers["payroll"])).json()
    assert detail["cover_letter"] == "Hallo!" and detail["salary_expectation"] == "45k" and detail["phone"] == "+49 30 123"


async def test_apply_without_files_is_fine(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    assert (await apply(client, job["id"])).status_code == 201


async def test_bell_for_hiring_team_without_applicant_data(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"], title="Lager", member_account_ids=[ctx.accounts["lead"].id, ctx.accounts["staff"].id])
    await apply(client, job["id"])
    notes = (await db_session.execute(select(Notification).where(Notification.type == NotificationType.RECRUITING_APPLICATION))).scalars().all()
    assert {n.recipient_account_id for n in notes} == {ctx.accounts["lead"].id, ctx.accounts["staff"].id}
    assert all(n.message == "Neue Bewerbung für „Lager“." for n in notes)


async def test_bell_goes_to_admin_and_hr_without_team(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    await apply(client, job["id"])
    recipients = {n.recipient_account_id for n in (await db_session.execute(select(Notification))).scalars().all()}
    assert recipients == {ctx.accounts["admin"].id, ctx.accounts["hr"].id, ctx.accounts["payroll"].id}


async def test_confirmation_mail_best_effort(client, db_session, monkeypatch) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"], title="Fahrer")
    sent = []

    async def fake_config(db, tenant_id):
        return object()

    async def fake_send(to, subject, body, config=None, raise_errors=False):
        sent.append((to, subject, body))
        return True

    monkeypatch.setattr(recruiting_service, "resolve_smtp_config", fake_config)
    monkeypatch.setattr(recruiting_service, "send_email", fake_send)
    assert (await apply(client, job["id"])).status_code == 201
    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == "clara@example.com" and subject == "Ihre Bewerbung bei Musterfirma" and "„Fahrer“" in body

    async def broken_send(*args, **kwargs):
        raise RuntimeError("SMTP kaputt")

    monkeypatch.setattr(recruiting_service, "send_email", broken_send)
    assert (await apply(client, job["id"], data=apply_form(email="zwei@example.com"))).status_code == 201
    assert len((await db_session.execute(select(RecruitingApplication))).scalars().all()) == 2


async def test_no_confirmation_without_mail_setup(client, db_session, monkeypatch) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])

    async def no_config(db, tenant_id):
        return None

    async def must_not_send(*args, **kwargs):
        raise AssertionError("darf nicht senden")

    monkeypatch.setattr(recruiting_service, "resolve_smtp_config", no_config)
    monkeypatch.setattr(recruiting_service, "send_email", must_not_send)
    assert (await apply(client, job["id"])).status_code == 201


async def test_honeypot_pretends_success_without_storing(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    response = await apply(client, job["id"], data=apply_form(website="http://spam.example.com"),
                           files=[("cv", ("cv.pdf", PDF, "application/pdf"))])
    assert response.status_code == 201 and response.json() == {"received": True}
    assert (await db_session.execute(select(RecruitingApplication))).scalars().all() == []
    assert (await db_session.execute(select(Notification))).scalars().all() == []


async def test_rate_limit_per_ip(client, db_session) -> None:
    from app.api.recruiting import APPLY_LIMIT

    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    for index in range(APPLY_LIMIT):
        assert (await apply(client, job["id"], data=apply_form(email=f"p{index}@example.com"))).status_code == 201
    blocked = await apply(client, job["id"], data=apply_form(email="zuviel@example.com"))
    assert blocked.status_code == 429 and blocked.json()["code"] == "TOO_MANY_APPLICATIONS"
    assert len((await db_session.execute(select(RecruitingApplication))).scalars().all()) == APPLY_LIMIT


async def test_invalid_attempts_count_towards_rate_limit(client, db_session) -> None:
    from app.api.recruiting import APPLY_LIMIT

    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    for _ in range(APPLY_LIMIT):
        await apply(client, job["id"], data=apply_form(website="bot"))
    assert (await apply(client, job["id"])).status_code == 429


@pytest.mark.parametrize(
    "overrides",
    [
        {"privacy_acknowledged": "false"},
        {"privacy_acknowledged": None},
        {"first_name": " "},
        {"last_name": "x" * 101},
        {"email": "nicht-gueltig"},
        {"phone": "<script>"},
        {"cover_letter": "x" * 20001},
        {"salary_expectation": "x" * 201},
        {"website": "x" * 501},
    ],
)
async def test_apply_validation(client, db_session, overrides) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    response = await apply(client, job["id"], data=apply_form(**overrides))
    assert response.status_code == 422
    assert (await db_session.execute(select(RecruitingApplication))).scalars().all() == []


async def test_apply_missing_required_field(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    data = apply_form()
    data.pop("email")
    assert (await apply(client, job["id"], data=data)).status_code == 422


@pytest.mark.parametrize(
    "file, code",
    [
        (("cv", ("cv.html", HTML, "text/html")), "UNSUPPORTED_FILE_TYPE"),
        (("cv", ("cv.pdf", HTML, "application/pdf")), "UNSUPPORTED_FILE_TYPE"),
        (("attachments", ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")), "UNSUPPORTED_FILE_TYPE"),
        (("attachments", ("leer.pdf", b"", "application/pdf")), "EMPTY_FILE"),
    ],
)
async def test_apply_file_checks_store_nothing(client, db_session, file, code) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    files = [("cv", ("ok.pdf", PDF, "application/pdf"))] if file[0] == "attachments" else []
    response = await apply(client, job["id"], files=files + [file])
    assert response.status_code == 400 and response.json()["code"] == code
    assert (await db_session.execute(select(RecruitingApplication))).scalars().all() == []
    assert (await db_session.execute(select(RecruitingAttachment))).scalars().all() == []


async def test_apply_file_limits(client, db_session, monkeypatch) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    too_many = [("attachments", (f"a{i}.pdf", PDF, "application/pdf")) for i in range(recruiting_service.MAX_ATTACHMENTS + 1)]
    response = await apply(client, job["id"], files=too_many)
    assert response.status_code == 400 and response.json()["code"] == "TOO_MANY_FILES"
    exact = [("cv", ("cv.pdf", PDF, "application/pdf"))] + [
        ("attachments", (f"a{i}.pdf", PDF, "application/pdf")) for i in range(recruiting_service.MAX_ATTACHMENTS - 1)
    ]
    assert (await apply(client, job["id"], files=exact)).status_code == 201
    monkeypatch.setattr(recruiting_service, "MAX_ATTACHMENT_BYTES", len(PDF) - 1)
    big = await apply(client, job["id"], data=apply_form(email="b@example.com"), files=[("cv", ("cv.pdf", PDF, "application/pdf"))])
    assert big.status_code == 413


async def test_application_after_deadline_is_refused(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"], application_deadline=str(date.today() - timedelta(days=1)))
    assert (await apply(client, job["id"])).status_code == 404


async def test_careers_paths_need_no_login_and_ignore_tokens_of_other_company(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    assert (await client.get("/public/careers", headers=ctx.headers["staff"])).status_code == 200
    assert (await client.get(f"/public/careers/jobs/{job['id']}")).status_code == 200
