from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, Holiday, HrRole, HrUser, Location, SummaryStatus, Tenant
from app.services.auth_service import hash_password
from app.services.timesheet_service import calculate_day, employee_timezone


async def _setup(db_session: AsyncSession, client: AsyncClient):
    locations = []
    for name in ("Ulm", "Köln", "Berlin"):
        location = Location(name=name, timezone="UTC")
        db_session.add(location)
        locations.append(location)
    db_session.add(HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR))
    await db_session.commit()
    for location in locations:
        await db_session.refresh(location)
    login = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    return locations, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_one_holiday_can_carry_several_locations(client: AsyncClient, db_session: AsyncSession) -> None:
    (ulm, koeln, berlin), headers = await _setup(db_session, client)

    created = await client.post(
        "/holidays",
        headers=headers,
        json={"date": "2026-06-04", "name": "Fronleichnam", "location_ids": [ulm.id, koeln.id, ulm.id]},
    )

    assert created.status_code == 201
    assert created.json()["location_ids"] == sorted([ulm.id, koeln.id])

    everything = (await client.get("/holidays?year=2026", headers=headers)).json()
    assert len([h for h in everything if h["name"] == "Fronleichnam"]) == 1  # eine Zeile, nicht je Standort

    for location, expected in ((ulm, 1), (koeln, 1), (berlin, 0)):
        listed = (await client.get(f"/holidays?year=2026&location_id={location.id}", headers=headers)).json()
        assert len(listed) == expected, location.name


async def test_holiday_without_locations_applies_everywhere(client: AsyncClient, db_session: AsyncSession) -> None:
    (ulm, _, berlin), headers = await _setup(db_session, client)

    created = await client.post(
        "/holidays", headers=headers, json={"date": "2026-10-03", "name": "Tag der Deutschen Einheit"}
    )

    assert created.json()["location_ids"] == []
    for location in (ulm, berlin):
        listed = (await client.get(f"/holidays?year=2026&location_id={location.id}", headers=headers)).json()
        assert [h["name"] for h in listed] == ["Tag der Deutschen Einheit"]


async def test_overlapping_scopes_on_same_date_rejected_but_disjoint_allowed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    (ulm, koeln, berlin), headers = await _setup(db_session, client)
    day = "2026-11-01"
    await client.post("/holidays", headers=headers, json={"date": day, "name": "Allerheiligen", "location_ids": [ulm.id]})

    overlap = await client.post(
        "/holidays", headers=headers, json={"date": day, "name": "Anderer", "location_ids": [ulm.id, koeln.id]}
    )
    everywhere = await client.post("/holidays", headers=headers, json={"date": day, "name": "Für alle"})
    disjoint = await client.post(
        "/holidays", headers=headers, json={"date": day, "name": "Nur Köln", "location_ids": [koeln.id]}
    )

    assert overlap.status_code == 409 and overlap.json()["code"] == "HOLIDAY_DATE_TAKEN"
    assert everywhere.status_code == 409
    assert disjoint.status_code == 201


async def test_update_locations_add_and_reset_to_all(client: AsyncClient, db_session: AsyncSession) -> None:
    (ulm, koeln, _), headers = await _setup(db_session, client)
    created = await client.post(
        "/holidays", headers=headers, json={"date": "2026-06-04", "name": "Fronleichnam", "location_ids": [ulm.id]}
    )
    holiday_id = created.json()["id"]

    widened = await client.patch(
        f"/holidays/{holiday_id}", headers=headers, json={"location_ids": [ulm.id, koeln.id]}
    )
    assert widened.json()["location_ids"] == sorted([ulm.id, koeln.id])

    unchanged = await client.patch(f"/holidays/{holiday_id}", headers=headers, json={"name": "Fronleichnam (kath.)"})
    assert unchanged.json()["location_ids"] == sorted([ulm.id, koeln.id])

    everywhere = await client.patch(f"/holidays/{holiday_id}", headers=headers, json={"location_ids": []})
    assert everywhere.json()["location_ids"] == []


