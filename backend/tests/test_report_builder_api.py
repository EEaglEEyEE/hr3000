"""Berichts-Builder über HTTP: Schalter, Rechte je Rolle und Spalte, Bereich der Führungskraft,
Quellen, Filter/Sortierung/Gruppierung, CSV, gespeicherte und geteilte Berichte, Audit, Mandanten."""
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.migration import PORTABLE_SETTINGS
from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    AbsenceTypeDefinition,
    Account,
    AttributeDefinition,
    AttributeSection,
    AttributeValue,
    AuditAction,
    AuditLogEntry,
    BalanceAdjustment,
    Compensation,
    ContractType,
    Employee,
    EmployeeDefaultShift,
    EmploymentContract,
    HrRole,
    Location,
    OvertimeBalance,
    PayType,
    SavedReport,
    Tenant,
)
from app.models.balance_adjustment import AdjustmentKind
from app.models.shift_template import TargetPeriod
from app.services import personal_data_service
from app.services import report_builder_service as builder
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings
from tests.org_helpers import department, supervisor_with_department

PERIOD_JAN = {"date_from": "2025-01-01", "date_to": "2025-01-31"}


async def _world(db_session: AsyncSession, client: AsyncClient, *, enabled: bool = True) -> dict:
    location = Location(name="Ulm", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    anna = Employee(location_id=location.id, first_name="Anna", last_name="Alpha", employee_number="A1", position="Vertrieb Innendienst",
                    hire_date=date(2020, 1, 1), birth_date=date(1990, 5, 1), balance_through=date.today())
    bernd = Employee(location_id=location.id, first_name="Bernd", last_name="Beta", employee_number="B1", hire_date=date(2021, 3, 1))
    carla = Employee(location_id=location.id, first_name="Carla", last_name="=Cmd()", employee_number="C1", active=False,
                     termination_date=date(2024, 12, 31))
    worker = Employee(location_id=location.id, first_name="Wim", last_name="Worker", employee_number="W1",
                      login_email="worker@example.com", password_hash=hash_password("pw"))
    db_session.add_all([anna, bernd, carla, worker])
    await db_session.commit()
    sales, lead, _ = await supervisor_with_department(db_session, location, email="sup@example.com", department_name="Vertrieb", members=(anna,))
    await department(db_session, "Lager", bernd)
    db_session.add_all([
        Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        Account(email="hr2@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
        Account(email="pay@example.com", password_hash=hash_password("pw"), role=HrRole.HR, payroll_access=True),
        Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN),
    ])
    (await get_or_create_settings(db_session, 1)).custom_reports_enabled = enabled
    await db_session.commit()
    headers = {}
    for name in ("hr", "hr2", "pay", "admin", "sup", "worker"):
        token = (await client.post("/auth/login", json={"email": f"{name}@example.com", "password": "pw"})).json()["access_token"]
        headers[name] = {"Authorization": f"Bearer {token}"}
    return dict(location=location, anna=anna, bernd=bernd, carla=carla, worker=worker, lead=lead, sales=sales, headers=headers)


def definition(source: str = "employees", columns=("last_name",), **extra) -> dict:
    return {"source": source, "columns": list(columns), **extra}


async def preview(client: AsyncClient, headers: dict, definition_: dict, **period):
    return await client.post("/report-builder/preview", headers=headers, json={"definition": definition_, **period})


def column(body: dict, key: str) -> list:
    index = [c["key"] for c in body["columns"]].index(key)
    return [row[index] for row in body["rows"]]


async def audits(db_session: AsyncSession, action: AuditAction) -> list[AuditLogEntry]:
    return list((await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == action).order_by(AuditLogEntry.id))).scalars().all())


# --- Schalter und Rollen ---------------------------------------------------------------------------


async def test_switch_off_blocks_everything(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client, enabled=False)
    admin = world["headers"]["admin"]
    calls = [
        client.get("/report-builder/catalog", headers=admin),
        preview(client, admin, definition()),
        client.post("/report-builder/export", headers=admin, json={"definition": definition()}),
        client.get("/report-builder/reports", headers=admin),
        client.post("/report-builder/reports", headers=admin, json={"name": "x", "definition": definition()}),
        client.get("/report-builder/reports/1", headers=admin),
        client.put("/report-builder/reports/1", headers=admin, json={"name": "x", "definition": definition()}),
        client.delete("/report-builder/reports/1", headers=admin),
        client.post("/report-builder/reports/1/run", headers=admin, json={}),
        client.post("/report-builder/reports/1/export", headers=admin, json={}),
    ]
    for call in calls:
        response = await call
        assert response.status_code == 403 and response.json()["code"] == "FEATURE_DISABLED"


