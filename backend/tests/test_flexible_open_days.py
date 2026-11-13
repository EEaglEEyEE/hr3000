"""Flexible Arbeitszeitmodelle unter „Zu klären“: Schalter „Tage flexibler Modelle melden“
(AppSettings.report_flexible_days) und Hinweis „Wochensoll nicht erreicht“ (DayFlag.WEEKLY_TARGET_MISSED).

Standard: alles wie bisher. Schalter aus: Tage flexibler Modelle gelten nirgends als offen („Zu klären“,
Monatsabschluss, Monatsbericht, Lohn-Export) – höchstens die abgerechnete Woche unter dem Wochensoll."""
import uuid
from datetime import date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AppSettings, DailySummary, Employee, HrRole, Location, SummaryStatus
from app.services import timesheet_service as ts
from app.services.auth_service import hash_password
from app.services.payroll_export_service import payroll_period
from app.services.period_service import build_month_report
from app.services.timesheet_service import DayFlag, flexible_week, needs_review

WEEK = "WEEKLY_TARGET_MISSED"
FLEX = {"weekly_hours": 8, "flexible": True, "valid_from": "2025-01-01"}
FIXED = {"daily_hours": [8, 8, 8, 8, 8, 0, 0], "valid_from": "2025-01-01"}
# Donnerstag, 20.03.2025: die Wochen 3.–9.3. und 10.–16.3. sind abgerechnet, die Woche 17.–23.3. läuft.
NOW = datetime(2025, 3, 20, 12, 0)


async def _company(db: AsyncSession, client: AsyncClient) -> dict[str, str]:
    db.add_all(
        [
            Location(name="Zentrale", timezone="UTC"),
            Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
        ]
    )
    await db.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _employee(db: AsyncSession, client: AsyncClient, headers: dict[str, str], model: dict | None = FLEX, **kwargs) -> Employee:
    location = (await db.execute(select(Location))).scalars().first()
    number = f"M{uuid.uuid4().hex[:6]}"
    employee = Employee(
        location_id=location.id, first_name="Fiona", last_name=kwargs.pop("last_name", "Flexibel"),
        employee_number=number, auto_break_enabled=False, **kwargs,
    )
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    if model is not None:
        response = await client.put(f"/employees/{employee.id}/work-time-model", headers=headers, json=model)
        assert response.status_code == 200, response.text
    return employee


