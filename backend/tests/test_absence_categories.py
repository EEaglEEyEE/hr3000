"""Kategorien Arbeitszeit (Homeoffice, zusätzliche Stunden), Feiertag (Feiertag GfB), Kind krank –
und das nachträgliche Ändern der Kategorie einer Abwesenheitsart."""
import csv
import io
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location
from app.models.period_closure import PeriodClosure, PeriodStatus
from app.services.auth_service import hash_password
from app.services.period_service import build_month_report

MONDAY = "2026-10-05"
TUESDAY = "2026-10-06"
WEDNESDAY = "2026-10-07"


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Klara", last_name="Kategorie", employee_number="K1")
    db_session.add_all(
        [
            employee,
            Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
            Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        ]
    )
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    r = await client.put(
        f"/employees/{employee.id}/work-time-model",
        headers=admin,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"},
    )
    assert r.status_code == 200, r.text
    return employee, admin


async def _type(client, admin, name, category):
    r = await client.post("/absence-types", headers=admin, json={"name": name, "category": category})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _absence(client, admin, employee_id, type_id, day, **extra):
    r = await client.post(
        "/absences", headers=admin, json={"employee_id": employee_id, "absence_type_id": type_id, "date_from": day, "date_to": day, **extra}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _payroll(client, admin, employee_id) -> dict:
    r = await client.get("/payroll-export", headers=admin, params={"employee_ids": [employee_id], "from": MONDAY, "to": WEDNESDAY})
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿")), delimiter=";"))
    return dict(zip(rows[0], rows[1]))


async def test_new_categories_are_counted_correctly(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    home = await _type(client, admin, "Homeoffice", "WORK_TIME")
    gfb = await _type(client, admin, "Feiertag GfB", "PUBLIC_HOLIDAY")
    child = await _type(client, admin, "Kind krank", "CHILD_SICK")
    await _absence(client, admin, employee.id, home, MONDAY)
    await _absence(client, admin, employee.id, gfb, TUESDAY)
    await _absence(client, admin, employee.id, child, WEDNESDAY)

    for day in (MONDAY, TUESDAY, WEDNESDAY):
        row = (await client.get(f"/employees/{employee.id}/timesheet", headers=admin, params={"from": day, "to": day})).json()[0]
        assert row["status"] == "ABSENCE" and row["actual_minutes"] == 480, (day, row)

    values = await _payroll(client, admin, employee.id)
    assert values["Ist (Std.)"] == "24,00"
    assert values["Sonderurlaubstage"] == "0" and values["Krankheitstage"] == "0"
    assert values["Feiertage"] == "1"  # Feiertag GfB
    assert values["Kind-krank-Tage"] == "1"

    report = await build_month_report(db_session, await db_session.get(Employee, employee.id), 2026, 10)
    assert report.child_sick_days == 1 and report.sick_days == 0 and report.special_leave_days == 0
    labels = {d.day.isoformat(): d.label for d in report.days}
    assert labels[MONDAY] == "Homeoffice" and labels[WEDNESDAY] == "Kind krank"

    stats = (await client.get("/reports/absence-stats", headers=admin, params={"year": 2026})).json()
    october = next(m for m in stats["months"] if m["month"] == 10)
    assert october["child_sick_days"] == 1 and october["sick_days"] == 0 and october["special_leave_days"] == 0


async def test_change_category_recalculates_existing_entries(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    home = await _type(client, admin, "Homeoffice", "SPECIAL_LEAVE")
    await _absence(client, admin, employee.id, home, MONDAY)
    assert (await _payroll(client, admin, employee.id))["Sonderurlaubstage"] == "1"

    r = await client.patch(f"/absence-types/{home}", headers=admin, json={"category": "WORK_TIME"})
    assert r.status_code == 200 and r.json()["category"] == "WORK_TIME"
    absences = (await client.get(f"/employees/{employee.id}/absences", headers=admin)).json()
    assert [a["type"] for a in absences] == ["WORK_TIME"]
    assert (await _payroll(client, admin, employee.id))["Sonderurlaubstage"] == "0"

    log = (await client.get("/audit-log", headers=admin)).json()
    entries = log["items"] if isinstance(log, dict) else log
    assert any("Kategorie geändert" in (e.get("detail") or "") for e in entries)


async def test_change_from_sick_to_child_sick_and_vacation_balance(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    kind = await _type(client, admin, "Kind krank (alt)", "SICK")
    await _absence(client, admin, employee.id, kind, MONDAY)
    await client.patch(f"/absence-types/{kind}", headers=admin, json={"category": "CHILD_SICK"})
    values = await _payroll(client, admin, employee.id)
    assert values["Krankheitstage"] == "0" and values["Kind-krank-Tage"] == "1"

    # Umstellen auf Urlaub wirkt auch aufs Urlaubskonto
    await client.patch(f"/absence-types/{kind}", headers=admin, json={"category": "VACATION"})
    leave = (await client.get(f"/employees/{employee.id}/leave-entitlement", headers=admin, params={"year": 2026})).json()
    assert leave["used_days"] == 1


async def test_change_blocked_by_locked_month_or_hour_entries(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    home = await _type(client, admin, "Homeoffice", "SPECIAL_LEAVE")
    await _absence(client, admin, employee.id, home, MONDAY, duration_minutes=180)
    r = await client.patch(f"/absence-types/{home}", headers=admin, json={"category": "VACATION"})
    assert r.status_code == 409 and r.json()["code"] == "DURATION_NOT_FOR_VACATION"

    now = datetime.now(UTC).replace(tzinfo=None)
    db_session.add(
        PeriodClosure(
            tenant_id=1, employee_id=employee.id, year=2026, month=10, status=PeriodStatus.CLOSED,
            target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=now, closed_at=now,
        )
    )
    await db_session.commit()
    r = await client.patch(f"/absence-types/{home}", headers=admin, json={"category": "WORK_TIME"})
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_LOCKED"
    types = {t["id"]: t for t in (await client.get("/absence-types", headers=admin)).json()}
    assert types[home]["category"] == "SPECIAL_LEAVE"  # nichts geändert
    absences = (await client.get(f"/employees/{employee.id}/absences", headers=admin)).json()
    assert [a["type"] for a in absences] == ["SPECIAL_LEAVE"]


async def test_category_change_validation_and_permissions(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin = await _setup(db_session, client)
    home = await _type(client, admin, "Homeoffice", "SPECIAL_LEAVE")
    assert (await client.patch(f"/absence-types/{home}", headers=admin, json={"category": "HOMEOFFICE"})).status_code == 422
    hr = {"Authorization": "Bearer " + (await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]}
    assert (await client.patch(f"/absence-types/{home}", headers=hr, json={"category": "WORK_TIME"})).status_code == 403
