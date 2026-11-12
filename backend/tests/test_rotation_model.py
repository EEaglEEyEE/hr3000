"""Mehrwöchiges Arbeitszeitmodell: Turnus über 2 bis 4 Wochen mit Stunden je Wochentag – als
individuelle Angabe am Mitarbeiter und als Arbeitszeitmodell, mit allen Folgewirkungen (Tagessoll,
Gleitzeitkonto, „Zu klären“, Urlaubstage, Anspruch, Feiertage, Monatsbericht, Lohn-Export)."""
import csv
import io
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    AuditLogEntry,
    Employee,
    EmployeeDefaultShift,
    Holiday,
    HrRole,
    Location,
    PeriodClosure,
    PeriodStatus,
    Tenant,
    WorkTimeProfile,
    WorkTimeProfileVersion,
)
from app.models.rotation import (
    ROTATION_MAX_WEEKS,
    ROTATION_MIN_WEEKS,
    monday_of,
    parse_rotation,
    rotation_week_index,
    serialize_rotation,
)
from app.schemas.work_time_model import WorkTimeModelInput, WorkTimeModelSetRequest
from app.services.auth_service import hash_password
from app.services.leave_service import _workdays_of, computed_entitlement, workdays_per_week
from app.services.period_service import build_month_report
from app.services.settings_service import get_or_create_settings

# Woche 1: Mo–Mi je 8 Std., Woche 2: Do/Fr je 8 Std. -> im Schnitt 20 Std. und 2,5 Tage je Woche
WEEK_A = [8, 8, 8, 0, 0, 0, 0]
WEEK_B = [0, 0, 0, 8, 8, 0, 0]
AB = {"rotation_weeks": [WEEK_A, WEEK_B]}
# Gültig ab Do 01.10.2026 -> Woche 1 = 28.09.–04.10., Woche 2 = 05.–11.10., Woche 1 = 12.–18.10. …
VALID_FROM = "2026-10-01"


# ---------------------------------------------------------------------------------------------
# Rechenkern (app/models/rotation.py)
# ---------------------------------------------------------------------------------------------


def test_limits_are_two_to_four_weeks() -> None:
    assert (ROTATION_MIN_WEEKS, ROTATION_MAX_WEEKS) == (2, 4)


@pytest.mark.parametrize(
    ("day", "monday"),
    [
        (date(2026, 10, 5), date(2026, 10, 5)),  # Montag bleibt
        (date(2026, 10, 8), date(2026, 10, 5)),  # Donnerstag
        (date(2026, 10, 11), date(2026, 10, 5)),  # Sonntag
        (date(2027, 1, 1), date(2026, 12, 28)),  # über den Jahreswechsel
        (date(2024, 2, 29), date(2024, 2, 26)),  # Schalttag
    ],
)
def test_monday_of(day: date, monday: date) -> None:
    assert monday_of(day) == monday


def test_serialize_and_parse_round_trip() -> None:
    weeks = [[480, 480, 480, 0, 0, 0, 0], [0, 0, 0, 450, 465, 0, 0]]
    text = serialize_rotation(weeks)
    assert text == "480,480,480,0,0,0,0;0,0,0,450,465,0,0"
    assert parse_rotation(text) == weeks


def test_four_full_weeks_fit_the_column() -> None:
    # längster denkbarer Wert: 4 Wochen × 7 Tage mit je 1440 Minuten
    assert len(serialize_rotation([[1440] * 7] * 4)) <= 160


@pytest.mark.parametrize("value", [None, ""])
def test_parse_rotation_without_value(value: str | None) -> None:
    assert parse_rotation(value) is None


@pytest.mark.parametrize(
    ("day", "weeks", "index"),
    [
        (date(2026, 9, 28), 2, 0),  # Montag der Woche 1
        (date(2026, 10, 4), 2, 0),  # Sonntag der Woche 1
        (date(2026, 10, 5), 2, 1),  # Montag der Woche 2
        (date(2026, 10, 11), 2, 1),
        (date(2026, 10, 12), 2, 0),  # Turnus beginnt von vorn
        (date(2026, 9, 27), 2, 1),  # Sonntag davor: rückwärts weitergezählt
        (date(2026, 9, 21), 2, 1),
        (date(2026, 9, 14), 2, 0),
        (date(2026, 10, 12), 3, 2),
        (date(2026, 10, 19), 3, 0),
        (date(2026, 10, 19), 4, 3),
        (date(2026, 10, 26), 4, 0),
        (date(2026, 9, 21), 4, 3),  # eine Woche vor dem Start
        (date(2026, 9, 7), 3, 0),  # drei Wochen vor dem Start
        (date(2027, 9, 27), 2, 0),  # 52 Wochen später
        (date(2027, 10, 4), 2, 1),
    ],
)
def test_rotation_week_index(day: date, weeks: int, index: int) -> None:
    assert rotation_week_index(date(2026, 9, 28), weeks, day) == index


def test_rotation_week_index_uses_the_week_of_the_start() -> None:
    # Start mitten in der Woche: Woche 1 ist die Kalenderwoche des Starts.
    assert rotation_week_index(date(2026, 10, 1), 2, date(2026, 9, 28)) == 0
    assert rotation_week_index(date(2026, 10, 1), 2, date(2026, 10, 5)) == 1


def _version(**fields) -> EmployeeDefaultShift:
    return EmployeeDefaultShift(employee_id=1, valid_from=date(2026, 10, 1), weekdays_mask=0b0011111, **fields)


def test_mixin_without_rotation_falls_back_to_day_minutes() -> None:
    plain = _version()
    assert plain.rotation_weeks is None and plain.rotation_week_on(date(2026, 10, 5)) is None
    assert plain.day_minutes_on(date(2026, 10, 5)) is None and plain.average_workdays is None
    per_day = _version(day_minutes="480,480,240,0,0,0,0")
    assert per_day.day_minutes_list == [480, 480, 240, 0, 0, 0, 0]
    assert per_day.day_minutes_on(date(2026, 10, 5)) == [480, 480, 240, 0, 0, 0, 0]
    assert per_day.average_workdays is None


