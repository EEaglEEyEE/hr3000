"""Recruiting: Löschfristen (Hintergrundlauf, Talentpool, Statistik), Einstellungen und Hilfsfunktionen."""
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import (
    AppSettings,
    AuditAction,
    AuditLogEntry,
    RecruitingApplication,
    RecruitingAttachment,
    RecruitingNote,
    RecruitingStat,
    Tenant,
)
from app.services import recruiting_service as svc
from tests.recruiting_helpers import PDF, company, create_application, create_job, enable, other_company, settings_row


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


# --- Hilfsfunktionen -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "day, months, expected",
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2026, 5, 15), 6, date(2026, 11, 15)),
        (date(2026, 11, 30), 3, date(2027, 2, 28)),
        (date(2026, 12, 1), 12, date(2027, 12, 1)),
        (date(2026, 3, 10), 0, date(2026, 3, 10)),
    ],
)
def test_add_months(day, months, expected) -> None:
    assert svc.add_months(day, months) == expected


@pytest.mark.parametrize(
    "title, slug",
    [
        ("Sachbearbeiter (m/w/d)", "sachbearbeiter-m-w-d"),
        ("Bürokauffrau – Teilzeit", "buerokauffrau-teilzeit"),
        ("Straßenbauer", "strassenbauer"),
        ("!!!", "stelle"),
        ("A" * 100, "a" * 80),
    ],
)
def test_slugify(title, slug) -> None:
    assert svc.slugify(title) == slug


def _app(stage: str, closed: datetime | None, talent_pool: bool = False) -> RecruitingApplication:
    return RecruitingApplication(stage=stage, closed_at=closed, talent_pool=talent_pool)


def test_delete_on_rules() -> None:
    row = AppSettings(recruiting_retention_months=6, recruiting_talent_pool_months=12)
    closed = datetime(2026, 1, 15, 9, 0)
    assert svc.delete_on(_app("REJECTED", closed), row) == date(2026, 7, 15)
    assert svc.delete_on(_app("WITHDRAWN", closed), row) == date(2026, 7, 15)
    assert svc.delete_on(_app("REJECTED", closed, talent_pool=True), row) == date(2027, 1, 15)
    for stage in ("NEW", "SCREENING", "INTERVIEW", "OFFER", "HIRED"):
        assert svc.delete_on(_app(stage, closed), row) is None
    assert svc.delete_on(_app("REJECTED", None), row) is None


def test_encrypt_text_helpers() -> None:
    assert svc.encrypt_text(None) is None and svc.encrypt_text("") is None
    token = svc.encrypt_text("geheim")
    assert token != "geheim" and svc.decrypt_text(token) == "geheim"
    assert svc.decrypt_text(None) is None


def test_account_name() -> None:
    from app.models import Account, Employee

    assert svc.account_name(None, None) is None
    assert svc.account_name(Account(email="a@example.com"), None) == "a@example.com"
    assert svc.account_name(Account(email=None), None) == "Entferntes Konto"
    assert svc.account_name(Account(email="a@example.com"), Employee(first_name="A", last_name="B")) == "A B"


def test_check_attachment_accepts_only_pdf_and_images() -> None:
    from app.errors import AppError

    assert svc.check_attachment(PDF, "x.pdf") == "application/pdf"
    with pytest.raises(AppError) as docx:
        svc.check_attachment(b"PK\x03\x04" + b"\x00" * 10, "x.docx")
    assert docx.value.code == "UNSUPPORTED_FILE_TYPE"


# --- Löschlauf -------------------------------------------------------------------------------


async def _closed_application(client, db_session, ctx, job, *, stage="REJECTED", closed=datetime(2026, 1, 15, 12), talent_pool=False, email="x@example.com"):
    app = await create_application(client, ctx.headers["admin"], job["id"], email=email, talent_pool=talent_pool)
    base = f"/recruiting/applications/{app['id']}"
    await client.post(f"{base}/attachments", files={"file": ("cv.pdf", PDF)}, headers=ctx.headers["admin"])
    await client.post(f"{base}/notes", json={"body": "Notiz"}, headers=ctx.headers["admin"])
    await client.put(f"{base}/rating", json={"score": 2}, headers=ctx.headers["admin"])
    payload = {"stage": stage, "rejection_reason": "OTHER"} if stage == "REJECTED" else {"stage": stage}
    await client.post(f"{base}/stage", json=payload, headers=ctx.headers["admin"])
    row = await db_session.get(RecruitingApplication, app["id"])
    row.closed_at = closed if stage in ("REJECTED", "WITHDRAWN") else None
    await db_session.commit()
    return app


