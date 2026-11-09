"""Mitarbeiter schlagen Änderungen eigener Daten vor; HR übernimmt oder lehnt ab. Bank/Steuer/SV
nur mit „Vergütung & Lohn-Export“, nur Felder aus Abschnitten mit „EDIT“."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Employee, HrRole, Location, Notification, NotificationType
from app.services.auth_service import hash_password

PW = "pw123456"


async def _setup(client: AsyncClient, db_session: AsyncSession):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    db_session.add_all([
        Account(email="chefin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN),
        Account(email="hr@example.com", password_hash=hash_password(PW), role=HrRole.HR),
    ])
    await db_session.commit()
    erika = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="1",
        login_email="erika@example.com", password_hash=hash_password(PW),
    )
    db_session.add(erika)
    await db_session.commit()
    tokens = {}
    for name in ("chefin", "hr", "erika"):
        r = await client.post("/auth/login", json={"email": f"{name}@example.com", "password": PW})
        tokens[name] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return erika, tokens


async def test_propose_and_approve(client: AsyncClient, db_session: AsyncSession) -> None:
    erika, t = await _setup(client, db_session)
    editable = (await client.post("/attribute-sections", headers=t["chefin"], json={"name": "Kontakt", "employee_access": "EDIT"})).json()
    readonly = (await client.post("/attribute-sections", headers=t["chefin"], json={"name": "Intern", "employee_access": "VIEW"})).json()
    shirt = (await client.post("/attributes", headers=t["chefin"], json={"section_id": editable["id"], "label": "T-Shirt", "field_type": "SELECT", "options": ["S", "M"]})).json()
    band = (await client.post("/attributes", headers=t["chefin"], json={"section_id": readonly["id"], "label": "Band", "field_type": "TEXT"})).json()

    denied = await client.post("/me/change-requests", headers=t["erika"], json={"attributes": {str(band["id"]): "A"}})
    assert denied.status_code == 400
    proposal = await client.post(
        "/me/change-requests", headers=t["erika"],
        json={"personal": {"city": "Kassel", "iban": "DE89 3704 0044 0532 0130 00"}, "attributes": {str(shirt["id"]): "M"}, "note": "Umgezogen"},
    )
    assert proposal.status_code == 201
    request_id = proposal.json()["id"]
    assert proposal.json()["contains_payroll"] is True
    notes = (await db_session.execute(select(Notification).where(Notification.type == NotificationType.DATA_CHANGE_REQUESTED))).scalars().all()
    assert len(notes) == 2  # Admin und HR

    # HR ohne Lohn-Freigabe sieht die IBAN nicht und darf nicht entscheiden
    listed = (await client.get("/change-requests", headers=t["hr"])).json()
    iban = next(i for i in listed[0]["items"] if i["field"] == "iban")
    assert iban["new"] == "•••"
    assert (await client.post(f"/change-requests/{request_id}/decide", headers=t["hr"], json={"approve": True})).status_code == 403

    decided = await client.post(f"/change-requests/{request_id}/decide", headers=t["chefin"], json={"approve": True})
    assert decided.json()["status"] == "APPROVED"
    data = (await client.get(f"/employees/{erika.id}/personal-data", headers=t["chefin"])).json()
    assert (data["city"], data["iban"]) == ("Kassel", "DE89370400440532013000")
    values = {v["attribute_id"]: v["value"] for v in (await client.get(f"/employees/{erika.id}/attributes", headers=t["chefin"])).json()}
    assert values[shirt["id"]] == "M"
    mine = (await client.get("/me/change-requests", headers=t["erika"])).json()
    assert mine[0]["status"] == "APPROVED"
    assert (await client.post(f"/change-requests/{request_id}/decide", headers=t["chefin"], json={"approve": False})).status_code == 400


async def test_reject_keeps_data(client: AsyncClient, db_session: AsyncSession) -> None:
    erika, t = await _setup(client, db_session)
    request_id = (await client.post("/me/change-requests", headers=t["erika"], json={"personal": {"city": "Kassel"}})).json()["id"]
    r = await client.post(f"/change-requests/{request_id}/decide", headers=t["hr"], json={"approve": False, "note": "Bitte Meldebescheinigung"})
    assert r.json()["status"] == "REJECTED"
    assert (await client.get(f"/employees/{erika.id}/personal-data", headers=t["hr"])).json()["city"] is None
    assert (await client.post("/me/change-requests", headers=t["erika"], json={})).status_code == 400
