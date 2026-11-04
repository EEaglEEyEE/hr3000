from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, HrRole, HrUser, Location
from app.services.auth_service import decode_token, hash_password


async def _create_hr_user(db_session: AsyncSession, email: str, password: str) -> HrUser:
    user = HrUser(email=email, password_hash=hash_password(password), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_device(db_session: AsyncSession, token: str) -> Device:
    location = Location(name="Standort A", timezone="Europe/Berlin")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    device = Device(location_id=location.id, device_token=token, name="Kiosk A1")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


async def test_hr_login_success(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session, "hr@example.com", "s3cret-pw")

    response = await client.post(
        "/auth/hr/login", json={"email": "hr@example.com", "password": "s3cret-pw"}
    )

    assert response.status_code == 200
    body = response.json()
    assert decode_token(body["access_token"])["type"] == "access"
    assert decode_token(body["refresh_token"])["type"] == "refresh"


async def test_hr_login_wrong_password(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session, "hr@example.com", "s3cret-pw")

    response = await client.post(
        "/auth/hr/login", json={"email": "hr@example.com", "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "E-Mail oder Passwort falsch.", "code": "INVALID_CREDENTIALS"}


async def test_hr_login_unknown_email(client: AsyncClient, db_session: AsyncSession) -> None:
    response = await client.post(
        "/auth/hr/login", json={"email": "nobody@example.com", "password": "whatever"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


async def test_hr_refresh_issues_new_token_pair(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session, "hr@example.com", "s3cret-pw")
    login_response = await client.post(
        "/auth/hr/login", json={"email": "hr@example.com", "password": "s3cret-pw"}
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await client.post("/auth/hr/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert decode_token(response.json()["access_token"])["type"] == "access"


async def test_hr_refresh_rejects_access_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session, "hr@example.com", "s3cret-pw")
    login_response = await client.post(
        "/auth/hr/login", json={"email": "hr@example.com", "password": "s3cret-pw"}
    )
    access_token = login_response.json()["access_token"]

    response = await client.post("/auth/hr/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"


async def test_device_login_success(client: AsyncClient, db_session: AsyncSession) -> None:
    device = await _create_device(db_session, "device-token-123")

    response = await client.post("/auth/device/login", json={"device_token": "device-token-123"})

    assert response.status_code == 200
    body = response.json()
    assert body["location_id"] == device.location_id
    assert body["device_name"] == "Kiosk A1"
    claims = decode_token(body["access_token"])
    assert claims["type"] == "device"
    assert claims["sub"] == str(device.id)


async def test_device_login_unknown_token(client: AsyncClient, db_session: AsyncSession) -> None:
    response = await client.post("/auth/device/login", json={"device_token": "does-not-exist"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Unbekanntes Gerät.", "code": "INVALID_DEVICE_TOKEN"}
