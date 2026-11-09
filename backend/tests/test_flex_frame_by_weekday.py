"""Gleitzeit-Rahmen je Wochentag – im Arbeitszeitmodell und individuell am Mitarbeiter, z.B. freitags
kürzer oder an einzelnen Tagen ohne Rahmen. Wirkt nur auf den Hinweis "außerhalb Gleitzeit-Rahmen"."""
import uuid
from datetime import date, time

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AuditAction, AuditLogEntry, Employee, EmployeeDefaultShift, HrRole, Location
from app.schemas.core_time import (
    CoreTimeDay,
    FlexFrameDay,
    day_windows,
    describe_day_windows,
    parse_day_windows,
    serialize_day_windows,
)
from app.schemas.work_time_model import WorkTimeModelInput, WorkTimeModelSetRequest, WorkTimeProfileCreateRequest
from app.services.auth_service import hash_password

FULL_TIME = {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4]}
LONG = {"start": "07:00", "end": "19:00"}
FRIDAY_SHORT = {"start": "07:00", "end": "14:00"}
# Mo, Di, Do lang, Mi ohne Rahmen, Fr kurz, Wochenende ohne
FRAME_DAYS = [LONG, LONG, None, LONG, FRIDAY_SHORT, None, None]
MONDAY, WEDNESDAY, THURSDAY, FRIDAY = "2026-10-05", "2026-10-07", "2026-10-08", "2026-10-09"
T = time.fromisoformat


@pytest.fixture(autouse=True)
def _rules_changed_before_test_days(monkeypatch):
    """Pünktlichkeits-Hinweise gelten erst ab der letzten Regeländerung – hier ab 01.10.2026."""
    import app.api.settings as settings_api

    class _Date(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 1)

    monkeypatch.setattr(settings_api, "date", _Date)


# --- Hilfsfunktionen (ohne Datenbank) -------------------------------------------------------------


def test_parse_and_serialize_round_trip() -> None:
    days = [FlexFrameDay(start=T("07:00"), end=T("19:00")), None, None, None, FlexFrameDay(start=T("07:00"), end=T("14:00")), None, None]
    text = serialize_day_windows(days)
    assert text == "07:00-19:00,,,,07:00-14:00,,"
    parsed = parse_day_windows(text)
    assert parsed[0] == (T("07:00"), T("19:00")) and parsed[4] == (T("07:00"), T("14:00"))
    assert parsed[1] is None and len(parsed) == 7


def test_parse_edge_cases() -> None:
    assert parse_day_windows(None) is None
    assert parse_day_windows("") is None
    # kürzer gespeichert: mit "kein Fenster" aufgefüllt
    assert parse_day_windows("08:00-16:00") == [(T("08:00"), T("16:00"))] + [None] * 6
    assert serialize_day_windows(None) is None


def test_day_windows_sources() -> None:
    assert day_windows(None, T("07:00"), T("19:00")) == [(T("07:00"), T("19:00"))] * 7
    assert day_windows(None, None, None) == [None] * 7
    assert day_windows(None, T("07:00"), None) == [None] * 7
    mixed = [CoreTimeDay(start=T("09:00"), end=T("15:00")), (T("10:00"), T("12:00")), None, None, None, None, None]
    assert day_windows(mixed, T("01:00"), T("02:00"))[:3] == [(T("09:00"), T("15:00")), (T("10:00"), T("12:00")), None]


def test_describe_day_windows_groups_equal_days() -> None:
    days = [(T("07:00"), T("19:00"))] * 4 + [(T("07:00"), T("14:00")), None, None]
    assert describe_day_windows(days) == "Mo–Do 07:00–19:00, Fr 07:00–14:00, Sa–So ohne"
    alternating = [(T("08:00"), T("16:00")), None] * 3 + [None]
    assert describe_day_windows(alternating) == (
        "Mo 08:00–16:00, Di ohne, Mi 08:00–16:00, Do ohne, Fr 08:00–16:00, Sa–So ohne"
    )
    assert describe_day_windows([None] * 7, empty="keiner") == "Mo–So keiner"


