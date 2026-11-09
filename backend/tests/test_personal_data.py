"""Stammdaten: Status (Onboarding/Aktiv/Auszeit/Inaktiv), Kostenstellen mit Aufteilung, persönliche
Daten verschlüsselt – Bank/Steuer/SV nur mit „Vergütung & Lohn-Export“."""
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Absence, AbsenceApprovalStatus, AbsenceType, Account, EmployeePersonalData, HrRole, Location
from app.services.auth_service import hash_password

PW = "pw123456"
IBAN = "DE89 3704 0044 0532 0130 00"


async def _setup(client: AsyncClient, db_session: AsyncSession) -> tuple[Location, dict, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    db_session.add_all([
        Account(email="chefin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN),
        Account(email="hr@example.com", password_hash=hash_password(PW), role=HrRole.HR),
    ])
    await db_session.commit()
    tokens = []
    for email in ("chefin@example.com", "hr@example.com"):
        r = await client.post("/auth/login", json={"email": email, "password": PW})
        tokens.append({"Authorization": f"Bearer {r.json()['access_token']}"})
    return location, tokens[0], tokens[1]


async def _employee(client: AsyncClient, admin: dict, location: Location, number: str, **extra) -> dict:
    r = await client.post(
        "/employees", headers=admin,
        json={"location_id": location.id, "first_name": "Erika", "last_name": f"M{number}", "employee_number": number, **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_status(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin, _ = await _setup(client, db_session)
    today = date.today()
    future = await _employee(client, admin, location, "1", hire_date=str(today + timedelta(days=10)))
    leave = await _employee(client, admin, location, "2")
    gone = await _employee(client, admin, location, "3", termination_date=str(today - timedelta(days=1)))
    db_session.add(Absence(
        employee_id=leave["id"], type=AbsenceType.PARENTAL_LEAVE, date_from=today - timedelta(days=5),
        date_to=today + timedelta(days=100), approval_status=AbsenceApprovalStatus.APPROVED,
    ))
    await db_session.commit()
    statuses = {e["id"]: e["employment_status"] for e in (await client.get("/employees", headers=admin)).json()}
    assert statuses[future["id"]] == "ONBOARDING"
    assert statuses[leave["id"]] == "LEAVE"
    assert statuses[gone["id"]] == "INACTIVE"
    assert (await client.get(f"/employees/{leave['id']}", headers=admin)).json()["employment_status"] == "LEAVE"


async def test_cost_centers(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin, _ = await _setup(client, db_session)
    erika = await _employee(client, admin, location, "1")
    a = (await client.post("/cost-centers", headers=admin, json={"code": "100", "name": "Verwaltung"})).json()
    b = (await client.post("/cost-centers", headers=admin, json={"code": "200", "name": "Lager"})).json()
    assert (await client.post("/cost-centers", headers=admin, json={"code": "100", "name": "X"})).status_code == 409

    bad = await client.put(f"/employees/{erika['id']}/cost-centers", headers=admin, json=[{"cost_center_id": a["id"], "percent": 60}])
    assert bad.status_code == 400 and bad.json()["code"] == "COST_CENTERS_INVALID"
    ok = await client.put(
        f"/employees/{erika['id']}/cost-centers", headers=admin,
        json=[{"cost_center_id": a["id"], "percent": 60}, {"cost_center_id": b["id"], "percent": 40}],
    )
    assert ok.status_code == 200
    assert (await client.get(f"/employees/{erika['id']}", headers=admin)).json()["cost_centers"] == ok.json()
    # benutzte Kostenstelle: nicht löschen, archivieren
    assert (await client.delete(f"/cost-centers/{a['id']}", headers=admin)).status_code == 409
    await client.patch(f"/cost-centers/{a['id']}", headers=admin, json={"archived": True})
    assert [c["code"] for c in (await client.get("/cost-centers", headers=admin)).json()] == ["200"]


async def test_personal_data_encrypted_and_payroll_fields_need_permission(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin, hr = await _setup(client, db_session)
    erika = await _employee(client, admin, location, "1", login_email="erika@example.com", password="startpasswort-1")

    saved = await client.patch(
        f"/employees/{erika['id']}/personal-data", headers=admin,
        json={"street": "Hauptstr. 1", "zip_code": "36251", "city": "Bad Hersfeld", "iban": IBAN, "tax_class": 1, "children_count": 2},
    )
    assert saved.status_code == 200
    assert (saved.json()["iban"], saved.json()["city"]) == ("DE89370400440532013000", "Bad Hersfeld")
    raw = (await db_session.execute(select(EmployeePersonalData.data))).scalar_one()
    assert "Hersfeld" not in raw and "DE89" not in raw  # verschlüsselt gespeichert

    # HR ohne „Vergütung & Lohn-Export“: sieht Adresse, aber keine Bankdaten und darf sie nicht ändern
    seen = (await client.get(f"/employees/{erika['id']}/personal-data", headers=hr)).json()
    assert (seen["city"], seen["iban"], seen["payroll_visible"]) == ("Bad Hersfeld", None, False)
    denied = await client.patch(f"/employees/{erika['id']}/personal-data", headers=hr, json={"iban": IBAN})
    assert denied.status_code == 403
    assert (await client.patch(f"/employees/{erika['id']}/personal-data", headers=hr, json={"phone": "06621 123"})).status_code == 200
    # Teilupdate: Bankdaten bleiben erhalten
    assert (await client.get(f"/employees/{erika['id']}/personal-data", headers=admin)).json()["iban"] == "DE89370400440532013000"

    invalid = await client.patch(f"/employees/{erika['id']}/personal-data", headers=admin, json={"iban": "DE00 1234"})
    assert invalid.status_code == 422

    # Die Person selbst sieht alles; Datenexport enthält es
    me = await client.post("/auth/login", json={"email": "erika@example.com", "password": "startpasswort-1"})
    own = (await client.get("/me/personal-data", headers={"Authorization": f"Bearer {me.json()['access_token']}"})).json()
    assert (own["iban"], own["phone"]) == ("DE89370400440532013000", "06621 123")
    export = (await client.get(f"/employees/{erika['id']}/data-export", headers=admin)).json()
    assert export["personal_data"]["children_count"] == 2
