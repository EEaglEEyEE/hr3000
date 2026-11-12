"""Hinweisgebersystem – öffentliche Meldeseite ohne Anmeldung (api/whistle_public.py)."""
import hashlib
import logging
import re
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.main import SkipPublicAccessLog
from app.models import AuditLogEntry, Notification, NotificationType, WhistleCase, WhistleMessage
from app.services import whistle_service
from tests.whistle_helpers import (
    ALL_TABLES,
    OTHER,
    PDF,
    PNG,
    REPORT,
    access,
    company,
    other_company,
    report,
    set_enabled,
    table_text,
)

BASE = "/public/whistle"


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


# --- Schalter --------------------------------------------------------------------------------


async def test_everything_is_404_while_switched_off(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client, enabled=False)
    body = {"case_number": "H-ABCDEFGH", "access_code": "A" * 20}
    responses = [
        await client.get(f"{BASE}/info"),
        await client.post(f"{BASE}/reports", json=REPORT),
        await client.post(f"{BASE}/status", json=body),
        await client.post(f"{BASE}/messages", json={**body, "body": "Hallo"}),
        await client.post(f"{BASE}/attachments", data=body, files={"file": ("a.pdf", PDF, "application/pdf")}),
    ]
    assert [r.status_code for r in responses] == [404] * 5
    assert all(r.json()["code"] == "NOT_FOUND" for r in responses)


