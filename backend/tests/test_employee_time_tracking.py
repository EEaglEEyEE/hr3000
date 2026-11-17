"""„Zeiterfassung“ je Mitarbeiter abschaltbar (Employee.time_tracking, Migration 0166).

Ohne Zeiterfassung: kein Stempeln (TIME_TRACKING_DISABLED bzw. am Tablet „nicht gefunden“), kein Soll/Ist/
Gleitzeitkonto, nichts unter „Zu klären“; Abwesenheiten, Urlaubskonto, Monatsabschluss und Lohn-Export
bleiben. Gilt rückwirkend für alle nicht abgeschlossenen Monate (kein „gilt ab“)."""
import csv
import importlib.util
import io
import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.public_api import ApiEmployee
from app.config import settings
from app.errors import AppError
from app.models import (
    AbsenceType,
    Account,
    AppSettings,
    DailySummary,
    Device,
    Employee,
    HrRole,
    Location,
    OvertimeBalance,
    PeriodClosure,
    Punch,
    PunchCorrectionRequest,
    SummaryStatus,
    Tenant,
)
from app.schemas.employee import EmployeeCreateRequest, EmployeeResponse, EmployeeUpdateRequest
from app.services import report_catalog
from app.services.absence_type_service import format_days
from app.services.auth_service import hash_password
from app.services.employee_import_service import parse_bulk_import_csv
from app.services.leave_service import leave_balance
from app.services.pairing_service import token_hash
from app.services.payroll_accounting_service import build_month
from app.services.payroll_export_service import payroll_period
from app.services.period_service import _report_html, build_month_report
from app.services.surcharge_service import compute_surcharges
from app.services.timesheet_service import (
    balance_start,
    calculate_day,
    ensure_time_tracking,
    flexible_week,
    missing_punch_reported,
    rebuild_balance,
)

PW = "pw"
FIXED = {"daily_hours": [8, 8, 8, 8, 8, 0, 0], "valid_from": "2025-01-01"}
FLEX = {"weekly_hours": 20, "flexible": True, "valid_from": "2025-01-01"}
# „Jetzt“: Donnerstag, 20.03.2025, 12:00 UTC
NOW = datetime(2025, 3, 20, 12, 0)
UTC_TZ = ZoneInfo("UTC")


@pytest.fixture(autouse=True)
def _documents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "docs"))


