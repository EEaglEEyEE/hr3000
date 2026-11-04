from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, Employee, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _create_location(db_session: AsyncSession, name: str = "Standort A") -> Location:
    location = Location(name=name, timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


async def _create_employee(db_session: AsyncSession, location: Location, number: str) -> Employee:
    employee = Employee(
        location_id=location.id,
        first_name="Max",
        last_name="Mustermann",
        employee_number=number,
        active=True,
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _create_device(db_session: AsyncSession, location: Location, token: str) -> Device:
    device = Device(location_id=location.id, device_token=token, name="Kiosk A1")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


async def _create_hr_user(db_session: AsyncSession) -> HrUser:
    user = HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _device_token(client: AsyncClient, raw_token: str) -> str:
    response = await client.post("/auth/device/login", json={"device_token": raw_token})
    return response.json()["access_token"]


async def _hr_token(client: AsyncClient) -> str:
    response = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    return response.json()["access_token"]


async def test_open_day_appears_after_incomplete_punch(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, "EMP-1")
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    device_token = await _device_token(client, "device-1")
    hr_token = await _hr_token(client)

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "11111111-1111-1111-1111-111111111111",
        },
    )
    # Am Folgetag wird schon wieder gestempelt -> der 10.8. wurde offensichtlich
    # vergessen abzuschließen (sonst wäre es nur "gerade anwesend", siehe
    # test_calculate_day_open_come_without_later_punch_is_present).
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-11T06:00:00Z",
            "idempotency_key": "11111111-1111-1111-1111-111111111112",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-11T14:00:00Z",
            "idempotency_key": "11111111-1111-1111-1111-111111111113",
        },
    )

    response = await client.get(
        "/timesheet/open-days", headers={"Authorization": f"Bearer {hr_token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["employee_id"] == employee.id
    assert body[0]["work_date"] == "2026-08-10"


async def test_open_day_disappears_once_completed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, "EMP-1")
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    device_token = await _device_token(client, "device-1")
    hr_token = await _hr_token(client)

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "22222222-2222-2222-2222-222222222222",
        },
    )
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T14:00:00Z",
            "idempotency_key": "33333333-3333-3333-3333-333333333333",
        },
    )

    response = await client.get(
        "/timesheet/open-days", headers={"Authorization": f"Bearer {hr_token}"}
    )

    assert response.json() == []