def test_mixin_resolves_the_week_of_a_day() -> None:
    version = _version(rotation_minutes="480,480,480,0,0,0,0;0,0,0,480,480,0,0", rotation_start=date(2026, 9, 28))
    assert version.rotation_weeks == [[480, 480, 480, 0, 0, 0, 0], [0, 0, 0, 480, 480, 0, 0]]
    assert version.rotation_week_on(date(2026, 10, 1)) == 0
    assert version.rotation_week_on(date(2026, 10, 8)) == 1
    assert version.day_minutes_on(date(2026, 10, 8)) == [0, 0, 0, 480, 480, 0, 0]
    assert version.day_minutes_on(date(2026, 10, 13)) == [480, 480, 480, 0, 0, 0, 0]
    assert version.average_workdays == 2.5


def test_mixin_without_start_uses_the_week_of_valid_from() -> None:
    version = _version(rotation_minutes="480,0,0,0,0,0,0;0,480,0,0,0,0,0")
    assert version.rotation_week_on(date(2026, 9, 28)) == 0  # Montag der Woche des Gültig-ab
    assert version.rotation_week_on(date(2026, 10, 6)) == 1


def test_mixin_is_shared_with_profile_versions() -> None:
    version = WorkTimeProfileVersion(
        profile_id=1, valid_from=date(2000, 1, 1), weekdays_mask=127,
        rotation_minutes="480,480,480,480,0,0,0;480,480,480,0,0,0,0;480,480,0,0,0,0,0", rotation_start=date(2026, 9, 28),
    )
    assert version.rotation_week_on(date(2026, 10, 12)) == 2
    assert version.average_workdays == 3.0


# ---------------------------------------------------------------------------------------------
# Eingabeprüfung (Pydantic)
# ---------------------------------------------------------------------------------------------


def test_input_derives_average_and_weekdays() -> None:
    model = WorkTimeModelInput(rotation_weeks=[WEEK_A, WEEK_B])
    assert model.weekly_hours == 20 and model.weekdays == [0, 1, 2, 3, 4]
    assert model.rotation_minutes == [[480, 480, 480, 0, 0, 0, 0], [0, 0, 0, 480, 480, 0, 0]]
    assert model.daily_hours is None and model.day_minutes is None and model.rotation_start is None


@pytest.mark.parametrize("count", [2, 3, 4])
def test_input_accepts_two_to_four_weeks(count: int) -> None:
    model = WorkTimeModelInput(rotation_weeks=[WEEK_A] * count)
    assert len(model.rotation_minutes) == count and model.weekly_hours == 24


@pytest.mark.parametrize(
    "weeks",
    [
        [WEEK_A],  # nur eine Woche
        [WEEK_A] * 5,  # fünf Wochen
        [],  # leer
        [WEEK_A, [8, 8, 8, 0, 0, 0]],  # sechs Werte
        [WEEK_A, [8, 8, 8, 0, 0, 0, 0, 0]],  # acht Werte
        [WEEK_A, [-1, 8, 8, 0, 0, 0, 0]],  # negativ
        [WEEK_A, [24.5, 0, 0, 0, 0, 0, 0]],  # mehr als 24 Std.
        [[0] * 7, [0] * 7],  # kein Tag mit Soll
        [[0.001] * 7, [0] * 7],  # rundet auf 0 Minuten
        [WEEK_A, [10, 10, 10, 10, 10, 10, 0.5]],  # mehr als 60 Std. in einer Woche
    ],
)
def test_input_rejects_invalid_rotations(weeks: list) -> None:
    with pytest.raises(ValidationError):
        WorkTimeModelInput(rotation_weeks=weeks)


def test_input_allows_a_free_week_and_sixty_hours() -> None:
    assert WorkTimeModelInput(rotation_weeks=[WEEK_A, [0] * 7]).weekly_hours == 12
    assert WorkTimeModelInput(rotation_weeks=[[10] * 6 + [0], WEEK_A]).weekly_hours == 42


@pytest.mark.parametrize(
    "extra",
    [{"flexible": True, "weekly_hours": 20}, {"on_demand": True}, {"monthly_hours": 80, "weekdays": [0, 1]}],
)
def test_input_rejects_combination_with_other_variants(extra: dict) -> None:
    with pytest.raises(ValidationError):
        WorkTimeModelInput(rotation_weeks=[WEEK_A, WEEK_B], **extra)


def test_input_ignores_other_soll_fields_of_the_dialog() -> None:
    # Der Dialog schickt beim Wechsel der Variante ggf. alte Werte mit – maßgeblich ist der Turnus.
    model = WorkTimeModelInput(
        rotation_weeks=[WEEK_A, WEEK_B], weekly_hours=40, weekdays=[5, 6], daily_hours=[1] * 7, monthly_cap_hours=10
    )
    assert (model.weekly_hours, model.weekdays, model.daily_hours, model.monthly_cap_hours) == (20, [0, 1, 2, 3, 4], None, None)


def test_input_rotation_start_is_moved_to_monday() -> None:
    assert WorkTimeModelInput(rotation_weeks=[WEEK_A, WEEK_B], rotation_start="2026-10-08").rotation_start == date(2026, 10, 5)
    assert WorkTimeModelInput(rotation_weeks=[WEEK_A, WEEK_B], rotation_start="2026-10-05").rotation_start == date(2026, 10, 5)


@pytest.mark.parametrize("start", ["1999-12-31", "2101-01-01", "kein Datum"])
def test_input_rejects_rotation_start_out_of_range(start: str) -> None:
    with pytest.raises(ValidationError):
        WorkTimeModelInput(rotation_weeks=[WEEK_A, WEEK_B], rotation_start=start)


def test_input_rejects_rotation_start_without_rotation() -> None:
    with pytest.raises(ValidationError):
        WorkTimeModelInput(weekly_hours=40, weekdays=[0, 1, 2, 3, 4], rotation_start="2026-10-05")


def test_input_daily_maximum_looks_at_every_week() -> None:
    assert WorkTimeModelInput(rotation_weeks=[WEEK_A, WEEK_B]).exceeds_daily_maximum is False
    assert WorkTimeModelInput(rotation_weeks=[WEEK_A, [0, 0, 0, 10, 0, 0, 0]]).exceeds_daily_maximum is False
    assert WorkTimeModelInput(rotation_weeks=[WEEK_A, [0, 0, 0, 10.5, 0, 0, 0]]).exceeds_daily_maximum is True


def test_input_rounds_to_minutes() -> None:
    model = WorkTimeModelInput(rotation_weeks=[[7.7, 0, 0, 0, 0, 0, 0], [0, 3.75, 0, 0, 0, 0, 0]])
    assert model.rotation_minutes == [[462, 0, 0, 0, 0, 0, 0], [0, 225, 0, 0, 0, 0, 0]]


