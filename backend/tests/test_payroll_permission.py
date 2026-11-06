"""Berechtigung „Vergütung & Lohn-Export“: Admins immer, HR nur mit Freigabe – gleich für Vergütung,
Zulagen, Lohnkosten, DATEV, Lohnarten und Beträge im Lohn-Export."""
import csv
import io
from datetime import date
from decimal import Decimal

import jwt
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AllowanceUnit, Employee, HrRole, HrUser, Location, PayComponent, PayComponentKind, PayComponentType
from app.services.auth_service import hash_password


async def _login(client: AsyncClient, email: str) -> dict:
    token = (await client.post("/auth/hr/login", json={"email": email, "password": "pw"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _setup(db_session: AsyncSession, client: AsyncClient) -> tuple[int, dict, dict, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Paul", last_name="Payroll", employee_number="P1")
    db_session.add_all(
        [
            employee,
            HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
            HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
            HrUser(email="lohn@example.com", password_hash=hash_password("pw"), role=HrRole.HR, payroll_access=True),
        ]
    )
    await db_session.commit()
    employee_id = employee.id
    db_session.add(
        PayComponent(
            tenant_id=1, employee_id=employee_id, kind=PayComponentKind.ALLOWANCE, amount=Decimal("50"), unit=AllowanceUnit.PER_MONTH,
            valid_from=date(2026, 1, 1), type=PayComponentType(tenant_id=1, kind=PayComponentKind.ALLOWANCE, name="Fahrtkosten"),
        )
    )
    await db_session.commit()
    return employee_id, await _login(client, "admin@example.com"), await _login(client, "hr@example.com"), await _login(client, "lohn@example.com")


def _claims(headers: dict) -> dict:
    return jwt.decode(headers["Authorization"].split()[1], settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


async def test_same_permission_everywhere(client: AsyncClient, db_session: AsyncSession) -> None:
    employee_id, admin, hr, payroll = await _setup(db_session, client)
    assert (_claims(admin)["payroll"], _claims(hr)["payroll"], _claims(payroll)["payroll"]) == (True, False, True)
    month = {"employee_ids": [employee_id], "month": "2026-10"}
    endpoints = [
        ("GET", f"/employees/{employee_id}/compensation", None),
        ("GET", f"/employees/{employee_id}/pay-components", None),
        ("GET", "/reports/labor-costs", {"from": "2026-10-01", "to": "2026-10-31"}),
        ("GET", "/payroll-export/datev/preview", month),
        ("GET", "/payroll-export/datev/settings", None),
        ("GET", "/wage-types", None),
        ("GET", "/pay-component-types", None),
    ]
    await client.put("/payroll-export/datev/settings", headers=admin, json={"consultant_number": "1234567", "client_number": "10001"})
    for method, path, params in endpoints:
        for headers, expected in ((hr, 403), (payroll, 200), (admin, 200)):
            r = await client.request(method, path, headers=headers, params=params)
            assert r.status_code == expected, (path, expected, r.text)

    # Lohn-Export (CSV) dürfen alle mit vollem HR-Zugriff, Beträge nur mit Berechtigung
    params = {"employee_ids": [employee_id], "from": "2026-10-01", "to": "2026-10-31"}
    for headers, has_amounts in ((hr, False), (payroll, True)):
        r = await client.get("/payroll-export", headers=headers, params=params)
        header = next(csv.reader(io.StringIO(r.text.lstrip("﻿")), delimiter=";"))
        assert ("Zulage Fahrtkosten (€)" in header) is has_amounts

    # Lohnart eines Zuschlags: mit Berechtigung; die Regel selbst ändern nur Admins
    rule = (await client.post("/surcharge-rules", headers=admin, json={"name": "Sonntag", "kind": "SUNDAY", "percent": 50})).json()
    assert (await client.put(f"/surcharge-rules/{rule['id']}/wage-type", headers=hr, json={"wage_type": "1300"})).status_code == 403
    r = await client.put(f"/surcharge-rules/{rule['id']}/wage-type", headers=payroll, json={"wage_type": "1300"})
    assert r.status_code == 200 and r.json()["wage_type"] == "1300"
    assert (await client.patch(f"/surcharge-rules/{rule['id']}", headers=payroll, json={"percent": 60})).status_code == 403
    # DATEV-Nummern ohne Zugriff auf die Einstellungen
    r = await client.put("/payroll-export/datev/settings", headers=payroll, json={"consultant_number": "7654321", "client_number": "2"})
    assert r.status_code == 200 and (await client.get("/settings", headers=admin)).json()["datev_consultant_number"] == "7654321"
    assert (await client.put("/payroll-export/datev/settings", headers=payroll, json={"consultant_number": "12", "client_number": "2"})).status_code == 422


async def test_grant_via_hr_role(client: AsyncClient, db_session: AsyncSession) -> None:
    employee_id, admin, _, payroll = await _setup(db_session, client)
    r = await client.patch(f"/employees/{employee_id}/hr-role", headers=admin, json={"hr_role": "HR", "payroll_access": True})
    assert r.status_code == 200 and r.json()["hr_payroll_access"] is True
    # Wechsel zu Teamleader nimmt die Berechtigung weg; nur Admins vergeben sie
    r = await client.patch(f"/employees/{employee_id}/hr-role", headers=admin, json={"hr_role": "SUPERVISOR", "payroll_access": True})
    assert r.json()["hr_payroll_access"] is False
    assert (await client.patch(f"/employees/{employee_id}/hr-role", headers=payroll, json={"hr_role": "HR", "payroll_access": True})).status_code == 403
    log = (await client.get("/audit-log", headers=admin)).json()
    assert any("Vergütung & Lohn-Export an" in (e["detail"] or "") for e in log)
