import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    Compensation,
    ContractType,
    Employee,
    EmploymentContract,
    HrRole,
    HrUser,
    Location,
    PayType,
)
from app.services.auth_service import hash_password


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
        HrUser(email="sup@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR),
    ])
    await db_session.commit()
    await db_session.refresh(employee)
    headers = {}
    for name in ("hr", "admin", "sup"):
        headers[name] = {"Authorization": "Bearer " + (await client.post("/auth/hr/login", json={"email": f"{name}@example.com", "password": "pw"})).json()["access_token"]}
    return employee, headers


async def test_reports_require_full_hr_and_labor_costs_require_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _setup(db_session, client)
    for path in ("/reports/absence-stats?year=2025", "/reports/vacation?year=2025", "/reports/overtime", "/reports/attention"):
        assert (await client.get(path, headers=headers["sup"])).status_code == 403, path
        assert (await client.get(path, headers=headers["hr"])).status_code == 200, path
    cost = "/reports/labor-costs?from=2025-03-01&to=2025-03-31"
    assert (await client.get(cost, headers=headers["hr"])).status_code == 403
    assert (await client.get(cost, headers=headers["admin"])).status_code == 200


async def test_absence_stats_count_workdays_and_sick_rate(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    # Mo 3.3. - So 9.3.2025: 6 Arbeitstage (Mo-Sa), Sonntag zählt nicht.
    db_session.add(Absence(employee_id=employee.id, type=AbsenceType.SICK, date_from=date(2025, 3, 3), date_to=date(2025, 3, 9), approval_status=AbsenceApprovalStatus.APPROVED))
    db_session.add(Absence(employee_id=employee.id, type=AbsenceType.VACATION, date_from=date(2025, 4, 7), date_to=date(2025, 4, 8), approval_status=AbsenceApprovalStatus.APPROVED))
    db_session.add(Absence(employee_id=employee.id, type=AbsenceType.VACATION, date_from=date(2025, 4, 14), date_to=date(2025, 4, 14), approval_status=AbsenceApprovalStatus.PENDING))
    await db_session.commit()

    stats = (await client.get("/reports/absence-stats?year=2025", headers=headers["hr"])).json()
    months = {m["month"]: m for m in stats["months"]}
    assert months[3]["sick_days"] == 6 and months[4]["vacation_days"] == 2  # PENDING zählt nicht
    assert stats["employees"][0]["sick_days"] == 6 and stats["active_employee_count"] == 1
    assert 0 < stats["sick_rate_percent"] < 5


async def test_vacation_overtime_and_attention(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    today = date.today()
    db_session.add(Absence(employee_id=employee.id, type=AbsenceType.SICK, date_from=today - timedelta(days=60), date_to=today - timedelta(days=10), approval_status=AbsenceApprovalStatus.APPROVED))
    db_session.add(EmploymentContract(
        tenant_id=1, employee_id=employee.id, valid_from=today - timedelta(days=100), contract_type=ContractType.FIXED_TERM,
        probation_end=today + timedelta(days=10), fixed_term_end=today + timedelta(days=45),
    ))
    await db_session.commit()

    vacation = (await client.get(f"/reports/vacation?year={today.year}", headers=headers["hr"])).json()
    assert vacation[0]["remaining_days"] == vacation[0]["entitled_days"] and vacation[0]["used_days"] == 0

    assert (await client.get("/reports/overtime", headers=headers["hr"])).json()[0]["balance_minutes"] == 0

    attention = (await client.get("/reports/attention", headers=headers["hr"])).json()
    assert {i["kind"] for i in attention} == {"BEM", "PROBATION_ENDING", "FIXED_TERM_ENDING"}


async def test_labor_costs_hourly_with_surcharges_and_audit(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    db_session.add(Compensation(tenant_id=1, employee_id=employee.id, valid_from=date(2025, 1, 1), pay_type=PayType.HOURLY, amount=20, currency="EUR"))
    await db_session.commit()
    await client.post("/surcharge-rules/defaults", headers=headers["admin"])
    # Sonntag 6.4.2025, 8 bis 12 Uhr = 4 h.
    for punch_type, ts in (("COME", "2025-04-06T08:00:00Z"), ("GO", "2025-04-06T12:00:00Z")):
        r = await client.post("/punches", headers=headers["hr"], json={"employee_id": employee.id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())})
        assert r.status_code == 201

    report = (await client.get("/reports/labor-costs?from=2025-04-01&to=2025-04-30", headers=headers["admin"])).json()
    row = report["rows"][0]
    assert row["pay_type"] == "HOURLY" and row["actual_minutes"] == 240
    assert row["base_cost"] == 80.0 and row["surcharge_cost"] == 40.0 and report["total_cost"] == 120.0  # 4 h x 20 EUR + 4 h x 20 EUR x 50 %

    too_long = await client.get("/reports/labor-costs?from=2025-01-01&to=2025-12-31", headers=headers["admin"])
    assert too_long.status_code == 400 and too_long.json()["code"] == "RANGE_TOO_LARGE"
