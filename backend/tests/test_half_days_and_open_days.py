"""Halbe Abwesenheitstage (z.B. ½ Urlaub, an Heiligabend ½ Sonderurlaub + ½ Urlaub) und
"Zu klären": nachträglich behobene Tage verschwinden, HR kann Tage als erledigt markieren."""
import csv
import io
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location
from absence_helpers import require_vacation_approval
from app.services.auth_service import hash_password
from app.services.period_service import build_month_report
from app.services.settings_service import get_or_create_settings

MONDAY = "2026-10-05"  # Woche 05.–09.10.2026 liegt in der Vergangenheit
TUESDAY = "2026-10-06"
WEDNESDAY = "2026-10-07"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _setup(db_session: AsyncSession, client: AsyncClient):
    """Mitarbeiterin mit 40-Std.-Woche (8 Std. Mo–Fr) und Überstundenkonto ab 01.10.2026."""
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(
        location_id=location.id,
        first_name="Erika",
        last_name="Muster",
        employee_number="E1",
        login_email="erika@example.com",
        password_hash=hash_password("pw123456"),
    )
    db_session.add_all(
        [
            employee,
            Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
            Account(email="lead@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR),
        ]
    )
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    settings_row.balance_start_date = date(2026, 10, 1)
    await db_session.commit()
    admin = _bearer((await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"])
    me = _bearer(
        (await client.post("/auth/login", json={"email": "erika@example.com", "password": "pw123456"})).json()["access_token"]
    )
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"},
    )
    assert r.status_code == 200, r.text
    return employee, admin, me


async def _absence(client, headers, employee_id, day, absence_type="VACATION", half=True, day_to=None):
    return await client.post(
        "/absences",
        headers=headers,
        json={"employee_id": employee_id, "type": absence_type, "date_from": day, "date_to": day_to or day, "half_day": half},
    )


async def _punch(client, headers, employee_id, punch_type, ts):
    r = await client.post(
        "/punches",
        headers=headers,
        json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.text


async def _day(client, admin, employee_id, day):
    return (await client.get(f"/employees/{employee_id}/timesheet", headers=admin, params={"from": day, "to": day})).json()[0]


async def _open_days(client, admin, employee_id):
    r = await client.get("/timesheet/open-days", headers=admin)
    assert r.status_code == 200, r.text
    return [d["work_date"] for d in r.json() if d["employee_id"] == employee_id]


# --- Halbe Tage ------------------------------------------------------------------------------


async def test_half_day_only_for_a_single_day(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    r = await _absence(client, admin, employee.id, MONDAY, day_to=TUESDAY)
    assert r.status_code == 422
    full = await _absence(client, admin, employee.id, MONDAY, half=False, day_to=TUESDAY)
    assert full.status_code == 201 and full.json()["half_day"] is False
    r = await client.patch(f"/absences/{full.json()['id']}", headers=admin, json={"half_day": True})
    assert r.status_code == 400 and r.json()["code"] == "HALF_DAY_SINGLE_DAY"
    # Auf einen Tag verkürzt geht es.
    r = await client.patch(f"/absences/{full.json()['id']}", headers=admin, json={"half_day": True, "date_to": MONDAY})
    assert r.status_code == 200 and r.json()["half_day"] is True
    assert (await client.patch(f"/absences/{full.json()['id']}", headers=admin, json={"half_day": "vielleicht"})).status_code == 422


async def test_half_vacation_plus_half_day_of_work(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    assert (await _absence(client, admin, employee.id, MONDAY)).status_code == 201
    await _punch(client, admin, employee.id, "COME", f"{MONDAY}T08:00:00Z")
    await _punch(client, admin, employee.id, "GO", f"{MONDAY}T12:00:00Z")

    day = await _day(client, admin, employee.id, MONDAY)
    # 4 Std. gearbeitet + 4 Std. Urlaubsgutschrift = Soll erfüllt
    assert day["status"] == "COMPLETE"
    assert day["target_minutes"] == 480 and day["actual_minutes"] == 480
    assert day["absence_label"] == "½ Urlaub"
    assert "WORK_DURING_ABSENCE" not in day["flags"]

    leave = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=admin, params={"year": 2026})).json()
    assert leave["used_days"] == 0.5


async def test_christmas_eve_half_special_leave_and_half_vacation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    assert (await _absence(client, admin, employee.id, TUESDAY, "SPECIAL_LEAVE")).status_code == 201
    assert (await _absence(client, admin, employee.id, TUESDAY, "VACATION")).status_code == 201

    day = await _day(client, admin, employee.id, TUESDAY)
    assert day["status"] == "ABSENCE"
    assert day["actual_minutes"] == 480 and day["target_minutes"] == 480
    assert day["absence_label"] == "½ Sonderurlaub + ½ Urlaub"
    assert TUESDAY not in await _open_days(client, admin, employee.id)

    leave = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=admin, params={"year": 2026})).json()
    assert leave["used_days"] == 0.5

    report = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 10)
    assert report.vacation_days == 0.5 and report.special_leave_days == 0.5
    tuesday = next(d for d in report.days if d.day == date(2026, 10, 6))
    assert tuesday.label == "½ Sonderurlaub + ½ Urlaub"

    calendar = (await client.get("/team-calendar", headers=admin, params={"from": TUESDAY, "to": TUESDAY})).json()
    cell = calendar[0]["days"][0]
    assert cell["status"] == "ABSENCE" and cell["half_day"] is False and cell["absence_label"] == "½ Sonderurlaub + ½ Urlaub"