def test_day_window_errors_name_the_kind() -> None:
    with pytest.raises(ValidationError, match="Gleitzeit-Rahmen: der Beginn muss vor dem Ende liegen"):
        FlexFrameDay(start=T("19:00"), end=T("07:00"))
    with pytest.raises(ValidationError, match="Kernzeit: der Beginn muss vor dem Ende liegen"):
        CoreTimeDay(start=T("12:00"), end=T("12:00"))


# --- Eingaben prüfen -----------------------------------------------------------------------------


def _profile_input(**fields) -> WorkTimeProfileCreateRequest:
    return WorkTimeProfileCreateRequest(name="M", **FULL_TIME, **fields)


def test_custom_frame_per_weekday_drops_single_frame() -> None:
    model = _profile_input(flex_frame_mode="CUSTOM", flex_frame_start="06:00", flex_frame_end="20:00", flex_frame_days=FRAME_DAYS)
    assert model.flex_frame_start is None and model.flex_frame_end is None
    assert model.flex_frame_days[4].end == T("14:00") and model.flex_frame_days[2] is None


def test_frame_days_only_with_custom_mode() -> None:
    for mode in ("TENANT", "NONE"):
        model = _profile_input(flex_frame_mode=mode, flex_frame_days=FRAME_DAYS, flex_frame_start="06:00", flex_frame_end="20:00")
        assert model.flex_frame_days is None and model.flex_frame_start is None


def test_frame_validation_errors() -> None:
    with pytest.raises(ValidationError, match="bitte Beginn und Ende angeben"):
        _profile_input(flex_frame_mode="CUSTOM")
    with pytest.raises(ValidationError, match="Beginn muss vor dem Ende"):
        _profile_input(flex_frame_mode="CUSTOM", flex_frame_start="19:00", flex_frame_end="07:00")
    with pytest.raises(ValidationError):
        _profile_input(flex_frame_mode="CUSTOM", flex_frame_days=FRAME_DAYS[:6])
    with pytest.raises(ValidationError, match="Gleitzeit-Rahmen"):
        _profile_input(flex_frame_mode="CUSTOM", flex_frame_days=[{"start": "19:00", "end": "07:00"}, *FRAME_DAYS[1:]])


def test_core_time_must_fit_the_frame_of_each_day() -> None:
    # einheitliche Kernzeit 09–15, freitags endet der Rahmen um 14:00
    with pytest.raises(ValidationError, match="an jedem Tag innerhalb des Gleitzeit-Rahmens"):
        _profile_input(core_time_mode="CUSTOM", core_time_start="09:00", core_time_end="15:00",
                       flex_frame_mode="CUSTOM", flex_frame_days=FRAME_DAYS)
    # Kernzeit freitags kürzer: passt
    core_days = [{"start": "09:00", "end": "15:00"}] * 4 + [{"start": "09:00", "end": "12:00"}, None, None]
    _profile_input(core_time_mode="CUSTOM", core_time_days=core_days, flex_frame_mode="CUSTOM", flex_frame_days=FRAME_DAYS)
    # Tag ohne Rahmen (Mittwoch) begrenzt die Kernzeit nicht
    wide_wednesday = [*core_days[:2], {"start": "06:00", "end": "21:00"}, *core_days[3:]]
    _profile_input(core_time_mode="CUSTOM", core_time_days=wide_wednesday, flex_frame_mode="CUSTOM", flex_frame_days=FRAME_DAYS)
    # einheitlicher Rahmen und einheitliche Kernzeit: bisherige Meldung
    with pytest.raises(ValidationError, match="Die Kernzeit muss innerhalb des Gleitzeit-Rahmens liegen"):
        _profile_input(core_time_mode="CUSTOM", core_time_start="07:00", core_time_end="15:00",
                       flex_frame_mode="CUSTOM", flex_frame_start="08:00", flex_frame_end="18:00")
    # Kernzeit wie Einstellungen: hier nicht prüfbar, also erlaubt
    _profile_input(flex_frame_mode="CUSTOM", flex_frame_days=FRAME_DAYS)


def test_employee_input_without_frame_means_unchanged() -> None:
    model = WorkTimeModelSetRequest(**FULL_TIME, valid_from="2026-10-01")
    assert model.flex_frame_mode is None and model.flex_frame_days is None
    profile = _profile_input()
    assert profile.flex_frame_mode == "TENANT"  # Modelle setzen den Rahmen immer


