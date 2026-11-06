from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BreakRule, HrRole, HrUser
from app.services.auth_service import hash_password


async def _create_hr_user(db_session: AsyncSession, role: HrRole) -> HrUser:
    user = HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=role)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_admin_can_create_list_update_delete_break_rule(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session, HrRole.ADMIN)
    token = await _hr_token(client)
    # Ohne Gesetzesschutz darf die Staffel auch ganz leer werden (z.B. Tarifvertrag).
    assert (await client.patch("/settings", headers={"Authorization": f"Bearer {token}"}, json={"legal_break_minimum": False})).status_code == 200

    create_response = await client.post(
        "/break-rules",
        headers={"Authorization": f"Bearer {token}"},
        json={"min_work_minutes": 360, "deduct_minutes": 30},
    )
    assert create_response.status_code == 201
    rule_id = create_response.json()["id"]

    list_response = await client.get("/break-rules", headers={"Authorization": f"Bearer {token}"})
    assert len(list_response.json()) == 1

    patch_response = await client.patch(
        f"/break-rules/{rule_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"deduct_minutes": 45},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["deduct_minutes"] == 45
    assert patch_response.json()["min_work_minutes"] == 360

    delete_response = await client.delete(
        f"/break-rules/{rule_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert delete_response.status_code == 204

    list_after = await client.get("/break-rules", headers={"Authorization": f"Bearer {token}"})
    assert list_after.json() == []


async def test_hr_role_cannot_manage_break_rules(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session, HrRole.HR)
    token = await _hr_token(client)

    response = await client.post(
        "/break-rules",
        headers={"Authorization": f"Bearer {token}"},
        json={"min_work_minutes": 360, "deduct_minutes": 30},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ADMIN_PERMISSION_REQUIRED"


async def test_update_missing_break_rule_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session, HrRole.ADMIN)
    token = await _hr_token(client)

    response = await client.patch(
        "/break-rules/999",
        headers={"Authorization": f"Bearer {token}"},
        json={"deduct_minutes": 45},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "BREAK_RULE_NOT_FOUND"