# --- Hilfen ---------------------------------------------------------------------------------------


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": PW})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _setup(db: AsyncSession, client: AsyncClient, *, model: dict | None = FIXED) -> dict:
    location = Location(name="Zentrale", timezone="UTC")
    db.add(location)
    await db.commit()
    await db.refresh(location)
    tracker = Employee(
        location_id=location.id, first_name="Tom", last_name="Tracker", employee_number="T1", auto_break_enabled=False,
        login_email="tom@example.com", password_hash=hash_password(PW), pin_hash=hash_password("1234"),
    )
    nontracker = Employee(
        location_id=location.id, first_name="Nora", last_name="Ohnezeit", employee_number="N1", auto_break_enabled=False,
        login_email="nora@example.com", password_hash=hash_password(PW), pin_hash=hash_password("1234"),
    )
    device = Device(name="Tablet", location_id=location.id, token_hash=token_hash("tok-time-tracking"))
    db.add_all([
        tracker, nontracker, device,
        Account(email="admin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN),
    ])
    await db.commit()
    await db.refresh(tracker)
    await db.refresh(nontracker)
    admin = await _login(client, "admin@example.com")
    if model is not None:
        for employee in (tracker, nontracker):
            response = await client.put(f"/employees/{employee.id}/work-time-model", headers=admin, json=model)
            assert response.status_code == 200, response.text
    token = (await client.post("/auth/device/login", json={"device_token": "tok-time-tracking"})).json()["access_token"]
    return {
        "location": location,
        "tracker": tracker,
        "non": nontracker,
        "admin": admin,
        "device": {"Authorization": f"Bearer {token}"},
        "tom": await _login(client, "tom@example.com"),
        "nora": await _login(client, "nora@example.com"),
    }


async def _toggle(client: AsyncClient, headers: dict, employee_id: int, value: bool) -> dict:
    response = await client.patch(f"/employees/{employee_id}", headers=headers, json={"time_tracking": value})
    assert response.status_code == 200, response.text
    assert response.json()["time_tracking"] is value
    return response.json()


async def _punch(client: AsyncClient, headers: dict, employee_id: int, punch_type: str, ts: str, key: str | None = None):
    return await client.post(
        "/punches", headers=headers,
        json={"employee_id": employee_id, "punch_type": punch_type, "timestamp_utc": ts, "idempotency_key": key or str(uuid.uuid4())},
    )


async def _work(client: AsyncClient, headers: dict, employee_id: int, day: str, hours: int = 8) -> None:
    assert (await _punch(client, headers, employee_id, "COME", f"{day}T08:00:00Z")).status_code == 201
    assert (await _punch(client, headers, employee_id, "GO", f"{day}T{8 + hours:02d}:00:00Z")).status_code == 201


async def _settings(client: AsyncClient, headers: dict, **values) -> None:
    response = await client.patch("/settings", headers=headers, json=values)
    assert response.status_code == 200, response.text


async def _vacation(client: AsyncClient, headers: dict, employee_id: int, date_from: str, date_to: str) -> None:
    response = await client.post(
        "/absences", headers=headers,
        json={"employee_id": employee_id, "type": "VACATION", "date_from": date_from, "date_to": date_to},
    )
    assert response.status_code == 201, response.text


def _assert_disabled(response) -> None:
    assert response.status_code == 403, response.text
    body = response.json()
    assert body["code"] == "TIME_TRACKING_DISABLED"
    assert body["detail"] == "Für diesen Mitarbeiter ist die Zeiterfassung ausgeschaltet."


async def _count(db: AsyncSession, model, employee_id: int) -> int:
    return (await db.execute(select(func.count()).select_from(model).where(model.employee_id == employee_id))).scalar_one()


# --- Modell, Schemas, Import ------------------------------------------------------------------------


def test_new_employee_object_tracks_time_before_flush() -> None:
    assert Employee(first_name="A", last_name="B", employee_number="1").time_tracking is True
    assert Employee(first_name="A", last_name="B", employee_number="1", time_tracking=False).time_tracking is False


def test_ensure_time_tracking_raises_only_without_time_tracking() -> None:
    ensure_time_tracking(Employee(first_name="A", last_name="B", employee_number="1"))
    with pytest.raises(AppError) as error:
        ensure_time_tracking(Employee(first_name="A", last_name="B", employee_number="1", time_tracking=False))
    assert (error.value.status_code, error.value.code) == (403, "TIME_TRACKING_DISABLED")


def test_schemas_default_and_validation() -> None:
    base = {"location_id": 1, "first_name": "A", "last_name": "B", "employee_number": "1"}
    assert EmployeeCreateRequest(**base).time_tracking is True
    assert EmployeeCreateRequest(**base, time_tracking=False).time_tracking is False
    assert EmployeeUpdateRequest().time_tracking is None
    assert EmployeeUpdateRequest(time_tracking=False).time_tracking is False
    for bad in ("vielleicht", [True], {"x": 1}, 2):
        with pytest.raises(ValidationError):
            EmployeeCreateRequest(**base, time_tracking=bad)
        with pytest.raises(ValidationError):
            EmployeeUpdateRequest(time_tracking=bad)
    assert "time_tracking" in EmployeeResponse.model_fields
    assert ApiEmployee.model_fields["time_tracking"].default is True


@pytest.mark.parametrize(
    "value, expected", [("ja", True), ("Nein", False), ("0", False), ("1", True), ("falsch", False), ("", True)]
)
def test_import_column_zeiterfassung(value: str, expected: bool) -> None:
    location = Location(id=1, name="Zentrale", timezone="UTC")
    content = f"vorname;nachname;personalnummer;standort;zeiterfassung\nA;B;1;Zentrale;{value}\n"
    rows, errors = parse_bulk_import_csv(content, [location], [], set(), set())
    assert errors == [] and rows[0].time_tracking is expected


def test_import_without_column_tracks_time_and_rejects_invalid_value() -> None:
    location = Location(id=1, name="Zentrale", timezone="UTC")
    rows, errors = parse_bulk_import_csv("vorname;nachname;personalnummer;standort\nA;B;1;Zentrale\n", [location], [], set(), set())
    assert errors == [] and rows[0].time_tracking is True
    rows, errors = parse_bulk_import_csv(
        "vorname;nachname;personalnummer;standort;zeiterfassung\nA;B;1;Zentrale;manchmal\n", [location], [], set(), set()
    )
    assert rows == [] and errors[0].row == 2 and "Zeiterfassung" in errors[0].message
    # Die bisherige Meldung für „aktiv“ bleibt unverändert.
    rows, errors = parse_bulk_import_csv(
        "vorname;nachname;personalnummer;standort;aktiv\nA;B;1;Zentrale;manchmal\n", [location], [], set(), set()
    )
    assert "für Aktiv" in errors[0].message


def test_report_catalog_has_time_tracking_column() -> None:
    column = report_catalog.STATIC_COLUMNS[report_catalog.SOURCE_EMPLOYEES]["time_tracking"]
    assert column.label == "Zeiterfassung" and column.type == report_catalog.BOOL


# --- Migration 0166 ----------------------------------------------------------------------------------

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _migration():
    spec = importlib.util.spec_from_file_location("m0166", _VERSIONS / "0166_employee_time_tracking.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migration_conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE employees (id INTEGER PRIMARY KEY, first_name VARCHAR(100))"))
        connection.execute(sa.text("INSERT INTO employees (id, first_name) VALUES (1, 'Alt'), (2, 'Auch alt')"))
        yield connection
    engine.dispose()


