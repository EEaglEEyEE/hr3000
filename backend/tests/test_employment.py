from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, HrRole, Account, Location
from app.services.auth_service import hash_password


async def _setup(db_session: AsyncSession, client: AsyncClient, role: HrRole):
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    employee = Employee(location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1")
    db_session.add(employee)
    db_session.add(Account(email="user@example.com", password_hash=hash_password("pw"), role=role))
    await db_session.commit()
    await db_session.refresh(employee)
    login = await client.post("/auth/login", json={"email": "user@example.com", "password": "pw"})
    return employee, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_contracts_effective_dating_and_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client, HrRole.HR)
    url = f"/employees/{employee.id}/contracts"

    first = await client.post(
        url, headers=headers,
        json={"valid_from": "2025-01-01", "contract_type": "FIXED_TERM", "fixed_term_end": "2026-12-31",
              "job_title": "Monteur", "probation_end": "2025-06-30"},
    )
    assert first.status_code == 201

    # Befristet ohne Ende -> Validierungsfehler
    missing_end = await client.post(url, headers=headers, json={"valid_from": "2027-01-01", "contract_type": "FIXED_TERM"})
    assert missing_end.status_code == 422

    # Folgevertrag schließt den offenen automatisch zum Vortag ab
    second = await client.post(url, headers=headers, json={"valid_from": "2027-01-01", "contract_type": "PERMANENT"})
    assert second.status_code == 201
    contracts = (await client.get(url, headers=headers)).json()
    assert [c["contract_type"] for c in contracts] == ["PERMANENT", "FIXED_TERM"]
    assert contracts[1]["valid_to"] == "2026-12-31"

    # Rückdatierter Vertrag, der überlappt -> abgelehnt
    overlap = await client.post(url, headers=headers, json={"valid_from": "2025-06-01", "contract_type": "PERMANENT"})
    assert overlap.status_code == 400 and overlap.json()["code"] == "OVERLAPPING_PERIOD"


async def test_contract_patch_and_delete(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client, HrRole.ADMIN)
    url = f"/employees/{employee.id}/contracts"
    created = (await client.post(url, headers=headers, json={"valid_from": "2025-01-01", "contract_type": "PERMANENT"})).json()

    patched = await client.patch(f"{url}/{created['id']}", headers=headers, json={"job_title": "Bauleiter", "notes": "ok"})
    assert patched.json()["job_title"] == "Bauleiter"

    deleted = await client.delete(f"{url}/{created['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(url, headers=headers)).json() == []


async def test_supervisor_cannot_access_contracts_or_compensation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client, HrRole.SUPERVISOR)

    assert (await client.get(f"/employees/{employee.id}/contracts", headers=headers)).status_code == 403
    assert (await client.get(f"/employees/{employee.id}/compensation", headers=headers)).status_code == 403


async def test_hr_can_manage_contracts_but_not_compensation(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client, HrRole.HR)

    contracts = await client.get(f"/employees/{employee.id}/contracts", headers=headers)
    compensation = await client.get(f"/employees/{employee.id}/compensation", headers=headers)
    created = await client.post(
        f"/employees/{employee.id}/compensation", headers=headers,
        json={"valid_from": "2026-01-01", "pay_type": "HOURLY", "amount": 20},
    )

    assert contracts.status_code == 200
    assert compensation.status_code == 403
    assert created.status_code == 403


async def test_compensation_admin_only_validated_and_audited_without_amount(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee, headers = await _setup(db_session, client, HrRole.ADMIN)
    url = f"/employees/{employee.id}/compensation"

    for bad in (
        {"valid_from": "2026-01-01", "pay_type": "HOURLY", "amount": 0},
        {"valid_from": "2026-01-01", "pay_type": "HOURLY", "amount": -5},
        {"valid_from": "2026-01-01", "pay_type": "HOURLY", "amount": 2_000_000},
        {"valid_from": "2026-01-01", "pay_type": "HOURLY", "amount": 20, "currency": "eur"},
        {"valid_from": "2026-01-01", "pay_type": "WEEKLY", "amount": 20},
    ):
        assert (await client.post(url, headers=headers, json=bad)).status_code == 422, bad

    first = await client.post(url, headers=headers, json={"valid_from": "2026-01-01", "pay_type": "HOURLY", "amount": 21.5})
    second = await client.post(url, headers=headers, json={"valid_from": "2026-07-01", "pay_type": "HOURLY", "amount": 23})
    assert first.status_code == 201 and second.status_code == 201

    listing = (await client.get(url, headers=headers)).json()
    assert [row["amount"] for row in listing] == [23.0, 21.5]
    assert listing[1]["valid_to"] == "2026-06-30"

    entries = (await client.get("/audit-log", headers=headers)).json()
    actions = {e["action"] for e in entries}
    assert {"COMPENSATION_CHANGED", "COMPENSATION_VIEWED"} <= actions
    assert all("21.5" not in (e["detail"] or "") and "23" not in (e["detail"] or "").replace("2026", "") for e in entries)

    deleted = await client.delete(f"{url}/{first.json()['id']}", headers=headers)
    assert deleted.status_code == 204


async def test_other_tenant_employee_not_reachable(client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _setup(db_session, client, HrRole.ADMIN)

    for path in ("/employees/9999/contracts", "/employees/9999/compensation"):
        assert (await client.get(path, headers=headers)).status_code == 404
