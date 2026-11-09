"""Eigene Felder der Personalakte: Abschnitte, Feldarten mit Prüfung, Verlauf mit Gültig-ab,
Sicht für Mitarbeiter, Mitarbeitendenhistorie."""
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Employee, HrRole, Location
from app.services.auth_service import hash_password

PW = "pw123456"


async def _setup(client: AsyncClient, db_session: AsyncSession):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    db_session.add(Account(email="chefin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN))
    await db_session.commit()
    erika = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="1",
        login_email="erika@example.com", password_hash=hash_password(PW),
    )
    boss = Employee(location_id=location.id, first_name="Bea", last_name="Chef", employee_number="2")
    db_session.add_all([erika, boss])
    await db_session.commit()
    tokens = []
    for email in ("chefin@example.com", "erika@example.com"):
        r = await client.post("/auth/login", json={"email": email, "password": PW})
        tokens.append({"Authorization": f"Bearer {r.json()['access_token']}"})
    return erika, boss, tokens[0], tokens[1]


async def test_fields_values_and_history(client: AsyncClient, db_session: AsyncSession) -> None:
    erika, boss, admin, me = await _setup(client, db_session)
    section = (await client.post("/attribute-sections", headers=admin, json={"name": "Ausstattung", "employee_access": "VIEW"})).json()
    hidden = (await client.post("/attribute-sections", headers=admin, json={"name": "Intern"})).json()
    shirt = (await client.post("/attributes", headers=admin, json={"section_id": section["id"], "label": "T-Shirt", "field_type": "SELECT", "options": ["S", "M", "L"]})).json()
    salary_band = (await client.post("/attributes", headers=admin, json={"section_id": hidden["id"], "label": "Gehaltsband", "field_type": "NUMBER", "dated": True})).json()
    mentor = (await client.post("/attributes", headers=admin, json={"section_id": section["id"], "label": "Pate", "field_type": "EMPLOYEE"})).json()
    assert (await client.post("/attributes", headers=admin, json={"section_id": section["id"], "label": "X", "field_type": "SELECT"})).status_code == 422

    base = f"/employees/{erika.id}/attributes"
    assert (await client.put(f"{base}/{shirt['id']}", headers=admin, json={"value": "XL"})).status_code == 400
    await client.put(f"{base}/{shirt['id']}", headers=admin, json={"value": "M"})
    await client.put(f"{base}/{mentor['id']}", headers=admin, json={"value": str(boss.id)})
    past, future = date.today() - timedelta(days=30), date.today() + timedelta(days=30)
    await client.put(f"{base}/{salary_band['id']}", headers=admin, json={"value": "3", "valid_from": str(past)})
    values = (await client.put(f"{base}/{salary_band['id']}", headers=admin, json={"value": "4,5", "valid_from": str(future)})).json()
    by_id = {v["attribute_id"]: v for v in values}
    assert (by_id[shirt["id"]]["value"], by_id[mentor["id"]]["display"]) == ("M", "Bea Chef")
    band = by_id[salary_band["id"]]
    assert (band["value"], band["display"]) == ("3", "3")  # der künftige Wert gilt noch nicht
    assert [h["value"] for h in band["history"]] == ["4.5", "3"]

    # Mitarbeiter sieht nur freigegebene Abschnitte
    assert [s["name"] for s in (await client.get("/me/attributes", headers=me)).json()] == ["Ausstattung"]
    mine = {v["attribute_id"] for v in (await client.get("/me/attribute-values", headers=me)).json()}
    assert mine == {shirt["id"], mentor["id"]}
    assert (await client.get(base, headers=me)).status_code == 403

    history = (await client.get(f"/employees/{erika.id}/history", headers=admin)).json()
    assert any("Gehaltsband: 4,5 ab" in h["what"] for h in history)
    assert history[0]["by"] == "chefin@example.com"
