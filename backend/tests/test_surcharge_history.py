"""Zuschlagsregeln mit Verlauf: Satz/Zeitfenster/Wochentage gelten ab Stichtag als neue Fassung,
zurückliegende Zeiträume rechnen mit der alten; eine Spalte je Regel im Lohn-Export."""
import csv
import io
import uuid
from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location, PeriodClosure, PeriodStatus
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient) -> tuple[int, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Nina", last_name="Nacht", employee_number="N1", auto_break_enabled=False)
    db_session.add_all([employee, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    employee_id = employee.id
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    for day in ("2026-10-05", "2026-10-12"):  # je 2 Std. in der Nacht (22–24 Uhr)
        for punch_type, clock in (("COME", "18:00"), ("GO", "23:59")):
            r = await client.post(
                "/punches", headers=admin,
                json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{day}T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
            )
            assert r.status_code == 201, r.text
    return employee_id, admin


async def test_rate_change_from_date_keeps_the_past(client: AsyncClient, db_session: AsyncSession) -> None:
    employee_id, admin = await _setup(db_session, client)
    r = await client.post("/surcharge-rules", headers=admin, json={"name": "Nacht", "kind": "NIGHT", "percent": 25, "start_time": "22:00", "end_time": "06:00"})
    assert r.status_code == 201 and r.json()["valid_from"] is None
    rule_id = r.json()["id"]

    r = await client.patch(f"/surcharge-rules/{rule_id}", headers=admin, json={"percent": 40, "valid_from": "2026-10-10"})
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["id"] != rule_id and new["percent"] == 40 and new["valid_from"] == "2026-10-10" and new["family_id"] == rule_id
    assert [x["id"] for x in (await client.get("/surcharge-rules", headers=admin)).json()] == [new["id"]]
    history = (await client.get("/surcharge-rules", headers=admin, params={"include_history": True})).json()
    assert [(x["percent"], x["valid_to"]) for x in history] == [(25, "2026-10-09"), (40, None)]

    lines = (await client.get(f"/employees/{employee_id}/surcharges", headers=admin, params={"from": "2026-10-01", "to": "2026-10-31"})).json()["lines"]
    assert sorted((line["percent"], line["minutes"]) for line in lines) == [(25, 119), (40, 119)]

    r = await client.get("/payroll-export", headers=admin, params={"employee_ids": [employee_id], "from": "2026-10-01", "to": "2026-10-31"})
    row = next(csv.DictReader(io.StringIO(r.text.lstrip("﻿")), delimiter=";"))
    assert row["Zuschlag Nacht (Std.)"] == "3,97"  # eine Spalte über beide Fassungen
    assert sum(1 for key in row if key.startswith("Zuschlag ")) == 1

    # Name ändern: in der Fassung, keine neue Fassung
    r = await client.patch(f"/surcharge-rules/{new['id']}", headers=admin, json={"name": "Nachtarbeit"})
    assert r.json()["id"] == new["id"] and r.json()["name"] == "Nachtarbeit"
    # Satz zum selben Stichtag nochmal ändern: ebenfalls in der Fassung
    r = await client.patch(f"/surcharge-rules/{new['id']}", headers=admin, json={"percent": 30, "valid_from": "2026-10-10"})
    assert r.json()["id"] == new["id"] and r.json()["percent"] == 30

    # Fassung löschen: die vorherige gilt wieder offen
    assert (await client.delete(f"/surcharge-rules/{new['id']}", headers=admin)).status_code == 204
    remaining = (await client.get("/surcharge-rules", headers=admin, params={"include_history": True})).json()
    assert [(x["id"], x["percent"], x["valid_to"]) for x in remaining] == [(rule_id, 25, None)]


async def test_change_not_into_closed_month(client: AsyncClient, db_session: AsyncSession) -> None:
    employee_id, admin = await _setup(db_session, client)
    rule_id = (await client.post("/surcharge-rules", headers=admin, json={"name": "Sonntag", "kind": "SUNDAY", "percent": 50})).json()["id"]
    db_session.add(
        PeriodClosure(
            tenant_id=1, employee_id=employee_id, year=2026, month=10, status=PeriodStatus.CLOSED, target_minutes=0,
            actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=datetime(2026, 11, 2, 9, 0),
        )
    )
    await db_session.commit()
    r = await client.patch(f"/surcharge-rules/{rule_id}", headers=admin, json={"percent": 60, "valid_from": "2026-10-15"})
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_LOCKED"
    r = await client.patch(f"/surcharge-rules/{rule_id}", headers=admin, json={"percent": 60, "valid_from": "2026-11-01"})
    assert r.status_code == 200 and r.json()["valid_from"] == "2026-11-01"
    r = await client.post("/surcharge-rules", headers=admin, json={"name": "Feiertag", "kind": "HOLIDAY", "percent": 125, "valid_from": "2026-10-01"})
    assert r.status_code == 409
