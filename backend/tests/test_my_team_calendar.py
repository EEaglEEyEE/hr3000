"""Teamkalender für Mitarbeiter: nur mit Einstellung, die eigene Abteilung (ohne Unterabteilungen, ohne
Abteilung nur man selbst), Art nur bei „farbig“."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee
from org_helpers import department
from tests.test_absence_types import _setup, _types


async def test_my_team_calendar(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    colleague = Employee(location_id=employee.location_id, first_name="Max", last_name="Kollege", employee_number="A2")
    other = Employee(location_id=employee.location_id, first_name="Lea", last_name="Fremd", employee_number="A3")
    sub = Employee(location_id=employee.location_id, first_name="Uwe", last_name="Unter", employee_number="A4")
    db_session.add_all([colleague, other, sub])
    await db_session.commit()
    sales = await department(db_session, "Vertrieb", employee, colleague)
    await department(db_session, "Innendienst", sub, parent=sales)
    types = await _types(client, headers)
    for type_name, day in (("Krank", "2025-03-10"), ("Urlaub", "2025-03-11")):
        r = await client.post(
            "/absences", headers=headers,
            json={"employee_id": colleague.id, "absence_type_id": types[type_name]["id"], "date_from": day, "date_to": day},
        )
        assert r.status_code == 201, r.text

    token = (await client.post("/auth/login", json={"email": "erika@example.com", "password": "pw123456"})).json()["access_token"]
    me = {"Authorization": f"Bearer {token}"}
    params = {"from": "2025-03-10", "to": "2025-03-11"}
    assert (await client.get("/me/team-calendar", headers=me, params=params)).status_code == 403  # Standard aus

    await client.patch("/settings", headers=headers, json={"team_calendar_for_employees": True})
    await client.patch(f"/absence-types/{types['Urlaub']['id']}", headers=headers, json={"calendar_visibility": "COLOR"})
    rows = (await client.get("/me/team-calendar", headers=me, params=params)).json()
    # nicht Lea (ohne Abteilung) und nicht Uwe (Unterabteilung)
    assert sorted(r["last_name"] for r in rows) == ["Kollege", "Muster"]
    assert {r["department_id"] for r in rows} == {sales.id}
    max_days = next(r["days"] for r in rows if r["last_name"] == "Kollege")
    assert (max_days[0]["status"], max_days[0]["absence_type"]) == ("ABSENCE", None)  # Krank: ausgegraut
    assert (max_days[1]["status"], max_days[1]["absence_type"]) == ("ABSENCE", "VACATION")  # Urlaub: farbig

    # Ohne Abteilung nur man selbst
    employee.department_id = None
    await db_session.commit()
    rows = (await client.get("/me/team-calendar", headers=me, params=params)).json()
    assert [(r["last_name"], r["department_id"]) for r in rows] == [("Muster", None)]
