from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, EmployeeDefaultShift, HrRole, Account, Location, ShiftTemplate
from app.services.auth_service import hash_password
from app.services.pairing_service import token_hash

_WEEKDAYS_MO_FR = 0b0011111


async def _create_location(db_session: AsyncSession) -> Location:
    location = Location(name="Standort A", timezone="UTC")
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


async def _create_hr_user(db_session: AsyncSession) -> Account:
    user = Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


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


async def _device_token(client: AsyncClient, raw_token: str) -> str:
    response = await client.post("/auth/device/login", json={"device_token": raw_token})
    return response.json()["access_token"]


async def test_hr_can_create_list_update_delete_holiday(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    create_response = await client.post(
        "/holidays",
        headers={"Authorization": f"Bearer {token}"},
        json={"date": "2026-12-25", "name": "1. Weihnachtstag"},
    )
    assert create_response.status_code == 201
    holiday_id = create_response.json()["id"]

    list_response = await client.get("/holidays", headers={"Authorization": f"Bearer {token}"})
    assert len(list_response.json()) == 1

    patch_response = await client.patch(
        f"/holidays/{holiday_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Weihnachten"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Weihnachten"

    delete_response = await client.delete(
        f"/holidays/{holiday_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert delete_response.status_code == 204


async def test_duplicate_holiday_date_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    await client.post(
        "/holidays",
        headers={"Authorization": f"Bearer {token}"},
        json={"date": "2026-12-25", "name": "1. Weihnachtstag"},
    )
    response = await client.post(
        "/holidays",
        headers={"Authorization": f"Bearer {token}"},
        json={"date": "2026-12-25", "name": "Doppelt"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "HOLIDAY_DATE_TAKEN"


async def test_kiosk_can_list_holidays(client: AsyncClient, db_session: AsyncSession) -> None:
    location = await _create_location(db_session)
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    hr_token = await _hr_token(client)
    await client.post(
        "/holidays",
        headers={"Authorization": f"Bearer {hr_token}"},
        json={"date": "2026-12-25", "name": "1. Weihnachtstag"},
    )

    device_token = await _device_token(client, "device-1")
    response = await client.get("/holidays", headers={"Authorization": f"Bearer {device_token}"})

    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_holiday_overrides_timesheet_day_status(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Mitarbeiter ohne jede Schichtplanung (plan_exists=False, siehe
    app/services/shift_planning_service.py): Feiertag zeigt weiterhin
    Ist=0/Soll=None statt einer Gutschrift, da es kein Tagesziel gibt, das
    gutgeschrieben werden könnte – ergänzt
    test_holiday_is_credited_neutrally_instead_of_reducing_target (mit
    zugewiesener Schicht)."""
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    token = await _hr_token(client)

    await client.post(
        "/holidays",
        headers={"Authorization": f"Bearer {token}"},
        json={"date": "2026-08-10", "name": "Testfeiertag"},
    )

    response = await client.get(
        f"/employees/{employee.id}/timesheet?from=2026-08-10&to=2026-08-10",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    day = response.json()[0]
    assert day["status"] == "HOLIDAY"
    assert day["actual_minutes"] == 0


async def test_holiday_is_credited_neutrally_instead_of_reducing_target(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ein Feiertag an einem Arbeitstag reduziert nicht mehr das Wochen-Soll
    (altes Wochenmodell) – er wird pro Tag mit dem vollen Tagesziel neutral
    gutgeschrieben (Ist = Soll, kein negativer Saldo-Effekt), siehe
    app/services/timesheet_service.py calculate_day."""
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location)
    await _create_hr_user(db_session)
    await _assign_default_shift(db_session, employee, target_minutes=480)
    token = await _hr_token(client)

    # Montag dieser Woche (10.8.) ist Feiertag und laut Default-Schicht ein
    # Arbeitstag.
    await client.post(
        "/holidays",
        headers={"Authorization": f"Bearer {token}"},
        json={"date": "2026-08-10", "name": "Testfeiertag"},
    )

    day_response = await client.get(
        f"/employees/{employee.id}/timesheet?from=2026-08-10&to=2026-08-10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert day_response.status_code == 200
    day = day_response.json()[0]
    assert day["status"] == "HOLIDAY"
    assert day["target_minutes"] == 480
    assert day["actual_minutes"] == 480

    week_response = await client.get(
        f"/employees/{employee.id}/weekly-balance?from=2026-08-10&to=2026-08-10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert week_response.status_code == 200
    week = week_response.json()[0]
    assert week["holiday_days"] == 1
    # Wochen-Soll bleibt voll (5 Arbeitstage x 480) – der Feiertag wird nicht
    # mehr heraus-prorata-isiert, sondern pro Tag neutral gutgeschrieben.
    assert week["target_minutes"] == 40 * 60
