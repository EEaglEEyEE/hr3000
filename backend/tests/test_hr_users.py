from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HrRole, HrUser
from app.services.auth_service import hash_password


async def _create_admin(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_hr_staff(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="staff@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _token(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/hr/login", json={"email": email, "password": "pw"})
    return response.json()["access_token"]


async def test_admin_can_create_and_list_hr_users(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin(db_session)
    token = await _token(client, "admin@example.com")

    create_response = await client.post(
        "/hr-users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "new-hr@example.com", "password": "pw123456", "role": "HR"},
    )

    assert create_response.status_code == 201
    body = create_response.json()
    assert body["email"] == "new-hr@example.com"
    assert "password" not in body
    assert "password_hash" not in body

    list_response = await client.get("/hr-users", headers={"Authorization": f"Bearer {token}"})
    assert len(list_response.json()) == 2  # admin + neu angelegt

    login_response = await client.post(
        "/auth/hr/login", json={"email": "new-hr@example.com", "password": "pw123456"}
    )
    assert login_response.status_code == 200


async def test_non_admin_cannot_create_hr_users(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_staff(db_session)
    token = await _token(client, "staff@example.com")

    response = await client.post(
        "/hr-users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "x@example.com", "password": "pw123456"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ADMIN_PERMISSION_REQUIRED"


async def test_create_hr_user_duplicate_email_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _create_admin(db_session)
    token = await _token(client, "admin@example.com")

    response = await client.post(
        "/hr-users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": admin.email, "password": "pw123456"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EMAIL_TAKEN"


async def test_admin_can_delete_hr_user(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_admin(db_session)
    other = await _create_hr_staff(db_session)
    token = await _token(client, "admin@example.com")

    response = await client.delete(f"/hr-users/{other.id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 204


async def test_admin_cannot_delete_self(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _create_admin(db_session)
    token = await _token(client, "admin@example.com")

    response = await client.delete(f"/hr-users/{admin.id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 400
    assert response.json()["code"] == "CANNOT_DELETE_SELF"
