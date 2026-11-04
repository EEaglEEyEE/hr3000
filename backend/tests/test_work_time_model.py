from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSettings, Employee, Holiday, HrRole, HrUser, Location
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient, role: HrRole = HrRole.ADMIN):
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(
        location_id=location.id, first_name="Erika", last_name="Musterfrau", employee_number="EMP-1"
    )
    db_session.add(employee)
    db_session.add(HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=role))
    await db_session.commit()
    await db_session.refresh(employee)
    login = await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})
    return employee, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _timesheet(client: AsyncClient, headers: dict, employee_id: int, start: str, end: str) -> dict:
    response = await client.get(
        f"/employees/{employee_id}/timesheet?from={start}&to={end}", headers=headers
    )
    assert response.status_code == 200
    return {d["work_date"]: d for d in response.json()}


async def test_work_time_model_sets_target_and_holiday_credit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee, headers = await _setup(db_session, client)
    db_session.add(Holiday(date=date(2026, 10, 7), name="Testfeiertag"))
    await db_session.commit()

    response = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=headers,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_work_time_model"] is True
    assert body["weekly_minutes"] == 2400
    assert body["daily_minutes"] == 480
    assert body["weekdays"] == [0, 1, 2, 3, 4]

    days = await _timesheet(client, headers, employee.id, "2026-10-05", "2026-10-11")
    assert days["2026-10-05"]["target_minutes"] == 480  # Montag
    assert days["2026-10-10"]["status"] == "PLANNED_OFF"  # Samstag, kein Arbeitstag
    # Feiertag auf einem Arbeitstag wird mit dem Tagessoll gutgeschrieben.
    assert days["2026-10-07"]["status"] == "HOLIDAY"
    assert days["2026-10-07"]["target_minutes"] == 480
    assert days["2026-10-07"]["actual_minutes"] == 480


