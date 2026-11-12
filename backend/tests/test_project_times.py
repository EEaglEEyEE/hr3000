"""Projektzeiterfassung (A16): Kunden und Projekte, Zuordnung beim Selbst-Eintragen, Korrektur durch HR,
Auswertung „Projektzeiten“ (auch für Führungskräfte im eigenen Bereich) und Quelle im Berichts-Builder."""
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    AppSettings,
    AuditAction,
    AuditLogEntry,
    CostCenter,
    Customer,
    Employee,
    HrRole,
    Location,
    Project,
    Punch,
    PunchSource,
    PunchType,
    Role,
    Tenant,
)
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.schemas.time_entry import TimeSpanIn
from app.services import project_service
from app.services.auth_service import hash_password
from app.services.role_permissions import dump_permissions, Area, Level
from app.services.timesheet_service import punch_order_key
from tests.org_helpers import supervisor_with_department

NOW = datetime(2026, 3, 4, 18, 0)  # Mi 04.03.2026, 19:00 Berlin
PW = "pw123456"


async def _login(client: AsyncClient, email: str, headers: dict | None = None) -> dict:
    token = (await client.post("/auth/login", headers=headers or {}, json={"email": email, "password": PW})).json()["access_token"]
    return {**(headers or {}), "Authorization": f"Bearer {token}"}


async def _world(db_session: AsyncSession, client: AsyncClient, *, enabled: bool = True, required: bool = False,
                 approval: bool = False):
    location = Location(name="Zentrale", timezone="Europe/Berlin")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    erika = Employee(location_id=location.id, first_name="Erika", last_name="Muster", employee_number="P1",
                     login_email="erika@example.com", password_hash=hash_password(PW), auto_break_enabled=False)
    otto = Employee(location_id=location.id, first_name="Otto", last_name="Other", employee_number="P2",
                    login_email="otto@example.com", password_hash=hash_password(PW), auto_break_enabled=False)
    db_session.add_all([erika, otto])
    await db_session.commit()
    db_session.add_all([
        Account(email="admin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN),
        Account(email="hr@example.com", password_hash=hash_password(PW), role=HrRole.HR),
    ])
    settings_row = (await db_session.execute(select(AppSettings).where(AppSettings.tenant_id == 1))).scalar_one()
    settings_row.self_time_entry_enabled = True
    settings_row.self_time_entry_approval = approval
    settings_row.project_times_enabled = enabled
    settings_row.project_required = required
    await db_session.commit()
    # Führungskraft von Erika (nicht von Otto)
    await supervisor_with_department(db_session, location, email="lead@example.com", password=PW, members=(erika,))
    await db_session.commit()
    headers = {name: await _login(client, f"{name}@example.com") for name in ("admin", "hr", "erika", "otto", "lead")}
    return dict(location=location, erika=erika, otto=otto, headers=headers)


async def _project(client: AsyncClient, headers: dict, **fields) -> dict:
    r = await client.post("/projects", headers=headers, json={"name": "Projekt", **fields})
    assert r.status_code == 201, r.text
    return r.json()


def _entry(work_date: str, *spans: dict) -> dict:
    return {"work_date": work_date, "spans": list(spans)}


async def _audits(db_session: AsyncSession) -> list[AuditLogEntry]:
    return (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.PROJECT_CHANGED))).scalars().all()


# --- Schemas und Rechenkern -------------------------------------------------------------------------


def test_schema_rules() -> None:
    assert ProjectCreate(name="  Neubau ", number="  ").model_dump()["number"] is None
    assert ProjectCreate(name="Neubau").name == "Neubau"
    with pytest.raises(ValidationError):
        ProjectCreate(name="   ")
    with pytest.raises(ValidationError, match="Gültig von"):
        ProjectCreate(name="X", valid_from=date(2026, 3, 2), valid_to=date(2026, 3, 1))
    with pytest.raises(ValidationError):
        ProjectCreate(name="X" * 121)
    with pytest.raises(ValidationError):
        ProjectCreate(name="X", number="1" * 41)
    assert ProjectUpdate(number=None).model_fields_set == {"number"}
    with pytest.raises(ValidationError, match="nur bei Arbeitszeiten"):
        TimeSpanIn(kind="BREAK", start="10:00", end="10:15", project_id=1)
    with pytest.raises(ValidationError):
        TimeSpanIn(start="08:00", end="09:00", note="x" * 201)
    assert TimeSpanIn(start="08:00", end="09:00", note="  ").note is None


