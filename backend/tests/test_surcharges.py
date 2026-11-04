import csv
import io
import uuid
from datetime import date, datetime, time

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Compensation, Employee, Holiday, HrRole, HrUser, Location, PayType, SurchargeKind, SurchargeRule
from app.services.auth_service import hash_password
from app.services.surcharge_service import classify_intervals


def _rule(rule_id: int, kind: SurchargeKind, percent: float, start=None, end=None, group=None, mask=127) -> SurchargeRule:
    return SurchargeRule(
        id=rule_id, tenant_id=1, name=f"r{rule_id}", kind=kind, percent=percent,
        start_time=start, end_time=end, exclusive_group=group, weekdays_mask=mask, active=True,
    )


def _iv(day: str, start: str, end: str):
    d = date.fromisoformat(day)
    return (datetime.combine(d, time.fromisoformat(start)), datetime.combine(d, time.fromisoformat(end)))


def test_night_window_crossing_midnight_applies_to_early_morning() -> None:
    night = _rule(1, SurchargeKind.NIGHT, 25, time(23, 0), time(6, 0))
    # Mittwoch 04:00-12:00: nur 04-06 liegt im Fenster des Vortags.
    totals = classify_intervals([_iv("2025-03-05", "04:00", "12:00")], [night], date(2025, 3, 5), False)
    assert totals[1] == 2 * 3600
    # Spätschicht 18-23:30: 23:00-23:30 im Fenster des gleichen Tages.
    totals = classify_intervals([_iv("2025-03-05", "18:00", "23:30")], [night], date(2025, 3, 5), False)
    assert totals[1] == 30 * 60


def test_sunday_and_holiday_in_same_exclusive_group_count_only_the_higher_rate() -> None:
    sunday = _rule(1, SurchargeKind.SUNDAY, 50, group="g")
    holiday = _rule(2, SurchargeKind.HOLIDAY, 125, group="g")
    night = _rule(3, SurchargeKind.NIGHT, 25, time(20, 0), time(6, 0))
    # Sonntag, zugleich Feiertag, 18-22 Uhr: 4 h Feiertag (nicht doppelt Sonntag), davon 2 h Nacht.
    totals = classify_intervals([_iv("2025-04-20", "18:00", "22:00")], [sunday, holiday, night], date(2025, 4, 20), True)
    assert totals.get(2) == 4 * 3600 and 1 not in totals and totals[3] == 2 * 3600
    # Normaler Sonntag: nur Sonntagszuschlag.
    totals = classify_intervals([_iv("2025-04-27", "08:00", "12:00")], [sunday, holiday], date(2025, 4, 27), False)
    assert totals == {1: 4 * 3600}


def test_custom_rule_respects_weekday_mask() -> None:
    saturday_only = _rule(1, SurchargeKind.CUSTOM, 20, time(13, 0), time(20, 0), mask=1 << 5)
    assert classify_intervals([_iv("2025-03-08", "12:00", "16:00")], [saturday_only], date(2025, 3, 8), False) == {1: 3 * 3600}
    assert classify_intervals([_iv("2025-03-07", "12:00", "16:00")], [saturday_only], date(2025, 3, 7), False) == {}


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1")
    db_session.add_all([
        employee,
        HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
    ])
    await db_session.commit()
    await db_session.refresh(employee)
    tokens = {}
    for name in ("hr", "admin"):
        tokens[name] = {"Authorization": "Bearer " + (await client.post("/auth/hr/login", json={"email": f"{name}@example.com", "password": "pw"})).json()["access_token"]}
    return employee, tokens


