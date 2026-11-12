"""Abwesenheitsquote und Köpfe/FTE: Bausteine, Dienst (app/services/workforce_stats_service.py) und
Endpoints /reports/absence-rate und /reports/headcount."""
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    Account,
    AppSettings,
    Employee,
    EmployeeDefaultShift,
    Holiday,
    HrRole,
    Location,
    Tenant,
)
from app.models.shift_template import TargetPeriod
from app.services import workforce_stats_service as stats
from app.services.auth_service import hash_password
from tests.org_helpers import department

MON_TO_FRI = 0b0011111


def version(**kwargs) -> EmployeeDefaultShift:
    values = dict(employee_id=1, valid_from=date(2020, 1, 1), valid_to=None, weekdays_mask=MON_TO_FRI, day_minutes=None,
                  flexible=False, on_demand=False, target_minutes=None, target_period=None, shift_template_id=None)
    values.update(kwargs)
    return EmployeeDefaultShift(**values)


# --- Bausteine --------------------------------------------------------------------------------------


def test_month_helpers():
    assert stats.month_end(2024, 2) == date(2024, 2, 29)
    assert stats.month_end(2025, 2) == date(2025, 2, 28)
    assert stats.month_end(2025, 12) == date(2025, 12, 31)
    assert stats.months_between(date(2024, 11, 30), date(2025, 2, 1)) == [(2024, 11), (2024, 12), (2025, 1), (2025, 2)]
    assert stats.months_between(date(2025, 3, 5), date(2025, 3, 6)) == [(2025, 3)]
    assert stats.month_key(2025, 3) == "2025-03"


def test_full_time_week_minutes():
    assert stats.full_time_week_minutes(None) == (2400, False)
    assert stats.full_time_week_minutes(AppSettings(default_day_minutes=None)) == (2400, False)
    assert stats.full_time_week_minutes(AppSettings(default_day_minutes="0,0,0,0,0,0,0")) == (2400, False)
    assert stats.full_time_week_minutes(AppSettings(default_day_minutes="480,480,480,480,240,0,0")) == (2160, True)


@pytest.mark.parametrize(
    "kwargs,template,expected",
    [
        ({"on_demand": True}, None, None),
        ({"flexible": True, "target_minutes": 2400, "target_period": TargetPeriod.WEEKLY}, None, 2400),
        ({"day_minutes": "480,480,240,0,0,0,0"}, None, 1200),
        ({"target_minutes": 10400, "target_period": TargetPeriod.MONTHLY}, None, 2400),
        ({"target_minutes": 1200, "target_period": TargetPeriod.WEEKLY}, None, 1200),
        ({"target_minutes": 480, "target_period": TargetPeriod.DAILY, "weekdays_mask": 0b0000111}, None, 1440),
        ({}, SimpleNamespace(target_minutes=480, target_period=TargetPeriod.DAILY), 2400),
        ({}, None, 0),
    ],
)
def test_weekly_minutes(kwargs, template, expected):
    assert stats.weekly_minutes(version(**kwargs), template) == expected


def test_fte_of():
    assert stats.fte_of(None, None, 2400) == 1.0
    assert stats.fte_of(version(on_demand=True), None, 2400) == 0.0
    assert stats.fte_of(version(target_minutes=1200, target_period=TargetPeriod.WEEKLY), None, 2400) == 0.5
    assert stats.fte_of(version(target_minutes=2400, target_period=TargetPeriod.WEEKLY), None, 2160) == 1.1111


def test_version_on():
    old = version(valid_from=date(2024, 1, 1), valid_to=date(2024, 12, 31))
    new = version(valid_from=date(2025, 1, 1))
    assert stats.version_on([old, new], date(2024, 12, 31)) is old
    assert stats.version_on([old, new], date(2025, 1, 1)) is new
    assert stats.version_on([old, new], date(2023, 12, 31)) is None
    assert stats.version_on([], date(2025, 1, 1)) is None


