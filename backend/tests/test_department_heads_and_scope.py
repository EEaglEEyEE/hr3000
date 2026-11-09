"""Abteilungsleitung statt Teams: Leitungen und Stellvertretungen anlegen, ändern und entfernen, keine
Kreise in den Führungskräften, wirksame Führungskräfte in der Mitarbeiterliste, Bereich einer
Führungskraft (app/services/scope_service.py) und Genehmigung über die Leitung
(app/services/approval_service.py)."""
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from absence_helpers import require_vacation_approval
from app.models import (
    Absence, AbsenceApprovalStatus, AbsenceType, Account, Employee, HrRole, Location, Tenant, TenantPlan,
)
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings
from org_helpers import department, supervisor_with_department

PW = "pw"
FUTURE = date.today() + timedelta(days=60)


async def _login(client: AsyncClient, email: str, password: str = PW) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _setup(client: AsyncClient, db_session: AsyncSession) -> tuple[Location, dict[str, str]]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add_all([location, Account(email="admin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN)])
    await db_session.commit()
    return location, await _login(client, "admin@example.com")


async def _employee(
    db_session: AsyncSession, location: Location, number: str, first: str, *, login: bool = False, **extra
) -> Employee:
    """Mitarbeiter (Nachname „Test“); mit login=True auch mit Zugang <vorname>@example.com."""
    person = Employee(location_id=location.id, first_name=first, last_name="Test", employee_number=number, **extra)
    if login:
        person.login_email = f"{first.lower()}@example.com"
        person.password_hash = hash_password(PW)
    db_session.add(person)
    await db_session.commit()
    return person


async def _ids(client: AsyncClient, headers: dict[str, str]) -> set[int]:
    response = await client.get("/employees", headers=headers)
    assert response.status_code == 200, response.text
    return {e["id"] for e in response.json()}


def _heads(*ids: int) -> dict:
    return {"leaders": [{"employee_id": i} for i in ids]}


def _leaders(body: dict) -> list[tuple]:
    return [(l["employee_id"], l["name"], l["role"], l["deputy_rights"]) for l in body["leaders"]]


def _vacation(employee_id: int, day: date = FUTURE) -> dict:
    return {"employee_id": employee_id, "type": "VACATION", "date_from": str(day), "date_to": str(day)}


# --- Leitung pflegen -------------------------------------------------------------------------


async def test_department_leaders_set_changed_and_cleared(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    bea = await _employee(db_session, location, "1", "Bea")
    carl = await _employee(db_session, location, "2", "Carl")
    dora = await _employee(db_session, location, "3", "Dora")

    created = await client.post("/departments", headers=admin, json={"name": "Vertrieb", **_heads(bea.id)})
    assert created.status_code == 201, created.text
    sales = created.json()
    assert _leaders(sales) == [(bea.id, "Bea Test", "HEAD", "STANDBY")]
    listed = (await client.get("/departments", headers=admin)).json()
    assert [(d["name"], _leaders(d)) for d in listed] == [("Vertrieb", [(bea.id, "Bea Test", "HEAD", "STANDBY")])]

    # Zwei Leitungen und eine Stellvertretung mit vollen Rechten (Reihenfolge bleibt)
    team = [
        {"employee_id": carl.id, "role": "HEAD"},
        {"employee_id": dora.id, "role": "HEAD", "deputy_rights": "ABSENCE"},  # bei Leitungen ohne Bedeutung
        {"employee_id": bea.id, "role": "DEPUTY", "deputy_rights": "FULL"},
    ]
    changed = await client.patch(f"/departments/{sales['id']}", headers=admin, json={"leaders": team})
    assert changed.status_code == 200, changed.text
    assert _leaders(changed.json()) == [
        (carl.id, "Carl Test", "HEAD", "STANDBY"),
        (dora.id, "Dora Test", "HEAD", "STANDBY"),
        (bea.id, "Bea Test", "DEPUTY", "FULL"),
    ]
    assert all(l["active"] for l in changed.json()["leaders"])
    # Umbenennen ohne Angabe zu den Leitungen lässt sie stehen
    renamed = await client.patch(f"/departments/{sales['id']}", headers=admin, json={"name": "Vertrieb Süd"})
    assert (renamed.json()["name"], len(renamed.json()["leaders"])) == ("Vertrieb Süd", 3)
    cleared = await client.patch(f"/departments/{sales['id']}", headers=admin, json={"leaders": []})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["leaders"] == []
    # Abteilung ohne Leitung
    store = (await client.post("/departments", headers=admin, json={"name": "Lager"})).json()
    assert store["leaders"] == []
    # Ungültige Eingaben werden schon bei der Eingabe abgelehnt
    for bad in (
        [{"employee_id": 0}],
        [{"employee_id": bea.id}, {"employee_id": bea.id, "role": "DEPUTY"}],  # doppelt
        [{"employee_id": bea.id, "role": "CHEF"}],
        [{"employee_id": bea.id, "role": "DEPUTY", "deputy_rights": "ALLES"}],
        [{"employee_id": i} for i in range(1, 52)],  # mehr als 50
    ):
        r = await client.post("/departments", headers=admin, json={"name": "X", "leaders": bad})
        assert r.status_code == 422, bad

    entries = (await client.get("/audit-log", headers=admin)).json()
    details = sorted(
        e["detail"]
        for e in entries
        if (e["action"], e["entity_type"], e["entity_id"]) == ("DEPARTMENT_CHANGED", "department", sales["id"])
    )
    assert details == sorted(
        [
            "Abteilung „Vertrieb“ angelegt, Leitung Bea Test",
            "Abteilung „Vertrieb“ geändert, Leitung Carl Test, Dora Test; Stellvertretung Bea Test (gleiche Rechte)",
            "Abteilung „Vertrieb Süd“ geändert",
            "Abteilung „Vertrieb Süd“ geändert, ohne Leitung",
        ]
    )


async def test_department_head_must_be_an_employee_of_the_company(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.commit()
    foreign_location = Location(tenant_id=2, name="Fremd", timezone="UTC")
    db_session.add(foreign_location)
    await db_session.commit()
    foreign = Employee(tenant_id=2, location_id=foreign_location.id, first_name="Fritz", last_name="Fremd", employee_number="F1")
    db_session.add(foreign)
    await db_session.commit()
    own = await _employee(db_session, location, "1", "Bea")
    own_id, foreign_id = own.id, foreign.id  # die App rollt bei Fehlern dieselbe Session zurück

    for head_id in (foreign_id, 99999):
        r = await client.post("/departments", headers=admin, json={"name": "Vertrieb", **_heads(own_id, head_id)})
        assert r.status_code == 404 and r.json()["code"] == "EMPLOYEE_NOT_FOUND", r.text
    assert (await client.get("/departments", headers=admin)).json() == []  # nichts angelegt

    sales = (await client.post("/departments", headers=admin, json={"name": "Vertrieb", **_heads(own_id)})).json()
    r = await client.patch(
        f"/departments/{sales['id']}", headers=admin,
        json={"leaders": [{"employee_id": foreign_id, "role": "DEPUTY"}]},
    )
    assert r.status_code == 404 and r.json()["code"] == "EMPLOYEE_NOT_FOUND"
    await db_session.rollback()
    assert [l["employee_id"] for l in (await client.get("/departments", headers=admin)).json()[0]["leaders"]] == [own_id]


async def test_supervisor_cannot_change_department_heads(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    sales, head, _ = await supervisor_with_department(db_session, location, department_name="Vertrieb")
    lead = await _login(client, "lead@example.com")

    r = await client.patch(f"/departments/{sales.id}", headers=lead, json={"leaders": []})
    assert r.status_code == 403 and r.json()["code"] == "HR_PERMISSION_REQUIRED"
    r = await client.post("/departments", headers=lead, json={"name": "Neu", **_heads(head.id)})
    assert r.status_code == 403
    assert [[l["employee_id"] for l in d["leaders"]] for d in (await client.get("/departments", headers=admin)).json()] == [[head.id]]


# --- Keine Kreise -----------------------------------------------------------------------------


async def test_override_that_closes_a_cycle_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    xaver = await _employee(db_session, location, "3", "Xaver")
    sales, paula, paula_account = await supervisor_with_department(
        db_session, location, email="paula@example.com", department_name="Vertrieb", first_name="Paula", employee_number="1"
    )
    _, sven, sven_account = await supervisor_with_department(
        db_session, location, email="sven@example.com", department_name="Innendienst", first_name="Sven",
        employee_number="2", members=(xaver,), parent=sales,
    )
    xaver_id, sven_id, paula_id = xaver.id, sven.id, paula.id
    # Kette über die Abteilungsleitungen: Xaver -> Sven -> Paula

    direct = await client.patch(f"/employees/{sven_id}", headers=admin, json={"supervisor_id": xaver_id})
    assert direct.status_code == 400 and direct.json()["code"] == "SUPERVISOR_CYCLE", direct.text
    assert "die eigene Führungskraft" in direct.json()["detail"]
    indirect = await client.patch(f"/employees/{paula_id}", headers=admin, json={"supervisor_id": xaver_id})
    assert indirect.status_code == 400 and indirect.json()["code"] == "SUPERVISOR_CYCLE", indirect.text
    # Die App verwirft nach dem Fehler ihre Session (eine je Anfrage); der Test teilt sie mit der App und
    # rollt deshalb selbst zurück – sonst stünde die abgelehnte Ausnahme noch im Speicher.
    await db_session.rollback()

    # Nichts gespeichert
    for person_id, effective in ((sven_id, [paula_id]), (paula_id, [])):
        body = (await client.get(f"/employees/{person_id}", headers=admin)).json()
        assert (body["supervisor_id"], body["effective_supervisor_ids"]) == (None, effective)
    # Sich selbst als Führungskraft gibt es nicht
    own = await client.patch(f"/employees/{paula_id}", headers=admin, json={"supervisor_id": paula_id})
    assert own.status_code == 404 and own.json()["code"] == "SUPERVISOR_NOT_FOUND"
    # Ohne Kreis geht die Ausnahme: Xaver direkt an Paula
    ok = await client.patch(f"/employees/{xaver_id}", headers=admin, json={"supervisor_id": paula_id})
    assert ok.status_code == 200, ok.text
    assert (ok.json()["supervisor_id"], ok.json()["effective_supervisor_ids"], ok.json()["supervisor_source"]) == (
        paula_id, [paula_id], "OVERRIDE",
    )


async def test_department_head_or_parent_that_closes_a_cycle_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    anna = await _employee(db_session, location, "1", "Anna")
    ben = await _employee(db_session, location, "2", "Ben")
    carl = await _employee(db_session, location, "3", "Carl")
    # Anna leitet den Einkauf, Ben arbeitet dort (Ben -> Anna). Anna selbst steht im Lager (ohne Leitung),
    # Ben leitet die Logistik (ohne Mitarbeiter).
    await department(db_session, "Einkauf", ben, head=anna)
    store = await department(db_session, "Lager", anna)
    logistics = await department(db_session, "Logistik", head=ben)
    anna_id, ben_id, carl_id, store_id, logistics_id = anna.id, ben.id, carl.id, store.id, logistics.id

    # Ben als Leitung des Lagers wäre Annas Führungskraft: Anna -> Ben -> Anna
    as_head = await client.patch(f"/departments/{store_id}", headers=admin, json=_heads(ben_id))
    assert as_head.status_code == 400 and as_head.json()["code"] == "SUPERVISOR_CYCLE", as_head.text
    # Lager unter die Logistik: Annas Führungskraft wäre die Leitung darüber, also Ben
    as_parent = await client.patch(f"/departments/{store_id}", headers=admin, json={"parent_id": logistics_id})
    assert as_parent.status_code == 400 and as_parent.json()["code"] == "SUPERVISOR_CYCLE", as_parent.text

    await db_session.rollback()
    rows = {
        d["name"]: (d["parent_id"], [l["employee_id"] for l in d["leaders"]])
        for d in (await client.get("/departments", headers=admin)).json()
    }
    assert rows == {"Einkauf": (None, [anna_id]), "Lager": (None, []), "Logistik": (None, [ben_id])}
    assert (await client.get(f"/employees/{anna_id}", headers=admin)).json()["effective_supervisor_ids"] == []
    assert (await client.get(f"/employees/{ben_id}", headers=admin)).json()["effective_supervisor_ids"] == [anna_id]
    # Als Stellvertretung ist Ben keine Führungskraft: kein Kreis
    deputy = await client.patch(f"/departments/{store_id}", headers=admin, json={"leaders": [{"employee_id": ben_id, "role": "DEPUTY"}]})
    assert deputy.status_code == 200, deputy.text

    # Ohne Kreis klappt beides
    ok = await client.patch(f"/departments/{store_id}", headers=admin, json=_heads(carl_id))
    assert ok.status_code == 200 and [l["employee_id"] for l in ok.json()["leaders"]] == [carl_id]
    anna_body = (await client.get(f"/employees/{anna_id}", headers=admin)).json()
    assert (anna_body["effective_supervisor_ids"], anna_body["supervisor_source"]) == ([carl_id], "DEPARTMENT")


# Bekannte Lücken in der App (siehe Bericht): Diese Änderungen erzeugen einen Kreis, ohne dass
# SUPERVISOR_CYCLE kommt. Ein bestehender Kreis blockiert danach jede weitere Änderung an Abteilung oder
# Führungskraft in der Firma. strict=True: Sobald die App das abfängt, schlägt der Test an und die
# Markierung muss weg.


async def test_clearing_an_override_that_closes_a_cycle_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    hugo = await _employee(db_session, location, "1", "Hugo")
    zora = await _employee(db_session, location, "2", "Zora")
    yves = await _employee(db_session, location, "3", "Yves")
    await department(db_session, "Vertrieb", hugo, yves, head=hugo)
    yves.supervisor_id = zora.id  # Yves -> Zora (Ausnahme)
    await db_session.commit()
    hugo_id, yves_id = hugo.id, yves.id
    assert (await client.patch(f"/employees/{hugo_id}", headers=admin, json={"supervisor_id": yves_id})).status_code == 200

    # Ohne Ausnahme wäre Hugo (Leitung) wieder Yves' Führungskraft: Hugo -> Yves -> Hugo
    r = await client.patch(f"/employees/{yves_id}", headers=admin, json={"clear_supervisor_id": True})
    assert r.status_code == 400 and r.json()["code"] == "SUPERVISOR_CYCLE"


async def test_clearing_a_department_head_that_closes_a_cycle_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    pia = await _employee(db_session, location, "1", "Pia")
    zora = await _employee(db_session, location, "2", "Zora")
    sven = await _employee(db_session, location, "3", "Sven", supervisor_id=zora.id)  # Sven -> Zora (Ausnahme)
    xaver = await _employee(db_session, location, "4", "Xaver")
    sales = await department(db_session, "Vertrieb", pia, head=pia)
    inside = await department(db_session, "Innendienst", sven, xaver, head=sven, parent=sales)
    pia_id, xaver_id, inside_id = pia.id, xaver.id, inside.id
    # Xaver -> Sven -> Zora; Pia -> Xaver (Ausnahme) ist noch kein Kreis
    assert (await client.patch(f"/employees/{pia_id}", headers=admin, json={"supervisor_id": xaver_id})).status_code == 200

    # Ohne Leitung im Innendienst wäre Pia (Leitung darüber) Xavers Führungskraft: Pia -> Xaver -> Pia
    r = await client.patch(f"/departments/{inside_id}", headers=admin, json={"leaders": []})
    assert r.status_code == 400 and r.json()["code"] == "SUPERVISOR_CYCLE"


async def test_reactivating_a_head_that_closes_a_cycle_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    anna = await _employee(db_session, location, "1", "Anna")
    ben = await _employee(db_session, location, "2", "Ben")
    purchasing = await department(db_session, "Einkauf", head=anna)
    await department(db_session, "Lager", anna, head=ben)  # Anna -> Ben
    anna_id, ben_id, purchasing_id = anna.id, ben.id, purchasing.id
    assert (await client.patch(f"/employees/{anna_id}", headers=admin, json={"active": False})).status_code == 200
    # Solange Anna ausgeschieden ist, hat Ben im Einkauf keine Führungskraft – kein Kreis
    moved = await client.patch(f"/employees/{ben_id}", headers=admin, json={"department_id": purchasing_id})
    assert moved.status_code == 200, moved.text

    # Anna wieder aktiv: Anna -> Ben (Lager) und Ben -> Anna (Einkauf)
    r = await client.patch(f"/employees/{anna_id}", headers=admin, json={"active": True})
    assert r.status_code == 400 and r.json()["code"] == "SUPERVISOR_CYCLE"


# --- Wirksame Führungskraft -------------------------------------------------------------------


async def test_employees_show_effective_supervisor_and_source(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    hans = await _employee(db_session, location, "1", "Hans")  # leitet den Vertrieb
    mia = await _employee(db_session, location, "2", "Mia")  # Vertrieb
    xenia = await _employee(db_session, location, "3", "Xenia")  # ohne Abteilung
    otto = await _employee(db_session, location, "4", "Otto", supervisor_id=xenia.id)  # Vertrieb, Ausnahme Xenia
    ex = await _employee(db_session, location, "5", "Ex", active=False)
    rita = await _employee(db_session, location, "6", "Rita", supervisor_id=ex.id)  # Ausnahme ausgeschieden
    nina = await _employee(db_session, location, "7", "Nina")  # Innendienst (ohne Leitung) unter Vertrieb
    sven = await _employee(db_session, location, "8", "Sven")  # leitet den Service unter Vertrieb
    sales = await department(db_session, "Vertrieb", hans, mia, otto, rita, head=hans)
    await department(db_session, "Innendienst", nina, parent=sales)
    await department(db_session, "Service", sven, head=sven, parent=sales)

    # (Ausnahme, wirksame Führungskräfte, Quelle)
    expected = {
        hans.id: (None, [], None),  # selbst Leitung, darüber keine
        mia.id: (None, [hans.id], "DEPARTMENT"),
        otto.id: (xenia.id, [xenia.id], "OVERRIDE"),
        rita.id: (ex.id, [hans.id], "DEPARTMENT"),  # ausgeschiedene Ausnahme zählt nicht
        nina.id: (None, [hans.id], "DEPARTMENT"),  # Abteilung ohne Leitung -> Leitung darüber
        sven.id: (None, [hans.id], "DEPARTMENT"),  # Leitung des Service -> Leitung darüber
        xenia.id: (None, [], None),
        ex.id: (None, [], None),
    }
    listed = (await client.get("/employees", headers=admin)).json()
    assert all("team_id" not in e for e in listed)
    assert {e["id"]: (e["supervisor_id"], e["effective_supervisor_ids"], e["supervisor_source"]) for e in listed} == expected
    for employee_id, values in expected.items():
        body = (await client.get(f"/employees/{employee_id}", headers=admin)).json()
        assert (body["supervisor_id"], body["effective_supervisor_ids"], body["supervisor_source"]) == values

    # Ausnahme aufheben: wieder die Abteilungsleitung
    cleared = (await client.patch(f"/employees/{otto.id}", headers=admin, json={"clear_supervisor_id": True})).json()
    assert (cleared["supervisor_id"], cleared["effective_supervisor_ids"], cleared["supervisor_source"]) == (None, [hans.id], "DEPARTMENT")
    # Neu angelegte Mitarbeiter bekommen die Leitung ihrer Abteilung (Tarif ohne Mitarbeitergrenze)
    tenant = await db_session.get(Tenant, 1)
    tenant.plan = TenantPlan.UNLIMITED
    await db_session.commit()
    created = await client.post(
        "/employees", headers=admin,
        json={"location_id": location.id, "first_name": "Neu", "last_name": "Test", "employee_number": "9", "department_id": sales.id},
    )
    assert created.status_code == 201, created.text
    assert (created.json()["effective_supervisor_ids"], created.json()["supervisor_source"]) == ([hans.id], "DEPARTMENT")


# --- Bereich einer Führungskraft --------------------------------------------------------------


async def test_head_sees_department_sub_departments_and_override_reports(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    mara = await _employee(db_session, location, "1", "Mara")  # Vertrieb
    ida = await _employee(db_session, location, "2", "Ida")  # Innendienst (Leitung Sven)
    rudi = await _employee(db_session, location, "3", "Rudi")  # Region Süd (ohne Leitung) unter Innendienst
    alex = await _employee(db_session, location, "4", "Alex")  # Außendienst (ohne Leitung) unter Vertrieb
    otto = await _employee(db_session, location, "5", "Otto")  # Lager, Ausnahme: Pia
    fritz = await _employee(db_session, location, "6", "Fritz")  # Lager, fremd
    sales, pia, pia_account = await supervisor_with_department(
        db_session, location, email="pia@example.com", department_name="Vertrieb", members=(mara,),
        first_name="Pia", employee_number="P1",
    )
    inside, sven, sven_account = await supervisor_with_department(
        db_session, location, email="sven@example.com", department_name="Innendienst", members=(ida,),
        first_name="Sven", employee_number="S1", parent=sales,
    )
    await department(db_session, "Region Süd", rudi, parent=inside)
    await department(db_session, "Außendienst", alex, parent=sales)
    await department(db_session, "Lager", otto, fritz)
    otto.supervisor_id = pia.id
    await db_session.commit()

    pia_scope = {pia.id, mara.id, sven.id, ida.id, rudi.id, alex.id, otto.id}
    sven_scope = {sven.id, ida.id, rudi.id}
    pia_headers = await _login(client, "pia@example.com")
    sven_headers = await _login(client, "sven@example.com")

    assert await _ids(client, pia_headers) == pia_scope
    assert await _ids(client, sven_headers) == sven_scope
    for headers, scope in ((pia_headers, pia_scope), (sven_headers, sven_scope)):
        for person in (pia, mara, sven, ida, rudi, alex, otto, fritz):
            r = await client.get(f"/employees/{person.id}", headers=headers)
            if person.id in scope:
                assert r.status_code == 200, (person.first_name, r.text)
            else:
                assert r.status_code == 404 and r.json()["code"] == "EMPLOYEE_NOT_FOUND", person.first_name
    # Teamkalender: derselbe Bereich
    calendar = (await client.get("/team-calendar", headers=pia_headers, params={"from": "2026-08-01", "to": "2026-08-02"})).json()
    assert {e["employee_id"] for e in calendar} == pia_scope
    # Admin sieht alle
    assert await _ids(client, admin) == pia_scope | {fritz.id}


async def test_supervisor_account_without_employee_sees_nobody(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    erika = await _employee(db_session, location, "1", "Erika")
    lead_setup = await supervisor_with_department(db_session, location, department_name="Vertrieb", members=(erika,))
    db_session.add(Account(email="ohne@example.com", password_hash=hash_password(PW), role=HrRole.SUPERVISOR))
    absence = Absence(
        employee_id=erika.id, type=AbsenceType.VACATION, date_from=FUTURE, date_to=FUTURE,
        approval_status=AbsenceApprovalStatus.PENDING,
    )
    db_session.add(absence)
    await db_session.commit()
    headers = await _login(client, "ohne@example.com")

    assert (await client.get("/employees", headers=headers)).json() == []
    r = await client.get(f"/employees/{erika.id}", headers=headers)
    assert r.status_code == 404 and r.json()["code"] == "EMPLOYEE_NOT_FOUND"
    assert (await client.get("/team-calendar", headers=headers, params={"from": "2026-08-01", "to": "2026-08-02"})).json() == []
    assert (await client.get("/absences/pending", headers=headers)).json() == []
    assert (await client.patch(f"/absences/{absence.id}/decide", headers=headers, json={"approve": True})).status_code == 403
    # Die Leitung der Abteilung sieht Erika
    assert erika.id in await _ids(client, await _login(client, "lead@example.com"))


# --- Genehmigung über die Leitung -------------------------------------------------------------


async def test_department_head_approves_absence_of_report(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _ = await _setup(client, db_session)
    erika = await _employee(db_session, location, "1", "Erika", login=True)
    _, lead, lead_account = await supervisor_with_department(db_session, location, department_name="Vertrieb", members=(erika,))
    _, olaf, olaf_account = await supervisor_with_department(
        db_session, location, email="olaf@example.com", department_name="Lager", first_name="Olaf", employee_number="O1"
    )
    await require_vacation_approval(db_session)

    created = await client.post("/absences", headers=await _login(client, "erika@example.com"), json=_vacation(erika.id))
    assert created.status_code == 201, created.text
    absence = created.json()
    assert (absence["approval_status"], absence["waiting_for"]) == ("PENDING", "Führungskraft")

    lead_headers = await _login(client, "lead@example.com")
    other = await _login(client, "olaf@example.com")
    assert [a["id"] for a in (await client.get("/absences/pending", headers=lead_headers)).json()] == [absence["id"]]
    assert (await client.get("/absences/pending", headers=other)).json() == []
    assert (await client.patch(f"/absences/{absence['id']}/decide", headers=other, json={"approve": True})).status_code == 403
    decided = await client.patch(f"/absences/{absence['id']}/decide", headers=lead_headers, json={"approve": True})
    assert decided.status_code == 200, decided.text
    assert (decided.json()["approval_status"], decided.json()["decided_by_account_id"]) == ("APPROVED", lead_account.id)


async def test_head_cannot_approve_own_absence_but_their_head_can(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _ = await _setup(client, db_session)
    sales, pia, pia_account = await supervisor_with_department(
        db_session, location, email="pia@example.com", department_name="Vertrieb", first_name="Pia", employee_number="P1"
    )
    _, sven, sven_account = await supervisor_with_department(
        db_session, location, email="sven@example.com", department_name="Innendienst", first_name="Sven",
        employee_number="S1", parent=sales,
    )
    await require_vacation_approval(db_session)
    # Mit Vier-Augen-Prinzip geht auch der eigene Antrag einer Führungskraft in die Genehmigung
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    settings_row.absence_four_eyes = True
    await db_session.commit()

    sven_headers = await _login(client, "sven@example.com")
    created = await client.post("/absences", headers=sven_headers, json=_vacation(sven.id))
    assert created.status_code == 201 and created.json()["approval_status"] == "PENDING", created.text
    absence_id = created.json()["id"]

    own = await client.patch(f"/absences/{absence_id}/decide", headers=sven_headers, json={"approve": True})
    assert own.status_code == 403 and own.json()["code"] == "FORBIDDEN"
    assert (await client.get("/absences/pending", headers=sven_headers)).json() == []

    pia_headers = await _login(client, "pia@example.com")
    assert [a["id"] for a in (await client.get("/absences/pending", headers=pia_headers)).json()] == [absence_id]
    decided = await client.patch(f"/absences/{absence_id}/decide", headers=pia_headers, json={"approve": True})
    assert decided.status_code == 200, decided.text
    assert (decided.json()["approval_status"], decided.json()["decided_by_account_id"]) == ("APPROVED", pia_account.id)


async def test_supervisor_chain_goes_to_the_effective_supervisor_only(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    ida = await _employee(db_session, location, "1", "Ida", login=True)
    sales, pia, pia_account = await supervisor_with_department(
        db_session, location, email="pia@example.com", department_name="Vertrieb", first_name="Pia",
        last_name="Plan", employee_number="P1",
    )
    _, sven, sven_account = await supervisor_with_department(
        db_session, location, email="sven@example.com", department_name="Innendienst", first_name="Sven",
        last_name="Senf", employee_number="S1", members=(ida,), parent=sales,
    )
    vacation = next(t for t in (await client.get("/absence-types", headers=admin)).json() if t["category"] == "VACATION")
    r = await client.patch(f"/absence-types/{vacation['id']}", headers=admin, json={"approval_chain": "SUPERVISOR", "requires_approval": True})
    assert r.status_code == 200, r.text
    ida_headers = await _login(client, "ida@example.com")
    pia_headers = await _login(client, "pia@example.com")
    sven_headers = await _login(client, "sven@example.com")

    # Ohne Ausnahme: die Leitung des Innendienstes, nicht die Leitung darüber
    first = (await client.post("/absences", headers=ida_headers, json=_vacation(ida.id))).json()
    assert first["waiting_for"] == "Führungskraft Sven Senf"
    assert (await client.get("/absences/pending", headers=pia_headers)).json() == []
    assert (await client.patch(f"/absences/{first['id']}/decide", headers=pia_headers, json={"approve": True})).status_code == 403
    approved = await client.patch(f"/absences/{first['id']}/decide", headers=sven_headers, json={"approve": True})
    assert approved.status_code == 200 and approved.json()["approval_status"] == "APPROVED"

    # Mit Ausnahme: genau die eingetragene Führungskraft
    assert (await client.patch(f"/employees/{ida.id}", headers=admin, json={"supervisor_id": pia.id})).status_code == 200
    second = (await client.post("/absences", headers=ida_headers, json=_vacation(ida.id, FUTURE + timedelta(days=7)))).json()
    assert second["waiting_for"] == "Führungskraft Pia Plan"
    assert (await client.patch(f"/absences/{second['id']}/decide", headers=sven_headers, json={"approve": True})).status_code == 403
    approved = await client.patch(f"/absences/{second['id']}/decide", headers=pia_headers, json={"approve": True})
    assert approved.status_code == 200 and approved.json()["approval_status"] == "APPROVED"


# Bekannter Fehler in der App (siehe Bericht): In Produktion hat jede Anfrage eine frische Session. Ist die
# Person selbst angemeldet, lädt die App ihren Mitarbeiter über Account.employee; Employee.account wird
# dabei nicht mitgeladen (selectin-Kreis Account <-> Employee) und später im async-Kontext nachgeladen
# -> MissingGreenlet (500). Die übrigen Tests teilen sich eine „warme“ Session mit der App und sehen das
# nicht; expunge_all() stellt den Zustand am Anfang einer echten Anfrage her.


async def test_effective_supervisor_decides_with_fresh_session(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(client, db_session)
    ida = await _employee(db_session, location, "1", "Ida", login=True)
    _, sven, sven_account = await supervisor_with_department(
        db_session, location, email="sven@example.com", department_name="Innendienst", first_name="Sven", members=(ida,)
    )
    vacation = next(t for t in (await client.get("/absence-types", headers=admin)).json() if t["category"] == "VACATION")
    r = await client.patch(f"/absence-types/{vacation['id']}", headers=admin, json={"approval_chain": "SUPERVISOR", "requires_approval": True})
    assert r.status_code == 200, r.text
    absence = (await client.post("/absences", headers=await _login(client, "ida@example.com"), json=_vacation(ida.id))).json()
    sven_headers = await _login(client, "sven@example.com")

    db_session.expunge_all()
    pending = await client.get("/absences/pending", headers=sven_headers)
    assert [a["id"] for a in pending.json()] == [absence["id"]]
    db_session.expunge_all()
    decided = await client.patch(f"/absences/{absence['id']}/decide", headers=sven_headers, json={"approve": True})
    assert decided.status_code == 200 and decided.json()["approval_status"] == "APPROVED"


async def test_head_reads_own_record_with_fresh_session(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _ = await _setup(client, db_session)
    _, head, head_account = await supervisor_with_department(db_session, location)
    head_id = head.id
    headers = await _login(client, "lead@example.com")

    db_session.expunge_all()
    r = await client.get(f"/employees/{head_id}", headers=headers)
    assert r.status_code == 200 and r.json()["hr_role"] == "SUPERVISOR"