def test_project_seconds_subtracts_breaks_and_ignores_open_spans() -> None:
    def punch(kind: PunchType, hour: float, project: int | None = None) -> Punch:
        return Punch(punch_type=kind, timestamp_utc=datetime(2026, 3, 2) + timedelta(hours=hour), project_id=project)

    day = [
        punch(PunchType.GO, 6),  # Gehen ohne Kommen: ignoriert
        punch(PunchType.COME, 7, 1), punch(PunchType.BREAK_START, 9), punch(PunchType.BREAK_END, 9.5), punch(PunchType.GO, 11),
        punch(PunchType.COME, 11, 2), punch(PunchType.GO, 12),
        punch(PunchType.COME, 12, None), punch(PunchType.GO, 13),  # ohne Projekt
        punch(PunchType.COME, 14, 1),  # offen
    ]
    assert project_service.project_seconds(day) == {1: 3.5 * 3600, 2: 3600}


def test_label_and_validity() -> None:
    project = Project(name="Neubau", number="P-7", valid_from=date(2026, 3, 1), valid_to=date(2026, 3, 31))
    assert project_service.project_label(project, "Kunde A") == "P-7 Neubau (Kunde A)"
    assert project_service.project_label(Project(name="Intern")) == "Intern"
    assert project_service.valid_on(project, date(2026, 3, 1)) and project_service.valid_on(project, date(2026, 3, 31))
    assert not project_service.valid_on(project, date(2026, 2, 28)) and not project_service.valid_on(project, date(2026, 4, 1))


# --- Stammdaten ---------------------------------------------------------------------------------------