def test_is_planned_workday():
    monday, saturday = date(2025, 3, 10), date(2025, 3, 15)
    assert stats.is_planned_workday([], {}, 1, monday) is True
    assert stats.is_planned_workday([], {}, 1, saturday) is False
    assert stats.is_planned_workday([], {monday: [None]}, 1, monday) is False  # Feiertag überall
    assert stats.is_planned_workday([], {monday: [{2}]}, 1, monday) is True  # nur anderer Standort
    assert stats.is_planned_workday([], {monday: [{1, 2}]}, 1, monday) is False
    assert stats.is_planned_workday([version(on_demand=True)], {}, 1, monday) is False
    assert stats.is_planned_workday([version(flexible=True)], {}, 1, monday) is True
    assert stats.is_planned_workday([version(flexible=True)], {}, 1, saturday) is False
    assert stats.is_planned_workday([version(day_minutes="0,480,0,0,0,0,0")], {}, 1, monday) is False
    assert stats.is_planned_workday([version(day_minutes="480,0,0,0,0,0,0")], {}, 1, monday) is True
    assert stats.is_planned_workday([version(weekdays_mask=0b0000010)], {}, 1, monday) is False
    assert stats.is_planned_workday([version(weekdays_mask=0b1000000)], {}, 1, date(2025, 3, 16)) is True


def test_employment_helpers():
    person = Employee(hire_date=date(2025, 2, 10), termination_date=date(2025, 5, 31), active=False)
    assert not stats.employed_on(person, date(2025, 2, 9))
    assert stats.employed_on(person, date(2025, 2, 10))
    assert stats.employed_on(person, date(2025, 5, 31))
    assert not stats.employed_on(person, date(2025, 6, 1))
    assert stats.employed_on(Employee(hire_date=None, termination_date=None), date(1990, 1, 1))
    assert stats.counts_in_history(person)  # deaktiviert, aber mit Austritt
    assert not stats.counts_in_history(Employee(active=False, termination_date=None))
    assert stats.counts_in_history(Employee(active=True, termination_date=None))


def test_absence_day_weight():
    assert stats.absence_day_weight(Absence(half_day=False, duration_minutes=None)) == 1.0
    assert stats.absence_day_weight(Absence(half_day=True, duration_minutes=None)) == 0.5
    assert stats.absence_day_weight(Absence(half_day=False, duration_minutes=120)) == 0.0


def test_rate_cell():
    assert stats.RateCell(0, 0).rate_percent is None
    assert stats.RateCell(6, 39).rate_percent == 15.38
    assert stats.RateCell(0, 10).rate_percent == 0.0


# --- Szenario ---------------------------------------------------------------------------------------