async def test_payroll_export_counts_half_days(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    await _absence(client, admin, employee.id, MONDAY, "VACATION", half=False)
    await _absence(client, admin, employee.id, TUESDAY, "VACATION")
    await _absence(client, admin, employee.id, TUESDAY, "SICK")
    r = await client.get("/payroll-export", headers=admin, params={"employee_ids": [employee.id], "from": MONDAY, "to": TUESDAY})
    assert r.status_code == 200, r.text
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿")), delimiter=";"))
    values = dict(zip(rows[0], rows[1]))
    assert values["Urlaubstage"] == "1,5"
    assert values[next(h for h in rows[0] if h.startswith("Krank"))] == "0,5"


async def test_half_days_cannot_be_combined_with_full_days_or_a_third_half(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    assert (await _absence(client, admin, employee.id, MONDAY)).status_code == 201
    assert (await _absence(client, admin, employee.id, MONDAY, "SPECIAL_LEAVE")).status_code == 201
    third = await _absence(client, admin, employee.id, MONDAY, "SICK")
    assert third.status_code == 409 and third.json()["code"] == "ABSENCE_OVERLAP"
    # Ganztägig über einen Zeitraum, der den halben Tag enthält
    over = await _absence(client, admin, employee.id, "2026-10-02", half=False, day_to=TUESDAY)
    assert over.status_code == 409

    assert (await _absence(client, admin, employee.id, WEDNESDAY, half=False)).status_code == 201
    half_on_full = await _absence(client, admin, employee.id, WEDNESDAY, "SPECIAL_LEAVE")
    assert half_on_full.status_code == 409 and "ganztägige" in half_on_full.json()["detail"]


async def test_rejected_half_day_does_not_block_another(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, me = await _setup(db_session, client)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()
    first = await _absence(client, me, employee.id, MONDAY)
    second = await _absence(client, me, employee.id, MONDAY)
    assert first.json()["approval_status"] == "PENDING" and second.status_code == 201
    assert (await _absence(client, me, employee.id, MONDAY)).status_code == 409
    await client.patch(f"/absences/{first.json()['id']}/decide", headers=admin, json={"approve": False})
    assert (await _absence(client, me, employee.id, MONDAY)).status_code == 201


async def test_half_day_without_work_leaves_the_other_half_open(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    await _absence(client, admin, employee.id, MONDAY)
    day = await _day(client, admin, employee.id, MONDAY)
    assert day["status"] == "OPEN_MISSING_PUNCH" and day["actual_minutes"] == 240
    assert MONDAY in await _open_days(client, admin, employee.id)

    balance = (await client.get(f"/employees/{employee.id}/overtime-balance", headers=admin)).json()
    days_since_start = balance["running_balance_minutes"]
    assert days_since_start < 0  # Fehlende Hälfte und Tage ohne Stempelung belasten das Konto


async def test_half_unpaid_day_halves_the_target(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    await _absence(client, admin, employee.id, MONDAY, "UNPAID")
    await _punch(client, admin, employee.id, "COME", f"{MONDAY}T08:00:00Z")
    await _punch(client, admin, employee.id, "GO", f"{MONDAY}T12:00:00Z")
    day = await _day(client, admin, employee.id, MONDAY)
    assert day["target_minutes"] == 240 and day["actual_minutes"] == 240 and day["status"] == "COMPLETE"


async def test_dashboard_shows_half_day(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    today = date.today().isoformat()
    await _absence(client, admin, employee.id, today)
    dashboard = (await client.get("/dashboard", headers=admin)).json()
    titles = [e["title"] for e in dashboard["events"] if e["kind"] == "ABSENCE"]
    assert titles == ["½ Urlaub"]


# --- Zu klären -------------------------------------------------------------------------------


async def test_day_fixed_by_absence_disappears_from_open_days(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    assert MONDAY in await _open_days(client, admin, employee.id)  # Arbeitstag ohne Stempelung
    # Korrektur über eine Abwesenheit markiert das Konto nur als veraltet – die Liste muss trotzdem stimmen.
    await _absence(client, admin, employee.id, MONDAY, half=False)
    assert MONDAY not in await _open_days(client, admin, employee.id)


async def test_day_fixed_by_holiday_or_work_model_disappears(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    assert {MONDAY, TUESDAY} <= set(await _open_days(client, admin, employee.id))
    r = await client.post("/holidays", headers=admin, json={"date": MONDAY, "name": "Betriebsfeier"})
    assert r.status_code == 201, r.text
    assert MONDAY not in await _open_days(client, admin, employee.id)
    # Dienstag ist laut neuem Modell (rückwirkend) gar kein Arbeitstag
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"weekly_hours": 32, "weekdays": [0, 2, 3, 4], "valid_from": "2026-10-01"},
    )
    assert r.status_code == 200, r.text
    open_days = await _open_days(client, admin, employee.id)
    assert TUESDAY not in open_days and WEDNESDAY in open_days


async def test_mark_missing_day_done_and_reopen(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    await _punch(client, admin, employee.id, "COME", f"{MONDAY}T08:00:00Z")  # "Gehen" fehlt
    await _punch(client, admin, employee.id, "COME", f"{TUESDAY}T08:00:00Z")  # am Folgetag weitergestempelt
    assert MONDAY in await _open_days(client, admin, employee.id)

    r = await client.put(f"/employees/{employee.id}/day-reviews/{MONDAY}", headers=admin, json={"note": "Mitarbeiter war krank nach Hause"})
    assert r.status_code == 204
    assert MONDAY not in await _open_days(client, admin, employee.id)
    # Erledigt ändert nichts an der Berechnung (keine automatische Ergänzung).
    day = await _day(client, admin, employee.id, MONDAY)
    assert day["status"] == "OPEN_MISSING_PUNCH" and day["reviewed"] is True
    report = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 10)
    assert date(2026, 10, 5) not in report.open_days

    assert (await client.delete(f"/employees/{employee.id}/day-reviews/{MONDAY}", headers=admin)).status_code == 204
    assert MONDAY in await _open_days(client, admin, employee.id)


async def test_only_full_hr_can_mark_days_done(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, _, me = await _setup(db_session, client)
    lead = _bearer((await client.post("/auth/login", json={"email": "lead@example.com", "password": "pw"})).json()["access_token"])
    assert (await client.put(f"/employees/{employee.id}/day-reviews/{MONDAY}", headers=lead)).status_code == 403
    assert (await client.put(f"/employees/{employee.id}/day-reviews/{MONDAY}", headers=me)).status_code in (401, 403)
    assert (await client.put(f"/employees/{employee.id}/day-reviews/kein-datum", headers=_bearer("x"))).status_code in (401, 422)