async def test_customers_crud_and_rules(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    hr, erika, lead = world["headers"]["hr"], world["headers"]["erika"], world["headers"]["lead"]
    assert (await client.post("/customers", headers=erika, json={"name": "A"})).status_code == 403
    assert (await client.post("/customers", headers=lead, json={"name": "A"})).status_code == 403
    assert (await client.get("/customers", headers=lead)).status_code == 403
    assert (await client.post("/customers", headers=hr, json={"name": "  "})).status_code == 422
    created = await client.post("/customers", headers=hr, json={"name": " Stadtwerke "})
    assert created.status_code == 201 and created.json()["name"] == "Stadtwerke"
    customer_id = created.json()["id"]
    assert (await client.post("/customers", headers=hr, json={"name": "Stadtwerke"})).status_code == 409
    other = (await client.post("/customers", headers=hr, json={"name": "Bäckerei"})).json()
    assert (await client.patch(f"/customers/{other['id']}", headers=hr, json={"name": "Stadtwerke"})).status_code == 409
    await _project(client, hr, customer_id=customer_id)
    listed = (await client.get("/customers", headers=hr)).json()
    assert [(c["name"], c["project_count"]) for c in listed] == [("Bäckerei", 0), ("Stadtwerke", 1)]
    r = await client.delete(f"/customers/{customer_id}", headers=hr)
    assert r.status_code == 409 and r.json()["code"] == "CUSTOMER_IN_USE"
    r = await client.patch(f"/customers/{customer_id}", headers=hr, json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["project_count"] == 1
    assert (await client.delete(f"/customers/{other['id']}", headers=hr)).status_code == 204
    assert (await client.delete(f"/customers/{other['id']}", headers=hr)).status_code == 404
    assert (await client.patch("/customers/999", headers=hr, json={"name": "X"})).status_code == 404
    assert (await client.patch(f"/customers/{customer_id}", headers=hr, json={"name": " "})).status_code == 422
    details = [a.detail for a in await _audits(db_session)]
    assert any("Kunde angelegt: Stadtwerke" in d for d in details) and any("Kunde gelöscht: Bäckerei" in d for d in details)


async def test_projects_crud_and_delete_rules(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    world = await _world(db_session, client)
    hr, admin = world["headers"]["hr"], world["headers"]["admin"]
    db_session.add(CostCenter(tenant_id=1, code="4711", name="Bau"))
    await db_session.commit()
    cost_center = (await db_session.execute(select(CostCenter))).scalar_one()
    customer = (await client.post("/customers", headers=hr, json={"name": "Stadtwerke"})).json()
    project = await _project(client, hr, name="Netzausbau", number="P-1", customer_id=customer["id"], cost_center_id=cost_center.id,
                             billable=True, valid_from="2026-01-01", valid_to="2026-12-31")
    assert project["customer_name"] == "Stadtwerke" and project["cost_center_label"] == "4711 Bau" and not project["in_use"]
    r = await client.post("/projects", headers=hr, json={"name": "Doppelt", "number": "P-1"})
    assert r.status_code == 409 and r.json()["code"] == "PROJECT_NUMBER_TAKEN"
    assert (await client.post("/projects", headers=hr, json={"name": "X", "customer_id": 999})).status_code == 404
    assert (await client.post("/projects", headers=hr, json={"name": "X", "cost_center_id": 999})).status_code == 404
    assert (await client.post("/projects", headers=hr, json={"name": "X", "valid_from": "2026-02-01", "valid_to": "2026-01-01"})).status_code == 422
    internal = await _project(client, admin, name="Intern", billable=False)
    # ändern: Nummer und Kunde leeren, Zeitraum gegen bestehende Werte prüfen
    r = await client.patch(f"/projects/{project['id']}", headers=hr, json={"number": None, "customer_id": None})
    assert r.status_code == 200 and r.json()["number"] is None and r.json()["customer_id"] is None
    r = await client.patch(f"/projects/{project['id']}", headers=hr, json={"valid_to": "2025-12-01"})
    assert r.status_code == 422
    assert (await client.patch(f"/projects/{project['id']}", headers=hr, json={"name": None})).status_code == 422
    assert (await client.patch(f"/projects/{internal['id']}", headers=hr, json={"number": "P-2"})).status_code == 200
    assert (await client.patch(f"/projects/{project['id']}", headers=hr, json={"number": "P-2"})).status_code == 409
    assert (await client.patch("/projects/999", headers=hr, json={"name": "Y"})).status_code == 404
    listed = (await client.get("/projects", headers=hr)).json()
    assert {p["name"] for p in listed} == {"Netzausbau", "Intern"}

    # benutztes Projekt: nicht löschbar, nur deaktivierbar
    await client.post("/me/time-entries", headers=world["headers"]["erika"], json=_entry(
        "2026-03-02", {"start": "08:00", "end": "10:00", "project_id": project["id"]}))
    r = await client.delete(f"/projects/{project['id']}", headers=hr)
    assert r.status_code == 409 and r.json()["code"] == "PROJECT_IN_USE"
    r = await client.patch(f"/projects/{project['id']}", headers=hr, json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["in_use"] is True
    assert (await client.delete(f"/projects/{internal['id']}", headers=hr)).status_code == 204
    assert (await client.delete(f"/projects/{internal['id']}", headers=hr)).status_code == 404
    details = [a.detail for a in await _audits(db_session)]
    assert any(d.startswith("Projekt angelegt: P-1 Netzausbau") for d in details)
    assert any("Projekt gelöscht" in d for d in details)


async def test_master_data_is_isolated_per_company(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    project = await _project(client, world["headers"]["hr"], name="Geheim")
    customer = (await client.post("/customers", headers=world["headers"]["hr"], json={"name": "Kunde"})).json()
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme"))
    await db_session.commit()
    db_session.add(Account(tenant_id=2, email="hr@acme.example.com", password_hash=hash_password(PW), role=HrRole.HR))
    await db_session.commit()
    foreign = await _login(client, "hr@acme.example.com", {"X-Tenant-Subdomain": "acme"})
    assert (await client.get("/projects", headers=foreign)).json() == []
    assert (await client.get("/customers", headers=foreign)).json() == []
    assert (await client.patch(f"/projects/{project['id']}", headers=foreign, json={"name": "X"})).status_code == 404
    assert (await client.delete(f"/projects/{project['id']}", headers=foreign)).status_code == 404
    assert (await client.delete(f"/customers/{customer['id']}", headers=foreign)).status_code == 404
    assert (await client.post("/projects", headers=foreign, json={"name": "X", "customer_id": customer["id"]})).status_code == 404


async def test_custom_role_master_data(client: AsyncClient, db_session: AsyncSession) -> None:
    await _world(db_session, client)
    role = Role(tenant_id=1, name="Stammdaten", permissions=dump_permissions({Area.MASTER_DATA: Level.EDIT}))
    viewer = Role(tenant_id=1, name="Zeit", permissions=dump_permissions({Area.TIME: Level.VIEW}))
    db_session.add_all([role, viewer])
    await db_session.commit()
    db_session.add_all([
        Account(email="md@example.com", password_hash=hash_password(PW), role=HrRole.HR, custom_role_id=role.id),
        Account(email="tv@example.com", password_hash=hash_password(PW), role=HrRole.HR, custom_role_id=viewer.id),
    ])
    await db_session.commit()
    md, tv = await _login(client, "md@example.com"), await _login(client, "tv@example.com")
    assert (await client.post("/projects", headers=md, json={"name": "Ok"})).status_code == 201
    assert (await client.get("/projects", headers=tv)).status_code == 200
    assert (await client.post("/projects", headers=tv, json={"name": "Nein"})).status_code == 403
    assert (await client.get("/reports/project-times", headers=md, params={"from": "2026-03-01", "to": "2026-03-31"})).status_code == 403


# --- Selbst eintragen mit Projekt -------------------------------------------------------------------


async def test_entry_with_project_and_rules(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    world = await _world(db_session, client, required=True)
    hr, erika = world["headers"]["hr"], world["headers"]["erika"]
    customer = (await client.post("/customers", headers=hr, json={"name": "Stadtwerke"})).json()
    netz = await _project(client, hr, name="Netz", number="P-1", customer_id=customer["id"])
    old = await _project(client, hr, name="Alt", valid_to="2026-03-01")
    off = await _project(client, hr, name="Aus", active=False)

    r = await client.post("/me/time-entries", headers=erika, json=_entry("2026-03-02", {"start": "08:00", "end": "12:00"}))
    assert r.status_code == 422 and r.json()["code"] == "PROJECT_REQUIRED"
    for project_id in (old["id"], off["id"], 9999):
        r = await client.post("/me/time-entries", headers=erika, json=_entry("2026-03-02", {"start": "08:00", "end": "12:00", "project_id": project_id}))
        assert r.status_code == 422 and r.json()["code"] == "PROJECT_INVALID", project_id
    r = await client.post("/me/time-entries", headers=erika, json=_entry(
        "2026-03-02",
        {"start": "08:00", "end": "12:00", "project_id": netz["id"], "note": " Leitungsplan "},
        {"start": "12:00", "end": "13:00", "project_id": netz["id"]},
        {"kind": "BREAK", "start": "10:00", "end": "10:15"},
    ))
    assert r.status_code == 201, r.text
    punches = sorted((await db_session.execute(select(Punch).where(Punch.employee_id == world["erika"].id))).scalars().all(), key=punch_order_key)
    comes = [p for p in punches if p.punch_type == PunchType.COME]
    assert [(p.project_id, p.activity_note) for p in comes] == [(netz["id"], "Leitungsplan"), (netz["id"], None)]
    assert all(p.project_id is None for p in punches if p.punch_type != PunchType.COME)

    week = (await client.get("/me/time-entries", headers=erika, params={"from": "2026-03-02", "to": "2026-03-08"})).json()
    assert week["projects_enabled"] and week["project_required"]
    assert [o["label"] for o in week["projects"]] == ["P-1 Netz (Stadtwerke)", "Alt"]
    assert week["project_names"] == {str(netz["id"]): "P-1 Netz (Stadtwerke)"}
    assert week["days"][0]["spans"][0]["project_id"] == netz["id"] and week["days"][0]["spans"][0]["note"] == "Leitungsplan"
    # inaktiver Kunde: Projekt nicht mehr auswählbar
    await client.patch(f"/customers/{customer['id']}", headers=hr, json={"active": False})
    week = (await client.get("/me/time-entries", headers=erika, params={"from": "2026-03-02", "to": "2026-03-08"})).json()
    assert [o["label"] for o in week["projects"]] == ["Alt"]
    r = await client.post("/me/time-entries", headers=erika, json=_entry("2026-03-03", {"start": "08:00", "end": "09:00", "project_id": netz["id"]}))
    assert r.status_code == 422 and "nicht mehr aktiv" in r.json()["detail"]


async def test_projects_switched_off(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    world = await _world(db_session, client, enabled=False)
    erika = world["headers"]["erika"]
    db_session.add(Project(tenant_id=1, name="X"))
    await db_session.commit()
    project_id = (await db_session.execute(select(Project.id))).scalar_one()
    r = await client.post("/me/time-entries", headers=erika, json=_entry("2026-03-02", {"start": "08:00", "end": "09:00", "project_id": project_id}))
    assert r.status_code == 422 and r.json()["code"] == "PROJECT_TIMES_DISABLED"
    r = await client.post("/me/time-entries", headers=erika, json=_entry("2026-03-02", {"start": "08:00", "end": "09:00", "note": "x"}))
    assert r.status_code == 422
    assert (await client.post("/me/time-entries", headers=erika, json=_entry("2026-03-02", {"start": "08:00", "end": "09:00"}))).status_code == 201
    week = (await client.get("/me/time-entries", headers=erika, params={"from": "2026-03-02", "to": "2026-03-02"})).json()
    assert week["projects_enabled"] is False and week["projects"] == []
    r = await client.get("/reports/project-times", headers=world["headers"]["hr"], params={"from": "2026-03-01", "to": "2026-03-31"})
    assert r.status_code == 403 and r.json()["code"] == "PROJECT_TIMES_DISABLED"
    assert (await client.get("/features", headers=world["headers"]["hr"])).json()["project_times_enabled"] is False


async def test_approval_keeps_project_and_drops_deleted_one(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    world = await _world(db_session, client, approval=True)
    hr, erika = world["headers"]["hr"], world["headers"]["erika"]
    netz = await _project(client, hr, name="Netz", number="P-1")
    temp = await _project(client, hr, name="Temp")
    first = (await client.post("/me/time-entries", headers=erika, json=_entry("2026-03-02", {"start": "08:00", "end": "12:00", "project_id": netz["id"], "note": "Plan"}))).json()
    second = (await client.post("/me/time-entries", headers=erika, json=_entry("2026-03-03", {"start": "08:00", "end": "12:00", "project_id": temp["id"]}))).json()
    pending = (await client.get("/punch-correction-requests", headers=hr, params={"status": "PENDING"})).json()
    by_id = {p["id"]: p for p in pending}
    assert by_id[first["request_id"]]["items"][0]["project_id"] == netz["id"]
    assert by_id[first["request_id"]]["project_names"] == {str(netz["id"]): "P-1 Netz"}
    week = (await client.get("/me/time-entries", headers=erika, params={"from": "2026-03-02", "to": "2026-03-03"})).json()
    assert week["days"][0]["pending"][0]["spans"][0]["project_id"] == netz["id"]
    assert week["days"][0]["pending"][0]["spans"][0]["note"] == "Plan"

    assert (await client.patch(f"/punch-correction-requests/{first['request_id']}/decide", headers=hr, json={"approve": True})).status_code == 200
    # Projekt ist noch nicht benutzt (nur beantragt) → löschbar; beim Übernehmen entfällt es
    assert (await client.delete(f"/projects/{temp['id']}", headers=hr)).status_code == 204
    assert (await client.patch(f"/punch-correction-requests/{second['request_id']}/decide", headers=hr, json={"approve": True})).status_code == 200
    comes = (await db_session.execute(
        select(Punch).where(Punch.employee_id == world["erika"].id, Punch.punch_type == PunchType.COME).order_by(Punch.timestamp_utc)
    )).scalars().all()
    assert [(p.project_id, p.activity_note, p.source) for p in comes] == [
        (netz["id"], "Plan", PunchSource.SELF_ENTRY), (None, None, PunchSource.SELF_ENTRY),
    ]


async def test_hr_changes_project_of_a_punch(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    world = await _world(db_session, client)
    hr = world["headers"]["hr"]
    netz = await _project(client, hr, name="Netz")
    erika = world["erika"]
    come = Punch(employee_id=erika.id, location_id=erika.location_id, punch_type=PunchType.COME, timestamp_utc=datetime(2026, 3, 2, 7), source=PunchSource.KIOSK)
    go = Punch(employee_id=erika.id, location_id=erika.location_id, punch_type=PunchType.GO, timestamp_utc=datetime(2026, 3, 2, 11), source=PunchSource.KIOSK)
    db_session.add_all([come, go])
    await db_session.commit()
    r = await client.patch(f"/punches/{come.id}", headers=hr, json={"correction_reason": "Projekt nachgetragen", "project_id": netz["id"], "activity_note": " Netzplan "})
    assert r.status_code == 200 and r.json()["project_id"] == netz["id"] and r.json()["activity_note"] == "Netzplan"
    audit = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.PUNCH_CORRECTED))).scalars().all()
    assert "Projekt" in audit[-1].detail
    r = await client.patch(f"/punches/{go.id}", headers=hr, json={"correction_reason": "x", "project_id": netz["id"]})
    assert r.status_code == 400 and r.json()["code"] == "PROJECT_ONLY_ON_COME"
    assert (await client.patch(f"/punches/{come.id}", headers=hr, json={"correction_reason": "x", "project_id": 999})).status_code == 404
    # ohne Projektfelder bleibt das Projekt
    r = await client.patch(f"/punches/{come.id}", headers=hr, json={"correction_reason": "Zeit", "timestamp_utc": "2026-03-02T06:30:00"})
    assert r.status_code == 200 and r.json()["project_id"] == netz["id"]
    r = await client.patch(f"/punches/{come.id}", headers=hr, json={"correction_reason": "kein Projekt", "project_id": None})
    assert r.status_code == 200 and r.json()["project_id"] is None and r.json()["activity_note"] == "Netzplan"


# --- Auswertung -----------------------------------------------------------------------------------------


async def test_project_times_report(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    world = await _world(db_session, client)
    hr, lead = world["headers"]["hr"], world["headers"]["lead"]
    customer = (await client.post("/customers", headers=hr, json={"name": "Stadtwerke"})).json()
    db_session.add(CostCenter(tenant_id=1, code="10", name="Bau"))
    await db_session.commit()
    cost_center_id = (await db_session.execute(select(CostCenter.id))).scalar_one()
    netz = await _project(client, hr, name="Netz", number="P-1", customer_id=customer["id"], cost_center_id=cost_center_id)
    intern = await _project(client, hr, name="Intern", billable=False)
    erika_h, otto_h = world["headers"]["erika"], world["headers"]["otto"]
    assert (await client.post("/me/time-entries", headers=erika_h, json=_entry(
        "2026-03-02",
        {"start": "08:00", "end": "12:00", "project_id": netz["id"]},
        {"kind": "BREAK", "start": "10:00", "end": "10:30"},
        {"start": "12:00", "end": "13:00", "project_id": intern["id"]},
        {"start": "13:00", "end": "14:00"},
    ))).status_code == 201
    # Nachtschicht: zählt zum Tag des Beginns (03.03.)
    assert (await client.post("/me/time-entries", headers=erika_h, json=_entry(
        "2026-03-03", {"start": "22:00", "end": "02:00", "end_next_day": True, "project_id": netz["id"]}))).status_code == 201
    assert (await client.post("/me/time-entries", headers=otto_h, json=_entry(
        "2026-03-02", {"start": "09:00", "end": "11:00", "project_id": netz["id"]}))).status_code == 201

    params = {"from": "2026-03-01", "to": "2026-03-31"}
    body = (await client.get("/reports/project-times", headers=hr, params=params)).json()
    rows = {(r["last_name"], r["project_name"]): r for r in body["rows"]}
    assert rows[("Muster", "Netz")]["minutes"] == 210 + 240
    assert rows[("Muster", "Intern")]["minutes"] == 60 and rows[("Muster", "Intern")]["billable"] is False
    assert rows[("Other", "Netz")]["minutes"] == 120
    assert rows[("Muster", "Netz")]["customer_name"] == "Stadtwerke" and rows[("Muster", "Netz")]["cost_center"] == "10 Bau"
    assert (body["total_minutes"], body["billable_minutes"], body["non_billable_minutes"]) == (630, 570, 60)
    # Filter
    only = (await client.get("/reports/project-times", headers=hr, params={**params, "project_id": intern["id"]})).json()
    assert [r["project_name"] for r in only["rows"]] == ["Intern"]
    by_customer = (await client.get("/reports/project-times", headers=hr, params={**params, "customer_id": customer["id"]})).json()
    assert {r["project_name"] for r in by_customer["rows"]} == {"Netz"}
    by_employee = (await client.get("/reports/project-times", headers=hr, params={**params, "employee_id": world["otto"].id})).json()
    assert [r["last_name"] for r in by_employee["rows"]] == ["Other"]
    first_day = (await client.get("/reports/project-times", headers=hr, params={"from": "2026-03-02", "to": "2026-03-02"})).json()
    assert first_day["total_minutes"] == 210 + 60 + 120
    # Führungskraft: nur ihr Bereich (Erika), Mitarbeiter gar nicht
    scoped = (await client.get("/reports/project-times", headers=lead, params=params)).json()
    assert {r["last_name"] for r in scoped["rows"]} == {"Muster"}
    assert (await client.get("/reports/project-times", headers=erika_h, params=params)).status_code == 403
    # Zeitraum
    assert (await client.get("/reports/project-times", headers=hr, params={"from": "2026-03-31", "to": "2026-03-01"})).status_code == 400
    assert (await client.get("/reports/project-times", headers=hr, params={"from": "2025-01-01", "to": "2026-03-01"})).status_code == 400
    empty = (await client.get("/reports/project-times", headers=hr, params={"from": "2026-01-01", "to": "2026-01-31"})).json()
    assert empty["rows"] == [] and empty["total_minutes"] == 0


async def test_report_builder_source(client: AsyncClient, db_session: AsyncSession, at_time) -> None:
    at_time(NOW)
    world = await _world(db_session, client, enabled=False)
    hr = world["headers"]["hr"]
    settings_row = (await db_session.execute(select(AppSettings).where(AppSettings.tenant_id == 1))).scalar_one()
    settings_row.custom_reports_enabled = True
    await db_session.commit()
    catalog_body = (await client.get("/report-builder/catalog", headers=hr)).json()
    assert "project_times" not in {s["key"] for s in catalog_body["sources"]}
    definition = {"source": "project_times", "columns": ["last_name", "project", "customer", "billable", "project_hours"]}
    period = {"date_from": "2026-03-01", "date_to": "2026-03-31"}
    r = await client.post("/report-builder/preview", headers=hr, json={"definition": definition, **period})
    assert r.status_code == 400 and r.json()["code"] == "REPORT_SOURCE_DISABLED"

    settings_row.project_times_enabled = True
    await db_session.commit()
    source = next(s for s in (await client.get("/report-builder/catalog", headers=hr)).json()["sources"] if s["key"] == "project_times")
    assert source["requires_period"] is True and {"project", "project_number", "billable", "cost_center", "project_hours"} <= {c["key"] for c in source["columns"]}
    netz = await _project(client, hr, name="Netz")
    await client.post("/me/time-entries", headers=world["headers"]["erika"], json=_entry(
        "2026-03-02", {"start": "08:00", "end": "09:30", "project_id": netz["id"]}))
    r = await client.post("/report-builder/preview", headers=hr, json={"definition": {**definition, "group_by": "project"}, **period})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == [["Muster", "Netz", None, True, 1.5]]
    lead = (await client.post("/report-builder/preview", headers=world["headers"]["lead"], json={"definition": definition, **period})).json()
    assert [row[0] for row in lead["rows"]] == ["Muster"]


async def test_settings_switches(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client, enabled=False)
    admin = world["headers"]["admin"]
    current = (await client.get("/settings", headers=admin)).json()
    assert current["project_times_enabled"] is False and current["project_required"] is False
    r = await client.patch("/settings", headers=admin, json={"project_times_enabled": True, "project_required": True})
    assert r.status_code == 200 and r.json()["project_times_enabled"] and r.json()["project_required"]
    assert (await client.get("/features", headers=world["headers"]["hr"])).json()["project_times_enabled"] is True
    assert (await client.patch("/settings", headers=world["headers"]["hr"], json={"project_times_enabled": False})).status_code == 403
