"""Zeiten selbst eintragen (Stundenzettel, A14): Schalter, Genehmigung über die Korrekturanträge,
Regeln (Zukunft, rückwirkend, Überschneidung, gesperrte Monate) und Wirkung auf Tag, API und Audit."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    AppSettings,
    AuditAction,
    AuditLogEntry,
    CorrectionRequestKind,
    Employee,
    HrRole,
    Location,
    Notification,
    PeriodClosure,
    PeriodStatus,
    Punch,
    PunchCorrectionRequest,
    PunchSource,
    PunchType,
)
from app.schemas.time_entry import TimeEntryCreate, TimeSpanIn
from app.services import time_entry_service as entries
from app.services.auth_service import hash_password
from app.services.timesheet_service import punch_order_key

BERLIN = ZoneInfo("Europe/Berlin")
# "Jetzt": Mittwoch, 04.03.2026, 19:00 Uhr Berlin (MEZ = UTC+1)
NOW = datetime(2026, 3, 4, 18, 0)
TODAY = "2026-03-04"
PW = "pw123456"


async def _setup(db_session: AsyncSession, client: AsyncClient, *, enabled: bool = True, approval: bool = False,
                 backdate: int = 7, auto_break: bool = False):
    location = Location(name="Zentrale", timezone="Europe/Berlin")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Erika", last_name="Muster", employee_number="S1",
                        login_email="erika@example.com", password_hash=hash_password(PW), auto_break_enabled=auto_break)
    other = Employee(location_id=location.id, first_name="Otto", last_name="Other", employee_number="S2",
                     login_email="otto@example.com", password_hash=hash_password(PW))
    db_session.add_all([employee, other, Account(email="hr@example.com", password_hash=hash_password(PW), role=HrRole.HR)])
    settings_row = (await db_session.execute(select(AppSettings).where(AppSettings.tenant_id == 1))).scalar_one()
    settings_row.self_time_entry_enabled = enabled
    settings_row.self_time_entry_approval = approval
    settings_row.self_time_entry_backdate_days = backdate
    await db_session.commit()
    await db_session.refresh(employee)
    await db_session.refresh(other)

    async def login(email: str) -> dict:
        token = (await client.post("/auth/login", json={"email": email, "password": PW})).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return employee, other, await login("hr@example.com"), await login("erika@example.com"), await login("otto@example.com")


def _body(work_date: str = "2026-03-02", *spans: tuple, comment: str | None = None) -> dict:
    spans = spans or (("08:00", "12:00"),)
    result = []
    for span in spans:
        start, end, *rest = span
        item = {"start": start, "end": end}
        for extra in rest:
            item.update(extra)
        result.append(item)
    body = {"work_date": work_date, "spans": result}
    if comment is not None:
        body["comment"] = comment
    return body


async def _punches(db_session: AsyncSession, employee_id: int) -> list[Punch]:
    rows = (await db_session.execute(select(Punch).where(Punch.employee_id == employee_id))).scalars().all()
    return sorted(rows, key=punch_order_key)


def _local(punch: Punch) -> str:
    return punch.timestamp_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(BERLIN).strftime("%d. %H:%M")


# --- Schema ----------------------------------------------------------------------------------------


def test_span_requires_end_after_start_and_next_day_flag() -> None:
    with pytest.raises(ValidationError):
        TimeSpanIn(start="12:00", end="08:00")
    with pytest.raises(ValidationError):
        TimeSpanIn(start="08:00", end="08:00")
    span = TimeSpanIn(start="22:00", end="06:00", end_next_day=True)
    assert (span.start_minutes(), span.end_minutes()) == (1320, 1440 + 360)
    with pytest.raises(ValidationError):
        TimeSpanIn(start="8:00", end="12:00")
    with pytest.raises(ValidationError):
        TimeSpanIn(start="08:00", end="24:00")
    with pytest.raises(ValidationError):
        TimeSpanIn(kind="ERRAND", start="08:00", end="09:00")


def test_entry_validation_rules() -> None:
    ok = TimeEntryCreate(work_date=date(2026, 3, 2), spans=[
        {"start": "08:00", "end": "12:00"}, {"start": "12:00", "end": "16:00"},
        {"kind": "BREAK", "start": "10:00", "end": "10:15"},
    ], comment="  ")
    assert ok.comment is None
    with pytest.raises(ValidationError, match="überschneiden"):
        TimeEntryCreate(work_date=date(2026, 3, 2), spans=[{"start": "08:00", "end": "12:00"}, {"start": "11:00", "end": "13:00"}])
    with pytest.raises(ValidationError, match="Pausen überschneiden"):
        TimeEntryCreate(work_date=date(2026, 3, 2), spans=[
            {"start": "08:00", "end": "16:00"}, {"kind": "BREAK", "start": "10:00", "end": "11:00"},
            {"kind": "BREAK", "start": "10:30", "end": "11:30"},
        ])
    with pytest.raises(ValidationError, match="innerhalb einer Arbeitszeit"):
        TimeEntryCreate(work_date=date(2026, 3, 2), spans=[{"start": "08:00", "end": "12:00"}, {"kind": "BREAK", "start": "12:00", "end": "12:30"}])
    with pytest.raises(ValidationError, match="innerhalb einer Arbeitszeit"):
        TimeEntryCreate(work_date=date(2026, 3, 2), spans=[{"start": "08:00", "end": "12:00"}, {"kind": "BREAK", "start": "08:00", "end": "08:30"}])
    with pytest.raises(ValidationError, match="mindestens eine Arbeitszeit"):
        TimeEntryCreate(work_date=date(2026, 3, 2), spans=[{"kind": "BREAK", "start": "08:00", "end": "08:30"}])
    with pytest.raises(ValidationError):
        TimeEntryCreate(work_date=date(2026, 3, 2), spans=[])
    with pytest.raises(ValidationError):
        TimeEntryCreate(work_date=date(2026, 3, 2), spans=[{"start": f"{h:02d}:00", "end": f"{h:02d}:30"} for h in range(11)])
    with pytest.raises(ValidationError):
        TimeEntryCreate(work_date=date(2026, 3, 2), spans=[{"start": "08:00", "end": "09:00"}], comment="x" * 501)


# --- Service: Umrechnung und Überschneidung ---------------------------------------------------------


def test_spans_to_items_orders_end_before_start_and_keeps_next_day() -> None:
    spans = [TimeSpanIn(start="12:00", end="16:00"), TimeSpanIn(start="08:00", end="12:00"),
             TimeSpanIn(kind="BREAK", start="09:00", end="09:30"), TimeSpanIn(start="22:00", end="01:00", end_next_day=True)]
    items = entries.spans_to_items(spans)
    assert [(i["punch_type"], i["time"], i["next_day"]) for i in items] == [
        ("COME", "08:00", False), ("BREAK_START", "09:00", False), ("BREAK_END", "09:30", False), ("GO", "12:00", False),
        ("COME", "12:00", False), ("GO", "16:00", False), ("COME", "22:00", False), ("GO", "01:00", True),
    ]
    extras = entries.spans_to_items([TimeSpanIn(start="08:00", end="09:00")], [{"x": 1}])
    assert extras[0]["x"] == 1 and "x" not in extras[1]


def test_items_to_intervals_converts_local_time_including_dst() -> None:
    items = entries.spans_to_items([TimeSpanIn(start="22:00", end="06:00", end_next_day=True),
                                    TimeSpanIn(kind="BREAK", start="23:00", end="23:30")])
    intervals = entries.items_to_intervals(date(2026, 3, 28), items, BERLIN)  # Umstellung auf MESZ in der Nacht
    assert [(k, a.isoformat(), b.isoformat()) for k, (a, b), _ in intervals] == [
        ("BREAK", "2026-03-28T22:00:00", "2026-03-28T22:30:00"),
        ("WORK", "2026-03-28T21:00:00", "2026-03-29T04:00:00"),
    ]
    assert entries.describe(date(2026, 3, 2), entries.spans_to_items([TimeSpanIn(start="08:00", end="12:00")]), BERLIN) == "08:00–12:00"


def test_overlaps_allows_touching_spans() -> None:
    a = datetime(2026, 3, 2, 8)
    existing = [(a, a + timedelta(hours=4))]
    assert not entries.overlaps((a + timedelta(hours=4), a + timedelta(hours=6)), existing, [])
    assert not entries.overlaps((a - timedelta(hours=2), a), existing, [])
    assert entries.overlaps((a + timedelta(hours=3), a + timedelta(hours=5)), existing, [])
    assert entries.overlaps((a + timedelta(hours=1), a + timedelta(hours=2)), existing, [])
    assert entries.overlaps((a - timedelta(hours=1), a + timedelta(hours=9)), existing, [])
    assert entries.overlaps((a, a + timedelta(hours=1)), [], [a + timedelta(minutes=30)])
    assert not entries.overlaps((a, a + timedelta(hours=1)), [], [a, a + timedelta(hours=1)])


def test_rules_are_clamped() -> None:
    row = AppSettings(tenant_id=1, self_time_entry_enabled=True, self_time_entry_approval=None, self_time_entry_backdate_days=500)
    rules = entries.rules_of(row)
    assert rules.enabled and rules.approval and rules.backdate_days == entries.MAX_BACKDATE_DAYS
    assert entries.rules_of(AppSettings(tenant_id=1, self_time_entry_backdate_days=None)).backdate_days == 7
    assert entries.rules_of(AppSettings(tenant_id=1, self_time_entry_backdate_days=-3)).backdate_days == 0
    assert entries.earliest_date(rules, date(2026, 3, 4)) == date(2026, 1, 1)


def test_punch_order_key_puts_end_before_start_at_the_same_moment() -> None:
    moment = datetime(2026, 3, 2, 11)
    come = Punch(id=1, punch_type=PunchType.COME, timestamp_utc=moment)
    go = Punch(id=2, punch_type=PunchType.GO, timestamp_utc=moment)
    earlier = Punch(id=3, punch_type=PunchType.BREAK_START, timestamp_utc=moment - timedelta(minutes=1))
    assert sorted([come, go, earlier], key=punch_order_key) == [earlier, go, come]
    same_kind = [Punch(id=5, punch_type=PunchType.BREAK_END, timestamp_utc=moment), Punch(id=4, punch_type=PunchType.GO, timestamp_utc=moment)]
    assert [p.id for p in sorted(same_kind, key=punch_order_key)] == [4, 5]


# --- API: Schalter und Zugriff ----------------------------------------------------------------------


async def test_disabled_by_default_and_only_for_employees(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, hr, me, _ = await _setup(db_session, client, enabled=False)
    week = await client.get("/me/time-entries", headers=me, params={"from": "2026-03-02", "to": "2026-03-08"})
    assert week.status_code == 200 and week.json()["enabled"] is False
    assert all(not d["can_enter"] for d in week.json()["days"])
    r = await client.post("/me/time-entries", headers=me, json=_body())
    assert r.status_code == 403 and r.json()["code"] == "SELF_TIME_ENTRY_DISABLED"
    assert (await client.post("/me/time-entries", headers=hr, json=_body())).status_code == 403
    assert (await client.get("/me/time-entries", headers=hr, params={"from": TODAY, "to": TODAY})).status_code == 403
    assert (await client.get("/me/time-entries", params={"from": TODAY, "to": TODAY})).status_code in (401, 403)
    assert (await client.get("/dashboard", headers=me)).json()["self_time_entry_enabled"] is False
    assert AppSettings().self_time_entry_enabled in (None, False)


async def test_settings_switches_and_bounds(client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(Account(email="admin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN))
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": PW})).json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    current = (await client.get("/settings", headers=admin)).json()
    assert (current["self_time_entry_enabled"], current["self_time_entry_approval"], current["self_time_entry_backdate_days"]) == (False, True, 7)
    assert (await client.patch("/settings", headers=admin, json={"self_time_entry_backdate_days": 63})).status_code == 422
    assert (await client.patch("/settings", headers=admin, json={"self_time_entry_backdate_days": -1})).status_code == 422
    r = await client.patch("/settings", headers=admin, json={
        "self_time_entry_enabled": True, "self_time_entry_approval": False, "self_time_entry_backdate_days": 0,
    })
    assert r.status_code == 200
    assert (r.json()["self_time_entry_enabled"], r.json()["self_time_entry_approval"], r.json()["self_time_entry_backdate_days"]) == (True, False, 0)
    audit = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.SETTINGS_CHANGED))).scalars().all()
    assert any("self_time_entry_backdate_days=0" in (a.detail or "") for a in audit)


# --- Ohne Genehmigung: sofort wirksam ---------------------------------------------------------------


async def test_entry_without_approval_creates_self_entry_punches(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, hr, me, _ = await _setup(db_session, client)
    body = _body("2026-03-02", ("08:00", "12:00"), ("12:30", "16:30"), ("09:00", "09:15", {"kind": "BREAK"}), comment="Außentermin")
    r = await client.post("/me/time-entries", headers=me, json=body)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "APPLIED" and len(r.json()["punch_ids"]) == 6
    punches = await _punches(db_session, employee.id)
    assert [(p.punch_type.value, _local(p), p.source) for p in punches] == [
        ("COME", "02. 08:00", PunchSource.SELF_ENTRY), ("BREAK_START", "02. 09:00", PunchSource.SELF_ENTRY),
        ("BREAK_END", "02. 09:15", PunchSource.SELF_ENTRY), ("GO", "02. 12:00", PunchSource.SELF_ENTRY),
        ("COME", "02. 12:30", PunchSource.SELF_ENTRY), ("GO", "02. 16:30", PunchSource.SELF_ENTRY),
    ]
    assert not any(p.corrected for p in punches)
    audit = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.TIME_ENTRY_CREATED))).scalars().all()
    assert len(audit) == 1 and "08:00–12:00" in audit[0].detail and "Pause 09:00–09:15" in audit[0].detail

    week = (await client.get("/me/time-entries", headers=me, params={"from": "2026-03-02", "to": "2026-03-08"})).json()
    assert week["approval_required"] is False and week["today"] == TODAY and week["earliest_date"] == "2026-02-25"
    monday = week["days"][0]
    assert monday["actual_minutes"] == 4 * 60 - 15 + 4 * 60
    assert [(s["kind"], s["source"], s["deletable"]) for s in monday["spans"]] == [
        ("WORK", "SELF_ENTRY", True), ("BREAK", "SELF_ENTRY", False), ("WORK", "SELF_ENTRY", True),
    ]
    assert [d["can_enter"] for d in week["days"]] == [True, True, True, False, False, False, False]
    # HR sieht die Quelle in der Zeiterfassung des Mitarbeiters
    listed = (await client.get(f"/employees/{employee.id}/punches", headers=hr)).json()
    assert {p["source"] for p in listed} == {"SELF_ENTRY"}
    timesheet = await client.get(f"/employees/{employee.id}/timesheet", headers=hr, params={"from": "2026-03-02", "to": "2026-03-02"})
    assert timesheet.status_code == 200 and timesheet.json()[0]["actual_minutes"] == 465


async def test_touching_spans_are_valid_in_any_order(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, _, me, _ = await _setup(db_session, client)
    # Erst den Nachmittag, dann den Vormittag, der genau dort endet, wo der Nachmittag beginnt.
    assert (await client.post("/me/time-entries", headers=me, json=_body("2026-03-03", ("12:00", "16:00")))).status_code == 201
    assert (await client.post("/me/time-entries", headers=me, json=_body("2026-03-03", ("08:00", "12:00")))).status_code == 201
    # … und genau anschließend
    assert (await client.post("/me/time-entries", headers=me, json=_body("2026-03-03", ("16:00", "17:00")))).status_code == 201
    week = (await client.get("/me/time-entries", headers=me, params={"from": "2026-03-03", "to": "2026-03-03"})).json()
    assert week["days"][0]["actual_minutes"] == 9 * 60
    assert len(week["days"][0]["spans"]) == 3


async def test_hr_manual_punches_at_the_same_minute_pair_correctly(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    """Kern-Regel der Reihenfolge: ein später angelegtes Gehen zum selben Zeitpunkt wie ein früheres
    Kommen beendet erst die eine Spanne, dann beginnt die nächste (früher: widersprüchlich)."""
    at_time(NOW)
    employee, _, hr, _, _ = await _setup(db_session, client)
    for punch_type, stamp in (("COME", "2026-03-02T11:00:00"), ("GO", "2026-03-02T15:00:00"),
                              ("COME", "2026-03-02T07:00:00"), ("GO", "2026-03-02T11:00:00")):
        r = await client.post("/punches", headers=hr, json={
            "employee_id": employee.id, "punch_type": punch_type, "timestamp_utc": stamp, "idempotency_key": f"k-{punch_type}-{stamp}",
        })
        assert r.status_code == 201, r.text
    days = (await client.get(f"/employees/{employee.id}/timesheet", headers=hr, params={"from": "2026-03-02", "to": "2026-03-02"})).json()
    assert days[0]["status"] == "COMPLETE" and days[0]["actual_minutes"] == 8 * 60


async def test_auto_break_and_night_span(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, _, me, _ = await _setup(db_session, client, auto_break=True)
    from app.models import BreakRule, BreakRuleKind

    db_session.add(BreakRule(tenant_id=1, kind=BreakRuleKind.LEGAL, min_work_minutes=360, deduct_minutes=30, valid_from=date(2020, 1, 1)))
    await db_session.commit()
    assert (await client.post("/me/time-entries", headers=me, json=_body("2026-03-02", ("08:00", "17:00")))).status_code == 201
    punches = await _punches(db_session, employee.id)
    assert [p.source for p in punches].count(PunchSource.AUTO_BREAK) == 2
    # Nachtschicht über Mitternacht gehört zum Tag des Beginns
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-03", ("22:00", "02:00", {"end_next_day": True})))
    assert r.status_code == 201, r.text
    week = (await client.get("/me/time-entries", headers=me, params={"from": "2026-03-02", "to": "2026-03-04"})).json()
    assert week["days"][0]["actual_minutes"] == 9 * 60 - 30
    assert week["days"][1]["actual_minutes"] == 4 * 60
    assert week["days"][2]["spans"] == []


# --- Regeln ----------------------------------------------------------------------------------------


async def test_rejects_future_old_and_unfinished_entries(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    _, _, _, me, _ = await _setup(db_session, client, backdate=7)
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-05"))
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_IN_FUTURE"
    r = await client.post("/me/time-entries", headers=me, json=_body(TODAY, ("18:00", "20:00")))
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_IN_FUTURE" and "18:00–20:00" in r.json()["detail"]
    assert (await client.post("/me/time-entries", headers=me, json=_body(TODAY, ("15:00", "19:00")))).status_code == 201
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-02-24"))
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_TOO_OLD" and "7 Tage" in r.json()["detail"]
    assert (await client.post("/me/time-entries", headers=me, json=_body("2026-02-25"))).status_code == 201


async def test_backdate_zero_means_only_today(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    _, _, _, me, _ = await _setup(db_session, client, backdate=0)
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-03"))
    assert r.status_code == 422 and "nur für heute" in r.json()["detail"]
    assert (await client.post("/me/time-entries", headers=me, json=_body(TODAY))).status_code == 201


async def test_rejects_overlaps_with_punches_open_shift_and_pending(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, _, me, _ = await _setup(db_session, client, approval=True)
    db_session.add_all([
        Punch(employee_id=employee.id, location_id=employee.location_id, punch_type=PunchType.COME,
              timestamp_utc=datetime(2026, 3, 2, 7), source=PunchSource.KIOSK),
        Punch(employee_id=employee.id, location_id=employee.location_id, punch_type=PunchType.GO,
              timestamp_utc=datetime(2026, 3, 2, 11), source=PunchSource.KIOSK),
        # heute seit 07:00 Berlin anwesend (noch kein Gehen)
        Punch(employee_id=employee.id, location_id=employee.location_id, punch_type=PunchType.COME,
              timestamp_utc=datetime(2026, 3, 4, 6), source=PunchSource.KIOSK),
    ])
    await db_session.commit()
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-02", ("11:00", "13:00")))
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_OVERLAP" and "11:00–13:00" in r.json()["detail"]
    # direkt danach ist erlaubt (als Antrag)
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-02", ("12:00", "14:00")))
    assert r.status_code == 201 and r.json()["status"] == "PENDING"
    # Überschneidung mit dem offenen Antrag
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-02", ("13:30", "15:00")))
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_OVERLAP"
    # heute läuft die Schicht noch
    r = await client.post("/me/time-entries", headers=me, json=_body(TODAY, ("09:00", "10:00")))
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_OVERLAP"
    assert (await client.post("/me/time-entries", headers=me, json=_body(TODAY, ("06:00", "07:00")))).status_code == 201


async def test_rejects_locked_month_outside_employment_and_too_long(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, _, me, _ = await _setup(db_session, client, backdate=30)
    db_session.add(PeriodClosure(tenant_id=1, employee_id=employee.id, year=2026, month=2, status=PeriodStatus.CLOSED,
                                 target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=date(2026, 3, 1)))
    await db_session.commit()
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-02-27"))
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_LOCKED"
    week = (await client.get("/me/time-entries", headers=me, params={"from": "2026-02-27", "to": "2026-03-01"})).json()
    assert [d["can_enter"] for d in week["days"]] == [False, False, True]

    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-02", ("06:00", "23:00")))
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_TOO_LONG"

    employee = await db_session.get(Employee, employee.id)
    employee.hire_date = date(2026, 3, 3)
    await db_session.commit()
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-02"))
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_OUTSIDE_EMPLOYMENT"
    week = (await client.get("/me/time-entries", headers=me, params={"from": "2026-03-02", "to": "2026-03-03"})).json()
    assert [d["can_enter"] for d in week["days"]] == [False, True]
    employee.hire_date = None
    employee.termination_date = date(2026, 3, 1)
    await db_session.commit()
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-02"))
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_OUTSIDE_EMPLOYMENT"


async def test_range_is_limited(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    _, _, _, me, _ = await _setup(db_session, client)
    assert (await client.get("/me/time-entries", headers=me, params={"from": "2026-03-01", "to": "2026-04-01"})).status_code == 400
    assert (await client.get("/me/time-entries", headers=me, params={"from": "2026-03-05", "to": "2026-03-01"})).status_code == 400
    assert (await client.get("/me/time-entries", headers=me, params={"from": "2026-03-01", "to": "2026-03-31"})).status_code == 200


# --- Mit Genehmigung ---------------------------------------------------------------------------------


async def test_approval_flow_through_correction_requests(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, hr, me, otto = await _setup(db_session, client, approval=True)
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-02", ("08:00", "12:00"), comment="Messe"))
    assert r.status_code == 201 and r.json()["status"] == "PENDING"
    request_id = r.json()["request_id"]
    assert await _punches(db_session, employee.id) == []  # zählt noch nicht
    notes = (await db_session.execute(select(Notification))).scalars().all()
    assert any("bittet um Genehmigung" in n.message for n in notes)

    week = (await client.get("/me/time-entries", headers=me, params={"from": "2026-03-02", "to": "2026-03-02"})).json()
    assert week["approval_required"] is True
    assert week["days"][0]["pending"][0]["request_id"] == request_id and week["days"][0]["pending"][0]["comment"] == "Messe"
    assert week["days"][0]["actual_minutes"] is None

    pending = (await client.get("/punch-correction-requests", headers=hr, params={"status": "PENDING"})).json()
    assert [(p["id"], p["kind"]) for p in pending] == [(request_id, "TIME_ENTRY")]
    assert [i["punch_type"] for i in pending[0]["items"]] == ["COME", "GO"]
    # ein Korrekturantrag für denselben Tag bleibt möglich
    corr = await client.post("/punch-correction-requests", headers=me, json={
        "work_date": "2026-03-02", "items": [{"punch_type": "COME", "time": "13:00"}, {"punch_type": "GO", "time": "14:00"}], "reason": "vergessen",
    })
    assert corr.status_code == 201 and corr.json()["kind"] == "CORRECTION"
    # der Mitarbeiter darf nicht selbst entscheiden, andere sehen den Antrag nicht
    assert (await client.patch(f"/punch-correction-requests/{request_id}/decide", headers=me, json={"approve": True})).status_code == 403
    assert (await client.get("/punch-correction-requests", headers=otto)).json() == []

    r = await client.patch(f"/punch-correction-requests/{request_id}/decide", headers=hr, json={"approve": True})
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    punches = await _punches(db_session, employee.id)
    assert [(p.punch_type.value, _local(p), p.source) for p in punches] == [
        ("COME", "02. 08:00", PunchSource.SELF_ENTRY), ("GO", "02. 12:00", PunchSource.SELF_ENTRY),
    ]
    notes = (await db_session.execute(select(Notification))).scalars().all()
    assert any("wurden genehmigt" in n.message for n in notes)
    audit = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.PUNCH_CORRECTION_DECIDED))).scalars().all()
    assert audit and audit[-1].detail.startswith("Zeiteintrag Übernommen")
    # genehmigte Zeiten lassen sich nicht selbst löschen
    r = await client.delete(f"/me/time-entries/{punches[0].id}", headers=me)
    assert r.status_code == 403 and r.json()["code"] == "TIME_ENTRY_LOCKED"
    week = (await client.get("/me/time-entries", headers=me, params={"from": "2026-03-02", "to": "2026-03-02"})).json()
    assert week["days"][0]["actual_minutes"] == 240 and not week["days"][0]["spans"][0]["deletable"]


async def test_rejection_and_withdrawal(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, hr, me, otto = await _setup(db_session, client, approval=True)
    first = (await client.post("/me/time-entries", headers=me, json=_body("2026-03-02"))).json()["request_id"]
    second = (await client.post("/me/time-entries", headers=me, json=_body("2026-03-03"))).json()["request_id"]
    r = await client.patch(f"/punch-correction-requests/{first}/decide", headers=hr, json={"approve": False, "note": "Bitte stempeln"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    assert await _punches(db_session, employee.id) == []
    notes = (await db_session.execute(select(Notification))).scalars().all()
    assert any("wurden abgelehnt" in n.message for n in notes)
    # zurückziehen: nur eigene, nur offene
    assert (await client.delete(f"/me/time-entries/requests/{first}", headers=me)).status_code == 400
    assert (await client.delete(f"/me/time-entries/requests/{second}", headers=otto)).status_code == 404
    assert (await client.delete("/me/time-entries/requests/9999", headers=me)).status_code == 404
    assert (await client.delete(f"/me/time-entries/requests/{second}", headers=me)).status_code == 204
    assert await db_session.get(PunchCorrectionRequest, second) is None
    corr = (await client.post("/punch-correction-requests", headers=me, json={
        "work_date": "2026-03-03", "items": [{"punch_type": "GO", "time": "17:00"}], "reason": "vergessen"})).json()
    assert (await client.delete(f"/me/time-entries/requests/{corr['id']}", headers=me)).status_code == 404


async def test_approval_rechecks_overlap_and_ignores_backdate_window(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, hr, me, _ = await _setup(db_session, client, approval=True)
    request_id = (await client.post("/me/time-entries", headers=me, json=_body("2026-03-02", ("08:00", "12:00")))).json()["request_id"]
    clash = (await client.post("/me/time-entries", headers=me, json=_body("2026-03-02", ("12:00", "13:00")))).json()["request_id"]
    # inzwischen hat HR eine überschneidende Stempelung gebucht
    db_session.add(Punch(employee_id=employee.id, location_id=employee.location_id, punch_type=PunchType.COME,
                         timestamp_utc=datetime(2026, 3, 2, 10), source=PunchSource.MANUAL_HR))
    db_session.add(Punch(employee_id=employee.id, location_id=employee.location_id, punch_type=PunchType.GO,
                         timestamp_utc=datetime(2026, 3, 2, 10, 30), source=PunchSource.MANUAL_HR))
    await db_session.commit()
    employee_id = employee.id
    r = await client.patch(f"/punch-correction-requests/{request_id}/decide", headers=hr, json={"approve": True})
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_OVERLAP"
    assert (await db_session.get(PunchCorrectionRequest, request_id)).status.value == "PENDING"
    assert len(await _punches(db_session, employee_id)) == 2
    # zwei Wochen später darf HR einen alten Antrag noch übernehmen
    at_time(NOW + timedelta(days=14))
    r = await client.patch(f"/punch-correction-requests/{clash}/decide", headers=hr, json={"approve": True})
    assert r.status_code == 200, r.text
    assert len(await _punches(db_session, employee_id)) == 4


async def test_approval_in_locked_month_is_rejected(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, hr, me, _ = await _setup(db_session, client, approval=True)
    request_id = (await client.post("/me/time-entries", headers=me, json=_body("2026-03-02"))).json()["request_id"]
    db_session.add(PeriodClosure(tenant_id=1, employee_id=employee.id, year=2026, month=3, status=PeriodStatus.CLOSED,
                                 target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=date(2026, 3, 4)))
    await db_session.commit()
    r = await client.patch(f"/punch-correction-requests/{request_id}/decide", headers=hr, json={"approve": True})
    assert r.status_code == 409


# --- Selbst löschen ----------------------------------------------------------------------------------


async def test_delete_own_entry_without_approval(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, other, hr, me, otto = await _setup(db_session, client)
    await client.post("/me/time-entries", headers=me, json=_body("2026-03-02", ("08:00", "12:00"), ("09:00", "09:30", {"kind": "BREAK"})))
    await client.post("/me/time-entries", headers=me, json=_body("2026-03-02", ("13:00", "15:00")))
    punches = await _punches(db_session, employee.id)
    come = punches[0]
    assert (await client.delete(f"/me/time-entries/{come.id}", headers=otto)).status_code == 404
    assert (await client.delete(f"/me/time-entries/{punches[1].id}", headers=me)).status_code == 404  # keine Spanne
    r = await client.delete(f"/me/time-entries/{come.id}", headers=me)
    assert r.status_code == 204
    remaining = await _punches(db_session, employee.id)
    assert [(p.punch_type.value, _local(p)) for p in remaining] == [("COME", "02. 13:00"), ("GO", "02. 15:00")]
    audit = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.TIME_ENTRY_DELETED))).scalars().all()
    assert len(audit) == 1 and "BREAK_START" in audit[0].detail
    week = (await client.get("/me/time-entries", headers=me, params={"from": "2026-03-02", "to": "2026-03-02"})).json()
    assert week["days"][0]["actual_minutes"] == 120

    # von HR korrigiert → nicht mehr selbst löschbar
    r = await client.patch(f"/punches/{remaining[1].id}", headers=hr, json={"timestamp_utc": "2026-03-02T14:30:00", "correction_reason": "x"})
    assert r.status_code == 200
    r = await client.delete(f"/me/time-entries/{remaining[0].id}", headers=me)
    assert r.status_code == 409 and r.json()["code"] == "TIME_ENTRY_CHANGED"
    # Tablet-Stempelungen lassen sich nie selbst löschen
    kiosk = Punch(employee_id=employee.id, location_id=employee.location_id, punch_type=PunchType.COME,
                  timestamp_utc=datetime(2026, 3, 3, 7), source=PunchSource.KIOSK)
    db_session.add(kiosk)
    await db_session.commit()
    assert (await client.delete(f"/me/time-entries/{kiosk.id}", headers=me)).status_code == 404
    # außerhalb des Zeitraums
    at_time(NOW + timedelta(days=10))
    r = await client.delete(f"/me/time-entries/{remaining[0].id}", headers=me)
    assert r.status_code == 422


# --- API v1 und Migrationsdaten -----------------------------------------------------------------------


async def test_public_api_shows_approved_but_not_pending(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, hr, me, _ = await _setup(db_session, client, approval=True)
    db_session.add(Account(email="admin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN))
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": PW})).json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    created = (await client.post("/api-clients", headers=admin, json={"name": "Lohn", "scopes": ["attendances:read"]})).json()
    api_token = (await client.post("/v1/auth/token", json={"client_id": created["client_id"], "client_secret": created["client_secret"]})).json()
    api = {"Authorization": f"Bearer {api_token['access_token']}"}

    first = (await client.post("/me/time-entries", headers=me, json=_body("2026-03-02"))).json()["request_id"]
    await client.post("/me/time-entries", headers=me, json=_body("2026-03-03"))
    page = (await client.get("/v1/punches", headers=api, params={"from": "2026-03-01", "to": "2026-03-04"})).json()
    assert page["data"] == []
    await client.patch(f"/punch-correction-requests/{first}/decide", headers=hr, json={"approve": True})
    page = (await client.get("/v1/punches", headers=api, params={"from": "2026-03-01", "to": "2026-03-04"})).json()
    assert [(p["type"], p["source"]) for p in page["data"]] == [("COME", "SELF_ENTRY"), ("GO", "SELF_ENTRY")]


async def test_request_kind_defaults_to_correction(db_session: AsyncSession) -> None:
    location = Location(name="Z", timezone="Europe/Berlin")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="A", last_name="B", employee_number="K1")
    db_session.add(employee)
    await db_session.commit()
    row = PunchCorrectionRequest(tenant_id=1, employee_id=employee.id, work_date=date(2026, 3, 2), items="[]", reason="x")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    assert row.kind == CorrectionRequestKind.CORRECTION


async def test_conflict_safety_net_and_occupied_edge_cases(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    employee, _, _, me, _ = await _setup(db_session, client)
    settings_row = (await db_session.execute(select(AppSettings).where(AppSettings.tenant_id == 1))).scalar_one()
    settings_row.max_shift_span_hours = 8
    # 02.03.: "Kommen" 01:00 ohne "Gehen" – belegt bis 09:00 (maximale Schichtlänge 8 Std.)
    db_session.add(Punch(employee_id=employee.id, location_id=employee.location_id, punch_type=PunchType.COME,
                         timestamp_utc=datetime(2026, 3, 2, 0), source=PunchSource.KIOSK))
    # 03.: doppeltes Kommen, einzelnes Gehen und eine einzelne Pause (Datenfehler)
    for punch_type, hour in ((PunchType.COME, 6), (PunchType.COME, 8), (PunchType.GO, 9), (PunchType.GO, 11), (PunchType.BREAK_START, 13)):
        db_session.add(Punch(employee_id=employee.id, location_id=employee.location_id, punch_type=punch_type,
                             timestamp_utc=datetime(2026, 3, 3, hour), source=PunchSource.MANUAL_HR))
    await db_session.commit()
    employee_id = employee.id

    intervals, points = await entries.occupied(db_session, await db_session.get(Employee, employee_id), date(2026, 3, 3))
    assert (datetime(2026, 3, 3, 6), datetime(2026, 3, 3, 8)) in intervals
    assert (datetime(2026, 3, 3, 8), datetime(2026, 3, 3, 9)) in intervals
    assert datetime(2026, 3, 3, 11) in points and datetime(2026, 3, 3, 13) in points

    # Der Tag hätte danach zweimal "Kommen" hintereinander – das Sicherheitsnetz lehnt ab.
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-02", ("10:00", "12:00")))
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_CONFLICT"
    assert len(await _punches(db_session, employee_id)) == 6
    # Ein einzelner Zeitpunkt in der neuen Spanne gilt als Überschneidung
    r = await client.post("/me/time-entries", headers=me, json=_body("2026-03-03", ("13:30", "14:30")))
    assert r.status_code == 422 and r.json()["code"] == "TIME_ENTRY_OVERLAP"


async def test_other_company_cannot_see_or_decide(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    from app.models import Tenant

    at_time(NOW)
    _, _, _, me, _ = await _setup(db_session, client, approval=True)
    request_id = (await client.post("/me/time-entries", headers=me, json=_body("2026-03-02"))).json()["request_id"]
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme"))
    await db_session.commit()
    db_session.add(Account(tenant_id=2, email="hr@acme.example.com", password_hash=hash_password(PW), role=HrRole.HR))
    await db_session.commit()
    acme = {"X-Tenant-Subdomain": "acme"}
    token = (await client.post("/auth/login", headers=acme, json={"email": "hr@acme.example.com", "password": PW})).json()["access_token"]
    foreign = {**acme, "Authorization": f"Bearer {token}"}
    assert (await client.get("/punch-correction-requests", headers=foreign)).json() == []
    r = await client.patch(f"/punch-correction-requests/{request_id}/decide", headers=foreign, json={"approve": True})
    assert r.status_code == 404
    assert (await db_session.get(PunchCorrectionRequest, request_id)).status.value == "PENDING"
    # Konto der eigenen Firma gegen die fremde Firma: abgewiesen
    assert (await client.get("/me/time-entries", headers={**me, **acme}, params={"from": TODAY, "to": TODAY})).status_code == 401
