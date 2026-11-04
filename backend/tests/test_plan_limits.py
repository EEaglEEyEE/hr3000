"""Tarife: kostenlos bis 5 aktive Mitarbeiter, darüber nur mit Abo (PAID) oder unbegrenzt (UNLIMITED).
Geprüft wird beim Anlegen, beim CSV-Import und beim Reaktivieren; inaktive Mitarbeiter zählen nicht."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Employee, HrRole, HrUser, Location, Tenant, TenantPlan
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient, active: int = 0, inactive: int = 0):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    db_session.add(HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    for i in range(active + inactive):
        db_session.add(
            Employee(location_id=location.id, first_name=f"M{i}", last_name="Test", employee_number=f"E{i}", active=i < active)
        )
    await db_session.commit()
    token = (await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    return location, {"Authorization": f"Bearer {token}"}


async def _create(client, admin, location_id, number, active=True):
    return await client.post(
        "/employees",
        headers=admin,
        json={"location_id": location_id, "first_name": "Neu", "last_name": "Test", "employee_number": number, "active": active},
    )


async def _set_plan(db_session: AsyncSession, plan: TenantPlan) -> None:
    tenant = await db_session.get(Tenant, 1)
    tenant.plan = plan
    await db_session.commit()


async def test_new_tenants_start_free_with_five_employees(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(db_session, client, active=4)
    plan = (await client.get("/plan", headers=admin)).json()
    assert plan == {"plan": "FREE", "active_employees": 4, "limit": settings.free_employee_limit, "remaining": 1}

    assert (await _create(client, admin, location.id, "N1")).status_code == 201  # Nr. 5
    sixth = await _create(client, admin, location.id, "N2")
    assert sixth.status_code == 402 and sixth.json()["code"] == "PLAN_LIMIT_REACHED"
    assert "5 aktive Mitarbeiter" in sixth.json()["detail"]
    # Inaktiv anlegen geht weiterhin (z.B. ausgeschiedene Mitarbeiter nachpflegen)
    assert (await _create(client, admin, location.id, "N3", active=False)).status_code == 201
    assert (await client.get("/plan", headers=admin)).json()["remaining"] == 0


async def test_reactivating_counts_but_other_edits_do_not(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client, active=5, inactive=1)
    employees = {e["employee_number"]: e for e in (await client.get("/employees", headers=admin)).json()}
    inactive_id = employees["E5"]["id"]
    active_id = employees["E0"]["id"]

    r = await client.patch(f"/employees/{inactive_id}", headers=admin, json={"active": True})
    assert r.status_code == 402
    # Aktive Mitarbeiter bearbeiten bleibt möglich, auch "active: true" erneut senden.
    assert (await client.patch(f"/employees/{active_id}", headers=admin, json={"first_name": "Anna", "active": True})).status_code == 200
    # Platz schaffen und dann reaktivieren
    assert (await client.patch(f"/employees/{active_id}", headers=admin, json={"active": False})).status_code == 200
    assert (await client.patch(f"/employees/{inactive_id}", headers=admin, json={"active": True})).status_code == 200


async def test_csv_import_stops_at_the_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client, active=3)
    csv_text = (
        "vorname;nachname;personalnummer;standort;team;aktiv;eintrittsdatum;geburtsdatum\n"
        "A;Eins;I1;Zentrale;;ja;;\n"
        "B;Zwei;I2;Zentrale;;nein;;\n"
        "C;Drei;I3;Zentrale;;ja;;\n"
        "D;Vier;I4;Zentrale;;ja;;\n"
    )
    r = await client.post(
        "/employees/bulk-import", headers=admin, files={"file": ("m.csv", csv_text.encode("utf-8"), "text/csv")}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 2 freie Plätze: I1 und I3 aktiv, I2 inaktiv zählt nicht, I4 scheitert an der Grenze (Zeile 5)
    assert body["created"] == 3
    assert [(e["row"], "aktive Mitarbeiter" in e["message"]) for e in body["errors"]] == [(5, True)]
    assert (await client.get("/plan", headers=admin)).json()["active_employees"] == 5


async def test_paid_and_unlimited_have_no_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(db_session, client, active=5)
    for plan, number in ((TenantPlan.PAID, "P1"), (TenantPlan.UNLIMITED, "U1")):
        await _set_plan(db_session, plan)
        assert (await _create(client, admin, location.id, number)).status_code == 201
        status = (await client.get("/plan", headers=admin)).json()
        assert status["plan"] == plan.value and status["limit"] is None and status["remaining"] is None


async def test_downgrade_keeps_existing_employees_but_blocks_new(client: AsyncClient, db_session: AsyncSession) -> None:
    location, admin = await _setup(db_session, client, active=8)
    await _set_plan(db_session, TenantPlan.FREE)
    status = (await client.get("/plan", headers=admin)).json()
    assert status["active_employees"] == 8 and status["remaining"] == 0
    # Bestehende bleiben aktiv und nutzbar, nur neue kommen nicht dazu.
    assert len((await client.get("/employees", headers=admin, params={"active": True})).json()) == 8
    assert (await _create(client, admin, location.id, "N9")).status_code == 402


async def test_super_admin_sees_usage_and_sets_plan(client: AsyncClient, db_session: AsyncSession) -> None:
    await _setup(db_session, client, active=2, inactive=3)
    db_session.add(HrUser(tenant_id=None, email="super@example.com", password_hash=hash_password("super-pw"), role=HrRole.SUPER_ADMIN))
    await db_session.commit()
    host = {"Host": settings.super_admin_hostname}
    token = (await client.post("/auth/hr/login", headers=host, json={"email": "super@example.com", "password": "super-pw"})).json()["access_token"]
    sa = {**host, "Authorization": f"Bearer {token}"}

    tenants = (await client.get("/tenants", headers=sa)).json()
    assert [(t["plan"], t["active_employees"]) for t in tenants] == [("FREE", 2)]
    r = await client.patch(f"/tenants/{tenants[0]['id']}", headers=sa, json={"plan": "UNLIMITED"})
    assert r.status_code == 200 and r.json()["plan"] == "UNLIMITED"
    assert (await client.patch(f"/tenants/{tenants[0]['id']}", headers=sa, json={"plan": "GRATIS"})).status_code == 422

    created = await client.post("/tenants", headers=sa, json={"subdomain": "neu", "name": "Neu GmbH", "admin_email": "a@neu.example"})
    assert created.status_code == 201 and created.json()["plan"] == "FREE"


async def test_tenant_admin_cannot_change_own_plan(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    assert (await client.patch("/tenants/1", headers=admin, json={"plan": "UNLIMITED"})).status_code in (401, 403)
    assert (await client.patch("/settings", headers=admin, json={"plan": "UNLIMITED"})).status_code == 200  # unbekanntes Feld wird ignoriert
    assert (await client.get("/plan", headers=admin)).json()["plan"] == "FREE"
