"""Werkzeug "Super-Admin-Passwort vergessen" (app/tools/reset_super_admin_password.py)."""

import pytest

from app.config import settings
from app.models import HrRole, HrUser
from app.services.auth_service import hash_password, verify_password
from app.tools.reset_super_admin_password import reset_super_admin_password


async def test_reset_sets_new_password_that_works_for_login(client, db_session, monkeypatch):
    db_session.add(
        HrUser(tenant_id=None, email="chef@example.com", password_hash=hash_password("alt"), role=HrRole.SUPER_ADMIN)
    )
    # Ein Mandanten-Admin mit gleicher Rolle-Bezeichnung darf nicht betroffen sein.
    db_session.add(HrUser(email="admin@example.com", password_hash=hash_password("bleibt"), role=HrRole.ADMIN))
    await db_session.commit()

    email, password = await reset_super_admin_password(db_session)
    assert email == "chef@example.com"
    assert len(password) >= 20

    admin_host = {"Host": settings.super_admin_hostname}
    old = await client.post("/auth/hr/login", json={"email": email, "password": "alt"}, headers=admin_host)
    assert old.status_code == 401
    new = await client.post("/auth/hr/login", json={"email": email, "password": password}, headers=admin_host)
    assert new.status_code == 200, new.text

    tenant_admin = (await db_session.execute(HrUser.__table__.select().where(HrUser.email == "admin@example.com"))).one()
    assert verify_password("bleibt", tenant_admin.password_hash)


async def test_each_reset_creates_a_different_password(db_session):
    db_session.add(HrUser(tenant_id=None, email="chef@example.com", password_hash=hash_password("x"), role=HrRole.SUPER_ADMIN))
    await db_session.commit()
    _, first = await reset_super_admin_password(db_session)
    _, second = await reset_super_admin_password(db_session)
    assert first != second


async def test_refuses_without_exactly_one_super_admin(db_session):
    with pytest.raises(RuntimeError, match="gefunden: 0"):
        await reset_super_admin_password(db_session)
    db_session.add_all(
        [
            HrUser(tenant_id=None, email="a@example.com", password_hash=hash_password("x"), role=HrRole.SUPER_ADMIN),
            HrUser(tenant_id=None, email="b@example.com", password_hash=hash_password("x"), role=HrRole.SUPER_ADMIN),
        ]
    )
    await db_session.commit()
    with pytest.raises(RuntimeError, match="gefunden: 2"):
        await reset_super_admin_password(db_session)
