"""Hinweisgebersystem – Meldestelle (api/whistle.py): Vertraulichkeit, Bearbeitung, Fristen,
Aufbewahrung und Benennung der Beauftragten."""
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Account, AuditAction, AuditLogEntry, HrRole, WhistleAttachment, WhistleCase, WhistleMessage, WhistleOfficer
from app.services import whistle_service
from app.services.auth_service import hash_password
from tests.whistle_helpers import (
    ALL_TABLES,
    OTHER,
    PDF,
    access,
    appoint,
    company,
    login,
    other_company,
    report,
    set_enabled,
    table_text,
)


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


async def _case_with_attachment(client: AsyncClient, db: AsyncSession) -> tuple[dict, WhistleCase]:
    created = await report(client, anonymous=False, contact_name="Hanna Hinweis", contact_email="hanna@example.com", occurred_where="Lager")
    response = await client.post("/public/whistle/attachments", data=access(created), files={"file": ("beleg.pdf", PDF, "application/pdf")})
    assert response.status_code == 201
    case = await db.scalar(select(WhistleCase).where(WhistleCase.case_number == created["case_number"]))
    return created, case


async def _super_admin(client: AsyncClient, db: AsyncSession) -> dict:
    db.add(Account(tenant_id=None, email="super@example.com", password_hash=hash_password("pw"), role=HrRole.SUPER_ADMIN))
    await db.commit()
    return await login(client, "super@example.com", {"Host": settings.super_admin_hostname})


# --- Vertraulichkeit -------------------------------------------------------------------------