async def test_switching_off_hides_existing_reports_too(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    created = await report(client)
    await set_enabled(db_session, False)
    assert (await client.post(f"{BASE}/status", json=access(created))).status_code == 404


async def test_default_is_off(client: AsyncClient, db_session: AsyncSession) -> None:
    assert (await client.get(f"{BASE}/info")).status_code == 404


async def test_super_admin_host_has_no_report_page(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    response = await client.get(f"{BASE}/info", headers={"Host": settings.super_admin_hostname})
    assert response.status_code == 404


async def test_info_shows_company_and_limits(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    response = await client.get(f"{BASE}/info")
    assert response.status_code == 200
    assert response.json() == {
        "company_name": "Musterfirma",
        "accepting_reports": True,
        "max_attachment_bytes": 10 * 1024 * 1024,
        "max_attachments": 10,
    }
    assert response.headers["cache-control"] == "no-store"


async def test_without_officer_no_reports_are_accepted(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client, with_officer=False)
    assert (await client.get(f"{BASE}/info")).json()["accepting_reports"] is False
    response = await client.post(f"{BASE}/reports", json=REPORT)
    assert response.status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(WhistleCase)) == 0


# --- Meldung abgeben -------------------------------------------------------------------------


async def test_report_returns_case_number_and_code_once(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    created = await report(client)
    assert re.fullmatch(r"H-[A-HJ-NP-Z2-9]{8}", created["case_number"])
    assert re.fullmatch(r"([A-HJ-NP-Z2-9]{5}-){3}[A-HJ-NP-Z2-9]{5}", created["access_code"])

    case = await db_session.scalar(select(WhistleCase))
    code = created["access_code"].replace("-", "")
    assert case.access_code_hash == hashlib.sha256(f"1:{created['case_number']}:{code}".encode()).hexdigest()
    assert case.status == "RECEIVED" and case.anonymous is True and case.unread_for_office is True
    # Der Code steht nirgends im Klartext
    dump = await table_text(db_session, *ALL_TABLES)
    assert code not in dump and created["access_code"] not in dump


async def test_content_is_encrypted_in_the_database(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    await report(
        client,
        anonymous=False,
        contact_name="Hanna Hinweis",
        contact_email="hanna@example.com",
        occurred_when="Im Oktober 2026",
        occurred_where="Lager Süd",
    )
    dump = await table_text(db_session, *ALL_TABLES)
    for plain in ("Rechnungen werden doppelt", "Hanna Hinweis", "hanna@example.com", "Oktober 2026", "Lager Süd"):
        assert plain not in dump


async def test_reports_never_store_ip_account_or_audit_actor(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    audit_before = await db_session.scalar(select(func.count()).select_from(AuditLogEntry))
    # Auch angemeldet: der Anmelde-Header wird ignoriert
    created = await report(client, headers=people.employee)
    await client.post(f"{BASE}/messages", headers=people.employee, json={**access(created), "body": "Nachtrag"})
    await client.post(f"{BASE}/attachments", headers=people.employee, data=access(created), files={"file": ("a.pdf", PDF, "application/pdf")})

    dump = await table_text(db_session, *ALL_TABLES)
    assert "127.0.0.1" not in dump
    assert await db_session.scalar(select(func.count()).select_from(AuditLogEntry)) == audit_before
    message = await db_session.scalar(select(WhistleMessage))
    assert message.kind == "REPORTER" and message.author_account_id is None
    columns = {c.name for c in WhistleCase.__table__.columns}
    assert not {"ip", "ip_address", "account_id", "employee_id", "created_by_account_id"} & columns


async def test_invalid_token_does_not_block_a_report(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    response = await client.post(f"{BASE}/reports", headers={"Authorization": "Bearer kaputt"}, json=REPORT)
    assert response.status_code == 201


async def test_officers_are_notified_without_content(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    created = await report(client)
    notes = (await db_session.scalars(select(Notification))).all()
    assert [(n.recipient_account_id, n.type) for n in notes] == [(people.officer_id, NotificationType.WHISTLEBLOWING)]
    assert created["case_number"] in notes[0].message and "Rechnungen" not in notes[0].message
    # Admin und HR bekommen nichts
    assert (await client.get("/notifications", headers=people.admin)).json() == []
    assert (await client.get("/notifications", headers=people.hr)).json() == []


@pytest.mark.parametrize(
    "payload",
    [
        {**REPORT, "description": "zu kurz"},
        {**REPORT, "description": "          \n\n   "},
        {**REPORT, "description": "x" * 10001},
        {**REPORT, "category": "SPAM"},
        {**REPORT, "anonymous": True, "contact_name": "Hanna"},
        {**REPORT, "anonymous": False},
        {**REPORT, "anonymous": False, "contact_email": "keine-adresse"},
        {**REPORT, "occurred_where": "x" * 201},
        {**REPORT, "unbekannt": 1},
        {"description": REPORT["description"]},
    ],
)
async def test_report_validation(client: AsyncClient, db_session: AsyncSession, payload: dict) -> None:
    await company(db_session, client)
    response = await client.post(f"{BASE}/reports", json=payload)
    assert response.status_code == 422, response.text


async def test_report_boundaries_are_accepted(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    await report(client, description="x" * 10)
    await report(client, description="x" * 10000, occurred_where="y" * 200)
    await report(client, anonymous=False, contact_email="nur@example.com", contact_name="  ")


async def test_reports_per_ip_are_limited(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    for _ in range(whistle_service.REPORTS_PER_IP):
        await report(client)
    response = await client.post(f"{BASE}/reports", json=REPORT)
    assert response.status_code == 429 and response.json()["code"] == "TOO_MANY_REPORTS"


async def test_reports_per_company_are_limited(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    await company(db_session, client)
    monkeypatch.setattr(whistle_service, "REPORTS_PER_TENANT_PER_DAY", 2)
    monkeypatch.setattr(whistle_service, "REPORTS_PER_IP", 100)
    await report(client)
    await report(client)
    assert (await client.post(f"{BASE}/reports", json=REPORT)).status_code == 429


# --- Stand abfragen --------------------------------------------------------------------------


async def test_status_with_number_and_code(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    created = await report(client)
    response = await client.post(f"{BASE}/status", json=access(created))
    assert response.status_code == 200
    data = response.json()
    assert data["case_number"] == created["case_number"] and data["status"] == "RECEIVED"
    assert data["description"] == REPORT["description"] and data["messages"] == [] and data["attachments"] == []
    assert response.headers["cache-control"] == "no-store"


async def test_code_is_accepted_without_dashes_and_in_lower_case(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    created = await report(client)
    body = {"case_number": " " + created["case_number"].lower(), "access_code": created["access_code"].replace("-", " ").lower()}
    assert (await client.post(f"{BASE}/status", json=body)).status_code == 200


async def test_wrong_code_unknown_case_and_other_company_look_the_same(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    await other_company(db_session, client)
    created = await report(client)
    other = await report(client, headers=OTHER)
    wrong = await client.post(f"{BASE}/status", json={**access(created), "access_code": "A" * 20})
    unknown = await client.post(f"{BASE}/status", json={"case_number": "H-ZZZZZZZZ", "access_code": created["access_code"]})
    garbage = await client.post(f"{BASE}/status", json={"case_number": "1234", "access_code": "x"})
    # Vorgang und Code der anderen Firma gelten hier nicht – und umgekehrt
    foreign = await client.post(f"{BASE}/status", json=access(other))
    swapped = await client.post(f"{BASE}/status", headers=OTHER, json=access(created))
    for response in (wrong, unknown, garbage, foreign, swapped):
        assert response.status_code == 401
        assert response.json() == {"detail": "Vorgangsnummer oder Zugangscode stimmen nicht.", "code": "WHISTLE_ACCESS_INVALID"}
    # Die eigene Firma findet ihren Vorgang
    assert (await client.post(f"{BASE}/status", headers=OTHER, json=access(other))).status_code == 200


async def test_code_of_another_case_does_not_open_this_one(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    first = await report(client)
    second = await report(client)
    body = {"case_number": first["case_number"], "access_code": second["access_code"]}
    assert (await client.post(f"{BASE}/status", json=body)).status_code == 401


async def test_failures_per_case_are_limited(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    created = await report(client)
    for _ in range(whistle_service.ACCESS_FAILURES_PER_CASE):
        assert (await client.post(f"{BASE}/status", json={**access(created), "access_code": "B" * 20})).status_code == 401
    # Danach ist der Vorgang vorübergehend gesperrt – auch mit dem richtigen Code
    blocked = await client.post(f"{BASE}/status", json=access(created))
    assert blocked.status_code == 429 and blocked.json()["code"] == "TOO_MANY_ATTEMPTS"


async def test_failures_per_ip_are_limited_across_cases(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    created = await report(client)
    for i in range(whistle_service.ACCESS_FAILURES_PER_IP):
        number = f"H-{'ABCDEFGHJK'[i]}AAAAAAA"
        assert (await client.post(f"{BASE}/status", json={"case_number": number, "access_code": "C" * 20})).status_code == 401
    assert (await client.post(f"{BASE}/status", json=access(created))).status_code == 429


async def test_malformed_numbers_count_per_ip_only(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    for _ in range(whistle_service.ACCESS_FAILURES_PER_IP):
        await client.post(f"{BASE}/status", json={"case_number": "kaputt", "access_code": "x"})
    assert (await client.post(f"{BASE}/status", json={"case_number": "kaputt", "access_code": "x"})).status_code == 429


@pytest.mark.parametrize(
    "payload",
    [{}, {"case_number": "", "access_code": "x"}, {"case_number": "H-AAAAAAAA", "access_code": "x" * 61}, {"case_number": "H", "access_code": "x", "mehr": 1}],
)
async def test_status_validation(client: AsyncClient, db_session: AsyncSession, payload: dict) -> None:
    await company(db_session, client)
    assert (await client.post(f"{BASE}/status", json=payload)).status_code == 422


async def test_access_data_is_never_accepted_in_the_url(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    created = await report(client)
    response = await client.get(f"{BASE}/status", params=access(created))
    assert response.status_code == 405


# --- Rückkanal -------------------------------------------------------------------------------


async def test_reporter_can_write_and_read_office_messages(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    created = await report(client)
    case_id = (await db_session.scalar(select(WhistleCase))).id
    await client.get(f"/whistle/cases/{case_id}", headers=people.officer)
    await client.post(f"/whistle/cases/{case_id}/messages", headers=people.officer, json={"kind": "MESSAGE", "body": "Danke, wir prüfen das.", "mark": "ACKNOWLEDGEMENT"})
    await client.post(f"/whistle/cases/{case_id}/messages", headers=people.officer, json={"kind": "NOTE", "body": "Intern: Buchhaltung fragen"})

    response = await client.post(f"{BASE}/messages", json={**access(created), "body": "  Weitere Belege folgen.  "})
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "IN_REVIEW" and data["acknowledged_at"] is not None
    assert [(m["from_office"], m["body"], m["mark"]) for m in data["messages"]] == [
        (True, "Danke, wir prüfen das.", "ACKNOWLEDGEMENT"),
        (False, "Weitere Belege folgen.", None),
    ]
    assert "Intern" not in response.text  # interne Notizen sieht die meldende Person nie


async def test_new_reporter_message_flags_the_case_and_rings_once(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    created = await report(client)
    case = await db_session.scalar(select(WhistleCase))
    await client.get(f"/whistle/cases/{case.id}", headers=people.officer)
    await client.post(f"{BASE}/messages", json={**access(created), "body": "Eins"})
    await client.post(f"{BASE}/messages", json={**access(created), "body": "Zwei"})
    await db_session.refresh(case)
    assert case.unread_for_office is True
    messages = [n.message for n in (await db_session.scalars(select(Notification).order_by(Notification.id))).all()]
    assert len(messages) == 2 and "Neue Nachricht" in messages[1]


@pytest.mark.parametrize("body", ["", "   ", "x" * 5001])
async def test_reporter_message_validation(client: AsyncClient, db_session: AsyncSession, body: str) -> None:
    await company(db_session, client)
    created = await report(client)
    assert (await client.post(f"{BASE}/messages", json={**access(created), "body": body})).status_code == 422


async def test_reporter_message_needs_valid_code(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    created = await report(client)
    response = await client.post(f"{BASE}/messages", json={**access(created), "access_code": "D" * 20, "body": "Hallo"})
    assert response.status_code == 401
    assert await db_session.scalar(select(func.count()).select_from(WhistleMessage)) == 0


async def test_reporter_messages_are_limited(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    await company(db_session, client)
    created = await report(client)
    monkeypatch.setattr(whistle_service, "MESSAGES_PER_CASE_PER_HOUR", 2)
    for _ in range(2):
        assert (await client.post(f"{BASE}/messages", json={**access(created), "body": "Hallo"})).status_code == 201
    assert (await client.post(f"{BASE}/messages", json={**access(created), "body": "Hallo"})).status_code == 429


async def test_reporter_messages_have_an_upper_bound(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    await company(db_session, client)
    created = await report(client)
    monkeypatch.setattr(whistle_service, "MAX_REPORTER_MESSAGES_PER_CASE", 1)
    assert (await client.post(f"{BASE}/messages", json={**access(created), "body": "Eins"})).status_code == 201
    response = await client.post(f"{BASE}/messages", json={**access(created), "body": "Zwei"})
    assert response.status_code == 409 and response.json()["code"] == "WHISTLE_MESSAGE_LIMIT"


# --- Anhänge ---------------------------------------------------------------------------------


async def _attach(client: AsyncClient, created: dict, name: str, data: bytes, headers: dict | None = None):
    return await client.post(f"{BASE}/attachments", headers=headers or {}, data=access(created), files={"file": (name, data, "application/octet-stream")})


async def test_attachment_is_stored_encrypted_with_clean_name(client: AsyncClient, db_session: AsyncSession, tmp_path) -> None:
    await company(db_session, client)
    created = await report(client)
    response = await _attach(client, created, "../../geheim/Beleg <1>.pdf", PDF)
    assert response.status_code == 201
    assert response.json()["attachments"] == [
        {"filename": "Beleg 1.pdf", "size_bytes": len(PDF), "created_at": response.json()["attachments"][0]["created_at"]}
    ]
    stored = [p for p in (tmp_path / "docs").rglob("*") if p.is_file()]
    assert len(stored) == 1 and PDF not in stored[0].read_bytes()
    assert "Beleg" not in await table_text(db_session, "whistle_attachments")


async def test_attachment_type_is_checked_by_content(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    created = await report(client)
    html = await _attach(client, created, "foto.png", b"<html><script>x</script>")
    exe = await _attach(client, created, "a.pdf", b"MZ\x90\x00")
    empty = await _attach(client, created, "leer.pdf", b"")
    png = await _attach(client, created, "bild.pdf", PNG)
    assert (html.status_code, html.json()["code"]) == (415, "UNSUPPORTED_FILE_TYPE")
    assert (exe.status_code, exe.json()["code"]) == (415, "UNSUPPORTED_FILE_TYPE")
    assert (empty.status_code, empty.json()["code"]) == (400, "EMPTY_FILE")
    assert png.status_code == 201


async def test_attachment_size_is_limited(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    await company(db_session, client)
    created = await report(client)
    monkeypatch.setattr(whistle_service, "MAX_ATTACHMENT_BYTES", len(PDF))
    assert (await _attach(client, created, "genau.pdf", PDF)).status_code == 201
    too_big = await _attach(client, created, "gross.pdf", PDF + b"x")
    assert (too_big.status_code, too_big.json()["code"]) == (413, "FILE_TOO_LARGE")


async def test_attachments_per_case_are_limited(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    await company(db_session, client)
    created = await report(client)
    monkeypatch.setattr(whistle_service, "MAX_ATTACHMENTS_PER_CASE", 2)
    assert (await _attach(client, created, "1.pdf", PDF)).status_code == 201
    assert (await _attach(client, created, "2.pdf", PDF)).status_code == 201
    third = await _attach(client, created, "3.pdf", PDF)
    assert (third.status_code, third.json()["code"]) == (409, "WHISTLE_ATTACHMENT_LIMIT")


async def test_attachment_quota_per_company(client: AsyncClient, db_session: AsyncSession, monkeypatch, tmp_path) -> None:
    await company(db_session, client)
    created = await report(client)
    monkeypatch.setattr(whistle_service, "MAX_TENANT_ATTACHMENT_BYTES", len(PDF) + 5)
    assert (await _attach(client, created, "1.pdf", PDF)).status_code == 201
    response = await _attach(client, created, "2.pdf", PDF)
    assert (response.status_code, response.json()["code"]) == (413, "DOCUMENT_QUOTA_EXCEEDED")
    assert len([p for p in (tmp_path / "docs").rglob("*") if p.is_file()]) == 1


async def test_attachment_needs_valid_code(client: AsyncClient, db_session: AsyncSession, tmp_path) -> None:
    await company(db_session, client)
    created = await report(client)
    response = await client.post(
        f"{BASE}/attachments", data={**access(created), "access_code": "E" * 20}, files={"file": ("a.pdf", PDF, "application/pdf")}
    )
    assert response.status_code == 401
    assert not (tmp_path / "docs").exists() or not any(p.is_file() for p in (tmp_path / "docs").rglob("*"))


async def test_attachment_of_other_company_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    await other_company(db_session, client)
    created = await report(client)
    assert (await _attach(client, created, "a.pdf", PDF, headers=OTHER)).status_code == 401


async def test_attachment_file_is_removed_when_saving_fails(client: AsyncClient, db_session: AsyncSession, monkeypatch, tmp_path) -> None:
    await company(db_session, client)
    created = await report(client)

    async def broken(*_args, **_kwargs):
        raise RuntimeError("DB weg")

    monkeypatch.setattr(whistle_service, "_flag_unread", broken)
    with pytest.raises(RuntimeError):
        await _attach(client, created, "a.pdf", PDF)
    assert not any(p.is_file() for p in Path(tmp_path / "docs").rglob("*"))


# --- Zugriffsprotokoll -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "kept"),
    [("/public/whistle/status", False), ("/public/whistle/reports", False), ("/public/tenant-lookup", False), ("/whistle/cases", True), ("/employees", True)],
)
def test_access_log_skips_whistle_endpoints(path: str, kept: bool) -> None:
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("10.0.0.1:1", "POST", path, "1.1", 200), None)
    assert SkipPublicAccessLog().filter(record) is kept