def test_from_input_keeps_the_rotation() -> None:
    model = WorkTimeModelInput(rotation_weeks=[WEEK_A, WEEK_B], rotation_start="2026-10-07")
    request = WorkTimeModelSetRequest.from_input(model, date(2026, 11, 1))
    assert request.rotation_minutes == model.rotation_minutes and request.rotation_start == date(2026, 10, 5)
    assert request.valid_from == date(2026, 11, 1)


# ---------------------------------------------------------------------------------------------
# Helfer für die Endpoint-Tests
# ---------------------------------------------------------------------------------------------


async def _login(client: AsyncClient, email: str) -> dict:
    r = await client.post("/auth/login", json={"email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _setup(db_session: AsyncSession, client: AsyncClient, *, termination: date | None = None, hire: date | None = None):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1", auto_break_enabled=False,
        termination_date=termination, hire_date=hire, login_email="erika@example.com", password_hash=hash_password("pw"),
    )
    db_session.add_all([employee, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    await db_session.refresh(employee)
    return employee, await _login(client, "admin@example.com")


async def _put(client: AsyncClient, admin: dict, employee_id: int, valid_from: str = VALID_FROM, **model):
    return await client.put(
        f"/employees/{employee_id}/work-time-model", headers=admin, json={**(model or AB), "valid_from": valid_from}
    )


async def _days(client: AsyncClient, headers: dict, employee_id: int, start: str, end: str) -> dict:
    r = await client.get(f"/employees/{employee_id}/timesheet", headers=headers, params={"from": start, "to": end})
    assert r.status_code == 200, r.text
    return {d["work_date"]: d for d in r.json()}


async def _targets(client: AsyncClient, headers: dict, employee_id: int, start: str, end: str) -> list[int]:
    days = await _days(client, headers, employee_id, start, end)
    return [days[key]["target_minutes"] or 0 for key in sorted(days)]


async def _work(client: AsyncClient, admin: dict, employee_id: int, day: str, come: str = "08:00", go: str = "16:00") -> None:
    for punch_type, clock in (("COME", come), ("GO", go)):
        r = await client.post(
            "/punches", headers=admin,
            json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{day}T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text


async def _balance(client: AsyncClient, headers: dict, employee_id: int) -> int:
    r = await client.get(f"/employees/{employee_id}/overtime-balance", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["running_balance_minutes"]


async def _profile(client: AsyncClient, admin: dict, name: str = "Wechselwoche", **model) -> dict:
    r = await client.post("/work-time-profiles", headers=admin, json={"name": name, **(model or AB)})
    assert r.status_code == 201, r.text
    return r.json()


async def _assign(client: AsyncClient, admin: dict, employee_id: int, profile_id: int, valid_from: str = VALID_FROM) -> dict:
    r = await client.put(
        f"/employees/{employee_id}/work-time-profile", headers=admin, json={"profile_id": profile_id, "valid_from": valid_from}
    )
    assert r.status_code == 200, r.text
    return r.json()


def _csv_row(response) -> dict:
    assert response.status_code == 200, response.text
    rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿")), delimiter=";"))
    return dict(zip(rows[0], rows[1]))


# ---------------------------------------------------------------------------------------------
# Individuelle Angabe am Mitarbeiter
# ---------------------------------------------------------------------------------------------


async def test_set_rotation_model_response(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await _put(client, admin, employee.id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rotation_minutes"] == [[480, 480, 480, 0, 0, 0, 0], [0, 0, 0, 480, 480, 0, 0]]
    assert body["rotation_start"] == "2026-09-28"  # Montag der Woche des Gültig-ab
    assert body["weekly_minutes"] == 1200 and body["daily_minutes"] is None and body["day_minutes"] is None
    assert body["weekdays"] == [0, 1, 2, 3, 4]
    assert (body["flexible"], body["on_demand"], body["monthly_minutes"]) == (False, False, None)

    again = (await client.get(f"/employees/{employee.id}/work-time-model", headers=admin)).json()
    assert again["rotation_minutes"] == body["rotation_minutes"] and again["rotation_start"] == "2026-09-28"

    stored = (await db_session.execute(select(EmployeeDefaultShift))).scalars().one()
    assert stored.rotation_minutes == "480,480,480,0,0,0,0;0,0,0,480,480,0,0"
    assert stored.rotation_start == date(2026, 9, 28) and stored.day_minutes is None and stored.weekdays_mask == 0b0011111


async def test_daily_target_follows_the_rotation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, admin, employee.id)).status_code == 200
    # Woche 2 (05.–11.10.): Do/Fr
    assert await _targets(client, admin, employee.id, "2026-10-05", "2026-10-11") == [0, 0, 0, 480, 480, 0, 0]
    # Woche 1 (12.–18.10.): Mo–Mi
    assert await _targets(client, admin, employee.id, "2026-10-12", "2026-10-18") == [480, 480, 480, 0, 0, 0, 0]
    # und wieder Woche 2, Woche 1 – auch über den Monatswechsel
    assert await _targets(client, admin, employee.id, "2026-10-19", "2026-11-01") == [0, 0, 0, 480, 480, 0, 0, 480, 480, 480, 0, 0, 0, 0]
    days = await _days(client, admin, employee.id, "2026-10-05", "2026-10-08")
    assert days["2026-10-05"]["status"] == "PLANNED_OFF"  # Montag der Woche 2 ist frei


async def test_week_one_is_the_week_of_valid_from(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    # Gültig ab einem Donnerstag: der Donnerstag liegt in Woche 1 (dort frei), die Tage davor ohne Modell.
    assert (await _put(client, admin, employee.id)).status_code == 200
    assert await _targets(client, admin, employee.id, "2026-10-01", "2026-10-04") == [0, 0, 0, 0]
    # Gültig ab einem Montag: Woche 1 beginnt genau an diesem Tag.
    other = (await _put(client, admin, employee.id, valid_from="2026-10-19")).json()
    assert other["rotation_start"] == "2026-10-19"
    assert await _targets(client, admin, employee.id, "2026-10-19", "2026-10-25") == [480, 480, 480, 0, 0, 0, 0]


async def test_rotation_start_overrides_the_anchor(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    # „Turnus beginnt am“ Mi 07.10. -> Woche 1 ab Mo 05.10. (statt 28.09.)
    r = await _put(client, admin, employee.id, **AB, rotation_start="2026-10-07")
    assert r.status_code == 200 and r.json()["rotation_start"] == "2026-10-05"
    assert await _targets(client, admin, employee.id, "2026-10-05", "2026-10-11") == [480, 480, 480, 0, 0, 0, 0]
    assert await _targets(client, admin, employee.id, "2026-10-12", "2026-10-18") == [0, 0, 0, 480, 480, 0, 0]


async def test_rotation_start_may_lie_after_valid_from(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    # Startpunkt in der Zukunft der Fassung: der Turnus läuft rückwärts weiter.
    r = await _put(client, admin, employee.id, **AB, rotation_start="2026-10-26")
    assert r.status_code == 200 and r.json()["rotation_start"] == "2026-10-26"
    assert await _targets(client, admin, employee.id, "2026-10-12", "2026-10-18") == [480, 480, 480, 0, 0, 0, 0]
    assert await _targets(client, admin, employee.id, "2026-10-19", "2026-10-25") == [0, 0, 0, 480, 480, 0, 0]


async def test_three_week_rotation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    weeks = [[8, 8, 8, 8, 8, 0, 0], [6, 6, 6, 6, 0, 0, 0], [0, 0, 0, 0, 0, 5, 5]]
    r = await _put(client, admin, employee.id, valid_from="2026-09-28", rotation_weeks=weeks)
    assert r.status_code == 200, r.text
    assert r.json()["weekly_minutes"] == round((40 + 24 + 10) * 60 / 3) and r.json()["weekdays"] == [0, 1, 2, 3, 4, 5, 6]
    assert await _targets(client, admin, employee.id, "2026-09-28", "2026-10-04") == [480] * 5 + [0, 0]
    assert await _targets(client, admin, employee.id, "2026-10-05", "2026-10-11") == [360] * 4 + [0, 0, 0]
    assert await _targets(client, admin, employee.id, "2026-10-12", "2026-10-18") == [0] * 5 + [300, 300]
    assert await _targets(client, admin, employee.id, "2026-10-19", "2026-10-25") == [480] * 5 + [0, 0]


async def test_four_week_rotation_with_a_free_week(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    weeks = [[8, 0, 0, 0, 0, 0, 0], [0, 8, 0, 0, 0, 0, 0], [0] * 7, [0, 0, 0, 4.5, 0, 0, 0]]
    r = await _put(client, admin, employee.id, valid_from="2026-09-28", rotation_weeks=weeks)
    assert r.status_code == 200 and r.json()["weekly_minutes"] == round(20.5 * 60 / 4)
    assert await _targets(client, admin, employee.id, "2026-09-28", "2026-10-25") == (
        [480, 0, 0, 0, 0, 0, 0] + [0, 480, 0, 0, 0, 0, 0] + [0] * 7 + [0, 0, 0, 270, 0, 0, 0]
    )
    assert await _targets(client, admin, employee.id, "2026-10-26", "2026-10-27") == [480, 0]


@pytest.mark.parametrize(
    "model",
    [
        {"rotation_weeks": [WEEK_A]},
        {"rotation_weeks": [WEEK_A] * 5},
        {"rotation_weeks": [WEEK_A, [8, 8]]},
        {"rotation_weeks": [WEEK_A, [25, 0, 0, 0, 0, 0, 0]]},
        {"rotation_weeks": [WEEK_A, [-2, 0, 0, 0, 0, 0, 0]]},
        {"rotation_weeks": [[0] * 7, [0] * 7]},
        {"rotation_weeks": [WEEK_A, WEEK_B], "flexible": True},
        {"rotation_weeks": [WEEK_A, WEEK_B], "on_demand": True},
        {"rotation_weeks": [WEEK_A, WEEK_B], "monthly_hours": 80},
        {"rotation_weeks": [WEEK_A, WEEK_B], "rotation_start": "1990-01-01"},
        {"rotation_weeks": "A/B"},
        {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "rotation_start": "2026-10-05"},
    ],
)
async def test_invalid_rotation_is_rejected_by_the_backend(client: AsyncClient, db_session: AsyncSession, model: dict) -> None:
    employee, admin = await _setup(db_session, client)
    r = await _put(client, admin, employee.id, **model)
    assert r.status_code == 422, r.text
    assert (await db_session.execute(select(EmployeeDefaultShift))).scalars().all() == []


async def test_more_than_ten_hours_a_day_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await _put(client, admin, employee.id, rotation_weeks=[WEEK_A, [0, 0, 0, 11, 0, 0, 0]])
    assert r.status_code == 400, r.text
    ok = await _put(client, admin, employee.id, rotation_weeks=[WEEK_A, [0, 0, 0, 10, 0, 0, 0]])
    assert ok.status_code == 200


async def test_history_and_switch_back_to_even_model(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, admin, employee.id)).status_code == 200
    r = await _put(client, admin, employee.id, valid_from="2026-10-19", weekly_hours=40, weekdays=[0, 1, 2, 3, 4])
    assert r.status_code == 200 and r.json()["rotation_minutes"] is None and r.json()["rotation_start"] is None

    history = (await client.get(f"/employees/{employee.id}/work-time-model/history", headers=admin)).json()
    by_start = {v["valid_from"]: v for v in history}
    assert by_start["2026-10-01"]["rotation_minutes"] == [[480, 480, 480, 0, 0, 0, 0], [0, 0, 0, 480, 480, 0, 0]]
    assert by_start["2026-10-01"]["valid_to"] == "2026-10-18" and by_start["2026-10-19"]["rotation_minutes"] is None
    # bis 18.10. Turnus (Woche 1), ab 19.10. gleichmäßig
    assert await _targets(client, admin, employee.id, "2026-10-12", "2026-10-25") == [480, 480, 480, 0, 0, 0, 0] + [480] * 5 + [0, 0]


async def test_later_version_keeps_its_own_anchor(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, admin, employee.id)).status_code == 200  # Woche 1 ab 28.09.
    # Neue Fassung ab Mo 05.10. ohne Startangabe: Woche 1 beginnt dort neu (wäre sonst Woche 2).
    r = await _put(client, admin, employee.id, valid_from="2026-10-05")
    assert r.json()["rotation_start"] == "2026-10-05"
    assert await _targets(client, admin, employee.id, "2026-10-05", "2026-10-11") == [480, 480, 480, 0, 0, 0, 0]
    # Mit „Turnus beginnt am“ läuft der bisherige Rhythmus weiter.
    r = await _put(client, admin, employee.id, valid_from="2026-10-05", **AB, rotation_start="2026-09-28")
    assert r.json()["rotation_start"] == "2026-09-28"
    assert await _targets(client, admin, employee.id, "2026-10-05", "2026-10-11") == [0, 0, 0, 480, 480, 0, 0]


async def test_update_version_changes_rotation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, admin, employee.id)).status_code == 200
    version = (await client.get(f"/employees/{employee.id}/work-time-model/history", headers=admin)).json()[0]
    r = await client.put(
        f"/employees/{employee.id}/work-time-model/versions/{version['id']}", headers=admin,
        json={"rotation_weeks": [WEEK_B, WEEK_A, WEEK_A], "rotation_start": "2026-10-05", "valid_from": VALID_FROM},
    )
    assert r.status_code == 200, r.text
    assert r.json()[0]["rotation_minutes"] == [[0, 0, 0, 480, 480, 0, 0], [480, 480, 480, 0, 0, 0, 0], [480, 480, 480, 0, 0, 0, 0]]
    assert await _targets(client, admin, employee.id, "2026-10-05", "2026-10-11") == [0, 0, 0, 480, 480, 0, 0]
    assert await _targets(client, admin, employee.id, "2026-10-12", "2026-10-18") == [480, 480, 480, 0, 0, 0, 0]

    # zurück auf „je Tag“: der Turnus verschwindet vollständig
    r = await client.put(
        f"/employees/{employee.id}/work-time-model/versions/{version['id']}", headers=admin,
        json={"daily_hours": [4, 4, 0, 0, 0, 0, 0], "valid_from": VALID_FROM},
    )
    assert r.status_code == 200 and r.json()[0]["rotation_minutes"] is None
    stored = (await db_session.execute(select(EmployeeDefaultShift))).scalars().one()
    await db_session.refresh(stored)
    assert stored.rotation_minutes is None and stored.rotation_start is None and stored.day_minutes == "240,240,0,0,0,0,0"


async def test_delete_rotation_version(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, admin, employee.id)).status_code == 200
    version = (await client.get(f"/employees/{employee.id}/work-time-model/history", headers=admin)).json()[0]
    r = await client.delete(f"/employees/{employee.id}/work-time-model/versions/{version['id']}", headers=admin)
    assert r.status_code == 204
    assert await _targets(client, admin, employee.id, "2026-10-12", "2026-10-14") == [0, 0, 0]


async def test_audit_log_describes_the_rotation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, admin, employee.id)).status_code == 200
    details = [e.detail for e in (await db_session.execute(select(AuditLogEntry))).scalars().all() if e.detail and "Turnus" in e.detail]
    assert len(details) == 1
    assert "im Schnitt 20 h/Woche" in details[0]
    assert "Turnus über 2 Wochen (Woche 1: Mo 8 h, Di 8 h, Mi 8 h; Woche 2: Do 8 h, Fr 8 h), Woche 1 ab 28.09.2026" in details[0]


async def test_audit_log_names_a_free_week(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, admin, employee.id, rotation_weeks=[WEEK_A, [0] * 7])).status_code == 200
    details = [e.detail for e in (await db_session.execute(select(AuditLogEntry))).scalars().all() if e.detail and "Turnus" in e.detail]
    assert "Woche 2: frei" in details[0]


# ---------------------------------------------------------------------------------------------
# Rechte und Mandantentrennung
# ---------------------------------------------------------------------------------------------


async def test_employee_may_not_set_a_rotation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    own = await _login(client, "erika@example.com")
    r = await _put(client, own, employee.id)
    assert r.status_code == 403
    assert (await db_session.execute(select(EmployeeDefaultShift))).scalars().all() == []
    assert (await client.post("/work-time-profiles", headers=own, json={"name": "X", **AB})).status_code == 403


async def test_supervisor_may_not_set_a_rotation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    db_session.add(Account(email="sup@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR))
    await db_session.commit()
    supervisor = await _login(client, "sup@example.com")
    r = await _put(client, supervisor, employee.id)
    assert r.status_code == 403 and r.json()["code"] == "HR_PERMISSION_REQUIRED"
    r = await client.post("/work-time-profiles", headers=supervisor, json={"name": "X", **AB})
    assert r.status_code == 403


async def test_hr_may_set_a_rotation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    db_session.add(Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR))
    await db_session.commit()
    r = await _put(client, await _login(client, "hr@example.com"), employee.id)
    assert r.status_code == 200


async def test_without_login_nothing_happens(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, {}, employee.id)).status_code in (401, 403)


async def test_other_tenant_cannot_see_or_change_the_rotation(client: AsyncClient, db_session: AsyncSession) -> None:
    """Mitarbeiter und Arbeitszeitmodelle einer fremden Firma sind nicht sichtbar (404) und bleiben unverändert."""
    _, admin = await _setup(db_session, client)
    db_session.add(Tenant(id=2, subdomain="other", name="Other"))
    await db_session.flush()
    foreign_location = Location(tenant_id=2, name="Fremd", timezone="UTC")
    db_session.add(foreign_location)
    await db_session.flush()
    foreign = Employee(tenant_id=2, location_id=foreign_location.id, first_name="Fremd", last_name="Firma", employee_number="F1")
    profile = WorkTimeProfile(tenant_id=2, name="Fremder Turnus", archived=False)
    db_session.add_all([foreign, profile])
    await db_session.flush()
    rotation = "480,480,480,0,0,0,0;0,0,0,480,480,0,0"
    db_session.add_all([
        EmployeeDefaultShift(employee_id=foreign.id, valid_from=date(2026, 10, 1), weekdays_mask=31, target_minutes=1200,
                             rotation_minutes=rotation, rotation_start=date(2026, 9, 28)),
        WorkTimeProfileVersion(profile_id=profile.id, valid_from=date(2000, 1, 1), weekdays_mask=31, target_minutes=1200,
                               rotation_minutes=rotation, rotation_start=date(2026, 9, 28)),
    ])
    await db_session.commit()

    assert (await client.get(f"/employees/{foreign.id}/work-time-model", headers=admin)).status_code == 404
    assert (await _put(client, admin, foreign.id, rotation_weeks=[WEEK_B, WEEK_A])).status_code == 404
    r = await client.put(
        f"/work-time-profiles/{profile.id}/model", headers=admin, json={"rotation_weeks": [WEEK_B, WEEK_A], "valid_from": VALID_FROM}
    )
    assert r.status_code == 404
    assert (await client.get(f"/work-time-profiles/{profile.id}/history", headers=admin)).status_code == 404
    assert (await client.get("/work-time-profiles", headers=admin)).json() == []
    rows = (await db_session.execute(select(EmployeeDefaultShift))).scalars().all()
    assert [(row.rotation_minutes, row.rotation_start) for row in rows] == [(rotation, date(2026, 9, 28))]


# ---------------------------------------------------------------------------------------------
# Folgewirkungen
# ---------------------------------------------------------------------------------------------


async def test_balance_counts_the_days_of_each_rotation_week(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client, termination=date(2026, 10, 16))
    assert (await _put(client, admin, employee.id)).status_code == 200
    await _work(client, admin, employee.id, "2026-10-08", "08:00", "17:00")  # Do Woche 2: 9 Std. bei 8 Soll
    # Fr 09.10. fehlt (-8), Mo 12.10./Di 13.10./Mi 14.10. fehlen (je -8); Do/Fr der Woche 1 sind frei
    assert await _balance(client, admin, employee.id) == 60 - 480 * 4
    await _work(client, admin, employee.id, "2026-10-09")
    await _work(client, admin, employee.id, "2026-10-12")
    await _work(client, admin, employee.id, "2026-10-13")
    await _work(client, admin, employee.id, "2026-10-14", "08:00", "15:30")  # 30 Min. zu wenig
    assert await _balance(client, admin, employee.id) == 60 - 30
    # Arbeit an einem freien Tag der Turnus-Woche zählt voll als Mehrarbeit.
    await _work(client, admin, employee.id, "2026-10-15", "08:00", "10:00")
    assert await _balance(client, admin, employee.id) == 60 - 30 + 120


async def test_changing_the_rotation_rebuilds_the_balance(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client, termination=date(2026, 10, 9))
    assert (await _put(client, admin, employee.id)).status_code == 200
    await _work(client, admin, employee.id, "2026-10-05")  # Mo der Woche 2: frei -> +8 Std.
    assert await _balance(client, admin, employee.id) == 480 - 960  # Do/Fr fehlen
    # Turnus eine Woche verschieben: jetzt ist die Woche Mo–Mi -> Mo erfüllt, Di/Mi fehlen
    assert (await _put(client, admin, employee.id, **AB, rotation_start="2026-10-05")).status_code == 200
    assert await _balance(client, admin, employee.id) == -960


async def test_open_days_flag_unplanned_work_and_missing_days(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client, termination=date(2026, 10, 16))
    assert (await _put(client, admin, employee.id)).status_code == 200
    await _work(client, admin, employee.id, "2026-10-05")  # Montag der Woche 2: frei -> außerplanmäßig
    await _work(client, admin, employee.id, "2026-10-12")  # Montag der Woche 1: planmäßig

    days = await _days(client, admin, employee.id, "2026-10-05", "2026-10-12")
    assert days["2026-10-05"]["flags"] == ["UNPLANNED_WORK"]
    assert days["2026-10-12"]["flags"] == [] and days["2026-10-12"]["status"] == "COMPLETE"

    open_days = (await client.get("/timesheet/open-days", headers=admin)).json()
    by_date = {d["work_date"]: d for d in open_days}
    assert by_date["2026-10-05"]["flags"] == ["UNPLANNED_WORK"]
    # fehlende Stempelung nur an den Soll-Tagen der jeweiligen Turnus-Woche
    assert {"2026-10-08", "2026-10-09", "2026-10-13", "2026-10-14"} <= set(by_date)
    assert not {"2026-10-06", "2026-10-07", "2026-10-15", "2026-10-16", "2026-10-12"} & set(by_date)


async def test_vacation_counts_only_rotation_workdays(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, admin, employee.id)).status_code == 200
    # zwei Wochen Urlaub: Woche 2 (Do/Fr) + Woche 1 (Mo–Mi) = 5 Urlaubstage statt 10
    r = await client.post(
        "/absences", headers=admin, json={"employee_id": employee.id, "type": "VACATION", "date_from": "2026-10-05", "date_to": "2026-10-18"}
    )
    assert r.status_code == 201, r.text
    entitlement = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=admin, params={"year": 2026})).json()
    assert entitlement["used_days"] == 5

    days = await _days(client, admin, employee.id, "2026-10-05", "2026-10-18")
    credited = {key: day["actual_minutes"] for key, day in days.items() if day["status"] == "ABSENCE" and day["target_minutes"]}
    assert credited == {"2026-10-08": 480, "2026-10-09": 480, "2026-10-12": 480, "2026-10-13": 480, "2026-10-14": 480}


