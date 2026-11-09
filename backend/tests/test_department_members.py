"""Mitarbeiter im Organigramm einer Abteilung hinzufügen: POST /departments/{id}/members (mehrere auf
einmal, alles oder nichts, nur Admin und HR)."""
import json
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.departments import AUDIT_DETAIL_MAX, _members_note
from app.models import Account, AuditAction, AuditLogEntry, Department, Employee, HrRole, Location, Tenant, WebhookDelivery
from app.services.auth_service import hash_password
from org_helpers import department

PW = "pw123456"


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": PW})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _person(
    db_session: AsyncSession, location: Location, number: str, first: str, role: HrRole | None = None, login: bool = False
) -> Employee:
    person = Employee(location_id=location.id, first_name=first, last_name="Test", employee_number=number)
    db_session.add(person)
    await db_session.flush()
    if role is not None or login:
        db_session.add(
            Account(email=f"{first.lower()}@example.com", password_hash=hash_password(PW), role=role, employee=person)
        )
    await db_session.commit()
    return person


async def _company(db_session: AsyncSession) -> dict[str, int]:
    """Vertrieb (Leitung Hanna, Mitarbeiterin Max), Lager (Leitung Tom, Mitarbeiter Lea), ohne Abteilung:
    Olga und Otto. Gibt die IDs zurück – die App rollt bei Fehlern dieselbe Session zurück."""
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add_all([location, Account(email="admin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN)])
    await db_session.commit()
    hanna = await _person(db_session, location, "1", "Hanna", HrRole.SUPERVISOR)
    tom = await _person(db_session, location, "2", "Tom", HrRole.SUPERVISOR)
    max_ = await _person(db_session, location, "3", "Max")
    lea = await _person(db_session, location, "4", "Lea")
    olga = await _person(db_session, location, "5", "Olga")
    otto = await _person(db_session, location, "6", "Otto")
    sales = await department(db_session, "Vertrieb", hanna, max_, head=hanna)
    store = await department(db_session, "Lager", tom, lea, head=tom)
    return {
        "hanna": hanna.id, "tom": tom.id, "max": max_.id, "lea": lea.id, "olga": olga.id, "otto": otto.id,
        "sales": sales.id, "store": store.id, "location": location.id,
    }


async def _department_of(db_session: AsyncSession, employee_id: int) -> int | None:
    return (await db_session.execute(select(Employee.department_id).where(Employee.id == employee_id))).scalar_one()


async def _audits(db_session: AsyncSession) -> list[AuditLogEntry]:
    return list(
        (
            await db_session.execute(
                select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.DEPARTMENT_CHANGED).order_by(AuditLogEntry.id)
            )
        ).scalars()
    )


async def test_admin_adds_people_without_department_and_from_other_departments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ids = await _company(db_session)
    admin = await _login(client, "admin@example.com")
    before = len(await _audits(db_session))

    response = await client.post(
        f"/departments/{ids['sales']}/members", headers=admin, json={"employee_ids": [ids["olga"], ids["lea"]]}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["added"] == 2
    assert body["department"]["id"] == ids["sales"]
    assert body["department"]["employee_count"] == 4  # Hanna, Max, Olga, Lea
    db_session.expire_all()
    assert await _department_of(db_session, ids["olga"]) == ids["sales"]
    assert await _department_of(db_session, ids["lea"]) == ids["sales"]
    assert await _department_of(db_session, ids["otto"]) is None  # nicht gewählt, bleibt
    audits = await _audits(db_session)
    assert len(audits) == before + 1
    detail = audits[-1].detail
    assert detail.startswith("2 Mitarbeiter in Abteilung „Vertrieb“ aufgenommen: ")
    assert "Olga Test (bisher ohne Abteilung)" in detail
    assert "Lea Test (bisher „Lager“)" in detail
    assert audits[-1].entity_id == ids["sales"]


async def test_added_people_get_the_department_heads_as_supervisors(client: AsyncClient, db_session: AsyncSession) -> None:
    ids = await _company(db_session)
    admin = await _login(client, "admin@example.com")
    await client.post(f"/departments/{ids['store']}/members", headers=admin, json={"employee_ids": [ids["olga"]]})

    olga = (await client.get(f"/employees/{ids['olga']}", headers=admin)).json()
    assert olga["department_id"] == ids["store"]
    assert olga["effective_supervisor_ids"] == [ids["tom"]]
    assert olga["supervisor_source"] == "DEPARTMENT"
    chart = (await client.get("/org-chart", headers=admin)).json()
    person = next(p for p in chart["people"] if p["employee_id"] == ids["olga"])
    assert (person["department"], person["supervisor_ids"]) == ("Lager", [ids["tom"]])


async def test_people_already_in_the_department_stay_unchanged(client: AsyncClient, db_session: AsyncSession) -> None:
    ids = await _company(db_session)
    admin = await _login(client, "admin@example.com")
    before = len(await _audits(db_session))

    only_members = await client.post(
        f"/departments/{ids['sales']}/members", headers=admin, json={"employee_ids": [ids["max"], ids["hanna"]]}
    )
    assert only_members.status_code == 200
    assert only_members.json()["added"] == 0
    assert len(await _audits(db_session)) == before  # nichts geändert, nichts protokolliert

    mixed = await client.post(
        f"/departments/{ids['sales']}/members", headers=admin, json={"employee_ids": [ids["max"], ids["otto"]]}
    )
    assert mixed.json()["added"] == 1
    audits = await _audits(db_session)
    assert len(audits) == before + 1
    assert audits[-1].detail == "1 Mitarbeiter in Abteilung „Vertrieb“ aufgenommen: Otto Test (bisher ohne Abteilung)"


async def test_hr_may_add_members(client: AsyncClient, db_session: AsyncSession) -> None:
    ids = await _company(db_session)
    location = await db_session.get(Location, ids["location"])
    await _person(db_session, location, "7", "Helga", HrRole.HR)
    hr = await _login(client, "helga@example.com")
    response = await client.post(f"/departments/{ids['store']}/members", headers=hr, json={"employee_ids": [ids["otto"]]})
    assert response.status_code == 200, response.text
    assert response.json()["added"] == 1


@pytest.mark.parametrize("who", ["hanna", "max"])
async def test_supervisors_and_employees_may_not_add_members(client: AsyncClient, db_session: AsyncSession, who: str) -> None:
    ids = await _company(db_session)
    if who == "max":
        location = await db_session.get(Location, ids["location"])
        await _person(db_session, location, "8", "Mia", login=True)
        who = "mia"
    headers = await _login(client, f"{who}@example.com")
    response = await client.post(f"/departments/{ids['sales']}/members", headers=headers, json={"employee_ids": [ids["olga"]]})
    assert response.status_code == 403
    db_session.expire_all()
    assert await _department_of(db_session, ids["olga"]) is None


async def test_unknown_or_foreign_people_change_nothing(client: AsyncClient, db_session: AsyncSession) -> None:
    ids = await _company(db_session)
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.commit()
    foreign_location = Location(tenant_id=2, name="Fremd", timezone="UTC")
    db_session.add(foreign_location)
    await db_session.commit()
    foreign = Employee(tenant_id=2, location_id=foreign_location.id, first_name="Fritz", last_name="Fremd", employee_number="F1")
    db_session.add(foreign)
    await db_session.commit()
    foreign_id = foreign.id
    admin = await _login(client, "admin@example.com")

    for stranger in (foreign_id, 99999):
        response = await client.post(
            f"/departments/{ids['sales']}/members", headers=admin, json={"employee_ids": [ids["olga"], stranger]}
        )
        assert response.status_code == 404
        assert response.json()["code"] == "EMPLOYEE_NOT_FOUND"
    db_session.expire_all()
    assert await _department_of(db_session, ids["olga"]) is None  # alles oder nichts
    assert await _department_of(db_session, foreign_id) is None


async def test_unknown_or_foreign_department(client: AsyncClient, db_session: AsyncSession) -> None:
    ids = await _company(db_session)
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.commit()
    foreign = Department(tenant_id=2, name="Fremd")
    db_session.add(foreign)
    await db_session.commit()
    foreign_id = foreign.id
    admin = await _login(client, "admin@example.com")
    for department_id in (foreign_id, 99999):
        response = await client.post(f"/departments/{department_id}/members", headers=admin, json={"employee_ids": [ids["olga"]]})
        assert response.status_code == 404
        assert response.json()["code"] == "DEPARTMENT_NOT_FOUND"


async def test_anonymized_people_cannot_be_added(client: AsyncClient, db_session: AsyncSession) -> None:
    ids = await _company(db_session)
    otto = await db_session.get(Employee, ids["otto"])
    otto.anonymized_at = datetime(2026, 1, 1)
    otto.active = False
    await db_session.commit()
    admin = await _login(client, "admin@example.com")
    response = await client.post(
        f"/departments/{ids['sales']}/members", headers=admin, json={"employee_ids": [ids["olga"], ids["otto"]]}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "ALREADY_ANONYMIZED"
    db_session.expire_all()
    assert await _department_of(db_session, ids["olga"]) is None


async def test_inactive_people_can_be_added(client: AsyncClient, db_session: AsyncSession) -> None:
    """Wie beim Bearbeiten eines Mitarbeiters: auch Ausgeschiedene lassen sich zuordnen (das Organigramm
    zeigt sie nicht)."""
    ids = await _company(db_session)
    otto = await db_session.get(Employee, ids["otto"])
    otto.active = False
    await db_session.commit()
    admin = await _login(client, "admin@example.com")
    response = await client.post(f"/departments/{ids['sales']}/members", headers=admin, json={"employee_ids": [ids["otto"]]})
    assert response.status_code == 200
    assert response.json()["added"] == 1
    assert response.json()["department"]["employee_count"] == 2  # zählt nur aktive


async def test_supervisor_cycle_is_rejected_and_nothing_changes(client: AsyncClient, db_session: AsyncSession) -> None:
    """Hanna leitet den Vertrieb, Tom das Lager, Hanna arbeitet im Lager (Tom ist ihre Führungskraft).
    Kommt Tom in den Vertrieb, wäre Hanna seine Führungskraft – ein Kreis."""
    ids = await _company(db_session)
    hanna = await db_session.get(Employee, ids["hanna"])
    hanna.department_id = ids["store"]
    await db_session.commit()
    admin = await _login(client, "admin@example.com")
    response = await client.post(
        f"/departments/{ids['sales']}/members", headers=admin, json={"employee_ids": [ids["olga"], ids["tom"]]}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SUPERVISOR_CYCLE"
    db_session.expire_all()
    assert await _department_of(db_session, ids["tom"]) == ids["store"]
    assert await _department_of(db_session, ids["olga"]) is None


async def test_webhook_event_for_every_moved_person(client: AsyncClient, db_session: AsyncSession) -> None:
    ids = await _company(db_session)
    admin = await _login(client, "admin@example.com")
    hook = await client.post(
        "/webhooks", headers=admin, json={"url": "https://example.com/hook", "events": ["employee.updated"]}
    )
    assert hook.status_code == 201, hook.text
    await client.post(
        f"/departments/{ids['sales']}/members", headers=admin, json={"employee_ids": [ids["max"], ids["olga"], ids["otto"]]}
    )
    deliveries = (await db_session.execute(select(WebhookDelivery))).scalars().all()
    moved = sorted(json.loads(d.payload)["data"]["employee_id"] for d in deliveries if d.event == "employee.updated")
    assert moved == sorted([ids["olga"], ids["otto"]])  # Max war schon im Vertrieb


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"employee_ids": []},
        {"employee_ids": [0]},
        {"employee_ids": [-3]},
        {"employee_ids": ["x"]},
        {"employee_ids": [5, 5]},
        {"employee_ids": list(range(1, 502))},
        {"employee_ids": None},
    ],
)
async def test_request_validation(client: AsyncClient, db_session: AsyncSession, payload: dict) -> None:
    ids = await _company(db_session)
    admin = await _login(client, "admin@example.com")
    response = await client.post(f"/departments/{ids['sales']}/members", headers=admin, json=payload)
    assert response.status_code == 422


async def test_duplicate_message_is_readable(client: AsyncClient, db_session: AsyncSession) -> None:
    ids = await _company(db_session)
    admin = await _login(client, "admin@example.com")
    response = await client.post(
        f"/departments/{ids['sales']}/members", headers=admin, json={"employee_ids": [ids["olga"], ids["olga"]]}
    )
    assert response.status_code == 422
    assert "Jede Person nur einmal" in response.text


def test_members_note_names_where_people_came_from() -> None:
    sales = Department(name="Vertrieb")
    a = Employee(first_name="Ada", last_name="A")
    b = Employee(first_name="Bo", last_name="B")
    assert _members_note(sales, [(a, None), (b, "Lager")]) == (
        "2 Mitarbeiter in Abteilung „Vertrieb“ aufgenommen: Ada A (bisher ohne Abteilung), Bo B (bisher „Lager“)"
    )


def test_members_note_is_cut_to_the_column_length() -> None:
    sales = Department(name="Vertrieb")
    many = [(Employee(first_name=f"Person{i}", last_name="Mit Langem Nachnamen"), "Lager") for i in range(40)]
    note = _members_note(sales, many)
    assert len(note) == AUDIT_DETAIL_MAX
    assert note.endswith("…")
    assert note.startswith("40 Mitarbeiter in Abteilung „Vertrieb“ aufgenommen: Person0")


def test_members_note_exactly_at_the_limit_is_not_cut() -> None:
    prefix = "1 Mitarbeiter in Abteilung „X“ aufgenommen: "
    suffix = " (bisher ohne Abteilung)"
    last = "L"
    first = "F" * (AUDIT_DETAIL_MAX - len(prefix) - len(suffix) - len(last) - 1)
    note = _members_note(Department(name="X"), [(Employee(first_name=first, last_name=last), None)])
    assert len(note) == AUDIT_DETAIL_MAX
    assert not note.endswith("…")
