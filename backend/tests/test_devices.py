from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession, name: str = "Standort A") -> Location:
    location = Location(name=name, timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_hr_user(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_hr_can_create_and_list_devices(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/devices",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": location.id, "name": "Kiosk A1"},
    )

    assert create_response.status_code == 201
    body = create_response.json()
    assert body["name"] == "Kiosk A1"
    assert len(body["device_token"]) > 10

    list_response = await client.get("/devices", headers={"Authorization": f"Bearer {token}"})
    assert len(list_response.json()) == 1


async def test_create_device_unknown_location(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.post(
        "/devices",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": 999, "name": "Kiosk"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "LOCATION_NOT_FOUND"


async def test_hr_can_rename_move_and_regenerate_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location_a = await _create_location(db_session, "Standort A")
    location_b = await _create_location(db_session, "Standort B")
    device = Device(location_id=location_a.id, device_token="old-token", name="Kiosk A1")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.patch(
        f"/devices/{device.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": location_b.id, "name": "Kiosk B1", "regenerate_token": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["location_id"] == location_b.id
    assert body["name"] == "Kiosk B1"
    assert body["device_token"] != "old-token"


async def test_hr_can_delete_device(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    device = Device(location_id=location.id, device_token="tok", name="Kiosk A1")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.delete(f"/devices/{device.id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 204

    list_response = await client.get("/devices", headers={"Authorization": f"Bearer {token}"})
    assert list_response.json() == []


async def test_devices_filtered_by_location(client: AsyncClient, db_session: AsyncSession) -> None:
    location_a = await _create_location(db_session, "Standort A")
    location_b = await _create_location(db_session, "Standort B")
    db_session.add(Device(location_id=location_a.id, device_token="tok-a", name="Kiosk A1"))
    db_session.add(Device(location_id=location_b.id, device_token="tok-b", name="Kiosk B1"))
    await db_session.commit()
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.get(
        f"/devices?location_id={location_a.id}", headers={"Authorization": f"Bearer {token}"}
    )

    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Kiosk A1"


async def test_device_screen_hours_modes(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_hr_user(db_session)
    headers = {"Authorization": f"Bearer {await _hr_token(client)}"}
    device = (await client.post("/devices", headers=headers, json={"location_id": location.id, "name": "Eingang"})).json()
    url = f"/devices/{device['id']}"
    assert device["screen_hours_mode"] is None  # Standard: wie Einstellungen

    r = await client.patch(url, headers=headers, json={"screen_hours_mode": "CUSTOM", "screen_on_from": "22:00", "screen_on_until": "06:00"})
    assert r.status_code == 200, r.text
    assert (r.json()["screen_hours_mode"], r.json()["screen_on_from"], r.json()["screen_on_until"]) == ("CUSTOM", "22:00:00", "06:00:00")

    r = await client.patch(url, headers=headers, json={"screen_hours_mode": "ALWAYS", "screen_on_from": "08:00", "screen_on_until": "09:00"})
    assert r.status_code == 200
    assert (r.json()["screen_hours_mode"], r.json()["screen_on_from"], r.json()["screen_on_until"]) == ("ALWAYS", None, None)

    r = await client.patch(url, headers=headers, json={"screen_hours_mode": "DEFAULT"})
    assert r.status_code == 200 and r.json()["screen_hours_mode"] is None

    for body in (
        {"screen_hours_mode": "CUSTOM"},
        {"screen_hours_mode": "CUSTOM", "screen_on_from": "06:00"},
        {"screen_hours_mode": "CUSTOM", "screen_on_from": "06:00", "screen_on_until": "06:00"},
        {"screen_hours_mode": "NACHTS"},
    ):
        assert (await client.patch(url, headers=headers, json=body)).status_code == 422, body
    # Andere Felder ändern lässt die Bildschirmzeiten in Ruhe
    await client.patch(url, headers=headers, json={"screen_hours_mode": "ALWAYS"})
    r = await client.patch(url, headers=headers, json={"name": "Eingang Nord"})
    assert r.json()["screen_hours_mode"] == "ALWAYS"


async def test_device_screen_hours_foreign_tenant(client: AsyncClient, db_session: AsyncSession) -> None:
    from app.models import Tenant

    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.commit()
    other_location = Location(tenant_id=2, name="Fremd", timezone="UTC")
    db_session.add(other_location)
    await db_session.commit()
    foreign = Device(tenant_id=2, location_id=other_location.id, name="Fremd", device_token="tok-foreign")
    db_session.add(foreign)
    await db_session.commit()
    await _create_hr_user(db_session)
    headers = {"Authorization": f"Bearer {await _hr_token(client)}"}
    r = await client.patch(f"/devices/{foreign.id}", headers=headers, json={"screen_hours_mode": "ALWAYS"})
    assert r.status_code == 404
