"""Schnittstellen zwischen den Features aus Phase 7–10, die getrennt entstanden sind:
- mehrwöchiges Arbeitszeitmodell (A15) × Abwesenheitsquote/FTE/eigene Berichte (C4)
- abgegoltene Überstunden (A6) × Lohnbuchhaltung (C1) und eigene Berichte (C4)"""
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Employee, EmployeeDefaultShift, HrRole, Location
from app.schemas.payroll_accounting import AccountingHours
from app.services import report_catalog as catalog
from app.services import workforce_stats_service as stats
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings

# Woche 1: Mo–Mi je 8 Std., Woche 2: Do/Fr je 8 Std.; Woche 1 beginnt am Mo 28.09.2026
ROTATION = "480,480,480,0,0,0,0;0,0,0,480,480,0,0"
START = date(2026, 9, 28)


def _rotation_version(**kwargs) -> EmployeeDefaultShift:
    values = dict(employee_id=1, valid_from=date(2026, 9, 28), valid_to=None, weekdays_mask=0b0011111, day_minutes=None,
                  flexible=False, on_demand=False, target_minutes=1200, target_period=None, shift_template_id=None,
                  rotation_minutes=ROTATION, rotation_start=START)
    values.update(kwargs)
    return EmployeeDefaultShift(**values)


# --- A15 × C4: Statistik-Bausteine --------------------------------------------------------------------


@pytest.mark.parametrize(
    "day, planned",
    [
        (date(2026, 9, 28), True),   # Woche 1, Montag
        (date(2026, 9, 30), True),   # Woche 1, Mittwoch
        (date(2026, 10, 1), False),  # Woche 1, Donnerstag: frei
        (date(2026, 10, 5), False),  # Woche 2, Montag: frei
        (date(2026, 10, 8), True),   # Woche 2, Donnerstag
        (date(2026, 10, 9), True),   # Woche 2, Freitag
        (date(2026, 10, 10), False),  # Samstag
        (date(2026, 10, 12), True),  # wieder Woche 1
        (date(2026, 9, 21), False),  # vor dem Start: Woche 2, Montag frei (Turnus läuft rückwärts)
        (date(2026, 9, 24), True),   # vor dem Start: Woche 2, Donnerstag
    ],
)
def test_planned_workday_follows_the_rotation_week(day: date, planned: bool) -> None:
    assert stats.is_planned_workday([_rotation_version(valid_from=date(2026, 1, 1))], {}, 1, day) is planned


def test_planned_workdays_of_a_month_are_not_the_union_of_all_weeks() -> None:
    versions = [_rotation_version(valid_from=date(2026, 1, 1))]
    days = [date(2026, 10, d) for d in range(1, 32)]
    planned = sum(stats.is_planned_workday(versions, {}, 1, day) for day in days)
    # Oktober 2026: Woche-1-Wochen ab 28.09., 12.10., 26.10. (Mo–Mi) und Woche-2-Wochen ab 05.10., 19.10. (Do/Fr)
    assert planned == 3 + 3 + 2 + 2 + 0  # 12.–14., 26.–28., 08./09., 22./23. (28.–30.09. liegt im September)
    union = sum(day.weekday() < 5 for day in days)
    assert planned < union == 22


def test_holiday_still_wins_over_rotation() -> None:
    versions = [_rotation_version(valid_from=date(2026, 1, 1))]
    assert stats.is_planned_workday(versions, {date(2026, 10, 12): [None]}, 1, date(2026, 10, 12)) is False
    assert stats.is_planned_workday(versions, {date(2026, 10, 12): [{2}]}, 1, date(2026, 10, 12)) is True


def test_weekly_minutes_is_the_average_over_the_rotation() -> None:
    assert stats.weekly_minutes(_rotation_version(), None) == 1200
    # auch wenn target_minutes fehlt oder veraltet ist, zählt der Turnus
    assert stats.weekly_minutes(_rotation_version(target_minutes=None), None) == 1200
    assert stats.weekly_minutes(_rotation_version(target_minutes=2400), None) == 1200
    three = _rotation_version(rotation_minutes="480,0,0,0,0,0,0;480,480,0,0,0,0,0;0,0,0,0,0,0,0")
    assert stats.weekly_minutes(three, None) == 480  # (8 + 16 + 0) / 3 Std.


def test_fte_of_rotation() -> None:
    assert stats.fte_of(_rotation_version(), None, 2400) == 0.5
    assert stats.weekly_minutes(_rotation_version(on_demand=True), None) is None


def test_plain_models_unchanged() -> None:
    plain = _rotation_version(rotation_minutes=None, rotation_start=None, target_minutes=None, day_minutes="480,480,0,0,0,0,0")
    assert stats.weekly_minutes(plain, None) == 960
    assert stats.is_planned_workday([plain], {}, 1, date(2026, 10, 6)) is True
    assert stats.is_planned_workday([plain], {}, 1, date(2026, 10, 7)) is False


# --- A6 × C4/C1: Katalog und Schema --------------------------------------------------------------------


def test_time_source_offers_settled_column() -> None:
    column = catalog.STATIC_COLUMNS[catalog.SOURCE_TIME_MONTHS]["settled_hours"]
    assert column.summable is True and "abgegolten" in column.label


def test_accounting_hours_default_for_old_snapshots() -> None:
    old = AccountingHours(target_minutes=1, actual_minutes=2, balance_minutes=1, payout_minutes=0, open_days=0)
    assert old.settled_minutes == 0
    assert AccountingHours(**old.model_dump(exclude={"settled_minutes"}), settled_minutes=90).settled_minutes == 90


