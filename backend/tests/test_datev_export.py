"""DATEV-LODAS-Export: Importdatei mit Ist-Stunden (Stundenlöhner), Zuschlagsstunden und
Zulagen/Einmalzahlungen je Lohnart; Hinweise für alles, was nicht übertragen werden kann."""
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Compensation, Employee, HrRole, HrUser, Location, PayType
from app.services.auth_service import hash_password

AUGUST = {"month": "2026-08"}


async def _setup(db_session: AsyncSession, client: AsyncClient) -> tuple[list[Employee], dict, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    hourly = Employee(location_id=location.id, first_name="Hanna", last_name="Hourly", employee_number="12", auto_break_enabled=False)
    salaried = Employee(location_id=location.id, first_name="Sven", last_name="Salary", employee_number="13", auto_break_enabled=False)
    odd = Employee(location_id=location.id, first_name="Olga", last_name="Odd", employee_number="A-7", auto_break_enabled=False)
    db_session.add_all(
        [
            hourly,
            salaried,
            odd,
            HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
            HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        ]
    )
    await db_session.commit()
    for employee in (hourly, salaried, odd):
        await db_session.refresh(employee)
    db_session.add_all(
        [
            Compensation(tenant_id=1, employee_id=hourly.id, valid_from=date(2026, 1, 1), pay_type=PayType.HOURLY, amount=15, currency="EUR"),
            Compensation(tenant_id=1, employee_id=salaried.id, valid_from=date(2026, 1, 1), pay_type=PayType.MONTHLY, amount=3000, currency="EUR"),
        ]
    )
    await db_session.commit()
    tokens = []
    for email in ("admin@example.com", "hr@example.com"):
        login = await client.post("/auth/hr/login", json={"email": email, "password": "pw"})
        tokens.append({"Authorization": f"Bearer {login.json()['access_token']}"})
    return [hourly, salaried, odd], tokens[0], tokens[1]


async def _work(client: AsyncClient, admin: dict, employee: Employee, day: str, come: str, go: str) -> None:
    for punch_type, clock in (("COME", come), ("GO", go)):
        r = await client.post(
            "/punches",
            headers=admin,
            json={"employee_id": employee.id, "punch_type": punch_type, "timestamp_utc": f"{day}T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text


def _params(employees: list[Employee]) -> dict:
    return {**AUGUST, "employee_ids": [e.id for e in employees]}


async def test_datev_requires_configuration_and_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    employees, admin, hr = await _setup(db_session, client)
    r = await client.get("/payroll-export/datev", headers=admin, params=_params(employees))
    assert r.status_code == 400 and r.json()["code"] == "DATEV_NOT_CONFIGURED"
    r = await client.patch("/settings", headers=admin, json={"datev_consultant_number": "123", "datev_client_number": "1"})
    assert r.status_code == 422  # Beraternummer 4–7 Ziffern
    r = await client.patch("/settings", headers=admin, json={"datev_consultant_number": "1234567", "datev_client_number": "123456"})
    assert r.status_code == 422  # Mandantennummer 1–5 Ziffern
    r = await client.patch("/settings", headers=admin, json={"datev_consultant_number": "1234567", "datev_client_number": "10001"})
    assert r.status_code == 200 and r.json()["datev_client_number"] == "10001"
    assert (await client.get("/payroll-export/datev", headers=hr, params=_params(employees))).status_code == 403
    assert (await client.get("/payroll-export/datev", headers=admin, params={**_params(employees), "month": "2026-13"})).status_code == 422


async def test_datev_file_and_preview(client: AsyncClient, db_session: AsyncSession) -> None:
    (hourly, salaried, odd), admin, _ = await _setup(db_session, client)
    await client.patch(
        "/settings",
        headers=admin,
        json={"datev_consultant_number": "1234567", "datev_client_number": "10001", "datev_hours_wage_type": "1000"},
    )
    night = await client.post(
        "/surcharge-rules",
        headers=admin,
        json={"name": "Nacht", "kind": "NIGHT", "percent": 25, "start_time": "22:00", "end_time": "06:00", "wage_type": "1200"},
    )
    assert night.status_code == 201 and night.json()["wage_type"] == "1200"
    await client.post("/surcharge-rules", headers=admin, json={"name": "Sonntag", "kind": "SUNDAY", "percent": 50})

    await _work(client, admin, hourly, "2026-08-10", "14:00", "23:00")  # 9 Std., davon 1 Std. Nacht
    await _work(client, admin, hourly, "2026-08-16", "10:00", "12:00")  # Sonntag (ohne Lohnart)
    await _work(client, admin, salaried, "2026-08-11", "08:00", "16:00")
    for employee, payload in (
        (hourly, {"kind": "ONE_TIME", "name": "Urlaubsgeld", "amount": 300, "pay_date": "2026-08-20", "wage_type": "3000"}),
        (salaried, {"kind": "ALLOWANCE", "name": "Fahrtkosten", "amount": 50, "unit": "PER_MONTH", "valid_from": "2026-01-01", "wage_type": "2000"}),
        (salaried, {"kind": "ONE_TIME", "name": "Prämie", "amount": 99.5, "pay_date": "2026-08-31"}),
    ):
        r = await client.post(f"/employees/{employee.id}/pay-components", headers=admin, json=payload)
        assert r.status_code == 201, r.text

    params = _params([hourly, salaried, odd])
    r = await client.get("/payroll-export/datev", headers=admin, params=params)
    assert r.status_code == 200, r.text
    assert 'filename="datev-lodas_2026-08.txt"' in r.headers["content-disposition"]
    lines = r.content.decode("cp1252").split("\r\n")
    assert lines[:8] == [
        "[Allgemein]",
        "Ziel=LODAS",
        "Version_SST=1.0",
        "BeraterNr=1234567",
        "MandantenNr=10001",
        "Datumsformat=TT.MM.JJJJ",
        "Feldtrennzeichen=;",
        "Zahlenkomma=,",
    ]
    assert "1;u_lod_bwd_buchung_standard;abrechnung_zeitraum#bwd;pnr#bwd;la_eigene#bwd;bs_nr#bwd;bs_wert_butab#bwd;" in lines
    data = lines[lines.index("[Bewegungsdaten]") + 1 :]
    assert [line for line in data if line] == [
        # Hourly: 9 + 2 Ist-Stunden (Stundenlohn), 1 Nachtstunde, Urlaubsgeld
        "1;01.08.2026;12;1000;01;11,00;",
        "1;01.08.2026;12;1200;01;1,00;",
        "1;01.08.2026;12;3000;02;300,00;",
        # Salary: Monatsgehalt -> keine Stunden; Fahrtkosten als Betrag
        "1;01.08.2026;13;2000;02;50,00;",
    ]

    preview = await client.get("/payroll-export/datev/preview", headers=admin, params=params)
    assert preview.status_code == 200
    body = preview.json()
    assert body["lines"][0] == {
        "personnel_number": "12", "name": "Hourly, Hanna", "wage_type": "1000", "key": "01", "value": 11.0, "label": "Ist-Stunden"
    }
    warnings = "\n".join(body["warnings"])
    assert "Odd, Olga: Personalnummer „A-7“ ist nicht rein numerisch" in warnings
    assert "Salary, Sven: Einmalzahlung Prämie ohne Lohnart" in warnings
    assert "Zuschlag „Sonntag“ ohne Lohnart" in warnings


async def test_datev_hours_without_wage_type_warns(client: AsyncClient, db_session: AsyncSession) -> None:
    (hourly, _, _), admin, _ = await _setup(db_session, client)
    await client.patch("/settings", headers=admin, json={"datev_consultant_number": "1234567", "datev_client_number": "10001"})
    await _work(client, admin, hourly, "2026-08-10", "08:00", "12:00")
    body = (await client.get("/payroll-export/datev/preview", headers=admin, params=_params([hourly]))).json()
    assert body["lines"] == []
    assert any("Keine Lohnart für Ist-Stunden" in w and "Hourly, Hanna" in w for w in body["warnings"])
