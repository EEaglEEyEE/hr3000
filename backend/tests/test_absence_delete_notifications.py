"""Abwesenheiten mit Benachrichtigungen löschen (Fehler seit Migration 0037).

notifications.related_absence_id ist ein Fremdschlüssel auf absences.id ohne ON DELETE. MySQL lehnte
das Löschen deshalb ab, sobald es zur Abwesenheit eine Benachrichtigung gab (Entscheidung über einen
Antrag, Vertretung) – in der Web-App ein Serverfehler 500. Die Tests liefen unter SQLite ohne
Fremdschlüsselprüfung und haben das nie gesehen; hier wird sie deshalb eingeschaltet.
"""
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.period_service as period_service
from absence_helpers import require_vacation_approval
from app.models import Absence, AbsenceApprovalStatus, AbsenceType, Employee, Notification, NotificationType
from app.services.auth_service import hash_password
from app.services.notification_service import unlink_absence
from tests.test_absence_types import _setup, _types

ERIKA = {"email": "erika@example.com", "password": "pw123456"}


@pytest.fixture
async def fk_on(db_session: AsyncSession) -> None:
    """SQLite prüft Fremdschlüssel nur mit PRAGMA foreign_keys=ON (je Verbindung). Die Test-Engine hat
    genau eine Verbindung (StaticPool), das PRAGMA gilt also für den ganzen Test."""
    async with db_session.bind.connect() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        assert (await conn.exec_driver_sql("PRAGMA foreign_keys")).scalar() == 1


