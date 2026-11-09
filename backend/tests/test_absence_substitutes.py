"""Vertretung bei Abwesenheiten (je Abwesenheitsart: nicht / optional / Pflicht beim eigenen Antrag)."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, Notification, NotificationType
from app.services.auth_service import hash_password
from tests.test_absence_types import _setup, _types


async def _colleague(db_session: AsyncSession, employee: Employee, **extra) -> Employee:
    colleague = Employee(
        location_id=employee.location_id, first_name="Max", last_name="Vertreter", employee_number="A2",
        login_email="max@example.com", password_hash=hash_password("pw123456"), **extra,
    )
    db_session.add(colleague)
    await db_session.commit()
    await db_session.refresh(colleague)
    return colleague


async def _employee_headers(client: AsyncClient) -> dict:
    token = (await client.post("/auth/login", json={"email": "erika@example.com", "password": "pw123456"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_required_substitute_for_own_requests_and_notification(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    colleague = await _colleague(db_session, employee)
    vacation = (await _types(client, headers))["Urlaub"]
    r = await client.patch(f"/absence-types/{vacation['id']}", headers=headers, json={"substitute_mode": "REQUIRED"})
    assert r.status_code == 200 and r.json()["substitute_mode"] == "REQUIRED"

    me = await _employee_headers(client)
    body = {"employee_id": employee.id, "absence_type_id": vacation["id"], "date_from": "2025-03-10", "date_to": "2025-03-12"}
    missing = await client.post("/absences", headers=me, json=body)
    assert missing.status_code == 400 and missing.json()["code"] == "SUBSTITUTE_REQUIRED"

    candidates = (await client.get(f"/employees/{employee.id}/substitute-candidates", headers=me)).json()
    assert [c["last_name"] for c in candidates] == ["Vertreter"]  # ohne die Person selbst

    ok = await client.post("/absences", headers=me, json={**body, "substitute_employee_id": colleague.id})
    assert ok.status_code == 201, ok.text
    assert ok.json()["substitute_name"] == "Max Vertreter"

    # Genehmigt (ohne Genehmigungspflicht sofort) -> Vertretung bekommt eine Benachrichtigung
    notes = (
        await db_session.execute(select(Notification).where(Notification.type == NotificationType.SUBSTITUTE_ASSIGNED))
    ).scalars().all()
    assert len(notes) == 1 and notes[0].recipient_account_id == colleague.account.id
    assert "Erika Muster" in notes[0].message and "10.03.2025" in notes[0].message

    # HR darf die Vertretung weglassen
    hr = await client.post("/absences", headers=headers, json={**body, "date_from": "2025-04-01", "date_to": "2025-04-01"})
    assert hr.status_code == 201, hr.text


async def test_substitute_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    inactive = await _colleague(db_session, employee, active=False)
    vacation = (await _types(client, headers))["Urlaub"]
    body = {"employee_id": employee.id, "absence_type_id": vacation["id"], "date_from": "2025-03-10", "date_to": "2025-03-10"}

    not_allowed = await client.post("/absences", headers=headers, json={**body, "substitute_employee_id": inactive.id})
    assert not_allowed.status_code == 400 and not_allowed.json()["code"] == "SUBSTITUTE_NOT_ALLOWED"  # Standard: keine Vertretung

    await client.patch(f"/absence-types/{vacation['id']}", headers=headers, json={"substitute_mode": "OPTIONAL"})
    gone = await client.post("/absences", headers=headers, json={**body, "substitute_employee_id": inactive.id})
    assert gone.status_code == 404 and gone.json()["code"] == "SUBSTITUTE_NOT_FOUND"
    own = await client.post("/absences", headers=headers, json={**body, "substitute_employee_id": employee.id})
    assert own.status_code == 400 and own.json()["code"] == "SUBSTITUTE_SELF"

    created = await client.post("/absences", headers=headers, json=body)
    assert created.status_code == 201 and created.json()["substitute_employee_id"] is None
