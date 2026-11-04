"""Schichten über Mitternacht gehören zum Tag des Kommens."""
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, EmployeeDefaultShift, HrRole, HrUser, Location, ShiftTemplate

SATURDAY = "2026-08-15"


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="A", timezone="Europe/Berlin")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Nina", last_name="Nacht", employee_number="N1", termination_date=date(2026, 8, 16))
    template = ShiftTemplate(name="Nacht", target_minutes=480)
    db_session.add_all([employee, template, HrUser(email="admin@example.com", password_hash=__import__("app.services.auth_service", fromlist=["hash_password"]).hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    db_session.add(EmployeeDefaultShift(employee_id=employee.id, shift_template_id=template.id, valid_from=date(2026, 1, 1), weekdays_mask=1 << 5))  # nur Samstag
    await db_session.commit()
    token = (await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    return employee, {"Authorization": f"Bearer {token}"}


async def _punch(client, headers, employee_id, punch_type, ts):
    r = await client.post("/punches", headers=headers, json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text


async def test_night_shift_counts_on_start_day_with_sunday_and_night_surcharges(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    # Samstag 22:00 bis Sonntag 06:00 Ortszeit (CEST = UTC+2).
    await _punch(client, headers, employee.id, "COME", "2026-08-15T20:00:00Z")
    await _punch(client, headers, employee.id, "GO", "2026-08-16T04:00:00Z")

    days = {d["work_date"]: d for d in (await client.get(f"/employees/{employee.id}/timesheet", headers=headers, params={"from": "2026-08-15", "to": "2026-08-16"})).json()}
    assert days[SATURDAY]["status"] == "COMPLETE" and days[SATURDAY]["actual_minutes"] == 480
    assert days["2026-08-16"]["actual_minutes"] is None  # Sonntag kein eigener (fehlerhafter) Tag
    assert days["2026-08-16"]["status"] != "ERROR"

    balance = (await client.get(f"/employees/{employee.id}/overtime-balance", headers=headers)).json()
    assert balance["running_balance_minutes"] == 0

    await client.post("/surcharge-rules", headers=headers, json={"name": "Nacht", "kind": "NIGHT", "percent": 25, "start_time": "20:00:00", "end_time": "06:00:00"})
    await client.post("/surcharge-rules", headers=headers, json={"name": "Sonntag", "kind": "SUNDAY", "percent": 50})
    report = (await client.get(f"/employees/{employee.id}/surcharges", headers=headers, params={"from": SATURDAY, "to": SATURDAY})).json()
    minutes = {line["name"]: line["minutes"] for line in report["lines"]}
    assert minutes["Nacht"] == 480  # komplett im Nachtfenster
    assert minutes["Sonntag"] == 360  # ab 0 Uhr Sonntag


async def test_go_much_later_is_treated_as_forgotten(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    await _punch(client, headers, employee.id, "COME", "2026-08-15T06:00:00Z")
    await _punch(client, headers, employee.id, "GO", "2026-08-16T05:00:00Z")  # 23 Std. später
    days = {d["work_date"]: d for d in (await client.get(f"/employees/{employee.id}/timesheet", headers=headers, params={"from": "2026-08-15", "to": "2026-08-16"})).json()}
    # Samstag bleibt offen ("Gehen" vergessen), das späte "Gehen" wird nicht als 23-Std.-Schicht gezählt.
    assert days[SATURDAY]["status"] == "OPEN_MISSING_PUNCH" and days[SATURDAY]["actual_minutes"] is None
