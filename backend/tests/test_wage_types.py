"""Seite „Lohnarten“: Lohnart je Zeitart und Katalog der Zulagen-/Einmalzahlungsarten."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient) -> tuple[int, dict, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Wanda", last_name="Lohnart", employee_number="W1")
    db_session.add_all(
        [
            employee,
            HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
            HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        ]
    )
    await db_session.commit()
    await db_session.refresh(employee)
    headers = []
    for email in ("admin@example.com", "hr@example.com"):
        token = (await client.post("/auth/hr/login", json={"email": email, "password": "pw"})).json()["access_token"]
        headers.append({"Authorization": f"Bearer {token}"})
    return employee.id, headers[0], headers[1]


async def test_wage_types_per_time_type(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin, hr = await _setup(db_session, client)
    items = (await client.get("/wage-types", headers=admin)).json()["items"]
    assert [i["item"] for i in items][:2] == ["WORKED", "VACATION"] and all(i["wage_type"] is None for i in items)
    assert next(i for i in items if i["item"] == "PUBLIC_HOLIDAY")["label"] == "Feiertag"

    r = await client.put("/wage-types", headers=admin, json={"items": {"WORKED": "1000", "SICK": " 1300 "}})
    assert r.status_code == 200
    assert {i["item"]: i["wage_type"] for i in r.json()["items"]} | {} == {
        "WORKED": "1000", "VACATION": None, "SICK": "1300", "CHILD_SICK": None, "SPECIAL_LEAVE": None,
        "PUBLIC_HOLIDAY": None, "WORK_TIME": None, "OVERTIME_PAYOUT": None,
    }
    r = await client.put("/wage-types", headers=admin, json={"items": {"SICK": ""}})
    assert {i["item"]: i["wage_type"] for i in r.json()["items"]}["SICK"] is None
    for bad in ({"WORKED": "12a"}, {"WORKED": "1234567"}, {"UNKNOWN": "1"}):
        assert (await client.put("/wage-types", headers=admin, json={"items": bad})).status_code == 422, bad
    assert (await client.get("/wage-types", headers=hr)).status_code == 403
    log = (await client.get("/audit-log", headers=admin)).json()
    assert any(e["detail"].startswith("Lohnarten geändert: WORKED=1000") for e in log)


async def test_pay_component_type_catalog(client: AsyncClient, db_session: AsyncSession) -> None:
    employee_id, admin, hr = await _setup(db_session, client)
    r = await client.post("/pay-component-types", headers=admin, json={"kind": "ALLOWANCE", "name": " Fahrtkosten ", "wage_type": "2000"})
    assert r.status_code == 201 and r.json()["name"] == "Fahrtkosten" and r.json()["in_use"] == 0
    type_id = r.json()["id"]
    assert (await client.post("/pay-component-types", headers=admin, json={"kind": "ALLOWANCE", "name": "Fahrtkosten"})).status_code == 409
    # gleicher Name als Einmalzahlung ist eine eigene Art
    assert (await client.post("/pay-component-types", headers=admin, json={"kind": "ONE_TIME", "name": "Fahrtkosten"})).status_code == 201
    assert (await client.get("/pay-component-types", headers=hr)).status_code == 403

    url = f"/employees/{employee_id}/pay-components"
    allowance = {"kind": "ALLOWANCE", "amount": 50, "unit": "PER_MONTH", "valid_from": "2026-09-01"}
    r = await client.post(url, headers=admin, json={**allowance, "type_id": type_id})
    assert r.status_code == 201 and (r.json()["name"], r.json()["wage_type"], r.json()["type_id"]) == ("Fahrtkosten", "2000", type_id)
    # über den Namen (Groß-/Kleinschreibung egal) landet es bei derselben Art
    r = await client.post(url, headers=admin, json={**allowance, "type_name": "fahrtkosten"})
    assert r.status_code == 201 and r.json()["type_id"] == type_id
    # Art passt nicht zur Einmalzahlung
    r = await client.post(url, headers=admin, json={"kind": "ONE_TIME", "amount": 10, "pay_date": "2026-09-15", "type_id": type_id})
    assert r.status_code == 400 and r.json()["code"] == "PAY_COMPONENT_TYPE_KIND"
    assert (await client.post(url, headers=admin, json={**allowance})).status_code == 422  # ohne Art

    r = await client.patch(f"/pay-component-types/{type_id}", headers=admin, json={"name": "Fahrtgeld", "wage_type": "2010"})
    assert r.status_code == 200 and r.json()["in_use"] == 2
    assert {c["name"] for c in (await client.get(url, headers=admin)).json()} == {"Fahrtgeld"}
    r = await client.delete(f"/pay-component-types/{type_id}", headers=admin)
    assert r.status_code == 409 and r.json()["code"] == "PAY_COMPONENT_TYPE_IN_USE"
    assert (await client.patch(f"/pay-component-types/{type_id}", headers=admin, json={"active": False})).json()["active"] is False
    r = await client.post(url, headers=admin, json={**allowance, "type_id": type_id})
    assert r.status_code == 400 and r.json()["code"] == "PAY_COMPONENT_TYPE_INACTIVE"