async def _punch(client: AsyncClient, headers: dict[str, str], employee_id: int, punch_type: str, ts_utc: str) -> None:
    response = await client.post(
        "/punches", headers=headers,
        json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts_utc, "idempotency_key": str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text


async def _work(client: AsyncClient, headers: dict[str, str], employee_id: int, day: str, hours: int) -> None:
    await _punch(client, headers, employee_id, "COME", f"{day}T08:00:00Z")
    await _punch(client, headers, employee_id, "GO", f"{day}T{8 + hours:02d}:00:00Z")


async def _settings(client: AsyncClient, headers: dict[str, str], **values) -> dict:
    response = await client.patch("/settings", headers=headers, json=values)
    assert response.status_code == 200, response.text
    return response.json()


async def _open_days(client: AsyncClient, headers: dict[str, str]) -> list[dict]:
    response = await client.get("/timesheet/open-days", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _enable_week_hint(client: AsyncClient, headers: dict[str, str]) -> dict:
    """„Wochensoll nicht erreicht“ einschalten (alle anderen Häkchen wie im Standard)."""
    current = (await client.get("/settings", headers=headers)).json()["disabled_day_flags"]
    return await _settings(client, headers, disabled_day_flags=[f for f in current if f != WEEK])


async def _day(client: AsyncClient, headers: dict[str, str], employee_id: int, day: str) -> dict:
    response = await client.get(f"/employees/{employee_id}/timesheet", headers=headers, params={"from": day, "to": day})
    assert response.status_code == 200, response.text
    return response.json()[0]


# --- Regel „Tag offen“ (Einheit) --------------------------------------------------------------------

TODAY = date(2025, 3, 20)
PAST = date(2025, 3, 9)


@pytest.mark.parametrize(
    "status, flags, work_date",
    [
        (SummaryStatus.ERROR, [], PAST),
        (SummaryStatus.ERROR, [], TODAY),
        (SummaryStatus.OPEN_MISSING_PUNCH, [], PAST),
        (SummaryStatus.PRESENT, [], date(2025, 3, 1)),  # liegengebliebenes „anwesend“
        (SummaryStatus.ON_BREAK, [], date(2025, 3, 1)),
        (SummaryStatus.COMPLETE, [], PAST),
        (SummaryStatus.COMPLETE, [DayFlag.HOLIDAY_WORK], PAST),  # steht nach calculate_day nie im Cache, hier nur die Regel
        (SummaryStatus.COMPLETE, [DayFlag.OVER_MAX_DAILY, DayFlag.WORK_DURING_ABSENCE], TODAY),
    ],
)
def test_exempt_day_is_never_open_without_week_hint(status: SummaryStatus, flags: list[str], work_date: date) -> None:
    assert needs_review(status, flags, work_date, TODAY, exempt=True) is False


@pytest.mark.parametrize("status", [SummaryStatus.OPEN_MISSING_PUNCH, SummaryStatus.COMPLETE, SummaryStatus.ERROR, SummaryStatus.ABSENCE])
def test_exempt_day_is_open_with_week_hint(status: SummaryStatus) -> None:
    assert needs_review(status, [DayFlag.WEEKLY_TARGET_MISSED], PAST, TODAY, exempt=True) is True


def test_week_hint_opens_settlement_day_without_punches() -> None:
    # Sonntag ohne Stempelung und ohne Tagessoll: „Stempelung fehlt“ wird nicht gemeldet, der Hinweis schon.
    flags = [DayFlag.WEEKLY_TARGET_MISSED]
    assert needs_review(SummaryStatus.OPEN_MISSING_PUNCH, flags, PAST, TODAY, missing_reported=False) is True
    assert needs_review(SummaryStatus.OPEN_MISSING_PUNCH, [], PAST, TODAY, missing_reported=False) is False


def test_rule_unchanged_for_other_days() -> None:
    assert needs_review(SummaryStatus.ERROR, [], PAST, TODAY) is True
    assert needs_review(SummaryStatus.OPEN_MISSING_PUNCH, [], PAST, TODAY) is True
    assert needs_review(SummaryStatus.COMPLETE, [DayFlag.HOLIDAY_WORK], PAST, TODAY) is True
    assert needs_review(SummaryStatus.COMPLETE, [], PAST, TODAY) is False
    assert needs_review(SummaryStatus.PRESENT, [], TODAY, TODAY) is False
    assert needs_review(SummaryStatus.PRESENT, [], date(2025, 3, 19), TODAY) is False
    assert needs_review(SummaryStatus.PRESENT, [], date(2025, 3, 18), TODAY) is True


def test_week_hint_is_a_known_special_case() -> None:
    assert DayFlag.WEEKLY_TARGET_MISSED in ts.DAY_FLAGS
    assert len(",".join(ts.DAY_FLAGS)) <= 200  # passt in app_settings.disabled_day_flags / daily_summaries.flags


# --- Standard: nichts ändert sich ---------------------------------------------------------------------


async def test_defaults_keep_behaviour(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    headers = await _company(db_session, client)
    settings = (await client.get("/settings", headers=headers)).json()
    assert settings["report_flexible_days"] is True
    assert WEEK in settings["disabled_day_flags"]
    assert settings["weekly_target_from"] is None

    employee = await _employee(db_session, client, headers)
    await _work(client, headers, employee.id, "2025-03-04", 3)  # Woche 1: 3 von 8 Std.
    await _punch(client, headers, employee.id, "COME", "2025-03-11T08:00:00Z")  # Woche 2: Gehen vergessen

    rows = await _open_days(client, headers)
    # Wie bisher: der unvollständige Tag ist offen, ein verfehltes Wochensoll wird nicht gemeldet.
    assert [(row["work_date"], row["status"], row["flags"]) for row in rows] == [("2025-03-11", "OPEN_MISSING_PUNCH", [])]
    assert rows[0]["week_target_minutes"] is None and rows[0]["week_actual_minutes"] is None


# --- Schalter „Tage flexibler Modelle melden“ aus ---------------------------------------------------


async def test_switch_off_hides_incomplete_and_contradictory_days(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    headers = await _company(db_session, client)
    employee = await _employee(db_session, client, headers)
    await _work(client, headers, employee.id, "2025-03-04", 3)
    await _punch(client, headers, employee.id, "COME", "2025-03-11T08:00:00Z")  # Gehen vergessen
    await _punch(client, headers, employee.id, "GO", "2025-03-12T16:00:00Z")  # Gehen ohne Kommen
    assert {row["work_date"] for row in await _open_days(client, headers)} == {"2025-03-11", "2025-03-12"}

    assert (await _settings(client, headers, report_flexible_days=False))["report_flexible_days"] is False
    assert await _open_days(client, headers) == []

    # Status und Zeiten bleiben am Tag sichtbar – nur „offen“ ist er nicht mehr.
    forgotten = await _day(client, headers, employee.id, "2025-03-11")
    assert forgotten["status"] == "OPEN_MISSING_PUNCH" and forgotten["actual_minutes"] is None and forgotten["flags"] == []
    assert (await _day(client, headers, employee.id, "2025-03-12"))["status"] == "ERROR"
    cached = (
        await db_session.execute(select(DailySummary).where(DailySummary.employee_id == employee.id).order_by(DailySummary.work_date))
    ).scalars().all()
    assert [(c.work_date.isoformat(), c.review_exempt) for c in cached] == [
        ("2025-03-04", True), ("2025-03-11", True), ("2025-03-12", True),
    ]

    # Wieder einschalten: die Tage erscheinen wieder.
    await _settings(client, headers, report_flexible_days=True)
    assert {row["work_date"] for row in await _open_days(client, headers)} == {"2025-03-11", "2025-03-12"}


async def test_switch_off_drops_special_cases_of_flexible_days(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    headers = await _company(db_session, client)
    employee = await _employee(db_session, client, headers)
    await _work(client, headers, employee.id, "2025-03-05", 11)  # mehr als 10 Std.
    await client.post(
        "/absences", headers=headers,
        json={"employee_id": employee.id, "type": "VACATION", "date_from": "2025-03-06", "date_to": "2025-03-06"},
    )
    await _work(client, headers, employee.id, "2025-03-06", 2)  # gestempelt trotz Urlaub
    assert {row["work_date"]: row["flags"] for row in await _open_days(client, headers)} == {
        "2025-03-05": ["OVER_MAX_DAILY"], "2025-03-06": ["WORK_DURING_ABSENCE"],
    }

    await _settings(client, headers, report_flexible_days=False)
    assert await _open_days(client, headers) == []
    long_day = await _day(client, headers, employee.id, "2025-03-05")
    # Der Hinweis fällt weg, die Kennzeichnung „über 10 Std.“ am Tag bleibt.
    assert long_day["flags"] == [] and long_day["exceeds_max_daily_minutes"] is True and long_day["actual_minutes"] == 660


async def test_switch_off_leaves_fixed_models_alone(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    headers = await _company(db_session, client)
    flexible = await _employee(db_session, client, headers)
    fixed = await _employee(db_session, client, headers, model=FIXED, last_name="Fest")
    without = await _employee(db_session, client, headers, model=None, last_name="Ohne")
    for employee in (flexible, fixed, without):
        await _punch(client, headers, employee.id, "COME", "2025-03-18T08:00:00Z")  # Dienstag, Gehen vergessen
    await _settings(client, headers, report_flexible_days=False, report_days_without_punches=False)

    rows = await _open_days(client, headers)
    assert sorted(row["last_name"] for row in rows) == ["Fest", "Ohne"]
    assert all(row["work_date"] == "2025-03-18" for row in rows)


async def test_switch_off_applies_to_month_closing_report_and_payroll(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    headers = await _company(db_session, client)
    employee = await _employee(db_session, client, headers)
    await _work(client, headers, employee.id, "2025-03-04", 3)
    await _punch(client, headers, employee.id, "COME", "2025-03-11T08:00:00Z")

    async def overview() -> int:
        rows = (await client.get("/period-closures", headers=headers, params={"year": 2025, "month": 3})).json()
        return next(row["open_day_count"] for row in rows if row["employee_id"] == employee.id)

    assert await overview() == 1
    assert (await build_month_report(db_session, employee, 2025, 3)).open_days == [date(2025, 3, 11)]
    period = await payroll_period(db_session, employee, date(2025, 3, 1), date(2025, 3, 31))
    assert [d.day for d in period.days if d.open] == [date(2025, 3, 11)]
    blocked = await client.post(f"/employees/{employee.id}/period-closures/2025/2/submit", headers=headers)
    assert blocked.status_code in (200, 201), blocked.text  # Februar hat keinen offenen Tag

    await _settings(client, headers, report_flexible_days=False)
    assert await overview() == 0
    await db_session.refresh(employee)
    report = await build_month_report(db_session, employee, 2025, 3)
    assert report.open_days == []
    # Der Tag bleibt im Bericht als „Stempelung fehlt“ lesbar.
    assert next(d for d in report.days if d.day == date(2025, 3, 11)).label == "Stempelung fehlt"
    period = await payroll_period(db_session, employee, date(2025, 3, 1), date(2025, 3, 31))
    assert not any(d.open for d in period.days)


# --- Hinweis „Wochensoll nicht erreicht“ -------------------------------------------------------------


async def test_week_hint_reports_settled_week_below_target(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(datetime(2025, 3, 3, 6, 0))
    headers = await _company(db_session, client)
    assert (await _enable_week_hint(client, headers))["weekly_target_from"] == "2025-03-03"
    employee = await _employee(db_session, client, headers)
    at_time(NOW)
    await _work(client, headers, employee.id, "2025-03-03", 3)  # Woche 1 (ab Montag): 5 von 8 Std.
    await _work(client, headers, employee.id, "2025-03-08", 2)
    await _work(client, headers, employee.id, "2025-03-12", 8)  # Woche 2: genau 8 Std.
    await _work(client, headers, employee.id, "2025-03-18", 1)  # Woche 3 läuft noch

    rows = await _open_days(client, headers)
    assert len(rows) == 1
    row = rows[0]
    assert (row["work_date"], row["flags"], row["times"]) == ("2025-03-09", [WEEK], "")
    assert (row["week_target_minutes"], row["week_actual_minutes"]) == (480, 300)

    sunday = await _day(client, headers, employee.id, "2025-03-09")
    assert sunday["flags"] == [WEEK] and sunday["reviewed"] is False
    assert (await _day(client, headers, employee.id, "2025-03-16"))["flags"] == []  # Soll erreicht
    assert (await _day(client, headers, employee.id, "2025-03-23"))["flags"] == []  # Woche noch nicht vorbei

    # Dieselbe Regel im Monatsbericht, beim Monatsabschluss und im Lohn-Export.
    report = await build_month_report(db_session, employee, 2025, 3)
    assert report.open_days == [date(2025, 3, 9)]
    assert next(d for d in report.days if d.day == date(2025, 3, 9)).label == "Wochensoll nicht erreicht"
    overview = (await client.get("/period-closures", headers=headers, params={"year": 2025, "month": 3})).json()
    assert next(r["open_day_count"] for r in overview if r["employee_id"] == employee.id) == 1
    period = await payroll_period(db_session, employee, date(2025, 3, 1), date(2025, 3, 31))
    assert [d.day for d in period.days if d.open] == [date(2025, 3, 9)]

    # Das Konto bucht dieselbe Woche: 300 − 480 Minuten.
    balance = (await client.get(f"/employees/{employee.id}/overtime-balance", headers=headers)).json()
    assert balance["running_balance_minutes"] == (300 - 480) + (480 - 480)


async def test_week_hint_can_be_marked_done_and_clears_when_week_is_filled(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(datetime(2025, 3, 3, 6, 0))
    headers = await _company(db_session, client)
    await _enable_week_hint(client, headers)
    first = await _employee(db_session, client, headers)
    second = await _employee(db_session, client, headers, last_name="Zweite")
    at_time(NOW)
    for employee in (first, second):
        await _work(client, headers, employee.id, "2025-03-03", 3)  # Woche 1: 3 von 8 Std.
        await _work(client, headers, employee.id, "2025-03-12", 8)  # Woche 2 erreicht
    assert len(await _open_days(client, headers)) == 2

    # „Erledigt“ am Abrechnungstag
    done = await client.put(f"/employees/{first.id}/day-reviews/2025-03-09", headers=headers)
    assert done.status_code == 204, done.text
    assert [row["employee_id"] for row in await _open_days(client, headers)] == [second.id]
    assert (await _day(client, headers, first.id, "2025-03-09"))["reviewed"] is True

    # Nachgetragene Zeit bringt die Woche aufs Soll: der Hinweis verschwindet von selbst.
    await _work(client, headers, second.id, "2025-03-07", 5)
    assert await _open_days(client, headers) == []
    assert (await _day(client, headers, second.id, "2025-03-09"))["flags"] == []


async def test_week_hint_only_from_the_day_it_was_switched_on(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    headers = await _company(db_session, client)
    employee = await _employee(db_session, client, headers)
    await _work(client, headers, employee.id, "2025-03-03", 3)  # Woche 3.–9.3. unter Soll, Woche 10.–16.3. ohne Zeit
    assert (await _enable_week_hint(client, headers))["weekly_target_from"] == "2025-03-20"
    assert await _open_days(client, headers) == []  # frühere Wochen bleiben geschlossen

    at_time(datetime(2025, 3, 25, 12, 0))  # die Woche 17.–23.3. ist jetzt abgerechnet (0 von 8 Std.)
    rows = await _open_days(client, headers)
    assert [(row["work_date"], row["week_actual_minutes"]) for row in rows] == [("2025-03-23", 0)]

    # Ausschalten entfernt den Hinweis wieder; der Stichtag bleibt stehen, bis neu eingeschaltet wird.
    current = (await client.get("/settings", headers=headers)).json()["disabled_day_flags"]
    await _settings(client, headers, disabled_day_flags=[*current, WEEK])
    assert await _open_days(client, headers) == []
    at_time(datetime(2025, 3, 31, 12, 0))
    assert (await _enable_week_hint(client, headers))["weekly_target_from"] == "2025-03-31"
    assert await _open_days(client, headers) == []  # der 23.3. liegt vor dem neuen Stichtag


async def test_week_hint_counts_credits_and_ignores_other_models(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(datetime(2025, 3, 3, 6, 0))
    headers = await _company(db_session, client)
    await _enable_week_hint(client, headers)
    vacation = await _employee(db_session, client, headers, last_name="Urlaub")
    fixed = await _employee(db_session, client, headers, model=FIXED, last_name="Fest")
    without = await _employee(db_session, client, headers, model=None, last_name="Ohne")
    on_demand = await _employee(db_session, client, headers, model={"on_demand": True, "valid_from": "2025-01-01"}, last_name="Aufwand")
    at_time(NOW)
    # Urlaub Mo–Fr = 5 × 8/5 Std. Gutschrift = Wochensoll erreicht, ohne eine Stempelung in der Woche.
    await _work(client, headers, vacation.id, "2025-03-03", 8)
    await client.post(
        "/absences", headers=headers,
        json={"employee_id": vacation.id, "type": "VACATION", "date_from": "2025-03-10", "date_to": "2025-03-14"},
    )
    for employee in (fixed, without, on_demand):
        await _work(client, headers, employee.id, "2025-03-03", 1)
    await _settings(client, headers, report_days_without_punches=False)

    assert [row for row in await _open_days(client, headers) if WEEK in row["flags"]] == []
    assert (await _day(client, headers, vacation.id, "2025-03-16"))["flags"] == []


async def test_week_hint_on_last_day_of_employment(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(datetime(2025, 3, 3, 6, 0))
    headers = await _company(db_session, client)
    await _enable_week_hint(client, headers)
    employee = await _employee(db_session, client, headers, termination_date=date(2025, 3, 12))  # Mittwoch
    at_time(NOW)
    await _work(client, headers, employee.id, "2025-03-03", 8)  # Woche 1 erreicht
    await _work(client, headers, employee.id, "2025-03-10", 1)  # letzte Woche: Mo–Mi, Soll 3/7 von 8 Std.

    rows = await _open_days(client, headers)
    assert [(row["work_date"], row["week_target_minutes"], row["week_actual_minutes"]) for row in rows] == [
        ("2025-03-12", round(480 * 3 / 7), 60)
    ]
    tz = await ts.employee_timezone(db_session, employee)
    assert await flexible_week(db_session, employee, date(2025, 3, 16), tz) is None  # nach dem Austritt


async def test_both_switches_report_only_the_missed_week(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    """Der gewünschte Betrieb: Tage flexibler Mitarbeiter erscheinen nicht – höchstens die Woche unter dem Soll."""
    at_time(datetime(2025, 3, 3, 6, 0))
    headers = await _company(db_session, client)
    await _enable_week_hint(client, headers)
    await _settings(client, headers, report_flexible_days=False)
    short = await _employee(db_session, client, headers, last_name="Kurz")
    enough = await _employee(db_session, client, headers, last_name="Genug")
    at_time(NOW)
    # Kurz: 5 Std. gezählt, am Mittwoch das Gehen vergessen (zählt 0 – nichts wird geschätzt).
    await _work(client, headers, short.id, "2025-03-03", 5)
    await _punch(client, headers, short.id, "COME", "2025-03-05T08:00:00Z")
    # Genug: trotz vergessenem Gehen am Mittwoch 9 Std. in der Woche.
    await _work(client, headers, enough.id, "2025-03-03", 9)
    await _punch(client, headers, enough.id, "COME", "2025-03-05T08:00:00Z")
    for employee in (short, enough):
        await _work(client, headers, employee.id, "2025-03-12", 8)  # Woche 2 erreicht

    rows = await _open_days(client, headers)
    assert [(row["last_name"], row["work_date"], row["flags"]) for row in rows] == [("Kurz", "2025-03-09", [WEEK])]
    assert (rows[0]["week_target_minutes"], rows[0]["week_actual_minutes"]) == (480, 300)
    overview = (await client.get("/period-closures", headers=headers, params={"year": 2025, "month": 3})).json()
    assert {r["employee_id"]: r["open_day_count"] for r in overview} == {short.id: 1, enough.id: 0}
    sunday = (
        await db_session.execute(
            select(DailySummary).where(DailySummary.employee_id == short.id, DailySummary.work_date == date(2025, 3, 9))
        )
    ).scalar_one()
    assert sunday.review_exempt is True and sunday.flags == WEEK


async def test_week_hint_after_model_change_within_the_week(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(datetime(2025, 3, 3, 6, 0))
    headers = await _company(db_session, client)
    await _enable_week_hint(client, headers)
    employee = await _employee(db_session, client, headers, model=FIXED)
    at_time(NOW)
    # Mo–Mi feste Tage (je 8 Std.), ab Donnerstag flexibel mit 8 Wochenstunden: flexibles Soll = 4/7.
    change = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=headers, json={**FLEX, "valid_from": "2025-03-06"}
    )
    assert change.status_code == 200, change.text
    for day in ("2025-03-03", "2025-03-04", "2025-03-05"):
        await _work(client, headers, employee.id, day, 8)
    await _work(client, headers, employee.id, "2025-03-07", 1)
    await _work(client, headers, employee.id, "2025-03-12", 8)  # Woche 2 erreicht

    tz = await ts.employee_timezone(db_session, employee)
    week = await flexible_week(db_session, employee, date(2025, 3, 9), tz)
    assert (week.target_minutes, week.actual_minutes) == (round(480 * 4 / 7), 60)
    assert [row["work_date"] for row in await _open_days(client, headers) if WEEK in row["flags"]] == ["2025-03-09"]


# --- flexible_week (Einheit) --------------------------------------------------------------------------


async def test_flexible_week_only_on_settlement_days(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    headers = await _company(db_session, client)
    employee = await _employee(db_session, client, headers)
    tz = await ts.employee_timezone(db_session, employee)
    assert await flexible_week(db_session, employee, date(2025, 3, 9), tz) is None  # noch keine Stempelung: kein Konto

    await _work(client, headers, employee.id, "2025-03-05", 2)  # Konto beginnt am Mittwoch
    assert await flexible_week(db_session, employee, date(2025, 3, 2), tz) is None  # vor Kontobeginn
    assert await flexible_week(db_session, employee, date(2025, 3, 8), tz) is None  # Samstag
    assert await flexible_week(db_session, employee, date(2025, 3, 23), tz) is None  # Woche läuft noch
    assert await flexible_week(db_session, employee, date(2025, 3, 20), tz) is None  # heute
    week = await flexible_week(db_session, employee, date(2025, 3, 9), tz)
    assert (week.target_minutes, week.actual_minutes) == (round(480 * 5 / 7), 120)  # Mi–So anteilig
    empty = await flexible_week(db_session, employee, date(2025, 3, 16), tz)
    assert (empty.target_minutes, empty.actual_minutes) == (480, 0)


async def test_flexible_week_none_for_fixed_model(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    headers = await _company(db_session, client)
    employee = await _employee(db_session, client, headers, model=FIXED)
    await _work(client, headers, employee.id, "2025-03-03", 2)
    tz = await ts.employee_timezone(db_session, employee)
    assert await flexible_week(db_session, employee, date(2025, 3, 9), tz) is None


async def test_review_rules_without_settings_row(db_session: AsyncSession) -> None:
    rules = await ts._review_rules(db_session, 4711)
    assert rules.disabled == {DayFlag.WEEKLY_TARGET_MISSED}
    assert rules.report_flexible_days is True and rules.weekly_target_from is None


async def test_review_rules_read_settings(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    headers = await _company(db_session, client)
    await _settings(client, headers, report_flexible_days=False, disabled_day_flags=[])
    rules = await ts._review_rules(db_session, 1)
    assert rules.disabled == set() and rules.report_flexible_days is False and rules.weekly_target_from == date(2025, 3, 20)


# --- Einstellungen ------------------------------------------------------------------------------------


async def test_settings_validation_and_roles(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _company(db_session, client)
    assert (await client.patch("/settings", headers=headers, json={"report_flexible_days": "vielleicht"})).status_code == 422
    assert (await client.patch("/settings", headers=headers, json={"disabled_day_flags": ["GIBT_ES_NICHT"]})).status_code == 400
    assert (await client.patch("/settings", headers=headers, json={"disabled_day_flags": [WEEK]})).status_code == 200

    db_session.add(Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR))
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]
    forbidden = await client.patch("/settings", headers={"Authorization": f"Bearer {token}"}, json={"report_flexible_days": False})
    assert forbidden.status_code == 403


async def test_unchanged_switch_does_not_rebuild(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    headers = await _company(db_session, client)
    employee = await _employee(db_session, client, headers)
    await _work(client, headers, employee.id, "2025-03-04", 3)
    await _open_days(client, headers)  # rechnet das Konto
    await db_session.refresh(employee)
    through = employee.balance_through
    assert through is not None
    await _settings(client, headers, report_flexible_days=True)  # schon an: nichts zu tun
    await db_session.refresh(employee)
    assert employee.balance_through == through
    await _settings(client, headers, report_flexible_days=False)
    await db_session.refresh(employee)
    assert employee.balance_through is None  # Tages-Cache wird neu aufgebaut


async def test_settings_transfer(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _company(db_session, client)
    await _settings(client, headers, report_flexible_days=False)
    exported = (await client.get("/migration/settings-export", headers=headers)).json()
    assert exported["settings"]["report_flexible_days"] is False
    assert WEEK in exported["settings"]["disabled_day_flags"]

    # Datei von vor dieser Version: kennt weder Schalter noch Hinweis – der Hinweis bleibt aus.
    old_file = {"format": "hr3000-settings", "version": 1, "settings": {"disabled_day_flags": ["EARLY_LEAVE"]}}
    imported = await client.post("/migration/settings-import", headers=headers, params={"apply": "true"}, json=old_file)
    assert imported.status_code == 200, imported.text
    row = (await db_session.execute(select(AppSettings))).scalars().first()
    await db_session.refresh(row)
    assert set(row.disabled_day_flags.split(",")) == {"EARLY_LEAVE", WEEK}
    assert row.weekly_target_from is None and row.report_flexible_days is False

    # Neue Datei mit eingeschaltetem Hinweis wird so übernommen.
    new_file = {**old_file, "settings": {"disabled_day_flags": ["EARLY_LEAVE"], "report_flexible_days": True}}
    assert (await client.post("/migration/settings-import", headers=headers, params={"apply": "true"}, json=new_file)).status_code == 200
    await db_session.refresh(row)
    assert row.disabled_day_flags == "EARLY_LEAVE" and row.report_flexible_days is True
    assert row.weekly_target_from is not None
