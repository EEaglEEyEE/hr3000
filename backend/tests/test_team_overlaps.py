"""Überschneidungen im Team: beim Antrag (Mitarbeiter nur mit Einstellung, ohne Art) und bei der
Genehmigung (mit Art und Resturlaub)."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, Team
from app.services.auth_service import hash_password
from tests.test_absence_types import _setup, _types


async def _team_setup(db_session: AsyncSession, client: AsyncClient):
    employee, headers = await _setup(db_session, client)
    team = Team(tenant_id=employee.tenant_id, name="Vertrieb")
    other_team = Team(tenant_id=employee.tenant_id, name="Lager")
    db_session.add_all([team, other_team])
    await db_session.commit()
    employee.team_id = team.id
    colleague = Employee(location_id=employee.location_id, first_name="Max", last_name="Kollege", employee_number="A2", team_id=team.id)
    stranger = Employee(location_id=employee.location_id, first_name="Lea", last_name="Lager", employee_number="A3", team_id=other_team.id)
    db_session.add_all([colleague, stranger])
    await db_session.commit()
    vacation = (await _types(client, headers))["Urlaub"]
    for person in (colleague, stranger):
        r = await client.post(
            "/absences", headers=headers,
            json={"employee_id": person.id, "absence_type_id": vacation["id"], "date_from": "2025-03-10", "date_to": "2025-03-14"},
        )
        assert r.status_code == 201, r.text
    return employee, headers, vacation


async def test_overlaps_for_approvers_and_employees(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers, _ = await _team_setup(db_session, client)
    params = {"from": "2025-03-12", "to": "2025-03-13"}

    hr_view = (await client.get(f"/employees/{employee.id}/team-overlaps", headers=headers, params=params)).json()
    assert [(o["name"], o["type_name"], o["pending"]) for o in hr_view] == [("Max Kollege", "Urlaub", False)]

    token = (await client.post("/auth/login", json={"email": "erika@example.com", "password": "pw123456"})).json()["access_token"]
    me = {"Authorization": f"Bearer {token}"}
    assert (await client.get(f"/employees/{employee.id}/team-overlaps", headers=me, params=params)).json() == []  # Standard aus

    r = await client.patch("/settings", headers=headers, json={"absence_overlaps_for_employees": True})
    assert r.status_code == 200, r.text
    own_view = (await client.get(f"/employees/{employee.id}/team-overlaps", headers=me, params=params)).json()
    assert [(o["name"], o["type_name"]) for o in own_view] == [("Max Kollege", None)]  # ohne Art

    bad = await client.get(f"/employees/{employee.id}/team-overlaps", headers=headers, params={"from": "2025-03-13", "to": "2025-03-12"})
    assert bad.status_code == 400


async def test_pending_requests_show_overlaps_and_remaining_vacation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers, vacation = await _team_setup(db_session, client)
    await client.patch(f"/absence-types/{vacation['id']}", headers=headers, json={"requires_approval": True})
    token = (await client.post("/auth/login", json={"email": "erika@example.com", "password": "pw123456"})).json()["access_token"]
    me = {"Authorization": f"Bearer {token}"}
    r = await client.post(
        "/absences", headers=me,
        json={"employee_id": employee.id, "absence_type_id": vacation["id"], "date_from": "2025-03-13", "date_to": "2025-03-17"},
    )
    assert r.status_code == 201 and r.json()["approval_status"] == "PENDING", r.text

    pending = (await client.get("/absences/pending", headers=headers)).json()
    assert len(pending) == 1
    assert [o["name"] for o in pending[0]["team_overlaps"]] == ["Max Kollege"]
    assert pending[0]["remaining_vacation_days"] is not None
