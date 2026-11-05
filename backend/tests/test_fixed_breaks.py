"""Feste Pause: neben der gesetzlichen Staffel feste Pausenminuten und feste Pausenzeiten –
mandantenweit unter "Pausenregeln" oder je Mitarbeiter im Arbeitszeitmodell bzw. in der
Schichtvorlage. Die gesetzliche Staffel bleibt immer Untergrenze."""
import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BreakMode,
    BreakRule,
    BreakRuleKind,
    Employee,
    HrRole,
    HrUser,
    Location,
    Punch,
    PunchSource,
    PunchType,
    ShiftTemplate,
)
from app.services.auth_service import hash_password
from app.services.surcharge_service import work_intervals
from app.services.timesheet_service import pair_punches_detail

DAY = date(2026, 10, 6)  # Dienstag
UTC = ZoneInfo("UTC")


async def _setup(db_session: AsyncSession, client: AsyncClient, auto_break: bool = False) -> tuple[Employee, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(
        location_id=location.id, first_name="Pia", last_name="Pause", employee_number="P1", auto_break_enabled=auto_break
    )
    db_session.add_all(
        [
            employee,
            HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
            # gesetzliche Staffel
            BreakRule(min_work_minutes=360, deduct_minutes=30),
            BreakRule(min_work_minutes=540, deduct_minutes=45),
        ]
    )
    await db_session.commit()
    await db_session.refresh(employee)
    login = await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})
    return employee, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _punches(db_session: AsyncSession, employee: Employee, *entries: tuple[str, str], day: date = DAY) -> None:
    for punch_type, clock in entries:
        hour, minute = map(int, clock.split(":"))
        db_session.add(
            Punch(
                employee_id=employee.id,
                location_id=employee.location_id,
                punch_type=PunchType(punch_type),
                timestamp_utc=datetime.combine(day, time(hour, minute)),
                source=PunchSource.KIOSK,
                idempotency_key=str(uuid.uuid4()),
            )
        )
    await db_session.commit()


async def _day(db_session: AsyncSession, employee: Employee, day: date = DAY) -> tuple[int | None, int | None]:
    actual, _, breaks = await pair_punches_detail(db_session, employee, day, UTC)
    return actual, breaks


async def _window(client: AsyncClient, admin: dict, start: str, end: str, valid_from: str = "2026-01-01") -> dict:
    r = await client.post(
        "/break-rules",
        headers=admin,
        json={"kind": "FIXED_WINDOW", "start_time": start, "end_time": end, "valid_from": valid_from},
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- feste Pausenzeit (Mandant) --------------------------------------------------------------------


async def test_fixed_window_deducted_without_punching(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    rule = await _window(client, admin, "12:00", "12:30")
    assert rule["kind"] == "FIXED_WINDOW" and rule["deduct_minutes"] == 30 and rule["min_work_minutes"] == 0
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "16:00"))
    # 8 Std. anwesend, 30 Min. feste Pause – deckt auch die gesetzliche Pause (>6 Std. = 30 Min.)
    assert await _day(db_session, employee) == (450, 30)


async def test_fixed_window_partial_presence_and_punched_break(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _window(client, admin, "12:00", "12:30")
    # nur bis 12:15 da: 15 Min. der Pausenzeit
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "12:15"))
    assert await _day(db_session, employee) == (240, 15)
    # endet vor der Pausenzeit: kein Abzug
    await _punches(db_session, employee, ("COME", "07:00"), ("GO", "11:00"), day=date(2026, 10, 7))
    assert await _day(db_session, employee, date(2026, 10, 7)) == (240, 0)
    # gestempelte Pause 12:15–12:45 überdeckt die halbe Pausenzeit: nicht doppelt abziehen
    await _punches(
        db_session,
        employee,
        ("COME", "08:00"), ("BREAK_START", "12:15"), ("BREAK_END", "12:45"), ("GO", "16:00"),
        day=date(2026, 10, 8),
    )
    # 480 brutto – 30 gestempelt – 15 restliche Pausenzeit
    assert await _day(db_session, employee, date(2026, 10, 8)) == (435, 45)


async def test_fixed_window_and_legal_minimum(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _window(client, admin, "09:00", "09:15")
    # 10 Std. anwesend: gesetzlich 45 Min. – 15 Min. Frühstück zählen, 30 Min. kommen dazu
    await _punches(db_session, employee, ("COME", "07:00"), ("GO", "17:00"))
    assert await _day(db_session, employee) == (555, 45)


async def test_fixed_window_effective_from_date(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _window(client, admin, "12:00", "12:30", valid_from="2026-10-07")
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "12:30"))
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "12:30"), day=date(2026, 10, 7))
    assert await _day(db_session, employee) == (270, 0)
    assert await _day(db_session, employee, date(2026, 10, 7)) == (240, 30)


