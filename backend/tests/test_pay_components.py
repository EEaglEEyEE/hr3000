"""Zulagen (je Monat oder je Ist-Stunde) und Einmalzahlungen: nur Admin, Audit ohne Beträge, im
Lohn-Export nur, wenn ein Admin ihn zieht; abgeschlossene Monate bleiben unverändert."""
import csv
import io
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, HrUser, Location, PeriodClosure, PeriodStatus
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient) -> tuple[Employee, dict, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Zoe", last_name="Zulage", employee_number="Z1", auto_break_enabled=False)
    db_session.add_all(
        [
            employee,
            HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
            HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        ]
    )
    await db_session.commit()
    await db_session.refresh(employee)
    tokens = []
    for email in ("admin@example.com", "hr@example.com"):
        login = await client.post("/auth/hr/login", json={"email": email, "password": "pw"})
        tokens.append({"Authorization": f"Bearer {login.json()['access_token']}"})
    return employee, tokens[0], tokens[1]


def _rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=";"))


async def _create(client: AsyncClient, admin: dict, employee: Employee, **payload) -> dict:
    r = await client.post(f"/employees/{employee.id}/pay-components", headers=admin, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def test_admin_manages_pay_components_hr_cannot(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, hr = await _setup(db_session, client)
    url = f"/employees/{employee.id}/pay-components"
    allowance = await _create(
        client, admin, employee, kind="ALLOWANCE", name=" Fahrtkosten ", amount=50, unit="PER_MONTH", valid_from="2026-08-16", wage_type="2000"
    )
    assert allowance["name"] == "Fahrtkosten" and allowance["pay_date"] is None
    bonus = await _create(client, admin, employee, kind="ONE_TIME", name="Weihnachtsgeld", amount=500, pay_date="2026-11-30")
    assert bonus["unit"] is None and bonus["valid_from"] is None

    listed = (await client.get(url, headers=admin)).json()
    assert [c["name"] for c in listed] == ["Fahrtkosten", "Weihnachtsgeld"]
    for method, path in (("GET", url), ("POST", url), ("DELETE", f"{url}/{bonus['id']}")):
        r = await client.request(method, path, headers=hr, json={} if method == "POST" else None)
        assert r.status_code == 403, (method, path)

    r = await client.patch(f"{url}/{allowance['id']}", headers=admin, json={"valid_to": "2026-12-31", "note": "bis Jahresende"})
    assert r.status_code == 200 and r.json()["valid_to"] == "2026-12-31" and r.json()["note"] == "bis Jahresende"
    r = await client.patch(f"{url}/{allowance['id']}", headers=admin, json={"valid_to": "2026-08-01"})
    assert r.status_code == 400
    r = await client.patch(f"{url}/{bonus['id']}", headers=admin, json={"valid_to": "2026-12-31"})
    assert r.status_code == 400 and r.json()["code"] == "NOT_AN_ALLOWANCE"
    assert (await client.delete(f"{url}/{bonus['id']}", headers=admin)).status_code == 204

    entries = (await client.get("/audit-log", headers=admin)).json()
    details = [e["detail"] for e in entries if e["action"] in ("COMPENSATION_CHANGED", "COMPENSATION_VIEWED")]
    assert "Zulage „Fahrtkosten“ angelegt (ab 2026-08-16)" in details
    assert "Einmalzahlung „Weihnachtsgeld“ gelöscht" in details
    assert not any("50" in d or "500" in d for d in details)  # keine Beträge im Audit-Log


async def test_pay_component_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    url = f"/employees/{employee.id}/pay-components"
    for payload in (
        {"kind": "ALLOWANCE", "name": "X", "amount": 10, "valid_from": "2026-08-01"},  # ohne Einheit
        {"kind": "ALLOWANCE", "name": "X", "amount": 10, "unit": "PER_MONTH"},  # ohne Beginn
        {"kind": "ALLOWANCE", "name": "X", "amount": 10, "unit": "PER_MONTH", "valid_from": "2026-08-01", "valid_to": "2026-07-01"},
        {"kind": "ONE_TIME", "name": "X", "amount": 10},  # ohne Datum
        {"kind": "ONE_TIME", "name": "  ", "amount": 10, "pay_date": "2026-08-01"},
        {"kind": "ONE_TIME", "name": "X", "amount": 10.005, "pay_date": "2026-08-01"},
        {"kind": "ONE_TIME", "name": "X", "amount": 0, "pay_date": "2026-08-01"},
        {"kind": "ONE_TIME", "name": "X", "amount": 10, "pay_date": "2026-08-01", "wage_type": "LA12"},
        {"kind": "BONUS", "name": "X", "amount": 10, "pay_date": "2026-08-01"},
    ):
        r = await client.post(url, headers=admin, json=payload)
        assert r.status_code == 422, payload


async def test_payroll_export_amounts_only_for_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, hr = await _setup(db_session, client)
    await _create(client, admin, employee, kind="ALLOWANCE", name="Fahrtkosten", amount=50, unit="PER_MONTH", valid_from="2026-08-16")
    await _create(client, admin, employee, kind="ALLOWANCE", name="Erschwernis", amount=1.5, unit="PER_HOUR", valid_from="2026-08-01")
    await _create(client, admin, employee, kind="ONE_TIME", name="Urlaubsgeld", amount=300, pay_date="2026-08-20")
    await _create(client, admin, employee, kind="ONE_TIME", name="Weihnachtsgeld", amount=500, pay_date="2026-11-30")
    for punch_type, ts in (("COME", "2026-08-10T06:00:00Z"), ("GO", "2026-08-10T14:00:00Z")):
        r = await client.post(
            "/punches",
            headers=admin,
            json={"employee_id": employee.id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201

    params = {"employee_ids": [employee.id], "from": "2026-08-01", "to": "2026-08-31"}
    r = await client.get("/payroll-export", params=params, headers=admin)
    assert r.status_code == 200, r.text
    row = _rows(r.text)[0]
    assert row["Zulage Erschwernis (€)"] == "12,00"  # 8 Ist-Stunden × 1,50 €
    assert row["Zulage Fahrtkosten (€)"] == "25,81"  # 16 von 31 Tagen
    assert row["Einmalzahlung Urlaubsgeld (€)"] == "300,00"
    assert "Einmalzahlung Weihnachtsgeld (€)" not in row  # liegt nicht im Zeitraum
    header = r.text.lstrip("﻿").splitlines()[0].split(";")
    assert header[-3:] == ["Zulage Erschwernis (€)", "Zulage Fahrtkosten (€)", "Einmalzahlung Urlaubsgeld (€)"]

    september = _rows((await client.get("/payroll-export", params={**params, "from": "2026-09-01", "to": "2026-09-30"}, headers=admin)).text)[0]
    assert september["Zulage Fahrtkosten (€)"] == "50,00"
    assert september["Zulage Erschwernis (€)"] == "0,00"

    hr_row = _rows((await client.get("/payroll-export", params=params, headers=hr)).text)[0]
    assert not any(key.startswith(("Zulage", "Einmalzahlung")) for key in hr_row)


async def test_closed_month_stays_unchanged(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _ = await _setup(db_session, client)
    db_session.add(
        PeriodClosure(
            tenant_id=1, employee_id=employee.id, year=2026, month=8, status=PeriodStatus.CLOSED,
            target_minutes=0, actual_minutes=0, delta_minutes=0, balance_end_minutes=0, submitted_at=date(2026, 9, 1),
        )
    )
    await db_session.commit()
    url = f"/employees/{employee.id}/pay-components"
    r = await client.post(url, headers=admin, json={"kind": "ONE_TIME", "name": "Prämie", "amount": 100, "pay_date": "2026-08-15"})
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_LOCKED"
    r = await client.post(url, headers=admin, json={"kind": "ALLOWANCE", "name": "Bonus", "amount": 20, "unit": "PER_MONTH", "valid_from": "2026-07-01"})
    assert r.status_code == 409
    allowance = await _create(client, admin, employee, kind="ALLOWANCE", name="Bonus", amount=20, unit="PER_MONTH", valid_from="2026-07-01", valid_to="2026-07-31")
    # Verlängern in den abgeschlossenen August: gesperrt; Lohnart (an der Art) ändern geht
    r = await client.patch(f"{url}/{allowance['id']}", headers=admin, json={"clear_valid_to": True})
    assert r.status_code == 409
    r = await client.patch(f"/pay-component-types/{allowance['type_id']}", headers=admin, json={"wage_type": "2100"})
    assert r.status_code == 200 and r.json()["wage_type"] == "2100"
    assert (await client.get(url, headers=admin)).json()[0]["wage_type"] == "2100"