def _run(conn, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_migration_chain() -> None:
    module = _migration()
    assert (module.revision, module.down_revision) == ("0166_employee_time_tracking", "0165_company_enrollment_key")


def test_migration_keeps_time_tracking_for_existing_employees(migration_conn) -> None:
    module = _migration()
    _run(migration_conn, module.upgrade)
    column = {c["name"]: c for c in sa.inspect(migration_conn).get_columns("employees")}["time_tracking"]
    assert column["nullable"] is False
    assert migration_conn.execute(sa.text("SELECT time_tracking FROM employees ORDER BY id")).scalars().all() == [1, 1]
    migration_conn.execute(sa.text("INSERT INTO employees (id, first_name) VALUES (3, 'Neu')"))
    assert migration_conn.execute(sa.text("SELECT time_tracking FROM employees WHERE id = 3")).scalar_one() == 1
    _run(migration_conn, module.downgrade)
    assert {c["name"] for c in sa.inspect(migration_conn).get_columns("employees")} == {"id", "first_name"}


# --- Anlegen und Ändern über die API -----------------------------------------------------------------


async def test_create_defaults_to_time_tracking_and_accepts_off(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client, model=None)
    base = {"location_id": ctx["location"].id, "first_name": "Neu", "last_name": "Person", "no_work_time_model": True}
    default = await client.post("/employees", headers=ctx["admin"], json={**base, "employee_number": "X1"})
    assert default.status_code == 201, default.text
    assert default.json()["time_tracking"] is True
    off = await client.post("/employees", headers=ctx["admin"], json={**base, "employee_number": "X2", "time_tracking": False})
    assert off.status_code == 201 and off.json()["time_tracking"] is False
    stored = await db_session.get(Employee, off.json()["id"])
    assert stored.time_tracking is False
    bad = await client.post("/employees", headers=ctx["admin"], json={**base, "employee_number": "X3", "time_tracking": "vielleicht"})
    assert bad.status_code == 422
    listed = {e["employee_number"]: e["time_tracking"] for e in (await client.get("/employees", headers=ctx["admin"])).json()}
    assert listed["X1"] is True and listed["X2"] is False


async def test_bulk_import_sets_time_tracking(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client, model=None)
    content = "vorname;nachname;personalnummer;standort;zeiterfassung\nAna;Eins;I1;Zentrale;nein\nBen;Zwei;I2;Zentrale;\n"
    response = await client.post(
        "/employees/bulk-import", headers=ctx["admin"], files={"file": ("import.csv", content.encode(), "text/csv")}
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 2
    rows = dict((await db_session.execute(select(Employee.employee_number, Employee.time_tracking).where(Employee.employee_number.in_(["I1", "I2"])))).all())
    assert rows == {"I1": False, "I2": True}


async def test_update_toggles_and_validates(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client)
    employee = ctx["tracker"]
    await _toggle(client, ctx["admin"], employee.id, False)
    # Andere Änderungen lassen den Schalter unverändert.
    other = await client.patch(f"/employees/{employee.id}", headers=ctx["admin"], json={"first_name": "Thomas"})
    assert other.status_code == 200 and other.json()["time_tracking"] is False
    bad = await client.patch(f"/employees/{employee.id}", headers=ctx["admin"], json={"time_tracking": "ja bitte"})
    assert bad.status_code == 422
    await _toggle(client, ctx["admin"], employee.id, True)
    # Mitarbeiter selbst darf den Schalter nicht ändern.
    own = await client.patch(f"/employees/{employee.id}", headers=ctx["tom"], json={"time_tracking": False})
    assert own.status_code in (401, 403)
    await db_session.refresh(employee)
    assert employee.time_tracking is True


async def test_tenant_isolation_of_the_switch(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client, model=None)
    db_session.add(Tenant(id=2, subdomain="anderefirma", name="Andere Firma"))
    await db_session.flush()
    foreign_location = Location(tenant_id=2, name="Fremd", timezone="UTC")
    db_session.add(foreign_location)
    await db_session.flush()
    foreign = Employee(tenant_id=2, location_id=foreign_location.id, first_name="F", last_name="Remd", employee_number="F1")
    db_session.add(foreign)
    await db_session.commit()
    response = await client.patch(f"/employees/{foreign.id}", headers=ctx["admin"], json={"time_tracking": False})
    assert response.status_code == 404
    await db_session.refresh(foreign)
    assert foreign.time_tracking is True
    assert foreign.id not in {e["id"] for e in (await client.get("/employees", headers=ctx["admin"])).json()}


# --- Tablet ---------------------------------------------------------------------------------------------


async def test_tablet_list_excludes_employees_without_time_tracking(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client, model=None)
    url = f"/locations/{ctx['location'].id}/employees"
    assert {e["id"] for e in (await client.get(url, headers=ctx["device"])).json()} == {ctx["tracker"].id, ctx["non"].id}
    await _toggle(client, ctx["admin"], ctx["non"].id, False)
    for headers in (ctx["device"], ctx["admin"]):
        response = await client.get(url, headers=headers)
        assert response.status_code == 200
        assert [e["id"] for e in response.json()] == [ctx["tracker"].id]


async def test_device_punch_is_rejected_and_duplicate_key_still_counts_as_duplicate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ctx = await _setup(db_session, client, model=None)
    non = ctx["non"]
    key = str(uuid.uuid4())
    assert (await _punch(client, ctx["device"], non.id, "COME", "2025-03-10T08:00:00Z", key)).status_code == 201
    await _toggle(client, ctx["admin"], non.id, False)
    # Offline-Warteschlange: dieselbe Stempelung erneut gesendet -> weiterhin PUNCH_DUPLICATE (gilt als Erfolg).
    again = await _punch(client, ctx["device"], non.id, "COME", "2025-03-10T08:00:00Z", key)
    assert again.status_code == 409 and again.json()["code"] == "PUNCH_DUPLICATE"
    # Neue Stempelung -> abgelehnt (ohne PIN-Prüfung, also ohne PIN-Sperre).
    await _settings(client, ctx["admin"], require_pin_for_punch=True)
    for _ in range(6):
        _assert_disabled(await _punch(client, ctx["device"], non.id, "GO", "2025-03-10T16:00:00Z"))
    assert await _count(db_session, Punch, non.id) == 1
    # Kollege mit Zeiterfassung stempelt normal.
    ok = await client.post(
        "/punches", headers=ctx["device"],
        json={"employee_id": ctx["tracker"].id, "punch_type": "COME", "timestamp_utc": "2025-03-10T08:00:00Z",
              "idempotency_key": str(uuid.uuid4()), "pin": "1234"},
    )
    assert ok.status_code == 201, ok.text


async def test_hr_manual_punch_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client, model=None)
    await _toggle(client, ctx["admin"], ctx["non"].id, False)
    _assert_disabled(await _punch(client, ctx["admin"], ctx["non"].id, "COME", "2025-03-10T08:00:00Z"))
    assert (await _punch(client, ctx["admin"], ctx["tracker"].id, "COME", "2025-03-10T08:00:00Z")).status_code == 201


async def test_hr_can_still_correct_and_delete_existing_punches(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client, model=None)
    non = ctx["non"]
    come = (await _punch(client, ctx["admin"], non.id, "COME", "2025-03-10T08:00:00Z")).json()
    go = (await _punch(client, ctx["admin"], non.id, "GO", "2025-03-10T16:00:00Z")).json()
    await _toggle(client, ctx["admin"], non.id, False)
    corrected = await client.patch(
        f"/punches/{come['id']}", headers=ctx["admin"],
        json={"timestamp_utc": "2025-03-10T07:30:00Z", "correction_reason": "Korrektur alter Buchung"},
    )
    assert corrected.status_code == 200, corrected.text
    deleted = await client.delete(f"/punches/{go['id']}", headers=ctx["admin"], params={"reason": "Alte Buchung entfernen"})
    assert deleted.status_code == 204, deleted.text
    assert await _count(db_session, Punch, non.id) == 1
    listed = await client.get(f"/employees/{non.id}/punches", headers=ctx["admin"])
    assert [p["id"] for p in listed.json()] == [come["id"]]


async def test_portal_punching_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client, model=None)
    await _settings(client, ctx["admin"], portal_punching_enabled=True)
    await _toggle(client, ctx["admin"], ctx["non"].id, False)
    _assert_disabled(await client.post("/me/punches", headers=ctx["nora"], json={"punch_type": "COME"}))
    assert await _count(db_session, Punch, ctx["non"].id) == 0
    assert (await client.post("/me/punches", headers=ctx["tom"], json={"punch_type": "COME"})).status_code == 201
    # Ohne Freischaltung des Mandanten bleibt die bisherige Meldung.
    await _settings(client, ctx["admin"], portal_punching_enabled=False)
    closed = await client.post("/me/punches", headers=ctx["nora"], json={"punch_type": "COME"})
    assert closed.status_code == 403 and closed.json()["code"] == "PORTAL_PUNCHING_DISABLED"


