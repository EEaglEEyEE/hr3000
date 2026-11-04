from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HrRole, HrUser
from app.services.auth_service import hash_password


async def _create_hr_user(db_session: AsyncSession, role: HrRole = HrRole.ADMIN) -> HrUser:
    user = HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_import_holidays_with_explicit_bundesland(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.post(
        "/holidays/import",
        headers={"Authorization": f"Bearer {token}"},
        json={"year": 2026, "bundesland": "BY"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["skipped_existing"] == 0
    names = {h["name"] for h in body["imported"]}
    assert "Mariä Himmelfahrt" in names
    assert "Heilige Drei Könige" in names

    list_response = await client.get(
        "/holidays", params={"year": 2026}, headers={"Authorization": f"Bearer {token}"}
    )
    assert len(list_response.json()) == len(body["imported"])


async def test_import_holidays_skips_existing_dates(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    await client.post(
        "/holidays",
        headers={"Authorization": f"Bearer {token}"},
        json={"date": "2026-01-01", "name": "Bereits angelegt"},
    )

    response = await client.post(
        "/holidays/import",
        headers={"Authorization": f"Bearer {token}"},
        json={"year": 2026, "bundesland": "BY"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["skipped_existing"] == 1
    assert all(h["date"] != "2026-01-01" for h in body["imported"])


async def test_import_uses_default_bundesland_when_omitted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)
    await client.patch(
        "/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"default_bundesland": "SN"},
    )

    response = await client.post(
        "/holidays/import",
        headers={"Authorization": f"Bearer {token}"},
        json={"year": 2026},
    )

    assert response.status_code == 200
    names = {h["name"] for h in response.json()["imported"]}
    assert "Buß- und Bettag" in names


async def test_import_without_bundesland_and_without_default_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    response = await client.post(
        "/holidays/import",
        headers={"Authorization": f"Bearer {token}"},
        json={"year": 2026},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "BUNDESLAND_REQUIRED"
