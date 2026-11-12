"""Recruiting: Bewerbungen intern – Anlage, Rechte, Phasen, Notizen, Bewertungen, Anhänge, Gehalt."""
import pytest
from sqlalchemy import select

from app.config import settings
from app.models import (
    AuditAction,
    AuditLogEntry,
    RecruitingApplication,
    RecruitingAttachment,
    RecruitingNote,
    RecruitingRating,
    RecruitingStageEvent,
    RecruitingStat,
)
from app.services import document_service
from app.services.secret_box import decrypt_secret
from tests.recruiting_helpers import HTML, PDF, PNG, company, create_application, create_job, other_company


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


async def _setup(client, db_session):
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"], member_account_ids=[ctx.accounts["lead"].id, ctx.accounts["staff"].id])
    other_job = await create_job(client, ctx.headers["admin"], title="Andere Stelle")
    return ctx, job, other_job


async def _audit(db_session, action):
    return (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == action).order_by(AuditLogEntry.id))).scalars().all()


async def test_manual_application_is_encrypted_and_has_history(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    body = await create_application(
        client, ctx.headers["payroll"], job["id"], phone="+49 170 1234567", cover_letter="Ich bewerbe mich gern.",
        salary_expectation="52.000 €",
    )
    assert body["source"] == "MANUAL" and body["stage"] == "NEW" and body["job_title"] == job["title"]
    assert body["cover_letter"] == "Ich bewerbe mich gern." and body["salary_expectation"] == "52.000 €"
    assert [e["to_stage"] for e in body["events"]] == ["NEW"] and body["events"][0]["from_stage"] is None
    row = await db_session.get(RecruitingApplication, body["id"])
    assert "Ich bewerbe" not in row.cover_letter_encrypted and decrypt_secret(row.cover_letter_encrypted) == "Ich bewerbe mich gern."
    assert "52.000" not in row.salary_expectation_encrypted
    assert body["can_manage"] is True and body["delete_on"] is None


async def test_salary_only_with_payroll_permission(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    denied = await client.post(
        "/recruiting/applications",
        json={"job_id": job["id"], "first_name": "A", "last_name": "B", "email": "a@example.com", "salary_expectation": "60k"},
        headers=ctx.headers["hr"],
    )
    assert denied.status_code == 403 and denied.json()["code"] == "PAYROLL_PERMISSION_REQUIRED"
    created = await create_application(client, ctx.headers["admin"], job["id"], salary_expectation="60k")
    for role in ("hr", "lead", "staff"):
        detail = (await client.get(f"/recruiting/applications/{created['id']}", headers=ctx.headers[role])).json()
        assert detail["salary_expectation"] is None and detail["salary_visible"] is False
    detail = (await client.get(f"/recruiting/applications/{created['id']}", headers=ctx.headers["payroll"])).json()
    assert detail["salary_expectation"] == "60k" and detail["salary_visible"] is True
    patch = await client.patch(f"/recruiting/applications/{created['id']}", json={"salary_expectation": "70k"}, headers=ctx.headers["hr"])
    assert patch.status_code == 403


@pytest.mark.parametrize(
    "overrides",
    [
        {"first_name": ""},
        {"last_name": "x" * 101},
        {"email": "keine-adresse"},
        {"phone": "abc"},
        {"phone": "1" * 41},
        {"cover_letter": "x" * 20001},
        {"salary_expectation": "x" * 201},
        {"job_id": 0},
    ],
)
async def test_manual_application_validation(client, db_session, overrides) -> None:
    ctx, job, _ = await _setup(client, db_session)
    payload = {"job_id": job["id"], "first_name": "A", "last_name": "B", "email": "a@example.com", **overrides}
    assert (await client.post("/recruiting/applications", json=payload, headers=ctx.headers["admin"])).status_code == 422


async def test_manual_application_for_unknown_job_is_404(client, db_session) -> None:
    ctx, _, _ = await _setup(client, db_session)
    payload = {"job_id": 999, "first_name": "A", "last_name": "B", "email": "a@example.com"}
    assert (await client.post("/recruiting/applications", json=payload, headers=ctx.headers["admin"])).status_code == 404


@pytest.mark.parametrize("role", ["lead", "staff"])
async def test_members_cannot_create_edit_or_delete(client, db_session, role) -> None:
    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"])
    payload = {"job_id": job["id"], "first_name": "A", "last_name": "B", "email": "a@example.com"}
    assert (await client.post("/recruiting/applications", json=payload, headers=ctx.headers[role])).status_code == 403
    assert (await client.patch(f"/recruiting/applications/{app['id']}", json={"first_name": "X"}, headers=ctx.headers[role])).status_code == 403
    assert (await client.delete(f"/recruiting/applications/{app['id']}", headers=ctx.headers[role])).status_code == 403
    files = {"file": ("cv.pdf", PDF, "application/pdf")}
    assert (await client.post(f"/recruiting/applications/{app['id']}/attachments", files=files, headers=ctx.headers[role])).status_code == 403
    assert (await client.get("/recruiting/applications/due-for-deletion", headers=ctx.headers[role])).status_code == 403


async def test_visibility_of_applications_by_role(client, db_session) -> None:
    ctx, job, other_job = await _setup(client, db_session)
    mine = await create_application(client, ctx.headers["admin"], job["id"])
    hidden = await create_application(client, ctx.headers["admin"], other_job["id"], email="x@example.com")
    for role in ("admin", "hr"):
        ids = {a["id"] for a in (await client.get("/recruiting/applications", headers=ctx.headers[role])).json()}
        assert ids == {mine["id"], hidden["id"]}
    for role in ("lead", "staff"):
        ids = [a["id"] for a in (await client.get("/recruiting/applications", headers=ctx.headers[role])).json()]
        assert ids == [mine["id"]]
        detail = await client.get(f"/recruiting/applications/{mine['id']}", headers=ctx.headers[role])
        assert detail.status_code == 200 and detail.json()["can_manage"] is False
        response = await client.get(f"/recruiting/applications/{hidden['id']}", headers=ctx.headers[role])
        assert response.status_code == 404 and response.json()["code"] == "RECRUITING_APPLICATION_NOT_FOUND"
        stage = await client.post(f"/recruiting/applications/{hidden['id']}/stage", json={"stage": "SCREENING"}, headers=ctx.headers[role])
        assert stage.status_code == 404
    assert (await client.get("/recruiting/applications", headers=ctx.headers["other"])).json() == []
    assert (await client.get(f"/recruiting/applications/{mine['id']}", headers=ctx.headers["other"])).status_code == 404


async def test_list_filters(client, db_session) -> None:
    ctx, job, other_job = await _setup(client, db_session)
    a = await create_application(client, ctx.headers["admin"], job["id"])
    b = await create_application(client, ctx.headers["admin"], other_job["id"], email="b@example.com")
    await client.post(f"/recruiting/applications/{b['id']}/stage", json={"stage": "INTERVIEW"}, headers=ctx.headers["admin"])
    by_job = (await client.get(f"/recruiting/applications?job_id={job['id']}", headers=ctx.headers["admin"])).json()
    assert [x["id"] for x in by_job] == [a["id"]]
    by_stage = (await client.get("/recruiting/applications?stage=INTERVIEW", headers=ctx.headers["admin"])).json()
    assert [x["id"] for x in by_stage] == [b["id"]]
    assert (await client.get("/recruiting/applications?stage=UNKNOWN", headers=ctx.headers["admin"])).status_code == 422


async def test_foreign_company_cannot_reach_applications(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    acme = await other_company(db_session, client)
    app = await create_application(client, ctx.headers["admin"], job["id"])
    assert (await client.get("/recruiting/applications", headers=acme)).json() == []
    for method, url, kwargs in (
        ("get", f"/recruiting/applications/{app['id']}", {}),
        ("patch", f"/recruiting/applications/{app['id']}", {"json": {"first_name": "X"}}),
        ("delete", f"/recruiting/applications/{app['id']}", {}),
        ("post", f"/recruiting/applications/{app['id']}/stage", {"json": {"stage": "SCREENING"}}),
        ("post", f"/recruiting/applications/{app['id']}/notes", {"json": {"body": "x"}}),
        ("put", f"/recruiting/applications/{app['id']}/rating", {"json": {"score": 3}}),
    ):
        assert (await getattr(client, method)(url, headers=acme, **kwargs)).status_code == 404, url
    payload = {"job_id": job["id"], "first_name": "A", "last_name": "B", "email": "a@example.com"}
    assert (await client.post("/recruiting/applications", json=payload, headers=acme)).status_code == 404


async def test_update_application(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"], phone="0151", cover_letter="alt")
    body = (await client.patch(
        f"/recruiting/applications/{app['id']}",
        json={"first_name": "Berta", "email": "berta@example.com", "phone": "", "cover_letter": "", "talent_pool": True},
        headers=ctx.headers["hr"],
    )).json()
    assert body["first_name"] == "Berta" and body["email"] == "berta@example.com"
    assert body["phone"] is None and body["cover_letter"] is None and body["talent_pool"] is True
    entry = (await _audit(db_session, AuditAction.RECRUITING_APPLICATION_CHANGED))[-1]
    assert "first_name" in entry.detail and "Berta" not in entry.detail


async def test_update_application_validation(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"])
    for payload in ({"first_name": ""}, {"email": "x"}, {"phone": "abc"}):
        assert (await client.patch(f"/recruiting/applications/{app['id']}", json=payload, headers=ctx.headers["admin"])).status_code == 422


async def test_stage_change_with_history_and_audit(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"])
    body = (await client.post(f"/recruiting/applications/{app['id']}/stage", json={"stage": "SCREENING"}, headers=ctx.headers["staff"])).json()
    assert body["stage"] == "SCREENING"
    assert [(e["from_stage"], e["to_stage"]) for e in body["events"]] == [(None, "NEW"), ("NEW", "SCREENING")]
    assert body["events"][1]["account_name"] == "Staff Muster"
    entry = (await _audit(db_session, AuditAction.RECRUITING_APPLICATION_CHANGED))[-1]
    assert entry.detail == "Phase NEW → SCREENING"
    same = (await client.post(f"/recruiting/applications/{app['id']}/stage", json={"stage": "SCREENING"}, headers=ctx.headers["lead"])).json()
    assert len(same["events"]) == 2


async def test_reject_requires_reason_and_starts_deadline(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"])
    url = f"/recruiting/applications/{app['id']}/stage"
    assert (await client.post(url, json={"stage": "REJECTED"}, headers=ctx.headers["admin"])).status_code == 422
    assert (await client.post(url, json={"stage": "SCREENING", "rejection_reason": "SALARY"}, headers=ctx.headers["admin"])).status_code == 422
    assert (await client.post(url, json={"stage": "INTERVIEW", "rejection_note": "x"}, headers=ctx.headers["admin"])).status_code == 422
    assert (await client.post(url, json={"stage": "REJECTED", "rejection_reason": "BAD"}, headers=ctx.headers["admin"])).status_code == 422
    assert (await client.post(url, json={"stage": "REJECTED", "rejection_reason": "OTHER", "rejection_note": "x" * 501}, headers=ctx.headers["admin"])).status_code == 422
    body = (await client.post(url, json={"stage": "REJECTED", "rejection_reason": "EXPERIENCE", "rejection_note": "Zu wenig Praxis"}, headers=ctx.headers["admin"])).json()
    assert body["rejection_reason"] == "EXPERIENCE" and body["rejection_note"] == "Zu wenig Praxis"
    assert body["closed_at"] is not None and body["delete_on"] is not None
    reopened = (await client.post(url, json={"stage": "INTERVIEW"}, headers=ctx.headers["admin"])).json()
    assert reopened["closed_at"] is None and reopened["rejection_reason"] is None and reopened["delete_on"] is None
    withdrawn = (await client.post(url, json={"stage": "WITHDRAWN", "rejection_note": "Andere Stelle angenommen"}, headers=ctx.headers["admin"])).json()
    assert withdrawn["rejection_reason"] is None and withdrawn["rejection_note"] == "Andere Stelle angenommen"


async def test_notes_encrypted_with_author_and_delete_rights(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"])
    url = f"/recruiting/applications/{app['id']}/notes"
    body = (await client.post(url, json={"body": "  Starker Eindruck  "}, headers=ctx.headers["staff"])).json()
    note = body["notes"][0]
    assert note["body"] == "Starker Eindruck" and note["author_name"] == "Staff Muster" and note["can_delete"] is True
    row = (await db_session.execute(select(RecruitingNote))).scalar_one()
    assert "Starker" not in row.body_encrypted
    lead_view = (await client.get(f"/recruiting/applications/{app['id']}", headers=ctx.headers["lead"])).json()
    assert lead_view["notes"][0]["can_delete"] is False
    assert (await client.delete(f"{url}/{note['id']}", headers=ctx.headers["lead"])).status_code == 403
    assert (await client.delete(f"{url}/999", headers=ctx.headers["lead"])).status_code == 404
    assert (await client.delete(f"{url}/{note['id']}", headers=ctx.headers["hr"])).json()["notes"] == []
    assert (await client.post(url, json={"body": "  "}, headers=ctx.headers["staff"])).status_code == 422
    assert (await client.post(url, json={"body": "x" * 5001}, headers=ctx.headers["staff"])).status_code == 422
    details = [e.detail for e in await _audit(db_session, AuditAction.RECRUITING_APPLICATION_CHANGED)]
    assert "Notiz hinzugefügt" in details and "Notiz gelöscht" in details
    assert not any("Starker" in (d or "") for d in details)


async def test_note_of_other_application_is_404(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    a = await create_application(client, ctx.headers["admin"], job["id"])
    b = await create_application(client, ctx.headers["admin"], job["id"], email="b@example.com")
    note = (await client.post(f"/recruiting/applications/{a['id']}/notes", json={"body": "x"}, headers=ctx.headers["admin"])).json()["notes"][0]
    assert (await client.delete(f"/recruiting/applications/{b['id']}/notes/{note['id']}", headers=ctx.headers["admin"])).status_code == 404


async def test_ratings_one_per_account(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"])
    url = f"/recruiting/applications/{app['id']}/rating"
    await client.put(url, json={"score": 4, "comment": "Gut"}, headers=ctx.headers["staff"])
    body = (await client.put(url, json={"score": 2}, headers=ctx.headers["lead"])).json()
    assert body["average_rating"] == 3.0 and body["rating_count"] == 2
    updated = (await client.put(url, json={"score": 5, "comment": "Sehr gut"}, headers=ctx.headers["staff"])).json()
    mine = next(r for r in updated["ratings"] if r["mine"])
    assert mine["score"] == 5 and mine["comment"] == "Sehr gut" and updated["rating_count"] == 2
    assert (await db_session.execute(select(RecruitingRating))).scalars().all().__len__() == 2
    assert "Sehr gut" not in "".join(r.comment_encrypted or "" for r in (await db_session.execute(select(RecruitingRating))).scalars().all())
    for score in (0, 6):
        assert (await client.put(url, json={"score": score}, headers=ctx.headers["staff"])).status_code == 422
    assert (await client.put(url, json={"score": 3, "comment": "x" * 2001}, headers=ctx.headers["staff"])).status_code == 422
    removed = (await client.delete(url, headers=ctx.headers["staff"])).json()
    assert removed["rating_count"] == 1 and removed["average_rating"] == 2.0
    again = (await client.delete(url, headers=ctx.headers["staff"])).json()
    assert again["rating_count"] == 1


async def test_attachments_upload_view_download_delete(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"])
    url = f"/recruiting/applications/{app['id']}/attachments"
    body = (await client.post(url, files={"file": ("lebenslauf.pdf", PDF, "application/pdf")}, data={"kind": "CV"}, headers=ctx.headers["hr"])).json()
    attachment = body["attachments"][0]
    assert attachment["kind"] == "CV" and attachment["content_type"] == "application/pdf" and attachment["size_bytes"] == len(PDF)
    row = (await db_session.execute(select(RecruitingAttachment))).scalar_one()
    raw = (document_service._path_for(row.storage_key)).read_bytes()
    assert PDF not in raw and b"%PDF" not in raw

    download = await client.get(f"{url}/{attachment['id']}/download", headers=ctx.headers["staff"])
    assert download.status_code == 200 and download.content == PDF
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff" and download.headers["cache-control"] == "private, no-store"
    inline = await client.get(f"{url}/{attachment['id']}/download?inline=true", headers=ctx.headers["lead"])
    assert inline.headers["content-disposition"].startswith("inline;")
    accesses = await _audit(db_session, AuditAction.RECRUITING_ATTACHMENT_ACCESSED)
    assert [a.detail.split()[-1] for a in accesses] == ["heruntergeladen", "angesehen"]
    assert all("lebenslauf" not in a.detail for a in accesses)

    assert (await client.get(f"{url}/999/download", headers=ctx.headers["admin"])).status_code == 404
    deleted = (await client.delete(f"{url}/{attachment['id']}", headers=ctx.headers["admin"])).json()
    assert deleted["attachments"] == []
    assert not document_service._path_for(row.storage_key).exists()


async def test_attachment_file_missing_is_410(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"])
    url = f"/recruiting/applications/{app['id']}/attachments"
    attachment = (await client.post(url, files={"file": ("a.png", PNG, "image/png")}, headers=ctx.headers["admin"])).json()["attachments"][0]
    row = (await db_session.execute(select(RecruitingAttachment))).scalar_one()
    document_service._path_for(row.storage_key).unlink()
    assert (await client.get(f"{url}/{attachment['id']}/download", headers=ctx.headers["admin"])).status_code == 410


@pytest.mark.parametrize(
    "file, code, status",
    [
        (("x.html", HTML, "text/html"), "UNSUPPORTED_FILE_TYPE", 400),
        (("fake.pdf", HTML, "application/pdf"), "UNSUPPORTED_FILE_TYPE", 400),
        (("doc.docx", b"PK\x03\x04" + b"\x00" * 20, "application/vnd.openxmlformats"), "UNSUPPORTED_FILE_TYPE", 400),
        (("leer.pdf", b"", "application/pdf"), "EMPTY_FILE", 400),
    ],
)
async def test_attachment_type_checks(client, db_session, file, code, status) -> None:
    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"])
    response = await client.post(f"/recruiting/applications/{app['id']}/attachments", files={"file": file}, headers=ctx.headers["admin"])
    assert response.status_code == status and response.json()["code"] == code


async def test_attachment_size_and_count_limits(client, db_session, monkeypatch) -> None:
    from app.services import recruiting_service

    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"])
    url = f"/recruiting/applications/{app['id']}/attachments"
    monkeypatch.setattr(recruiting_service, "MAX_ATTACHMENT_BYTES", len(PDF))
    assert (await client.post(url, files={"file": ("ok.pdf", PDF, "application/pdf")}, headers=ctx.headers["admin"])).status_code == 201
    big = await client.post(url, files={"file": ("big.pdf", PDF + b"x", "application/pdf")}, headers=ctx.headers["admin"])
    assert big.status_code == 413
    monkeypatch.setattr(recruiting_service, "MAX_ATTACHMENTS", 1)
    full = await client.post(url, files={"file": ("two.pdf", PDF, "application/pdf")}, headers=ctx.headers["admin"])
    assert full.status_code == 400 and full.json()["code"] == "TOO_MANY_FILES"
    assert (await client.post(url, data={"kind": "PHOTO"}, files={"file": ("a.pdf", PDF, "application/pdf")}, headers=ctx.headers["admin"])).status_code == 422


async def test_attachment_of_other_application_is_404(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    a = await create_application(client, ctx.headers["admin"], job["id"])
    b = await create_application(client, ctx.headers["admin"], job["id"], email="b@example.com")
    attachment = (await client.post(f"/recruiting/applications/{a['id']}/attachments", files={"file": ("a.pdf", PDF, "application/pdf")}, headers=ctx.headers["admin"])).json()["attachments"][0]
    assert (await client.get(f"/recruiting/applications/{b['id']}/attachments/{attachment['id']}/download", headers=ctx.headers["admin"])).status_code == 404
    assert (await client.delete(f"/recruiting/applications/{b['id']}/attachments/{attachment['id']}", headers=ctx.headers["admin"])).status_code == 404


async def test_immediate_delete_removes_everything_but_count(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    app = await create_application(client, ctx.headers["admin"], job["id"], cover_letter="geheim")
    base = f"/recruiting/applications/{app['id']}"
    await client.post(f"{base}/attachments", files={"file": ("a.pdf", PDF, "application/pdf")}, headers=ctx.headers["admin"])
    await client.post(f"{base}/notes", json={"body": "Notiz"}, headers=ctx.headers["admin"])
    await client.put(f"{base}/rating", json={"score": 3}, headers=ctx.headers["admin"])
    await client.post(f"{base}/stage", json={"stage": "INTERVIEW"}, headers=ctx.headers["admin"])
    key = (await db_session.execute(select(RecruitingAttachment))).scalar_one().storage_key

    assert (await client.delete(base, headers=ctx.headers["hr"])).status_code == 204
    for model in (RecruitingApplication, RecruitingAttachment, RecruitingNote, RecruitingRating, RecruitingStageEvent):
        assert (await db_session.execute(select(model))).scalars().all() == [], model
    stat = (await db_session.execute(select(RecruitingStat))).scalar_one()
    assert (stat.job_id, stat.stage, stat.count) == (job["id"], "INTERVIEW", 1)
    assert not document_service._path_for(key).exists()
    entry = (await _audit(db_session, AuditAction.RECRUITING_DELETED))[-1]
    assert "Sofort gelöscht" in entry.detail and "Bea" not in entry.detail and "bea@" not in entry.detail
    assert (await client.get(base, headers=ctx.headers["admin"])).status_code == 404
    job_body = (await client.get(f"/recruiting/jobs/{job['id']}", headers=ctx.headers["admin"])).json()
    assert job_body["deleted_counts"] == {"INTERVIEW": 1} and job_body["application_count"] == 0


async def test_deleted_counts_accumulate(client, db_session) -> None:
    ctx, job, _ = await _setup(client, db_session)
    for index in range(2):
        app = await create_application(client, ctx.headers["admin"], job["id"], email=f"x{index}@example.com")
        await client.delete(f"/recruiting/applications/{app['id']}", headers=ctx.headers["admin"])
    assert (await db_session.execute(select(RecruitingStat))).scalar_one().count == 2
