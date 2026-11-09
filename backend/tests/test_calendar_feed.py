"""Kalender-Abo (iCal): privater Link, Inhalt nach den Kalender-Regeln, alter Link ungültig."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, Team
from tests.test_absence_types import _setup, _types


async def test_calendar_feed(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    team = Team(tenant_id=employee.tenant_id, name="Vertrieb")
    db_session.add(team)
    await db_session.commit()
    employee.team_id = team.id
    colleague = Employee(location_id=employee.location_id, first_name="Max", last_name="Kollege", employee_number="A2", team_id=team.id)
    db_session.add(colleague)
    await db_session.commit()
    types = await _types(client, headers)
    from datetime import date, timedelta

    day = (date.today() + timedelta(days=7)).isoformat()
    for person, type_name in ((employee, "Urlaub"), (colleague, "Krank")):
        r = await client.post(
            "/absences", headers=headers,
            json={"employee_id": person.id, "absence_type_id": types[type_name]["id"], "date_from": day, "date_to": day},
        )
        assert r.status_code == 201, r.text

    # HR: alles mit Art
    path = (await client.post("/me/calendar-token", headers=headers)).json()["path"]
    feed = await client.get(path.removeprefix("/api"))
    assert feed.status_code == 200 and feed.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VCALENDAR" in feed.text and "Max Kollege: Krank" in feed.text and "Erika Muster: Urlaub" in feed.text

    # Mitarbeiterin: eigenes mit Art; Team nur mit Freigabe und dann ausgegraut
    token = (await client.post("/auth/login", json={"email": "erika@example.com", "password": "pw123456"})).json()["access_token"]
    me = {"Authorization": f"Bearer {token}"}
    own_path = (await client.post("/me/calendar-token", headers=me)).json()["path"]
    own = (await client.get(own_path.removeprefix("/api"))).text
    assert "SUMMARY:Urlaub" in own and "Kollege" not in own
    await client.patch("/settings", headers=headers, json={"team_calendar_for_employees": True})
    own = (await client.get(own_path.removeprefix("/api"))).text
    assert "Max Kollege: abwesend" in own and "Krank" not in own

    # Neuer Link -> alter ungültig
    await client.post("/me/calendar-token", headers=me)
    assert (await client.get(own_path.removeprefix("/api"))).status_code == 404
