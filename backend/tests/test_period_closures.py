import os
import sys
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AuditAction, AuditLogEntry, Employee, HrRole, Account, Location, Notification
from app.services.auth_service import hash_password

if sys.platform == "darwin":
    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


async def _login(client: AsyncClient, path: str, email: str) -> dict[str, str]:
    response = await client.post(path, json={"email": email, "password": "pw"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1",
        login_email="erika@example.com", password_hash=hash_password("pw"),
    )
    other = Employee(
        location_id=location.id, first_name="Max", last_name="Andere", employee_number="E2",
        login_email="max@example.com", password_hash=hash_password("pw"),
    )
    db_session.add_all([
        employee, other,
        Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
    ])
    await db_session.commit()
    await db_session.refresh(employee)
    return {
        "employee": employee,
        "hr": await _login(client, "/auth/login", "hr@example.com"),
        "admin": await _login(client, "/auth/login", "admin@example.com"),
        "self": await _login(client, "/auth/login", "erika@example.com"),
        "other": await _login(client, "/auth/login", "max@example.com"),
    }


async def _punch(client, headers, employee_id, punch_type, ts):
    return await client.post(
        "/punches", headers=headers,
        json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())},
    )


async def _work_day(client, headers, employee_id, day: str):
    assert (await _punch(client, headers, employee_id, "COME", f"{day}T08:00:00Z")).status_code == 201
    assert (await _punch(client, headers, employee_id, "GO", f"{day}T16:30:00Z")).status_code == 201


MARCH = "/period-closures/2025/3"


def _url(employee_id: int, action: str, month: int = 3) -> str:
    return f"/employees/{employee_id}/period-closures/2025/{month}/{action}"


async def test_submit_creates_visible_pdf_notifies_and_locks_the_month(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ctx = await _setup(db_session, client)
    employee, hr = ctx["employee"], ctx["hr"]
    await _work_day(client, hr, employee.id, "2025-03-10")

    submitted = await client.post(_url(employee.id, "submit"), headers=hr)
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["status"] == "SUBMITTED" and body["actual_minutes"] == 510  # 8,5 h (keine Pausenregel im Test-Mandanten)
    assert body["document_id"] is not None

    # Mitarbeiter sieht den Nachweis in seiner Akte und kann ihn laden.
    docs = (await client.get(f"/employees/{employee.id}/documents", headers=ctx["self"])).json()
    assert [d["category"] for d in docs] == ["TIME_REPORT"]
    download = await client.get(f"/employees/{employee.id}/documents/{docs[0]['id']}/download", headers=ctx["self"])
    assert download.status_code == 200 and download.content.startswith(b"%PDF")

    notifications = (await db_session.execute(select(Notification).where(Notification.recipient_account_id == employee.account.id))).scalars().all()
    assert [n.type.value for n in notifications] == ["PERIOD_SUBMITTED"]

    # Gesperrt: Stempelung, Korrektur, Abwesenheit, Arbeitszeitmodell im Monat.
    blocked = await _punch(client, hr, employee.id, "COME", "2025-03-11T08:00:00Z")
    assert blocked.status_code == 409 and blocked.json()["code"] == "PERIOD_LOCKED"
    absence = await client.post("/absences", headers=hr, json={"employee_id": employee.id, "type": "SICK", "date_from": "2025-03-20", "date_to": "2025-03-21"})
    assert absence.status_code == 409 and absence.json()["code"] == "PERIOD_LOCKED"
    model = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=hr,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2025-03-01"},
    )
    assert model.status_code == 409 and model.json()["code"] == "PERIOD_LOCKED"
    # Andere Monate bleiben frei.
    assert (await _punch(client, hr, employee.id, "COME", "2025-04-02T08:00:00Z")).status_code == 201


async def test_cannot_submit_open_month_twice_or_with_open_days(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client)
    employee, hr = ctx["employee"], ctx["hr"]

    current = date.today()
    not_ended = await client.post(
        f"/employees/{employee.id}/period-closures/{current.year}/{current.month}/submit", headers=hr
    )
    assert not_ended.status_code == 409 and not_ended.json()["code"] == "PERIOD_NOT_ENDED"

    # Tag 5: Kommen ohne Gehen, danach weiter gestempelt -> offen.
    assert (await _punch(client, hr, employee.id, "COME", "2025-03-05T08:00:00Z")).status_code == 201
    await _work_day(client, hr, employee.id, "2025-03-06")
    blocked = await client.post(_url(employee.id, "submit"), headers=hr)
    assert blocked.status_code == 409 and blocked.json()["code"] == "OPEN_DAYS_PRESENT" and "05.03." in blocked.json()["detail"]

    forced = await client.post(_url(employee.id, "submit"), headers=hr, json={"ignore_open_days": True})
    assert forced.status_code == 200
    again = await client.post(_url(employee.id, "submit"), headers=hr)
    assert again.status_code == 409 and again.json()["code"] == "PERIOD_ALREADY_SUBMITTED"