async def _company(db_session: AsyncSession) -> dict:
    location = Location(name="Ulm", timezone="UTC")
    db_session.add(location)
    await db_session.commit()

    def person(number: str, **kwargs) -> Employee:
        return Employee(location_id=location.id, first_name=number, last_name=f"Person {number}", employee_number=number, **kwargs)

    people = {
        "A": person("A", hire_date=date(2020, 1, 1)),
        "B": person("B", hire_date=date(2020, 1, 1)),
        "C": person("C", hire_date=date(2025, 3, 15)),
        "D": person("D", active=False),  # deaktiviert ohne Austritt: zählt nie
        "E": person("E", anonymized_at=datetime(2025, 1, 1)),  # anonymisiert: zählt nie
    }
    db_session.add_all(people.values())
    await db_session.commit()
    await department(db_session, "Vertrieb", people["A"])
    await department(db_session, "Lager", people["B"])
    # B arbeitet Mo und Mi
    db_session.add(version(employee_id=people["B"].id, weekdays_mask=0b0000101))
    db_session.add(Holiday(date=date(2025, 3, 3), name="Feiertag"))
    approved = AbsenceApprovalStatus.APPROVED
    db_session.add_all(
        [
            Absence(employee_id=people["A"].id, type=AbsenceType.SICK, date_from=date(2025, 3, 3), date_to=date(2025, 3, 9), approval_status=approved),
            Absence(employee_id=people["A"].id, type=AbsenceType.CHILD_SICK, date_from=date(2025, 4, 1), date_to=date(2025, 4, 1), half_day=True, approval_status=approved),
            Absence(employee_id=people["A"].id, type=AbsenceType.VACATION, date_from=date(2025, 4, 2), date_to=date(2025, 4, 2), approval_status=approved),
            Absence(employee_id=people["B"].id, type=AbsenceType.SICK, date_from=date(2025, 3, 10), date_to=date(2025, 3, 12), approval_status=approved),
            Absence(employee_id=people["B"].id, type=AbsenceType.SICK, date_from=date(2025, 4, 7), date_to=date(2025, 4, 7), approval_status=AbsenceApprovalStatus.PENDING),
            Absence(employee_id=people["B"].id, type=AbsenceType.SICK, date_from=date(2025, 4, 9), date_to=date(2025, 4, 9), duration_minutes=120, approval_status=approved),
            Absence(employee_id=people["D"].id, type=AbsenceType.SICK, date_from=date(2025, 3, 3), date_to=date(2025, 3, 31), approval_status=approved),
        ]
    )
    await db_session.commit()
    return people


async def test_absence_rate_counts_planned_workdays_and_departments(db_session: AsyncSession) -> None:
    await _company(db_session)
    result = await stats.absence_rate(db_session, 1, date(2025, 3, 1), date(2025, 4, 30), {AbsenceType.SICK, AbsenceType.CHILD_SICK}, today=date(2026, 1, 1))
    march, april = result.months["2025-03"], result.months["2025-04"]
    # März: A 20 (21 Mo–Fr minus Feiertag), B 8 (Mo/Mi minus Feiertag), C 11 (ab 15.3.)
    assert (march.workdays, march.absence_days) == (39, 6.0)  # A 4 (Feiertag zählt nicht), B 2 (Di ist kein Arbeitstag)
    assert march.rate_percent == 15.38
    # April: A 22, B 9, C 22; nur Kind krank (halber Tag) – offener Antrag und Stundenangabe zählen nicht
    assert (april.workdays, april.absence_days) == (53, 0.5)
    assert (result.total.workdays, result.total.absence_days) == (92, 6.5)
    names = {v: k for k, v in result.department_names.items()}
    sales = result.departments[names["Vertrieb"]]
    assert (sales["2025-03"].workdays, sales["2025-03"].absence_days, sales["2025-03"].rate_percent) == (20, 4.0, 20.0)
    assert result.departments[None]["2025-03"].workdays == 11
    assert result.through == date(2025, 4, 30)


async def test_absence_rate_with_vacation_category_and_today_cut(db_session: AsyncSession) -> None:
    await _company(db_session)
    result = await stats.absence_rate(db_session, 1, date(2025, 3, 1), date(2025, 4, 30), {AbsenceType.VACATION}, today=date(2025, 3, 31))
    assert result.through == date(2025, 3, 31)
    assert result.months["2025-04"].workdays == 0 and result.months["2025-04"].rate_percent is None
    assert result.total.absence_days == 0


async def test_absence_rate_in_the_future_and_empty_company(db_session: AsyncSession) -> None:
    result = await stats.absence_rate(db_session, 1, date(2025, 3, 1), date(2025, 3, 31), {AbsenceType.SICK}, today=date(2025, 1, 1))
    assert result.through is None and result.total.workdays == 0 and list(result.months) == ["2025-03"]
    result = await stats.absence_rate(db_session, 1, date(2025, 3, 1), date(2025, 3, 31), set(), today=date(2026, 1, 1))
    assert result.total.absence_days == 0