async def test_only_appointed_officer_sees_reports(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    _, case = await _case_with_attachment(client, db_session)
    attachment_id = (await db_session.scalar(select(WhistleAttachment))).id

    listing = await client.get("/whistle/cases", headers=people.officer)
    assert listing.status_code == 200 and [c["id"] for c in listing.json()] == [case.id]

    # Admin, HR, Führungskraft und Mitarbeiter sind nicht benannt: nichts, nicht einmal die Liste
    for headers in (people.admin, people.hr, people.supervisor, people.employee):
        for method, url in (
            ("GET", "/whistle/cases"),
            ("GET", f"/whistle/cases/{case.id}"),
            ("GET", f"/whistle/cases/{case.id}/attachments/{attachment_id}"),
            ("POST", f"/whistle/cases/{case.id}/messages"),
            ("PATCH", f"/whistle/cases/{case.id}"),
            ("DELETE", f"/whistle/cases/{case.id}"),
        ):
            body = {"kind": "NOTE", "body": "x"} if method == "POST" else {"status": "IN_REVIEW"} if method == "PATCH" else None
            response = await client.request(method, url, headers=headers, json=body)
            assert response.status_code == 404, (method, url, response.text)
            assert "Rechnungen" not in response.text
    await db_session.refresh(case)
    assert case.status == "RECEIVED"


async def test_super_admin_sees_nothing(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    _, case = await _case_with_attachment(client, db_session)
    headers = await _super_admin(client, db_session)
    assert (await client.get("/whistle/cases", headers=headers)).status_code == 404
    assert (await client.get(f"/whistle/cases/{case.id}", headers=headers)).status_code == 404
    status = await client.get("/whistle/status", headers=headers)
    assert status.json() == {"enabled": False, "officer": False}
    # Mit dem Token auf der Firmenadresse: ungültig
    token_only = {"Authorization": headers["Authorization"]}
    assert (await client.get("/whistle/cases", headers=token_only)).status_code == 401


async def test_officer_of_other_company_sees_nothing(client: AsyncClient, db_session: AsyncSession) -> None:
    await company(db_session, client)
    _, case = await _case_with_attachment(client, db_session)
    foreign = await other_company(db_session, client)
    assert (await client.get("/whistle/cases", headers=foreign)).json() == []
    assert (await client.get(f"/whistle/cases/{case.id}", headers=foreign)).status_code == 404
    response = await client.patch(f"/whistle/cases/{case.id}", headers=foreign, json={"status": "IN_REVIEW"})
    assert response.status_code == 404


async def test_switch_off_hides_cases_from_officer(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    await report(client)
    await set_enabled(db_session, False)
    assert (await client.get("/whistle/cases", headers=people.officer)).status_code == 404
    assert (await client.get("/whistle/status", headers=people.officer)).json() == {"enabled": False, "officer": False}


async def test_dismissed_officer_loses_access(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    await report(client)
    assert (await client.delete(f"/whistle/officers/{people.officer_id}", headers=people.admin)).status_code == 200
    assert (await client.get("/whistle/cases", headers=people.officer)).status_code == 404


async def test_status_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    assert (await client.get("/whistle/status", headers=people.officer)).json() == {"enabled": True, "officer": True}
    for headers in (people.admin, people.hr, people.supervisor, people.employee):
        assert (await client.get("/whistle/status", headers=headers)).json() == {"enabled": True, "officer": False}
    assert (await client.get("/whistle/status")).status_code in (401, 403)


async def test_case_ids_are_checked(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    assert (await client.get("/whistle/cases/0", headers=people.officer)).status_code == 422
    assert (await client.get("/whistle/cases/999", headers=people.officer)).status_code == 404


# --- Ansehen und Protokoll -------------------------------------------------------------------


async def test_detail_decrypts_and_is_audited_without_content(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    created, case = await _case_with_attachment(client, db_session)
    response = await client.get(f"/whistle/cases/{case.id}", headers=people.officer)
    assert response.status_code == 200
    data = response.json()
    assert data["description"].startswith("Geheimer Sachverhalt")
    assert (data["contact_name"], data["contact_email"], data["occurred_where"], data["occurred_when"]) == (
        "Hanna Hinweis", "hanna@example.com", "Lager", None,
    )
    assert data["anonymous"] is False and data["unread"] is False
    assert [a["filename"] for a in data["attachments"]] == ["beleg.pdf"]
    assert [(p["action"], p["actor_label"], p["detail"]) for p in data["protocol"]] == [
        ("WHISTLE_CASE_VIEWED", "Olga Ombud", "angesehen")
    ]
    entry = await db_session.scalar(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.WHISTLE_CASE_VIEWED))
    assert entry.actor_account_id == people.officer_id and entry.entity_id == case.id
    assert entry.detail == f"{created['case_number']}: angesehen"
    await db_session.refresh(case)
    assert case.unread_for_office is False


async def test_general_audit_log_hides_case_entries_but_shows_appointments(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    _, case = await _case_with_attachment(client, db_session)
    await client.get(f"/whistle/cases/{case.id}", headers=people.officer)
    await client.post("/whistle/officers", headers=people.admin, json={"account_id": people.employee_account_id})
    entries = (await client.get("/audit-log", headers=people.admin)).json()
    actions = {e["action"] for e in entries}
    assert "WHISTLE_CASE_VIEWED" not in actions and "WHISTLE_OFFICER_CHANGED" in actions
    assert all(e["entity_type"] != "whistle_case" for e in entries)
    filtered = (await client.get("/audit-log", headers=people.admin, params={"entity_type": "whistle_case"})).json()
    assert filtered == []


async def test_list_shows_deadlines_and_unread(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    await report(client)
    case = await db_session.scalar(select(WhistleCase))
    case.received_at = datetime(2026, 1, 5, 9, 0)
    await db_session.commit()
    item = (await client.get("/whistle/cases", headers=people.officer)).json()[0]
    assert item["ack_due"] == "2026-01-12" and item["ack_overdue"] is True
    assert item["feedback_due"] == "2026-04-12" and item["feedback_overdue"] is True
    assert item["unread"] is True and item["delete_after"] is None and item["deletion_due"] is False


async def test_list_is_newest_first(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    first = await report(client)
    second = await report(client)
    cases = (await db_session.scalars(select(WhistleCase))).all()
    for case in cases:
        case.received_at = datetime(2026, 11, 1) if case.case_number == first["case_number"] else datetime(2026, 11, 5)
    await db_session.commit()
    numbers = [c["case_number"] for c in (await client.get("/whistle/cases", headers=people.officer)).json()]
    assert numbers == [second["case_number"], first["case_number"]]


# --- Nachrichten und Notizen -----------------------------------------------------------------


async def test_acknowledgement_sets_date_and_status(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    await report(client)
    case = await db_session.scalar(select(WhistleCase))
    response = await client.post(
        f"/whistle/cases/{case.id}/messages", headers=people.officer,
        json={"kind": "MESSAGE", "body": "Ihre Meldung ist eingegangen.", "mark": "ACKNOWLEDGEMENT"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "IN_REVIEW" and data["acknowledged_at"] is not None and data["ack_overdue"] is False
    assert [(m["kind"], m["mark"], m["author_label"]) for m in data["messages"]] == [("OFFICE", "ACKNOWLEDGEMENT", "Olga Ombud")]
    acknowledged = date.fromisoformat(data["acknowledged_at"][:10])
    assert data["feedback_due"] == whistle_service.add_months(acknowledged, 3).isoformat()
    assert data["protocol"][0]["detail"] == "Eingangsbestätigung gesendet"

    again = await client.post(
        f"/whistle/cases/{case.id}/messages", headers=people.officer,
        json={"kind": "MESSAGE", "body": "Noch mal", "mark": "ACKNOWLEDGEMENT"},
    )
    assert again.status_code == 409 and again.json()["code"] == "WHISTLE_ALREADY_ACKNOWLEDGED"


async def test_feedback_message_sets_feedback_date(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    await report(client)
    case = await db_session.scalar(select(WhistleCase))
    response = await client.post(
        f"/whistle/cases/{case.id}/messages", headers=people.officer,
        json={"kind": "MESSAGE", "body": "Wir haben Maßnahmen ergriffen.", "mark": "FEEDBACK"},
    )
    data = response.json()
    assert data["status"] == "FEEDBACK_GIVEN" and data["feedback_at"] is not None and data["feedback_overdue"] is False


async def test_note_is_internal_and_encrypted(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    created = await report(client)
    case = await db_session.scalar(select(WhistleCase))
    response = await client.post(f"/whistle/cases/{case.id}/messages", headers=people.officer, json={"kind": "NOTE", "body": "Zeuge: Herr Lagerist"})
    assert response.status_code == 201
    assert response.json()["messages"][0]["kind"] == "NOTE"
    assert response.json()["status"] == "RECEIVED"  # eine Notiz ändert den Status nicht
    public = (await client.post("/public/whistle/status", json=access(created))).json()
    assert public["messages"] == []
    assert "Lagerist" not in await table_text(db_session, *ALL_TABLES)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "NOTE", "body": "x", "mark": "ACKNOWLEDGEMENT"},
        {"kind": "MAIL", "body": "x"},
        {"kind": "MESSAGE", "body": " "},
        {"kind": "MESSAGE", "body": "x" * 5001},
        {"kind": "MESSAGE", "body": "x", "mark": "OTHER"},
        {"kind": "MESSAGE", "body": "x", "author_account_id": 1},
    ],
)
async def test_office_message_validation(client: AsyncClient, db_session: AsyncSession, payload: dict) -> None:
    people = await company(db_session, client)
    await report(client)
    case = await db_session.scalar(select(WhistleCase))
    assert (await client.post(f"/whistle/cases/{case.id}/messages", headers=people.officer, json=payload)).status_code == 422


# --- Status und Abschluss --------------------------------------------------------------------


async def test_close_needs_note_and_sets_deletion_date(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    created = await report(client)
    case = await db_session.scalar(select(WhistleCase))
    missing = await client.patch(f"/whistle/cases/{case.id}", headers=people.officer, json={"status": "CLOSED"})
    assert missing.status_code == 422
    closed = await client.patch(
        f"/whistle/cases/{case.id}", headers=people.officer, json={"status": "CLOSED", "closing_note": "Verdacht bestätigt, Abmahnung."}
    )
    assert closed.status_code == 200
    data = closed.json()
    closed_on = date.fromisoformat(data["closed_at"][:10])
    assert data["status"] == "CLOSED" and data["closing_note"] == "Verdacht bestätigt, Abmahnung."
    assert data["delete_after"] == whistle_service.add_months(closed_on, 36).isoformat()
    assert data["ack_overdue"] is False and data["feedback_overdue"] is False
    assert data["protocol"][0]["detail"] == "Status Abgeschlossen"
    # Die meldende Person sieht den Status, nicht den Vermerk
    public = await client.post("/public/whistle/status", json=access(created))
    assert public.json()["status"] == "CLOSED" and "Abmahnung" not in public.text
    assert "Abmahnung" not in await table_text(db_session, *ALL_TABLES)


async def test_closing_note_only_with_closed_status(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    await report(client)
    case = await db_session.scalar(select(WhistleCase))
    for payload in ({"status": "IN_REVIEW", "closing_note": "x"}, {"status": "UNKNOWN"}, {"status": "CLOSED", "closing_note": "x" * 4001}):
        assert (await client.patch(f"/whistle/cases/{case.id}", headers=people.officer, json=payload)).status_code == 422


async def test_status_changes_and_reopen_keep_closing_note_as_internal_note(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    await report(client)
    case = await db_session.scalar(select(WhistleCase))
    url = f"/whistle/cases/{case.id}"
    assert (await client.patch(url, headers=people.officer, json={"status": "IN_REVIEW"})).json()["status"] == "IN_REVIEW"
    same = await client.patch(url, headers=people.officer, json={"status": "IN_REVIEW"})
    assert len([p for p in same.json()["protocol"] if p["action"] == "WHISTLE_CASE_CHANGED"]) == 1  # keine Änderung
    feedback = (await client.patch(url, headers=people.officer, json={"status": "FEEDBACK_GIVEN"})).json()
    assert feedback["feedback_at"] is not None
    await client.patch(url, headers=people.officer, json={"status": "CLOSED", "closing_note": "Erledigt."})
    edited = await client.patch(url, headers=people.officer, json={"status": "CLOSED", "closing_note": "Erledigt, ergänzt."})
    assert edited.json()["closing_note"] == "Erledigt, ergänzt." and edited.json()["protocol"][0]["detail"] == "Abschlussvermerk geändert"
    reopened = (await client.patch(url, headers=people.officer, json={"status": "IN_REVIEW"})).json()
    assert reopened["status"] == "IN_REVIEW"
    assert reopened["closed_at"] is None and reopened["delete_after"] is None and reopened["closing_note"] is None
    notes = [m["body"] for m in reopened["messages"] if m["kind"] == "NOTE"]
    assert len(notes) == 1 and notes[0].endswith("Erledigt, ergänzt.") and "wieder geöffnet" in notes[0]


# --- Anhänge herunterladen -------------------------------------------------------------------


async def test_officer_downloads_attachment_and_it_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    _, case = await _case_with_attachment(client, db_session)
    attachment = await db_session.scalar(select(WhistleAttachment))
    response = await client.get(f"/whistle/cases/{case.id}/attachments/{attachment.id}", headers=people.officer)
    assert response.status_code == 200 and response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert "beleg.pdf" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff" and response.headers["cache-control"] == "no-store"
    entry = await db_session.scalar(select(AuditLogEntry).where(AuditLogEntry.detail.like("%Anhang heruntergeladen")))
    assert entry.actor_account_id == people.officer_id


async def test_attachment_of_another_case_is_not_found(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    _, first = await _case_with_attachment(client, db_session)
    other = await report(client)
    other_case = await db_session.scalar(select(WhistleCase).where(WhistleCase.case_number == other["case_number"]))
    attachment = await db_session.scalar(select(WhistleAttachment).where(WhistleAttachment.case_id == first.id))
    assert (await client.get(f"/whistle/cases/{other_case.id}/attachments/{attachment.id}", headers=people.officer)).status_code == 404
    assert (await client.get(f"/whistle/cases/{first.id}/attachments/9999", headers=people.officer)).status_code == 404


async def test_missing_attachment_file(client: AsyncClient, db_session: AsyncSession, tmp_path) -> None:
    people = await company(db_session, client)
    _, case = await _case_with_attachment(client, db_session)
    attachment = await db_session.scalar(select(WhistleAttachment))
    for path in (tmp_path / "docs").rglob("*"):
        if path.is_file():
            path.unlink()
    response = await client.get(f"/whistle/cases/{case.id}/attachments/{attachment.id}", headers=people.officer)
    assert response.status_code == 410


# --- Aufbewahrung und Löschen ----------------------------------------------------------------


async def test_delete_only_after_retention(client: AsyncClient, db_session: AsyncSession, monkeypatch, tmp_path) -> None:
    people = await company(db_session, client)
    created, case = await _case_with_attachment(client, db_session)
    url = f"/whistle/cases/{case.id}"
    await client.post(f"{url}/messages", headers=people.officer, json={"kind": "NOTE", "body": "Notiz"})

    open_case = await client.delete(url, headers=people.officer)
    assert open_case.status_code == 409 and open_case.json()["code"] == "WHISTLE_RETENTION_ACTIVE"
    closed = (await client.patch(url, headers=people.officer, json={"status": "CLOSED", "closing_note": "Fertig."})).json()
    delete_after = date.fromisoformat(closed["delete_after"])
    monkeypatch.setattr(whistle_service, "today", lambda: delete_after - timedelta(days=1))
    assert (await client.delete(url, headers=people.officer)).status_code == 409

    monkeypatch.setattr(whistle_service, "today", lambda: delete_after)
    listed = (await client.get("/whistle/cases", headers=people.officer)).json()
    assert listed[0]["deletion_due"] is True
    assert (await client.delete(url, headers=people.officer)).status_code == 204

    for model in (WhistleCase, WhistleMessage, WhistleAttachment):
        assert await db_session.scalar(select(func.count()).select_from(model)) == 0
    assert not any(p.is_file() for p in Path(tmp_path / "docs").rglob("*"))
    entry = await db_session.scalar(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.WHISTLE_CASE_DELETED))
    assert entry.detail == f"{created['case_number']}: gelöscht" and entry.actor_account_id == people.officer_id
    # Danach kommt auch die meldende Person nicht mehr hinein
    assert (await client.post("/public/whistle/status", json=access(created))).status_code == 401


async def test_protocol_of_new_case_ignores_entries_of_deleted_case_with_same_id(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    people = await company(db_session, client)
    await report(client)
    case = await db_session.scalar(select(WhistleCase))
    url = f"/whistle/cases/{case.id}"
    closed = (await client.patch(url, headers=people.officer, json={"status": "CLOSED", "closing_note": "Fertig."})).json()
    monkeypatch.setattr(whistle_service, "today", lambda: date.fromisoformat(closed["delete_after"]))
    await client.delete(url, headers=people.officer)
    await report(client)
    new_case = await db_session.scalar(select(WhistleCase))
    detail = (await client.get(f"/whistle/cases/{new_case.id}", headers=people.officer)).json()
    assert [p["detail"] for p in detail["protocol"]] == ["angesehen"]


# --- Beauftragte benennen --------------------------------------------------------------------


async def test_admin_appoints_and_dismisses_officers(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    listing = (await client.get("/whistle/officers", headers=people.admin)).json()
    assert [o["name"] for o in listing["officers"]] == ["Olga Ombud"]
    candidate_ids = {c["account_id"] for c in listing["candidates"]}
    assert people.employee_account_id in candidate_ids and people.admin_id in candidate_ids
    assert people.no_login_account_id not in candidate_ids  # ohne Zugang nicht benennbar

    appointed = await client.post("/whistle/officers", headers=people.admin, json={"account_id": people.employee_account_id})
    assert appointed.status_code == 201
    assert {o["account_id"] for o in appointed.json()["officers"]} == {people.officer_id, people.employee_account_id}
    assert (await client.get("/whistle/status", headers=people.employee)).json()["officer"] is True

    dismissed = await client.delete(f"/whistle/officers/{people.employee_account_id}", headers=people.admin)
    assert [o["account_id"] for o in dismissed.json()["officers"]] == [people.officer_id]
    entries = (await db_session.scalars(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.WHISTLE_OFFICER_CHANGED).order_by(AuditLogEntry.id))).all()
    assert [(e.actor_account_id, e.entity_id, e.detail) for e in entries] == [
        (people.admin_id, people.employee_account_id, "Als Meldestellen-Beauftragte:r benannt: Erik Einfach"),
        (people.admin_id, people.employee_account_id, "Als Meldestellen-Beauftragte:r abberufen: Erik Einfach"),
    ]


async def test_appointing_an_admin_does_not_grant_others(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    await report(client)
    await client.post("/whistle/officers", headers=people.admin, json={"account_id": people.admin_id})
    assert (await client.get("/whistle/cases", headers=people.admin)).status_code == 200
    assert (await client.get("/whistle/cases", headers=people.hr)).status_code == 404


async def test_appoint_errors(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    await other_company(db_session, client)
    foreign_id = await db_session.scalar(select(Account.id).where(Account.email == "ombud@example.com"))
    duplicate = await client.post("/whistle/officers", headers=people.admin, json={"account_id": people.officer_id})
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "WHISTLE_OFFICER_EXISTS")
    foreign = await client.post("/whistle/officers", headers=people.admin, json={"account_id": foreign_id})
    assert foreign.status_code == 404
    no_login = await client.post("/whistle/officers", headers=people.admin, json={"account_id": people.no_login_account_id})
    assert (no_login.status_code, no_login.json()["code"]) == (400, "ACCOUNT_WITHOUT_LOGIN")
    for payload in ({"account_id": 0}, {}, {"account_id": "x"}, {"account_id": 1, "role": "ADMIN"}):
        assert (await client.post("/whistle/officers", headers=people.admin, json=payload)).status_code == 422
    missing = await client.delete("/whistle/officers/9999", headers=people.admin)
    assert (missing.status_code, missing.json()["code"]) == (404, "WHISTLE_OFFICER_NOT_FOUND")
    other_tenant = await client.delete(f"/whistle/officers/{foreign_id}", headers=people.admin)
    assert other_tenant.status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(WhistleOfficer).where(WhistleOfficer.tenant_id == 2)) == 1


async def test_only_admins_manage_officers(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    for headers in (people.hr, people.supervisor, people.employee, people.officer):
        assert (await client.get("/whistle/officers", headers=headers)).status_code == 403
        response = await client.post("/whistle/officers", headers=headers, json={"account_id": people.employee_account_id})
        assert response.status_code == 403
        assert (await client.delete(f"/whistle/officers/{people.officer_id}", headers=headers)).status_code == 403


async def test_officer_entries_follow_account_deletion(client: AsyncClient, db_session: AsyncSession) -> None:
    """Fremdschlüssel: Beauftragung verschwindet mit dem Konto, Nachrichten behalten ihren Text."""
    people = await company(db_session, client)
    await report(client)
    case = await db_session.scalar(select(WhistleCase))
    await client.post(f"/whistle/cases/{case.id}/messages", headers=people.officer, json={"kind": "NOTE", "body": "Notiz"})
    extra = Account(tenant_id=1, email="temp@example.com", password_hash=hash_password("pw"))
    db_session.add(extra)
    await db_session.commit()
    await appoint(db_session, extra.id)
    message = await db_session.scalar(select(WhistleMessage))
    message.author_account_id = extra.id
    await db_session.commit()
    await db_session.delete(extra)
    await db_session.commit()
    db_session.expire_all()
    assert await db_session.scalar(select(func.count()).select_from(WhistleOfficer).where(WhistleOfficer.account_id == extra.id)) == 0
    assert (await db_session.scalar(select(WhistleMessage))).author_account_id is None


async def test_cases_cascade_to_messages_and_attachments(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    _, case = await _case_with_attachment(client, db_session)
    await client.post(f"/whistle/cases/{case.id}/messages", headers=people.officer, json={"kind": "NOTE", "body": "Notiz"})
    await db_session.delete(case)
    await db_session.commit()
    assert await db_session.scalar(select(func.count()).select_from(WhistleMessage)) == 0
    assert await db_session.scalar(select(func.count()).select_from(WhistleAttachment)) == 0


async def test_second_company_cases_are_separate(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await company(db_session, client)
    foreign = await other_company(db_session, client)
    await report(client)
    await report(client, headers=OTHER)
    assert len((await client.get("/whistle/cases", headers=people.officer)).json()) == 1
    assert len((await client.get("/whistle/cases", headers=foreign)).json()) == 1