async def test_single_vacation_day_on_a_free_rotation_day_costs_nothing(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, admin, employee.id)).status_code == 200
    for day in ("2026-10-05", "2026-10-15"):  # Mo der Woche 2, Do der Woche 1: beide frei
        r = await client.post("/absences", headers=admin, json={"employee_id": employee.id, "type": "VACATION", "date_from": day, "date_to": day})
        assert r.status_code in (201, 400), r.text
    entitlement = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=admin, params={"year": 2026})).json()
    assert entitlement["used_days"] == 0
    r = await client.post("/absences", headers=admin, json={"employee_id": employee.id, "type": "VACATION", "date_from": "2026-10-08", "date_to": "2026-10-08"})
    assert r.status_code == 201
    entitlement = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=admin, params={"year": 2026})).json()
    assert entitlement["used_days"] == 1


async def test_entitlement_uses_average_workdays(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    settings_row = await get_or_create_settings(db_session, 1)
    settings_row.default_annual_vacation_days = 30
    settings_row.prorate_part_time_vacation = True
    settings_row.prorate_partial_year_vacation = False
    await db_session.commit()
    assert (await _put(client, admin, employee.id, valid_from="2026-01-01")).status_code == 200

    # 2,5 Arbeitstage je Woche im Schnitt -> 30 × 2,5 / 5 = 15 Tage
    assert await computed_entitlement(db_session, employee, 2026) == 15
    assert await workdays_per_week(db_session, employee.id, date(2026, 6, 1)) == 2.5
    body = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=admin, params={"year": 2026})).json()
    assert body["workdays_per_week"] == 2.5 and body["suggested_entitled_days"] == 15