async def test_purge_deletes_after_deadline_and_keeps_counts(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    rejected = await _closed_application(client, db_session, ctx, job)
    withdrawn = await _closed_application(client, db_session, ctx, job, stage="WITHDRAWN", email="w@example.com")
    pool = await _closed_application(client, db_session, ctx, job, talent_pool=True, email="p@example.com")
    running = await _closed_application(client, db_session, ctx, job, stage="INTERVIEW", email="r@example.com")
    hired = await _closed_application(client, db_session, ctx, job, stage="HIRED", email="h@example.com")
    keys = {a.application_id: a.storage_key for a in (await db_session.execute(select(RecruitingAttachment))).scalars().all()}

    assert await svc.purge_due_applications(db_session, 1, date(2026, 7, 14)) == 0
    assert await svc.purge_due_applications(db_session, 1, date(2026, 7, 15)) == 2
    remaining = {a.id for a in (await db_session.execute(select(RecruitingApplication))).scalars().all()}
    assert remaining == {pool["id"], running["id"], hired["id"]}
    for app_id in (rejected["id"], withdrawn["id"]):
        assert not (Path(settings.documents_dir) / keys[app_id][:2] / keys[app_id]).exists()
    assert (Path(settings.documents_dir) / keys[pool["id"]][:2] / keys[pool["id"]]).exists()
    assert {n.application_id for n in (await db_session.execute(select(RecruitingNote))).scalars().all()} == remaining
    stats = {(s.stage, s.count) for s in (await db_session.execute(select(RecruitingStat))).scalars().all()}
    assert stats == {("REJECTED", 1), ("WITHDRAWN", 1)}
    audit = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.RECRUITING_DELETED))).scalars().all()
    assert len(audit) == 2 and all(a.actor_account_id is None and "Löschfrist" in a.detail for a in audit)
    assert all("x@example.com" not in a.detail and "Bea" not in a.detail for a in audit)

    assert await svc.purge_due_applications(db_session, 1, date(2027, 1, 14)) == 0
    assert await svc.purge_due_applications(db_session, 1, date(2027, 1, 15)) == 1
    stats = {(s.stage, s.count) for s in (await db_session.execute(select(RecruitingStat))).scalars().all()}
    assert stats == {("REJECTED", 2), ("WITHDRAWN", 1)}
    assert {a.id for a in (await db_session.execute(select(RecruitingApplication))).scalars().all()} == {running["id"], hired["id"]}


async def test_purge_uses_company_retention_settings(client, db_session) -> None:
    ctx = await company(db_session, client)
    await enable(db_session, recruiting_retention_months=1, recruiting_talent_pool_months=2)
    job = await create_job(client, ctx.headers["admin"])
    await _closed_application(client, db_session, ctx, job)
    await _closed_application(client, db_session, ctx, job, talent_pool=True, email="p@example.com")
    assert await svc.purge_due_applications(db_session, 1, date(2026, 2, 15)) == 1
    assert await svc.purge_due_applications(db_session, 1, date(2026, 3, 15)) == 1