def test_from_input_keeps_frame_days() -> None:
    source = WorkTimeModelInput(**FULL_TIME, flex_frame_mode="CUSTOM", flex_frame_days=FRAME_DAYS)
    copy = WorkTimeModelSetRequest.from_input(source, date(2026, 11, 1))
    assert copy.flex_frame_mode == "CUSTOM" and copy.flex_frame_days[4].end == T("14:00")
    assert copy.flex_frame_days[2] is None and len(copy.flex_frame_days) == 7  # "kein Rahmen" bleibt erhalten


# --- Über die API --------------------------------------------------------------------------------


async def _setup(db_session: AsyncSession, client: AsyncClient) -> dict:
    db_session.add(Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    # Firma: Rahmen 06–20, keine Toleranz, alle Hinweise an – Kernzeit keine
    r = await client.patch(
        "/settings", headers=admin,
        json={"flex_frame_start": "06:00", "flex_frame_end": "20:00", "late_tolerance_minutes": 0, "disabled_day_flags": []},
    )
    assert r.status_code == 200, r.text
    return admin


async def _employee(db_session: AsyncSession, number: str) -> Employee:
    location = (await db_session.execute(select(Location))).scalars().first()
    if location is None:
        location = Location(name="Zentrale", timezone="UTC")
        db_session.add(location)
        await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Gleit", last_name=number, employee_number=number, auto_break_enabled=False)
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _work(client: AsyncClient, admin: dict, employee_id: int, day: str, come: str, go: str) -> None:
    for punch_type, clock in (("COME", come), ("GO", go)):
        r = await client.post(
            "/punches", headers=admin,
            json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{day}T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text


async def _flags(client: AsyncClient, admin: dict, employee_id: int, first: str = MONDAY, last: str = FRIDAY) -> dict[str, list[str]]:
    r = await client.get(f"/employees/{employee_id}/timesheet", headers=admin, params={"from": first, "to": last})
    assert r.status_code == 200, r.text
    return {d["work_date"]: d["flags"] for d in r.json()}


async def _work_week(client: AsyncClient, admin: dict, employee_id: int) -> None:
    """Mo 07:30–15:30 (im Rahmen), Mi 05:00–13:00 (Mi ohne eigenen Rahmen), Do und Fr 07:30–15:30
    (Fr endet der Rahmen um 14:00)."""
    await _work(client, admin, employee_id, MONDAY, "07:30", "15:30")
    await _work(client, admin, employee_id, WEDNESDAY, "05:00", "13:00")
    await _work(client, admin, employee_id, THURSDAY, "07:30", "15:30")
    await _work(client, admin, employee_id, FRIDAY, "07:30", "15:30")


async def _audit_details(db_session: AsyncSession, action: AuditAction) -> list[str]:
    rows = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == action))).scalars().all()
    return [row.detail or "" for row in rows]