@pytest.mark.parametrize(
    ("weeks", "expected"),
    [
        ([WEEK_A, WEEK_B], 2.5),
        ([WEEK_A, WEEK_A], 3),  # ganzzahlig bleibt ganzzahlig
        ([[8, 8, 8, 8, 8, 0, 0], [8, 8, 8, 8, 0, 0, 0], [8, 8, 8, 0, 0, 0, 0]], 4),
        ([[8, 0, 0, 0, 0, 0, 0], [0] * 7, [0] * 7, [0] * 7], 0.25),
        ([[8, 8, 8, 8, 8, 8, 0], [8, 8, 8, 8, 8, 0, 0]], 5.5),
    ],
)
def test_workdays_of_rotation(weeks: list, expected: float) -> None:
    version = _version(rotation_minutes=serialize_rotation([[h * 60 for h in week] for week in weeks]))
    assert _workdays_of(version) == expected
    assert isinstance(_workdays_of(version), int) == (expected == int(expected))


async def test_holiday_is_credited_only_on_rotation_workdays(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    db_session.add_all([Holiday(date=date(2026, 10, 8), name="Soll-Tag"), Holiday(date=date(2026, 10, 15), name="freier Tag")])
    await db_session.commit()
    assert (await _put(client, admin, employee.id)).status_code == 200
    days = await _days(client, admin, employee.id, "2026-10-08", "2026-10-15")
    # Do der Woche 2: Soll 8 Std. -> gutgeschrieben; Do der Woche 1: frei -> keine Gutschrift
    assert (days["2026-10-08"]["status"], days["2026-10-08"]["target_minutes"], days["2026-10-08"]["actual_minutes"]) == ("HOLIDAY", 480, 480)
    assert not days["2026-10-15"]["target_minutes"] and not days["2026-10-15"]["actual_minutes"]


async def test_month_report_and_payroll_export(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client, termination=date(2026, 10, 31))
    assert (await _put(client, admin, employee.id)).status_code == 200
    await _work(client, admin, employee.id, "2026-10-08")
    await _work(client, admin, employee.id, "2026-10-12", "08:00", "17:00")

    # Oktober 2026: Woche 2 am 08./09. und 22./23. (4 Tage), Woche 1 am 12.–14. und 26.–28. (6 Tage)
    report = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 10)
    assert report.target_minutes == 10 * 480
    assert report.actual_minutes == 480 + 540
    targets = {d.day.isoformat(): d.target_minutes for d in report.days if d.target_minutes}
    assert sorted(targets) == [
        "2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14",
        "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27", "2026-10-28",
    ]
    pdf = await client.get(f"/employees/{employee.id}/month-report", headers=admin, params={"year": 2026, "month": 10})
    assert pdf.status_code == 200 and pdf.headers["content-type"].startswith("application/pdf")

    row = _csv_row(await client.get("/payroll-export", headers=admin, params={"employee_ids": [employee.id], "from": "2026-10-01", "to": "2026-10-31"}))
    assert row["Soll (Std.)"] == "80,00" and row["Ist (Std.)"] == "17,00" and row["Saldo (Std.)"] == "-63,00"