async def _headcount_company(db_session: AsyncSession) -> None:
    location = Location(name="Ulm", timezone="UTC")
    db_session.add(location)
    await db_session.commit()

    def person(number: str, **kwargs) -> Employee:
        return Employee(location_id=location.id, first_name=number, last_name=number, employee_number=number, **kwargs)

    a, b, c = person("A", hire_date=date(2020, 1, 1)), person("B"), person("C", hire_date=date(2024, 6, 1))
    d = person("D", hire_date=date(2025, 2, 10))
    e = person("E", hire_date=date(2020, 1, 1), termination_date=date(2025, 2, 28), active=False)
    f = person("F", active=False)
    g = person("G", hire_date=date(2020, 1, 1), termination_date=date(2025, 1, 15))
    db_session.add_all([a, b, c, d, e, f, g])
    await db_session.commit()
    await department(db_session, "Vertrieb", a, b)
    db_session.add_all(
        [
            version(employee_id=b.id, target_minutes=1200, target_period=TargetPeriod.WEEKLY),
            version(employee_id=c.id, on_demand=True),
        ]
    )
    await db_session.commit()


async def test_headcount_and_fte_per_month(db_session: AsyncSession) -> None:
    await _headcount_company(db_session)
    result = await stats.headcount(db_session, 1, None, date(2025, 1, 1), date(2025, 3, 31))
    rows = {m.month: m for m in result.months}
    assert (result.full_time_minutes, result.full_time_from_settings) == (2400, False)
    jan, feb, mar = rows["2025-01"], rows["2025-02"], rows["2025-03"]
    assert (jan.total.headcount, jan.total.fte, jan.joiners, jan.leavers) == (4, 2.5, 0, 1)
    assert (feb.total.headcount, feb.total.fte, feb.joiners, feb.leavers) == (5, 3.5, 1, 1)
    assert (mar.total.headcount, mar.total.fte, mar.joiners, mar.leavers) == (4, 2.5, 0, 0)
    assert mar.as_of == date(2025, 3, 31)
    sales = next(k for k, v in result.department_names.items() if v == "Vertrieb")
    assert (jan.departments[sales].headcount, jan.departments[sales].fte) == (2, 1.5)
    assert jan.departments[None].headcount == 2


async def test_headcount_uses_full_time_from_settings(db_session: AsyncSession) -> None:
    await _headcount_company(db_session)
    settings_row = AppSettings(tenant_id=1, default_day_minutes="480,480,480,480,480,0,0")
    result = await stats.headcount(db_session, 1, settings_row, date(2025, 3, 1), date(2025, 3, 1))
    assert result.full_time_from_settings and len(result.months) == 1


# --- Endpoints --------------------------------------------------------------------------------------