async def test_profile_with_frame_per_weekday(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _setup(db_session, client)
    employee = await _employee(db_session, "P1")
    r = await client.post(
        "/work-time-profiles", headers=admin,
        json={"name": "Büro Fr kurz", **FULL_TIME, "flex_frame_mode": "CUSTOM", "flex_frame_days": FRAME_DAYS},
    )
    assert r.status_code == 201, r.text
    profile = r.json()
    assert profile["flex_frame_mode"] == "CUSTOM" and profile["flex_frame_start"] is None
    assert profile["flex_frame_days"][4] == {"start": "07:00:00", "end": "14:00:00"}
    assert profile["flex_frame_days"][2] is None
    details = await _audit_details(db_session, AuditAction.SETTINGS_CHANGED)
    assert any("Gleitzeit-Rahmen je Wochentag (Mo–Di 07:00–19:00, Mi ohne, Do 07:00–19:00, Fr 07:00–14:00, Sa–So ohne)" in d for d in details)

    r = await client.put(f"/employees/{employee.id}/work-time-profile", headers=admin, json={"profile_id": profile["id"], "valid_from": "2026-10-01"})
    assert r.status_code == 200, r.text
    assert r.json()["flex_frame_days"][4]["end"] == "14:00:00"  # in die Fassung des Mitarbeiters übernommen

    await _work_week(client, admin, employee.id)
    flags = await _flags(client, admin, employee.id)
    assert flags[MONDAY] == [] and flags[THURSDAY] == []
    assert flags[FRIDAY] == ["OUTSIDE_FLEX_FRAME"]  # Gehen 15:30, Rahmen bis 14:00
    assert flags[WEDNESDAY] == []  # an diesem Tag kein Rahmen – auch nicht der der Firma

    # Modell ab Stichtag wieder mit einem Rahmen für alle Tage: gilt für den Zugewiesenen ab dann
    r = await client.put(
        f"/work-time-profiles/{profile['id']}/model", headers=admin,
        json={**FULL_TIME, "flex_frame_mode": "CUSTOM", "flex_frame_start": "07:00", "flex_frame_end": "19:00", "valid_from": "2026-10-12"},
    )
    assert r.status_code == 200, r.text
    model = (await client.get(f"/employees/{employee.id}/work-time-model", headers=admin)).json()
    assert model["flex_frame_days"] is None and model["flex_frame_start"] == "07:00:00"
    await _work(client, admin, employee.id, "2026-10-16", "07:30", "15:30")
    assert (await _flags(client, admin, employee.id, "2026-10-16", "2026-10-16"))["2026-10-16"] == []
    # Die Woche davor bleibt beim Rahmen je Wochentag
    assert (await _flags(client, admin, employee.id))[FRIDAY] == ["OUTSIDE_FLEX_FRAME"]


async def test_profile_frame_validation_over_api(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _setup(db_session, client)
    bad = [
        {"flex_frame_mode": "CUSTOM", "flex_frame_days": FRAME_DAYS[:5]},
        {"flex_frame_mode": "CUSTOM", "flex_frame_days": [{"start": "19:00", "end": "07:00"}, *FRAME_DAYS[1:]]},
        {"flex_frame_mode": "CUSTOM", "flex_frame_days": FRAME_DAYS, "core_time_mode": "CUSTOM", "core_time_start": "09:00", "core_time_end": "15:00"},
    ]
    for index, extra in enumerate(bad):
        r = await client.post("/work-time-profiles", headers=admin, json={"name": f"X{index}", **FULL_TIME, **extra})
        assert r.status_code == 422, extra


async def test_individual_frame_per_weekday(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _setup(db_session, client)
    employee = await _employee(db_session, "I1")
    r = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin,
        json={**FULL_TIME, "valid_from": "2026-10-01", "flex_frame_mode": "CUSTOM", "flex_frame_days": FRAME_DAYS},
    )
    assert r.status_code == 200, r.text
    assert r.json()["flex_frame_mode"] == "CUSTOM" and r.json()["flex_frame_days"][0]["start"] == "07:00:00"
    details = await _audit_details(db_session, AuditAction.EMPLOYEE_WORK_TIME_MODEL_SET)
    assert any("Gleitzeit-Rahmen je Wochentag" in d for d in details)

    await _work_week(client, admin, employee.id)
    flags = await _flags(client, admin, employee.id)
    assert flags[FRIDAY] == ["OUTSIDE_FLEX_FRAME"] and flags[WEDNESDAY] == [] and flags[MONDAY] == []

    # Neue Fassung ohne Angaben zum Rahmen: übernimmt den bisherigen (je Wochentag)
    r = await client.put(f"/employees/{employee.id}/work-time-model", headers=admin, json={**FULL_TIME, "weekly_hours": 38, "valid_from": "2026-10-12"})
    assert r.status_code == 200, r.text
    assert r.json()["flex_frame_mode"] == "CUSTOM" and r.json()["flex_frame_days"][4]["end"] == "14:00:00"

    # Nachträglich "kein Rahmen": der Freitag ist kein Hinweis mehr
    history = (await client.get(f"/employees/{employee.id}/work-time-model/history", headers=admin)).json()
    first = next(v for v in history if v["valid_from"] == "2026-10-01")
    r = await client.put(
        f"/employees/{employee.id}/work-time-model/versions/{first['id']}", headers=admin,
        json={**FULL_TIME, "valid_from": "2026-10-01", "flex_frame_mode": "NONE"},
    )
    assert r.status_code == 200, r.text
    edited = next(v for v in r.json() if v["valid_from"] == "2026-10-01")
    assert edited["flex_frame_mode"] == "NONE" and edited["flex_frame_days"] is None
    assert (await _flags(client, admin, employee.id))[FRIDAY] == []


async def test_individual_frame_single_and_tenant(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _setup(db_session, client)
    employee = await _employee(db_session, "I2")
    r = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin,
        json={**FULL_TIME, "valid_from": "2026-10-01", "flex_frame_mode": "CUSTOM", "flex_frame_start": "08:00", "flex_frame_end": "16:00"},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["flex_frame_start"], r.json()["flex_frame_days"]) == ("08:00:00", None)
    await _work(client, admin, employee.id, MONDAY, "07:30", "15:30")
    assert (await _flags(client, admin, employee.id))[MONDAY] == ["OUTSIDE_FLEX_FRAME"]  # Kommen vor 08:00
    # zurück auf "wie Einstellungen" (06–20): kein Hinweis
    r = await client.put(f"/employees/{employee.id}/work-time-model", headers=admin, json={**FULL_TIME, "valid_from": "2026-10-01", "flex_frame_mode": "TENANT"})
    assert r.status_code == 200 and r.json()["flex_frame_mode"] == "TENANT" and r.json()["flex_frame_start"] is None
    assert (await _flags(client, admin, employee.id))[MONDAY] == []
    # Prüfung auch am Mitarbeiter
    r = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin,
        json={**FULL_TIME, "valid_from": "2026-10-01", "flex_frame_mode": "CUSTOM", "flex_frame_days": FRAME_DAYS,
              "core_time_mode": "CUSTOM", "core_time_start": "09:00", "core_time_end": "15:00"},
    )
    assert r.status_code == 422


async def test_editing_a_profile_version_keeps_its_frame_unless_changed(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _setup(db_session, client)
    employee = await _employee(db_session, "E1")
    profile = (await client.post(
        "/work-time-profiles", headers=admin, json={"name": "Fr kurz", **FULL_TIME, "flex_frame_mode": "CUSTOM", "flex_frame_days": FRAME_DAYS},
    )).json()
    await client.put(f"/employees/{employee.id}/work-time-profile", headers=admin, json={"profile_id": profile["id"], "valid_from": "2026-10-01"})
    version_id = (await client.get(f"/employees/{employee.id}/work-time-model/history", headers=admin)).json()[0]["id"]
    r = await client.put(
        f"/employees/{employee.id}/work-time-model/versions/{version_id}", headers=admin,
        json={**FULL_TIME, "weekly_hours": 35, "valid_from": "2026-10-01"},
    )
    assert r.status_code == 200, r.text
    assert r.json()[0]["profile_id"] is None  # jetzt individuell …
    assert r.json()[0]["flex_frame_days"][4]["end"] == "14:00:00"  # … mit dem Rahmen des Modells


async def test_legacy_default_shift_inherits_frame_days(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _setup(db_session, client)
    employee = await _employee(db_session, "L1")
    r = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin,
        json={**FULL_TIME, "valid_from": "2026-10-01", "flex_frame_mode": "CUSTOM", "flex_frame_days": FRAME_DAYS},
    )
    assert r.status_code == 200, r.text
    template = await client.post(
        "/shift-templates", headers=admin,
        json={"name": "Tag", "start_time": "08:00", "end_time": "16:30", "break_mode": "FLEXIBLE", "min_break_minutes": 30, "target_minutes": 480},
    )
    assert template.status_code == 201, template.text
    r = await client.post(
        f"/employees/{employee.id}/default-shifts", headers=admin,
        json={"shift_template_id": template.json()["id"], "valid_from": "2026-11-02", "weekdays_mask": 31},
    )
    assert r.status_code == 201, r.text
    rows = (await db_session.execute(
        select(EmployeeDefaultShift).where(EmployeeDefaultShift.employee_id == employee.id).order_by(EmployeeDefaultShift.valid_from)
    )).scalars().all()
    await db_session.refresh(rows[-1])
    assert rows[-1].valid_from == date(2026, 11, 2)
    assert (rows[-1].flex_frame_mode, rows[-1].flex_frame_days) == ("CUSTOM", "07:00-19:00,07:00-19:00,,07:00-19:00,07:00-14:00,,")
