"""Fehler aus der Gesamtprüfung vom 05.11.2026 (Aufräumen, Paket 1)."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HrRole, Account, Location
from app.services.auth_service import hash_password


async def _admin(db_session: AsyncSession, client: AsyncClient, role: HrRole = HrRole.ADMIN, email: str = "admin@example.com") -> dict:
    db_session.add(Account(email=email, password_hash=hash_password("pw"), role=role))
    await db_session.commit()
    login = await client.post("/auth/login", json={"email": email, "password": "pw"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _location(db_session: AsyncSession) -> Location:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    return location


# --- A1: Mitarbeiter mit vollständigem Arbeitszeitmodell anlegen ---------------------------------


async def test_create_employee_with_monthly_model_and_break(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _admin(db_session, client)
    location = await _location(db_session)
    r = await client.post(
        "/employees",
        headers=admin,
        json={
            "location_id": location.id,
            "first_name": "Mona",
            "last_name": "Monat",
            "employee_number": "M1",
            "hire_date": "2026-10-01",
            "work_time_model": {"monthly_hours": 108.5, "weekdays": [0, 1, 2, 3, 4], "break_minutes": 30},
        },
    )
    assert r.status_code == 201, r.text
    model = (await client.get(f"/employees/{r.json()['id']}/work-time-model/history", headers=admin)).json()[0]
    assert model["monthly_minutes"] == 6510 and model["break_minutes"] == 30 and model["valid_from"] == "2026-10-01"

    r = await client.post(
        "/employees",
        headers=admin,
        json={
            "location_id": location.id,
            "first_name": "Ali",
            "last_name": "Aufwand",
            "employee_number": "A1",
            "work_time_model": {"on_demand": True, "monthly_cap_hours": 43},
        },
    )
    assert r.status_code == 201, r.text
    model = (await client.get(f"/employees/{r.json()['id']}/work-time-model", headers=admin)).json()
    assert model["on_demand"] is True and model["monthly_cap_minutes"] == 2580


# --- A6: HR bearbeitet Mitarbeiter mit HR-Berechtigung -------------------------------------------


async def test_hr_can_edit_team_leader_without_touching_access(client: AsyncClient, db_session: AsyncSession) -> None:
    from app.models import Employee

    admin = await _admin(db_session, client)
    hr = await _admin(db_session, client, HrRole.HR, "hr@example.com")
    location = await _location(db_session)
    lead = Employee(
        location_id=location.id, first_name="Tara", last_name="Team", employee_number="T1",
        login_email="tara@example.com", hr_role=HrRole.SUPERVISOR,
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    # Dialog schickt die unveränderte Login-E-Mail mit
    r = await client.patch(f"/employees/{lead.id}", headers=hr, json={"last_name": "Teamleiterin", "login_email": "tara@example.com"})
    assert r.status_code == 200, r.text
    assert r.json()["last_name"] == "Teamleiterin"
    # Echte Änderung der Zugangsdaten bleibt Admins vorbehalten
    r = await client.patch(f"/employees/{lead.id}", headers=hr, json={"login_email": "andere@example.com"})
    assert r.status_code == 403
    r = await client.patch(f"/employees/{lead.id}", headers=admin, json={"login_email": "andere@example.com"})
    assert r.status_code == 200


# --- A7: Standortliste für Teamleader -----------------------------------------------------------


async def test_location_list_for_department_head_is_scoped_without_chip_ids(client: AsyncClient, db_session: AsyncSession) -> None:
    from app.models import Employee
    from org_helpers import department, supervisor_with_department

    location = await _location(db_session)
    mine = Employee(location_id=location.id, first_name="Mia", last_name="Mein", employee_number="1", nfc_uid="AAA")
    other = Employee(location_id=location.id, first_name="Olf", last_name="Other", employee_number="2", nfc_uid="BBB")
    db_session.add_all([mine, other])
    await db_session.commit()
    # Die Leitung (mit eigenem Chip) führt Abteilung A mit Mia; Olf arbeitet in B.
    _, lead, lead_account = await supervisor_with_department(
        db_session, location, department_name="A", members=(mine,), employee_number="9"
    )
    lead.nfc_uid = "LLL"
    await department(db_session, "B", other)
    login = await client.post("/auth/login", json={"email": "lead@example.com", "password": "pw"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    rows = (await client.get(f"/locations/{location.id}/employees", headers=headers)).json()
    assert sorted((r["employee_number"], r["nfc_uid"]) for r in rows) == [("1", None), ("9", None)]
    admin = await _admin(db_session, client)
    rows = (await client.get(f"/locations/{location.id}/employees", headers=admin)).json()
    assert {r["nfc_uid"] for r in rows} == {"AAA", "BBB", "LLL"}


# --- A8: Ganztägige Abwesenheiten überschneiden sich nicht; Krankheit im Urlaub ----------------------


async def test_full_day_absences_do_not_overlap_and_sickness_returns_vacation(client: AsyncClient, db_session: AsyncSession) -> None:
    from sqlalchemy import select

    from app.models import Absence, Employee
    from app.services.leave_service import used_vacation_days

    admin = await _admin(db_session, client)
    location = await _location(db_session)
    employee = Employee(location_id=location.id, first_name="Ute", last_name="Urlaub", employee_number="U1")
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)

    r = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin, json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-08-01"}
    )
    assert r.status_code == 200, r.text

    async def create(kind: str, start: str, end: str, **extra):
        return await client.post(
            "/absences", headers=admin, json={"employee_id": employee.id, "type": kind, "date_from": start, "date_to": end, **extra}
        )

    assert (await create("VACATION", "2026-08-10", "2026-08-21")).status_code == 201  # 10 Arbeitstage
    r = await create("SPECIAL_LEAVE", "2026-08-12", "2026-08-12")
    assert r.status_code == 409 and r.json()["code"] == "ABSENCE_OVERLAP"
    r = await create("SICK", "2026-08-12", "2026-08-13")
    assert r.status_code == 409 and r.json()["code"] == "ABSENCE_OVERLAP_VACATION"
    assert "10.08.2026–21.08.2026" in r.json()["detail"]

    r = await create("SICK", "2026-08-12", "2026-08-13", split_vacation=True)
    assert r.status_code == 201, r.text
    vacations = (
        await db_session.execute(select(Absence).where(Absence.type == "VACATION").order_by(Absence.date_from))
    ).scalars().all()
    assert [(v.date_from.isoformat(), v.date_to.isoformat()) for v in vacations] == [
        ("2026-08-10", "2026-08-11"),
        ("2026-08-14", "2026-08-21"),
    ]
    assert "wegen Krankheit" in vacations[0].note
    assert await used_vacation_days(db_session, employee.id, 2026) == 8.0

    # Krankheit deckt den Rest-Urlaub ganz ab -> Urlaub entfällt
    r = await create("SICK", "2026-08-10", "2026-08-11", split_vacation=True)
    assert r.status_code == 201
    assert await used_vacation_days(db_session, employee.id, 2026) == 6.0

    # Ändern: Urlaub in eine Krankheit hinein verlängern -> abgelehnt, nichts geändert
    second = vacations[1]
    r = await client.patch(f"/absences/{second.id}", headers=admin, json={"date_from": "2026-08-13"})
    assert r.status_code == 409
    await db_session.refresh(second)
    assert second.date_from.isoformat() == "2026-08-14"


# --- A9: Vier-Augen-Prinzip ----------------------------------------------------------------------


async def test_four_eyes_switch_prevents_self_approval(client: AsyncClient, db_session: AsyncSession) -> None:
    from app.models import Employee

    admin = await _admin(db_session, client)
    location = await _location(db_session)
    hr_employee = Employee(
        location_id=location.id, first_name="Hanne", last_name="Hr", employee_number="H1",
        login_email="hanne@example.com", hr_role=HrRole.HR, password_hash=hash_password("pw"),
    )
    db_session.add(hr_employee)
    await db_session.commit()
    await db_session.refresh(hr_employee)
    types = (await client.get("/absence-types", headers=admin)).json()
    vacation = next(t for t in types if t["category"] == "VACATION")
    assert (await client.patch(f"/absence-types/{vacation['id']}", headers=admin, json={"requires_approval": True})).status_code == 200
    login = await client.post("/auth/login", json={"email": "hanne@example.com", "password": "pw"})
    assert login.status_code == 200, login.text
    hanne = {"Authorization": f"Bearer {login.json()['access_token']}"}

    async def request(day: str):
        r = await client.post(
            "/absences", headers=hanne, json={"employee_id": hr_employee.id, "absence_type_id": vacation["id"], "date_from": day, "date_to": day}
        )
        assert r.status_code == 201, r.text
        return r.json()

    # Aus (Standard): wer genehmigen darf, bekommt den eigenen Urlaub direkt genehmigt
    assert (await request("2026-12-01"))["approval_status"] == "APPROVED"

    assert (await client.patch("/settings", headers=admin, json={"absence_four_eyes": True})).json()["absence_four_eyes"] is True
    pending = await request("2026-12-02")
    assert pending["approval_status"] == "PENDING"
    r = await client.patch(f"/absences/{pending['id']}/decide", headers=hanne, json={"approve": True})
    assert r.status_code == 403 and r.json()["code"] == "FOUR_EYES"
    r = await client.patch(f"/absences/{pending['id']}/decide", headers=admin, json={"approve": True})
    assert r.status_code == 200 and r.json()["approval_status"] == "APPROVED"


# --- A10: Lohn-Export-Soll beim flexiblen Modell --------------------------------------------------


async def test_payroll_target_for_flexible_model_matches_month_report(client: AsyncClient, db_session: AsyncSession) -> None:
    from app.models import Employee
    from app.services.payroll_export_service import summarize_payroll
    from app.services.period_service import build_month_report
    from datetime import date

    admin = await _admin(db_session, client)
    location = await _location(db_session)
    employee = Employee(location_id=location.id, first_name="Fee", last_name="Flex", employee_number="F1")
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    r = await client.put(
        f"/employees/{employee.id}/work-time-model", headers=admin, json={"weekly_hours": 14, "flexible": True, "valid_from": "2026-07-01"}
    )
    assert r.status_code == 200, r.text
    summary = await summarize_payroll(db_session, employee, date(2026, 8, 1), date(2026, 8, 31))
    report = await build_month_report(db_session, employee, 2026, 8)
    assert summary.target_minutes == report.target_minutes == round(14 * 60 / 7 * 31)


# --- A11: Automatische Pausen bei Korrekturen neu setzen ---------------------------------------------


async def test_auto_breaks_follow_corrections(client: AsyncClient, db_session: AsyncSession) -> None:
    import uuid

    from sqlalchemy import select

    from app.models import BreakRule, Employee, Punch, PunchSource

    admin = await _admin(db_session, client)
    location = await _location(db_session)
    employee = Employee(location_id=location.id, first_name="Paul", last_name="Pause", employee_number="P9", auto_break_enabled=True)
    db_session.add_all([employee, BreakRule(min_work_minutes=360, deduct_minutes=30), BreakRule(min_work_minutes=540, deduct_minutes=45)])
    await db_session.commit()
    await db_session.refresh(employee)

    async def punch(kind: str, clock: str) -> dict:
        r = await client.post(
            "/punches",
            headers=admin,
            json={"employee_id": employee.id, "punch_type": kind, "timestamp_utc": f"2026-08-10T{clock}:00Z", "idempotency_key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text
        return r.json()

    async def auto_breaks() -> list[str]:
        stamps = (
            await db_session.execute(
                select(Punch.timestamp_utc).where(Punch.source == PunchSource.AUTO_BREAK).order_by(Punch.timestamp_utc)
            )
        ).scalars().all()
        return [t.strftime("%H:%M") for t in stamps]

    async def day() -> dict:
        r = await client.get(f"/employees/{employee.id}/timesheet", headers=admin, params={"from": "2026-08-10", "to": "2026-08-10"})
        return r.json()[0]

    await punch("COME", "08:00")
    go = await punch("GO", "18:00")  # 10 Std. -> 45 Min. automatisch
    assert await auto_breaks() == ["17:14", "17:59"]

    # "Gehen" vorverlegt: Pause wandert mit, der Tag bleibt sauber
    r = await client.patch(f"/punches/{go['id']}", headers=admin, json={"timestamp_utc": "2026-08-10T15:00:00Z", "correction_reason": "früher gegangen"})
    assert r.status_code == 200, r.text
    assert await auto_breaks() == ["14:29", "14:59"]
    assert (await day())["status"] == "COMPLETE" and (await day())["actual_minutes"] == 390

    # Echte Pause nachgetragen: die automatische entfällt (kein doppelter Abzug)
    await punch("BREAK_START", "12:00")
    await punch("BREAK_END", "12:30")
    assert await auto_breaks() == []
    assert (await day())["actual_minutes"] == 390

    # "Gehen" gelöscht: keine verwaisten Pausen
    r = await client.delete(f"/punches/{go['id']}", headers=admin)
    assert r.status_code == 204
    assert await auto_breaks() == []


# --- A12: Pausenänderung einer nur im Kalender genutzten Schichtvorlage --------------------------------


async def test_template_break_change_keeps_past_calendar_days(client: AsyncClient, db_session: AsyncSession) -> None:
    import uuid
    from datetime import date

    from app.models import Employee, ShiftPlanEntry
    from app.services.timesheet_service import pair_punches_detail
    from zoneinfo import ZoneInfo

    admin = await _admin(db_session, client)
    location = await _location(db_session)
    employee = Employee(location_id=location.id, first_name="Kai", last_name="Kalender", employee_number="K7", auto_break_enabled=False)
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    r = await client.post(
        "/shift-templates", headers=admin,
        json={"name": "Früh", "start_time": "06:00", "end_time": "14:00", "break_mode": "FIXED", "fixed_break_start": "10:00", "fixed_break_end": "10:30", "target_minutes": 450},
    )
    template_id = r.json()["id"]
    for day in ("2026-10-05", "2026-10-12"):
        db_session.add(ShiftPlanEntry(employee_id=employee.id, date=date.fromisoformat(day), shift_template_id=template_id, is_workday=True, target_minutes=450))
        for kind, clock in (("COME", "06:00"), ("GO", "14:00")):
            await client.post("/punches", headers=admin, json={
                "employee_id": employee.id, "punch_type": kind, "timestamp_utc": f"{day}T{clock}:00Z", "idempotency_key": str(uuid.uuid4()),
            })
    await db_session.commit()
    r = await client.patch(
        f"/shift-templates/{template_id}", headers=admin,
        json={"break_mode": "FLEXIBLE", "min_break_minutes": 45, "valid_from": "2026-10-10"},
    )
    assert r.status_code == 200, r.text
    before, _, _ = await pair_punches_detail(db_session, employee, date(2026, 10, 5), ZoneInfo("UTC"))
    after, _, _ = await pair_punches_detail(db_session, employee, date(2026, 10, 12), ZoneInfo("UTC"))
    assert (before, after) == (450, 435)  # alte Pause (30 Min. fest) bleibt für den 05.10.


# --- A13: Gleitzeit-Rahmen gilt nicht an Schichttagen --------------------------------------------------


async def test_flex_frame_not_checked_on_shift_days(client: AsyncClient, db_session: AsyncSession) -> None:
    import uuid

    from app.models import Employee

    admin = await _admin(db_session, client)
    location = await _location(db_session)
    employee = Employee(location_id=location.id, first_name="Nils", last_name="Nacht", employee_number="N1", auto_break_enabled=False)
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    assert (await client.patch("/settings", headers=admin, json={"flex_frame_start": "06:00", "flex_frame_end": "20:00"})).status_code == 200
    late = (await client.post("/shift-templates", headers=admin, json={"name": "Spät", "start_time": "14:00", "end_time": "22:00", "target_minutes": 480})).json()
    r = await client.post(
        f"/employees/{employee.id}/default-shifts", headers=admin,
        json={"shift_template_id": late["id"], "valid_from": "2026-10-01", "weekdays_mask": 31},
    )
    assert r.status_code == 201, r.text
    for kind, clock in (("COME", "14:00"), ("GO", "22:00")):
        await client.post("/punches", headers=admin, json={
            "employee_id": employee.id, "punch_type": kind, "timestamp_utc": f"2026-10-06T{clock}:00Z", "idempotency_key": str(uuid.uuid4()),
        })
    from app.services.settings_service import get_or_create_settings

    settings_row = await get_or_create_settings(db_session, 1)
    settings_row.punctuality_from = None  # Hinweise auch für den (vergangenen) Testtag
    await db_session.commit()
    day = (await client.get(f"/employees/{employee.id}/timesheet", headers=admin, params={"from": "2026-10-06", "to": "2026-10-06"})).json()[0]
    assert "OUTSIDE_FLEX_FRAME" not in day["flags"]
    # Gegenprobe: dieselben Zeiten ohne Schicht liegen außerhalb des Rahmens
    other = Employee(location_id=location.id, first_name="Ohne", last_name="Schicht", employee_number="N2", auto_break_enabled=False)
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    r = await client.put(
        f"/employees/{other.id}/work-time-model", headers=admin, json={"weekly_hours": 40, "weekdays": [0, 1, 2, 3, 4], "valid_from": "2026-10-01"}
    )
    assert r.status_code == 200
    for kind, clock in (("COME", "14:00"), ("GO", "22:00")):
        await client.post("/punches", headers=admin, json={
            "employee_id": other.id, "punch_type": kind, "timestamp_utc": f"2026-10-06T{clock}:00Z", "idempotency_key": str(uuid.uuid4()),
        })
    day = (await client.get(f"/employees/{other.id}/timesheet", headers=admin, params={"from": "2026-10-06", "to": "2026-10-06"})).json()[0]
    assert "OUTSIDE_FLEX_FRAME" in day["flags"]


# --- A14: Feldprüfung im Backend -----------------------------------------------------------------


async def test_backend_field_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    from app.models import Employee

    admin = await _admin(db_session, client)
    location = await _location(db_session)
    employee = Employee(location_id=location.id, first_name="Val", last_name="Idierung", employee_number="V1")
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)

    assert (await client.patch(f"/employees/{employee.id}", headers=admin, json={"pin": "12ab"})).status_code == 422
    assert (await client.patch(f"/employees/{employee.id}", headers=admin, json={"pin": "123"})).status_code == 422
    assert (await client.patch(f"/employees/{employee.id}", headers=admin, json={"pin": "123456789"})).status_code == 422
    assert (await client.patch(f"/employees/{employee.id}", headers=admin, json={"pin": "4711"})).status_code == 200

    assert (await client.post("/locations", headers=admin, json={"name": "Lager", "timezone": "Europe/Berln"})).status_code == 422
    assert (await client.post("/locations", headers=admin, json={"name": "  ", "timezone": "Europe/Berlin"})).status_code == 422
    r = await client.post("/locations", headers=admin, json={"name": "Lager", "timezone": "Europe/Vienna"})
    assert r.status_code == 201, r.text
    assert (await client.patch(f"/locations/{r.json()['id']}", headers=admin, json={"timezone": "Mars/Olympus"})).status_code == 422

    assert (await client.patch("/settings", headers=admin, json={"default_annual_vacation_days": 400})).status_code == 422
    assert (await client.patch("/settings", headers=admin, json={"balance_start_date": "0002-01-01"})).status_code == 422

    r = await client.post(
        f"/employees/{employee.id}/balance-adjustments", headers=admin,
        json={"effective_date": "2026-10-01", "minutes": 600, "kind": "PAYOUT", "note": "Auszahlung Oktober"},
    )
    assert r.status_code == 422
    r = await client.post(
        "/absences", headers=admin, json={"employee_id": employee.id, "type": "VACATION", "date_from": "2026-12-01", "date_to": "2026-12-01"}
    )
    assert (await client.patch(f"/absences/{r.json()['id']}/decide", headers=admin, json={"approve": True, "note": "x" * 301})).status_code == 422


# --- A15: Feiertage bei Standorten in mehreren Bundesländern ---------------------------------------------


async def test_holidays_per_state_when_locations_differ(client: AsyncClient, db_session: AsyncSession) -> None:
    from datetime import date

    from app.models import Location
    from app.services.holiday_service import is_holiday_for_location

    admin = await _admin(db_session, client)
    assert (await client.patch("/settings", headers=admin, json={"default_bundesland": "BY"})).status_code == 200
    munich = (await client.post("/locations", headers=admin, json={"name": "München", "timezone": "Europe/Berlin"})).json()
    berlin = (await client.post("/locations", headers=admin, json={"name": "Berlin", "timezone": "Europe/Berlin", "bundesland": "BE"})).json()
    year = date.today().year + 1
    # Heilige Drei Könige (06.01.) gilt in Bayern, nicht in Berlin; Frauentag (08.03.) nur in Berlin.
    assert await is_holiday_for_location(db_session, 1, date(year, 1, 6), munich["id"]) is True
    assert await is_holiday_for_location(db_session, 1, date(year, 1, 6), berlin["id"]) is False
    assert await is_holiday_for_location(db_session, 1, date(year, 3, 8), berlin["id"]) is True
    assert await is_holiday_for_location(db_session, 1, date(year, 3, 8), munich["id"]) is False
    assert isinstance(await db_session.get(Location, munich["id"]), Location)


# --- Automatische Pause trägt die Firma (Prod-Datenbank verlangt tenant_id) ------------------------------


async def test_auto_break_punches_carry_the_tenant(db_session: AsyncSession) -> None:
    """In den Tests füllt ein Hook fehlende tenant_id mit 1 – ein Mitarbeiter der Firma 2 zeigt, ob
    der Code sie selbst setzt (MySQL lehnt Zeilen ohne tenant_id ab)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from sqlalchemy import select

    from app.models import BreakRule, Employee, Punch, PunchSource, PunchType, Tenant
    from app.services.timesheet_service import maybe_auto_insert_break

    db_session.add(Tenant(id=2, subdomain="zwei", name="Zwei"))
    await db_session.commit()
    location = Location(tenant_id=2, name="Z", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(tenant_id=2, location_id=location.id, first_name="Z", last_name="Wei", employee_number="Z1", auto_break_enabled=True)
    db_session.add_all([employee, BreakRule(tenant_id=2, min_work_minutes=360, deduct_minutes=30)])
    await db_session.commit()
    come = Punch(tenant_id=2, employee_id=employee.id, location_id=location.id, punch_type=PunchType.COME,
                 timestamp_utc=datetime(2026, 8, 10, 8), source=PunchSource.KIOSK, idempotency_key="z-come")
    go = Punch(tenant_id=2, employee_id=employee.id, location_id=location.id, punch_type=PunchType.GO,
               timestamp_utc=datetime(2026, 8, 10, 16), source=PunchSource.KIOSK, idempotency_key="z-go")
    db_session.add_all([come, go])
    await db_session.commit()
    await maybe_auto_insert_break(db_session, employee, go, ZoneInfo("UTC"))
    tenants = (await db_session.execute(select(Punch.tenant_id).where(Punch.source == PunchSource.AUTO_BREAK))).scalars().all()
    assert tenants == [2, 2]
