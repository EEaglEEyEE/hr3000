from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLogEntry, Employee, HrRole, Account, Location
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1", hire_date=date(2030, 5, 1), login_email="e@example.com", password_hash=hash_password("pw"))
    db_session.add_all([
        employee,
        Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        Account(email="sup@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR),
    ])
    await db_session.commit()
    await db_session.refresh(employee)
    headers = {}
    for name, path in (("hr", "/auth/login"), ("sup", "/auth/login")):
        headers[name] = {"Authorization": "Bearer " + (await client.post(path, json={"email": f"{name}@example.com", "password": "pw"})).json()["access_token"]}
    headers["self"] = {"Authorization": "Bearer " + (await client.post("/auth/login", json={"email": "e@example.com", "password": "pw"})).json()["access_token"]}
    return employee, headers


async def test_default_templates_start_checklist_and_tick_items(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)

    defaults = await client.post("/checklist-templates/defaults", headers=headers["hr"])
    assert defaults.status_code == 201 and {t["kind"] for t in defaults.json()} == {"ONBOARDING", "OFFBOARDING"}
    assert (await client.post("/checklist-templates/defaults", headers=headers["hr"])).status_code == 409
    onboarding = next(t for t in defaults.json() if t["kind"] == "ONBOARDING")

    started = await client.post(f"/employees/{employee.id}/checklists", headers=headers["hr"], json={"template_id": onboarding["id"]})
    assert started.status_code == 201
    checklist = started.json()
    assert checklist["anchor_date"] == "2030-05-01"  # Anstelldatum
    assert checklist["items"][0]["due_date"] == "2030-04-24"  # 7 Tage davor
    assert len(checklist["items"]) == len(onboarding["items"])

    item = checklist["items"][0]
    done = await client.patch(f"/checklists/{checklist['id']}/items/{item['id']}", headers=headers["hr"], json={"done": True, "note": "Original im Ordner"})
    assert done.status_code == 200 and done.json()["done"] is True and done.json()["done_at"] is not None

    open_items = (await client.get("/checklists/open-items", headers=headers["hr"])).json()
    assert len(open_items) == len(onboarding["items"]) - 1 and all(not o["overdue"] for o in open_items)

    undone = await client.patch(f"/checklists/{checklist['id']}/items/{item['id']}", headers=headers["hr"], json={"done": False})
    assert undone.json()["done"] is False and undone.json()["done_at"] is None

    audit = {e.action for e in (await db_session.execute(select(AuditLogEntry))).scalars().all()}
    assert AuditAction.CHECKLIST_STARTED in audit


async def test_custom_template_update_and_permissions(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    body = {"kind": "OFFBOARDING", "name": "Kurz", "items": [{"title": "Schlüssel zurück", "responsible": "IT", "due_offset_days": 0}]}

    assert (await client.post("/checklist-templates", headers=headers["sup"], json=body)).status_code == 403  # Supervisor nicht
    assert (await client.post("/checklist-templates", headers=headers["self"], json=body)).status_code == 403
    assert (await client.post("/checklist-templates", headers=headers["hr"], json={**body, "items": []})).status_code == 422
    assert (await client.post("/checklist-templates", headers=headers["hr"], json={**body, "items": [{"title": "x" * 201}]})).status_code == 422

    template = (await client.post("/checklist-templates", headers=headers["hr"], json=body)).json()
    updated = await client.patch(f"/checklist-templates/{template['id']}", headers=headers["hr"], json={"items": [{"title": "A"}, {"title": "B", "due_offset_days": 5}]})
    assert [i["title"] for i in updated.json()["items"]] == ["A", "B"]

    started = (await client.post(f"/employees/{employee.id}/checklists", headers=headers["hr"], json={"template_id": template["id"], "anchor_date": "2020-01-01"})).json()
    # Vorlage ändern wirkt nicht zurück; überfällige Aufgaben werden markiert.
    await client.delete(f"/checklist-templates/{template['id']}", headers=headers["hr"])
    assert len((await client.get(f"/employees/{employee.id}/checklists", headers=headers["hr"])).json()[0]["items"]) == 2
    assert all(o["overdue"] for o in (await client.get("/checklists/open-items", headers=headers["hr"])).json())
    assert (await client.delete(f"/checklists/{started['id']}", headers=headers["hr"])).status_code == 204
    assert (await client.get(f"/employees/{employee.id}/checklists", headers=headers["hr"])).json() == []
