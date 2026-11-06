"""Sonderfälle für Dienstgang, Stempeln über den Web-Login und den Schalter für Abwesenheitsanträge.

Ergänzt test_errand_and_portal.py: widersprüchliche Buchungsfolgen, Pausenregeln, abgeschaltete
Stempelarten, gesperrte Monate, falsche Logins, Eingabevalidierung und Mandantentrennung.
"""
import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BreakRule, Device, Employee, HrRole, HrUser, Location, Tenant
from absence_helpers import require_vacation_approval
from app.models.period_closure import PeriodClosure, PeriodStatus
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _setup(db_session: AsyncSession, client: AsyncClient, *, errands: bool = True, portal: bool = False):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(
        location_id=location.id,
        first_name="Dora",
        last_name="Dienst",
        employee_number="D1",
        login_email="dora@example.com",
        password_hash=hash_password("pw123456"),
    )
    device = Device(name="Tablet", location_id=location.id, device_token="tok-edge")
    db_session.add_all([employee, device, HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN)])
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    settings_row.kiosk_errand_buttons = errands
    settings_row.portal_punching_enabled = portal
    await db_session.commit()
    admin = _bearer((await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"])
    me = _bearer(
        (await client.post("/auth/employee/login", json={"email": "dora@example.com", "password": "pw123456"})).json()["access_token"]
    )
    device_headers = _bearer((await client.post("/auth/device/login", json={"device_token": "tok-edge"})).json()["access_token"])
    return employee, admin, me, device_headers


async def _punch(client: AsyncClient, headers, employee_id: int, punch_type: str, ts: str):
    return await client.post(
        "/punches",
        headers=headers,
        json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": str(uuid.uuid4())},
    )


async def _punch_day(client: AsyncClient, headers, employee_id: int, day: str, sequence: list[tuple[str, str]]) -> None:
    for punch_type, time in sequence:
        r = await _punch(client, headers, employee_id, punch_type, f"{day}T{time}:00Z")
        assert r.status_code == 201, (punch_type, time, r.text)


async def _day(client: AsyncClient, admin, employee_id: int, day: str) -> dict:
    r = await client.get(f"/employees/{employee_id}/timesheet", headers=admin, params={"from": day, "to": day})
    assert r.status_code == 200, r.text
    return r.json()[0]


# --- Dienstgang: Buchungsfolgen ------------------------------------------------------------


async def test_errand_without_start_or_outside_presence_is_an_error(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _, device = await _setup(db_session, client)
    # Ende ohne Start
    await _punch_day(client, device, employee.id, "2026-08-03", [("COME", "08:00"), ("ERRAND_END", "09:00"), ("GO", "16:00")])
    # Start ohne vorheriges Kommen
    await _punch_day(client, device, employee.id, "2026-08-04", [("ERRAND_START", "08:00"), ("ERRAND_END", "09:00")])
    # Gehen, während der Dienstgang noch läuft
    await _punch_day(client, device, employee.id, "2026-08-05", [("COME", "08:00"), ("ERRAND_START", "09:00"), ("GO", "16:00")])
    # Pause während des Dienstgangs
    await _punch_day(
        client, device, employee.id, "2026-08-06",
        [("COME", "08:00"), ("ERRAND_START", "09:00"), ("BREAK_START", "10:00"), ("BREAK_END", "10:30"), ("ERRAND_END", "11:00"), ("GO", "16:00")],
    )
    # Zwei Dienstgänge ineinander
    await _punch_day(
        client, device, employee.id, "2026-08-07",
        [("COME", "08:00"), ("ERRAND_START", "09:00"), ("ERRAND_START", "10:00"), ("ERRAND_END", "11:00"), ("GO", "16:00")],
    )
    for day in ("2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"):
        result = await _day(client, admin, employee.id, day)
        assert result["status"] == "ERROR", (day, result)
        assert result["actual_minutes"] is None


async def test_several_errands_and_a_break_in_one_day(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _, device = await _setup(db_session, client)
    await _punch_day(
        client, device, employee.id, "2026-08-10",
        [
            ("COME", "08:00"),
            ("ERRAND_START", "09:00"),
            ("ERRAND_END", "10:00"),
            ("BREAK_START", "12:00"),
            ("BREAK_END", "12:30"),
            ("ERRAND_START", "14:00"),
            ("ERRAND_END", "15:00"),
            ("GO", "17:00"),
        ],
    )
    result = await _day(client, admin, employee.id, "2026-08-10")
    # 9 Std. brutto – 30 Min. gestempelte Pause; Dienstgänge zählen voll.
    assert result["status"] == "COMPLETE" and result["actual_minutes"] == 9 * 60 - 30


async def test_errand_time_counts_towards_the_statutory_break(client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(BreakRule(tenant_id=1, min_work_minutes=360, deduct_minutes=30))
    employee, admin, _, device = await _setup(db_session, client)
    # 7 Std. anwesend, davon 5 Std. Dienstgang, keine Pause gestempelt -> 30 Min. Abzug wie ohne Dienstgang.
    await _punch_day(client, device, employee.id, "2026-08-11", [("COME", "08:00"), ("ERRAND_START", "09:00"), ("ERRAND_END", "14:00"), ("GO", "15:00")])
    result = await _day(client, admin, employee.id, "2026-08-11")
    assert result["status"] == "COMPLETE" and result["actual_minutes"] == 7 * 60 - 30


async def test_forgotten_errand_end_becomes_open_once_the_next_day_is_punched(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(datetime(2026, 8, 12, 15, 0))  # Schicht läuft noch (innerhalb der maximalen Schichtlänge)
    employee, admin, _, device = await _setup(db_session, client)
    await _punch_day(client, device, employee.id, "2026-08-12", [("COME", "08:00"), ("ERRAND_START", "13:00")])
    assert (await _day(client, admin, employee.id, "2026-08-12"))["status"] == "ON_ERRAND"
    await _punch_day(client, device, employee.id, "2026-08-13", [("COME", "08:00")])
    assert (await _day(client, admin, employee.id, "2026-08-12"))["status"] == "OPEN_MISSING_PUNCH"


async def test_hr_can_close_an_open_errand_even_when_errands_are_switched_off(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _, device = await _setup(db_session, client)
    await _punch_day(client, device, employee.id, "2026-08-14", [("COME", "08:00"), ("ERRAND_START", "10:00")])
    assert (await client.patch("/settings", headers=admin, json={"kiosk_errand_buttons": False})).status_code == 200

    blocked = await _punch(client, device, employee.id, "ERRAND_END", "2026-08-14T12:00:00Z")
    assert blocked.status_code == 400 and blocked.json()["code"] == "PUNCH_TYPE_DISABLED"
    # Korrektur durch HR bleibt möglich – sonst ließe sich der Tag nie abschließen.
    fixed = await _punch(client, admin, employee.id, "ERRAND_END", "2026-08-14T12:00:00Z")
    assert fixed.status_code == 201 and fixed.json()["source"] == "MANUAL_HR"
    assert (await _punch(client, device, employee.id, "GO", "2026-08-14T16:00:00Z")).status_code == 201
    result = await _day(client, admin, employee.id, "2026-08-14")
    assert result["status"] == "COMPLETE" and result["actual_minutes"] == 8 * 60


async def test_switched_off_break_buttons_only_block_break_punches(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, _, device = await _setup(db_session, client)
    assert (await client.patch("/settings", headers=admin, json={"kiosk_break_buttons": False})).status_code == 200
    config = (await client.get("/device/config", headers=device)).json()
    assert config["break_buttons"] is False and config["errand_buttons"] is True

    for punch_type in ("BREAK_START", "BREAK_END"):
        r = await _punch(client, device, employee.id, punch_type, "2026-08-17T10:00:00Z")
        assert r.status_code == 400 and r.json()["code"] == "PUNCH_TYPE_DISABLED"
    await _punch_day(client, device, employee.id, "2026-08-17", [("COME", "08:00"), ("ERRAND_START", "09:00"), ("ERRAND_END", "10:00"), ("GO", "12:00")])
    assert (await _day(client, admin, employee.id, "2026-08-17"))["status"] == "COMPLETE"


async def test_dashboard_lists_employee_on_errand_separately(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, me, _ = await _setup(db_session, client, portal=True)
    assert (await client.post("/me/punches", headers=me, json={"punch_type": "COME"})).status_code == 201
    assert (await client.post("/me/punches", headers=me, json={"punch_type": "ERRAND_START"})).status_code == 201

    team = (await client.get("/dashboard", headers=admin)).json()["team"]
    assert [p["employee_id"] for p in team["on_errand"]] == [employee.id]
    assert employee.id not in [p["employee_id"] for p in team["present"]]
    mine = (await client.get("/dashboard", headers=me)).json()["me"]
    assert mine["today_status"] == "ON_ERRAND"


# --- Stempeln über den Web-Login -----------------------------------------------------------


async def test_portal_punch_rejects_wrong_principals_and_bad_input(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, me, device = await _setup(db_session, client, portal=True)
    assert (await client.post("/me/punches", json={"punch_type": "COME"})).status_code == 401
    assert (await client.post("/me/punches", headers=device, json={"punch_type": "COME"})).status_code in (401, 403)
    assert (await client.post("/me/punches", headers=_bearer("kein-gueltiges-token"), json={"punch_type": "COME"})).status_code == 401

    # Pydantic-Validierung: unbekannte Art, fehlendes Feld, falscher Typ
    for body in ({"punch_type": "LUNCH"}, {}, {"punch_type": 1}, {"punch_type": None}):
        assert (await client.post("/me/punches", headers=me, json=body)).status_code == 422, body


async def test_portal_punch_respects_break_and_errand_switches(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin, me, _ = await _setup(db_session, client, errands=False, portal=True)
    assert (await client.post("/me/punches", headers=me, json={"punch_type": "COME"})).status_code == 201
    r = await client.post("/me/punches", headers=me, json={"punch_type": "ERRAND_START"})
    assert r.status_code == 400 and r.json()["code"] == "PUNCH_TYPE_DISABLED"
    flags = (await client.get("/dashboard", headers=me)).json()["me"]
    assert flags["errand_buttons"] is False and flags["break_buttons"] is True

    await client.patch("/settings", headers=admin, json={"kiosk_break_buttons": False})
    r = await client.post("/me/punches", headers=me, json={"punch_type": "BREAK_START"})
    assert r.status_code == 400 and r.json()["code"] == "PUNCH_TYPE_DISABLED"
    assert (await client.get("/dashboard", headers=me)).json()["me"]["break_buttons"] is False


async def test_portal_double_click_guard_is_per_punch_type(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, me, _ = await _setup(db_session, client, portal=True)
    assert (await client.post("/me/punches", headers=me, json={"punch_type": "COME"})).status_code == 201
    # Sofort danach Gehen ist erlaubt (andere Art) …
    assert (await client.post("/me/punches", headers=me, json={"punch_type": "GO"})).status_code == 201
    # … zweimal Gehen innerhalb einer Minute nicht.
    second = await client.post("/me/punches", headers=me, json={"punch_type": "GO"})
    assert second.status_code == 409 and second.json()["code"] == "PUNCH_DUPLICATE"

    today = datetime.now(UTC).date().isoformat()
    punches = (await client.get(f"/employees/{employee.id}/punches", headers=admin, params={"from": today, "to": today})).json()
    assert [(p["punch_type"], p["source"]) for p in punches] == [("COME", "PORTAL"), ("GO", "PORTAL")]


async def test_portal_punch_is_blocked_in_a_locked_month(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, _, me, _ = await _setup(db_session, client, portal=True)
    now = datetime.now(UTC)
    db_session.add(
        PeriodClosure(
            tenant_id=1,
            employee_id=employee.id,
            year=now.year,
            month=now.month,
            status=PeriodStatus.CLOSED,
            target_minutes=0,
            actual_minutes=0,
            delta_minutes=0,
            balance_end_minutes=0,
            submitted_at=now.replace(tzinfo=None),
            closed_at=now.replace(tzinfo=None),
        )
    )
    await db_session.commit()
    r = await client.post("/me/punches", headers=me, json={"punch_type": "COME"})
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_LOCKED"


async def test_portal_punch_switch_off_again_and_deactivated_employee(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, me, _ = await _setup(db_session, client, portal=True)
    assert (await client.post("/me/punches", headers=me, json={"punch_type": "COME"})).status_code == 201

    await client.patch("/settings", headers=admin, json={"portal_punching_enabled": False})
    r = await client.post("/me/punches", headers=me, json={"punch_type": "GO"})
    assert r.status_code == 403 and r.json()["code"] == "PORTAL_PUNCHING_DISABLED"
    dashboard = (await client.get("/dashboard", headers=me)).json()
    assert dashboard["me"]["portal_punching"] is False and dashboard["portal_punching_enabled"] is False

    # Ausgeschiedene Mitarbeiter verlieren den Zugang sofort, auch mit noch gültigem Token.
    await client.patch("/settings", headers=admin, json={"portal_punching_enabled": True})
    employee.active = False
    await db_session.commit()
    assert (await client.post("/me/punches", headers=me, json={"punch_type": "GO"})).status_code == 401


async def test_employee_with_admin_role_can_punch_for_themselves(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, _, me, _ = await _setup(db_session, client, portal=True)
    employee.hr_role = HrRole.ADMIN
    await db_session.commit()
    r = await client.post("/me/punches", headers=me, json={"punch_type": "COME"})
    assert r.status_code == 201 and r.json()["employee_id"] == employee.id
    dashboard = (await client.get("/dashboard", headers=me)).json()
    assert dashboard["me"]["today_status"] == "PRESENT" and dashboard["team"] is not None


async def test_admin_account_without_employee_gets_flag_but_no_punch_card(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin, _, _ = await _setup(db_session, client, portal=True)
    dashboard = (await client.get("/dashboard", headers=admin)).json()
    assert dashboard["me"] is None and dashboard["portal_punching_enabled"] is True
    r = await client.post("/me/punches", headers=admin, json={"punch_type": "COME"})
    assert r.status_code == 403


async def test_portal_switch_of_another_tenant_has_no_effect(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, _, me, _ = await _setup(db_session, client, portal=False)
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.commit()
    db_session.add(HrUser(tenant_id=2, email="admin@acme.example.com", password_hash=hash_password("pw2"), role=HrRole.ADMIN))
    await db_session.commit()
    login = await client.post(
        "/auth/hr/login", headers={"X-Tenant-Subdomain": "acme"}, json={"email": "admin@acme.example.com", "password": "pw2"}
    )
    other_admin = {**_bearer(login.json()["access_token"]), "X-Tenant-Subdomain": "acme"}
    r = await client.patch(
        "/settings", headers=other_admin, json={"portal_punching_enabled": True, "kiosk_errand_buttons": True, "absence_requests_enabled": False}
    )
    assert r.status_code == 200, r.text

    r = await client.post("/me/punches", headers=me, json={"punch_type": "COME"})
    assert r.status_code == 403 and r.json()["code"] == "PORTAL_PUNCHING_DISABLED"
    body = {"employee_id": employee.id, "type": "VACATION", "date_from": "2026-09-07", "date_to": "2026-09-08"}
    assert (await client.post("/absences", headers=me, json=body)).status_code == 201


# --- Einstellungen: Validierung und Berechtigung -------------------------------------------


async def test_new_switches_validate_input_and_are_admin_only(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, me, _ = await _setup(db_session, client)
    for field in ("portal_punching_enabled", "kiosk_errand_buttons", "kiosk_break_buttons", "absence_requests_enabled"):
        assert (await client.patch("/settings", headers=admin, json={field: "vielleicht"})).status_code == 422, field
        assert (await client.patch("/settings", headers=admin, json={field: [True]})).status_code == 422, field
        assert (await client.patch("/settings", headers=me, json={field: True})).status_code in (401, 403), field

    # Teamleader (Mitarbeiter mit Rolle) dürfen keine Mandanten-Einstellungen ändern.
    employee.hr_role = HrRole.SUPERVISOR
    await db_session.commit()
    assert (await client.patch("/settings", headers=me, json={"portal_punching_enabled": True})).status_code == 403
    settings = (await client.get("/settings", headers=admin)).json()
    assert settings["portal_punching_enabled"] is False and settings["absence_requests_enabled"] is True

    # Ein leerer PATCH ändert nichts.
    assert (await client.patch("/settings", headers=admin, json={})).status_code == 200
    assert (await client.get("/settings", headers=admin)).json() == settings


# --- Abwesenheitsanträge abschaltbar -------------------------------------------------------


async def test_switched_off_requests_block_every_type_for_plain_employees(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, me, _ = await _setup(db_session, client)
    await client.patch("/settings", headers=admin, json={"absence_requests_enabled": False})
    for absence_type in ("VACATION", "SICK", "SPECIAL_LEAVE"):
        body = {"employee_id": employee.id, "type": absence_type, "date_from": "2026-09-07", "date_to": "2026-09-08"}
        r = await client.post("/absences", headers=me, json=body)
        assert r.status_code == 403 and r.json()["code"] == "ABSENCE_REQUESTS_DISABLED", absence_type
    assert (await client.get(f"/employees/{employee.id}/absences", headers=admin)).json() == []

    # Wieder einschalten -> Antrag geht durch.
    await client.patch("/settings", headers=admin, json={"absence_requests_enabled": True})
    body = {"employee_id": employee.id, "type": "VACATION", "date_from": "2026-09-07", "date_to": "2026-09-08"}
    assert (await client.post("/absences", headers=me, json=body)).status_code == 201


async def test_open_requests_stay_decidable_after_switching_off(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, admin, me, _ = await _setup(db_session, client)
    settings_row = await get_or_create_settings(db_session, tenant_id=1)
    await require_vacation_approval(db_session)
    await db_session.commit()
    body = {"employee_id": employee.id, "type": "VACATION", "date_from": "2026-09-14", "date_to": "2026-09-15"}
    request = await client.post("/absences", headers=me, json=body)
    assert request.status_code == 201 and request.json()["approval_status"] == "PENDING"

    await client.patch("/settings", headers=admin, json={"absence_requests_enabled": False})
    pending = (await client.get("/absences/pending", headers=admin)).json()
    assert [a["id"] for a in pending] == [request.json()["id"]]
    decided = await client.patch(f"/absences/{request.json()['id']}/decide", headers=admin, json={"approve": True})
    assert decided.status_code == 200 and decided.json()["approval_status"] == "APPROVED"


async def test_employee_with_hr_role_still_enters_own_absence_when_requests_are_off(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    employee, admin, me, _ = await _setup(db_session, client)
    await client.patch("/settings", headers=admin, json={"absence_requests_enabled": False})
    employee.hr_role = HrRole.ADMIN
    await db_session.commit()
    body = {"employee_id": employee.id, "type": "VACATION", "date_from": "2026-09-21", "date_to": "2026-09-22"}
    r = await client.post("/absences", headers=me, json=body)
    assert r.status_code == 201 and r.json()["approval_status"] == "APPROVED"
