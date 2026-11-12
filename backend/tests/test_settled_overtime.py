"""Monatlich mit dem Gehalt abgegoltene Überstunden: Mehrarbeit eines Kalendermonats bis zur Grenze
der Fassung wird dem Gleitzeitkonto nicht gutgeschrieben (Monatssaldo, fortlaufend gekappt).
Minusstunden, Korrekturbuchungen und Überstunden-Umwandlungen bleiben unberührt."""
import csv
import io
import uuid
from datetime import date, datetime

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
    HrRole,
    Location,
    OvertimeBalance,
    PeriodClosure,
    PeriodStatus,
    Tenant,
)
from app.schemas.work_time_model import WorkTimeModelInput
from app.services.auth_service import hash_password
from app.services.period_service import _report_html, build_month_report
from app.services.timesheet_service import (
    _Settlement,
    has_settled_limit,
    invalidate_balance,
    settled_between,
    settled_limit_for_month,
)

# Nur montags 8 Std. Soll: jeder Montag mit Stempelung steuert den Monatssaldo genau.
MONDAYS = [8, 0, 0, 0, 0, 0, 0]
# Montage im September/Oktober/November 2026
SEP = ["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28"]
OCT = ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]


# ---------------------------------------------------------------------------------------------
# Rechenkern
# ---------------------------------------------------------------------------------------------


def _version(valid_from: date, valid_to: date | None = None, limit: int | None = None, on_demand: bool = False) -> EmployeeDefaultShift:
    return EmployeeDefaultShift(
        employee_id=1, valid_from=valid_from, valid_to=valid_to, weekdays_mask=31, settled_overtime_minutes=limit, on_demand=on_demand
    )


def test_limit_uses_the_version_at_month_end() -> None:
    versions = [_version(date(2026, 9, 1), date(2026, 10, 14), 600), _version(date(2026, 10, 15), None, 120)]
    assert settled_limit_for_month(versions, None, date(2026, 9, 10)) == 600
    assert settled_limit_for_month(versions, None, date(2026, 10, 1)) == 120  # Wechsel im Monat: neue Fassung
    assert settled_limit_for_month(versions, None, date(2026, 10, 31)) == 120
    assert settled_limit_for_month(versions, None, date(2026, 8, 31)) == 0  # vor der ersten Fassung


def test_limit_at_termination_in_the_month() -> None:
    versions = [_version(date(2026, 9, 1), date(2026, 10, 24), 600), _version(date(2026, 10, 25), None, None)]
    # Austritt am 20.10.: maßgeblich ist die Fassung am letzten Beschäftigungstag
    assert settled_limit_for_month(versions, date(2026, 10, 20), date(2026, 10, 5)) == 600
    # Austritt erst im November: Fassung am 31.10.
    assert settled_limit_for_month(versions, date(2026, 11, 20), date(2026, 10, 5)) == 0


def test_limit_takes_the_last_version_of_the_month_when_it_ends_early() -> None:
    versions = [_version(date(2026, 9, 1), date(2026, 10, 10), 300)]
    assert settled_limit_for_month(versions, None, date(2026, 10, 3)) == 300
    assert settled_limit_for_month(versions, None, date(2026, 11, 3)) == 0


def test_limit_is_zero_for_on_demand_and_without_limit() -> None:
    assert settled_limit_for_month([_version(date(2026, 1, 1), None, 600, on_demand=True)], None, date(2026, 10, 1)) == 0
    assert settled_limit_for_month([_version(date(2026, 1, 1))], None, date(2026, 10, 1)) == 0
    assert settled_limit_for_month([], None, date(2026, 10, 1)) == 0


@pytest.mark.parametrize(
    ("deltas", "limit", "booked", "settled"),
    [
        ([60, 60], 600, [0, 0], 120),  # unter der Grenze: alles abgegolten
        ([300, 300], 600, [0, 0], 600),  # genau an der Grenze
        ([300, 360], 600, [0, 60], 600),  # darüber: nur der Rest zählt
        ([-120, -60], 600, [-120, -60], 0),  # Minusmonat bleibt unverändert
        ([120, -180], 600, [0, -60], 0),  # erst Plus, dann Minus: fortlaufend gekappt
        ([120, 120, -60], 180, [0, 60, -60], 180),  # über die Grenze, dann zurück auf die Grenze
        ([120, 120, -120], 180, [0, 60, -60], 120),  # über die Grenze, dann wieder darunter
        ([60, 60], 0, [60, 60], 0),  # ohne Grenze wie bisher
    ],
)
def test_settlement_books_month_saldo(deltas: list[int], limit: int, booked: list[int], settled: int) -> None:
    settlement = _Settlement([_version(date(2026, 1, 1), None, limit or None)], None)
    result = [settlement.book(date(2026, 10, 5 + i), delta) for i, delta in enumerate(deltas)]
    assert result == booked
    assert settlement.settled == settled
    # Konto-Änderung im Monat = Monatssaldo − abgegolten
    assert sum(result) == sum(deltas) - settled


