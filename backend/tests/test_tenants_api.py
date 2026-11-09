from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import HrRole, Account
from app.services.auth_service import hash_password


async def _create_super_admin(db_session: AsyncSession, email: str, password: str) -> Account:
    user = Account(tenant_id=None, email=email, password_hash=hash_password(password), role=HrRole.SUPER_ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _super_admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    await _create_super_admin(db_session, "super@example.com", "super-pw")
    login = await client.post(
        "/auth/login",
        headers={"Host": settings.super_admin_hostname},
        json={"email": "super@example.com", "password": "super-pw"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


async def test_create_tenant_bootstraps_admin_with_working_login(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _super_admin_token(client, db_session)

    response = await client.post(
        "/tenants",
        headers={"Authorization": f"Bearer {token}", "Host": settings.super_admin_hostname},
        json={"subdomain": "acme", "name": "Acme GmbH", "admin_email": "admin@acme.example"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["admin_email"] == "admin@acme.example"
    assert isinstance(body["initial_admin_password"], str) and len(body["initial_admin_password"]) > 0

    login = await client.post(
        "/auth/login",
        headers={"X-Tenant-Subdomain": "acme"},
        json={"email": "admin@acme.example", "password": body["initial_admin_password"]},
    )
    assert login.status_code == 200


async def test_create_tenant_duplicate_subdomain_conflicts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _super_admin_token(client, db_session)
    headers = {"Authorization": f"Bearer {token}", "Host": settings.super_admin_hostname}

    first = await client.post(
        "/tenants",
        headers=headers,
        json={"subdomain": "acme", "name": "Acme GmbH", "admin_email": "admin@acme.example"},
    )
    assert first.status_code == 201

    second = await client.post(
        "/tenants",
        headers=headers,
        json={"subdomain": "acme", "name": "Andere GmbH", "admin_email": "other@acme.example"},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "SUBDOMAIN_TAKEN"


async def test_reset_admin_password_issues_new_working_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _super_admin_token(client, db_session)
    headers = {"Authorization": f"Bearer {token}", "Host": settings.super_admin_hostname}

    create = await client.post(
        "/tenants",
        headers=headers,
        json={"subdomain": "acme", "name": "Acme GmbH", "admin_email": "admin@acme.example"},
    )
    tenant_id = create.json()["id"]
    old_password = create.json()["initial_admin_password"]

    reset = await client.post(f"/tenants/{tenant_id}/reset-admin-password", headers=headers)
    assert reset.status_code == 200
    reset_body = reset.json()
    assert reset_body["admin_email"] == "admin@acme.example"
    new_password = reset_body["new_password"]
    assert new_password != old_password

    old_login = await client.post(
        "/auth/login",
        headers={"X-Tenant-Subdomain": "acme"},
        json={"email": "admin@acme.example", "password": old_password},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/auth/login",
        headers={"X-Tenant-Subdomain": "acme"},
        json={"email": "admin@acme.example", "password": new_password},
    )
    assert new_login.status_code == 200


async def test_reset_admin_password_unknown_tenant_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _super_admin_token(client, db_session)
    response = await client.post(
        "/tenants/999999/reset-admin-password",
        headers={"Authorization": f"Bearer {token}", "Host": settings.super_admin_hostname},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "TENANT_NOT_FOUND"


async def test_update_admin_email_changes_login(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _super_admin_token(client, db_session)
    headers = {"Authorization": f"Bearer {token}", "Host": settings.super_admin_hostname}

    create = await client.post(
        "/tenants",
        headers=headers,
        json={"subdomain": "acme", "name": "Acme GmbH", "admin_email": "admin@acme.example"},
    )
    tenant_id = create.json()["id"]
    password = create.json()["initial_admin_password"]

    update = await client.patch(
        f"/tenants/{tenant_id}/admin-email",
        headers=headers,
        json={"new_email": "new-admin@acme.example"},
    )
    assert update.status_code == 200
    assert update.json()["admin_email"] == "new-admin@acme.example"

    old_login = await client.post(
        "/auth/login",
        headers={"X-Tenant-Subdomain": "acme"},
        json={"email": "admin@acme.example", "password": password},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/auth/login",
        headers={"X-Tenant-Subdomain": "acme"},
        json={"email": "new-admin@acme.example", "password": password},
    )
    assert new_login.status_code == 200


async def test_update_admin_email_conflicts_with_existing_email_in_same_tenant(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _super_admin_token(client, db_session)
    headers = {"Authorization": f"Bearer {token}", "Host": settings.super_admin_hostname}

    create = await client.post(
        "/tenants",
        headers=headers,
        json={"subdomain": "acme", "name": "Acme GmbH", "admin_email": "admin@acme.example"},
    )
    tenant_id = create.json()["id"]

    db_session.add(
        Account(
            tenant_id=tenant_id,
            email="hr@acme.example",
            password_hash=hash_password("pw"),
            role=HrRole.HR,
        )
    )
    await db_session.commit()

    response = await client.patch(
        f"/tenants/{tenant_id}/admin-email",
        headers=headers,
        json={"new_email": "hr@acme.example"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "EMAIL_TAKEN"


async def test_update_admin_email_unknown_tenant_404(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _super_admin_token(client, db_session)
    response = await client.patch(
        "/tenants/999999/admin-email",
        headers={"Authorization": f"Bearer {token}", "Host": settings.super_admin_hostname},
        json={"new_email": "someone@example.com"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "TENANT_NOT_FOUND"


async def test_reset_admin_password_tenant_without_admin_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Tenant 1 (Musterfirma, per conftest-Seed) hat keinen Account-Admin –
    # Erikas Admin-Zugang läuft über Employee.hr_role, nicht über Account.
    token = await _super_admin_token(client, db_session)
    response = await client.post(
        "/tenants/1/reset-admin-password",
        headers={"Authorization": f"Bearer {token}", "Host": settings.super_admin_hostname},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "ADMIN_NOT_FOUND"
