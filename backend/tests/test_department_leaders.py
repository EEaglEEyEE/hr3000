"""Mehrere Leitungen und Stellvertretungen (Entscheidung 09.11.2026): Was eine Stellvertretung je nach
Rechten sieht, entscheidet und wer benachrichtigt wird – solange die Leitung da ist und während sie
fehlt (app/services/scope_service.py, approval_service.py)."""
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from absence_helpers import require_vacation_approval
from app.models import (
    Absence, AbsenceApprovalStatus, AbsenceType, Account, Department, Employee, HrRole, Location, Notification,
)
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings
from org_helpers import department, set_leaders

PW = "pw"
FUTURE = date.today() + timedelta(days=60)


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": PW})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _person(db_session: AsyncSession, location: Location, number: str, first: str, role: HrRole | None = None) -> Employee:
    person = Employee(location_id=location.id, first_name=first, last_name="Test", employee_number=number)
    db_session.add(person)
    await db_session.flush()
    db_session.add(Account(email=f"{first.lower()}@example.com", password_hash=hash_password(PW), role=role, employee=person))
    await db_session.commit()
    return person


async def _company(db_session: AsyncSession) -> dict[str, Employee]:
    """Vertrieb: Leitung Hanna; Stellvertretungen Fritz (FULL), Sina (STANDBY), Abby (ABSENCE); Max arbeitet
    dort. Lea im Lager (ohne Leitung). Die Stellvertretungen gehören selbst keiner Abteilung an."""
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add_all([location, Account(email="admin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN)])
    await db_session.commit()
    people = {
        "hanna": await _person(db_session, location, "1", "Hanna", HrRole.SUPERVISOR),
        "fritz": await _person(db_session, location, "2", "Fritz", HrRole.SUPERVISOR),
        "sina": await _person(db_session, location, "3", "Sina", HrRole.SUPERVISOR),
        "abby": await _person(db_session, location, "4", "Abby", HrRole.SUPERVISOR),
        "max": await _person(db_session, location, "5", "Max"),
        "lea": await _person(db_session, location, "6", "Lea"),
    }
    await department(
        db_session, "Vertrieb", people["hanna"], people["max"], head=people["hanna"],
        deputies=((people["fritz"], "FULL"), (people["sina"], "STANDBY"), (people["abby"], "ABSENCE")),
    )
    await department(db_session, "Lager", people["lea"])
    await require_vacation_approval(db_session)
    return people


async def _absent_today(db_session: AsyncSession, person: Employee) -> None:
    db_session.add(Absence(
        employee_id=person.id, type=AbsenceType.VACATION, date_from=date.today(), date_to=date.today(),
        approval_status=AbsenceApprovalStatus.APPROVED,
    ))
    await db_session.commit()


async def _visible(client: AsyncClient, who: str) -> set[str]:
    response = await client.get("/employees", headers=await _login(client, f"{who}@example.com"))
    assert response.status_code == 200, response.text
    return {e["first_name"] for e in response.json()}


async def _request(client: AsyncClient, max_id: int, offset: int = 0) -> dict:
    day = FUTURE + timedelta(days=offset)
    response = await client.post(
        "/absences", headers=await _login(client, "max@example.com"),
        json={"employee_id": max_id, "type": "VACATION", "date_from": str(day), "date_to": str(day)},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _can_decide(client: AsyncClient, who: str, absence_id: int) -> bool:
    pending = (await client.get("/absences/pending", headers=await _login(client, f"{who}@example.com"))).json()
    return absence_id in [a["id"] for a in pending]


async def _notified(db_session: AsyncSession, people: dict[str, Employee]) -> set[str]:
    by_account = {p.account.id: name for name, p in people.items()}
    ids = (await db_session.execute(select(Notification.recipient_account_id))).scalars().all()
    return {by_account.get(i, f"#{i}") for i in ids}


async def test_what_each_deputy_sees_while_the_head_is_there(client: AsyncClient, db_session: AsyncSession) -> None:
    await _company(db_session)
    assert await _visible(client, "hanna") == {"Hanna", "Max"}
    assert await _visible(client, "fritz") == {"Fritz", "Max"}  # gleiche Rechte
    assert await _visible(client, "sina") == {"Sina", "Max"}  # sieht immer
    assert await _visible(client, "abby") == {"Abby"}  # nur während Abwesenheit


async def test_absence_deputy_sees_the_department_while_the_head_is_absent(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _company(db_session)
    await _absent_today(db_session, people["hanna"])
    assert await _visible(client, "abby") == {"Abby", "Max"}
    assert await _visible(client, "sina") == {"Sina", "Max"}
    max_id = people["max"].id
    detail = await client.get(f"/employees/{max_id}", headers=await _login(client, "abby@example.com"))
    assert detail.status_code == 200


async def test_absence_deputy_gets_404_for_the_department_while_the_head_is_there(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _company(db_session)
    max_id = people["max"].id
    detail = await client.get(f"/employees/{max_id}", headers=await _login(client, "abby@example.com"))
    assert detail.status_code == 404


async def test_who_decides_and_is_notified_while_the_head_is_there(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _company(db_session)
    absence = await _request(client, people["max"].id)
    assert absence["waiting_for"] == "Führungskraft"
    assert await _notified(db_session, people) == {"hanna", "fritz"}  # Leitung + Stellvertretung mit vollen Rechten
    assert await _can_decide(client, "hanna", absence["id"])
    assert await _can_decide(client, "fritz", absence["id"])
    assert not await _can_decide(client, "sina", absence["id"])
    assert not await _can_decide(client, "abby", absence["id"])
    sina = await _login(client, "sina@example.com")
    assert (await client.patch(f"/absences/{absence['id']}/decide", headers=sina, json={"approve": True})).status_code == 403
    fritz = await _login(client, "fritz@example.com")
    decided = await client.patch(f"/absences/{absence['id']}/decide", headers=fritz, json={"approve": True})
    assert decided.status_code == 200 and decided.json()["approval_status"] == "APPROVED"


async def test_who_decides_and_is_notified_while_the_head_is_absent(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _company(db_session)
    await _absent_today(db_session, people["hanna"])
    absence = await _request(client, people["max"].id)
    assert await _notified(db_session, people) == {"fritz", "sina", "abby"}  # Hanna fehlt: alle Stellvertretungen
    for who in ("fritz", "sina", "abby"):
        assert await _can_decide(client, who, absence["id"]), who
    assert await _can_decide(client, "hanna", absence["id"])  # Leitung darf trotzdem (z. B. von unterwegs)
    abby = await _login(client, "abby@example.com")
    decided = await client.patch(f"/absences/{absence['id']}/decide", headers=abby, json={"approve": False})
    assert decided.status_code == 200 and decided.json()["approval_status"] == "REJECTED"


async def test_deputies_act_when_the_head_cannot_log_in(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _company(db_session)
    people["hanna"].account.role = None  # Leitung ohne Verwaltungsrolle: kann nicht entscheiden
    await db_session.commit()
    absence = await _request(client, people["max"].id)
    assert await _notified(db_session, people) == {"fritz", "sina", "abby"}
    assert await _can_decide(client, "sina", absence["id"])
    assert await _visible(client, "abby") == {"Abby", "Max"}


async def test_deputies_never_decide_their_own_requests(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _company(db_session)
    sina = people["sina"]
    sina.department_id = people["max"].department_id  # Sina arbeitet selbst im Vertrieb
    (await get_or_create_settings(db_session, 1)).absence_four_eyes = True  # eigene Anträge nicht direkt genehmigt
    await db_session.commit()
    await _absent_today(db_session, people["hanna"])
    day = FUTURE
    created = await client.post(
        "/absences", headers=await _login(client, "sina@example.com"),
        json={"employee_id": sina.id, "type": "VACATION", "date_from": str(day), "date_to": str(day)},
    )
    assert created.status_code == 201, created.text
    assert created.json()["approval_status"] == "PENDING"
    absence_id = created.json()["id"]
    assert not await _can_decide(client, "sina", absence_id)
    assert await _can_decide(client, "abby", absence_id)


async def test_department_without_head_is_led_by_its_deputies(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _company(db_session)
    lea = people["lea"]
    store = (await db_session.execute(select(Department).where(Department.name == "Lager"))).scalar_one()
    await set_leaders(db_session, store, deputies=((people["sina"], "STANDBY"),))
    await db_session.commit()
    assert await _visible(client, "sina") == {"Sina", "Max", "Lea"}
    day = FUTURE
    created = await client.post(
        "/absences", headers=await _login(client, "lea@example.com"),
        json={"employee_id": lea.id, "type": "VACATION", "date_from": str(day), "date_to": str(day)},
    )
    assert created.status_code == 201, created.text
    assert await _can_decide(client, "sina", created.json()["id"])  # keine Leitung da: Stellvertretung entscheidet
    assert not await _can_decide(client, "hanna", created.json()["id"])


async def test_org_chart_lists_leaders_in_order_without_inactive_ones(client: AsyncClient, db_session: AsyncSession) -> None:
    people = await _company(db_session)
    people["abby"].active = False
    await db_session.commit()
    admin = await _login(client, "admin@example.com")
    chart = (await client.get("/org-chart", headers=admin)).json()
    sales = next(d for d in chart["departments"] if d["name"] == "Vertrieb")
    ids = {p.id: name for name, p in people.items()}
    assert [(ids[l["employee_id"]], l["role"], l["deputy_rights"]) for l in sales["leaders"]] == [
        ("hanna", "HEAD", "STANDBY"), ("fritz", "DEPUTY", "FULL"), ("sina", "DEPUTY", "STANDBY"),
    ]
    by_name = {p["first_name"]: p for p in chart["people"]}
    assert by_name["Max"]["supervisor_ids"] == [people["hanna"].id]
    assert by_name["Fritz"]["supervisor_ids"] == []  # Stellvertretungen sind keine Führungskräfte