def test_settlement_running_example() -> None:
    settlement = _Settlement([_version(date(2026, 1, 1), None, 180)], None)
    assert settlement.book(date(2026, 10, 5), 120) == 0 and settlement.settled == 120
    assert settlement.book(date(2026, 10, 12), 120) == 60 and settlement.settled == 180
    assert settlement.book(date(2026, 10, 19), -180) == -60 and settlement.settled == 60
    # neuer Monat beginnt bei 0
    assert settlement.book(date(2026, 11, 2), 60) == 0 and settlement.settled == 60 and settlement.raw == 60


def test_settlement_resume_checks_stored_rows() -> None:
    settlement = _Settlement([_version(date(2026, 1, 1), None, 180)], None)
    assert settlement.resume(date(2026, 10, 19), [(120, 120), (120, 180)])
    assert (settlement.raw, settlement.settled) == (240, 180)
    assert settlement.book(date(2026, 10, 19), -180) == -60
    # Zeilen mit anderer Grenze gerechnet -> neu ab Monatsanfang
    assert not _Settlement([_version(date(2026, 1, 1), None, 60)], None).resume(date(2026, 10, 19), [(120, 120)])
    assert not _Settlement([_version(date(2026, 1, 1))], None).resume(date(2026, 10, 19), [(120, 120)])
    # ohne Grenze und alte Zeilen ohne Abgeltung: passt
    assert _Settlement([_version(date(2026, 1, 1))], None).resume(date(2026, 10, 19), [(120, 0), (-60, 0)])
    assert _Settlement([], None).resume(date(2026, 10, 1), [])


def test_input_settled_overtime_hours() -> None:
    assert WorkTimeModelInput(weekly_hours=40, weekdays=[0, 1, 2, 3, 4], settled_overtime_hours=10).settled_overtime_minutes == 600
    assert WorkTimeModelInput(weekly_hours=40, weekdays=[0, 1, 2, 3, 4], settled_overtime_hours=7.5).settled_overtime_minutes == 450
    assert WorkTimeModelInput(weekly_hours=40, weekdays=[0, 1, 2, 3, 4], settled_overtime_hours=0).settled_overtime_minutes is None
    assert WorkTimeModelInput(weekly_hours=40, weekdays=[0, 1, 2, 3, 4]).settled_overtime_minutes is None
    assert WorkTimeModelInput(weekly_hours=40, weekdays=[0, 1, 2, 3, 4], settled_overtime_hours=100).settled_overtime_minutes == 6000
    # nach Aufwand ohne Grenze geht, 0 auch
    assert WorkTimeModelInput(on_demand=True, settled_overtime_hours=0).settled_overtime_minutes is None


@pytest.mark.parametrize(
    "data",
    [
        {"weekly_hours": 40, "weekdays": [0], "settled_overtime_hours": -1},
        {"weekly_hours": 40, "weekdays": [0], "settled_overtime_hours": 100.5},
        {"weekly_hours": 40, "weekdays": [0], "settled_overtime_hours": "viel"},
        {"on_demand": True, "settled_overtime_hours": 5},
    ],
)
def test_input_rejects_invalid_settled_overtime(data: dict) -> None:
    with pytest.raises(ValidationError):
        WorkTimeModelInput(**data)


# ---------------------------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------------------------