# --- Integration über die API --------------------------------------------------------------------------


async def _setup(
    client: AsyncClient, db: AsyncSession, *, model: dict, hire: date = date(2026, 1, 1), termination: date | None = None
) -> tuple[dict, Employee]:
    location = Location(name="Zentrale", timezone="UTC")
    db.add(location)
    await db.commit()
    employee = Employee(location_id=location.id, first_name="Tea", last_name="Turnus", employee_number="700",
                        auto_break_enabled=False, hire_date=hire, termination_date=termination)
    db.add_all([employee, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN,
                                  payroll_access=True)])
    row = await get_or_create_settings(db, 1)
    row.custom_reports_enabled = True
    row.payroll_accounting_enabled = True
    await db.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    r = await client.put(f"/employees/{employee.id}/work-time-model", headers=admin, json={**model, "valid_from": "2026-01-01"})
    assert r.status_code == 200, r.text
    return admin, employee


async def _work(client: AsyncClient, admin: dict, employee_id: int, day: str, hours: int) -> None:
    for punch_type, clock in (("COME", "08:00"), ("GO", f"{8 + hours:02d}:00")):
        r = await client.post("/punches", headers=admin, json={
            "employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{day}T{clock}:00Z",
            "idempotency_key": str(uuid.uuid4()),
        })
        assert r.status_code == 201, r.text


async def test_headcount_and_builder_use_rotation_average(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, employee = await _setup(client, db_session, model={
        "rotation_weeks": [[8, 8, 8, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0]], "rotation_start": "2026-09-28",
    })
    head = await client.get("/reports/headcount", headers=admin, params={"date_from": "2026-10-01", "date_to": "2026-10-31"})
    assert head.status_code == 200, head.text
    assert '"fte":0.5' in head.text.replace(" ", "") or "0.5" in head.text
    preview = await client.post("/report-builder/preview", headers=admin, json={
        "definition": {"source": "employees", "columns": ["last_name", "weekly_hours"]},
    })
    assert preview.status_code == 200, preview.text
    body = preview.json()
    index = [c["key"] for c in body["columns"]].index("weekly_hours")
    assert [row[index] for row in body["rows"]] == [20.0]


async def test_absence_rate_counts_rotation_workdays(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, employee = await _setup(client, db_session, model={
        "rotation_weeks": [[8, 8, 8, 0, 0, 0, 0], [0, 0, 0, 8, 8, 0, 0]], "rotation_start": "2026-09-28",
    })
    # krank Mo 05.10.–Fr 09.10.2026 (Woche 2): nur Do und Fr sind Soll-Arbeitstage
    types = (await client.get("/absence-types", headers=admin)).json()
    sick = next(t for t in types if t["category"] == "SICK") if types and "category" in types[0] else None
    payload = {"employee_id": employee.id, "date_from": "2026-10-05", "date_to": "2026-10-09"}
    payload.update({"absence_type_id": sick["id"]} if sick else {"type": "SICK"})
    created = await client.post("/absences", headers=admin, json=payload)
    assert created.status_code == 201, created.text
    rate = await client.get("/reports/absence-rate", headers=admin, params={"date_from": "2026-10-01", "date_to": "2026-10-31"})
    assert rate.status_code == 200, rate.text
    month = rate.json()["months"][0]
    total = month.get("total", month)
    assert total["workdays"] == 10  # 12.–14., 26.–28. (Woche 1) und 08./09., 22./23. (Woche 2)
    assert total["absence_days"] == 2


async def test_settled_overtime_in_payroll_accounting_and_builder(client: AsyncClient, db_session: AsyncSession) -> None:
    # Beschäftigt nur Mo 05.10. und Di 06.10.2026 – so entscheidet der Monatssaldo dieser zwei Tage:
    # je 3 Überstunden -> 6 Std. Mehrarbeit, davon 5 abgegolten
    admin, employee = await _setup(
        client, db_session, hire=date(2026, 10, 5), termination=date(2026, 10, 6),
        model={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "settled_overtime_hours": 5},
    )
    await _work(client, admin, employee.id, "2026-10-05", 11)
    await _work(client, admin, employee.id, "2026-10-06", 11)

    month = await client.get("/payroll-accounting/2026-10", headers=admin)
    assert month.status_code == 200, month.text
    row = next(r for r in month.json()["employees"] if r["employee_id"] == employee.id)
    assert row["hours"]["settled_minutes"] == 300

    preview = await client.post("/report-builder/preview", headers=admin, json={
        "definition": {"source": "time_months", "columns": ["last_name", "month", "settled_hours"]},
        "date_from": "2026-10-01", "date_to": "2026-10-31",
    })
    assert preview.status_code == 200, preview.text
    body = preview.json()
    index = [c["key"] for c in body["columns"]].index("settled_hours")
    assert [r[index] for r in body["rows"]] == [5.0]


async def test_without_limit_settled_is_zero(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, employee = await _setup(
        client, db_session, hire=date(2026, 10, 5), termination=date(2026, 10, 6),
        model={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4]},
    )
    await _work(client, admin, employee.id, "2026-10-05", 11)
    month = await client.get("/payroll-accounting/2026-10", headers=admin)
    row = next(r for r in month.json()["employees"] if r["employee_id"] == employee.id)
    assert row["hours"]["settled_minutes"] == 0