async def test_unknown_or_foreign_location_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    (ulm, _, _), headers = await _setup(db_session, client)
    db_session.add(Tenant(id=2, subdomain="other", name="Other"))
    await db_session.commit()
    foreign = Location(tenant_id=2, name="Fremd", timezone="UTC")
    db_session.add(foreign)
    await db_session.commit()
    await db_session.refresh(foreign)

    for ids in ([9999], [ulm.id, foreign.id]):
        response = await client.post(
            "/holidays", headers=headers, json={"date": "2026-06-04", "name": "X", "location_ids": ids}
        )
        assert response.status_code == 404 and response.json()["code"] == "LOCATION_NOT_FOUND"


async def test_import_merges_same_holiday_across_locations(client: AsyncClient, db_session: AsyncSession) -> None:
    (ulm, koeln, _), headers = await _setup(db_session, client)

    first = await client.post(
        "/holidays/import", headers=headers, json={"year": 2026, "location_id": ulm.id, "bundesland": "BW"}
    )
    second = await client.post(
        "/holidays/import", headers=headers, json={"year": 2026, "location_id": koeln.id, "bundesland": "NW"}
    )
    assert first.status_code == 200 and second.status_code == 200

    holidays = (await client.get("/holidays?year=2026", headers=headers)).json()
    new_year = [h for h in holidays if h["date"] == "2026-01-01"]
    assert len(new_year) == 1
    assert new_year[0]["location_ids"] == sorted([ulm.id, koeln.id])
    # Kein Datum taucht doppelt auf, solange sich die Standorte nicht überschneiden sollen.
    for holiday_date in {h["date"] for h in holidays}:
        same_day = [h for h in holidays if h["date"] == holiday_date]
        covered = [loc for h in same_day for loc in h["location_ids"]]
        assert len(covered) == len(set(covered))


async def test_holiday_of_another_tenant_does_not_apply(client: AsyncClient, db_session: AsyncSession) -> None:
    (ulm, _, _), headers = await _setup(db_session, client)
    await client.post("/holidays", headers=headers, json={"date": "2026-10-03", "name": "Firmenweit"})

    db_session.add(Tenant(id=2, subdomain="other", name="Other"))
    await db_session.commit()
    other_location = Location(tenant_id=2, name="Fremd", timezone="UTC")
    db_session.add(other_location)
    await db_session.commit()
    await db_session.refresh(other_location)
    other_employee = Employee(
        tenant_id=2, location_id=other_location.id, first_name="Frem", last_name="Der", employee_number="X1"
    )
    own_employee = Employee(location_id=ulm.id, first_name="Eigen", last_name="Er", employee_number="X2")
    db_session.add_all([other_employee, own_employee])
    await db_session.commit()
    await db_session.refresh(other_employee)
    await db_session.refresh(own_employee)

    own = await calculate_day(db_session, own_employee, date(2026, 10, 3), await employee_timezone(db_session, own_employee))
    other = await calculate_day(
        db_session, other_employee, date(2026, 10, 3), await employee_timezone(db_session, other_employee)
    )

    assert own.status != other.status
    assert other.status != SummaryStatus.HOLIDAY


async def test_deleting_location_assignment_keeps_holiday_row(client: AsyncClient, db_session: AsyncSession) -> None:
    (ulm, _, _), headers = await _setup(db_session, client)
    created = await client.post(
        "/holidays", headers=headers, json={"date": "2026-06-04", "name": "Fronleichnam", "location_ids": [ulm.id]}
    )

    deleted = await client.delete(f"/holidays/{created.json()['id']}", headers=headers)

    assert deleted.status_code == 204
    assert (await client.get("/holidays?year=2026", headers=headers)).json() == []
    assert (await db_session.get(Holiday, created.json()["id"])) is None
