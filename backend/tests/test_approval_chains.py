"""Genehmigungsketten je Abwesenheitsart: Führungskraft, erst Führungskraft dann Admin/HR, mehrere
Leitungen, Stellvertretung während der Abwesenheit der Leitungen, Rückfall von der abwesenden Ausnahme
auf die Abteilung, ohne Führungskraft Rückfall auf Admin/HR."""
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence, AbsenceApproval, AbsenceApprovalStatus, AbsenceType, Account, Employee, HrRole, Location, Notification,
)
from app.services.auth_service import hash_password
from tests.org_helpers import department

PW = "pw123456"
FUTURE = date.today() + timedelta(days=60)


async def _people(db_session: AsyncSession) -> dict[str, Employee]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    db_session.add(Account(email="hr@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN))
    await db_session.commit()

    def person(first: str, number: str, role: HrRole | None = None) -> Employee:
        return Employee(
            location_id=location.id, first_name=first, last_name="Test", employee_number=number,
            login_email=f"{first.lower()}@example.com", password_hash=hash_password(PW), hr_role=role,
        )

    people = {
        "bea": person("Bea", "1", HrRole.SUPERVISOR),
        "carl": person("Carl", "2", HrRole.SUPERVISOR),
        "tom": person("Tom", "3", HrRole.SUPERVISOR),
        "erika": person("Erika", "4"),
    }
    db_session.add_all(people.values())
    await db_session.commit()
    people["erika"].supervisor_id = people["bea"].id
    await db_session.commit()
    return people


async def _token(client: AsyncClient, email: str) -> dict[str, str]:
    r = await client.post("/auth/login", json={"email": email, "password": PW})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _set_chain(client: AsyncClient, hr: dict, chain: str) -> None:
    types = (await client.get("/absence-types", headers=hr)).json()
    vacation = next(t for t in types if t["category"] == "VACATION")
    r = await client.patch(f"/absence-types/{vacation['id']}", headers=hr, json={"approval_chain": chain, "requires_approval": True})
    assert r.status_code == 200 and r.json()["approval_chain"] == chain


async def _request(client: AsyncClient, people: dict, offset: int = 0) -> dict:
    erika = await _token(client, "erika@example.com")
    day = FUTURE + timedelta(days=offset)
    r = await client.post(
        "/absences", headers=erika,
        json={"employee_id": people["erika"].id, "type": "VACATION", "date_from": str(day), "date_to": str(day)},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_supervisor_decides(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _people(db_session)
    hr = await _token(client, "hr@example.com")
    await _set_chain(client, hr, "SUPERVISOR")
    absence = await _request(client, people)
    assert (absence["approval_status"], absence["waiting_for"]) == ("PENDING", "Führungskraft Bea Test")
    notes = (await db_session.execute(select(Notification.recipient_account_id))).scalars().all()
    assert notes == [people["bea"].account.id]

    bea, tom = await _token(client, "bea@example.com"), await _token(client, "tom@example.com")
    assert [a["id"] for a in (await client.get("/absences/pending", headers=bea)).json()] == [absence["id"]]
    assert (await client.get("/absences/pending", headers=tom)).json() == []
    assert (await client.patch(f"/absences/{absence['id']}/decide", headers=tom, json={"approve": True})).status_code == 403
    decided = await client.patch(f"/absences/{absence['id']}/decide", headers=bea, json={"approve": True})
    assert decided.json()["approval_status"] == "APPROVED"


async def test_supervisor_then_hr(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _people(db_session)
    hr = await _token(client, "hr@example.com")
    await _set_chain(client, hr, "SUPERVISOR_HR")
    absence = await _request(client, people)
    assert absence["waiting_for"] == "Schritt 1 von 2: Führungskraft Bea Test"
    bea = await _token(client, "bea@example.com")

    step1 = (await client.patch(f"/absences/{absence['id']}/decide", headers=bea, json={"approve": True})).json()
    assert (step1["approval_status"], step1["approval_step"], step1["waiting_for"]) == ("PENDING", 2, "Schritt 2 von 2: Admin/HR")
    assert (await client.patch(f"/absences/{absence['id']}/decide", headers=bea, json={"approve": True})).status_code == 403
    final = (await client.patch(f"/absences/{absence['id']}/decide", headers=hr, json={"approve": True})).json()
    assert final["approval_status"] == "APPROVED"
    history = (await db_session.execute(select(AbsenceApproval.step_type, AbsenceApproval.approved))).all()
    assert [tuple(row) for row in history] == [("SUPERVISOR", True), ("HR", True)]

    rejected = await _request(client, people, offset=1)
    r = await client.patch(f"/absences/{rejected['id']}/decide", headers=bea, json={"approve": False})
    assert r.json()["approval_status"] == "REJECTED"


async def _absent_today(db_session: AsyncSession, person: Employee) -> None:
    db_session.add(Absence(
        employee_id=person.id, type=AbsenceType.VACATION, date_from=date.today(), date_to=date.today(),
        approval_status=AbsenceApprovalStatus.APPROVED,
    ))
    await db_session.commit()


async def _in_department(db_session: AsyncSession, people: dict, *, heads: tuple, deputies: tuple = ()) -> None:
    """Erika ohne Ausnahme in eine Abteilung mit diesen Leitungen und Stellvertretungen."""
    people["erika"].supervisor_id = None
    await department(db_session, "Team", people["erika"], heads=heads, deputies=deputies)


async def _notified(db_session: AsyncSession) -> list[int]:
    return sorted((await db_session.execute(select(Notification.recipient_account_id))).scalars().all())


async def test_deputy_decides_while_all_heads_are_absent(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _people(db_session)
    await _in_department(db_session, people, heads=(people["bea"],), deputies=((people["carl"], "STANDBY"),))
    hr = await _token(client, "hr@example.com")
    await _set_chain(client, hr, "SUPERVISOR")
    await _absent_today(db_session, people["bea"])
    absence = await _request(client, people)
    assert absence["waiting_for"] == "Führungskraft Carl Test"
    assert await _notified(db_session) == [people["carl"].account.id]
    bea, carl = await _token(client, "bea@example.com"), await _token(client, "carl@example.com")
    assert (await client.patch(f"/absences/{absence['id']}/decide", headers=bea, json={"approve": True})).status_code == 403
    assert (await client.patch(f"/absences/{absence['id']}/decide", headers=carl, json={"approve": True})).status_code == 200


async def test_standby_deputy_waits_while_a_head_is_there(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _people(db_session)
    await _in_department(db_session, people, heads=(people["bea"],), deputies=((people["carl"], "STANDBY"),))
    hr = await _token(client, "hr@example.com")
    await _set_chain(client, hr, "SUPERVISOR")
    absence = await _request(client, people)
    assert absence["waiting_for"] == "Führungskraft Bea Test"
    carl = await _token(client, "carl@example.com")
    assert (await client.patch(f"/absences/{absence['id']}/decide", headers=carl, json={"approve": True})).status_code == 403


async def test_several_heads_are_all_notified_and_any_decides(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _people(db_session)
    await _in_department(db_session, people, heads=(people["bea"], people["tom"]), deputies=((people["carl"], "FULL"),))
    hr = await _token(client, "hr@example.com")
    await _set_chain(client, hr, "SUPERVISOR")
    absence = await _request(client, people)
    assert absence["waiting_for"] == "Führungskräfte Bea Test, Tom Test, Carl Test"  # Stellvertretung mit vollen Rechten dabei
    assert await _notified(db_session) == sorted(people[p].account.id for p in ("bea", "tom", "carl"))
    tom = await _token(client, "tom@example.com")
    decided = await client.patch(f"/absences/{absence['id']}/decide", headers=tom, json={"approve": True})
    assert decided.status_code == 200 and decided.json()["approval_status"] == "APPROVED"


async def test_present_heads_decide_absent_ones_do_not(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _people(db_session)
    await _in_department(db_session, people, heads=(people["bea"], people["tom"]), deputies=((people["carl"], "STANDBY"),))
    hr = await _token(client, "hr@example.com")
    await _set_chain(client, hr, "SUPERVISOR")
    await _absent_today(db_session, people["bea"])
    absence = await _request(client, people)
    assert absence["waiting_for"] == "Führungskraft Tom Test"  # Tom ist da: keine Stellvertretung nötig


async def test_absent_heads_without_deputy_stay_responsible(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _people(db_session)
    await _in_department(db_session, people, heads=(people["bea"],))
    hr = await _token(client, "hr@example.com")
    await _set_chain(client, hr, "SUPERVISOR")
    await _absent_today(db_session, people["bea"])
    absence = await _request(client, people)
    assert absence["waiting_for"] == "Führungskraft Bea Test"  # verwaist nicht, Admin/HR können ohnehin


async def test_absent_override_falls_back_to_the_department(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _people(db_session)
    await _in_department(db_session, people, heads=(people["bea"],))
    people["erika"].supervisor_id = people["tom"].id  # Ausnahme: Tom statt Bea
    await db_session.commit()
    hr = await _token(client, "hr@example.com")
    await _set_chain(client, hr, "SUPERVISOR")
    first = await _request(client, people)
    assert first["waiting_for"] == "Führungskraft Tom Test"
    await _absent_today(db_session, people["tom"])
    second = await _request(client, people, offset=1)
    assert second["waiting_for"] == "Führungskraft Bea Test"
    tom, bea = await _token(client, "tom@example.com"), await _token(client, "bea@example.com")
    assert (await client.patch(f"/absences/{second['id']}/decide", headers=tom, json={"approve": True})).status_code == 403
    assert (await client.patch(f"/absences/{second['id']}/decide", headers=bea, json={"approve": True})).status_code == 200


async def test_absent_override_without_department_stays_responsible(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _people(db_session)
    hr = await _token(client, "hr@example.com")
    await _set_chain(client, hr, "SUPERVISOR")
    await _absent_today(db_session, people["bea"])
    absence = await _request(client, people)
    assert absence["waiting_for"] == "Führungskraft Bea Test"


async def test_without_supervisor_admin_hr_decides(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _people(db_session)
    people["erika"].supervisor_id = None
    await db_session.commit()
    hr = await _token(client, "hr@example.com")
    await _set_chain(client, hr, "SUPERVISOR")
    absence = await _request(client, people)
    assert absence["waiting_for"] == "Admin/HR (keine Führungskraft mit Zugang)"
    bea = await _token(client, "bea@example.com")
    assert (await client.patch(f"/absences/{absence['id']}/decide", headers=bea, json={"approve": True})).status_code == 403
    assert (await client.patch(f"/absences/{absence['id']}/decide", headers=hr, json={"approve": True})).status_code == 200
