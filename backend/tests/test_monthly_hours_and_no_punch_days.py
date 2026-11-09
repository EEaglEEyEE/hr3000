"""Festes Monatssoll im Arbeitszeitmodell (z.B. 108,5 Std. jeden Monat, egal wie viele Arbeitstage)
und der Schalter "Arbeitstage ganz ohne Stempelung melden" (Zu klären, Monatsbericht, Lohn-Export)."""
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, Holiday, HrRole, Account, Location
from app.services.auth_service import hash_password
from app.services.payroll_export_service import summarize_payroll
from app.services.period_service import build_month_report
from app.services.settings_service import get_or_create_settings


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _setup(db_session: AsyncSession, client: AsyncClient) -> tuple[Employee, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Lena", last_name="Teilzeit", employee_number="T1")
    db_session.add_all([employee, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    await db_session.refresh(employee)
    login = await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})
    return employee, _bearer(login.json()["access_token"])


async def _month_targets(client: AsyncClient, headers: dict, employee_id: int, first: str, last: str) -> dict:
    r = await client.get(f"/employees/{employee_id}/timesheet", headers=headers, params={"from": first, "to": last})
    assert r.status_code == 200, r.text
    return {d["work_date"]: d for d in r.json()}


# --- Festes Monatssoll ------------------------------------------------------------------------


async def test_monthly_hours_same_target_in_short_and_long_month(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    db_session.add(Holiday(date=date(2026, 3, 4), name="Testfeiertag"))
    await db_session.commit()

    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"monthly_hours": 108.5, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-02-01"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["monthly_minutes"] == 6510
    assert body["weekly_minutes"] is None and body["daily_minutes"] is None
    assert body["weekdays"] == [0, 1, 2, 3, 4]
    assert body["shift_template_name"] is None and body["target_from_template"] is False

    # Februar 2026: 20 Arbeitstage, März 2026: 22 Arbeitstage – das Soll ist beide Male 108,5 Std.
    february = await _month_targets(client, admin, employee.id, "2026-02-01", "2026-02-28")
    march = await _month_targets(client, admin, employee.id, "2026-03-01", "2026-03-31")
    assert sum(d["target_minutes"] or 0 for d in february.values()) == 6510
    assert sum(d["target_minutes"] or 0 for d in march.values()) == 6510
    assert {d["target_minutes"] for d in february.values() if d["target_minutes"]} == {325, 326}
    assert march["2026-03-07"]["status"] == "PLANNED_OFF"  # Samstag
    # Feiertag an einem Arbeitstag: mit dem Tagessoll dieses Monats gutgeschrieben.
    holiday = march["2026-03-04"]
    assert holiday["status"] == "HOLIDAY"
    assert holiday["actual_minutes"] == holiday["target_minutes"] > 0

    history = (await client.get(f"/employees/{employee.id}/work-time-model/history", headers=admin)).json()
    assert history[0]["monthly_minutes"] == 6510

    entries = (await client.get("/audit-log", headers=admin)).json()
    entry = next(e for e in entries if e["action"] == "EMPLOYEE_WORK_TIME_MODEL_SET")
    assert "108.5 h/Monat an Mo, Di, Mi, Do, Fr" in entry["detail"]


async def test_monthly_hours_version_can_be_changed_back_to_weekly(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"monthly_hours": 108.5, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-02-01"},
    )
    version_id = (await client.get(f"/employees/{employee.id}/work-time-model/history", headers=admin)).json()[0]["id"]
    r = await client.put(
        f"/employees/{employee.id}/work-time-model/versions/{version_id}",
        headers=admin,
        json={"weekly_hours": 25, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-02-01"},
    )
    assert r.status_code == 200, r.text
    assert r.json()[0]["weekly_minutes"] == 1500 and r.json()[0]["monthly_minutes"] is None
    february = await _month_targets(client, admin, employee.id, "2026-02-01", "2026-02-28")
    assert sum(d["target_minutes"] or 0 for d in february.values()) == 20 * 300


async def test_monthly_hours_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"
    # 200 Std. an einem Wochentag = bis zu 50 Std. je Tag (§3 ArbZG)
    r = await client.put(url, headers=admin, json={"monthly_hours": 200, "weekdays": [0], "valid_from": "2026-02-01"})
    assert r.status_code == 400 and r.json()["code"] == "MAX_DAILY_WORKING_TIME_EXCEEDED"
    # flexibel + Monatsstunden, ohne Arbeitstage, unsinnige Werte
    for payload in (
        {"monthly_hours": 100, "flexible": True},
        {"monthly_hours": 100},
        {"monthly_hours": 0, "weekdays": [0]},
        {"monthly_hours": 999, "weekdays": [0, 1, 2, 3, 4]},
        {"monthly_hours": "viel", "weekdays": [0]},
    ):
        r = await client.put(url, headers=admin, json={**payload, "valid_from": "2026-02-01"})
        assert r.status_code == 422, payload


# --- Arbeitstage ohne Stempelung ------------------------------------------------------------------


async def _punch(client: AsyncClient, headers: dict, employee_id: int, punch_type: str, ts: str) -> None:
    r = await client.post(
        "/punches",
        headers=headers,
        json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.text


async def _open_days(client: AsyncClient, headers: dict, employee_id: int) -> set[str]:
    r = await client.get("/timesheet/open-days", headers=headers)
    assert r.status_code == 200, r.text
    return {d["work_date"] for d in r.json() if d["employee_id"] == employee_id}


async def test_days_without_punches_can_be_left_out(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    settings_row.balance_start_date = date(2026, 10, 5)
    await db_session.commit()
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"weekly_hours": 20, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"},
    )
    assert r.status_code == 200, r.text
    # Mo vollständig, Di gar nicht, Mi nur "Kommen" (unvollständig), Do/Fr gar nicht.
    await _punch(client, admin, employee.id, "COME", "2026-10-05T08:00:00Z")
    await _punch(client, admin, employee.id, "GO", "2026-10-05T16:00:00Z")
    await _punch(client, admin, employee.id, "COME", "2026-10-07T08:00:00Z")

    # Standard: Tage ohne Stempelung sind "zu klären" (bisheriges Verhalten).
    assert (await client.get("/settings", headers=admin)).json()["report_days_without_punches"] is True
    week = {"2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"}
    assert week <= await _open_days(client, admin, employee.id)
    report = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 10)
    tuesday = next(d for d in report.days if d.day == date(2026, 10, 6))
    assert tuesday.label == "Stempelung fehlt" and date(2026, 10, 6) in report.open_days
    payroll = await summarize_payroll(db_session, await db_session.get(Employee, employee.id), date(2026, 10, 5), date(2026, 10, 9))
    assert payroll.open_or_error_days == 4

    r = await client.patch("/settings", headers=admin, json={"report_days_without_punches": False})
    assert r.status_code == 200 and r.json()["report_days_without_punches"] is False
    assert (await client.patch("/settings", headers=admin, json={"report_days_without_punches": "egal"})).status_code == 422

    # Nur noch der unvollständig gestempelte Mittwoch ist offen.
    open_days = await _open_days(client, admin, employee.id)
    assert "2026-10-07" in open_days
    assert not open_days & {"2026-10-06", "2026-10-08", "2026-10-09"}
    await db_session.refresh(settings_row)  # per API geändert
    report = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 10)
    by_day = {d.day: d for d in report.days}
    assert by_day[date(2026, 10, 6)].label == ""
    assert by_day[date(2026, 10, 7)].label == "Stempelung fehlt"
    assert date(2026, 10, 6) not in report.open_days and date(2026, 10, 7) in report.open_days
    # Das Soll zählt trotzdem: ohne Stempelung 4 Std. Minus.
    assert by_day[date(2026, 10, 6)].target_minutes == 240 and by_day[date(2026, 10, 6)].delta_minutes == -240
    payroll = await summarize_payroll(db_session, await db_session.get(Employee, employee.id), date(2026, 10, 5), date(2026, 10, 9))
    assert payroll.open_or_error_days == 1

    # Wieder einschalten: die Tage erscheinen wieder.
    await client.patch("/settings", headers=admin, json={"report_days_without_punches": True})
    assert week <= await _open_days(client, admin, employee.id)


async def test_flexible_model_days_without_punches_never_open(client: AsyncClient, db_session: AsyncSession) -> None:
    """Flexibles Modell (Wochensoll ohne feste Tage): Tage ohne Stempelung sind auch im Lohn-Export
    nicht offen – nur unvollständige Buchungen."""
    employee, admin = await _setup(db_session, client)
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"weekly_hours": 20, "flexible": True, "valid_from": "2026-10-01"},
    )
    assert r.status_code == 200, r.text
    await _punch(client, admin, employee.id, "COME", "2026-10-05T08:00:00Z")
    await _punch(client, admin, employee.id, "GO", "2026-10-05T18:00:00Z")
    await _punch(client, admin, employee.id, "COME", "2026-10-07T08:00:00Z")
    assert await _open_days(client, admin, employee.id) == {"2026-10-07"}
    payroll = await summarize_payroll(db_session, await db_session.get(Employee, employee.id), date(2026, 10, 5), date(2026, 10, 11))
    assert payroll.open_or_error_days == 1