async def test_absence_stats_count_rotation_workdays(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, admin, employee.id, valid_from="2026-09-28")).status_code == 200
    r = await client.post("/absences", headers=admin, json={"employee_id": employee.id, "type": "SICK", "date_from": "2026-10-05", "date_to": "2026-10-11"})
    assert r.status_code == 201
    stats = (await client.get("/reports/absence-stats", headers=admin, params={"year": 2026})).json()
    october = next(m for m in stats["months"] if m["month"] == 10)
    assert october["sick_days"] == 2  # nur Do/Fr der Woche 2
    row = next(e for e in stats["employees"] if e["employee_id"] == employee.id)
    assert row["sick_days"] == 2


async def test_shift_plan_entry_takes_precedence(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    (await get_or_create_settings(db_session, 1)).shift_planning_enabled = True
    await db_session.commit()
    assert (await _put(client, admin, employee.id)).status_code == 200
    # Mo 05.10. (Woche 2: frei) wird im Schichtplan zum Arbeitstag, Do 08.10. (Soll) zum freien Tag.
    r = await client.put(f"/employees/{employee.id}/shift-plan-entries/2026-10-05", headers=admin, json={"is_workday": True, "target_minutes": 300})
    assert r.status_code == 200, r.text
    r = await client.put(f"/employees/{employee.id}/shift-plan-entries/2026-10-08", headers=admin, json={"is_workday": False})
    assert r.status_code == 200, r.text
    assert await _targets(client, admin, employee.id, "2026-10-05", "2026-10-11") == [300, 0, 0, 0, 480, 0, 0]


async def test_locked_month_blocks_the_change(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    assert (await _put(client, admin, employee.id)).status_code == 200
    db_session.add(PeriodClosure(tenant_id=1, employee_id=employee.id, year=2026, month=10, status=PeriodStatus.CLOSED, target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=date(2026, 11, 1)))
    await db_session.commit()
    r = await _put(client, admin, employee.id, **AB, rotation_start="2026-10-05")
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_LOCKED"
    assert (await _put(client, admin, employee.id, valid_from="2026-11-01", **AB, rotation_start="2026-10-05")).status_code == 200


async def test_new_employee_with_rotation_model(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    location = (await db_session.execute(select(Location))).scalars().first()
    r = await client.post(
        "/employees", headers=admin,
        json={
            "first_name": "Max", "last_name": "Neu", "employee_number": "E2", "location_id": location.id,
            "hire_date": "2026-10-01", "work_time_model": AB,
        },
    )
    assert r.status_code == 201, r.text
    model = (await client.get(f"/employees/{r.json()['id']}/work-time-model", headers=admin)).json()
    assert model["rotation_minutes"] == [[480, 480, 480, 0, 0, 0, 0], [0, 0, 0, 480, 480, 0, 0]]
    assert model["rotation_start"] == "2026-09-28"  # Woche des Eintritts


# ---------------------------------------------------------------------------------------------
# Arbeitszeitmodelle (Profile)
# ---------------------------------------------------------------------------------------------


async def test_profile_with_rotation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    profile = await _profile(client, admin, **AB, rotation_start="2026-09-30")
    assert profile["rotation_minutes"] == [[480, 480, 480, 0, 0, 0, 0], [0, 0, 0, 480, 480, 0, 0]]
    assert profile["rotation_start"] == "2026-09-28" and profile["weekly_minutes"] == 1200

    model = await _assign(client, admin, employee.id, profile["id"])
    assert model["profile_id"] == profile["id"] and model["rotation_start"] == "2026-09-28"
    assert await _targets(client, admin, employee.id, "2026-10-05", "2026-10-18") == [0, 0, 0, 480, 480, 0, 0, 480, 480, 480, 0, 0, 0, 0]

    listed = (await client.get("/work-time-profiles", headers=admin)).json()
    assert listed[0]["rotation_minutes"] == profile["rotation_minutes"]
    history = (await client.get(f"/work-time-profiles/{profile['id']}/history", headers=admin)).json()
    assert history[0]["rotation_minutes"] == profile["rotation_minutes"] and history[0]["rotation_start"] == "2026-09-28"


async def test_profile_without_start_begins_in_the_current_week(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    profile = await _profile(client, admin)
    assert profile["rotation_start"] == monday_of(date.today()).isoformat()


async def test_assignment_date_does_not_shift_the_rotation(client: AsyncClient, db_session: AsyncSession) -> None:
    """Der Turnus hängt am Modell, nicht am Tag der Zuweisung: zwei Mitarbeiter mit verschiedenen
    Zuweisungstagen arbeiten im selben Rhythmus."""
    employee, admin = await _setup(db_session, client)
    other = Employee(location_id=employee.location_id, first_name="Max", last_name="Zweiter", employee_number="E2", auto_break_enabled=False)
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    profile = await _profile(client, admin, **AB, rotation_start="2026-09-28")
    await _assign(client, admin, employee.id, profile["id"], "2026-10-01")
    await _assign(client, admin, other.id, profile["id"], "2026-10-12")
    for employee_id in (employee.id, other.id):
        assert await _targets(client, admin, employee_id, "2026-10-12", "2026-10-25") == [480, 480, 480, 0, 0, 0, 0, 0, 0, 0, 480, 480, 0, 0]


async def test_profile_change_reaches_assigned_employees(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    profile = await _profile(client, admin, "Vollzeit", weekly_hours=40, weekdays=[0, 1, 2, 3, 4])
    await _assign(client, admin, employee.id, profile["id"])
    assert await _targets(client, admin, employee.id, "2026-10-19", "2026-10-25") == [480] * 5 + [0, 0]

    r = await client.put(
        f"/work-time-profiles/{profile['id']}/model", headers=admin, json={**AB, "valid_from": "2026-10-19"}
    )
    assert r.status_code == 200, r.text
    # davor unverändert, ab 19.10. Turnus (Woche 1 = Woche des Stichtags)
    assert await _targets(client, admin, employee.id, "2026-10-12", "2026-10-18") == [480] * 5 + [0, 0]
    assert await _targets(client, admin, employee.id, "2026-10-19", "2026-11-01") == [480, 480, 480, 0, 0, 0, 0, 0, 0, 0, 480, 480, 0, 0]
    rows = (await db_session.execute(select(EmployeeDefaultShift).order_by(EmployeeDefaultShift.valid_from))).scalars().all()
    assert [(row.valid_from, row.rotation_minutes is not None, row.rotation_start) for row in rows] == [
        (date(2026, 10, 1), False, None), (date(2026, 10, 19), True, date(2026, 10, 19)),
    ]
    model = (await client.get(f"/employees/{employee.id}/work-time-model", headers=admin)).json()
    assert model["profile_id"] == profile["id"]

    # Nur der Startpunkt ändert sich: auch das wird nachgezogen.
    r = await client.put(
        f"/work-time-profiles/{profile['id']}/model", headers=admin, json={**AB, "rotation_start": "2026-10-12", "valid_from": "2026-10-19"}
    )
    assert r.status_code == 200, r.text
    assert await _targets(client, admin, employee.id, "2026-10-19", "2026-10-25") == [0, 0, 0, 480, 480, 0, 0]


async def test_profile_change_rebuilds_the_balance(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client, termination=date(2026, 10, 9))
    profile = await _profile(client, admin, **AB, rotation_start="2026-09-28")
    await _assign(client, admin, employee.id, profile["id"])
    await _work(client, admin, employee.id, "2026-10-05")
    assert await _balance(client, admin, employee.id) == 480 - 960
    r = await client.put(
        f"/work-time-profiles/{profile['id']}/model", headers=admin, json={**AB, "rotation_start": "2026-10-05", "valid_from": "2026-10-01"}
    )
    assert r.status_code == 200, r.text
    assert await _balance(client, admin, employee.id) == -960


async def test_profile_change_respects_locked_months(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    profile = await _profile(client, admin, **AB, rotation_start="2026-09-28")
    await _assign(client, admin, employee.id, profile["id"])
    db_session.add(PeriodClosure(tenant_id=1, employee_id=employee.id, year=2026, month=10, status=PeriodStatus.CLOSED, target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=date(2026, 11, 1)))
    await db_session.commit()
    r = await client.put(
        f"/work-time-profiles/{profile['id']}/model", headers=admin, json={**AB, "rotation_start": "2026-10-05", "valid_from": "2026-10-01"}
    )
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_LOCKED"
    assert await _targets(client, admin, employee.id, "2026-10-05", "2026-10-11") == [0, 0, 0, 480, 480, 0, 0]


@pytest.mark.parametrize(
    "model",
    [
        {"rotation_weeks": [WEEK_A]},
        {"rotation_weeks": [WEEK_A] * 5},
        {"rotation_weeks": [[0] * 7, [0] * 7]},
        {"rotation_weeks": [WEEK_A, [0, 0, 30, 0, 0, 0, 0]]},
        {"rotation_weeks": [WEEK_A, WEEK_B], "flexible": True},
        {"weekly_hours": 40, "weekdays": [0], "rotation_start": "2026-10-05"},
    ],
)
async def test_profile_validation(client: AsyncClient, db_session: AsyncSession, model: dict) -> None:
    _, admin = await _setup(db_session, client)
    r = await client.post("/work-time-profiles", headers=admin, json={"name": "Ungültig", **model})
    assert r.status_code == 422, r.text
    assert (await client.get("/work-time-profiles", headers=admin)).json() == []


async def test_profile_audit_log(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    await _profile(client, admin, **AB, rotation_start="2026-09-28")
    details = [e.detail for e in (await db_session.execute(select(AuditLogEntry))).scalars().all() if e.detail and "Wechselwoche" in e.detail]
    assert any("Turnus über 2 Wochen" in detail and "Woche 1 ab 28.09.2026" in detail for detail in details)