async def test_fixed_window_on_night_shift(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _window(client, admin, "02:00", "02:30")
    await _punches(db_session, employee, ("COME", "22:00"))
    await _punches(db_session, employee, ("GO", "06:00"), day=date(2026, 10, 7))
    assert await _day(db_session, employee) == (450, 30)


async def test_fixed_window_cut_from_surcharge_intervals(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _window(client, admin, "12:00", "12:30")
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "16:00"))
    pieces = await work_intervals(db_session, employee, DAY, UTC)
    assert pieces == [
        (datetime(2026, 10, 6, 8, 0), datetime(2026, 10, 6, 12, 0)),
        (datetime(2026, 10, 6, 12, 30), datetime(2026, 10, 6, 16, 0)),
    ]


# --- feste Minuten (Mandant) -----------------------------------------------------------------------


async def test_fixed_minutes_rule(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.post(
        "/break-rules", headers=admin, json={"kind": "FIXED_MINUTES", "min_work_minutes": 0, "deduct_minutes": 20, "valid_from": "2026-01-01"}
    )
    assert r.status_code == 201, r.text
    # dieselbe Schwelle wie die gesetzliche Staffel ist erlaubt (andere Art)
    r = await client.post(
        "/break-rules", headers=admin, json={"kind": "FIXED_MINUTES", "min_work_minutes": 360, "deduct_minutes": 40, "valid_from": "2026-01-01"}
    )
    assert r.status_code == 201, r.text
    # 4 Std.: 20 Min. fest, ohne Stempelung
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "12:00"))
    assert await _day(db_session, employee) == (220, 20)
    # länger gestempelt als fest: es zählt die gestempelte Pause
    await _punches(
        db_session, employee, ("COME", "08:00"), ("BREAK_START", "10:00"), ("BREAK_END", "10:30"), ("GO", "12:00"),
        day=date(2026, 10, 7),
    )
    assert await _day(db_session, employee, date(2026, 10, 7)) == (210, 30)
    # 8 Std.: feste 40 Min. liegen über der gesetzlichen Staffel (30 Min.)
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "16:00"), day=date(2026, 10, 8))
    assert await _day(db_session, employee, date(2026, 10, 8)) == (440, 40)


async def test_break_rule_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    await _window(client, admin, "12:00", "12:30")
    for payload in (
        {"kind": "FIXED_WINDOW", "start_time": "12:30", "end_time": "12:00"},
        {"kind": "FIXED_WINDOW", "start_time": "12:00"},
        {"kind": "FIXED_WINDOW", "start_time": "08:00", "end_time": "13:00"},  # > 4 Std.
        {"kind": "FIXED_MINUTES", "deduct_minutes": 30},
        {"kind": "SOMETHING", "min_work_minutes": 0, "deduct_minutes": 30},
    ):
        r = await client.post("/break-rules", headers=admin, json=payload)
        assert r.status_code == 422, payload
    r = await client.post("/break-rules", headers=admin, json={"kind": "FIXED_WINDOW", "start_time": "12:15", "end_time": "12:45"})
    assert r.status_code == 409 and r.json()["code"] == "WINDOW_OVERLAP"
    r = await client.post("/break-rules", headers=admin, json={"kind": "FIXED_WINDOW", "start_time": "12:30", "end_time": "12:45"})
    assert r.status_code == 201  # schließt direkt an


async def test_change_window_from_date_keeps_past(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    rule = await _window(client, admin, "12:00", "12:30")
    r = await client.patch(f"/break-rules/{rule['id']}", headers=admin, json={"end_time": "13:00", "valid_from": "2026-10-07"})
    assert r.status_code == 200, r.text
    assert r.json()["deduct_minutes"] == 60 and r.json()["valid_from"] == "2026-10-07"
    r = await client.patch(f"/break-rules/{rule['id']}", headers=admin, json={"end_time": "11:00"})
    assert r.status_code == 422
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "16:00"))
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "16:00"), day=date(2026, 10, 7))
    assert await _day(db_session, employee) == (450, 30)
    assert await _day(db_session, employee, date(2026, 10, 7)) == (420, 60)
    history = (await client.get("/break-rules?include_history=true", headers=admin)).json()
    assert [(h["start_time"], h["end_time"]) for h in history if h["kind"] == "FIXED_WINDOW"] == [("12:00:00", "12:30:00"), ("12:00:00", "13:00:00")]


# --- eigene Pause im Arbeitszeitmodell / in der Schichtvorlage ------------------------------------------


