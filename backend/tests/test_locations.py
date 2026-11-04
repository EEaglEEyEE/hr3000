from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HrRole, HrUser
from app.services.auth_service import hash_password


async def _create_hr_user(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_hr_can_create_and_list_locations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/locations",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Standort A", "timezone": "Europe/Berlin"},
    )
    assert create_response.status_code == 201

    list_response = await client.get("/locations", headers={"Authorization": f"Bearer {token}"})
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["name"] == "Standort A"


async def test_hr_can_update_location(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/locations",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Standort A", "timezone": "Europe/Berlin"},
    )
    location_id = create_response.json()["id"]

    patch_response = await client.patch(
        f"/locations/{location_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Standort A (Hauptsitz)"},
    )

    assert patch_response.status_code == 200
    body = patch_response.json()
    assert body["name"] == "Standort A (Hauptsitz)"
    assert body["timezone"] == "Europe/Berlin"


async def test_location_bundesland_can_be_set_and_cleared(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/locations",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Standort A", "timezone": "Europe/Berlin", "bundesland": "BY"},
    )
    assert create_response.json()["bundesland"] == "BY"
    location_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/locations/{location_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"bundesland": "NW"},
    )
    assert update_response.json()["bundesland"] == "NW"

    clear_response = await client.patch(
        f"/locations/{location_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"clear_bundesland": True},
    )
    assert clear_response.json()["bundesland"] is None


async def test_update_unknown_location(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.patch(
        "/locations/999", headers={"Authorization": f"Bearer {token}"}, json={"name": "X"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "LOCATION_NOT_FOUND"