async def test_register_card_and_setup_pin_treat_employee_as_not_found(client: AsyncClient, db_session: AsyncSession) -> None:
    ctx = await _setup(db_session, client, model=None)
    non = ctx["non"]
    await _settings(client, ctx["admin"], kiosk_rfid_enabled=True, kiosk_card_self_registration=True, kiosk_pin_self_setup=True)
    await _toggle(client, ctx["admin"], non.id, False)
    card = await client.post("/device/register-card", headers=ctx["device"], json={"employee_id": non.id, "pin": "1234", "nfc_uid": "04a1b2c3"})
    assert card.status_code == 404 and card.json()["code"] == "EMPLOYEE_NOT_FOUND"
    non.pin_hash = None
    await db_session.commit()
    pin = await client.post("/device/setup-pin", headers=ctx["device"], json={"employee_id": non.id, "pin": "4711"})
    assert pin.status_code == 404 and pin.json()["code"] == "EMPLOYEE_NOT_FOUND"
    await db_session.refresh(non)
    assert non.nfc_uid is None and non.pin_hash is None
    # Mit Zeiterfassung funktioniert beides.
    await _toggle(client, ctx["admin"], non.id, True)
    assert (await client.post("/device/setup-pin", headers=ctx["device"], json={"employee_id": non.id, "pin": "4711"})).status_code == 204
    assert (
        await client.post("/device/register-card", headers=ctx["device"], json={"employee_id": non.id, "pin": "4711", "nfc_uid": "04a1b2c3"})
    ).status_code == 204


