"""Mehrere feste Pausenzeiten je Arbeitszeitmodell (z.B. Frühstück 09:00–09:15 und Mittag 12:00–12:30):
jede wird abgezogen, soweit der Mitarbeiter in ihr anwesend war; die gesetzliche Staffel bleibt
Untergrenze. Eine einzelne Pausenzeit bleibt wie bisher in fixed_break_start/-end."""
from datetime import date, time
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmployeeDefaultShift
from app.schemas.break_rule import (
    MAX_BREAK_WINDOWS,
    BreakWindow,
    check_windows,
    fixed_break_windows,
    parse_break_windows,
    serialize_break_windows,
)
from app.schemas.work_time_model import WorkTimeModelInput, WorkTimeModelSetRequest
from tests.test_fixed_breaks import DAY, _day, _punches, _setup

T = time.fromisoformat
BASE = {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4]}
TWO = [{"start": "12:00", "end": "12:30"}, {"start": "09:00", "end": "09:15"}]  # absichtlich unsortiert


# --- Hilfsfunktionen ------------------------------------------------------------------------------


def test_windows_are_sorted_and_must_not_overlap() -> None:
    assert check_windows([(T("12:00"), T("12:30")), (T("09:00"), T("09:15"))]) == [(T("09:00"), T("09:15")), (T("12:00"), T("12:30"))]
    assert check_windows([(T("09:00"), T("09:15")), (T("09:15"), T("09:30"))])  # direkt hintereinander: erlaubt
    with pytest.raises(ValueError, match="überschneiden"):
        check_windows([(T("09:00"), T("10:00")), (T("09:30"), T("10:30"))])


def test_serialize_and_parse() -> None:
    windows = [(T("09:00"), T("09:15")), (T("12:00"), T("12:30"))]
    assert serialize_break_windows(windows) == "09:00-09:15,12:00-12:30"
    assert parse_break_windows("09:00-09:15,12:00-12:30") == windows
    assert serialize_break_windows(windows[:1]) is None  # eine Pausenzeit: alte Spalten
    assert serialize_break_windows([]) is None
    assert parse_break_windows(None) == [] and parse_break_windows("") == []


def test_fixed_break_windows_of_a_version() -> None:
    many = SimpleNamespace(fixed_break_windows="09:00-09:15,12:00-12:30", fixed_break_start=T("09:00"), fixed_break_end=T("09:15"))
    assert fixed_break_windows(many) == [(T("09:00"), T("09:15")), (T("12:00"), T("12:30"))]
    one = SimpleNamespace(fixed_break_windows=None, fixed_break_start=T("12:00"), fixed_break_end=T("12:30"))
    assert fixed_break_windows(one) == [(T("12:00"), T("12:30"))]
    template = SimpleNamespace(fixed_break_start=T("10:00"), fixed_break_end=T("10:30"))  # Schichtvorlage ohne Spalte
    assert fixed_break_windows(template) == [(T("10:00"), T("10:30"))]
    assert fixed_break_windows(SimpleNamespace(fixed_break_windows=None, fixed_break_start=None, fixed_break_end=None)) == []


def test_break_window_validation() -> None:
    with pytest.raises(ValidationError, match="vor ihrem Ende"):
        BreakWindow(start=T("13:00"), end=T("12:00"))
    with pytest.raises(ValidationError, match="höchstens 4 Stunden"):
        BreakWindow(start=T("08:00"), end=T("12:30"))


# --- Eingaben -------------------------------------------------------------------------------------


def test_input_with_several_windows() -> None:
    model = WorkTimeModelInput(**BASE, break_windows=TWO)
    assert model.break_window_list == [(T("09:00"), T("09:15")), (T("12:00"), T("12:30"))]
    assert model.break_start is None and model.break_end is None
    assert model.break_label == ", Pause 09:00–09:15, 12:00–12:30"


def test_single_window_in_the_list_becomes_the_old_fields() -> None:
    model = WorkTimeModelInput(**BASE, break_windows=[{"start": "12:00", "end": "12:30"}])
    assert (model.break_start, model.break_end, model.break_windows) == (T("12:00"), T("12:30"), None)
    assert model.break_label == ", Pause 12:00–12:30"


def test_input_errors() -> None:
    for extra in (
        {"break_windows": TWO, "break_start": "13:00", "break_end": "13:30"},
        {"break_windows": TWO, "break_minutes": 30},
        {"break_windows": [{"start": "09:00", "end": "10:00"}, {"start": "09:30", "end": "10:30"}]},
        {"break_windows": [{"start": f"{8 + i:02d}:00", "end": f"{8 + i:02d}:10"} for i in range(MAX_BREAK_WINDOWS + 1)]},
        {"break_windows": []},
    ):
        with pytest.raises(ValidationError):
            WorkTimeModelInput(**BASE, **extra)


