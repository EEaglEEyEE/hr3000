"""Eine Regel "Tag offen" für "Zu klären", Monatsabschluss, Monatsbericht und Lohn-Export; "Erledigt"
gilt nur, solange sich der Tag nicht ändert."""
import csv
import io
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DayReview, Employee, HrRole, Account, Location, Punch
from app.services.auth_service import hash_password

SATURDAY = "2026-10-10"  # Modell Mo–Fr: Stempeln am Samstag = "außerplanmäßig"


async def _setup(db_session: AsyncSession, client: AsyncClient) -> tuple[int, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Olga", last_name="Offen", employee_number="O1", auto_break_enabled=False)
    db_session.add_all([employee, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    employee_id = employee.id
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    r = await client.put(
        f"/employees/{employee_id}/work-time-model", headers=admin, json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"}
    )
    assert r.status_code == 200
    for punch_type, clock in (("COME", "08:00"), ("GO", "12:00")):
        r = await client.post(
            "/punches", headers=admin,
            json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{SATURDAY}T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text
    return employee_id, admin


async def _open_dates(client: AsyncClient, admin: dict) -> list[str]:
    return [row["work_date"] for row in (await client.get("/timesheet/open-days", headers=admin)).json()]


async def _csv_open_days(client: AsyncClient, admin: dict, employee_id: int) -> str:
    r = await client.get("/payroll-export", headers=admin, params={"employee_ids": [employee_id], "from": "2026-10-10", "to": "2026-10-10"})
    return next(csv.DictReader(io.StringIO(r.text.lstrip("﻿")), delimiter=";"))["Offene/fehlerhafte Tage"]


async def test_reviewed_day_reopens_when_it_changes(client: AsyncClient, db_session: AsyncSession) -> None:
    employee_id, admin = await _setup(db_session, client)
    assert SATURDAY in await _open_dates(client, admin)
    assert await _csv_open_days(client, admin, employee_id) == "1"  # Lohn-Export zählt denselben Tag

    assert (await client.put(f"/employees/{employee_id}/day-reviews/{SATURDAY}", headers=admin)).status_code == 204
    assert SATURDAY not in await _open_dates(client, admin)
    assert await _csv_open_days(client, admin, employee_id) == "0"
    timesheet = (await client.get(f"/employees/{employee_id}/timesheet", headers=admin, params={"from": SATURDAY, "to": SATURDAY})).json()
    assert timesheet[0]["reviewed"] is True

    # Später ändert sich der Tag (Gehen um 13:00 statt 12:00): wieder offen
    go = (
        await db_session.execute(select(Punch).where(Punch.employee_id == employee_id).order_by(Punch.timestamp_utc.desc()))
    ).scalars().first()
    r = await client.patch(f"/punches/{go.id}", headers=admin, json={"timestamp_utc": f"{SATURDAY}T13:00:00Z", "correction_reason": "Korrektur"})
    assert r.status_code == 200, r.text
    assert SATURDAY in await _open_dates(client, admin)
    assert await _csv_open_days(client, admin, employee_id) == "1"

    # erneut abhaken: gilt für den neuen Stand
    assert (await client.put(f"/employees/{employee_id}/day-reviews/{SATURDAY}", headers=admin)).status_code == 204
    assert SATURDAY not in await _open_dates(client, admin)


async def test_old_reviews_without_fingerprint_stay_valid(client: AsyncClient, db_session: AsyncSession) -> None:
    employee_id, admin = await _setup(db_session, client)
    db_session.add(DayReview(tenant_id=1, employee_id=employee_id, work_date=date(2026, 10, 10)))
    await db_session.commit()
    assert SATURDAY not in await _open_dates(client, admin)
    # Abschluss-Übersicht zählt genau die Tage, die "Zu klären" zeigt (eine Regel)
    open_in_october = [d for d in await _open_dates(client, admin) if d.startswith("2026-10")]
    overview = (await client.get("/period-closures", headers=admin, params={"year": 2026, "month": 10})).json()
    assert overview[0]["open_day_count"] == len(open_in_october) > 0
