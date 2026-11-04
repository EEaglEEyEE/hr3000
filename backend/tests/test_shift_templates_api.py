from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HrRole, HrUser
from app.services.auth_service import hash_password


async def _create_admin_hr_user(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_admin_can_create_and_update_shift_template(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    create_response = await client.post(
        "/shift-templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Frühschicht", "start_time": "06:00:00", "end_time": "14:00:00", "target_minutes": 480},
    )
    assert create_response.status_code == 201
    template_id = create_response.json()["id"]
    assert create_response.json()["start_time"] == "06:00:00"

    update_response = await client.patch(
        f"/shift-templates/{template_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"target_minutes": 450},
    )
    assert update_response.status_code == 200
    assert update_response.json()["target_minutes"] == 450


async def test_shift_template_target_period_defaults_to_daily_and_is_configurable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    create_response = await client.post(
        "/shift-templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Gleitzeit", "target_minutes": 2340},
    )
    assert create_response.status_code == 201
    template_id = create_response.json()["id"]
    assert create_response.json()["target_period"] == "DAILY"

    update_response = await client.patch(
        f"/shift-templates/{template_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"target_period": "WEEKLY"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["target_period"] == "WEEKLY"
    # target_minutes bleibt beim reinen Typwechsel unverändert.
    assert update_response.json()["target_minutes"] == 2340


async def test_duplicate_shift_template_name_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    payload = {"name": "Frühschicht", "target_minutes": 480}
    first = await client.post(
        "/shift-templates", headers={"Authorization": f"Bearer {token}"}, json=payload
    )
    assert first.status_code == 201

    second = await client.post(
        "/shift-templates", headers={"Authorization": f"Bearer {token}"}, json=payload
    )
    assert second.status_code == 409
    assert second.json()["code"] == "NAME_TAKEN"


async def test_delete_shift_template(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    create_response = await client.post(
        "/shift-templates",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Frühschicht", "target_minutes": 480},
    )
    template_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/shift-templates/{template_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert delete_response.status_code == 204

    list_response = await client.get("/shift-templates", headers={"Authorization": f"Bearer {token}"})
    assert list_response.json() == []