def test_from_input_keeps_all_windows() -> None:
    copy = WorkTimeModelSetRequest.from_input(WorkTimeModelInput(**BASE, break_windows=TWO), date(2026, 11, 1))
    assert copy.break_window_list == [(T("09:00"), T("09:15")), (T("12:00"), T("12:30"))]


# --- Über die API ---------------------------------------------------------------------------------


async def _versions(db_session: AsyncSession, employee_id: int) -> list[EmployeeDefaultShift]:
    rows = (await db_session.execute(
        select(EmployeeDefaultShift).where(EmployeeDefaultShift.employee_id == employee_id).order_by(EmployeeDefaultShift.valid_from)
    )).scalars().all()
    for row in rows:
        await db_session.refresh(row)
    return list(rows)


async def test_employee_with_two_fixed_breaks(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.put(f"/employees/{employee.id}/work-time-model", headers=admin, json={**BASE, "break_windows": TWO, "valid_from": "2026-10-01"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["break_windows"] == [{"start": "09:00:00", "end": "09:15:00"}, {"start": "12:00:00", "end": "12:30:00"}]
    assert (body["break_start"], body["break_end"], body["break_minutes"]) == ("09:00:00", "09:15:00", None)
    row = (await _versions(db_session, employee.id))[0]
    assert row.fixed_break_windows == "09:00-09:15,12:00-12:30"

    # ganzer Tag: beide Pausen (15 + 30 Min.)
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "16:00"))
    assert await _day(db_session, employee) == (435, 45)
    # erst ab 10:00 da: nur die Mittagspause; die gesetzliche (6 Std. → 30 Min.) ist damit erfüllt
    later = date(2026, 10, 7)
    await _punches(db_session, employee, ("COME", "10:00"), ("GO", "16:00"), day=later)
    assert await _day(db_session, employee, later) == (330, 30)
    # nur vormittags bis 11:00: Frühstückspause 15 Min., gesetzlich nichts nötig
    morning = date(2026, 10, 8)
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "11:00"), day=morning)
    assert await _day(db_session, employee, morning) == (165, 15)

    entries = (await client.get("/audit-log", headers=admin)).json()
    assert any(", Pause 09:00–09:15, 12:00–12:30" in e["detail"] for e in entries if e["action"] == "EMPLOYEE_WORK_TIME_MODEL_SET")


async def test_one_window_keeps_the_old_storage_and_minutes_clear_the_list(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"
    r = await client.put(url, headers=admin, json={**BASE, "break_windows": [{"start": "12:00", "end": "12:30"}], "valid_from": "2026-10-01"})
    assert r.status_code == 200, r.text
    assert r.json()["break_windows"] == [{"start": "12:00:00", "end": "12:30:00"}]
    row = (await _versions(db_session, employee.id))[0]
    assert (row.fixed_break_start, row.fixed_break_end, row.fixed_break_windows) == (T("12:00"), T("12:30"), None)

    # nachträglich zwei Pausenzeiten, dann wieder feste Minuten
    version_id = (await client.get(f"{url}/history", headers=admin)).json()[0]["id"]
    r = await client.put(f"{url}/versions/{version_id}", headers=admin, json={**BASE, "break_windows": TWO, "valid_from": "2026-10-01"})
    assert r.status_code == 200 and len(r.json()[0]["break_windows"]) == 2
    r = await client.put(f"{url}/versions/{version_id}", headers=admin, json={**BASE, "break_minutes": 45, "valid_from": "2026-10-01"})
    assert r.status_code == 200, r.text
    assert (r.json()[0]["break_windows"], r.json()[0]["break_minutes"]) == (None, 45)
    row = (await _versions(db_session, employee.id))[0]
    assert (row.fixed_break_start, row.fixed_break_windows) == (None, None)


async def test_profile_with_two_breaks_reaches_assigned_employees(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.post("/work-time-profiles", headers=admin, json={"name": "Werk", **BASE, "break_windows": TWO})
    assert r.status_code == 201, r.text
    assert len(r.json()["break_windows"]) == 2
    r = await client.put(f"/employees/{employee.id}/work-time-profile", headers=admin, json={"profile_id": r.json()["id"], "valid_from": "2026-10-01"})
    assert r.status_code == 200, r.text
    assert len(r.json()["break_windows"]) == 2
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "16:00"))
    assert await _day(db_session, employee, DAY) == (435, 45)


async def test_api_rejects_invalid_windows(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"
    for extra in (
        {"break_windows": [{"start": "09:00", "end": "10:00"}, {"start": "09:30", "end": "10:30"}]},
        {"break_windows": TWO, "break_minutes": 30},
        {"break_windows": [{"start": "12:00"}]},
    ):
        r = await client.put(url, headers=admin, json={**BASE, **extra, "valid_from": "2026-10-01"})
        assert r.status_code == 422, extra