async def _headers(db_session: AsyncSession, client: AsyncClient) -> dict:
    location = (await db_session.execute(Location.__table__.select().limit(1))).first()
    if location is None:
        db_session.add(Location(name="Zentrale", timezone="UTC"))
        await db_session.commit()
        location = (await db_session.execute(Location.__table__.select().limit(1))).first()
    worker = Employee(location_id=location.id, first_name="Mia", last_name="Mitarbeit", employee_number="M1",
                      login_email="worker@example.com", password_hash=hash_password("pw"))
    db_session.add_all([
        worker,
        Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
        Account(email="sup@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR),
    ])
    await db_session.commit()
    headers = {}
    for name in ("hr", "admin", "sup", "worker"):
        token = (await client.post("/auth/login", json={"email": f"{name}@example.com", "password": "pw"})).json()["access_token"]
        headers[name] = {"Authorization": f"Bearer {token}"}
    return headers


async def test_absence_rate_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    await _company(db_session)
    headers = await _headers(db_session, client)
    url = "/reports/absence-rate?date_from=2025-03-01&date_to=2025-04-30"
    for role in ("sup", "worker"):
        assert (await client.get(url, headers=headers[role])).status_code == 403
    response = await client.get(url, headers=headers["hr"])
    assert response.status_code == 200
    body = response.json()
    assert body["categories"] == ["SICK", "CHILD_SICK"]
    assert [m["month"] for m in body["months"]] == ["2025-03", "2025-04"]
    assert body["months"][0]["absence_days"] == 6.0
    # Mitarbeiterin M1 (ohne Abteilung, ohne Eintritt) zählt mit
    assert body["months"][0]["workdays"] == 39 + 20
    assert [d["name"] for d in body["departments"]] == ["Lager", "Vertrieb", "Ohne Abteilung"]
    assert body["departments"][1]["total"]["rate_percent"] == round(4.5 / 42 * 100, 2)
    vacation = (await client.get(url + "&categories=VACATION", headers=headers["admin"])).json()
    assert vacation["total"]["absence_days"] == 1.0 and vacation["categories"] == ["VACATION"]


@pytest.mark.parametrize(
    "query",
    [
        "date_from=2025-03-01",
        "date_from=2025-03-01&date_to=2025-02-01",
        "date_from=2025-01-01&date_to=2027-01-01",
        "date_from=2025-01-01&date_to=2025-02-01&categories=WORK_TIME",
        "date_from=2025-01-01&date_to=2025-02-01&categories=KRANK",
        "date_from=2025-01-01&date_to=2025-02-01&foo=1",
    ],
)
async def test_absence_rate_endpoint_validation(client: AsyncClient, db_session: AsyncSession, query: str) -> None:
    headers = await _headers(db_session, client)
    assert (await client.get(f"/reports/absence-rate?{query}", headers=headers["hr"])).status_code == 422


async def test_headcount_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    await _headcount_company(db_session)
    headers = await _headers(db_session, client)
    url = "/reports/headcount?date_from=2025-01-01&date_to=2025-03-31"
    assert (await client.get(url, headers=headers["sup"])).status_code == 403
    assert (await client.get(url, headers=headers["worker"])).status_code == 403
    assert (await client.get("/reports/headcount?date_from=2024-01-01&date_to=2027-01-01", headers=headers["hr"])).status_code == 422
    body = (await client.get(url, headers=headers["hr"])).json()
    assert body["full_time_weekly_hours"] == 40 and body["full_time_from_settings"] is False
    jan = body["months"][0]
    # + Mitarbeiterin M1 ohne Eintrittsdatum (Vollzeit)
    assert (jan["headcount"], jan["fte"], jan["joiners"], jan["leavers"]) == (5, 3.5, 0, 1)
    assert [d["name"] for d in body["departments"]] == ["Vertrieb", "Ohne Abteilung"]
    assert jan["departments"][0]["headcount"] == 2


async def test_fixed_reports_ignore_other_tenants(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _headers(db_session, client)
    db_session.add(Tenant(id=2, subdomain="other", name="Other"))
    await db_session.flush()
    foreign_location = Location(tenant_id=2, name="Fremd", timezone="UTC")
    db_session.add(foreign_location)
    await db_session.flush()
    foreign = Employee(tenant_id=2, location_id=foreign_location.id, first_name="F", last_name="F", employee_number="F1")
    db_session.add(foreign)
    await db_session.flush()
    db_session.add(Absence(employee_id=foreign.id, type=AbsenceType.SICK, date_from=date(2025, 3, 3), date_to=date(2025, 3, 7),
                           approval_status=AbsenceApprovalStatus.APPROVED))
    await db_session.commit()
    count = (await client.get("/reports/headcount?date_from=2025-03-01&date_to=2025-03-31", headers=headers["hr"])).json()
    assert count["months"][0]["headcount"] == 1
    rate = (await client.get("/reports/absence-rate?date_from=2025-03-01&date_to=2025-03-31", headers=headers["hr"])).json()
    assert rate["total"]["absence_days"] == 0
