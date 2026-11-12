from datetime import date, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceType,
    BreakRule,
    Device,
    Employee,
    EmployeeDefaultShift,
    HrRole,
    Account,
    Location,
    ShiftTemplate,
)
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings
from app.services.pairing_service import token_hash

_WEEKDAYS_MO_FR = 0b0011111


async def _seed_break_rules(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            BreakRule(min_work_minutes=360, deduct_minutes=30),
            BreakRule(min_work_minutes=540, deduct_minutes=45),
        ]
    )
    await db_session.commit()


async def _create_location(db_session: AsyncSession, timezone: str = "UTC") -> Location:
    location = Location(name="Standort A", timezone=timezone)
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(db_session: AsyncSession, location: Location) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Mustermann",
        employee_number="EMP-1",
        active=True,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_device(db_session: AsyncSession, location: Location, token: str) -> Device:
    device = Device(location_id=location.id, token_hash=token_hash(token), name="Kiosk A1")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


async def _assign_default_shift(db_session: AsyncSession, employee: Employee, target_minutes: int) -> None:
    template = ShiftTemplate(name="Normalschicht", target_minutes=target_minutes)
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    db_session.add(
        EmployeeDefaultShift(
            employee_id=employee.id,
            shift_template_id=template.id,
            valid_from=date(2026, 1, 1),
            weekdays_mask=_WEEKDAYS_MO_FR,
        )
    )
    await db_session.commit()


async def _create_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _device_token(client: AsyncClient, raw_token: str) -> str:
    response = await client.post("/auth/device/login", json={"device_token": raw_token})
    return response.json()["access_token"]


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_timesheet_reports_complete_and_open_days(
    client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(datetime(2026, 8, 11, 10, 0))  # Schicht läuft noch (innerhalb der maximalen Schichtlänge)
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    await _seed_break_rules(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)

    device_token = await _device_token(client, "device-1")
    hr_token = await _hr_token(client)

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T14:00:00Z",
            "idempotency_key": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        },
    )
    # Dienstag: nur COME gestempelt, noch kein späterer Tag mit Buchung -> PRESENT
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-11T06:00:00Z",
            "idempotency_key": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        },
    )
    # Mittwoch wird schon wieder gestempelt -> Dienstag ist jetzt tatsächlich
    # ein vergessener Punch-Out, kein "gerade anwesend" mehr.
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-12T06:00:00Z",
            "idempotency_key": "dddddddd-dddd-dddd-dddd-dddddddddddd",
        },
    )

    response = await client.get(
        f"/employees/{employee.id}/timesheet?from=2026-08-10&to=2026-08-12",
        headers={"Authorization": f"Bearer {hr_token}"},
    )

    assert response.status_code == 200
    days = response.json()
    assert days[0]["work_date"] == "2026-08-10"
    assert days[0]["status"] == "COMPLETE"
    assert days[0]["actual_minutes"] == 480 - 30
    assert days[0]["target_minutes"] == 480  # aus der zugewiesenen Schicht-Vorlage
    assert days[1]["work_date"] == "2026-08-11"
    assert days[1]["status"] == "OPEN_MISSING_PUNCH"
    assert days[1]["actual_minutes"] is None
    assert days[2]["work_date"] == "2026-08-12"
    assert days[2]["status"] == "PRESENT"
    assert days[2]["actual_minutes"] is None


async def test_weekly_balance_reports_week_totals(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    await _seed_break_rules(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)
    device_token = await _device_token(client, "device-1")
    hr_token = await _hr_token(client)

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "ffffffff-ffff-ffff-ffff-ffffffffffff",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T14:00:00Z",
            "idempotency_key": "99999999-9999-9999-9999-999999999999",
        },
    )

    response = await client.get(
        f"/employees/{employee.id}/weekly-balance?from=2026-08-10&to=2026-08-10",
        headers={"Authorization": f"Bearer {hr_token}"},
    )

    assert response.status_code == 200
    weeks = response.json()
    assert len(weeks) == 1
    assert weeks[0]["week_start"] == "2026-08-10"
    assert weeks[0]["week_end"] == "2026-08-16"
    assert weeks[0]["target_minutes"] == 40 * 60
    assert weeks[0]["actual_minutes"] == 480 - 30
    assert weeks[0]["delta_minutes"] == (480 - 30) - 40 * 60
    assert weeks[0]["absence_days"] == 0


