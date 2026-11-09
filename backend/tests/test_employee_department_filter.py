"""Mitarbeiterliste nach Abteilung filtern – eine Abteilung zeigt auch ihre Unterabteilungen
(Vertrieb → Innendienst), „ohne Abteilung“ die übrigen."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Department, Tenant
from app.services.department_service import subtree_ids
from tests.test_departments import _employee, _setup, _token


def test_subtree_ids() -> None:
    parents = {1: None, 2: 1, 3: 2, 4: None, 5: 4}
    assert subtree_ids(parents, 1) == {1, 2, 3}
    assert subtree_ids(parents, 2) == {2, 3}
    assert subtree_ids(parents, 3) == {3}
    assert subtree_ids(parents, 99) == {99}  # unbekannt: nur sich selbst
    assert subtree_ids({1: 2, 2: 1}, 1) == {1, 2}  # Zyklus bricht nicht


async def _names(client: AsyncClient, admin: dict, **params) -> list[str]:
    r = await client.get("/employees", headers=admin, params=params)
    assert r.status_code == 200, r.text
    return [e["first_name"] for e in r.json()]


async def test_filter_by_department_with_subdepartments(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _ = await _setup(db_session)
    admin = await _token(client, "chefin@example.com")
    sales = (await client.post("/departments", headers=admin, json={"name": "Vertrieb"})).json()
    inside = (await client.post("/departments", headers=admin, json={"name": "Innendienst", "parent_id": sales["id"]})).json()
    it = (await client.post("/departments", headers=admin, json={"name": "IT"})).json()
    await _employee(client, admin, location, "1", "Vera", department_id=sales["id"])
    await _employee(client, admin, location, "2", "Ines", department_id=inside["id"])
    await _employee(client, admin, location, "3", "Ivo", department_id=it["id"])
    await _employee(client, admin, location, "4", "Olaf")

    assert sorted(await _names(client, admin, department_id=sales["id"])) == ["Ines", "Vera"]
    assert await _names(client, admin, department_id=inside["id"]) == ["Ines"]
    assert await _names(client, admin, department_id=it["id"]) == ["Ivo"]
    assert await _names(client, admin, without_department="true") == ["Olaf"]
    assert len(await _names(client, admin)) == 4
    # Abteilung und Suche bzw. Standort kombinierbar
    assert await _names(client, admin, department_id=sales["id"], search="Ines") == ["Ines"]
    assert await _names(client, admin, department_id=sales["id"], location_id=location.id + 1) == []
    # Antwort enthält die Abteilung je Mitarbeiter
    r = await client.get("/employees", headers=admin, params={"department_id": inside["id"]})
    assert r.json()[0]["department_id"] == inside["id"]


async def test_department_filter_errors(client: AsyncClient, db_session: AsyncSession) -> None:
    await _setup(db_session)
    admin = await _token(client, "chefin@example.com")
    sales = (await client.post("/departments", headers=admin, json={"name": "Vertrieb"})).json()
    both = await client.get("/employees", headers=admin, params={"department_id": sales["id"], "without_department": "true"})
    assert both.status_code == 422 and both.json()["code"] == "INVALID_FILTER"
    assert (await client.get("/employees", headers=admin, params={"department_id": 0})).status_code == 422
    assert (await client.get("/employees", headers=admin, params={"department_id": 9999})).status_code == 404
    # Abteilung einer anderen Firma
    other = Tenant(subdomain="andere", name="Andere")
    db_session.add(other)
    await db_session.commit()
    foreign = Department(tenant_id=other.id, name="Fremd")
    db_session.add(foreign)
    await db_session.commit()
    assert (await client.get("/employees", headers=admin, params={"department_id": foreign.id})).status_code == 404
    assert (await client.get("/employees", headers=admin, params={"search": "x" * 101})).status_code == 422
