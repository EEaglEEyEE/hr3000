"""Gemeinsamer Rechenkern für Lohn-Export, DATEV und Lohnkosten: Gutschrift je Zeitart,
ausgezahlte Überstunden, Teilzeiträume aus denselben Tagen, Zulagen in den Lohnkosten."""
import csv
import io
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    AdjustmentKind,
    AllowanceUnit,
    BalanceAdjustment,
    Compensation,
    Employee,
    Holiday,
    HrRole,
    Account,
    Location,
    PayComponent,
    PayComponentKind,
    PayComponentType,
    PayType,
)
from app.services.auth_service import hash_password
from app.services.payroll_export_service import payroll_period, summarize_payroll


async def _setup(db_session: AsyncSession, client: AsyncClient) -> tuple[Employee, dict]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Lia", last_name="Lohn", employee_number="100", auto_break_enabled=False)
    db_session.add_all([employee, Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    await db_session.commit()
    await db_session.refresh(employee)
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    r = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin,
        json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-09-01"},
    )
    assert r.status_code == 200, r.text
    return employee, admin


def _absence(employee: Employee, category: AbsenceType, day: date, **extra) -> Absence:
    return Absence(
        employee_id=employee.id, type=category, date_from=day, date_to=day, approval_status=AbsenceApprovalStatus.APPROVED, **extra
    )


async def test_credits_per_time_type(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, _ = await _setup(db_session, client)
    db_session.add_all(
        [
            _absence(employee, AbsenceType.VACATION, date(2026, 10, 5)),  # Mo: ganzer Tag Urlaub
            _absence(employee, AbsenceType.VACATION, date(2026, 10, 6), half_day=True),  # Di: ½ Urlaub + ½ krank
            _absence(employee, AbsenceType.SICK, date(2026, 10, 6), half_day=True),
            Holiday(date=date(2026, 10, 7), name="Testfeiertag"),  # Mi: Feiertag
            _absence(employee, AbsenceType.WORK_TIME, date(2026, 10, 8), duration_minutes=180),  # Do: 3 Std. Homeoffice
        ]
    )
    await db_session.commit()
    period = await payroll_period(db_session, employee, date(2026, 10, 5), date(2026, 10, 9))
    by_day = {d.day: d.credits for d in period.days}
    assert by_day[date(2026, 10, 5)] == {AbsenceType.VACATION: 480}
    assert by_day[date(2026, 10, 6)] == {AbsenceType.VACATION: 240, AbsenceType.SICK: 240}
    assert by_day[date(2026, 10, 7)] == {AbsenceType.PUBLIC_HOLIDAY: 480}
    assert by_day[date(2026, 10, 8)] == {AbsenceType.WORK_TIME: 180}
    summary = period.summary()
    assert summary.credit_minutes == {
        AbsenceType.VACATION: 720, AbsenceType.SICK: 240, AbsenceType.PUBLIC_HOLIDAY: 480, AbsenceType.WORK_TIME: 180,
    }
    assert summary.vacation_days == 1.5 and summary.sick_days == 0.5 and summary.holiday_days == 1
    # Teilzeitraum aus denselben Tagen = eigene Rechnung über den Teilzeitraum
    part = await summarize_payroll(db_session, employee, date(2026, 10, 6), date(2026, 10, 7))
    assert period.summary(date(2026, 10, 6), date(2026, 10, 7)) == part


async def test_paid_out_overtime_in_csv(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    db_session.add_all(
        [
            BalanceAdjustment(tenant_id=1, employee_id=employee.id, effective_date=date(2026, 10, 31), minutes=-150, kind=AdjustmentKind.PAYOUT, note="Okt."),
            BalanceAdjustment(tenant_id=1, employee_id=employee.id, effective_date=date(2026, 11, 1), minutes=-60, kind=AdjustmentKind.PAYOUT, note="Nov."),
            BalanceAdjustment(tenant_id=1, employee_id=employee.id, effective_date=date(2026, 10, 2), minutes=90, kind=AdjustmentKind.CORRECTION, note="x"),
        ]
    )
    await db_session.commit()
    r = await client.get(
        "/payroll-export", headers=admin, params={"employee_ids": [employee.id], "from": "2026-10-01", "to": "2026-10-31"}
    )
    assert r.status_code == 200, r.text
    row = next(csv.DictReader(io.StringIO(r.text.lstrip("﻿")), delimiter=";"))
    assert row["Ausgezahlte Überstunden (Std.)"] == "2,50"


async def test_labor_costs_include_allowances(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    db_session.add_all(
        [
            Compensation(tenant_id=1, employee_id=employee.id, valid_from=date(2026, 1, 1), pay_type=PayType.MONTHLY, amount=Decimal("3100"), currency="EUR"),
            PayComponent(
                tenant_id=1, employee_id=employee.id, kind=PayComponentKind.ALLOWANCE, amount=Decimal("50"),
                unit=AllowanceUnit.PER_MONTH, valid_from=date(2026, 1, 1),
                type=PayComponentType(tenant_id=1, kind=PayComponentKind.ALLOWANCE, name="Fahrtkosten"),
            ),
            PayComponent(
                tenant_id=1, employee_id=employee.id, kind=PayComponentKind.ONE_TIME, amount=Decimal("200"), pay_date=date(2026, 10, 15),
                type=PayComponentType(tenant_id=1, kind=PayComponentKind.ONE_TIME, name="Prämie"),
            ),
        ]
    )
    await db_session.commit()
    r = await client.get("/reports/labor-costs", headers=admin, params={"from": "2026-10-01", "to": "2026-10-31"})
    assert r.status_code == 200, r.text
    row = r.json()["rows"][0]
    assert row["base_cost"] == 3100 and row["allowance_cost"] == 250 and row["total_cost"] == 3350
    assert r.json()["total_cost"] == 3350


async def test_month_status_and_export_log(client: AsyncClient, db_session: AsyncSession) -> None:
    from datetime import datetime

    from app.models import PeriodClosure, PeriodStatus

    employee, admin = await _setup(db_session, client)
    employee_id, location_id = employee.id, employee.location_id
    other = Employee(location_id=location_id, first_name="Otto", last_name="Offen", employee_number="101")
    third = Employee(location_id=location_id, first_name="Vera", last_name="Vorgelegt", employee_number="102")
    db_session.add_all([other, third, Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)])
    await db_session.commit()
    other_id, third_id = other.id, third.id

    def closure(emp_id: int, status: PeriodStatus) -> PeriodClosure:
        return PeriodClosure(
            tenant_id=1, employee_id=emp_id, year=2026, month=10, status=status, target_minutes=0, actual_minutes=0,
            delta_minutes=0, balance_end_minutes=0, submitted_at=datetime(2026, 11, 2, 9, 0),
        )

    db_session.add_all([closure(employee_id, PeriodStatus.CLOSED), closure(third_id, PeriodStatus.SUBMITTED)])
    await db_session.commit()
    ids = [employee_id, other_id, third_id]
    status = (await client.get("/payroll-export/status", headers=admin, params={"month": "2026-10", "employee_ids": ids})).json()
    assert (status["employee_count"], status["closed"], status["submitted"], status["open"]) == (3, 1, 1, 1)
    assert status["exports"] == []

    r = await client.get("/payroll-export", headers=admin, params={"employee_ids": ids, "from": "2026-10-01", "to": "2026-10-31"})
    assert r.status_code == 200
    await client.patch("/settings", headers=admin, json={"datev_consultant_number": "1234567", "datev_client_number": "10001"})
    assert (await client.get("/payroll-export/datev", headers=admin, params={"employee_ids": ids, "month": "2026-10"})).status_code == 200
    exports = (await client.get("/payroll-export/status", headers=admin, params={"month": "2026-10", "employee_ids": ids})).json()["exports"]
    assert [(e["kind"], e["employee_count"], e["created_by"]) for e in exports] == [("DATEV", 3, "admin@example.com"), ("CSV", 3, "admin@example.com")]
    # anderer Monat: nichts
    assert (await client.get("/payroll-export/status", headers=admin, params={"month": "2026-09"})).json()["exports"] == []

    token = (await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]
    hr = {"Authorization": f"Bearer {token}"}
    exports = (await client.get("/payroll-export/status", headers=hr, params={"month": "2026-10"})).json()["exports"]
    assert [e["kind"] for e in exports] == ["CSV"]  # DATEV nur für Admins