async def test_timesheet_rejects_invalid_range(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    hr_token = await _hr_token(client)

    response = await client.get(
        f"/employees/{employee.id}/timesheet?from=2026-08-11&to=2026-08-10",
        headers={"Authorization": f"Bearer {hr_token}"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_RANGE"


async def test_overtime_balance_defaults_to_zero_without_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    hr_token = await _hr_token(client)

    response = await client.get(
        f"/employees/{employee.id}/overtime-balance",
        headers={"Authorization": f"Bearer {hr_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "employee_id": employee.id,
        "balance_date": None,
        "daily_target_minutes": None,
        "daily_actual_minutes": None,
        "daily_delta_minutes": None,
        "running_balance_minutes": 0,
        "adjustment_minutes": 0,
        "balance_start": None,
        "settled_limit_minutes": None,
        "settled_month_minutes": 0,
    }


async def test_kiosk_can_read_balance_for_own_location_employee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_device(db_session, location, "device-1")
    await _seed_break_rules(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)
    employee.termination_date = date(2026, 8, 10)  # Konto endet am Testtag (datumsunabhängig)
    await db_session.commit()
    device_token = await _device_token(client, "device-1")

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "dddddddd-dddd-dddd-dddd-dddddddddddd",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T14:00:00Z",
            "idempotency_key": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        },
    )

    response = await client.get(
        f"/employees/{employee.id}/overtime-balance",
        headers={"Authorization": f"Bearer {device_token}"},
    )

    assert response.status_code == 200
    # Saldo ist jetzt tagesgenau (siehe app/services/timesheet_service.py) –
    # spiegelt nur das Ziel dieses einen Tages, nicht mehr die ganze Woche.
    assert response.json()["running_balance_minutes"] == (480 - 30) - 480


async def test_kiosk_cannot_read_balance_for_other_location_employee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location_a = await _create_location(db_session)
    location_b = await _create_location(db_session)
    employee_b = await _create_employee(db_session, location_b)
    await _create_device(db_session, location_a, "device-a")
    device_token = await _device_token(client, "device-a")

    response = await client.get(
        f"/employees/{employee_b.id}/overtime-balance",
        headers={"Authorization": f"Bearer {device_token}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "EMPLOYEE_NOT_FOUND"


async def test_timesheet_reports_absence_days_with_type(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    hr_user = await _create_hr_user(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)
    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.VACATION,
            date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 10),
            created_by_account_id=hr_user.id,
        )
    )
    await db_session.commit()
    hr_token = await _hr_token(client)

    response = await client.get(
        f"/employees/{employee.id}/timesheet?from=2026-08-10&to=2026-08-10",
        headers={"Authorization": f"Bearer {hr_token}"},
    )

    assert response.status_code == 200
    day = response.json()[0]
    assert day["status"] == "ABSENCE"
    assert day["absence_type"] == "VACATION"
    # Genehmigte Absenz an einem Arbeitstag wird neutral mit dem vollen
    # Tagesziel gutgeschrieben (kein negativer Saldo-Effekt), siehe
    # app/services/timesheet_service.py calculate_day.
    assert day["target_minutes"] == 480
    assert day["actual_minutes"] == 480


async def test_timesheet_marks_birthday_when_enabled_globally_and_per_employee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    employee.birth_date = date(1990, 8, 10)
    await _create_hr_user(db_session)
    settings_row = await get_or_create_settings(db_session, employee.tenant_id)
    settings_row.show_birthdays_in_calendar = True
    await db_session.commit()
    hr_token = await _hr_token(client)

    response = await client.get(
        f"/employees/{employee.id}/timesheet?from=2026-08-09&to=2026-08-11",
        headers={"Authorization": f"Bearer {hr_token}"},
    )

    assert response.status_code == 200
    days = {day["work_date"]: day["is_birthday"] for day in response.json()}
    assert days["2026-08-09"] is False
    assert days["2026-08-10"] is True
    assert days["2026-08-11"] is False


async def test_timesheet_hides_birthday_when_employee_disabled_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    employee.birth_date = date(1990, 8, 10)
    employee.show_birthday_in_calendar = False
    await _create_hr_user(db_session)
    settings_row = await get_or_create_settings(db_session, employee.tenant_id)
    settings_row.show_birthdays_in_calendar = True
    await db_session.commit()
    hr_token = await _hr_token(client)

    response = await client.get(
        f"/employees/{employee.id}/timesheet?from=2026-08-10&to=2026-08-10",
        headers={"Authorization": f"Bearer {hr_token}"},
    )

    assert response.json()[0]["is_birthday"] is False


async def test_timesheet_hides_birthday_when_global_toggle_off(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    employee.birth_date = date(1990, 8, 10)
    await _create_hr_user(db_session)
    await db_session.commit()
    hr_token = await _hr_token(client)

    # show_birthdays_in_calendar ist per Default False (siehe AppSettings) –
    # kein expliziter Settings-Zugriff nötig, um das zu testen.
    response = await client.get(
        f"/employees/{employee.id}/timesheet?from=2026-08-10&to=2026-08-10",
        headers={"Authorization": f"Bearer {hr_token}"},
    )

    assert response.json()[0]["is_birthday"] is False


async def test_timesheet_flags_day_exceeding_max_daily_working_time(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    hr_token = await _hr_token(client)

    # 11 Stunden gross (keine Pausenregeln geseedet, daher keine Kürzung) –
    # überschreitet die ArbZG-§3-Grenze von 10 Stunden/Tag.
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {hr_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "bbbbbbbb-1111-1111-1111-111111111111",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {hr_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T17:00:00Z",
            "idempotency_key": "bbbbbbbb-2222-2222-2222-222222222222",
        },
    )

    response = await client.get(
        f"/employees/{employee.id}/timesheet?from=2026-08-10&to=2026-08-10",
        headers={"Authorization": f"Bearer {hr_token}"},
    )

    day = response.json()[0]
    assert day["actual_minutes"] == 660
    assert day["exceeds_max_daily_minutes"] is True


async def test_timesheet_does_not_flag_day_within_max_daily_working_time(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    hr_token = await _hr_token(client)

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {hr_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "cccccccc-1111-1111-1111-111111111111",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {hr_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T14:00:00Z",
            "idempotency_key": "cccccccc-2222-2222-2222-222222222222",
        },
    )

    response = await client.get(
        f"/employees/{employee.id}/timesheet?from=2026-08-10&to=2026-08-10",
        headers={"Authorization": f"Bearer {hr_token}"},
    )

    day = response.json()[0]
    assert day["actual_minutes"] == 480
    assert day["exceeds_max_daily_minutes"] is False