async def test_only_the_employee_confirms_which_closes_and_only_admin_reopens(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ctx = await _setup(db_session, client)
    employee, hr = ctx["employee"], ctx["hr"]
    await _work_day(client, hr, employee.id, "2025-03-10")
    await client.post(_url(employee.id, "submit"), headers=hr)

    assert (await client.post(_url(employee.id, "confirm"), headers=hr)).status_code == 403  # HR bestätigt nicht für andere
    assert (await client.post(_url(employee.id, "confirm"), headers=ctx["other"])).status_code in (403, 404)
    # Die Bestätigung schließt den Monat direkt ab (kein eigener Status "bestätigt" mehr)
    confirmed = await client.post(_url(employee.id, "confirm"), headers=ctx["self"])
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "CLOSED"
    assert confirmed.json()["closed_without_confirmation"] is False and confirmed.json()["confirmed_at"] is not None
    assert (await client.post(_url(employee.id, "close"), headers=hr)).status_code == 409  # schon abgeschlossen

    assert (await client.post(_url(employee.id, "reopen"), headers=hr)).status_code == 403
    assert (await client.post(_url(employee.id, "reopen"), headers=ctx["admin"])).status_code == 204
    assert (await _punch(client, hr, employee.id, "COME", "2025-03-11T08:00:00Z")).status_code == 201

    # Der überholte Nachweis bleibt in der Akte, ist für den Mitarbeiter aber unsichtbar.
    assert (await client.get(f"/employees/{employee.id}/documents", headers=ctx["self"])).json() == []
    assert len((await client.get(f"/employees/{employee.id}/documents", headers=hr)).json()) == 1

    actions = {e.action for e in (await db_session.execute(select(AuditLogEntry))).scalars().all()}
    assert {AuditAction.PERIOD_SUBMITTED, AuditAction.PERIOD_CONFIRMED, AuditAction.PERIOD_REOPENED} <= actions


async def test_dispute_unlocks_month_notifies_hr_and_allows_resubmission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ctx = await _setup(db_session, client)
    employee, hr = ctx["employee"], ctx["hr"]
    await _work_day(client, hr, employee.id, "2025-03-10")
    await client.post(_url(employee.id, "submit"), headers=hr)

    too_short = await client.post(_url(employee.id, "dispute"), headers=ctx["self"], json={"reason": "x"})
    assert too_short.status_code == 422
    disputed = await client.post(_url(employee.id, "dispute"), headers=ctx["self"], json={"reason": "Am 11.03. habe ich auch gearbeitet."})
    assert disputed.status_code == 200 and disputed.json()["status"] == "DISPUTED"
    assert disputed.json()["dispute_reason"].startswith("Am 11.03.")

    hr_notes = (await db_session.execute(select(Notification).where(Notification.type == "PERIOD_DISPUTED"))).scalars().all()
    assert len(hr_notes) >= 1

    # Wieder bearbeitbar -> korrigieren und erneut vorlegen.
    await _work_day(client, hr, employee.id, "2025-03-11")
    resubmitted = await client.post(_url(employee.id, "submit"), headers=hr)
    assert resubmitted.status_code == 200 and resubmitted.json()["status"] == "SUBMITTED"
    assert resubmitted.json()["dispute_reason"] is None and resubmitted.json()["actual_minutes"] == 1020


async def test_close_without_confirmation_is_flagged(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client)
    employee, hr = ctx["employee"], ctx["hr"]
    await _work_day(client, hr, employee.id, "2025-03-10")
    await client.post(_url(employee.id, "submit"), headers=hr)
    closed = await client.post(_url(employee.id, "close"), headers=hr, json={"without_confirmation": True})
    assert closed.status_code == 200 and closed.json()["closed_without_confirmation"] is True


async def test_overview_and_bulk_submit(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client)
    employee, hr = ctx["employee"], ctx["hr"]
    await _work_day(client, hr, employee.id, "2025-03-10")

    results = await client.post("/period-closures/submit-all", headers=hr, json={"year": 2025, "month": 3})
    assert results.status_code == 200
    by_name = {r["last_name"]: r for r in results.json()}
    assert by_name["Muster"]["submitted"] is True and by_name["Andere"]["submitted"] is True

    overview = (await client.get("/period-closures", headers=hr, params={"year": 2025, "month": 3})).json()
    assert {r["last_name"]: r["status"] for r in overview} == {"Muster": "SUBMITTED", "Andere": "SUBMITTED"}

    # Mitarbeiter sehen nur ihre eigenen Abschlüsse, kein Überblick.
    assert (await client.get("/period-closures", headers=ctx["self"], params={"year": 2025, "month": 3})).status_code == 403
    own = await client.get(f"/employees/{employee.id}/period-closures", headers=ctx["self"])
    assert own.status_code == 200 and len(own.json()) == 1
    assert (await client.get(f"/employees/{employee.id}/period-closures", headers=ctx["other"])).status_code in (403, 404)


async def test_month_report_print_view_single_and_bulk(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client)
    employee, hr = ctx["employee"], ctx["hr"]
    await _work_day(client, hr, employee.id, "2025-03-10")

    single = await client.get(f"/employees/{employee.id}/month-report", headers=hr, params={"year": 2025, "month": 3})
    assert single.status_code == 200 and single.content.startswith(b"%PDF")
    assert single.headers["content-disposition"].startswith("inline")
    # Mitarbeiter selbst ja, fremder Mitarbeiter nein.
    assert (await client.get(f"/employees/{employee.id}/month-report", headers=ctx["self"], params={"year": 2025, "month": 3})).status_code == 200
    assert (await client.get(f"/employees/{employee.id}/month-report", headers=ctx["other"], params={"year": 2025, "month": 3})).status_code in (403, 404)

    bulk = await client.get("/month-reports", headers=hr, params={"year": 2025, "month": 3})
    assert bulk.status_code == 200 and bulk.content.startswith(b"%PDF")
    assert (await client.get("/month-reports", headers=ctx["self"], params={"year": 2025, "month": 3})).status_code == 403


async def test_open_requests_hold_back_submission(client: AsyncClient, db_session: AsyncSession) -> None:
    """Offene Anträge im Monat wären nach dem Vorlegen nicht mehr entscheidbar – erst Hinweis."""
    from datetime import date as _date

    from app.models import Absence, AbsenceApprovalStatus, AbsenceType

    ctx = await _setup(db_session, client)
    employee, hr = ctx["employee"], ctx["hr"]
    employee_id = employee.id
    await _work_day(client, hr, employee_id, "2025-03-10")
    db_session.add(
        Absence(
            employee_id=employee_id, type=AbsenceType.VACATION, date_from=_date(2025, 3, 27), date_to=_date(2025, 3, 28),
            approval_status=AbsenceApprovalStatus.PENDING,
        )
    )
    await db_session.commit()
    blocked = await client.post(_url(employee_id, "submit"), headers=hr)
    assert blocked.status_code == 409 and blocked.json()["code"] == "OPEN_REQUESTS_PRESENT"
    assert "1 Abwesenheitsantrag" in blocked.json()["detail"]
    forced = await client.post(_url(employee_id, "submit"), headers=hr, json={"ignore_open_requests": True, "ignore_open_days": True})
    assert forced.status_code == 200 and forced.json()["status"] == "SUBMITTED"


async def test_without_login_submit_closes_directly(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client)
    hr = ctx["hr"]
    location_id = ctx["employee"].location_id
    kiosk_only = Employee(location_id=location_id, first_name="Karl", last_name="Kiosk", employee_number="E3")
    db_session.add(kiosk_only)
    await db_session.commit()
    kiosk_id = kiosk_only.id
    await _work_day(client, hr, kiosk_id, "2025-03-10")
    r = await client.post(_url(kiosk_id, "submit"), headers=hr, json={"ignore_open_days": True})
    assert r.status_code == 200 and r.json()["status"] == "CLOSED" and r.json()["closed_without_confirmation"] is True


async def test_settings_that_recalculate_respect_closed_months(client: AsyncClient, db_session: AsyncSession) -> None:
    """Kontobeginn, Schichtplanung und maximale Schichtlänge rechneten bisher auch abgeschlossene
    Monate neu – jetzt nur, solange kein vorgelegter/abgeschlossener Monat betroffen ist."""
    from datetime import date as _date

    from app.models import ShiftPlanEntry

    ctx = await _setup(db_session, client)
    employee, hr, admin = ctx["employee"], ctx["hr"], ctx["admin"]
    employee_id = employee.id
    await _work_day(client, hr, employee_id, "2025-03-10")
    db_session.add(ShiftPlanEntry(employee_id=employee_id, date=_date(2025, 3, 12), is_workday=False))
    await db_session.commit()
    # vor dem Abschluss geht alles
    assert (await client.patch("/settings", headers=admin, json={"max_shift_span_hours": 14})).status_code == 200
    assert (await client.post(_url(employee_id, "submit"), headers=hr, json={"ignore_open_days": True})).status_code == 200

    for body in ({"balance_start_date": "2025-01-01"}, {"max_shift_span_hours": 16}, {"shift_planning_enabled": False}):
        r = await client.patch("/settings", headers=admin, json=body)
        assert r.status_code == 409 and r.json()["code"] == "PERIOD_LOCKED", body
    # Kontobeginn nach dem gesperrten Monat (bisher leer = erste Stempelung im März): betrifft März
    assert (await client.patch("/settings", headers=admin, json={"balance_start_date": "2025-06-01"})).status_code == 409
    assert (await client.post(_url(employee_id, "reopen"), headers=hr)).status_code == 204  # Vorlage zurückziehen
    assert (await client.patch("/settings", headers=admin, json={"balance_start_date": "2025-06-01"})).status_code == 200