async def _punch(client, headers, employee_id, punch_type, ts):
    r = await client.post("/punches", headers=headers, json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text


async def test_rule_management_is_admin_only_with_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    _, tokens = await _setup(db_session, client)
    body = {"name": "Nacht", "kind": "NIGHT", "percent": 25, "start_time": "22:00:00", "end_time": "06:00:00"}

    assert (await client.post("/surcharge-rules", headers=tokens["hr"], json=body)).status_code == 403
    assert (await client.post("/surcharge-rules", headers=tokens["admin"], json={**body, "percent": 0})).status_code == 422
    assert (await client.post("/surcharge-rules", headers=tokens["admin"], json={**body, "start_time": None})).status_code == 422
    assert (await client.post("/surcharge-rules", headers=tokens["admin"], json={**body, "weekdays": [7]})).status_code == 422

    created = await client.post("/surcharge-rules", headers=tokens["admin"], json=body)
    assert created.status_code == 201 and created.json()["weekdays"] == [0, 1, 2, 3, 4, 5, 6]
    # HR darf lesen, aber nicht ändern.
    assert len((await client.get("/surcharge-rules", headers=tokens["hr"])).json()) == 1
    assert (await client.patch(f"/surcharge-rules/{created.json()['id']}", headers=tokens["hr"], json={"percent": 30})).status_code == 403
    patched = await client.patch(f"/surcharge-rules/{created.json()['id']}", headers=tokens["admin"], json={"percent": 30})
    assert patched.json()["percent"] == 30

    # Standardregeln nur, wenn noch keine existieren.
    assert (await client.post("/surcharge-rules/defaults", headers=tokens["admin"])).status_code == 409
    assert (await client.delete(f"/surcharge-rules/{created.json()['id']}", headers=tokens["admin"])).status_code == 204
    defaults = await client.post("/surcharge-rules/defaults", headers=tokens["admin"])
    assert defaults.status_code == 201 and len(defaults.json()) == 3


async def test_employee_surcharges_payroll_columns_and_admin_only_amounts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee, tokens = await _setup(db_session, client)
    await client.post("/surcharge-rules/defaults", headers=tokens["admin"])
    db_session.add(Holiday(date=date(2025, 4, 18), name="Karfreitag"))
    db_session.add(Compensation(tenant_id=1, employee_id=employee.id, valid_from=date(2025, 1, 1), pay_type=PayType.HOURLY, amount=20, currency="EUR"))
    await db_session.commit()

    # Sonntag 6.4. 08-12 (4 h) und Karfreitag 18.4. 18-22 (4 h, davon 2 h nach 20 Uhr = Nacht).
    await _punch(client, tokens["hr"], employee.id, "COME", "2025-04-06T08:00:00Z")
    await _punch(client, tokens["hr"], employee.id, "GO", "2025-04-06T12:00:00Z")
    await _punch(client, tokens["hr"], employee.id, "COME", "2025-04-18T18:00:00Z")
    await _punch(client, tokens["hr"], employee.id, "GO", "2025-04-18T22:00:00Z")

    params = {"from": "2025-04-01", "to": "2025-04-30"}
    hr_report = (await client.get(f"/employees/{employee.id}/surcharges", headers=tokens["hr"], params=params)).json()
    by_name = {line["name"]: line for line in hr_report["lines"]}
    assert by_name["Sonntagsarbeit"]["minutes"] == 240
    assert by_name["Feiertagsarbeit"]["minutes"] == 240
    assert by_name["Nachtarbeit (20–6 Uhr)"]["minutes"] == 120
    assert hr_report["hourly_rate"] is None and all(line["amount"] is None for line in hr_report["lines"])

    admin_report = (await client.get(f"/employees/{employee.id}/surcharges", headers=tokens["admin"], params=params)).json()
    assert admin_report["hourly_rate"] == 20
    amounts = {line["name"]: line["amount"] for line in admin_report["lines"]}
    assert amounts["Sonntagsarbeit"] == 40.0  # 4 h x 20 EUR x 50 %
    assert amounts["Feiertagsarbeit"] == 100.0  # 4 h x 20 EUR x 125 %

    export = await client.get("/payroll-export", headers=tokens["hr"], params={"employee_ids": [employee.id], **params})
    rows = list(csv.DictReader(io.StringIO(export.text.lstrip("﻿")), delimiter=";"))
    assert rows[0]["Zuschlag Sonntagsarbeit (Std.)"] == "4,00"
    assert rows[0]["Zuschlag Feiertagsarbeit (Std.)"] == "4,00"


async def test_work_on_a_holiday_is_credited_on_top_of_the_holiday(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, tokens = await _setup(db_session, client)
    db_session.add(Holiday(date=date(2025, 4, 18), name="Karfreitag"))
    await db_session.commit()
    await _punch(client, tokens["hr"], employee.id, "COME", "2025-04-18T08:00:00Z")
    await _punch(client, tokens["hr"], employee.id, "GO", "2025-04-18T12:00:00Z")
    timesheet = (await client.get(f"/employees/{employee.id}/timesheet", headers=tokens["hr"], params={"from": "2025-04-18", "to": "2025-04-18"})).json()
    assert timesheet[0]["status"] == "HOLIDAY" and timesheet[0]["actual_minutes"] == 240
