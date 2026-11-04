import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import HrRole, HrUser, Location, Tenant
from app.services.auth_service import hash_password


async def _create_tenant(db_session: AsyncSession, tenant_id: int, subdomain: str, name: str) -> Tenant:
    tenant = Tenant(id=tenant_id, subdomain=subdomain, name=name)
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


async def _create_hr_user(
    db_session: AsyncSession,
    tenant_id: int | None,
    email: str,
    password: str,
    role: HrRole = HrRole.ADMIN,
) -> HrUser:
    user = HrUser(tenant_id=tenant_id, email=email, password_hash=hash_password(password), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_location(db_session: AsyncSession, tenant_id: int, name: str) -> Location:
    location = Location(tenant_id=tenant_id, name=name, timezone="Europe/Berlin")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def test_hr_user_email_unique_per_tenant_not_globally(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_tenant(db_session, 2, "acme", "Acme GmbH")
    await _create_hr_user(db_session, 1, "hr@example.com", "pw-tenant-1")
    # Dieselbe E-Mail in einem anderen Mandanten muss erlaubt sein (siehe
    # uq_hr_users_tenant_email statt eines globalen Unique-Index).
    await _create_hr_user(db_session, 2, "hr@example.com", "pw-tenant-2")

    response_1 = await client.post(
        "/auth/hr/login", json={"email": "hr@example.com", "password": "pw-tenant-1"}
    )
    assert response_1.status_code == 200

    response_2 = await client.post(
        "/auth/hr/login",
        headers={"X-Tenant-Subdomain": "acme"},
        json={"email": "hr@example.com", "password": "pw-tenant-2"},
    )
    assert response_2.status_code == 200

    # Passwort aus dem falschen Mandanten darf nicht funktionieren.
    response_wrong = await client.post(
        "/auth/hr/login",
        headers={"X-Tenant-Subdomain": "acme"},
        json={"email": "hr@example.com", "password": "pw-tenant-1"},
    )
    assert response_wrong.status_code == 401


async def test_cross_tenant_token_rejected_with_401_not_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_tenant(db_session, 2, "acme", "Acme GmbH")
    await _create_hr_user(db_session, 1, "hr@example.com", "pw-tenant-1")

    login = await client.post(
        "/auth/hr/login", json={"email": "hr@example.com", "password": "pw-tenant-1"}
    )
    token = login.json()["access_token"]

    response = await client.get(
        "/locations",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Subdomain": "acme"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"


async def test_unknown_subdomain_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "debug", False)

    response = await client.get("/locations")

    assert response.status_code == 404
    assert response.json()["code"] == "TENANT_NOT_FOUND"


async def test_dev_tenant_header_ignored_when_debug_false(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _create_tenant(db_session, 2, "acme", "Acme GmbH")
    monkeypatch.setattr(settings, "debug", False)

    response = await client.get("/locations", headers={"X-Tenant-Subdomain": "acme"})

    assert response.status_code == 404
    assert response.json()["code"] == "TENANT_NOT_FOUND"


async def test_locations_are_isolated_between_tenants(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_tenant(db_session, 2, "acme", "Acme GmbH")
    await _create_hr_user(db_session, 1, "admin1@example.com", "pw1", role=HrRole.ADMIN)
    await _create_location(db_session, 1, "Standort Musterfirma")
    await _create_location(db_session, 2, "Standort Acme")

    login = await client.post(
        "/auth/hr/login", json={"email": "admin1@example.com", "password": "pw1"}
    )
    token = login.json()["access_token"]

    response = await client.get("/locations", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert [loc["name"] for loc in response.json()] == ["Standort Musterfirma"]


async def test_super_admin_login_requires_super_admin_host(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session, None, "super@example.com", "super-pw", role=HrRole.SUPER_ADMIN)

    # Normaler Mandanten-Host (hier via Dev-Fallback "musterfirma") darf den
    # Super-Admin nicht einloggen – er ist keinem Tenant zugeordnet.
    on_tenant_host = await client.post(
        "/auth/hr/login", json={"email": "super@example.com", "password": "super-pw"}
    )
    assert on_tenant_host.status_code == 401

    on_super_admin_host = await client.post(
        "/auth/hr/login",
        headers={"Host": settings.super_admin_hostname},
        json={"email": "super@example.com", "password": "super-pw"},
    )
    assert on_super_admin_host.status_code == 200
