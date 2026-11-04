from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HrRole, HrUser
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


async def test_settings_default_to_pin_not_required(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session, HrRole.ADMIN)
    token = await _hr_token(client)

    response = await client.get("/settings", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "require_pin_for_punch": False,
        "vacation_approval_required": False,
        "default_bundesland": None,
        "default_annual_vacation_days": 0.0,
        "show_birthdays_in_calendar": False,
        # Test-Mandant wird in conftest.py mit aktiver Schichtplanung angelegt.
        "shift_planning_enabled": True,
        "balance_start_date": None,
        "default_auto_break": True,
        "default_show_birthday": True,
        "default_day_minutes": None,
        "prorate_part_time_vacation": True,
        "vacation_carry_over_auto": False,
        "vacation_carry_over_max_days": None,
        "vacation_carry_over_expiry": None,
        "disabled_day_flags": [],
        "max_shift_span_hours": 16,
        "kiosk_admin_pin_set": False,
        "rfid_required": False,
        "kiosk_rfid_enabled": True,
        "kiosk_card_self_registration": True,
        "kiosk_pin_self_setup": True,
        "kiosk_show_balance": True,
        "kiosk_show_vacation": True,
        "kiosk_break_buttons": True,
        "kiosk_errand_buttons": False,
        "portal_punching_enabled": False,
        "absence_requests_enabled": True,
        "core_time_start": None,
        "core_time_end": None,
        "punctuality_check": False,
        "late_tolerance_minutes": 5,
        "flex_frame_start": None,
        "flex_frame_end": None,
        "kiosk_greeting": None,
        "kiosk_sort": "LAST_NAME",
        "kiosk_theme": "DARK",
        "kiosk_screen_on_from": None,
        "kiosk_screen_on_until": None,
        "smtp_host": None,
        "smtp_port": 587,
        "smtp_user": None,
        "smtp_from": None,
        "smtp_security": "STARTTLS",
        "smtp_password_set": False,
        "email_notifications_enabled": True,
    }


async def test_admin_can_toggle_require_pin_for_punch(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session, HrRole.ADMIN)
    token = await _hr_token(client)

    patch_response = await client.patch(
        "/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"require_pin_for_punch": True},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["require_pin_for_punch"] is True

    get_response = await client.get("/settings", headers={"Authorization": f"Bearer {token}"})
    assert get_response.json()["require_pin_for_punch"] is True


async def test_admin_can_set_default_bundesland(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session, HrRole.ADMIN)
    token = await _hr_token(client)

    patch_response = await client.patch(
        "/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"default_bundesland": "BY"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["default_bundesland"] == "BY"

    get_response = await client.get("/settings", headers={"Authorization": f"Bearer {token}"})
    assert get_response.json()["default_bundesland"] == "BY"


async def test_admin_can_set_default_annual_vacation_days(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session, HrRole.ADMIN)
    token = await _hr_token(client)

    patch_response = await client.patch(
        "/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"default_annual_vacation_days": 30},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["default_annual_vacation_days"] == 30.0

    get_response = await client.get("/settings", headers={"Authorization": f"Bearer {token}"})
    assert get_response.json()["default_annual_vacation_days"] == 30.0


async def test_admin_can_toggle_show_birthdays_in_calendar(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session, HrRole.ADMIN)
    token = await _hr_token(client)

    patch_response = await client.patch(
        "/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"show_birthdays_in_calendar": True},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["show_birthdays_in_calendar"] is True

    get_response = await client.get("/settings", headers={"Authorization": f"Bearer {token}"})
    assert get_response.json()["show_birthdays_in_calendar"] is True


async def test_hr_role_cannot_read_or_change_settings(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session, HrRole.HR)
    token = await _hr_token(client)

    get_response = await client.get("/settings", headers={"Authorization": f"Bearer {token}"})
    assert get_response.status_code == 403
    assert get_response.json()["code"] == "ADMIN_PERMISSION_REQUIRED"

    patch_response = await client.patch(
        "/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"require_pin_for_punch": True},
    )
    assert patch_response.status_code == 403


async def test_kiosk_screen_hours_set_clear_and_validate(client: AsyncClient, db_session: AsyncSession) -> None:
    """Bildschirmzeiten am Tablet: beide Zeiten zusammen, nicht gleich, leeren = immer an, im Audit-Log."""
    await _create_hr_user(db_session, HrRole.ADMIN)
    headers = {"Authorization": f"Bearer {await _hr_token(client)}"}

    r = await client.patch("/settings", headers=headers, json={"kiosk_screen_on_from": "06:00", "kiosk_screen_on_until": "21:00"})
    assert r.status_code == 200, r.text
    assert (r.json()["kiosk_screen_on_from"], r.json()["kiosk_screen_on_until"]) == ("06:00:00", "21:00:00")
    # über Mitternacht ist erlaubt
    r = await client.patch("/settings", headers=headers, json={"kiosk_screen_on_from": "22:00", "kiosk_screen_on_until": "06:00"})
    assert r.status_code == 200 and r.json()["kiosk_screen_on_from"] == "22:00:00"

    for body in (
        {"kiosk_screen_on_from": "06:00"},
        {"kiosk_screen_on_until": "21:00"},
        {"kiosk_screen_on_from": "08:00", "kiosk_screen_on_until": "08:00"},
        {"kiosk_screen_on_from": "25:00", "kiosk_screen_on_until": "21:00"},
        {"kiosk_screen_on_from": "früh", "kiosk_screen_on_until": "21:00"},
    ):
        assert (await client.patch("/settings", headers=headers, json=body)).status_code == 422, body
    # unverändert nach den abgelehnten Versuchen
    assert (await client.get("/settings", headers=headers)).json()["kiosk_screen_on_from"] == "22:00:00"

    r = await client.patch("/settings", headers=headers, json={"clear_kiosk_screen_hours": True})
    assert r.status_code == 200 and r.json()["kiosk_screen_on_from"] is None and r.json()["kiosk_screen_on_until"] is None

    entries = (await client.get("/audit-log", headers=headers)).json()
    details = " | ".join(e.get("detail") or "" for e in entries)
    assert "kiosk_screen_hours=06:00-21:00" in details and "kiosk_screen_hours=immer an" in details


async def test_hr_role_cannot_change_kiosk_screen_hours(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session, HrRole.SUPERVISOR)
    headers = {"Authorization": f"Bearer {await _hr_token(client)}"}
    r = await client.patch("/settings", headers=headers, json={"kiosk_screen_on_from": "06:00", "kiosk_screen_on_until": "21:00"})
    assert r.status_code == 403