async def test_part_time_distributes_weekly_hours_over_days(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee, headers = await _setup(db_session, client)

    response = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=headers,
        json={"weekly_hours": 38.5, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"},
    )
    assert response.json()["weekly_minutes"] == 2310
    days = await _timesheet(client, headers, employee.id, "2026-10-05", "2026-10-09")
    assert sum(d["target_minutes"] for d in days.values()) == 2310


async def test_more_than_ten_hours_per_day_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)

    response = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=headers,
        json={"weekly_hours": 50, "weekdays": [0, 1, 2, 3], "valid_from": "2026-10-01"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "MAX_DAILY_WORKING_TIME_EXCEEDED"


async def test_invalid_input_is_rejected_by_validation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee, headers = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"

    for payload in (
        {"weekly_hours": 0, "weekdays": [0], "valid_from": "2026-10-01"},
        {"weekly_hours": 40, "weekdays": [], "valid_from": "2026-10-01"},
        {"weekly_hours": 40, "weekdays": [0, 0], "valid_from": "2026-10-01"},
        {"weekly_hours": 40, "weekdays": [7], "valid_from": "2026-10-01"},
        {"weekly_hours": 99, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"},
        {"weekly_hours": 40, "weekdays": [0], "valid_from": "kein-datum"},
    ):
        response = await client.put(url, headers=headers, json=payload)
        assert response.status_code == 422, payload


async def test_new_model_from_later_date_closes_previous(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee, headers = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"

    await client.put(
        url, headers=headers, json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"}
    )
    await client.put(
        url, headers=headers, json={"weekly_hours": 20, "weekdays": [0, 1], "valid_from": "2026-11-01"}
    )

    before = await _timesheet(client, headers, employee.id, "2026-10-26", "2026-10-26")
    after = await _timesheet(client, headers, employee.id, "2026-11-02", "2026-11-03")
    assert before["2026-10-26"]["target_minutes"] == 480
    assert after["2026-11-02"]["target_minutes"] == 600  # 20 h / 2 Tage
    assert after["2026-11-03"]["target_minutes"] == 600


async def test_same_start_date_updates_in_place(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"

    await client.put(
        url, headers=headers, json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"}
    )
    response = await client.put(
        url, headers=headers, json={"weekly_hours": 30, "weekdays": [0, 1, 2], "valid_from": "2026-10-01"}
    )

    assert response.status_code == 200
    assert response.json()["weekly_minutes"] == 1800
    assert response.json()["weekdays"] == [0, 1, 2]
    listing = await client.get(f"/employees/{employee.id}/default-shifts", headers=headers)
    assert len(listing.json()) == 1


async def test_get_without_configuration(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)

    response = await client.get(f"/employees/{employee.id}/work-time-model", headers=headers)

    assert response.status_code == 200
    assert response.json()["configured"] is False


async def test_work_time_model_change_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)

    await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=headers,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"},
    )

    entries = (await client.get("/audit-log", headers=headers)).json()
    entry = next(e for e in entries if e["action"] == "EMPLOYEE_WORK_TIME_MODEL_SET")
    assert "40 h/Woche an Mo, Di, Mi, Do, Fr" in entry["detail"]


async def test_supervisor_cannot_set_work_time_model(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client, role=HrRole.SUPERVISOR)

    response = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=headers,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"},
    )

    assert response.status_code == 403


async def test_shift_planning_disabled_blocks_entries_and_ignores_existing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee, headers = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"
    await client.put(
        url, headers=headers, json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"}
    )

    # Schichtplanung an: Tagesausnahme "frei" am Montag wirkt.
    entry = await client.put(
        f"/employees/{employee.id}/shift-plan-entries/2026-10-05",
        headers=headers,
        json={"is_workday": False},
    )
    assert entry.status_code == 200
    days = await _timesheet(client, headers, employee.id, "2026-10-05", "2026-10-05")
    assert days["2026-10-05"]["status"] == "PLANNED_OFF"

    settings_row = (await db_session.execute(select(AppSettings))).scalars().first()
    settings_row.shift_planning_enabled = False
    await db_session.commit()

    # Aus: bestehender Eintrag wird ignoriert, neue sind gesperrt.
    days = await _timesheet(client, headers, employee.id, "2026-10-05", "2026-10-05")
    assert days["2026-10-05"]["target_minutes"] == 480
    blocked = await client.put(
        f"/employees/{employee.id}/shift-plan-entries/2026-10-06",
        headers=headers,
        json={"is_workday": False},
    )
    assert blocked.status_code == 400
    assert blocked.json()["code"] == "SHIFT_PLANNING_DISABLED"


async def test_settings_expose_and_change_shift_planning_toggle(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, headers = await _setup(db_session, client)

    current = await client.get("/settings", headers=headers)
    assert current.json()["shift_planning_enabled"] is True

    updated = await client.patch("/settings", headers=headers, json={"shift_planning_enabled": False})
    assert updated.json()["shift_planning_enabled"] is False


async def test_features_readable_by_hr_and_supervisor(client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _setup(db_session, client, role=HrRole.SUPERVISOR)

    response = await client.get("/features", headers=headers)

    assert response.status_code == 200
    assert response.json()["shift_planning_enabled"] is True


async def test_earlier_start_date_replaces_later_models(client: AsyncClient, db_session: AsyncSession) -> None:
    """Rückwirkend ab 01.10. setzen, obwohl schon Modelle ab 01.10. und 13.10. existieren:
    alles ab dem Stichtag wird ersetzt, davor bleibt unverändert."""
    employee, headers = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"
    for body in (
        {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-09-01"},
        {"weekly_hours": 6.5, "weekdays": [0], "valid_from": "2026-10-01"},
        {"weekly_hours": 6.5, "weekdays": [0], "valid_from": "2026-10-13"},
    ):
        assert (await client.put(url, headers=headers, json=body)).status_code == 200

    response = await client.put(
        url, headers=headers, json={"weekly_hours": 32.5, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["valid_from"] == "2026-10-01" and response.json()["weekly_minutes"] == 1950

    listing = (await client.get(f"/employees/{employee.id}/default-shifts", headers=headers)).json()
    assert sorted((d["valid_from"], d["valid_to"]) for d in listing) == [
        ("2026-09-01", "2026-09-30"),
        ("2026-10-01", None),
    ]
    days = await _timesheet(client, headers, employee.id, "2026-09-29", "2026-10-14")
    assert days["2026-09-29"]["target_minutes"] == 480
    assert days["2026-10-13"]["target_minutes"] == 390  # Di, 32,5 h / 5 Tage


async def test_history_can_be_edited_and_deleted(client: AsyncClient, db_session: AsyncSession) -> None:
    from datetime import datetime

    from app.models import PeriodClosure, PeriodStatus

    employee, headers = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"
    for body in (
        {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-08-01"},
        {"weekly_hours": 20, "weekdays": [0, 1], "valid_from": "2026-09-01"},
        {"daily_hours": [8, 8, 4, 0, 0, 0, 0], "valid_from": "2026-10-01"},
    ):
        assert (await client.put(url, headers=headers, json=body)).status_code == 200

    history = (await client.get(f"{url}/history", headers=headers)).json()
    assert [(v["valid_from"], v["valid_to"], v["weekly_minutes"]) for v in history] == [
        ("2026-10-01", None, 1200),
        ("2026-09-01", "2026-09-30", 1200),
        ("2026-08-01", "2026-08-31", 2400),
    ]
    assert history[0]["uneven"] is True and history[0]["day_minutes"] == [480, 480, 240, 0, 0, 0, 0]

    # September-Fassung nachträglich auf 30 h Mo–Mi ab 15.08. ändern: August-Fassung endet am 14.08.
    september = history[1]["id"]
    r = await client.put(
        f"{url}/versions/{september}",
        headers=headers,
        json={"weekly_hours": 30, "weekdays": [0, 1, 2], "valid_from": "2026-08-15"},
    )
    assert r.status_code == 200, r.text
    assert [(v["valid_from"], v["valid_to"], v["weekly_minutes"]) for v in r.json()] == [
        ("2026-10-01", None, 1200),
        ("2026-08-15", "2026-09-30", 1800),
        ("2026-08-01", "2026-08-14", 2400),
    ]
    days = await _timesheet(client, headers, employee.id, "2026-08-14", "2026-08-17")
    assert days["2026-08-14"]["target_minutes"] == 480 and days["2026-08-17"]["target_minutes"] == 600
    # Beginn vor der vorherigen Fassung ist nicht möglich.
    bad = await client.put(
        f"{url}/versions/{september}", headers=headers, json={"weekly_hours": 30, "weekdays": [0], "valid_from": "2026-07-01"}
    )
    assert bad.status_code == 400

    # Löschen: die vorherige Fassung gilt bis zum Ende der gelöschten weiter.
    assert (await client.delete(f"{url}/versions/{september}", headers=headers)).status_code == 204
    history = (await client.get(f"{url}/history", headers=headers)).json()
    assert [(v["valid_from"], v["valid_to"]) for v in history] == [("2026-10-01", None), ("2026-08-01", "2026-09-30")]

    # Abgeschlossener Monat: Fassung darin nicht mehr änderbar.
    db_session.add(
        PeriodClosure(
            tenant_id=1, employee_id=employee.id, year=2026, month=8, status=PeriodStatus.CLOSED, target_minutes=0,
            actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=datetime(2026, 9, 1),
        )
    )
    await db_session.commit()
    locked = await client.delete(f"{url}/versions/{history[1]['id']}", headers=headers)
    assert locked.json()["code"] == "PERIOD_LOCKED"