async def test_overtime_balance_endpoint(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    non = ctx["non"]
    await _settings(client, ctx["admin"], kiosk_show_balance=True)
    await _work(client, ctx["admin"], non.id, "2025-03-10", hours=10)
    before = (await client.get(f"/employees/{non.id}/overtime-balance", headers=ctx["admin"])).json()
    assert before["time_tracking"] is True and before["running_balance_minutes"] != 0
    assert (await client.get(f"/employees/{non.id}/overtime-balance", headers=ctx["device"])).status_code == 200
    await _toggle(client, ctx["admin"], non.id, False)
    device = await client.get(f"/employees/{non.id}/overtime-balance", headers=ctx["device"])
    assert device.status_code == 404 and device.json()["code"] == "EMPLOYEE_NOT_FOUND"
    for headers in (ctx["admin"], ctx["nora"]):
        body = (await client.get(f"/employees/{non.id}/overtime-balance", headers=headers)).json()
        assert body["time_tracking"] is False
        assert body["running_balance_minutes"] == 0 and body["balance_date"] is None and body["balance_start"] is None


# --- Zeiten selbst eintragen und Korrekturanträge -----------------------------------------------------


async def test_self_time_entry_is_rejected_and_reported_as_disabled(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    row = (await db_session.execute(select(AppSettings).where(AppSettings.tenant_id == 1))).scalar_one()
    row.self_time_entry_enabled = True
    row.self_time_entry_approval = False
    await db_session.commit()
    await _toggle(client, ctx["admin"], ctx["non"].id, False)
    body = {"work_date": "2025-03-18", "spans": [{"start": "08:00", "end": "12:00"}]}
    _assert_disabled(await client.post("/me/time-entries", headers=ctx["nora"], json=body))
    week = await client.get("/me/time-entries", headers=ctx["nora"], params={"from": "2025-03-17", "to": "2025-03-20"})
    assert week.status_code == 200
    assert week.json()["enabled"] is False and not any(day["can_enter"] for day in week.json()["days"])
    # Kollege mit Zeiterfassung: unverändert.
    assert (await client.post("/me/time-entries", headers=ctx["tom"], json=body)).status_code == 201
    tom_week = (await client.get("/me/time-entries", headers=ctx["tom"], params={"from": "2025-03-17", "to": "2025-03-20"})).json()
    assert tom_week["enabled"] is True


async def test_time_entry_request_cannot_be_approved_after_switching_off(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    row = (await db_session.execute(select(AppSettings).where(AppSettings.tenant_id == 1))).scalar_one()
    row.self_time_entry_enabled = True
    row.self_time_entry_approval = True
    await db_session.commit()
    created = await client.post(
        "/me/time-entries", headers=ctx["nora"], json={"work_date": "2025-03-18", "spans": [{"start": "08:00", "end": "12:00"}]}
    )
    assert created.status_code == 201 and created.json()["status"] == "PENDING"
    await _toggle(client, ctx["admin"], ctx["non"].id, False)
    url = f"/punch-correction-requests/{created.json()['request_id']}/decide"
    _assert_disabled(await client.patch(url, headers=ctx["admin"], json={"approve": True}))
    assert await _count(db_session, Punch, ctx["non"].id) == 0
    rejected = await client.patch(url, headers=ctx["admin"], json={"approve": False})
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"


async def test_correction_requests_create_and_approve(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    payload = {"work_date": "2025-03-18", "items": [{"punch_type": "COME", "time": "08:00"}], "reason": "Vergessen"}
    existing = await client.post("/punch-correction-requests", headers=ctx["nora"], json=payload)
    assert existing.status_code == 201, existing.text
    await _toggle(client, ctx["admin"], ctx["non"].id, False)
    _assert_disabled(await client.post("/punch-correction-requests", headers=ctx["nora"], json={**payload, "work_date": "2025-03-17"}))
    url = f"/punch-correction-requests/{existing.json()['id']}/decide"
    _assert_disabled(await client.patch(url, headers=ctx["admin"], json={"approve": True}))
    request_row = await db_session.get(PunchCorrectionRequest, existing.json()["id"])
    await db_session.refresh(request_row)
    assert request_row.status.value == "PENDING"
    assert (await client.patch(url, headers=ctx["admin"], json={"approve": False})).status_code == 200
    assert await _count(db_session, Punch, ctx["non"].id) == 0


# --- Tagesberechnung, Urlaub, Konto -------------------------------------------------------------------


async def test_calculate_day_has_no_target_actual_or_flags(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    non = ctx["non"]
    # Alte Stempelung aus der Zeit mit Zeiterfassung: Kommen ohne Gehen (offen) und ein langer Tag.
    assert (await _punch(client, ctx["admin"], non.id, "COME", "2025-03-11T08:00:00Z")).status_code == 201
    await _work(client, ctx["admin"], non.id, "2025-03-12", hours=11)
    await _toggle(client, ctx["admin"], non.id, False)
    for day in (date(2025, 3, 10), date(2025, 3, 11), date(2025, 3, 12)):
        calc = await calculate_day(db_session, non, day, UTC_TZ)
        assert calc.target_minutes is None and calc.actual_minutes is None
        assert calc.flags == [] and calc.flexible_share == 0 and not calc.exceeds_max_daily_minutes
        assert calc.has_punches is False
        assert calc.status == SummaryStatus.OPEN_MISSING_PUNCH
        assert missing_punch_reported(calc, True) is False
    # Freier Tag laut Modell bleibt frei.
    assert (await calculate_day(db_session, non, date(2025, 3, 15), UTC_TZ)).status == SummaryStatus.PLANNED_OFF
    # Kollege mit Zeiterfassung: unverändert Soll 8 Std.
    tracked = await calculate_day(db_session, ctx["tracker"], date(2025, 3, 10), UTC_TZ)
    assert tracked.target_minutes == 480


async def test_vacation_still_counts_and_leave_balance_is_unchanged(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    for employee in (ctx["tracker"], ctx["non"]):
        await _vacation(client, ctx["admin"], employee.id, "2025-03-13", "2025-03-14")
    tracked_before = await leave_balance(db_session, ctx["tracker"].id, 2025)
    await _toggle(client, ctx["admin"], ctx["non"].id, False)
    non_balance = await leave_balance(db_session, ctx["non"].id, 2025)
    assert non_balance.used_days == tracked_before.used_days == 2
    assert non_balance.remaining_days == tracked_before.remaining_days
    calc = await calculate_day(db_session, ctx["non"], date(2025, 3, 13), UTC_TZ)
    assert calc.status == SummaryStatus.ABSENCE and calc.absence_type == AbsenceType.VACATION
    assert calc.absence_parts == [(AbsenceType.VACATION, 1.0)]
    assert calc.credit_parts == [(AbsenceType.VACATION, 480)]
    assert calc.target_minutes is None and calc.actual_minutes is None


async def test_flexible_model_has_no_weekly_target(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(datetime(2025, 3, 3, 6, 0))  # Hinweis „Wochensoll nicht erreicht“ gilt ab dem Einschalten
    ctx = await _setup(db_session, client, model=FLEX)
    non = ctx["non"]
    await _settings(client, ctx["admin"], balance_start_date="2025-03-01")
    current = (await client.get("/settings", headers=ctx["admin"])).json()["disabled_day_flags"]
    await _settings(client, ctx["admin"], disabled_day_flags=[f for f in current if f != "WEEKLY_TARGET_MISSED"])
    at_time(NOW)
    sunday = date(2025, 3, 16)
    tracked = await calculate_day(db_session, ctx["tracker"], sunday, UTC_TZ)
    assert "WEEKLY_TARGET_MISSED" in tracked.flags and tracked.flexible_share > 0
    await _toggle(client, ctx["admin"], non.id, False)
    calc = await calculate_day(db_session, non, sunday, UTC_TZ)
    assert calc.flags == [] and calc.flexible_share == 0 and calc.flexible is False
    assert await flexible_week(db_session, non, sunday, UTC_TZ) is None
    assert not any(d["employee_id"] == non.id for d in (await client.get("/timesheet/open-days", headers=ctx["admin"])).json())


async def test_balance_is_purged_when_switched_off_and_restored_when_switched_on(
    client: AsyncClient, db_session: AsyncSession, at_time
) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    non = ctx["non"]
    await _work(client, ctx["admin"], non.id, "2025-03-17", hours=10)
    assert (await _punch(client, ctx["admin"], non.id, "COME", "2025-03-18T08:00:00Z")).status_code == 201  # offen
    await rebuild_balance(db_session, non)
    balance_before = (await client.get(f"/employees/{non.id}/overtime-balance", headers=ctx["admin"])).json()["running_balance_minutes"]
    assert await _count(db_session, OvertimeBalance, non.id) > 0 and await _count(db_session, DailySummary, non.id) > 0

    await _toggle(client, ctx["admin"], non.id, False)
    await db_session.refresh(non)
    assert non.balance_through is None  # komplett neu zu rechnen
    assert await balance_start(db_session, non) is None
    await rebuild_balance(db_session, non)
    assert await _count(db_session, OvertimeBalance, non.id) == 0
    assert await _count(db_session, DailySummary, non.id) == 0

    await _toggle(client, ctx["admin"], non.id, True)
    after = (await client.get(f"/employees/{non.id}/overtime-balance", headers=ctx["admin"])).json()
    assert after["time_tracking"] is True and after["running_balance_minutes"] == balance_before
    assert await _count(db_session, OvertimeBalance, non.id) > 0
    assert any(d["employee_id"] == non.id for d in (await client.get("/timesheet/open-days", headers=ctx["admin"])).json())


async def test_unchanged_value_does_not_invalidate_balance(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    tracker = ctx["tracker"]
    await _work(client, ctx["admin"], tracker.id, "2025-03-17")
    await rebuild_balance(db_session, tracker)
    await db_session.refresh(tracker)
    marker = tracker.balance_through
    assert marker is not None
    await _toggle(client, ctx["admin"], tracker.id, True)
    await db_session.refresh(tracker)
    assert tracker.balance_through == marker


# --- Listen: Zu klären, Grenzen, Auswertung, Startseite -----------------------------------------------


async def test_open_days_balance_limits_and_overtime_report_exclude(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    tracker, non = ctx["tracker"], ctx["non"]
    await _settings(client, ctx["admin"], balance_start_date="2025-03-01", overtime_limit_min_hours=-1)
    for employee in (tracker, non):
        assert (await _punch(client, ctx["admin"], employee.id, "COME", "2025-03-18T08:00:00Z")).status_code == 201

    def ids(response) -> set[int]:
        assert response.status_code == 200, response.text
        return {row["employee_id"] for row in response.json()}

    assert ids(await client.get("/timesheet/open-days", headers=ctx["admin"])) == {tracker.id, non.id}
    assert ids(await client.get("/timesheet/balance-limits", headers=ctx["admin"])) == {tracker.id, non.id}
    assert ids(await client.get("/reports/overtime", headers=ctx["admin"])) == {tracker.id, non.id}

    await _toggle(client, ctx["admin"], non.id, False)
    assert ids(await client.get("/timesheet/open-days", headers=ctx["admin"])) == {tracker.id}
    assert ids(await client.get("/timesheet/balance-limits", headers=ctx["admin"])) == {tracker.id}
    assert ids(await client.get("/reports/overtime", headers=ctx["admin"])) == {tracker.id}
    assert non.id not in ids(await client.get("/timesheet/monthly-caps", headers=ctx["admin"]))


async def test_dashboard_me_without_time_tracking(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    await _settings(client, ctx["admin"], portal_punching_enabled=True)
    await _vacation(client, ctx["admin"], ctx["non"].id, "2025-03-20", "2025-03-20")
    await _toggle(client, ctx["admin"], ctx["non"].id, False)
    me = (await client.get("/dashboard", headers=ctx["nora"])).json()["me"]
    assert me["time_tracking"] is False and me["portal_punching"] is False and me["location_check"] is False
    assert me["balance_minutes"] is None and me["balance_date"] is None
    assert me["week_target_minutes"] is None and me["week_actual_minutes"] is None
    assert me["today_actual_minutes"] is None and me["today_times"] == ""
    assert me["today_status"] == "ABSENCE"  # Abwesenheiten bleiben sichtbar
    assert me["on_demand"] is False and me["monthly_cap_minutes"] is None
    assert me["vacation_remaining_days"] is not None
    tom = (await client.get("/dashboard", headers=ctx["tom"])).json()["me"]
    assert tom["time_tracking"] is True and tom["portal_punching"] is True
    assert isinstance(tom["balance_minutes"], int) and tom["week_target_minutes"] == 4 * 480


# --- Lohn, Monatsbericht, Monatsabschluss -------------------------------------------------------------


def _csv_rows(text: str) -> dict[str, dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=";")
    return {row["Personalnummer"]: row for row in reader}


async def test_payroll_export_leaves_hours_empty_but_keeps_absences(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    tracker, non = ctx["tracker"], ctx["non"]
    for employee in (tracker, non):
        await _work(client, ctx["admin"], employee.id, "2025-03-10")
        await _vacation(client, ctx["admin"], employee.id, "2025-03-13", "2025-03-14")
        assert (await _punch(client, ctx["admin"], employee.id, "COME", "2025-03-11T08:00:00Z")).status_code == 201
    await _toggle(client, ctx["admin"], non.id, False)
    response = await client.get(
        "/payroll-export", headers=ctx["admin"],
        params={"employee_ids": [tracker.id, non.id], "from": "2025-03-10", "to": "2025-03-14"},
    )
    assert response.status_code == 200, response.text
    rows = _csv_rows(response.text)
    assert (rows["N1"]["Soll (Std.)"], rows["N1"]["Ist (Std.)"], rows["N1"]["Saldo (Std.)"]) == ("", "", "")
    assert rows["N1"]["Urlaubstage"] == format_days(2.0) == rows["T1"]["Urlaubstage"]
    assert rows["N1"]["Offene/fehlerhafte Tage"] == "0"
    assert rows["T1"]["Soll (Std.)"] == "40,00" and rows["T1"]["Offene/fehlerhafte Tage"] != "0"

    period = await payroll_period(db_session, non, date(2025, 3, 10), date(2025, 3, 14))
    summary = period.summary()
    assert summary.time_tracking is False and summary.open_or_error_days == 0
    assert summary.worked_minutes == 0 and summary.vacation_days == 2
    assert summary.credit_minutes == {AbsenceType.VACATION: 960}  # Gutschrift je Zeitart bleibt (DATEV-Lohnart Urlaub)


async def test_payroll_accounting_hours_are_none(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    await _vacation(client, ctx["admin"], ctx["non"].id, "2025-02-10", "2025-02-11")
    await _toggle(client, ctx["admin"], ctx["non"].id, False)
    data = await build_month(db_session, 1, 2025, 2, include_pay=False)
    rows = {row["employee_id"]: row for row in data["employees"]}
    hours = rows[ctx["non"].id]["hours"]
    assert (hours["target_minutes"], hours["actual_minutes"], hours["balance_minutes"]) == (None, None, None)
    assert hours["open_days"] == 0
    assert {a["type"]: a["days"] for a in rows[ctx["non"].id]["absences"]} == {"VACATION": 2}
    assert "time_tracking" not in rows[ctx["non"].id]  # keine neuen Schlüssel: Freigaben gälten sonst als geändert
    assert rows[ctx["tracker"].id]["hours"]["target_minutes"] == 20 * 480


async def test_surcharges_are_zero_without_time_tracking(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    rule = await client.post(
        "/surcharge-rules", headers=ctx["admin"],
        json={"name": "Nacht", "kind": "NIGHT", "percent": 25, "start_time": "06:00", "end_time": "23:00"},
    )
    if rule.status_code != 201:
        pytest.skip(f"Zuschlagsregel nicht anlegbar: {rule.text}")
    await _work(client, ctx["admin"], ctx["non"].id, "2025-03-10")
    totals = await compute_surcharges(db_session, ctx["non"], date(2025, 3, 10), date(2025, 3, 10))
    assert any(t.minutes for t in totals)
    await _toggle(client, ctx["admin"], ctx["non"].id, False)
    totals = await compute_surcharges(db_session, ctx["non"], date(2025, 3, 10), date(2025, 3, 10))
    assert totals and all(t.minutes == 0 for t in totals)


async def test_month_report_without_times(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    non = ctx["non"]
    assert (await _punch(client, ctx["admin"], non.id, "COME", "2025-02-04T08:00:00Z")).status_code == 201
    await _vacation(client, ctx["admin"], non.id, "2025-02-10", "2025-02-11")
    await _toggle(client, ctx["admin"], non.id, False)
    report = await build_month_report(db_session, non, 2025, 2)
    assert report.time_tracking is False
    assert (report.target_minutes, report.actual_minutes, report.delta_minutes, report.balance_end_minutes) == (None, None, None, None)
    assert report.open_days == [] and report.vacation_days == 2 and report.surcharges == []
    assert all(d.target_minutes is None and d.actual_minutes is None and d.delta_minutes is None for d in report.days)
    assert all(d.blocks == "" and d.come is None for d in report.days)
    labels = {d.day: d.label for d in report.days}
    assert "Stempelung fehlt" not in labels.values()
    assert labels[date(2025, 2, 10)] == "Urlaub" and labels[date(2025, 2, 3)] == ""
    html = _report_html(report, for_confirmation=False)
    assert "Ohne Zeiterfassung" in html and "Überstundenkonto zum Monatsende" not in html
    pdf = await client.get(f"/employees/{non.id}/month-report", headers=ctx["admin"], params={"year": 2025, "month": 2})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    # Mit Zeiterfassung: Zusammenfassung wie bisher.
    tracked_html = _report_html(await build_month_report(db_session, ctx["tracker"], 2025, 2), for_confirmation=False)
    assert "Überstundenkonto zum Monatsende" in tracked_html and "Ohne Zeiterfassung" not in tracked_html


async def test_closure_submit_does_not_block_and_stores_zero(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    non = ctx["non"]
    assert (await _punch(client, ctx["admin"], non.id, "COME", "2025-02-04T08:00:00Z")).status_code == 201  # offen
    blocked = await client.post(f"/employees/{non.id}/period-closures/2025/2/submit", headers=ctx["admin"])
    assert blocked.status_code == 409 and blocked.json()["code"] == "OPEN_DAYS_PRESENT"
    await _toggle(client, ctx["admin"], non.id, False)
    submitted = await client.post(f"/employees/{non.id}/period-closures/2025/2/submit", headers=ctx["admin"])
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert (body["target_minutes"], body["actual_minutes"], body["delta_minutes"], body["balance_end_minutes"]) == (0, 0, 0, 0)
    overview = {r["employee_id"]: r for r in (await client.get("/period-closures", headers=ctx["admin"], params={"year": 2025, "month": 2})).json()}
    assert overview[non.id]["time_tracking"] is False and overview[non.id]["open_day_count"] == 0
    assert overview[ctx["tracker"].id]["time_tracking"] is True
    closure = (await db_session.execute(select(PeriodClosure).where(PeriodClosure.employee_id == non.id))).scalar_one()
    assert closure.status.value in ("SUBMITTED", "CLOSED")


async def test_closed_month_keeps_snapshot_after_switching_off(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    non = ctx["non"]
    await _work(client, ctx["admin"], non.id, "2025-02-03", hours=9)
    submitted = await client.post(f"/employees/{non.id}/period-closures/2025/2/submit", headers=ctx["admin"], json={"ignore_open_days": True})
    assert submitted.status_code == 200, submitted.text
    snapshot = submitted.json()
    assert snapshot["actual_minutes"] == 540
    await _toggle(client, ctx["admin"], non.id, False)  # kein „gilt ab“ -> auch bei gesperrtem Monat möglich
    closure = (await db_session.execute(select(PeriodClosure).where(PeriodClosure.employee_id == non.id))).scalar_one()
    await db_session.refresh(closure)
    assert (closure.target_minutes, closure.actual_minutes) == (snapshot["target_minutes"], 540)


async def test_datev_has_no_open_days_warning(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    from app.services.datev_export_service import build_datev_export

    at_time(NOW)
    ctx = await _setup(db_session, client)
    tracker, non = ctx["tracker"], ctx["non"]
    tracker.employee_number, non.employee_number = "101", "102"  # DATEV braucht numerische Personalnummern
    await db_session.commit()
    for employee in (tracker, non):
        assert (await _punch(client, ctx["admin"], employee.id, "COME", "2025-02-04T08:00:00Z")).status_code == 201
    await _toggle(client, ctx["admin"], non.id, False)
    export = await build_datev_export(db_session, 1, [tracker, non], 2025, 2)
    warnings = " | ".join(export.warnings)
    assert "Tracker, Tom: " in warnings and "offene oder fehlerhafte Tage" in warnings
    assert not any(w.startswith("Ohnezeit, Nora") and "offene" in w for w in export.warnings)


async def test_report_builder_time_rows_are_empty_and_column_available(
    client: AsyncClient, db_session: AsyncSession, at_time
) -> None:
    at_time(NOW)
    ctx = await _setup(db_session, client)
    row = (await db_session.execute(select(AppSettings).where(AppSettings.tenant_id == 1))).scalar_one()
    row.custom_reports_enabled = True
    await db_session.commit()
    await _settings(client, ctx["admin"], balance_start_date="2025-01-01")
    await _vacation(client, ctx["admin"], ctx["non"].id, "2025-02-10", "2025-02-11")
    await _toggle(client, ctx["admin"], ctx["non"].id, False)

    async def preview(definition: dict, **period) -> dict:
        response = await client.post("/report-builder/preview", headers=ctx["admin"], json={"definition": definition, **period})
        assert response.status_code == 200, response.text
        return response.json()

    people = await preview({"source": "employees", "columns": ["employee_number", "time_tracking"]})
    assert sorted(people["rows"]) == [["N1", False], ["T1", True]]
    columns = ["employee_number", "target_hours", "actual_hours", "delta_hours", "balance_hours", "vacation_taken"]
    months = await preview({"source": "time_months", "columns": columns}, date_from="2025-02-01", date_to="2025-02-28")
    rows = {r[0]: r for r in months["rows"]}
    assert rows["N1"][1:] == [None, None, None, None, 2.0]
    assert rows["T1"][1] == 160.0