async def _login(client: AsyncClient, email: str) -> dict:
    r = await client.post("/auth/login", json={"email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _setup(db_session: AsyncSession, client: AsyncClient, *, termination: date | None = date(2026, 10, 31), hire: date | None = None):
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


async def _model(client: AsyncClient, admin: dict, employee_id: int, valid_from: str = "2026-09-01", limit: float | None = 10, **model):
    body = {**(model or {"daily_hours": MONDAYS}), "valid_from": valid_from}
    if limit is not None:
        body["settled_overtime_hours"] = limit
    r = await client.put(f"/employees/{employee_id}/work-time-model", headers=admin, json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def _work(client: AsyncClient, admin: dict, employee_id: int, day: str, hours: float) -> None:
    minutes = round(hours * 60)
    go = f"{8 + minutes // 60:02d}:{minutes % 60:02d}"
    for punch_type, clock in (("COME", "08:00"), ("GO", go)):
        r = await client.post(
            "/punches", headers=admin,
            json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{day}T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text


async def _balance(client: AsyncClient, headers: dict, employee_id: int) -> dict:
    r = await client.get(f"/employees/{employee_id}/overtime-balance", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _rows(db_session: AsyncSession, employee_id: int) -> dict[str, tuple[int, int, int]]:
    """Kontozeilen: Datum -> (Tagessaldo, Kontostand, abgegolten im Monat bis hier)."""
    rows = (
        await db_session.execute(
            select(OvertimeBalance)
            .where(OvertimeBalance.employee_id == employee_id)
            .order_by(OvertimeBalance.balance_date)
            .execution_options(populate_existing=True)
        )
    ).scalars().all()
    return {r.balance_date.isoformat(): (r.daily_delta_minutes, r.running_balance_minutes, r.settled_minutes) for r in rows}


def _csv(response) -> list[dict]:
    assert response.status_code == 200, response.text
    rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿")), delimiter=";"))
    return [dict(zip(rows[0], row)) for row in rows[1:]], rows[0]


# ---------------------------------------------------------------------------------------------
# Gleitzeitkonto
# ---------------------------------------------------------------------------------------------


async def test_below_the_limit_nothing_reaches_the_account(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=10)
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)  # je +1 Std.
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 0
    rows = await _rows(db_session, employee.id)
    assert [rows[d] for d in OCT] == [(60, 0, 60), (60, 0, 120), (60, 0, 180), (60, 0, 240)]


async def test_exactly_at_the_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=4)
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 0
    assert (await _rows(db_session, employee.id))[OCT[-1]] == (60, 0, 240)


async def test_above_the_limit_only_the_rest_counts(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=3)
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 60
    rows = await _rows(db_session, employee.id)
    assert [rows[d][1:] for d in OCT] == [(0, 60), (0, 120), (0, 180), (60, 180)]


async def test_minus_month_stays_unchanged(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=10)
    for day in OCT:
        await _work(client, admin, employee.id, day, 7.5)  # je −30 Min.
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == -120
    assert all(settled == 0 for _, _, settled in (await _rows(db_session, employee.id)).values())


async def test_settlement_runs_continuously_within_the_month(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=3)
    for day, hours in zip(OCT, (10, 10, 5, 8)):  # +2, +2, −3, ±0
        await _work(client, admin, employee.id, day, hours)
    rows = await _rows(db_session, employee.id)
    # Konto zeigt nie Stunden, die später im Monat wieder verschwinden
    assert [rows[d] for d in OCT] == [(120, 0, 120), (120, 60, 180), (-180, 0, 60), (0, 0, 60)]
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 0


async def test_each_month_has_its_own_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=1)
    for day in SEP + OCT:
        await _work(client, admin, employee.id, day, 9)  # je Monat +4 Std.
    # je Monat 1 Std. abgegolten, 3 Std. ins Konto
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 2 * 180
    rows = await _rows(db_session, employee.id)
    assert rows[SEP[-1]] == (60, 180, 60) and rows[OCT[0]] == (60, 180, 60) and rows[OCT[-1]] == (60, 360, 60)


async def test_without_limit_everything_stays_as_before(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=None)
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    body = await _balance(client, admin, employee.id)
    assert body["running_balance_minutes"] == 240
    assert body["settled_limit_minutes"] is None and body["settled_month_minutes"] == 0
    assert all(settled == 0 for _, _, settled in (await _rows(db_session, employee.id)).values())


async def test_limit_zero_means_off(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    model = await _model(client, admin, employee.id, limit=0)
    assert model["settled_overtime_minutes"] is None
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 240


async def test_entry_in_the_month(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client, hire=date(2026, 10, 8))
    await _model(client, admin, employee.id, valid_from="2026-10-08", limit=1)
    for day in OCT[1:]:
        await _work(client, admin, employee.id, day, 9)
    # Monatssaldo ab Eintritt: +3 Std., davon 1 abgegolten
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 120
    assert OCT[0] not in await _rows(db_session, employee.id)


async def test_exit_in_the_month_uses_the_version_at_the_last_day(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client, termination=date(2026, 10, 20))
    await _model(client, admin, employee.id, limit=2)
    # Fassung ohne Grenze ab 25.10. – nach dem Austritt, zählt also nicht
    await _model(client, admin, employee.id, valid_from="2026-10-25", limit=None)
    for day in OCT[:3]:
        await _work(client, admin, employee.id, day, 9)
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 60
    assert set(await _rows(db_session, employee.id)) == set(OCT[:3])


async def test_version_change_in_the_month_applies_to_the_whole_month(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=None)
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 240
    # Grenze ab 15.10.: gilt für den ganzen Oktober (Fassung am Monatsende), also auch für den 05./12.
    await _model(client, admin, employee.id, valid_from="2026-10-15", limit=3)
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 60
    rows = await _rows(db_session, employee.id)
    assert rows[OCT[0]] == (60, 0, 60) and rows[OCT[-1]] == (60, 60, 180)

    # und umgekehrt: ab 15.10. wieder ohne Grenze -> der ganze Oktober ohne Abgeltung
    await _model(client, admin, employee.id, valid_from="2026-10-15", limit=None)
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 240
    assert all(settled == 0 for _, _, settled in (await _rows(db_session, employee.id)).values())


async def test_change_of_the_limit_recalculates_from_the_month_start(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=1)
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 180
    # nachträglich die Fassung ändern (gleicher Stichtag): Grenze 2 Std.
    version = (await client.get(f"/employees/{employee.id}/work-time-model/history", headers=admin)).json()[0]
    r = await client.put(
        f"/employees/{employee.id}/work-time-model/versions/{version['id']}", headers=admin,
        json={"daily_hours": MONDAYS, "settled_overtime_hours": 2, "valid_from": "2026-09-01"},
    )
    assert r.status_code == 200, r.text
    assert r.json()[0]["settled_overtime_minutes"] == 120
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 120


async def test_partial_invalidation_resumes_the_month(client: AsyncClient, db_session: AsyncSession) -> None:
    """Ändert sich nur ein späterer Tag, wird der Monat ab dem gespeicherten Stand fortgeschrieben –
    passen die gespeicherten Zeilen nicht mehr zur Grenze, ab Monatsanfang neu gerechnet."""
    employee, admin = await _setup(db_session, client)
    employee_id = employee.id
    await _model(client, admin, employee_id, limit=3)
    for day, hours in zip(OCT, (10, 10, 8, 6)):  # +2, +2, ±0, −2
        await _work(client, admin, employee_id, day, hours)
    assert (await _balance(client, admin, employee_id))["running_balance_minutes"] == 0
    rows = await _rows(db_session, employee_id)
    assert [rows[d] for d in OCT] == [(120, 0, 120), (120, 60, 180), (0, 60, 180), (-120, 0, 120)]
    # gespeicherte Zeile verfälschen und nur ab dem 26.10. neu rechnen lassen
    first = (await db_session.execute(select(OvertimeBalance).where(OvertimeBalance.balance_date == date(2026, 10, 5)))).scalar_one()
    first.settled_minutes = 0
    await invalidate_balance(db_session, employee_id, date(2026, 10, 26))
    await db_session.commit()
    assert (await _balance(client, admin, employee_id))["running_balance_minutes"] == 0
    assert (await _rows(db_session, employee_id))[OCT[0]] == (120, 0, 120)


async def test_balance_adjustments_are_not_settled(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=10)
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    r = await client.post(
        f"/employees/{employee.id}/balance-adjustments", headers=admin,
        json={"effective_date": "2026-10-10", "minutes": 300, "kind": "CORRECTION", "note": "Korrektur"},
    )
    assert r.status_code == 201, r.text
    body = await _balance(client, admin, employee.id)
    # +4 Std. abgegolten, die Korrektur (+5 Std.) zählt voll
    assert (body["running_balance_minutes"], body["adjustment_minutes"]) == (300, 300)


async def test_set_balance_books_on_top_of_the_settled_account(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=1)
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 180
    r = await client.post(
        f"/employees/{employee.id}/balance-adjustments/set-balance", headers=admin,
        json={"effective_date": "2026-10-31", "balance_minutes": 600, "note": "Stand laut Lohnbüro"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["minutes"] == 420
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 600


async def test_flexible_week_counts_in_the_month_of_its_settlement(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client, termination=date(2026, 10, 11))
    await _model(client, admin, employee.id, limit=1, weekly_hours=10, flexible=True)
    # Woche 28.09.–04.10.: 12 Std. bei 10 Soll -> +2 Std., abgerechnet am Sonntag 04.10. (Oktober)
    await _work(client, admin, employee.id, "2026-09-28", 6)
    await _work(client, admin, employee.id, "2026-09-29", 6)
    # Woche 05.–11.10.: genau 10 Std.
    await _work(client, admin, employee.id, "2026-10-05", 5)
    await _work(client, admin, employee.id, "2026-10-06", 5)
    rows = await _rows(db_session, employee.id)
    assert rows == {"2026-10-04": (120, 60, 60), "2026-10-11": (0, 60, 60)}
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 60


async def test_flexible_week_in_september_counts_in_september(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client, termination=date(2026, 10, 4))
    # Grenze nur im September (ab Oktober ohne): Woche 21.–27.09. wird im September abgerechnet
    await _model(client, admin, employee.id, limit=1, weekly_hours=10, flexible=True)
    await _model(client, admin, employee.id, valid_from="2026-10-01", limit=None, weekly_hours=10, flexible=True)
    await _work(client, admin, employee.id, "2026-09-21", 6)
    await _work(client, admin, employee.id, "2026-09-22", 6)
    await _work(client, admin, employee.id, "2026-09-28", 6)
    await _work(client, admin, employee.id, "2026-09-29", 6)
    rows = await _rows(db_session, employee.id)
    assert rows["2026-09-27"] == (120, 60, 60)  # September: 1 Std. abgegolten
    assert rows["2026-10-04"] == (120, 180, 0)  # Oktober ohne Grenze


async def test_rotation_model_with_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    """Zusammenspiel mit dem mehrwöchigen Modell: Woche 1 Mo, Woche 2 Di (je 8 Std.)."""
    employee, admin = await _setup(db_session, client)
    weeks = [[8, 0, 0, 0, 0, 0, 0], [0, 8, 0, 0, 0, 0, 0]]
    model = await _model(client, admin, employee.id, valid_from="2026-10-05", limit=1, rotation_weeks=weeks)
    assert model["rotation_minutes"] and model["settled_overtime_minutes"] == 60
    for day in ("2026-10-05", "2026-10-13", "2026-10-19", "2026-10-27"):
        await _work(client, admin, employee.id, day, 9)
    rows = await _rows(db_session, employee.id)
    assert list(rows) == ["2026-10-05", "2026-10-13", "2026-10-19", "2026-10-27"]
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 180


async def test_on_demand_has_no_settlement(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin,
        json={"on_demand": True, "settled_overtime_hours": 5, "valid_from": "2026-09-01"},
    )
    assert r.status_code == 422
    await _model(client, admin, employee.id, limit=None, on_demand=True)
    await _work(client, admin, employee.id, OCT[0], 9)
    body = await _balance(client, admin, employee.id)
    assert body["running_balance_minutes"] == 0 and body["settled_limit_minutes"] is None


# ---------------------------------------------------------------------------------------------
# Laufender Monat und Kontoansicht
# ---------------------------------------------------------------------------------------------


async def test_current_month_shows_settled_so_far(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    employee, admin = await _setup(db_session, client, termination=None)
    await _model(client, admin, employee.id, limit=3)
    at_time(datetime(2026, 10, 21, 12, 0))
    for day, hours in zip(OCT[:3], (10, 10, 9)):
        await _work(client, admin, employee.id, day, hours)
    body = await _balance(client, admin, employee.id)
    # bisheriger Monatssaldo +5 Std., gekappt bei 3
    assert (body["running_balance_minutes"], body["settled_month_minutes"], body["settled_limit_minutes"]) == (120, 180, 180)
    assert body["balance_date"] == "2026-10-19"

    # neuer Monat: noch nichts abgegolten. Der 26.10. fehlte (−8 Std.): Oktober endet mit −3 Std.,
    # die abgegoltenen 3 Std. entfallen wieder, das Konto zeigt den Minusmonat unverändert.
    at_time(datetime(2026, 11, 1, 12, 0))
    body = await _balance(client, admin, employee.id)
    assert (body["running_balance_minutes"], body["settled_month_minutes"], body["settled_limit_minutes"]) == (-180, 0, 180)


async def test_current_month_drops_settled_hours_after_a_minus_day(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    employee, admin = await _setup(db_session, client, termination=None)
    await _model(client, admin, employee.id, limit=3)
    at_time(datetime(2026, 10, 13, 12, 0))
    await _work(client, admin, employee.id, OCT[0], 10)
    await _work(client, admin, employee.id, OCT[1], 10)
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 60
    at_time(datetime(2026, 10, 20, 12, 0))
    await _work(client, admin, employee.id, OCT[2], 6)  # −2 Std. -> Monatssaldo +2, alles abgegolten
    body = await _balance(client, admin, employee.id)
    assert (body["running_balance_minutes"], body["settled_month_minutes"]) == (0, 120)


async def test_employee_sees_own_settled_hours(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    employee, admin = await _setup(db_session, client, termination=None)
    await _model(client, admin, employee.id, limit=2)
    at_time(datetime(2026, 10, 27, 12, 0))
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    own = await _login(client, "erika@example.com")
    body = await _balance(client, own, employee.id)
    assert (body["running_balance_minutes"], body["settled_month_minutes"], body["settled_limit_minutes"]) == (120, 120, 120)


# ---------------------------------------------------------------------------------------------
# Monatsbericht, Monatsabschluss, Lohn-Export
# ---------------------------------------------------------------------------------------------


async def test_month_report_shows_settled_hours(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=3)
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    report = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 10)
    assert (report.delta_minutes, report.settled_minutes, report.settled_limit_minutes, report.balance_end_minutes) == (240, 180, 180, 60)
    html = _report_html(report, False)
    assert "davon abgegolten (mit dem Gehalt, bis 3:00 h/Monat)" in html or "davon abgegolten (mit dem Gehalt, bis 3,00 h/Monat)" in html

    september = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 9)
    assert (september.settled_minutes, september.settled_limit_minutes) == (0, 180)

    pdf = await client.get(f"/employees/{employee.id}/month-report", headers=admin, params={"year": 2026, "month": 10})
    assert pdf.status_code == 200 and pdf.headers["content-type"].startswith("application/pdf")


async def test_month_report_without_limit_has_no_line(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=None)
    await _work(client, admin, employee.id, OCT[0], 9)
    report = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 10)
    assert (report.settled_minutes, report.settled_limit_minutes) == (0, 0)
    assert "davon abgegolten" not in _report_html(report, False)


async def test_period_closure_snapshot_contains_settled_hours(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=3)
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    r = await client.post(f"/employees/{employee.id}/period-closures/2026/10/submit", headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["delta_minutes"], body["settled_minutes"], body["balance_end_minutes"]) == (240, 180, 60)

    # Gesperrter Monat: die Grenze lässt sich für Oktober nicht mehr ändern …
    blocked = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin,
        json={"daily_hours": MONDAYS, "settled_overtime_hours": 1, "valid_from": "2026-10-15"},
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "PERIOD_LOCKED"
    # … ab November schon – der Oktober bleibt unverändert.
    await _model(client, admin, employee.id, valid_from="2026-11-01", limit=1)
    report = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 10)
    assert (report.settled_minutes, report.balance_end_minutes) == (180, 60)


async def test_payroll_export_appends_settled_column(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    other = Employee(location_id=employee.location_id, first_name="Max", last_name="Ohne", employee_number="E2", auto_break_enabled=False,
                     termination_date=date(2026, 10, 31))
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    await _model(client, admin, employee.id, limit=3)
    await _model(client, admin, other.id, limit=None)
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
        await _work(client, admin, other.id, day, 9)

    params = {"employee_ids": [employee.id, other.id], "from": "2026-10-01", "to": "2026-10-31"}
    rows, header = _csv(await client.get("/payroll-export", headers=admin, params=params))
    assert header[-1] == "Abgegoltene Überstunden (Std.)"
    assert header[:8] == ["Personalnummer", "Nachname", "Vorname", "Zeitraum von", "Zeitraum bis", "Soll (Std.)", "Ist (Std.)", "Saldo (Std.)"]
    by_name = {row["Nachname"]: row for row in rows}
    # Saldo bleibt Ist − Soll; die abgegoltenen Stunden stehen zusätzlich hinten
    assert (by_name["Muster"]["Saldo (Std.)"], by_name["Muster"]["Abgegoltene Überstunden (Std.)"]) == ("4,00", "3,00")
    assert by_name["Ohne"]["Abgegoltene Überstunden (Std.)"] == "0,00"

    # Zeitraum mitten im Monat: Stand am Ende minus Stand vor dem Beginn
    rows, _ = _csv(await client.get("/payroll-export", headers=admin, params={"employee_ids": [employee.id], "from": "2026-10-13", "to": "2026-10-31"}))
    # abgegolten am 26.10.: 3 Std., am 12.10.: 2 Std. -> im Zeitraum 1 Std.
    assert rows[0]["Abgegoltene Überstunden (Std.)"] == "1,00"


async def test_payroll_export_without_limit_is_unchanged(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=None)
    await _work(client, admin, employee.id, OCT[0], 9)
    _, header = _csv(await client.get("/payroll-export", headers=admin, params={"employee_ids": [employee.id], "from": "2026-10-01", "to": "2026-10-31"}))
    assert "Abgegoltene Überstunden (Std.)" not in header
    # Grenze erst ab November: im Oktober-Export keine Spalte
    await _model(client, admin, employee.id, valid_from="2026-11-01", limit=2)
    _, header = _csv(await client.get("/payroll-export", headers=admin, params={"employee_ids": [employee.id], "from": "2026-10-01", "to": "2026-10-31"}))
    assert "Abgegoltene Überstunden (Std.)" not in header


async def test_settled_between_and_has_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=1)
    for day in SEP + OCT:
        await _work(client, admin, employee.id, day, 9)
    employee = await db_session.get(Employee, employee.id)
    assert await settled_between(db_session, employee, date(2026, 9, 1), date(2026, 10, 31)) == 120
    assert await settled_between(db_session, employee, date(2026, 10, 1), date(2026, 10, 31)) == 60
    assert await settled_between(db_session, employee, date(2026, 10, 6), date(2026, 10, 31)) == 0  # schon am 05.10. voll
    assert await settled_between(db_session, employee, date(2026, 8, 1), date(2026, 8, 31)) == 0
    assert await has_settled_limit(db_session, employee, date(2026, 10, 1), date(2026, 10, 31))
    assert not await has_settled_limit(db_session, employee, date(2026, 8, 1), date(2026, 8, 31))


# ---------------------------------------------------------------------------------------------
# Arbeitszeitmodelle, Audit, Rechte
# ---------------------------------------------------------------------------------------------


async def test_profile_with_limit_is_synced_to_assigned_employees(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.post("/work-time-profiles", headers=admin, json={"name": "Leitung", "daily_hours": MONDAYS, "settled_overtime_hours": 2})
    assert r.status_code == 201, r.text
    profile = r.json()
    assert profile["settled_overtime_minutes"] == 120
    r = await client.put(f"/employees/{employee.id}/work-time-profile", headers=admin, json={"profile_id": profile["id"], "valid_from": "2026-09-01"})
    assert r.status_code == 200 and r.json()["settled_overtime_minutes"] == 120
    for day in OCT:
        await _work(client, admin, employee.id, day, 9)
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 120

    # Grenze im Modell ab 01.10. erhöhen: Konto der Zugewiesenen wird neu gerechnet
    r = await client.put(
        f"/work-time-profiles/{profile['id']}/model", headers=admin,
        json={"daily_hours": MONDAYS, "settled_overtime_hours": 4, "valid_from": "2026-10-01"},
    )
    assert r.status_code == 200, r.text
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == 0
    history = (await client.get(f"/work-time-profiles/{profile['id']}/history", headers=admin)).json()
    assert [v["settled_overtime_minutes"] for v in history] == [120, 240] or [v["settled_overtime_minutes"] for v in history] == [240, 120]
    rows = (await db_session.execute(select(EmployeeDefaultShift).order_by(EmployeeDefaultShift.valid_from))).scalars().all()
    assert [(row.valid_from, row.settled_overtime_minutes) for row in rows] == [(date(2026, 9, 1), 120), (date(2026, 10, 1), 240)]


async def test_profile_change_respects_locked_months(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    profile = (await client.post("/work-time-profiles", headers=admin, json={"name": "Leitung", "daily_hours": MONDAYS})).json()
    await client.put(f"/employees/{employee.id}/work-time-profile", headers=admin, json={"profile_id": profile["id"], "valid_from": "2026-09-01"})
    db_session.add(PeriodClosure(tenant_id=1, employee_id=employee.id, year=2026, month=10, status=PeriodStatus.CLOSED,
                                 target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=date(2026, 11, 1)))
    await db_session.commit()
    r = await client.put(
        f"/work-time-profiles/{profile['id']}/model", headers=admin,
        json={"daily_hours": MONDAYS, "settled_overtime_hours": 4, "valid_from": "2026-10-20"},
    )
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_LOCKED"


async def test_audit_log_names_the_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _model(client, admin, employee.id, limit=7.5)
    await client.post("/work-time-profiles", headers=admin, json={"name": "Leitung", "weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "settled_overtime_hours": 10})
    details = [e.detail or "" for e in (await db_session.execute(select(AuditLogEntry))).scalars().all()]
    assert any("abgegolten bis 7.5 h/Monat" in d for d in details)
    assert any("Leitung" in d and "abgegolten bis 10 h/Monat" in d for d in details)


@pytest.mark.parametrize("value", [-1, 100.5, "zehn"])
async def test_invalid_limit_is_rejected(client: AsyncClient, db_session: AsyncSession, value) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin,
        json={"daily_hours": MONDAYS, "settled_overtime_hours": value, "valid_from": "2026-09-01"},
    )
    assert r.status_code == 422
    r = await client.post("/work-time-profiles", headers=admin, json={"name": "X", "daily_hours": MONDAYS, "settled_overtime_hours": value})
    assert r.status_code == 422


async def test_only_hr_may_set_the_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    db_session.add(Account(email="sup@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR))
    await db_session.commit()
    body = {"daily_hours": MONDAYS, "settled_overtime_hours": 5, "valid_from": "2026-09-01"}
    for headers in (await _login(client, "erika@example.com"), await _login(client, "sup@example.com")):
        r = await client.put(f"/employees/{employee.id}/work-time-model", headers=headers, json=body)
        assert r.status_code == 403
    assert (await db_session.execute(select(EmployeeDefaultShift))).scalars().all() == []


async def test_other_tenant_cannot_change_the_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    db_session.add(Tenant(id=2, subdomain="other", name="Other"))
    await db_session.flush()
    location = Location(tenant_id=2, name="Fremd", timezone="UTC")
    db_session.add(location)
    await db_session.flush()
    foreign = Employee(tenant_id=2, location_id=location.id, first_name="Fremd", last_name="Firma", employee_number="F1")
    db_session.add(foreign)
    await db_session.commit()
    r = await client.put(
        f"/employees/{foreign.id}/work-time-model", headers=admin,
        json={"daily_hours": MONDAYS, "settled_overtime_hours": 5, "valid_from": "2026-09-01"},
    )
    assert r.status_code == 404
    assert (await client.get(f"/employees/{foreign.id}/overtime-balance", headers=admin)).status_code == 404


async def test_new_employee_with_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.post(
        "/employees", headers=admin,
        json={
            "first_name": "Max", "last_name": "Neu", "employee_number": "E2", "location_id": employee.location_id,
            "hire_date": "2026-10-01", "work_time_model": {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "settled_overtime_hours": 8},
        },
    )
    assert r.status_code == 201, r.text
    model = (await client.get(f"/employees/{r.json()['id']}/work-time-model", headers=admin)).json()
    assert model["settled_overtime_minutes"] == 480


async def test_flexible_week_merged_into_a_fixed_day_row(client: AsyncClient, db_session: AsyncSession) -> None:
    """Wechsel von flexibel auf feste Tage mitten in der Woche: die Wochenabrechnung landet in der
    Tageszeile des Sonntags – auch die Abgeltung zählt dort einmal für beide Teile."""
    employee, admin = await _setup(db_session, client, termination=date(2026, 10, 4))
    await _model(client, admin, employee.id, limit=1, weekly_hours=10, flexible=True)
    await _model(client, admin, employee.id, valid_from="2026-10-01", limit=1, daily_hours=[0, 0, 0, 0, 0, 0, 8])
    await _work(client, admin, employee.id, "2026-09-28", 8)
    await _work(client, admin, employee.id, "2026-09-29", 8)
    await _work(client, admin, employee.id, "2026-10-04", 9)
    rows = await _rows(db_session, employee.id)
    assert list(rows) == ["2026-10-04"]
    delta, running, settled = rows["2026-10-04"]
    assert delta > 60  # Sonntag +1 Std. plus Mehrarbeit aus dem flexiblen Teil der Woche
    assert settled == 60 and running == delta - 60
    assert (await _balance(client, admin, employee.id))["running_balance_minutes"] == running