async def test_open_day_appears_for_error_status(client: AsyncClient, db_session: AsyncSession) -> None:
    """Eine widersprüchliche Buchungsfolge (ERROR) muss ebenfalls in "Zu klären"
    auftauchen, nicht nur eine schlicht offene Buchung (OPEN_MISSING_PUNCH)."""
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, "EMP-1")
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    device_token = await _device_token(client, "device-1")
    hr_token = await _hr_token(client)

    # Gehen ohne vorheriges Kommen -> widersprüchlich (ERROR).
    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "GO",
            "timestamp_utc": "2026-08-10T14:00:00Z",
            "idempotency_key": "77777777-7777-7777-7777-777777777777",
        },
    )

    response = await client.get(
        "/timesheet/open-days", headers={"Authorization": f"Bearer {hr_token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["employee_id"] == employee.id
    assert body[0]["work_date"] == "2026-08-10"


async def test_punch_during_absence_is_to_be_clarified(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stempeln an einem Urlaubstag ist ein Widerspruch: der Tag zeigt Anwesenheit,
    erscheint aber unter "Zu klären" (Grund WORK_DURING_ABSENCE)."""
    from datetime import date

    from app.models import Absence, AbsenceType

    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, "EMP-1")
    await _create_device(db_session, location, "device-1")
    hr_user = await _create_hr_user(db_session)
    db_session.add(
        Absence(
            employee_id=employee.id,
            type=AbsenceType.VACATION,
            date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 10),
            created_by=hr_user.id,
        )
    )
    await db_session.commit()
    device_token = await _device_token(client, "device-1")
    hr_token = await _hr_token(client)

    await client.post(
        "/punches",
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "employee_id": employee.id,
            "punch_type": "COME",
            "timestamp_utc": "2026-08-10T06:00:00Z",
            "idempotency_key": "66666666-6666-6666-6666-666666666666",
        },
    )

    response = await client.get(
        "/timesheet/open-days", headers={"Authorization": f"Bearer {hr_token}"}
    )

    [day] = response.json()
    assert day["work_date"] == "2026-08-10" and "WORK_DURING_ABSENCE" in day["flags"]
    # Die gestempelte Zeit steht direkt dabei (offenes Ende, Standort-Zeitzone).
    assert day["times"] == "06:00–…"


async def test_open_days_filtered_by_location(client: AsyncClient, db_session: AsyncSession) -> None:
    location_a = await _create_location(db_session, "Standort A")
    location_b = await _create_location(db_session, "Standort B")
    employee_a = await _create_employee(db_session, location_a, "EMP-A")
    employee_b = await _create_employee(db_session, location_b, "EMP-B")
    await _create_device(db_session, location_a, "device-a")
    await _create_device(db_session, location_b, "device-b")
    await _create_hr_user(db_session)
    hr_token = await _hr_token(client)

    for employee, token_raw, key_prefix in (
        (employee_a, "device-a", "44444444-4444-4444-4444-44444444444"),
        (employee_b, "device-b", "55555555-5555-5555-5555-55555555555"),
    ):
        device_token = await _device_token(client, token_raw)
        await client.post(
            "/punches",
            headers={"Authorization": f"Bearer {device_token}"},
            json={
                "employee_id": employee.id,
                "punch_type": "COME",
                "timestamp_utc": "2026-08-10T06:00:00Z",
                "idempotency_key": f"{key_prefix}0",
            },
        )
        # Folgetag-Buchung, damit der 10.8. als vergessener Punch-Out zählt statt
        # nur "gerade anwesend".
        await client.post(
            "/punches",
            headers={"Authorization": f"Bearer {device_token}"},
            json={
                "employee_id": employee.id,
                "punch_type": "COME",
                "timestamp_utc": "2026-08-11T06:00:00Z",
                "idempotency_key": f"{key_prefix}1",
            },
        )
        await client.post(
            "/punches",
            headers={"Authorization": f"Bearer {device_token}"},
            json={
                "employee_id": employee.id,
                "punch_type": "GO",
                "timestamp_utc": "2026-08-11T14:00:00Z",
                "idempotency_key": f"{key_prefix}2",
            },
        )

    response = await client.get(
        f"/timesheet/open-days?location_id={location_a.id}",
        headers={"Authorization": f"Bearer {hr_token}"},
    )

    body = response.json()
    assert len(body) == 1
    assert body[0]["employee_id"] == employee_a.id


async def test_finished_special_case_of_today_is_listed(client: AsyncClient, db_session: AsyncSession) -> None:
    """Heute außerplanmäßig gestempelt und schon wieder ausgestempelt -> sofort "zu klären";
    eine heute noch laufende Schicht dagegen noch nicht."""
    from datetime import date

    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, "EMP-1")
    running = await _create_employee(db_session, location, "EMP-2")
    await _create_device(db_session, location, "device-1")
    await _create_hr_user(db_session)
    device_token = await _device_token(client, "device-1")
    hr = {"Authorization": f"Bearer {await _hr_token(client)}"}
    today = date.today()
    # Arbeitszeitmodell ohne den heutigen Wochentag -> Stempeln heute ist außerplanmäßig.
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=hr,
        json={"weekly_hours": 8, "weekdays": [(today.weekday() + 1) % 7], "valid_from": "2025-01-01"},
    )
    assert r.status_code == 200, r.text

    for index, (who, punch_type, hour) in enumerate(((employee, "COME", "01"), (employee, "GO", "02"), (running, "COME", "01"))):
        await client.post(
            "/punches",
            headers={"Authorization": f"Bearer {device_token}"},
            json={
                "employee_id": who.id,
                "punch_type": punch_type,
                "timestamp_utc": f"{today.isoformat()}T{hour}:00:00Z",
                "idempotency_key": f"77777777-7777-7777-7777-77777777777{index}",
            },
        )

    body = (await client.get("/timesheet/open-days", headers=hr)).json()
    assert [(d["employee_id"], d["flags"], d["times"]) for d in body] == [(employee.id, ["UNPLANNED_WORK"], "01:00–02:00")]


async def test_deleted_punches_leave_no_stale_open_days(client: AsyncClient, db_session: AsyncSession) -> None:
    """Werden Stempelungen gelöscht, verschwinden die zugehörigen Tage aus "Zu klären" – auch wenn
    danach gar keine Stempelung mehr übrig ist oder die erste gelöscht wurde."""
    location = await _create_location(db_session)
    employee = await _create_employee(db_session, location, "EMP-1")
    await _create_hr_user(db_session)
    hr = {"Authorization": f"Bearer {await _hr_token(client)}"}

    async def punch(punch_type: str, ts: str) -> int:
        r = await client.post(
            "/punches",
            headers=hr,
            json={"employee_id": employee.id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": ts + punch_type},
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    first = await punch("COME", "2026-08-10T06:00:00Z")  # offen: kein Gehen, danach weitere Tage
    await punch("COME", "2026-08-11T06:00:00Z")
    await punch("GO", "2026-08-11T14:00:00Z")
    assert [d["work_date"] for d in (await client.get("/timesheet/open-days", headers=hr)).json()] == ["2026-08-10"]

    # Erste Stempelung weg -> Konto beginnt später, der 10.8. darf nicht hängen bleiben.
    assert (await client.delete(f"/punches/{first}", headers=hr)).status_code == 204
    assert (await client.get("/timesheet/open-days", headers=hr)).json() == []

    # Neuer offener Tag, dann alles löschen -> nichts mehr zu klären.
    await punch("COME", "2026-08-12T06:00:00Z")
    await punch("COME", "2026-08-13T06:00:00Z")
    # Auch der 13.8. ist offen: seit dem Kommen ist die maximale Schichtlänge längst überschritten.
    assert [d["work_date"] for d in (await client.get("/timesheet/open-days", headers=hr)).json()] == ["2026-08-12", "2026-08-13"]
    for punch_row in (await client.get(f"/employees/{employee.id}/punches", headers=hr)).json():
        assert (await client.delete(f"/punches/{punch_row['id']}", headers=hr)).status_code == 204
    assert (await client.get("/timesheet/open-days", headers=hr)).json() == []