async def test_purge_runs_even_when_recruiting_is_switched_off(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    await _closed_application(client, db_session, ctx, job)
    row = await settings_row(db_session)
    row.recruiting_enabled = False
    await db_session.commit()
    assert await svc.purge_due_applications(db_session, 1, date(2026, 8, 1)) == 1


async def test_purge_only_touches_its_company(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    await _closed_application(client, db_session, ctx, job)
    await other_company(db_session, client)
    assert await svc.purge_due_applications(db_session, 2, date(2027, 1, 1)) == 0
    assert len((await db_session.execute(select(RecruitingApplication))).scalars().all()) == 1


async def test_due_for_deletion_list(client, db_session) -> None:
    ctx = await company(db_session, client)
    job = await create_job(client, ctx.headers["admin"])
    today = date.today()
    soon = await _closed_application(client, db_session, ctx, job, closed=datetime(today.year - 1, today.month, 1, 12))
    later = await _closed_application(client, db_session, ctx, job, email="l@example.com", closed=datetime.combine(today, datetime.min.time()))
    await _closed_application(client, db_session, ctx, job, stage="OFFER", email="o@example.com")
    due = (await client.get("/recruiting/applications/due-for-deletion", headers=ctx.headers["hr"])).json()
    assert [a["id"] for a in due] == [soon["id"]]
    assert due[0]["delete_on"] <= str(today)
    far = (await client.get("/recruiting/applications/due-for-deletion?within_days=365", headers=ctx.headers["hr"])).json()
    assert [a["id"] for a in far] == [soon["id"], later["id"]]
    for bad in (-1, 366):
        assert (await client.get(f"/recruiting/applications/due-for-deletion?within_days={bad}", headers=ctx.headers["hr"])).status_code == 422


async def test_reminder_loop_runs_purge_independent_of_reminders(client, db_session, monkeypatch) -> None:
    import asyncio

    from app.services import reminder_service

    calls = []

    async def fake_reminders(db, tenant_id, today):
        calls.append(("reminders", tenant_id))
        return 0

    async def fake_purge(db, tenant_id, today):
        calls.append(("purge", tenant_id))
        raise asyncio.CancelledError  # Schleife nach dem ersten Durchlauf beenden

    monkeypatch.setattr(reminder_service, "send_due_reminders", fake_reminders)
    monkeypatch.setattr(reminder_service.recruiting_service, "purge_due_applications", fake_purge)

    class Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *args):
            return False

    with pytest.raises(asyncio.CancelledError):
        await reminder_service.run_reminders(Factory(), 3600)
    assert calls == [("reminders", 1), ("purge", 1)]


async def test_tenant_purge_removes_attachment_files(client, db_session) -> None:
    from app.services.tenant_lifecycle import purge_tenant

    ctx = await company(db_session, client)
    acme = await other_company(db_session, client)
    acme_job = await create_job(client, acme, title="Acme")
    app = await create_application(client, acme, acme_job["id"])
    await client.post(f"/recruiting/applications/{app['id']}/attachments", files={"file": ("cv.pdf", PDF)}, headers=acme)
    own_job = await create_job(client, ctx.headers["admin"])
    own = await create_application(client, ctx.headers["admin"], own_job["id"])
    await client.post(f"/recruiting/applications/{own['id']}/attachments", files={"file": ("cv.pdf", PDF)}, headers=ctx.headers["admin"])
    rows = (await db_session.execute(select(RecruitingAttachment))).scalars().all()
    paths = {r.tenant_id: Path(settings.documents_dir) / r.storage_key[:2] / r.storage_key for r in rows}
    assert all(p.exists() for p in paths.values())

    await purge_tenant(db_session, 2)
    assert await db_session.get(Tenant, 2) is None
    assert not paths[2].exists() and paths[1].exists()
    assert [a.tenant_id for a in (await db_session.execute(select(RecruitingApplication))).scalars().all()] == [1]


# --- Einstellungen ---------------------------------------------------------------------------


async def test_settings_defaults_and_update(client, db_session) -> None:
    ctx = await company(db_session, client, enabled=False)
    current = (await client.get("/settings", headers=ctx.headers["admin"])).json()
    assert current["recruiting_enabled"] is False
    assert current["recruiting_retention_months"] == 6 and current["recruiting_talent_pool_months"] == 12
    assert current["recruiting_privacy_text"] is None and current["recruiting_privacy_url"] is None
    assert (await client.get("/features", headers=ctx.headers["hr"])).json()["recruiting_enabled"] is False

    response = await client.patch(
        "/settings",
        json={
            "recruiting_enabled": True, "recruiting_retention_months": 3, "recruiting_talent_pool_months": 24,
            "recruiting_privacy_text": "  Hinweise  ", "recruiting_privacy_url": "https://example.com/datenschutz",
        },
        headers=ctx.headers["admin"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recruiting_enabled"] is True and body["recruiting_retention_months"] == 3
    assert body["recruiting_talent_pool_months"] == 24 and body["recruiting_privacy_text"] == "Hinweise"
    assert (await client.get("/features", headers=ctx.headers["hr"])).json()["recruiting_enabled"] is True

    cleared = (await client.patch("/settings", json={"recruiting_privacy_text": "", "recruiting_privacy_url": ""}, headers=ctx.headers["admin"])).json()
    assert cleared["recruiting_privacy_text"] is None and cleared["recruiting_privacy_url"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"recruiting_retention_months": 0},
        {"recruiting_retention_months": 37},
        {"recruiting_talent_pool_months": 0},
        {"recruiting_talent_pool_months": 61},
        {"recruiting_privacy_url": "http://example.com"},
        {"recruiting_privacy_url": "javascript:alert(1)"},
        {"recruiting_privacy_url": "https://" + "x" * 500},
        {"recruiting_privacy_text": "x" * 5001},
    ],
)
async def test_settings_validation(client, db_session, payload) -> None:
    ctx = await company(db_session, client)
    assert (await client.patch("/settings", json=payload, headers=ctx.headers["admin"])).status_code == 422


async def test_only_admin_changes_recruiting_settings(client, db_session) -> None:
    ctx = await company(db_session, client, enabled=False)
    assert (await client.patch("/settings", json={"recruiting_enabled": True}, headers=ctx.headers["hr"])).status_code == 403
