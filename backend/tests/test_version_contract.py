"""Arbeitszeitmodell und Schicht getrennt: die Fassung der Arbeitszeit trägt Soll, Pause und Kernzeit,
eine Schichtvorlage liefert nur die Uhrzeiten (und ihre Pause, solange die Fassung keine eigene hat).
Ältere Standard-Schichten (Soll aus der Vorlage) rechnen unverändert weiter."""
import uuid
from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    Employee,
    EmployeeDefaultShift,
    HrRole,
    Account,
    Location,
)
from app.services.auth_service import hash_password
from app.services.shift_planning_service import EffectiveDayPlan

MONDAY, TUESDAY, THURSDAY = "2026-10-05", "2026-10-06", "2026-10-08"
FULL_TIME = {"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"}


@pytest.fixture(autouse=True)
def _rules_changed_before_test_days(monkeypatch):
    """Pünktlichkeits-Hinweise gelten erst ab der letzten Regeländerung – hier ab 01.10.2026."""
    import app.api.settings as settings_api

    class _Date(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 1)

    monkeypatch.setattr(settings_api, "date", _Date)


async def _setup(db_session: AsyncSession, client: AsyncClient, number: str = "V1") -> tuple[Employee, dict]:
    location = Location(name=f"Standort {number}", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(location_id=location.id, first_name="Vera", last_name="Vertrag", employee_number=number, auto_break_enabled=False)
    db_session.add(employee)
    if number == "V1":
        db_session.add(Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    await db_session.refresh(employee)
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    return employee, {"Authorization": f"Bearer {token}"}


async def _work(client: AsyncClient, admin: dict, employee_id: int, day: str, come: str, go: str) -> None:
    for punch_type, clock in (("COME", come), ("GO", go)):
        r = await client.post(
            "/punches",
            headers=admin,
            json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": f"{day}T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text


async def _day(client: AsyncClient, admin: dict, employee_id: int, day: str) -> dict:
    r = await client.get(f"/employees/{employee_id}/timesheet", headers=admin, params={"from": day, "to": day})
    assert r.status_code == 200, r.text
    return r.json()[0]


async def _template(client: AsyncClient, admin: dict, **body) -> int:
    r = await client.post("/shift-templates", headers=admin, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_times_template_gives_times_not_target(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"
    r = await client.patch(
        "/settings", headers=admin, json={"core_time_start": "09:00", "core_time_end": "15:00", "disabled_day_flags": [], "late_tolerance_minutes": 0}
    )
    assert r.status_code == 200, r.text
    late = await _template(
        client, admin, name="Spät", start_time="13:00", end_time="21:30", target_minutes=300,
        break_mode="FIXED", fixed_break_start="17:00", fixed_break_end="17:30",
    )

    r = await client.put(url, headers=admin, json={**FULL_TIME, "shift_template_id": late})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["shift_template_name"], body["shift_start"], body["shift_end"]) == ("Spät", "13:00:00", "21:30:00")
    assert body["weekly_minutes"] == 2400 and body["daily_minutes"] == 480 and body["target_from_template"] is False
    assert body["break_from_template"] is True and body["break_start"] == "17:00:00"

    await _work(client, admin, employee.id, MONDAY, "13:00", "21:30")
    await _work(client, admin, employee.id, TUESDAY, "13:20", "21:30")
    monday = await _day(client, admin, employee.id, MONDAY)
    # Soll aus dem Modell (nicht die 5 Std. der Vorlage), Pause der Vorlage, Schichtzeit vor Kernzeit
    assert (monday["target_minutes"], monday["actual_minutes"], monday["flags"]) == (480, 480, [])
    assert (await _day(client, admin, employee.id, TUESDAY))["flags"] == ["LATE_ARRIVAL"]

    # eigene Pause der Fassung geht vor
    r = await client.put(url, headers=admin, json={**FULL_TIME, "shift_template_id": late, "break_minutes": 45, "valid_from": THURSDAY})
    assert r.json()["break_from_template"] is False and r.json()["break_minutes"] == 45
    await _work(client, admin, employee.id, THURSDAY, "13:00", "21:30")
    assert (await _day(client, admin, employee.id, THURSDAY))["actual_minutes"] == 465

    # Schichtvorlage eines anderen Mandanten bzw. unbekannt: abgelehnt
    r = await client.put(url, headers=admin, json={**FULL_TIME, "shift_template_id": 9999})
    assert r.status_code == 404 and r.json()["code"] == "SHIFT_TEMPLATE_NOT_FOUND"
    history = (await client.get(f"{url}/history", headers=admin)).json()
    assert [h["shift_template_name"] for h in history] == ["Spät", "Spät"]


async def test_times_template_checks_working_time_law(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    night = await _template(client, admin, name="Nacht", start_time="22:00", end_time="06:00", target_minutes=480)
    long_day = await _template(client, admin, name="Lang", start_time="06:00", end_time="17:00", target_minutes=480)
    url = f"/employees/{employee.id}/work-time-model"
    assert (await client.put(url, headers=admin, json={**FULL_TIME, "shift_template_id": night})).status_code == 200
    r = await client.put(url, headers=admin, json={**FULL_TIME, "shift_template_id": long_day, "valid_from": "2026-10-02"})
    assert r.status_code == 400 and r.json()["code"] == "MAX_DAILY_WORKING_TIME_EXCEEDED"


async def test_legacy_standard_shift_until_saved_in_model(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    early = await _template(client, admin, name="Früh", start_time="06:00", end_time="14:30", target_minutes=480)
    r = await client.post(
        f"/employees/{employee.id}/default-shifts",
        headers=admin,
        json={"shift_template_id": early, "valid_from": "2026-10-01", "weekdays_mask": 31},
    )
    assert r.status_code == 201, r.text
    url = f"/employees/{employee.id}/work-time-model"
    model = (await client.get(url, headers=admin)).json()
    assert model["target_from_template"] is True and model["weekly_minutes"] == 2400 and model["shift_template_name"] == "Früh"

    # Soll der Vorlage ab Stichtag geändert: die ältere Standard-Schicht folgt ab dann
    r = await client.patch(f"/shift-templates/{early}", headers=admin, json={"target_minutes": 450, "valid_from": "2026-10-12"})
    assert r.status_code == 200, r.text
    new_early = r.json()["id"]
    assert (await _day(client, admin, employee.id, "2026-10-05"))["target_minutes"] == 480
    assert (await _day(client, admin, employee.id, "2026-10-12"))["target_minutes"] == 450

    # im Arbeitszeitmodell gespeichert: Soll fest übernommen, Vorlage nur noch für die Uhrzeiten
    history = (await client.get(f"{url}/history", headers=admin)).json()
    assert len(history) == 2
    r = await client.put(
        f"{url}/versions/{history[0]['id']}", headers=admin, json={**FULL_TIME, "valid_from": "2026-10-12", "shift_template_id": new_early}
    )
    assert r.status_code == 200, r.text
    assert r.json()[0]["target_from_template"] is False and r.json()[0]["shift_template_id"] == new_early
    assert (await _day(client, admin, employee.id, "2026-10-12"))["target_minutes"] == 480

    # weitere Soll-Änderung der Vorlage: das Modell mit eigenem Soll wird nicht geteilt und rechnet weiter
    r = await client.patch(f"/shift-templates/{new_early}", headers=admin, json={"target_minutes": 420, "valid_from": "2026-10-19"})
    assert r.status_code == 200, r.text
    assert len((await client.get(f"{url}/history", headers=admin)).json()) == 2
    assert (await _day(client, admin, employee.id, "2026-10-19"))["target_minutes"] == 480


async def test_plan_entries_give_times_only_without_day_target(client: AsyncClient, db_session: AsyncSession) -> None:
    helper, admin = await _setup(db_session, client)
    flex, _ = await _setup(db_session, client, number="V2")
    evening = await _template(client, admin, name="Abend", start_time="17:00", end_time="22:00", target_minutes=300)
    assert (await client.put(f"/employees/{helper.id}/work-time-model", headers=admin, json={"on_demand": True, "valid_from": "2026-10-01"})).status_code == 200
    assert (
        await client.put(f"/employees/{flex.id}/work-time-model", headers=admin, json={"weekly_hours": 20, "flexible": True, "valid_from": "2026-10-01"})
    ).status_code == 200
    for employee in (helper, flex):
        r = await client.put(
            f"/employees/{employee.id}/shift-plan-entries/{TUESDAY}", headers=admin, json={"is_workday": True, "shift_template_id": evening}
        )
        assert r.status_code == 200, r.text
        r = await client.put(f"/employees/{employee.id}/shift-plan-entries/{THURSDAY}", headers=admin, json={"is_workday": False})
        assert r.status_code == 200, r.text

    # nach Aufwand: geplanter Einsatz bringt kein Soll (kein Minus, wenn er ausfällt)
    assert (await _day(client, admin, helper.id, TUESDAY))["target_minutes"] is None
    # flexibel: weiter je Woche abgerechnet, ein "Frei" macht keinen festen Tag daraus
    tuesday = await _day(client, admin, flex.id, TUESDAY)
    assert tuesday["target_minutes"] is None and tuesday["status"] != "PLANNED_OFF"

    for employee, kind in ((helper, "on_demand"), (flex, "flexible")):
        days = (
            await client.get(f"/employees/{employee.id}/effective-shifts", headers=admin, params={"from": TUESDAY, "to": THURSDAY})
        ).json()
        by_date = {d["date"]: d for d in days}
        assert by_date[TUESDAY]["shift_template_id"] == evening and by_date[TUESDAY]["from_entry"] and by_date[TUESDAY][kind]
        assert by_date[THURSDAY]["is_workday"] is False


async def test_core_time_follows_the_version(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin = await _setup(db_session, client)
    url = f"/employees/{employee.id}/work-time-model"
    await client.patch("/settings", headers=admin, json={"core_time_start": "09:00", "core_time_end": "15:00", "disabled_day_flags": []})
    r = await client.put(url, headers=admin, json={**FULL_TIME, "core_time_mode": "NONE"})
    assert r.json()["core_time_mode"] == "NONE"
    r = await client.put(url, headers=admin, json={**FULL_TIME, "weekly_hours": 30, "valid_from": TUESDAY})
    assert r.json()["core_time_mode"] == "NONE"  # ohne Angabe: wie bisher
    r = await client.put(url, headers=admin, json={**FULL_TIME, "core_time_mode": "TENANT", "valid_from": THURSDAY})
    assert r.status_code == 200
    for day in (MONDAY, THURSDAY):
        await _work(client, admin, employee.id, day, "11:00", "13:00")
    assert (await _day(client, admin, employee.id, MONDAY))["flags"] == []
    assert set((await _day(client, admin, employee.id, THURSDAY))["flags"]) == {"LATE_ARRIVAL", "EARLY_LEAVE"}

    # Anlegen mit Modell inkl. Kernzeit
    r = await client.post(
        "/employees",
        headers=admin,
        json={
            "location_id": employee.location_id, "first_name": "Neu", "last_name": "Person", "employee_number": "N1",
            "hire_date": "2026-10-01", "work_time_model": {"weekly_hours": 20, "weekdays": [0, 1], "core_time_mode": "NONE"},
        },
    )
    assert r.status_code == 201, r.text
    model = (await client.get(f"/employees/{r.json()['id']}/work-time-model", headers=admin)).json()
    assert model["core_time_mode"] == "NONE" and model["weekly_minutes"] == 1200


async def test_leave_days_without_fixed_days_count_monday_to_friday(client: AsyncClient, db_session: AsyncSession) -> None:
    from app.services.leave_service import vacation_days_between

    employee, admin = await _setup(db_session, client)
    db_session.add(
        Absence(
            employee_id=employee.id, type=AbsenceType.VACATION, date_from=date(2026, 10, 7), date_to=date(2026, 10, 13),
            approval_status=AbsenceApprovalStatus.APPROVED,
        )
    )
    await db_session.commit()
    # Mi–Di ohne Arbeitszeitmodell: 5 Tage (Mo–Fr), nicht 6 – wie der Urlaubsanspruch (5-Tage-Woche)
    assert await vacation_days_between(db_session, employee.id, date(2026, 10, 1), date(2026, 10, 31)) == 5
    r = await client.put(f"/employees/{employee.id}/work-time-model", headers=admin, json={"on_demand": True, "valid_from": "2026-10-01"})
    assert r.status_code == 200
    assert await vacation_days_between(db_session, employee.id, date(2026, 10, 1), date(2026, 10, 31)) == 5


async def test_sick_rate_without_fixed_days(db_session: AsyncSession) -> None:
    from app.api.reports import _planned_workdays

    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    helper = Employee(location_id=location.id, first_name="Ali", last_name="Aushilfe", employee_number="A1")
    other = Employee(location_id=location.id, first_name="Ohne", last_name="Modell", employee_number="A2")
    db_session.add_all([helper, other])
    await db_session.commit()
    db_session.add(
        EmployeeDefaultShift(employee_id=helper.id, valid_from=date(2026, 1, 1), weekdays_mask=127, on_demand=True, target_minutes=0)
    )
    await db_session.commit()
    first, last = date(2026, 10, 5), date(2026, 10, 11)
    assert await _planned_workdays(db_session, helper, first, last, {}) == 0
    assert await _planned_workdays(db_session, other, first, last, {}) == 5


def test_pdf_label_for_days_without_template() -> None:
    from app.services.shift_plan_pdf_service import _model_label

    assert _model_label(EffectiveDayPlan(True, True, 450, None, None, None, False)) == "7,5 h"
    assert _model_label(EffectiveDayPlan(True, True, None, None, None, None, False, flexible_weekly_minutes=1200)) == "flexibel"
    assert _model_label(EffectiveDayPlan(True, True, None, None, time(8), time(16), False)) is None
