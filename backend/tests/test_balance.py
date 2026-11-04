"""Gleitzeitkonto: zählt jeden Soll-Tag, reagiert auf Abwesenheiten, Plan- und Feiertagsänderungen,
Korrekturbuchungen und den Saldo-Beginn."""
import uuid
from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLogEntry, Employee, EmployeeDefaultShift, HrRole, HrUser, Location, ShiftTemplate
from app.services.auth_service import hash_password

MONDAY = date(2026, 8, 10)
TUESDAY = date(2026, 8, 11)
WEDNESDAY = date(2026, 8, 12)


async def _setup(db_session: AsyncSession, client: AsyncClient, *, termination: date | None = WEDNESDAY, mask: int = 0b0011111):
    location = Location(name="A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1",
        termination_date=termination, login_email="e@example.com", password_hash=hash_password("pw"),
    )
    template = ShiftTemplate(name="Normal", target_minutes=480)
    db_session.add_all([
        employee, template,
        HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        HrUser(email="sup@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR),
    ])
    await db_session.commit()
    db_session.add(EmployeeDefaultShift(employee_id=employee.id, shift_template_id=template.id, valid_from=date(2026, 1, 1), weekdays_mask=mask))
    await db_session.commit()
    headers = {}
    for name in ("hr", "sup"):
        headers[name] = {"Authorization": "Bearer " + (await client.post("/auth/hr/login", json={"email": f"{name}@example.com", "password": "pw"})).json()["access_token"]}
    headers["self"] = {"Authorization": "Bearer " + (await client.post("/auth/employee/login", json={"email": "e@example.com", "password": "pw"})).json()["access_token"]}
    return employee, headers


async def _punch(client, headers, employee_id, punch_type, ts: str):
    r = await client.post("/punches", headers=headers, json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text


async def _balance(client, headers, employee_id) -> dict:
    r = await client.get(f"/employees/{employee_id}/overtime-balance", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_missing_days_count_and_absences_neutralize_them(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    await _punch(client, headers["hr"], employee.id, "COME", "2026-08-10T08:00:00Z")
    await _punch(client, headers["hr"], employee.id, "GO", "2026-08-10T16:00:00Z")  # Montag genau 8 Std.

    # Di + Mi: Soll ohne Stempelung und ohne Abwesenheit -> je -8 Std.
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == -960

    sick = await client.post("/absences", headers=headers["hr"], json={"employee_id": employee.id, "type": "SICK", "date_from": "2026-08-11", "date_to": "2026-08-12"})
    assert sick.status_code == 201
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == 0

    # Abwesenheit verkürzen -> Mittwoch fehlt wieder.
    await client.patch(f"/absences/{sick.json()['id']}", headers=headers["hr"], json={"date_to": "2026-08-11"})
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == -480
    await client.delete(f"/absences/{sick.json()['id']}", headers=headers["hr"])
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == -960

    # Missing days also show up in "Zu klären".
    open_days = (await client.get("/timesheet/open-days", headers=headers["hr"])).json()
    assert {d["work_date"] for d in open_days} == {"2026-08-11", "2026-08-12"}


async def test_plan_and_holiday_changes_update_the_balance(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    await _punch(client, headers["hr"], employee.id, "COME", "2026-08-10T08:00:00Z")
    await _punch(client, headers["hr"], employee.id, "GO", "2026-08-10T16:00:00Z")
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == -960

    # Mittwoch laut Schichtplan frei -> kein Soll mehr.
    free = await client.put(f"/employees/{employee.id}/shift-plan-entries/2026-08-12", headers=headers["hr"], json={"is_workday": False})
    assert free.status_code == 200, free.text
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == -480

    # Dienstag wird Feiertag -> Soll gutgeschrieben.
    holiday = await client.post("/holidays", headers=headers["hr"], json={"date": "2026-08-11", "name": "Testfeiertag", "location_ids": []})
    assert holiday.status_code == 201, holiday.text
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == 0

    await client.delete(f"/holidays/{holiday.json()['id']}", headers=headers["hr"])
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == -480


async def test_today_counts_only_once_completed(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client, termination=None, mask=0b1111111)
    today = datetime.now(UTC).date()
    await _punch(client, headers["hr"], employee.id, "COME", f"{today.isoformat()}T00:00:10Z")
    # Anwesend: der laufende Tag zählt noch nicht (kein "-8 Std." beim Einstempeln).
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == 0
    await _punch(client, headers["hr"], employee.id, "GO", f"{today.isoformat()}T00:00:20Z")
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == -480


async def test_balance_start_setting_cuts_history(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    await _punch(client, headers["hr"], employee.id, "COME", "2026-08-10T08:00:00Z")
    await _punch(client, headers["hr"], employee.id, "GO", "2026-08-10T12:00:00Z")  # Mo -4 Std.
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == -240 - 960

    admin = HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)
    db_session.add(admin)
    await db_session.commit()
    admin_headers = {"Authorization": "Bearer " + (await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]}
    r = await client.patch("/settings", headers=admin_headers, json={"balance_start_date": "2026-08-12"})
    assert r.status_code == 200 and r.json()["balance_start_date"] == "2026-08-12"
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == -480  # nur noch Mittwoch


async def test_manual_adjustments(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    await _punch(client, headers["hr"], employee.id, "COME", "2026-08-10T08:00:00Z")
    await _punch(client, headers["hr"], employee.id, "GO", "2026-08-10T16:00:00Z")
    url = f"/employees/{employee.id}/balance-adjustments"
    body = {"effective_date": "2026-08-10", "minutes": 600, "kind": "OPENING_BALANCE", "note": "Übertrag Altsystem"}

    assert (await client.post(url, headers=headers["sup"], json=body)).status_code == 403
    assert (await client.post(url, headers=headers["self"], json=body)).status_code == 403
    assert (await client.post(url, headers=headers["hr"], json={**body, "minutes": 0})).status_code == 422
    assert (await client.post(url, headers=headers["hr"], json={**body, "note": "  "})).status_code == 422
    future = (date.today() + timedelta(days=3)).isoformat()
    assert (await client.post(url, headers=headers["hr"], json={**body, "effective_date": future})).status_code == 400

    created = await client.post(url, headers=headers["hr"], json=body)
    assert created.status_code == 201
    balance = await _balance(client, headers["self"], employee.id)
    assert balance["adjustment_minutes"] == 600 and balance["running_balance_minutes"] == 600 - 960
    assert len((await client.get(url, headers=headers["self"])).json()) == 1

    assert (await client.delete(f"{url}/{created.json()['id']}", headers=headers["hr"])).status_code == 204
    assert (await _balance(client, headers["hr"], employee.id))["running_balance_minutes"] == -960
    actions = [e.action for e in (await db_session.execute(select(AuditLogEntry))).scalars().all()]
    assert actions.count(AuditAction.BALANCE_ADJUSTED) == 2


async def test_account_without_punches_starts_at_tenant_start_date(client: AsyncClient, db_session: AsyncSession) -> None:
    """Ohne Stichtag: kein Konto bis zur ersten Stempelung. Mit Stichtag: Konto ab dann, fehlende
    Tage zählen ins Minus – auch wenn der Mitarbeiter nie gestempelt hat."""
    from app.services.settings_service import get_or_create_settings

    employee, headers = await _setup(db_session, client)
    balance = await _balance(client, headers["hr"], employee.id)
    assert balance["running_balance_minutes"] == 0 and balance["balance_start"] is None

    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    settings_row.balance_start_date = TUESDAY
    employee.balance_through = None
    await db_session.commit()
    balance = await _balance(client, headers["hr"], employee.id)
    assert balance["balance_start"] == "2026-08-11"
    assert balance["running_balance_minutes"] == -960  # Di + Mi (Austritt Mi) je -8 Std.