async def _headers(client: AsyncClient, credentials: dict) -> dict:
    token = (await client.post("/auth/login", json=credentials)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _notes(db_session: AsyncSession, type_: NotificationType | None = None) -> list[Notification]:
    stmt = select(Notification).order_by(Notification.id)
    if type_ is not None:
        stmt = stmt.where(Notification.type == type_)
    rows = (await db_session.execute(stmt)).scalars().all()
    for row in rows:
        await db_session.refresh(row)
    return list(rows)


async def _decided_request(client: AsyncClient, db_session: AsyncSession, admin: dict, employee: Employee,
                           day: str, approve: bool = True) -> int:
    """Erika beantragt Urlaub (mit Genehmigungspflicht), der Admin entscheidet -> ABSENCE_DECIDED."""
    me = await _headers(client, ERIKA)
    r = await client.post("/absences", headers=me, json={"employee_id": employee.id, "type": "VACATION",
                                                         "date_from": day, "date_to": day})
    assert r.status_code == 201, r.text
    assert r.json()["approval_status"] == "PENDING"
    absence_id = r.json()["id"]
    r = await client.patch(f"/absences/{absence_id}/decide", headers=admin, json={"approve": approve})
    assert r.status_code == 200, r.text
    assert r.json()["approval_status"] == ("APPROVED" if approve else "REJECTED")
    return absence_id


async def _absence(db_session: AsyncSession, employee: Employee, day: date) -> Absence:
    row = Absence(employee_id=employee.id, type=AbsenceType.VACATION, date_from=day, date_to=day,
                  approval_status=AbsenceApprovalStatus.APPROVED)
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


def _note(employee: Employee, message: str, absence: Absence | None,
          type_: NotificationType = NotificationType.ABSENCE_DECIDED) -> Notification:
    return Notification(tenant_id=1, recipient_account_id=employee.account.id, type=type_, message=message,
                        related_absence_id=absence.id if absence is not None else None)


# --- unlink_absence direkt -----------------------------------------------------------------------


async def test_unlink_clears_only_notifications_of_that_absence(client: AsyncClient, db_session: AsyncSession,
                                                                fk_on) -> None:
    employee, _ = await _setup(db_session, client)
    a = await _absence(db_session, employee, date(2026, 8, 10))
    b = await _absence(db_session, employee, date(2026, 8, 11))
    db_session.add_all([
        _note(employee, "a entschieden", a),
        _note(employee, "a Vertretung", a, NotificationType.SUBSTITUTE_ASSIGNED),
        _note(employee, "b entschieden", b),
        _note(employee, "ohne Bezug", None, NotificationType.OPEN_DAYS_DIGEST),
    ])
    await db_session.commit()

    await unlink_absence(db_session, a.id)
    await db_session.commit()

    notes = await _notes(db_session)
    assert [(n.message, n.related_absence_id) for n in notes] == [
        ("a entschieden", None),
        ("a Vertretung", None),
        ("b entschieden", b.id),
        ("ohne Bezug", None),
    ]
    # Nur der Verweis ändert sich – Typ, Empfänger und Lesestatus bleiben
    assert [n.type for n in notes[:2]] == [NotificationType.ABSENCE_DECIDED, NotificationType.SUBSTITUTE_ASSIGNED]
    assert all(n.recipient_account_id == employee.account.id and n.read_at is None for n in notes)


async def test_unlink_keeps_read_state(client: AsyncClient, db_session: AsyncSession, fk_on) -> None:
    from datetime import datetime

    employee, _ = await _setup(db_session, client)
    a = await _absence(db_session, employee, date(2026, 8, 10))
    note = _note(employee, "gelesen", a)
    note.read_at = datetime(2026, 8, 1, 9, 30)
    db_session.add(note)
    await db_session.commit()

    await unlink_absence(db_session, a.id)
    await db_session.commit()

    [row] = await _notes(db_session)
    assert row.related_absence_id is None and row.read_at == datetime(2026, 8, 1, 9, 30)


async def test_unlink_without_notifications_is_a_noop(client: AsyncClient, db_session: AsyncSession, fk_on) -> None:
    employee, _ = await _setup(db_session, client)
    a = await _absence(db_session, employee, date(2026, 8, 10))

    await unlink_absence(db_session, a.id)
    await unlink_absence(db_session, 999_999)  # unbekannte ID: kein Fehler
    await db_session.commit()

    assert await _notes(db_session) == []
    assert await db_session.get(Absence, a.id) is not None  # die Abwesenheit selbst bleibt


async def test_unlink_twice_is_harmless(client: AsyncClient, db_session: AsyncSession, fk_on) -> None:
    employee, _ = await _setup(db_session, client)
    a = await _absence(db_session, employee, date(2026, 8, 10))
    db_session.add(_note(employee, "a", a))
    await db_session.commit()

    await unlink_absence(db_session, a.id)
    await unlink_absence(db_session, a.id)
    await db_session.commit()

    assert [n.related_absence_id for n in await _notes(db_session)] == [None]


async def test_without_unlink_the_foreign_key_blocks_the_delete(client: AsyncClient, db_session: AsyncSession,
                                                                fk_on) -> None:
    """Gegenprobe: ohne unlink_absence scheitert das Löschen – so wie vorher auf MySQL. Zeigt auch,
    dass die Fremdschlüsselprüfung in diesen Tests wirklich greift."""
    employee, _ = await _setup(db_session, client)
    a = await _absence(db_session, employee, date(2026, 8, 10))
    db_session.add(_note(employee, "a", a))
    await db_session.commit()

    await db_session.delete(a)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# --- DELETE /absences/{id} -----------------------------------------------------------------------


async def test_delete_approved_request_keeps_the_notification(client: AsyncClient, db_session: AsyncSession,
                                                              fk_on) -> None:
    employee, admin = await _setup(db_session, client)
    await require_vacation_approval(db_session)
    absence_id = await _decided_request(client, db_session, admin, employee, "2026-08-10")
    [note] = await _notes(db_session, NotificationType.ABSENCE_DECIDED)
    assert note.related_absence_id == absence_id

    r = await client.delete(f"/absences/{absence_id}", headers=admin)
    assert r.status_code == 204, r.text

    assert await db_session.get(Absence, absence_id) is None
    [note] = await _notes(db_session, NotificationType.ABSENCE_DECIDED)
    assert note.related_absence_id is None and "genehmigt" in note.message
    # Erika sieht ihre Benachrichtigung weiterhin
    listed = (await client.get("/notifications", headers=await _headers(client, ERIKA))).json()
    assert [(n["type"], n["related_absence_id"]) for n in listed] == [("ABSENCE_DECIDED", None)]


async def test_delete_rejected_request(client: AsyncClient, db_session: AsyncSession, fk_on) -> None:
    employee, admin = await _setup(db_session, client)
    await require_vacation_approval(db_session)
    absence_id = await _decided_request(client, db_session, admin, employee, "2026-08-10", approve=False)

    r = await client.delete(f"/absences/{absence_id}", headers=admin)
    assert r.status_code == 204, r.text
    [note] = await _notes(db_session, NotificationType.ABSENCE_DECIDED)
    assert note.related_absence_id is None and "abgelehnt" in note.message


async def test_delete_absence_with_substitute_notification(client: AsyncClient, db_session: AsyncSession,
                                                           fk_on) -> None:
    employee, admin = await _setup(db_session, client)
    colleague = Employee(location_id=employee.location_id, first_name="Max", last_name="Vertreter",
                         employee_number="A2", login_email="max@example.com", password_hash=hash_password("pw123456"))
    db_session.add(colleague)
    await db_session.commit()
    vacation = (await _types(client, admin))["Urlaub"]
    r = await client.patch(f"/absence-types/{vacation['id']}", headers=admin, json={"substitute_mode": "OPTIONAL"})
    assert r.status_code == 200, r.text
    r = await client.post("/absences", headers=admin, json={
        "employee_id": employee.id, "absence_type_id": vacation["id"], "date_from": "2026-08-10",
        "date_to": "2026-08-12", "substitute_employee_id": colleague.id,
    })
    assert r.status_code == 201, r.text
    absence_id = r.json()["id"]
    [note] = await _notes(db_session, NotificationType.SUBSTITUTE_ASSIGNED)
    assert note.related_absence_id == absence_id

    r = await client.delete(f"/absences/{absence_id}", headers=admin)
    assert r.status_code == 204, r.text
    [note] = await _notes(db_session, NotificationType.SUBSTITUTE_ASSIGNED)
    assert note.related_absence_id is None and "Erika Muster" in note.message


async def test_delete_leaves_notifications_of_other_absences_linked(client: AsyncClient, db_session: AsyncSession,
                                                                    fk_on) -> None:
    employee, admin = await _setup(db_session, client)
    await require_vacation_approval(db_session)
    first = await _decided_request(client, db_session, admin, employee, "2026-08-10")
    second = await _decided_request(client, db_session, admin, employee, "2026-08-11", approve=False)

    r = await client.delete(f"/absences/{first}", headers=admin)
    assert r.status_code == 204, r.text

    notes = await _notes(db_session, NotificationType.ABSENCE_DECIDED)
    assert sorted((n.related_absence_id or 0) for n in notes) == [0, second]
    r = await client.delete(f"/absences/{second}", headers=admin)
    assert r.status_code == 204, r.text
    assert [n.related_absence_id for n in await _notes(db_session, NotificationType.ABSENCE_DECIDED)] == [None, None]


async def test_delete_without_notifications_still_works(client: AsyncClient, db_session: AsyncSession,
                                                        fk_on) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.post("/absences", headers=admin, json={"employee_id": employee.id, "type": "VACATION",
                                                            "date_from": "2026-08-10", "date_to": "2026-08-10"})
    assert r.status_code == 201, r.text
    r = await client.delete(f"/absences/{r.json()['id']}", headers=admin)
    assert r.status_code == 204, r.text
    assert await _notes(db_session) == []


async def test_locked_month_blocks_delete_and_keeps_the_link(client: AsyncClient, db_session: AsyncSession,
                                                             fk_on, monkeypatch: pytest.MonkeyPatch) -> None:
    employee, admin = await _setup(db_session, client)
    await require_vacation_approval(db_session)
    absence_id = await _decided_request(client, db_session, admin, employee, "2026-08-10")

    async def locked(db, employee_id):
        return {(2026, 8)}

    monkeypatch.setattr(period_service, "locked_months", locked)
    r = await client.delete(f"/absences/{absence_id}", headers=admin)
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_LOCKED"
    assert await db_session.get(Absence, absence_id) is not None
    [note] = await _notes(db_session, NotificationType.ABSENCE_DECIDED)
    assert note.related_absence_id == absence_id


async def test_employee_cannot_delete_and_link_stays(client: AsyncClient, db_session: AsyncSession, fk_on) -> None:
    employee, admin = await _setup(db_session, client)
    await require_vacation_approval(db_session)
    absence_id = await _decided_request(client, db_session, admin, employee, "2026-08-10")

    r = await client.delete(f"/absences/{absence_id}", headers=await _headers(client, ERIKA))
    assert r.status_code in (401, 403)
    [note] = await _notes(db_session, NotificationType.ABSENCE_DECIDED)
    assert note.related_absence_id == absence_id


# --- Krank im Urlaub: Urlaub wird ganz ersetzt ---------------------------------------------------


async def test_sickness_covering_a_decided_vacation_removes_it(client: AsyncClient, db_session: AsyncSession,
                                                               fk_on) -> None:
    employee, admin = await _setup(db_session, client)
    await require_vacation_approval(db_session)
    vacation_id = await _decided_request(client, db_session, admin, employee, "2026-08-10")

    r = await client.post("/absences", headers=admin, json={"employee_id": employee.id, "type": "SICK",
                                                            "date_from": "2026-08-10", "date_to": "2026-08-10",
                                                            "split_vacation": True})
    assert r.status_code == 201, r.text

    # SQLite vergibt die frei gewordene ID gleich wieder (hier an die Krankmeldung) – deshalb nach Art prüfen
    rows = (await db_session.execute(select(Absence))).scalars().all()
    for row in rows:
        await db_session.refresh(row)
    assert [(row.id, row.type) for row in rows] == [(r.json()["id"], AbsenceType.SICK)]
    [note] = await _notes(db_session, NotificationType.ABSENCE_DECIDED)
    assert note.related_absence_id is None and vacation_id is not None


async def test_sickness_shortening_a_vacation_keeps_the_link(client: AsyncClient, db_session: AsyncSession,
                                                             fk_on) -> None:
    """Wird der Urlaub nur gekürzt, bleibt er bestehen – und die Benachrichtigung verweist weiter darauf."""
    employee, admin = await _setup(db_session, client)
    await require_vacation_approval(db_session)
    me = await _headers(client, ERIKA)
    r = await client.post("/absences", headers=me, json={"employee_id": employee.id, "type": "VACATION",
                                                         "date_from": "2026-08-10", "date_to": "2026-08-12"})
    vacation_id = r.json()["id"]
    r = await client.patch(f"/absences/{vacation_id}/decide", headers=admin, json={"approve": True})
    assert r.status_code == 200 and r.json()["approval_status"] == "APPROVED", r.text

    r = await client.post("/absences", headers=admin, json={"employee_id": employee.id, "type": "SICK",
                                                            "date_from": "2026-08-12", "date_to": "2026-08-12",
                                                            "split_vacation": True})
    assert r.status_code == 201, r.text

    vacation = await db_session.get(Absence, vacation_id)
    await db_session.refresh(vacation)
    assert (vacation.date_from.isoformat(), vacation.date_to.isoformat()) == ("2026-08-10", "2026-08-11")
    [note] = await _notes(db_session, NotificationType.ABSENCE_DECIDED)
    assert note.related_absence_id == vacation_id
