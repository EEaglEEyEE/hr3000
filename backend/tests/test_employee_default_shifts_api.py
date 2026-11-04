from datetime import time

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, HrUser, Location, ShiftTemplate
from app.services.auth_service import hash_password

_MO_FR = 0b0011111


async def _create_employee(db_session: AsyncSession) -> Employee:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    employee = Employee(
        location_id=location.id, first_name="Max", last_name="Mustermann", employee_number="EMP-1", active=True
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_template(db_session: AsyncSession, name: str, start: time | None, end: time | None) -> ShiftTemplate:
    template = ShiftTemplate(name=name, start_time=start, end_time=end, target_minutes=480)
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


async def _create_admin_hr_user(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_create_default_shift_closes_open_previous_period(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_employee(db_session)
    template = await _create_template(db_session, "Frueh", time(6, 0), time(14, 0))
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    first = await client.post(
        f"/employees/{employee.id}/default-shifts",
        headers={"Authorization": f"Bearer {token}"},
        json={"shift_template_id": template.id, "valid_from": "2026-01-01", "weekdays_mask": _MO_FR},
    )
    assert first.status_code == 201
    assert first.json()["valid_to"] is None

    second = await client.post(
        f"/employees/{employee.id}/default-shifts",
        headers={"Authorization": f"Bearer {token}"},
        json={"shift_template_id": template.id, "valid_from": "2026-06-01", "weekdays_mask": _MO_FR},
    )
    assert second.status_code == 201

    list_response = await client.get(
        f"/employees/{employee.id}/default-shifts", headers={"Authorization": f"Bearer {token}"}
    )
    by_valid_from = {row["valid_from"]: row for row in list_response.json()}
    assert by_valid_from["2026-01-01"]["valid_to"] == "2026-05-31"
    assert by_valid_from["2026-06-01"]["valid_to"] is None


async def test_create_default_shift_rejects_overlap(client: AsyncClient, db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    template = await _create_template(db_session, "Frueh", time(6, 0), time(14, 0))
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    await client.post(
        f"/employees/{employee.id}/default-shifts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "shift_template_id": template.id,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "weekdays_mask": _MO_FR,
        },
    )

    overlapping = await client.post(
        f"/employees/{employee.id}/default-shifts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "shift_template_id": template.id,
            "valid_from": "2026-06-01",
            "valid_to": "2026-06-30",
            "weekdays_mask": _MO_FR,
        },
    )
    assert overlapping.status_code == 400
    assert overlapping.json()["code"] == "OVERLAPPING_PERIOD"


async def test_create_default_shift_rejects_rest_period_violation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_employee(db_session)
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    # 06:00-22:00 an aufeinanderfolgenden Tagen wäre nur 8h Ruhezeit – seit
    # Einführung von check_max_daily_working_time (ArbZG §3, siehe
    # test_create_default_shift_rejects_max_daily_working_time) greift bei
    # einer einzelnen, jeden Tag identisch wiederholten Schicht aber IMMER
    # zuerst die 10h-Grenze, sobald der Ruhezeit-Verstoß rein rechnerisch
    # möglich wäre (Lücke = 24h - Schichtdauer, also < 11h nur ab > 13h
    # Schichtdauer). Dieser Test deckt daher den ANDEREN Pfad von
    # check_rest_period_for_default ab: die Grenzprüfung gegen eine bereits
    # bestehende, endende Zuordnung (day_before/day_after), bei der zwei
    # unterschiedliche, je für sich zulässige (≤10h) Vorlagen aufeinandertreffen.
    all_days = 0b1111111
    late_shift = await _create_template(db_session, "Spaet", time(13, 0), time(23, 0))
    early_shift = await _create_template(db_session, "Frueh", time(6, 0), time(14, 0))

    first = await client.post(
        f"/employees/{employee.id}/default-shifts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "shift_template_id": late_shift.id,
            "valid_from": "2026-01-01",
            "valid_to": "2026-01-31",
            "weekdays_mask": all_days,
        },
    )
    assert first.status_code == 201

    response = await client.post(
        f"/employees/{employee.id}/default-shifts",
        headers={"Authorization": f"Bearer {token}"},
        json={"shift_template_id": early_shift.id, "valid_from": "2026-02-01", "weekdays_mask": all_days},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "REST_PERIOD_VIOLATION"


async def test_create_default_shift_rejects_max_daily_working_time(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee = await _create_employee(db_session)
    # 06:00-22:00 = 16 Stunden, überschreitet die ArbZG-§3-Höchstgrenze von
    # 10 Stunden/Tag deutlich.
    long_shift = await _create_template(db_session, "Lang", time(6, 0), time(22, 0))
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    response = await client.post(
        f"/employees/{employee.id}/default-shifts",
        headers={"Authorization": f"Bearer {token}"},
        json={"shift_template_id": long_shift.id, "valid_from": "2026-01-01", "weekdays_mask": _MO_FR},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "MAX_DAILY_WORKING_TIME_EXCEEDED"


async def test_delete_default_shift(client: AsyncClient, db_session: AsyncSession) -> None:
    employee = await _create_employee(db_session)
    template = await _create_template(db_session, "Frueh", time(6, 0), time(14, 0))
    await _create_admin_hr_user(db_session)
    token = await _token(client)

    create_response = await client.post(
        f"/employees/{employee.id}/default-shifts",
        headers={"Authorization": f"Bearer {token}"},
        json={"shift_template_id": template.id, "valid_from": "2026-01-01", "weekdays_mask": _MO_FR},
    )
    default_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/employees/{employee.id}/default-shifts/{default_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_response.status_code == 204
