"""Abteilungen (hierarchisch, mit Leitung), Führungskraft und Position am Mitarbeiter, Organigramm als
Abteilungsbaum mit Personen."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AppSettings, Employee, HrRole, Location
from app.services.auth_service import hash_password

PW = "pw123456"


async def _setup(db_session: AsyncSession) -> tuple[Location, dict[str, str]]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    db_session.add(Account(email="chefin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN))
    await db_session.commit()
    return location, {}


async def _token(client: AsyncClient, email: str, password: str = PW) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _employee(client: AsyncClient, admin, location: Location, number: str, first: str, **extra) -> dict:
    response = await client.post(
        "/employees", headers=admin,
        json={"location_id": location.id, "first_name": first, "last_name": "Test", "employee_number": number, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_departments_hierarchy(client: AsyncClient, db_session: AsyncSession) -> None:
    await _setup(db_session)
    admin = await _token(client, "chefin@example.com")
    sales = (await client.post("/departments", headers=admin, json={"name": "Vertrieb"})).json()
    inside = (await client.post("/departments", headers=admin, json={"name": "Innendienst", "parent_id": sales["id"]})).json()
    assert inside["parent_id"] == sales["id"]
    assert (await client.post("/departments", headers=admin, json={"name": "Vertrieb"})).status_code == 409
    # kein Kreis: Vertrieb kann nicht unter Innendienst hängen
    cycle = await client.patch(f"/departments/{sales['id']}", headers=admin, json={"parent_id": inside["id"]})
    assert cycle.status_code == 400 and cycle.json()["code"] == "DEPARTMENT_CYCLE"
    assert (await client.delete(f"/departments/{sales['id']}", headers=admin)).status_code == 409  # hat Unterabteilung
    moved = await client.patch(f"/departments/{inside['id']}", headers=admin, json={"clear_parent_id": True, "name": "Service"})
    assert moved.json() == {
        "id": inside["id"], "name": "Service", "parent_id": None, "leaders": [], "employee_count": 0,
    }
    assert (await client.delete(f"/departments/{sales['id']}", headers=admin)).status_code == 204
    assert [d["name"] for d in (await client.get("/departments", headers=admin)).json()] == ["Service"]


async def test_supervisor_position_and_org_chart(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _ = await _setup(db_session)
    admin = await _token(client, "chefin@example.com")
    sales = (await client.post("/departments", headers=admin, json={"name": "Vertrieb"})).json()
    boss = await _employee(client, admin, location, "1", "Bea", position="Vertriebsleitung", department_id=sales["id"])
    erika = await _employee(
        client, admin, location, "2", "Erika", supervisor_id=boss["id"], department_id=sales["id"],
        login_email="erika@example.com", password="startpasswort-1",
    )
    assert (erika["supervisor_id"], erika["department_id"]) == (boss["id"], sales["id"])
    assert (erika["effective_supervisor_ids"], erika["supervisor_source"]) == ([boss["id"]], "OVERRIDE")
    # Kreis über die Führungskraft wird abgelehnt
    cycle = await client.patch(f"/employees/{boss['id']}", headers=admin, json={"supervisor_id": erika["id"]})
    assert cycle.status_code == 400 and cycle.json()["code"] == "SUPERVISOR_CYCLE"
    # Die App verwirft nach dem Fehler ihre Session; der Test teilt sie mit der App und rollt selbst zurück.
    await db_session.rollback()
    # Sich selbst als Führungskraft: keine andere Person der Firma
    own = await client.patch(f"/employees/{boss['id']}", headers=admin, json={"supervisor_id": boss["id"]})
    assert own.status_code == 404 and own.json()["code"] == "SUPERVISOR_NOT_FOUND"

    chart = (await client.get("/org-chart", headers=admin)).json()
    assert chart["departments"] == [{"id": sales["id"], "name": "Vertrieb", "parent_id": None, "leaders": []}]
    by_name = {p["first_name"]: p for p in chart["people"]}
    assert by_name["Erika"]["supervisor_ids"] == [boss["id"]]
    assert by_name["Bea"]["supervisor_ids"] == []
    assert (by_name["Bea"]["position"], by_name["Bea"]["department"], by_name["Bea"]["department_id"]) == (
        "Vertriebsleitung", "Vertrieb", sales["id"],
    )
    assert (await client.get("/departments", headers=admin)).json()[0]["employee_count"] == 2

    # Bea leitet den Vertrieb: Führungskraft auch ohne Ausnahme
    head = await client.patch(
        f"/departments/{sales['id']}", headers=admin,
        json={"leaders": [{"employee_id": boss["id"]}, {"employee_id": erika["id"], "role": "DEPUTY", "deputy_rights": "FULL"}]},
    )
    assert [(l["employee_id"], l["name"], l["role"]) for l in head.json()["leaders"]] == [
        (boss["id"], "Bea Test", "HEAD"), (erika["id"], "Erika Test", "DEPUTY"),
    ]
    await client.patch(f"/employees/{erika['id']}", headers=admin, json={"clear_supervisor_id": True})
    chart = (await client.get("/org-chart", headers=admin)).json()
    assert chart["departments"][0]["leaders"] == [
        {"employee_id": boss["id"], "role": "HEAD", "deputy_rights": "STANDBY"},
        {"employee_id": erika["id"], "role": "DEPUTY", "deputy_rights": "FULL"},
    ]
    assert {p["first_name"]: p["supervisor_ids"] for p in chart["people"]} == {"Bea": [], "Erika": [boss["id"]]}

    # Mitarbeiter sehen das Organigramm nur mit Einstellung
    erika_headers = await _token(client, "erika@example.com", "startpasswort-1")
    assert (await client.get("/org-chart", headers=erika_headers)).status_code == 403
    settings_row = (await db_session.execute(select(AppSettings))).scalar_one()
    settings_row.org_chart_for_employees = True
    await db_session.commit()
    assert (await client.get("/org-chart", headers=erika_headers)).status_code == 200

    # Ausgeschiedene Führungskraft: Erika steht danach oben, die Abteilung ohne (aktive) Leitung
    await client.patch(f"/employees/{boss['id']}", headers=admin, json={"active": False})
    chart = (await client.get("/org-chart", headers=admin)).json()
    assert [(p["first_name"], p["supervisor_ids"]) for p in chart["people"]] == [("Erika", [])]
    assert chart["departments"][0]["leaders"] == [{"employee_id": erika["id"], "role": "DEPUTY", "deputy_rights": "FULL"}]
    listed = (await client.get("/departments", headers=admin)).json()[0]["leaders"]
    assert [(l["name"], l["active"]) for l in listed] == [("Bea Test", False), ("Erika Test", True)]  # Inaktive bleiben sichtbar
    # Führungskraft entfernen, Position leeren
    cleared = await client.patch(f"/employees/{erika['id']}", headers=admin, json={"clear_supervisor_id": True, "position": ""})
    assert (cleared.json()["supervisor_id"], cleared.json()["position"]) == (None, None)


async def test_department_heads_see_but_cannot_change_departments(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _ = await _setup(db_session)
    db_session.add(
        Employee(
            location_id=location.id, first_name="Tom", last_name="Lead", employee_number="9",
            login_email="tom@example.com", password_hash=hash_password(PW), hr_role=HrRole.SUPERVISOR,
        )
    )
    await db_session.commit()
    tom = await _token(client, "tom@example.com")
    assert (await client.get("/departments", headers=tom)).status_code == 200
    assert (await client.post("/departments", headers=tom, json={"name": "X"})).status_code == 403
    assert (await client.get("/org-chart", headers=tom)).status_code == 200