async def test_switch_is_off_by_default_and_admin_can_turn_it_on(client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/features", headers=headers)).json()["custom_reports_enabled"] is False
    assert (await client.get("/report-builder/catalog", headers=headers)).status_code == 403
    patched = await client.patch("/settings", headers=headers, json={"custom_reports_enabled": True})
    assert patched.status_code == 200 and patched.json()["custom_reports_enabled"] is True
    assert (await client.get("/features", headers=headers)).json()["custom_reports_enabled"] is True
    assert (await client.get("/report-builder/catalog", headers=headers)).status_code == 200
    assert (await client.patch("/settings", headers=headers, json={"custom_reports_enabled": "ja"})).status_code == 422
    assert "custom_reports_enabled" in PORTABLE_SETTINGS
    changed = await audits(db_session, AuditAction.SETTINGS_CHANGED)
    assert changed


async def test_employee_without_role_and_anonymous_are_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    assert (await client.get("/report-builder/catalog", headers=world["headers"]["worker"])).status_code == 403
    assert (await preview(client, world["headers"]["worker"], definition())).status_code == 403
    assert (await client.get("/report-builder/catalog")).status_code in (401, 403)


# --- Positivliste ----------------------------------------------------------------------------------


async def _attributes(db_session: AsyncSession, world: dict) -> dict:
    section = AttributeSection(tenant_id=1, name="Weiteres")
    archived_section = AttributeSection(tenant_id=1, name="Alt", archived=True)
    db_session.add_all([section, archived_section])
    await db_session.flush()
    size = AttributeDefinition(tenant_id=1, section_id=section.id, label="Schuhgröße", field_type="NUMBER")
    color = AttributeDefinition(tenant_id=1, section_id=section.id, label="Farbe", field_type="SELECT", options='["Rot", "Blau"]')
    mentor = AttributeDefinition(tenant_id=1, section_id=section.id, label="Pate", field_type="EMPLOYEE")
    archived = AttributeDefinition(tenant_id=1, section_id=section.id, label="Archiviert", field_type="TEXT", archived=True)
    hidden = AttributeDefinition(tenant_id=1, section_id=archived_section.id, label="Im alten Bereich", field_type="TEXT")
    db_session.add_all([size, color, mentor, archived, hidden])
    await db_session.flush()
    db_session.add_all([
        AttributeValue(tenant_id=1, employee_id=world["anna"].id, attribute_id=size.id, value="38"),
        AttributeValue(tenant_id=1, employee_id=world["bernd"].id, attribute_id=size.id, value="44"),
        AttributeValue(tenant_id=1, employee_id=world["bernd"].id, attribute_id=size.id, value="45", valid_from=date.today() + timedelta(days=30)),
        AttributeValue(tenant_id=1, employee_id=world["anna"].id, attribute_id=color.id, value="Rot"),
        AttributeValue(tenant_id=1, employee_id=world["anna"].id, attribute_id=mentor.id, value=str(world["bernd"].id)),
    ])
    await db_session.commit()
    return dict(size=size, color=color, mentor=mentor, archived=archived, hidden=hidden)


async def test_catalog_depends_on_role(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    attributes = await _attributes(db_session, world)

    async def keys(role: str) -> dict[str, set[str]]:
        body = (await client.get("/report-builder/catalog", headers=world["headers"][role])).json()
        return {s["key"]: {c["key"] for c in s["columns"]} for s in body["sources"]}

    sup, hr, pay, admin = await keys("sup"), await keys("hr"), await keys("pay"), await keys("admin")
    size_key = f"attr_{attributes['size'].id}"
    assert "last_name" in sup["employees"] and "birth_date" not in sup["employees"] and size_key not in sup["employees"]
    assert "birth_date" in hr["employees"] and "city" in hr["employees"] and size_key in hr["employees"]
    assert not hr["employees"] & ({"iban", "tax_id", "tax_class", "pay_amount", "pay_type"})
    assert {"iban", "tax_id", "tax_class", "pay_amount", "pay_type"} <= pay["employees"] <= admin["employees"]
    assert f"attr_{attributes['archived'].id}" not in admin["employees"]
    assert f"attr_{attributes['hidden'].id}" not in admin["employees"]
    assert sup["absences"] == hr["absences"] and "days" in sup["absences"]
    body = (await client.get("/report-builder/catalog", headers=world["headers"]["hr"])).json()
    employees = next(s for s in body["sources"] if s["key"] == "employees")
    color = next(c for c in employees["columns"] if c["key"] == f"attr_{attributes['color'].id}")
    assert color["type"] == "enum" and [o["value"] for o in color["options"]] == ["Rot", "Blau"] and color["group"] == "Eigene Felder"
    assert next(s for s in body["sources"] if s["key"] == "time_months")["requires_period"] is True
    assert body["max_page_size"] == 200 and body["max_range_days"] == 366 and len(body["operators"]) == 11


# --- Mitarbeitende ---------------------------------------------------------------------------------


async def test_employee_source_columns_filter_sort_and_pagination(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    db_session.add(EmployeeDefaultShift(employee_id=world["bernd"].id, valid_from=date(2020, 1, 1), weekdays_mask=31,
                                        target_minutes=1200, target_period=TargetPeriod.WEEKLY))
    db_session.add(EmploymentContract(tenant_id=1, employee_id=world["anna"].id, valid_from=date(2020, 1, 1),
                                      contract_type=ContractType.FIXED_TERM, fixed_term_end=date(2030, 12, 31)))
    await db_session.commit()
    columns = ["last_name", "department", "location", "supervisor", "status", "work_time_model", "weekly_hours", "fte",
               "hire_date", "termination_date", "position", "birth_date", "contract_type", "fixed_term_end", "probation_end"]
    response = await preview(client, world["headers"]["hr"], definition(columns=columns, sort=[{"column": "last_name"}]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_rows"] == 5 and body["date_from"] is None
    assert column(body, "last_name") == ["=Cmd()", "Alpha", "Beta", "Leitung", "Worker"]
    rows = {row[0]: dict(zip([c["key"] for c in body["columns"]], row)) for row in body["rows"]}
    anna, bernd, carla = rows["Alpha"], rows["Beta"], rows["=Cmd()"]
    assert anna["department"] == "Vertrieb" and anna["location"] == "Ulm" and anna["supervisor"] == "Sam Leitung"
    assert anna["status"] == "Aktiv" and carla["status"] == "Inaktiv" and carla["termination_date"] == "2024-12-31"
    assert anna["work_time_model"] is None and anna["weekly_hours"] is None and anna["fte"] == 1.0
    assert (bernd["work_time_model"], bernd["weekly_hours"], bernd["fte"]) == ("Individuell", 20.0, 0.5)
    assert anna["birth_date"] == "1990-05-01" and anna["contract_type"] == "Befristet" and anna["fixed_term_end"] == "2030-12-31"
    assert body["totals"] == {"weekly_hours": 20.0, "fte": 4.5}

    filtered = (await preview(client, world["headers"]["hr"], definition(
        columns=["last_name"],
        filters=[{"column": "status", "operator": "ne", "value": "INACTIVE"}, {"column": "hire_date", "operator": "gte", "value": "2021-01-01"}],
    ))).json()
    assert column(filtered, "last_name") == ["Beta"]
    page = (await preview(client, world["headers"]["hr"], definition(columns=["last_name"], sort=[{"column": "last_name", "direction": "desc"}]),
                          page=2, page_size=2)).json()
    assert page["rows"] == [["Beta"], ["Alpha"]] and page["total_rows"] == 5 and page["page"] == 2


async def test_group_by_department_with_counts(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    body = (await preview(client, world["headers"]["hr"], definition(columns=["last_name", "fte"], group_by="department"))).json()
    assert body["group_by"] == "department"
    assert [(g["label"], g["count"], g["sums"]) for g in body["groups"]] == [
        ("Lager", 1, {"fte": 1.0}), ("Vertrieb", 2, {"fte": 2.0}), ("", 2, {"fte": 2.0})
    ]
    assert column(body, "last_name")[:3] == ["Beta", "Alpha", "Leitung"]


async def test_personal_data_and_compensation_columns_need_rights(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    await personal_data_service.save(db_session, world["anna"], {"city": "Ulm", "iban": "DE89370400440532013000", "tax_class": 3, "children_count": 2})
    db_session.add(Compensation(tenant_id=1, employee_id=world["anna"].id, valid_from=date(2020, 1, 1), pay_type=PayType.MONTHLY, amount=3500))
    db_session.add(Compensation(tenant_id=1, employee_id=world["anna"].id, valid_from=date.today() + timedelta(days=10), pay_type=PayType.MONTHLY, amount=9999))
    await db_session.commit()
    headers = world["headers"]

    hr = await preview(client, headers["hr"], definition(columns=["last_name", "city", "children_count"], filters=[{"column": "city", "operator": "eq", "value": "ulm"}]))
    assert hr.status_code == 200 and hr.json()["rows"] == [["Alpha", "Ulm", 2.0]]
    for role, key in (("hr", "iban"), ("hr", "pay_amount"), ("hr", "tax_class"), ("sup", "city"), ("sup", "birth_date")):
        response = await preview(client, headers[role], definition(columns=["last_name", key]))
        assert response.status_code == 403 and response.json()["code"] == "REPORT_COLUMN_FORBIDDEN", (role, key)
    # auch nicht als Filter, Sortierung oder Gruppierung
    for extra in (
        {"filters": [{"column": "iban", "operator": "starts_with", "value": "DE"}]},
        {"sort": [{"column": "pay_amount"}]},
        {"group_by": "pay_type"},
    ):
        assert (await preview(client, headers["hr"], definition(**extra))).status_code == 403

    pay = (await preview(client, headers["pay"], definition(columns=["last_name", "iban", "tax_class", "pay_type", "pay_amount"],
                                                            filters=[{"column": "pay_amount", "operator": "gt", "value": 0}]))).json()
    assert pay["rows"] == [["Alpha", "DE89370400440532013000", 3.0, "Monatsgehalt", 3500.0]]
    viewed = await audits(db_session, AuditAction.COMPENSATION_VIEWED)
    assert len(viewed) == 1 and viewed[0].entity_type == "saved_report" and "3500" not in (viewed[0].detail or "")
    # Bank ohne Vergütung: kein Vergütungs-Eintrag
    await preview(client, headers["pay"], definition(columns=["last_name", "iban"]))
    assert len(await audits(db_session, AuditAction.COMPENSATION_VIEWED)) == 1


async def test_attribute_columns_values_and_filters(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    attributes = await _attributes(db_session, world)
    size, color, mentor = (f"attr_{attributes[k].id}" for k in ("size", "color", "mentor"))
    body = (await preview(client, world["headers"]["hr"], definition(
        columns=["last_name", size, color, mentor], filters=[{"column": size, "operator": "gte", "value": 40}]))).json()
    assert body["rows"] == [["Beta", 44.0, None, None]]  # künftiger Wert 45 gilt noch nicht
    body = (await preview(client, world["headers"]["hr"], definition(
        columns=["last_name", color, mentor], filters=[{"column": color, "operator": "in", "value": ["Rot"]}]))).json()
    assert body["rows"] == [["Alpha", "Rot", "Bernd Beta"]]
    bad = await preview(client, world["headers"]["hr"], definition(columns=["last_name"], filters=[{"column": color, "operator": "eq", "value": "Grün"}]))
    assert bad.status_code == 422 and bad.json()["code"] == "REPORT_FILTER_INVALID"
    bad = await preview(client, world["headers"]["hr"], definition(columns=["last_name"], filters=[{"column": size, "operator": "contains", "value": "4"}]))
    assert bad.status_code == 422
    for key in (f"attr_{attributes['archived'].id}", "attr_999999"):
        unknown = await preview(client, world["headers"]["hr"], definition(columns=["last_name", key]))
        assert unknown.status_code == 400 and unknown.json()["code"] == "REPORT_COLUMN_UNKNOWN"
    assert (await preview(client, world["headers"]["sup"], definition(columns=["last_name", size]))).status_code == 403


async def test_supervisor_sees_only_own_area(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    body = (await preview(client, world["headers"]["sup"], definition(columns=["last_name"], sort=[{"column": "last_name"}]))).json()
    assert column(body, "last_name") == ["Alpha", "Leitung"]
    db_session.add(Absence(employee_id=world["bernd"].id, type=AbsenceType.SICK, date_from=date(2025, 1, 6), date_to=date(2025, 1, 6),
                           approval_status=AbsenceApprovalStatus.APPROVED))
    await db_session.commit()
    body = (await preview(client, world["headers"]["sup"], definition("absences", ["last_name", "days"]), **PERIOD_JAN)).json()
    assert body["total_rows"] == 0


async def test_supervisor_without_employee_sees_nothing(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    db_session.add(Account(email="lonely@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR))
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "lonely@example.com", "password": "pw"})).json()["access_token"]
    body = (await preview(client, {"Authorization": f"Bearer {token}"}, definition())).json()
    assert body["total_rows"] == 0 and world


# --- Abwesenheiten ---------------------------------------------------------------------------------


async def test_absence_source(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    sick_type = AbsenceTypeDefinition(tenant_id=1, name="Krankheit (AU)", category=AbsenceType.SICK)
    db_session.add(sick_type)
    await db_session.flush()
    approved = AbsenceApprovalStatus.APPROVED
    db_session.add_all([
        Absence(employee_id=world["anna"].id, type=AbsenceType.SICK, absence_type_id=sick_type.id, date_from=date(2025, 1, 13), date_to=date(2025, 1, 19), approval_status=approved),
        Absence(employee_id=world["bernd"].id, type=AbsenceType.VACATION, date_from=date(2025, 1, 30), date_to=date(2025, 2, 4), approval_status=AbsenceApprovalStatus.PENDING),
        Absence(employee_id=world["bernd"].id, type=AbsenceType.VACATION, date_from=date(2025, 1, 2), date_to=date(2025, 1, 2), half_day=True, approval_status=approved),
        Absence(employee_id=world["bernd"].id, type=AbsenceType.TIME_OFF_IN_LIEU, date_from=date(2025, 1, 3), date_to=date(2025, 1, 3), duration_minutes=90, approval_status=approved),
        Absence(employee_id=world["anna"].id, type=AbsenceType.SICK, date_from=date(2025, 2, 10), date_to=date(2025, 2, 10), approval_status=approved),
    ])
    await db_session.commit()
    headers = world["headers"]["hr"]
    missing = await preview(client, headers, definition("absences", ["last_name"]))
    assert missing.status_code == 400 and missing.json()["code"] == "REPORT_PERIOD_REQUIRED"
    columns = ["last_name", "date_from", "date_to", "absence_type", "category", "days", "hours", "half_day", "approval_status"]
    body = (await preview(client, headers, definition("absences", columns, sort=[{"column": "date_from"}]), **PERIOD_JAN)).json()
    assert body["date_from"] == "2025-01-01" and body["date_to"] == "2025-01-31"
    assert body["rows"] == [
        ["Beta", "2025-01-02", "2025-01-02", "Urlaub", "Urlaub", 0.5, None, True, "Genehmigt"],
        ["Beta", "2025-01-03", "2025-01-03", "Freizeitausgleich", "Freizeitausgleich", 0.0, 1.5, False, "Genehmigt"],
        ["Alpha", "2025-01-13", "2025-01-19", "Krankheit (AU)", "Krankheit", 5.0, None, False, "Genehmigt"],
        ["Beta", "2025-01-30", "2025-02-04", "Urlaub", "Urlaub", 2.0, None, False, "Offen"],  # nur Tage im Zeitraum
    ]
    assert body["totals"] == {"days": 7.5, "hours": 1.5}
    grouped = (await preview(client, headers, definition("absences", ["last_name", "days"], group_by="category",
                                                         filters=[{"column": "approval_status", "operator": "eq", "value": "APPROVED"}]), **PERIOD_JAN)).json()
    assert [(g["label"], g["count"], g["sums"]["days"]) for g in grouped["groups"]] == [("Freizeitausgleich", 1, 0.0), ("Krankheit", 1, 5.0), ("Urlaub", 1, 0.5)]
    too_long = await preview(client, headers, definition("absences", ["last_name"]), date_from="2024-01-01", date_to="2025-01-02")
    assert too_long.status_code == 422


# --- Zeit je Monat ---------------------------------------------------------------------------------


async def test_time_months_source_uses_balance_cache(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    anna = world["anna"]
    db_session.add_all([
        OvertimeBalance(employee_id=anna.id, balance_date=date(2025, 1, 2), daily_target_minutes=480, daily_actual_minutes=540, daily_delta_minutes=60, running_balance_minutes=60),
        OvertimeBalance(employee_id=anna.id, balance_date=date(2025, 1, 3), daily_target_minutes=480, daily_actual_minutes=480, daily_delta_minutes=0, running_balance_minutes=60),
        OvertimeBalance(employee_id=anna.id, balance_date=date(2025, 2, 3), daily_target_minutes=480, daily_actual_minutes=435, daily_delta_minutes=-45, running_balance_minutes=15),
        BalanceAdjustment(tenant_id=1, employee_id=anna.id, effective_date=date(2025, 3, 10), minutes=120, kind=AdjustmentKind.CORRECTION, note="Korrektur"),
        BalanceAdjustment(tenant_id=1, employee_id=anna.id, effective_date=date(2025, 4, 10), minutes=600, kind=AdjustmentKind.CORRECTION, note="später"),
        Absence(employee_id=anna.id, type=AbsenceType.VACATION, date_from=date(2025, 1, 6), date_to=date(2025, 1, 7), approval_status=AbsenceApprovalStatus.APPROVED),
    ])
    await db_session.commit()
    headers = world["headers"]["hr"]
    columns = ["last_name", "month", "target_hours", "actual_hours", "delta_hours", "balance_hours", "vacation_taken", "vacation_remaining"]
    body = (await preview(client, headers, definition("time_months", columns, filters=[{"column": "last_name", "operator": "eq", "value": "Alpha"}]),
                          date_from="2025-01-15", date_to="2025-03-02")).json()
    assert body["date_from"] == "2025-01-01" and body["date_to"] == "2025-03-31"  # ganze Monate
    rows = [row[:7] for row in body["rows"]]
    assert rows == [
        ["Alpha", "2025-01", 16.0, 17.0, 1.0, 1.0, 2.0],
        ["Alpha", "2025-02", 8.0, 7.25, -0.75, 0.25, 0.0],
        ["Alpha", "2025-03", 0.0, 0.0, 0.0, 2.25, 0.0],
    ]
    assert all(isinstance(row[7], float) for row in body["rows"])
    assert body["totals"]["delta_hours"] == 0.25 and body["totals"]["vacation_taken"] == 2.0
    # Stand vor dem Zeitraum wird übernommen (März ohne gerechnete Tage)
    march = (await preview(client, headers, definition("time_months", ["last_name", "balance_hours"], filters=[{"column": "last_name", "operator": "eq", "value": "Alpha"}]),
                           date_from="2025-03-01", date_to="2025-03-31")).json()
    assert march["rows"] == [["Alpha", 2.25]]
    # ausgeschiedene Carla (Austritt 2024) hat 2025 keine Zeilen, Bernd (Konto nie gerechnet) wird nachgerechnet
    everyone = (await preview(client, headers, definition("time_months", ["last_name", "delta_hours"]), date_from="2025-01-01", date_to="2025-01-31")).json()
    assert "=Cmd()" not in column(everyone, "last_name") and "Beta" in column(everyone, "last_name")
    await db_session.refresh(world["bernd"])
    assert world["bernd"].balance_through is not None


# --- Grenzen ---------------------------------------------------------------------------------------


async def test_result_too_large(client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    world = await _world(db_session, client)
    monkeypatch.setattr(builder, "MAX_ROWS", 2)
    response = await preview(client, world["headers"]["hr"], definition())
    assert response.status_code == 400 and response.json()["code"] == "RESULT_TOO_LARGE"
    ok = await preview(client, world["headers"]["hr"], definition(filters=[{"column": "last_name", "operator": "starts_with", "value": "A"}]))
    assert ok.status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"definition": {"source": "employees", "columns": ["last_name"], "sql": "SELECT * FROM accounts"}},
        {"definition": {"source": "accounts", "columns": ["email"]}},
        {"definition": {"source": "employees", "columns": ["password_hash"]}},
        {"definition": {"source": "employees", "columns": ["last_name"]}, "page_size": 1000},
        {"definition": {"source": "employees", "columns": ["last_name"]}, "date_from": "2025-01-01"},
    ],
)
async def test_invalid_definitions_are_rejected(client: AsyncClient, db_session: AsyncSession, payload: dict) -> None:
    world = await _world(db_session, client)
    assert (await client.post("/report-builder/preview", headers=world["headers"]["admin"], json=payload)).status_code == 422


# --- CSV -------------------------------------------------------------------------------------------


async def test_csv_export_format_and_audit(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    response = await client.post("/report-builder/export", headers=world["headers"]["hr"], json={
        "definition": definition(columns=["last_name", "hire_date", "fte"], sort=[{"column": "last_name"}]), "page_size": 1})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="bericht.csv"'
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")
    lines = text[1:].split("\r\n")
    assert lines[0] == "Nachname;Eintritt;Vollzeitanteil (FTE)"
    assert lines[1] == "'=Cmd();;1"  # Formel entschärft, alle Zeilen trotz page_size
    assert lines[2] == "Alpha;01.01.2020;1"
    assert lines[-2] == "Gesamt;5;5"
    exported = await audits(db_session, AuditAction.REPORT_EXPORTED)
    assert len(exported) == 1 and exported[0].entity_id == 0
    assert exported[0].detail == "Ad-hoc-Bericht, Quelle Mitarbeitende, 3 Spalten, 5 Zeilen"
    assert "Alpha" not in exported[0].detail
    assert (await client.post("/report-builder/export", headers=world["headers"]["hr"], json={
        "definition": definition(columns=["iban"])})).status_code == 403


async def test_preview_is_audited_without_content(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    await preview(client, world["headers"]["sup"], definition("absences", ["last_name"]), **PERIOD_JAN)
    runs = await audits(db_session, AuditAction.REPORT_RUN)
    assert len(runs) == 1 and runs[0].entity_type == "saved_report"
    assert runs[0].detail == "Ad-hoc-Bericht, Quelle Abwesenheiten, 1 Spalten, 0 Zeilen, Zeitraum 01.01.2025–31.01.2025"


# --- Gespeicherte Berichte -------------------------------------------------------------------------


async def test_saved_report_crud_and_visibility(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    h = world["headers"]
    created = await client.post("/report-builder/reports", headers=h["hr"], json={
        "name": " Eintritte ", "description": "Neue Leute", "definition": definition(columns=["last_name", "hire_date"])})
    assert created.status_code == 201, created.text
    report = created.json()
    assert report["name"] == "Eintritte" and report["mine"] and report["can_edit"] and not report["shared"]
    assert report["owner_name"] == "hr@example.com"
    rid = report["id"]

    # privat: andere sehen ihn nicht (auch Admins nicht)
    for role in ("hr2", "admin", "sup"):
        assert (await client.get(f"/report-builder/reports/{rid}", headers=h[role])).status_code == 404
        assert (await client.get("/report-builder/reports", headers=h[role])).json() == []
    assert len((await client.get("/report-builder/reports", headers=h["hr"])).json()) == 1

    # teilen
    shared = await client.put(f"/report-builder/reports/{rid}", headers=h["hr"], json={
        "name": "Eintritte", "definition": definition(columns=["last_name", "hire_date"]), "shared": True})
    assert shared.status_code == 200 and shared.json()["shared"] and shared.json()["description"] is None
    other = (await client.get(f"/report-builder/reports/{rid}", headers=h["hr2"])).json()
    assert other["mine"] is False and other["can_edit"] is False
    assert (await client.get(f"/report-builder/reports/{rid}", headers=h["admin"])).json()["can_edit"] is True
    assert (await client.put(f"/report-builder/reports/{rid}", headers=h["hr2"], json={"name": "x", "definition": definition()})).status_code == 403
    assert (await client.delete(f"/report-builder/reports/{rid}", headers=h["hr2"])).status_code == 403
    assert (await client.delete(f"/report-builder/reports/{rid}", headers=h["sup"])).status_code == 403
    renamed = await client.put(f"/report-builder/reports/{rid}", headers=h["admin"], json={"name": "Von Admin", "definition": definition(), "shared": True})
    assert renamed.status_code == 200 and renamed.json()["owner_account_id"] == report["owner_account_id"]
    assert (await client.delete(f"/report-builder/reports/{rid}", headers=h["admin"])).status_code == 204
    assert (await client.get(f"/report-builder/reports/{rid}", headers=h["hr"])).status_code == 404
    assert (await client.delete(f"/report-builder/reports/{rid}", headers=h["hr"])).status_code == 404

    changes = [e.detail for e in await audits(db_session, AuditAction.REPORT_CHANGED)]
    assert changes == ["Bericht „Eintritte“ angelegt", "Bericht „Eintritte“ geändert (geteilt)", "Bericht „Von Admin“ geändert (geteilt)", "Bericht „Von Admin“ gelöscht"]


@pytest.mark.parametrize(
    "payload,status",
    [
        ({"name": "", "definition": {"source": "employees", "columns": ["last_name"]}}, 422),
        ({"name": "x" * 101, "definition": {"source": "employees", "columns": ["last_name"]}}, 422),
        ({"name": "ok", "definition": {"source": "employees", "columns": []}}, 422),
        ({"name": "ok", "definition": {"source": "employees", "columns": ["iban"]}}, 403),
        ({"name": "ok", "definition": {"source": "employees", "columns": ["attr_99999"]}}, 400),
        ({"name": "ok", "definition": {"source": "employees", "columns": ["last_name"]}, "tenant_id": 2}, 422),
    ],
)
async def test_saving_validates_definition_and_rights(client: AsyncClient, db_session: AsyncSession, payload: dict, status: int) -> None:
    world = await _world(db_session, client)
    assert (await client.post("/report-builder/reports", headers=world["headers"]["hr"], json=payload)).status_code == status
    assert (await db_session.execute(select(SavedReport))).scalars().all() == []


async def test_shared_report_omits_forbidden_columns_and_respects_scope(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    h = world["headers"]
    await personal_data_service.save(db_session, world["anna"], {"iban": "DE89370400440532013000", "city": "Ulm"})
    await db_session.commit()
    created = (await client.post("/report-builder/reports", headers=h["pay"], json={
        "name": "Bank", "shared": True, "definition": definition(columns=["last_name", "iban", "city"], sort=[{"column": "last_name"}])})).json()
    rid = created["id"]

    own = (await client.post(f"/report-builder/reports/{rid}/run", headers=h["pay"], json={})).json()
    assert own["omitted_columns"] == [] and [c["key"] for c in own["columns"]] == ["last_name", "iban", "city"]
    hr = (await client.post(f"/report-builder/reports/{rid}/run", headers=h["hr"], json={})).json()
    assert hr["omitted_columns"] == ["IBAN"] and [c["key"] for c in hr["columns"]] == ["last_name", "city"]
    assert "DE89370400440532013000" not in str(hr)
    sup = (await client.post(f"/report-builder/reports/{rid}/run", headers=h["sup"], json={})).json()
    assert sup["omitted_columns"] == ["IBAN", "Ort"] and sup["rows"] == [["Alpha"], ["Leitung"]]
    csv_text = (await client.post(f"/report-builder/reports/{rid}/export", headers=h["sup"], json={})).content.decode("utf-8")
    assert csv_text[1:].split("\r\n")[:3] == ["Nachname", "Alpha", "Leitung"]
    runs = await audits(db_session, AuditAction.REPORT_RUN)
    assert runs[-1].entity_id == rid and "Bericht „Bank“" in runs[-1].detail and "2 Spalten ausgelassen" in runs[-1].detail
    assert (await audits(db_session, AuditAction.REPORT_EXPORTED))[-1].entity_id == rid

    # Filter auf einer nicht erlaubten Spalte: immer 403 (kein Rückschluss über den Filter)
    filtered = (await client.post("/report-builder/reports", headers=h["pay"], json={
        "name": "Filter", "shared": True, "definition": definition(columns=["last_name"], filters=[{"column": "iban", "operator": "starts_with", "value": "DE"}])})).json()
    response = await client.post(f"/report-builder/reports/{filtered['id']}/run", headers=h["hr"], json={})
    assert response.status_code == 403 and response.json()["code"] == "REPORT_COLUMN_FORBIDDEN"
    # keine Spalte sichtbar
    only = (await client.post("/report-builder/reports", headers=h["pay"], json={
        "name": "Nur Bank", "shared": True, "definition": definition(columns=["iban"])})).json()
    assert (await client.post(f"/report-builder/reports/{only['id']}/run", headers=h["hr"], json={})).status_code == 403


async def test_saved_time_report_needs_period_and_export_filename(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    h = world["headers"]
    rid = (await client.post("/report-builder/reports", headers=h["hr"], json={
        "name": "Krankheit Übersicht 2025/Q1", "definition": definition("absences", ["last_name", "days"])})).json()["id"]
    missing = await client.post(f"/report-builder/reports/{rid}/run", headers=h["hr"], json={})
    assert missing.status_code == 400 and missing.json()["code"] == "REPORT_PERIOD_REQUIRED"
    assert (await client.post(f"/report-builder/reports/{rid}/run", headers=h["hr"], json={"date_from": "2025-01-01"})).status_code == 422
    ok = await client.post(f"/report-builder/reports/{rid}/run", headers=h["hr"], json=PERIOD_JAN)
    assert ok.status_code == 200 and ok.json()["total_rows"] == 0
    export = await client.post(f"/report-builder/reports/{rid}/export", headers=h["hr"], json=PERIOD_JAN)
    assert export.headers["content-disposition"] == 'attachment; filename="Krankheit__bersicht_2025_Q1.csv"'


async def test_archived_attribute_column_is_omitted_when_running_saved_report(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    attributes = await _attributes(db_session, world)
    size = f"attr_{attributes['size'].id}"
    rid = (await client.post("/report-builder/reports", headers=world["headers"]["hr"], json={
        "name": "Größen", "definition": definition(columns=["last_name", size])})).json()["id"]
    attributes["size"].archived = True
    await db_session.commit()
    body = (await client.post(f"/report-builder/reports/{rid}/run", headers=world["headers"]["hr"], json={})).json()
    assert body["omitted_columns"] == ["Gelöschtes Feld"] and [c["key"] for c in body["columns"]] == ["last_name"]
    # beim Speichern dagegen: Fehler
    assert (await client.put(f"/report-builder/reports/{rid}", headers=world["headers"]["hr"], json={
        "name": "Größen", "definition": definition(columns=["last_name", size])})).status_code == 400


async def test_outdated_definition(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    hr_id = (await db_session.execute(select(Account.id).where(Account.email == "hr@example.com"))).scalar_one()
    report = SavedReport(tenant_id=1, owner_account_id=hr_id, name="Alt", definition='{"source": "salaries", "columns": ["x"]}')
    db_session.add(report)
    await db_session.commit()
    response = await client.get(f"/report-builder/reports/{report.id}", headers=world["headers"]["hr"])
    assert response.status_code == 409 and response.json()["code"] == "REPORT_DEFINITION_OUTDATED"
    assert (await client.post(f"/report-builder/reports/{report.id}/run", headers=world["headers"]["hr"], json={})).status_code == 409
    assert (await client.get("/report-builder/reports", headers=world["headers"]["hr"])).json() == []


async def test_reports_of_other_tenants_are_invisible(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    db_session.add(Tenant(id=2, subdomain="other", name="Other"))
    await db_session.flush()
    foreign = SavedReport(tenant_id=2, owner_account_id=None, name="Fremd", shared=True,
                          definition='{"source": "employees", "columns": ["last_name"]}')
    db_session.add(foreign)
    await db_session.commit()
    for role in ("admin", "hr"):
        assert (await client.get(f"/report-builder/reports/{foreign.id}", headers=world["headers"][role])).status_code == 404
        assert (await client.post(f"/report-builder/reports/{foreign.id}/run", headers=world["headers"][role], json={})).status_code == 404
        assert (await client.delete(f"/report-builder/reports/{foreign.id}", headers=world["headers"][role])).status_code == 404
        assert (await client.get("/report-builder/reports", headers=world["headers"][role])).json() == []
    assert (await db_session.get(SavedReport, foreign.id)) is not None


async def test_other_tenant_employees_never_appear(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    db_session.add(Tenant(id=2, subdomain="other", name="Other"))
    await db_session.flush()
    location = Location(tenant_id=2, name="Fremd", timezone="UTC")
    db_session.add(location)
    await db_session.flush()
    db_session.add(Employee(tenant_id=2, location_id=location.id, first_name="F", last_name="Fremd", employee_number="F1"))
    await db_session.commit()
    body = (await preview(client, world["headers"]["admin"], definition())).json()
    assert "Fremd" not in column(body, "last_name") and body["total_rows"] == 5


async def test_deleting_owner_account_keeps_report_for_admins(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    gone = Account(email="gone@example.com", password_hash=hash_password("pw"), role=HrRole.HR)
    db_session.add(gone)
    await db_session.flush()
    report = SavedReport(tenant_id=1, owner_account_id=gone.id, name="Verwaist", definition='{"source": "employees", "columns": ["last_name"]}')
    db_session.add(report)
    await db_session.commit()
    await db_session.delete(gone)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.owner_account_id is None
    listed = (await client.get("/report-builder/reports", headers=world["headers"]["admin"])).json()
    assert [(r["name"], r["owner_name"], r["can_edit"]) for r in listed] == [("Verwaist", None, True)]
    assert (await client.get("/report-builder/reports", headers=world["headers"]["hr"])).json() == []


async def test_owner_name_uses_linked_employee(client: AsyncClient, db_session: AsyncSession) -> None:
    world = await _world(db_session, client)
    created = (await client.post("/report-builder/reports", headers=world["headers"]["sup"], json={
        "name": "Mein Team", "definition": definition()})).json()
    assert created["owner_name"] == "Sam Leitung"