async def test_work_time_model_break_replaces_tenant_rules(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    await _window(client, admin, "12:00", "12:30")
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "break_minutes": 60, "valid_from": "2026-10-07"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["break_minutes"] == 60 and r.json()["break_start"] is None
    assert r.json()["template_name"] == "Arbeitszeitmodell 40 h/Woche, Pause 60 Min."
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "17:00"))
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "17:00"), day=date(2026, 10, 7))
    # vor dem Modell: Pausenzeit des Mandanten (30 Min.); danach 60 Min. aus dem Modell
    assert await _day(db_session, employee) == (510, 30)
    assert await _day(db_session, employee, date(2026, 10, 7)) == (480, 60)

    entries = (await client.get("/audit-log", headers=admin)).json()
    entry = next(e for e in entries if e["action"] == "EMPLOYEE_WORK_TIME_MODEL_SET")
    assert entry["detail"].startswith("40 h/Woche an Mo, Di, Mi, Do, Fr, Pause 60 Min. ab")

    # feste Uhrzeit im Modell; die gesetzliche Staffel bleibt Untergrenze
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "break_start": "11:30", "break_end": "11:45", "valid_from": "2026-10-08"},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["break_start"], r.json()["break_end"], r.json()["break_minutes"]) == ("11:30:00", "11:45:00", None)
    await _punches(db_session, employee, ("COME", "08:00"), ("GO", "16:00"), day=date(2026, 10, 8))
    assert await _day(db_session, employee, date(2026, 10, 8)) == (450, 30)
    history = (await client.get(f"/employees/{employee.id}/work-time-model/history", headers=admin)).json()
    assert [h["break_minutes"] for h in history] == [None, 60]


async def test_work_time_model_break_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"
    base = {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"}
    for extra in (
        {"break_minutes": 30, "break_start": "12:00", "break_end": "12:30"},
        {"break_start": "12:00"},
        {"break_start": "13:00", "break_end": "12:00"},
        {"break_minutes": 0},
        {"break_minutes": 500},
    ):
        r = await client.put(url, headers=admin, json={**base, **extra})
        assert r.status_code == 422, extra


async def test_shift_template_fixed_break_now_applies(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.post(
        "/shift-templates",
        headers=admin,
        json={"name": "Früh", "start_time": "06:00", "end_time": "14:30", "break_mode": "FIXED", "fixed_break_start": "10:00", "fixed_break_end": "10:30", "target_minutes": 480},
    )
    assert r.status_code == 201, r.text
    template_id = r.json()["id"]
    r = await client.post(
        f"/employees/{employee.id}/default-shifts",
        headers=admin,
        json={"shift_template_id": template_id, "valid_from": "2026-10-01", "weekdays_mask": 31},
    )
    assert r.status_code == 201, r.text
    await _punches(db_session, employee, ("COME", "06:00"), ("GO", "14:30"))
    assert await _day(db_session, employee) == (480, 30)

    # Pause ab Stichtag geändert: der Tag davor rechnet mit der bisherigen Pausenzeit
    r = await client.patch(
        f"/shift-templates/{template_id}",
        headers=admin,
        json={"break_mode": "FLEXIBLE", "min_break_minutes": 45, "valid_from": "2026-10-07"},
    )
    assert r.status_code == 200, r.text
    await _punches(db_session, employee, ("COME", "06:00"), ("GO", "14:30"), day=date(2026, 10, 7))
    assert await _day(db_session, employee) == (480, 30)
    assert await _day(db_session, employee, date(2026, 10, 7)) == (465, 45)
    archived = (await db_session.execute(select(ShiftTemplate).where(ShiftTemplate.archived.is_(True)))).scalars().all()
    assert len(archived) == 1 and archived[0].break_mode == BreakMode.FIXED

    r = await client.post(
        "/shift-templates", headers=admin, json={"name": "Spät", "break_mode": "FIXED", "fixed_break_start": "18:00"}
    )
    assert r.status_code == 422


# --- automatische Pause -----------------------------------------------------------------------------


async def _api_punch(client: AsyncClient, admin: dict, employee: Employee, punch_type: str, clock: str) -> None:
    r = await client.post(
        "/punches",
        headers=admin,
        json={
            "employee_id": employee.id,
            "punch_type": punch_type,
            "timestamp_utc": f"{DAY.isoformat()}T{clock}:00Z",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 201, r.text


async def test_auto_break_only_books_rest_beyond_fixed_window(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client, auto_break=True)
    await _window(client, admin, "12:00", "12:30")
    await _api_punch(client, admin, employee, "COME", "07:00")
    await _api_punch(client, admin, employee, "GO", "17:00")
    auto = (
        await db_session.execute(select(Punch).where(Punch.source == PunchSource.AUTO_BREAK).order_by(Punch.timestamp_utc))
    ).scalars().all()
    # gesetzlich 45 Min., 30 davon deckt die feste Pausenzeit: gebucht werden nur 15 Min.
    assert len(auto) == 2
    assert (auto[1].timestamp_utc - auto[0].timestamp_utc).total_seconds() == 15 * 60
    assert await _day(db_session, employee) == (555, 45)


async def test_tenant_rule_kinds_listed(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    await _window(client, admin, "12:00", "12:30")
    rules = (await client.get("/break-rules", headers=admin)).json()
    assert [r["kind"] for r in rules] == ["LEGAL", "LEGAL", "FIXED_WINDOW"]
    stored = (await db_session.execute(select(BreakRule).where(BreakRule.kind == BreakRuleKind.LEGAL))).scalars().all()
    assert len(stored) == 2
