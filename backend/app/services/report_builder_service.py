"""Berichts-Builder: Spalten je Konto, Rechteprüfung, Ausführung und CSV.

Ausführung ohne freies SQL: Je Datenquelle lädt ein Lader die benötigten Spalten in wenigen
Sammelabfragen (keine Abfrage je Zeile), danach wird in Python gefiltert, sortiert, gruppiert und
geblättert. Spaltenschlüssel werden nie in eine Abfrage eingesetzt, sondern nur gegen die
Positivliste (app/services/report_catalog.py) und den Attribut-Katalog der Firma geprüft.

Rechte (siehe docs/technik.md):
- Spalten mit Zugriff „hr“ nur für Admin/HR, „payroll“ nur mit Berechtigung „Vergütung & Lohn-Export“.
- Ad-hoc-Vorschau/-Export und Speichern mit einer nicht erlaubten Spalte: 403. Ein gespeicherter
  (geteilter) Bericht lässt beim Ausführen nicht erlaubte Ausgabespalten weg und meldet sie in
  ``omitted_columns``; Filter, Sortierung oder Gruppierung auf einer nicht erlaubten Spalte sind
  immer 403 (sonst ließe sich über den Filter auf den Inhalt schließen).
- Führungskräfte sehen in jedem Bericht nur Zeilen ihres Bereichs (scope_service).
"""
import csv
import io
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor
from app.errors import AppError
from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    AbsenceTypeDefinition,
    AppSettings,
    AttributeDefinition,
    AttributeSection,
    AttributeValue,
    BalanceAdjustment,
    Compensation,
    Employee,
    EmployeePersonalData,
    EmploymentContract,
    Location,
    OvertimeBalance,
    WorkTimeProfile,
)
from app.schemas.report_builder import (
    CatalogColumn,
    CatalogOperator,
    CatalogOption,
    CatalogResponse,
    CatalogSource,
    MAX_PAGE_SIZE,
    MAX_RANGE_DAYS,
    ReportDefinition,
    ReportGroup,
    ReportPeriod,
    ReportResult,
    ReportResultColumn,
)
from app.services import project_service
from app.services import report_catalog as catalog
from app.services import workforce_stats_service as stats
from app.services.attribute_service import current as current_attribute_value
from app.services.attribute_service import options_of
from app.services.leave_service import leave_balance
from app.services.org_service import load_org
from app.services.personal_data_service import mark_leave
from app.services.scope_service import visible_employee_ids
from app.services.secret_box import decrypt_secret
from app.services.settings_service import get_or_create_settings
from app.services.timesheet_service import ensure_balance_current

# Höchstzahl Zeilen eines Laufs (nach dem Filtern) – Vorschau blättert, die CSV enthält alle.
MAX_ROWS = 20_000

_ATTRIBUTE_TYPES = {
    "TEXT": catalog.TEXT,
    "NUMBER": catalog.NUMBER,
    "DATE": catalog.DATE,
    "SELECT": catalog.ENUM,
    "BOOLEAN": catalog.BOOL,
    "EMPLOYEE": catalog.TEXT,
}
ATTRIBUTE_GROUP = "Eigene Felder"

Row = dict[str, object]


# --- Schalter und Spalten -------------------------------------------------------------------------


async def ensure_enabled(db: AsyncSession, tenant_id: int) -> AppSettings:
    settings_row = await get_or_create_settings(db, tenant_id)
    if not settings_row.custom_reports_enabled:
        raise AppError(403, "FEATURE_DISABLED", "Eigene Berichte sind in den Einstellungen ausgeschaltet.")
    return settings_row


def can_use(actor: Actor, spec: catalog.ColumnSpec) -> bool:
    if spec.access == catalog.ACCESS_PAYROLL:
        return actor.has_payroll_access
    if spec.access == catalog.ACCESS_HR:
        return actor.is_full_hr_level
    return True


async def attribute_columns(db: AsyncSession, tenant_id: int) -> dict[str, tuple[catalog.ColumnSpec, AttributeDefinition]]:
    """Nicht archivierte eigene Felder (in nicht archivierten Bereichen) als Spalten ``attr_<id>``.
    Lesbar wie in der Personalakte nur für Admin/HR."""
    rows = await db.execute(
        select(AttributeDefinition)
        .join(AttributeSection, AttributeSection.id == AttributeDefinition.section_id)
        .where(
            AttributeDefinition.tenant_id == tenant_id,
            AttributeDefinition.archived.is_(False),
            AttributeSection.archived.is_(False),
        )
        .order_by(AttributeSection.sort_order, AttributeSection.id, AttributeDefinition.sort_order, AttributeDefinition.id)
    )
    result: dict[str, tuple[catalog.ColumnSpec, AttributeDefinition]] = {}
    for definition in rows.scalars().all():
        kind = _ATTRIBUTE_TYPES.get(definition.field_type, catalog.TEXT)
        options = tuple((o, o) for o in options_of(definition)) if kind == catalog.ENUM else ()
        spec = catalog.ColumnSpec(
            key=f"attr_{definition.id}",
            label=definition.label,
            type=kind,
            access=catalog.ACCESS_HR,
            options=options,
            summable=False,
            group=ATTRIBUTE_GROUP,
        )
        result[spec.key] = (spec, definition)
    return result


async def build_catalog(db: AsyncSession, actor: Actor) -> CatalogResponse:
    """Positivliste für dieses Konto: nur Spalten, die es sehen darf."""
    attributes = await attribute_columns(db, actor.tenant_id)
    projects_enabled = (await get_or_create_settings(db, actor.tenant_id)).project_times_enabled
    sources = []
    for key, label in catalog.SOURCES.items():
        if key == catalog.SOURCE_PROJECT_TIMES and not projects_enabled:
            continue
        specs = list(catalog.STATIC_COLUMNS[key].values())
        if key == catalog.SOURCE_EMPLOYEES:
            specs += [spec for spec, _ in attributes.values()]
        columns = [
            CatalogColumn(
                key=spec.key,
                label=spec.label,
                type=spec.type,
                group=spec.group,
                operators=list(spec.operators),
                options=[CatalogOption(value=v, label=l) for v, l in spec.options],
                summable=spec.summable,
            )
            for spec in specs
            if can_use(actor, spec)
        ]
        sources.append(CatalogSource(key=key, label=label, requires_period=key in catalog.TIME_BASED_SOURCES, columns=columns))
    return CatalogResponse(
        sources=sources,
        operators=[CatalogOperator(key=k, label=v) for k, v in catalog.OPERATOR_LABELS.items()],
        max_columns=catalog.MAX_COLUMNS,
        max_filters=catalog.MAX_FILTERS,
        max_sorts=catalog.MAX_SORTS,
        max_range_days=MAX_RANGE_DAYS,
        max_page_size=MAX_PAGE_SIZE,
    )


# --- Plan: geprüfte Definition --------------------------------------------------------------------


@dataclass
class Plan:
    source: str
    columns: list[catalog.ColumnSpec]
    omitted: list[str]
    filters: list[tuple[catalog.ColumnSpec, str, object]]
    sort: list[tuple[catalog.ColumnSpec, bool]]
    group: catalog.ColumnSpec | None
    attributes: dict[str, AttributeDefinition] = field(default_factory=dict)

    @property
    def needed(self) -> set[str]:
        keys = {c.key for c in self.columns} | {f[0].key for f in self.filters} | {s[0].key for s in self.sort}
        if self.group is not None:
            keys.add(self.group.key)
        return keys

    @property
    def shows_compensation(self) -> bool:
        return any(c.key in catalog.COMPENSATION_KEYS for c in self.columns)


async def resolve(db: AsyncSession, actor: Actor, definition: ReportDefinition, *, lenient: bool = False) -> Plan:
    """Prüft eine Definition für dieses Konto. ``lenient`` (gespeicherter Bericht ausführen): nicht
    erlaubte oder nicht mehr vorhandene Ausgabespalten werden weggelassen statt abgelehnt."""
    if definition.source == catalog.SOURCE_PROJECT_TIMES and not (await get_or_create_settings(db, actor.tenant_id)).project_times_enabled:
        raise AppError(400, "REPORT_SOURCE_DISABLED", "Projektzeiten sind in den Einstellungen ausgeschaltet.")
    available: dict[str, catalog.ColumnSpec] = dict(catalog.STATIC_COLUMNS[definition.source])
    attribute_defs: dict[str, AttributeDefinition] = {}
    if definition.source == catalog.SOURCE_EMPLOYEES:
        for key, (spec, attribute) in (await attribute_columns(db, actor.tenant_id)).items():
            available[key] = spec
            attribute_defs[key] = attribute

    def lookup(key: str) -> catalog.ColumnSpec:
        spec = available.get(key)
        if spec is None:
            raise AppError(400, "REPORT_COLUMN_UNKNOWN", f"Die Spalte „{key}“ gibt es nicht (mehr).")
        if not can_use(actor, spec):
            raise AppError(403, "REPORT_COLUMN_FORBIDDEN", f"Keine Berechtigung für die Spalte „{spec.label}“.")
        return spec

    columns: list[catalog.ColumnSpec] = []
    omitted: list[str] = []
    for key in definition.columns:
        spec = available.get(key)
        if lenient and (spec is None or not can_use(actor, spec)):
            omitted.append(spec.label if spec is not None else "Gelöschtes Feld")
            continue
        columns.append(lookup(key))
    if not columns:
        raise AppError(403, "REPORT_COLUMN_FORBIDDEN", "Keine Spalte dieses Berichts ist für Sie sichtbar.")

    filters = []
    for item in definition.filters:
        spec = lookup(item.column)
        try:
            value = catalog.normalize_filter_value(spec, item.operator, item.value)
        except ValueError as exc:
            raise AppError(422, "REPORT_FILTER_INVALID", str(exc)) from exc
        filters.append((spec, item.operator, value))
    sort = [(lookup(s.column), s.direction == "desc") for s in definition.sort]
    group = lookup(definition.group_by) if definition.group_by is not None else None
    plan = Plan(definition.source, columns, omitted, filters, sort, group)
    plan.attributes = {k: v for k, v in attribute_defs.items() if k in plan.needed}
    return plan


def resolve_period(source: str, period: ReportPeriod, today: date | None = None) -> tuple[date | None, date | None]:
    """Zeitraum eines Laufs: Pflicht bei zeitbezogenen Quellen; „Zeit je Monat“ auf ganze Monate
    erweitert. Bei „Mitarbeitende“ ohne Bedeutung."""
    if source not in catalog.TIME_BASED_SOURCES:
        return None, None
    if period.date_from is None or period.date_to is None:
        raise AppError(400, "REPORT_PERIOD_REQUIRED", "Bitte einen Zeitraum wählen.")
    if source == catalog.SOURCE_TIME_MONTHS:
        return date(period.date_from.year, period.date_from.month, 1), stats.month_end(period.date_to.year, period.date_to.month)
    return period.date_from, period.date_to


# --- Lader -----------------------------------------------------------------------------------------


@dataclass
class _Context:
    db: AsyncSession
    tenant_id: int
    settings_row: AppSettings
    plan: Plan
    today: date
    visible: set[int] | None


async def _base_employees(ctx: _Context) -> list[Employee]:
    stmt = select(Employee).where(Employee.tenant_id == ctx.tenant_id, Employee.anonymized_at.is_(None))
    if ctx.visible is not None:
        if not ctx.visible:
            return []
        stmt = stmt.where(Employee.id.in_(ctx.visible))
    rows = await ctx.db.execute(stmt.order_by(Employee.last_name, Employee.first_name, Employee.id))
    return list(rows.scalars().all())


async def _names(db: AsyncSession, model, tenant_id: int) -> dict[int, str]:
    rows = await db.execute(select(model.id, model.name).where(model.tenant_id == tenant_id))
    return {row_id: name for row_id, name in rows.all()}


async def _person_values(ctx: _Context, employees: list[Employee]) -> dict[int, Row]:
    needed = ctx.plan.needed
    departments = await stats.load_department_names(ctx.db, ctx.tenant_id) if "department" in needed else {}
    locations = await _names(ctx.db, Location, ctx.tenant_id) if "location" in needed else {}
    return {
        e.id: {
            "employee_number": e.employee_number,
            "last_name": e.last_name,
            "first_name": e.first_name,
            "department": departments.get(e.department_id) if e.department_id is not None else None,
            "location": locations.get(e.location_id),
        }
        for e in employees
    }


def _current(rows: list, today: date):
    """Gültige Zeile zum Stichtag (valid_from ≤ heute ≤ valid_to), die jüngste zuerst."""
    valid = [r for r in rows if r.valid_from <= today and (r.valid_to is None or r.valid_to >= today)]
    return max(valid, key=lambda r: (r.valid_from, r.id)) if valid else None


def _attribute_raw(definition: AttributeDefinition, value: str | None, names: dict[int, str]) -> object:
    if value is None:
        return None
    kind = definition.field_type
    try:
        if kind == "NUMBER":
            return float(Decimal(value))
        if kind == "DATE":
            return date.fromisoformat(value)
    except (InvalidOperation, ValueError):
        return None
    if kind == "BOOLEAN":
        return value == "true"
    if kind == "EMPLOYEE":
        return names.get(int(value)) if value.isdigit() else None
    return value


def model_name(version, templates: dict, profiles: dict[int, str]) -> str | None:
    """Anzeigename des Arbeitszeitmodells einer Fassung."""
    if version is None:
        return None
    if version.profile_id is not None and version.profile_id in profiles:
        return profiles[version.profile_id]
    if version.on_demand:
        return "Nach Aufwand"
    if version.flexible:
        return "Flexibel"
    template = templates.get(version.shift_template_id) if version.shift_template_id is not None else None
    if template is not None:
        return template.name
    return "Individuell"


async def load_employee_rows(ctx: _Context) -> list[Row]:
    db, needed, today = ctx.db, ctx.plan.needed, ctx.today
    employees = await _base_employees(ctx)
    if not employees:
        return []
    ids = [e.id for e in employees]
    rows = await _person_values(ctx, employees)

    names: dict[int, str] = {}
    if "supervisor" in needed or any(a.field_type == "EMPLOYEE" for a in ctx.plan.attributes.values()):
        result = await db.execute(select(Employee.id, Employee.first_name, Employee.last_name).where(Employee.tenant_id == ctx.tenant_id))
        names = {i: f"{first} {last}" for i, first, last in result.all()}
    org = await load_org(db, ctx.tenant_id) if "supervisor" in needed else None
    if "status" in needed:
        await mark_leave(db, employees, today)

    versions: dict[int, list] = {}
    templates: dict = {}
    profiles: dict[int, str] = {}
    full_time = stats.FULL_TIME_FALLBACK_MINUTES
    if needed & {"work_time_model", "weekly_hours", "fte"}:
        versions = await stats.load_versions(db, ids, today)
        templates = await stats.load_templates(db, ctx.tenant_id)
        profiles = await _names(db, WorkTimeProfile, ctx.tenant_id)
        full_time, _ = stats.full_time_week_minutes(ctx.settings_row)

    contracts: dict[int, list[EmploymentContract]] = {}
    if needed & {"contract_type", "probation_end", "fixed_term_end"}:
        result = await db.execute(select(EmploymentContract).where(EmploymentContract.employee_id.in_(ids)))
        for contract in result.scalars().all():
            contracts.setdefault(contract.employee_id, []).append(contract)

    compensations: dict[int, list[Compensation]] = {}
    if needed & catalog.COMPENSATION_KEYS:
        result = await db.execute(select(Compensation).where(Compensation.employee_id.in_(ids)))
        for compensation in result.scalars().all():
            compensations.setdefault(compensation.employee_id, []).append(compensation)

    personal: dict[int, dict] = {}
    if needed & catalog.PERSONAL_DATA_KEYS:
        result = await db.execute(select(EmployeePersonalData).where(EmployeePersonalData.employee_id.in_(ids)))
        for item in result.scalars().all():
            plain = decrypt_secret(item.data)
            personal[item.employee_id] = json.loads(plain) if plain else {}

    attribute_values: dict[tuple[int, int], list[AttributeValue]] = {}
    if ctx.plan.attributes:
        result = await db.execute(
            select(AttributeValue).where(
                AttributeValue.employee_id.in_(ids),
                AttributeValue.attribute_id.in_([a.id for a in ctx.plan.attributes.values()]),
            )
        )
        for value in result.scalars().all():
            attribute_values.setdefault((value.employee_id, value.attribute_id), []).append(value)

    result_rows: list[Row] = []
    for employee in employees:
        row = rows[employee.id]
        row.update(
            position=employee.position,
            hire_date=employee.hire_date,
            termination_date=employee.termination_date,
            birth_date=employee.birth_date,
        )
        if "status" in needed:
            row["status"] = employee.employment_status
        if org is not None:
            chain = [names[i] for i in org.supervisors(employee.id) if i in names]
            row["supervisor"] = ", ".join(chain) or None
        if versions:
            version = stats.version_on(versions.get(employee.id, []), today)
            template = templates.get(version.shift_template_id) if version is not None and version.shift_template_id else None
            row["work_time_model"] = model_name(version, templates, profiles)
            minutes = stats.weekly_minutes(version, template) if version is not None else None
            row["weekly_hours"] = round(minutes / 60, 2) if minutes is not None else None
            row["fte"] = stats.fte_of(version, template, full_time)
        contract = _current(contracts.get(employee.id, []), today)
        row["contract_type"] = contract.contract_type.value if contract is not None else None
        row["probation_end"] = contract.probation_end if contract is not None else None
        row["fixed_term_end"] = contract.fixed_term_end if contract is not None else None
        compensation = _current(compensations.get(employee.id, []), today)
        row["pay_type"] = compensation.pay_type.value if compensation is not None else None
        row["pay_amount"] = float(compensation.amount) if compensation is not None else None
        data = personal.get(employee.id, {})
        for key in catalog.PERSONAL_DATA_KEYS:
            value = data.get(key)
            row[key] = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value
        for key, attribute in ctx.plan.attributes.items():
            value = current_attribute_value(attribute_values.get((employee.id, attribute.id), []), today)
            row[key] = _attribute_raw(attribute, value.value if value is not None else None, names)
        result_rows.append(row)
    return result_rows


async def load_absence_rows(ctx: _Context, first: date, last: date) -> list[Row]:
    db, needed = ctx.db, ctx.plan.needed
    employees = await _base_employees(ctx)
    if not employees:
        return []
    by_id = {e.id: e for e in employees}
    persons = await _person_values(ctx, employees)
    result = await db.execute(
        select(Absence)
        .where(Absence.employee_id.in_(list(by_id)), Absence.date_from <= last, Absence.date_to >= first)
        .order_by(Absence.date_from, Absence.id)
    )
    absences = list(result.scalars().all())
    type_names: dict[int, str] = {}
    if "absence_type" in needed:
        type_names = {
            i: name
            for i, name in (
                await db.execute(select(AbsenceTypeDefinition.id, AbsenceTypeDefinition.name).where(AbsenceTypeDefinition.tenant_id == ctx.tenant_id))
            ).all()
        }
    versions: dict[int, list] = {}
    scopes: stats.HolidayScopes = {}
    if "days" in needed:
        versions = await stats.load_versions(db, list(by_id), last)
        scopes = await stats.load_holiday_scopes(db, ctx.tenant_id, first, last)
    category_labels = dict(catalog.ABSENCE_CATEGORY_LABELS)
    rows: list[Row] = []
    order = {e.id: index for index, e in enumerate(employees)}
    for absence in sorted(absences, key=lambda a: (order[a.employee_id], a.date_from, a.id)):
        employee = by_id[absence.employee_id]
        row: Row = dict(persons[employee.id])
        row.update(
            date_from=absence.date_from,
            date_to=absence.date_to,
            absence_type=type_names.get(absence.absence_type_id) if absence.absence_type_id in type_names else category_labels.get(absence.type.value),
            category=absence.type.value,
            half_day=bool(absence.half_day),
            approval_status=absence.approval_status.value,
            hours=round(absence.duration_minutes / 60, 2) if absence.duration_minutes is not None else None,
        )
        if "days" in needed:
            weight = stats.absence_day_weight(absence)
            days = 0.0
            day = max(absence.date_from, first)
            while weight and day <= min(absence.date_to, last):
                if stats.is_planned_workday(versions.get(employee.id, []), scopes, employee.location_id, day):
                    days += weight
                day += timedelta(days=1)
            row["days"] = days
        rows.append(row)
    return rows


async def load_project_rows(ctx: _Context, first: date, last: date) -> list[Row]:
    """Projektzeiten je Mitarbeiter und Projekt (services/project_service.project_times)."""
    times = await project_service.project_times(ctx.db, ctx.tenant_id, first, last, visible=ctx.visible)
    persons = await _person_values(ctx, list({t.employee.id: t.employee for t in times}.values()))
    rows: list[Row] = []
    for item in times:
        row: Row = dict(persons[item.employee.id])
        row.update(
            project=item.project.name,
            project_number=item.project.number,
            customer=item.customer.name if item.customer else None,
            billable=bool(item.project.billable),
            cost_center=f"{item.cost_center.code} {item.cost_center.name}" if item.cost_center else None,
            project_hours=round(item.minutes / 60, 2),
        )
        rows.append(row)
    return rows


async def load_time_month_rows(ctx: _Context, first: date, last: date) -> list[Row]:
    """Zeit je Monat aus dem Konto-Cache (overtime_balances): Soll/Ist/Saldo als Monatssummen,
    Kontostand zum Monatsende inkl. Korrekturbuchungen. Veraltete Konten werden vorher einmal je
    Mitarbeiter nachgerechnet (ensure_balance_current), nie Tag für Tag neu."""
    db, needed, today = ctx.db, ctx.plan.needed, ctx.today
    employees = await _base_employees(ctx)
    if not employees:
        return []
    ids = [e.id for e in employees]
    persons = await _person_values(ctx, employees)
    months = stats.months_between(first, last)

    balance_keys = {"target_hours", "actual_hours", "delta_hours", "balance_hours", "settled_hours"}
    month_end_settled: dict[tuple[int, int, int], int] = {}
    sums: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    month_end_balance: dict[tuple[int, int, int], int] = {}
    carry_in: dict[int, int] = {}
    adjustments: dict[int, list[tuple[date, int]]] = {}
    if needed & balance_keys:
        stale_before = min(last, today - timedelta(days=1))
        for employee in employees:
            if employee.balance_through is None or employee.balance_through < stale_before:
                await ensure_balance_current(db, employee)
        year_col = extract("year", OvertimeBalance.balance_date)
        month_col = extract("month", OvertimeBalance.balance_date)
        in_range = and_(OvertimeBalance.employee_id.in_(ids), OvertimeBalance.balance_date >= first, OvertimeBalance.balance_date <= last)
        result = await db.execute(
            select(
                OvertimeBalance.employee_id,
                year_col,
                month_col,
                func.sum(OvertimeBalance.daily_target_minutes),
                func.sum(OvertimeBalance.daily_actual_minutes),
                func.sum(OvertimeBalance.daily_delta_minutes),
                func.max(OvertimeBalance.balance_date),
            )
            .where(in_range)
            .group_by(OvertimeBalance.employee_id, year_col, month_col)
        )
        last_days: list[tuple[int, date]] = []
        for employee_id, year, month, target, actual, delta, last_day in result.all():
            sums[(employee_id, int(year), int(month))] = (int(target or 0), int(actual or 0), int(delta or 0))
            last_days.append((employee_id, last_day))
        if "settled_hours" in needed and last_days:
            # Abgeltung: Stand am letzten gerechneten Tag des Monats (läuft je Monat fort)
            wanted = {(e, d) for e, d in last_days}
            result = await db.execute(
                select(OvertimeBalance.employee_id, OvertimeBalance.balance_date, OvertimeBalance.settled_minutes).where(
                    in_range, OvertimeBalance.balance_date.in_(sorted({d for _, d in last_days}))
                )
            )
            for employee_id, day, settled in result.all():
                if (employee_id, day) in wanted:
                    month_end_settled[(employee_id, day.year, day.month)] = settled or 0
        if "balance_hours" in needed:
            # Kontostand am letzten gerechneten Tag je Monat …
            if last_days:
                wanted = {(e, d) for e, d in last_days}
                result = await db.execute(
                    select(OvertimeBalance.employee_id, OvertimeBalance.balance_date, OvertimeBalance.running_balance_minutes).where(
                        in_range, OvertimeBalance.balance_date.in_(sorted({d for _, d in last_days}))
                    )
                )
                for employee_id, day, running in result.all():
                    if (employee_id, day) in wanted:
                        month_end_balance[(employee_id, day.year, day.month)] = running
            # … und der Stand vor dem Zeitraum (für Monate ohne gerechnete Tage)
            before = (
                select(OvertimeBalance.employee_id, func.max(OvertimeBalance.balance_date).label("day"))
                .where(OvertimeBalance.employee_id.in_(ids), OvertimeBalance.balance_date < first)
                .group_by(OvertimeBalance.employee_id)
                .subquery()
            )
            result = await db.execute(
                select(OvertimeBalance.employee_id, OvertimeBalance.running_balance_minutes).join(
                    before, and_(OvertimeBalance.employee_id == before.c.employee_id, OvertimeBalance.balance_date == before.c.day)
                )
            )
            carry_in = {employee_id: running for employee_id, running in result.all()}
            result = await db.execute(
                select(BalanceAdjustment.employee_id, BalanceAdjustment.effective_date, BalanceAdjustment.minutes).where(
                    BalanceAdjustment.employee_id.in_(ids), BalanceAdjustment.effective_date <= last
                )
            )
            for employee_id, day, minutes in result.all():
                adjustments.setdefault(employee_id, []).append((day, minutes))

    vacation: dict[tuple[int, int, int], float] = {}
    if "vacation_taken" in needed:
        versions = await stats.load_versions(db, ids, last)
        scopes = await stats.load_holiday_scopes(db, ctx.tenant_id, first, last)
        by_id = {e.id: e for e in employees}
        result = await db.execute(
            select(Absence).where(
                Absence.employee_id.in_(ids),
                Absence.type == AbsenceType.VACATION,
                Absence.approval_status == AbsenceApprovalStatus.APPROVED,
                Absence.date_from <= last,
                Absence.date_to >= first,
            )
        )
        for absence in result.scalars().all():
            employee = by_id[absence.employee_id]
            weight = stats.absence_day_weight(absence)
            day = max(absence.date_from, first)
            while weight and day <= min(absence.date_to, last):
                if stats.is_planned_workday(versions.get(employee.id, []), scopes, employee.location_id, day):
                    key = (employee.id, day.year, day.month)
                    vacation[key] = vacation.get(key, 0.0) + weight
                day += timedelta(days=1)

    remaining: dict[tuple[int, int], float] = {}

    rows: list[Row] = []
    for employee in employees:
        running = carry_in.get(employee.id, 0)
        for year, month in months:
            start, end = date(year, month, 1), stats.month_end(year, month)
            key = (employee.id, year, month)
            employed = (employee.hire_date is None or employee.hire_date <= end) and (
                employee.termination_date is None or employee.termination_date >= start
            )
            has_data = key in sums or key in vacation
            if not has_data and not (employed and stats.counts_in_history(employee)):
                continue
            running = month_end_balance.get(key, running)
            row: Row = dict(persons[employee.id])
            target, actual, delta = sums.get(key, (0, 0, 0))
            row.update(
                month=stats.month_key(year, month),
                target_hours=round(target / 60, 2),
                actual_hours=round(actual / 60, 2),
                delta_hours=round(delta / 60, 2),
                settled_hours=round(month_end_settled.get(key, 0) / 60, 2),
                vacation_taken=vacation.get(key, 0.0),
            )
            if "balance_hours" in needed:
                adjusted = sum(minutes for day, minutes in adjustments.get(employee.id, []) if day <= end)
                row["balance_hours"] = round((running + adjusted) / 60, 2)
            if "vacation_remaining" in needed:
                # Urlaubskonto je Mitarbeiter und Jahr einmal (bewusste Ausnahme von „keine Abfrage
                # je Zeile“: die Kontoregeln mit Übertrag und Verfall gibt es nur je Person).
                if (employee.id, year) not in remaining:
                    remaining[(employee.id, year)] = (await leave_balance(db, employee.id, year)).remaining_days
                row["vacation_remaining"] = remaining[(employee.id, year)]
            rows.append(row)
    return rows


# --- Filtern, Sortieren, Gruppieren ---------------------------------------------------------------


def _fold(value: object) -> object:
    return value.casefold() if isinstance(value, str) else value


def matches(spec: catalog.ColumnSpec, operator: str, expected: object, raw: object) -> bool:
    empty = raw is None or raw == ""
    if operator == "is_empty":
        return empty
    if operator == "is_not_empty":
        return not empty
    if operator == "ne":
        return empty or _fold(raw) != _fold(expected)
    if empty:
        return False
    if operator == "eq":
        return _fold(raw) == _fold(expected)
    if operator == "in":
        return _fold(raw) in {_fold(item) for item in expected}
    if operator == "contains":
        return str(expected).casefold() in str(raw).casefold()
    if operator == "starts_with":
        return str(raw).casefold().startswith(str(expected).casefold())
    try:
        if operator == "gt":
            return raw > expected
        if operator == "gte":
            return raw >= expected
        if operator == "lt":
            return raw < expected
        if operator == "lte":
            return raw <= expected
    except TypeError:
        return False
    return False


def _sort_key(spec: catalog.ColumnSpec, raw: object) -> object:
    if spec.type == catalog.ENUM:
        return spec.option_label(raw).casefold()
    if isinstance(raw, str):
        return raw.casefold()
    return raw


def sort_rows(rows: list[Row], sorts: list[tuple[catalog.ColumnSpec, bool]]) -> list[Row]:
    """Stabile Mehrfachsortierung; leere Werte immer zuletzt."""
    for spec, descending in reversed(sorts):
        present = [r for r in rows if r.get(spec.key) not in (None, "")]
        absent = [r for r in rows if r.get(spec.key) in (None, "")]
        present.sort(key=lambda r: _sort_key(spec, r[spec.key]), reverse=descending)
        rows = present + absent
    return rows


def german_number(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".") if value != int(value) else str(int(value))
    return text.replace(".", ",")


def text_of(spec: catalog.ColumnSpec, raw: object) -> str:
    """Anzeige wie in der CSV: Datum TT.MM.JJJJ, Dezimalkomma, Ja/Nein, Auswahlwerte als Text."""
    if raw is None:
        return ""
    if spec.type == catalog.ENUM:
        return spec.option_label(str(raw))
    if isinstance(raw, bool):
        return "Ja" if raw else "Nein"
    if isinstance(raw, date):
        return raw.strftime("%d.%m.%Y")
    if isinstance(raw, (int, float)):
        return german_number(float(raw))
    return str(raw)


def cell_of(spec: catalog.ColumnSpec, raw: object) -> object:
    """Zelle der JSON-Antwort: Datum als JJJJ-MM-TT, Zahl auf 2 Stellen, Auswahlwerte als Text."""
    if raw is None or raw == "":
        return None
    if spec.type == catalog.ENUM:
        return spec.option_label(str(raw))
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, date):
        return raw.isoformat()
    if isinstance(raw, (int, float)):
        return round(float(raw), 2)
    return str(raw)


def _sums(columns: list[catalog.ColumnSpec], rows: list[Row]) -> dict[str, float]:
    return {
        spec.key: round(sum(float(r[spec.key]) for r in rows if isinstance(r.get(spec.key), (int, float))), 2)
        for spec in columns
        if spec.summable
    }


@dataclass
class Outcome:
    plan: Plan
    rows: list[Row]
    groups: list[tuple[str, list[Row]]]
    date_from: date | None
    date_to: date | None


async def execute(
    db: AsyncSession, actor: Actor, settings_row: AppSettings, plan: Plan, period: ReportPeriod, today: date | None = None
) -> Outcome:
    first, last = resolve_period(plan.source, period, today)
    ctx = _Context(db, actor.tenant_id, settings_row, plan, today or date.today(), await visible_employee_ids(db, actor))
    if plan.source == catalog.SOURCE_EMPLOYEES:
        rows = await load_employee_rows(ctx)
    elif plan.source == catalog.SOURCE_ABSENCES:
        rows = await load_absence_rows(ctx, first, last)
    elif plan.source == catalog.SOURCE_PROJECT_TIMES:
        rows = await load_project_rows(ctx, first, last)
    else:
        rows = await load_time_month_rows(ctx, first, last)
    for spec, operator, expected in plan.filters:
        rows = [r for r in rows if matches(spec, operator, expected, r.get(spec.key))]
    if len(rows) > MAX_ROWS:
        raise AppError(400, "RESULT_TOO_LARGE", f"Der Bericht hätte mehr als {MAX_ROWS:,} Zeilen – bitte filtern oder den Zeitraum verkürzen.".replace(",", "."))
    sorts = list(plan.sort)
    if plan.group is not None:
        sorts = [(plan.group, False), *[s for s in sorts if s[0].key != plan.group.key]]
    rows = sort_rows(rows, sorts)
    groups: list[tuple[str, list[Row]]] = []
    if plan.group is not None:
        for row in rows:
            label = text_of(plan.group, row.get(plan.group.key))
            if groups and groups[-1][0] == label:
                groups[-1][1].append(row)
            else:
                groups.append((label, [row]))
    return Outcome(plan, rows, groups, first, last)


def to_result(outcome: Outcome, period: ReportPeriod) -> ReportResult:
    plan = outcome.plan
    start = (period.page - 1) * period.page_size
    page_rows = outcome.rows[start : start + period.page_size]
    return ReportResult(
        columns=[ReportResultColumn(key=c.key, label=c.label, type=c.type, summable=c.summable) for c in plan.columns],
        rows=[[cell_of(c, r.get(c.key)) for c in plan.columns] for r in page_rows],
        total_rows=len(outcome.rows),
        page=period.page,
        page_size=period.page_size,
        totals=_sums(plan.columns, outcome.rows),
        group_by=plan.group.key if plan.group is not None else None,
        group_by_label=plan.group.label if plan.group is not None else None,
        groups=[ReportGroup(label=label, count=len(rows), sums=_sums(plan.columns, rows)) for label, rows in outcome.groups],
        omitted_columns=plan.omitted,
        date_from=outcome.date_from,
        date_to=outcome.date_to,
    )


# --- CSV ------------------------------------------------------------------------------------------


def csv_safe(value: str) -> str:
    """Schutz vor CSV-/Formel-Injektion wie im Lohn-Export (app/api/payroll_export._csv_text)."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _csv_cell(spec: catalog.ColumnSpec, raw: object) -> str:
    text = text_of(spec, raw)
    # Zahlen und Datumswerte erzeugt das System selbst; nur Text kann eine Formel enthalten.
    if spec.type in (catalog.TEXT, catalog.ENUM) and isinstance(raw, str):
        return csv_safe(text)
    return text


def to_csv(outcome: Outcome) -> str:
    """UTF-8 mit BOM, Semikolon, Dezimalkomma – wie der Lohn-Export. Bei Gruppierung folgt nach den
    Zeilen ein Block mit Anzahl und Summen je Gruppe und gesamt."""
    columns = outcome.plan.columns
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow([csv_safe(c.label) for c in columns])
    for row in outcome.rows:
        writer.writerow([_csv_cell(c, row.get(c.key)) for c in columns])
    summable = [c for c in columns if c.summable]
    if outcome.plan.group is not None or summable:
        writer.writerow([])
        writer.writerow([csv_safe(outcome.plan.group.label) if outcome.plan.group else "", "Anzahl", *[csv_safe(c.label) for c in summable]])
        for label, rows in outcome.groups:
            sums = _sums(summable, rows)
            writer.writerow([csv_safe(label) or "(leer)", str(len(rows)), *[german_number(sums[c.key]) for c in summable]])
        totals = _sums(summable, outcome.rows)
        writer.writerow(["Gesamt", str(len(outcome.rows)), *[german_number(totals[c.key]) for c in summable]])
    return "﻿" + buffer.getvalue()


def audit_detail(outcome: Outcome, name: str | None = None) -> str:
    """Protokolltext ohne Inhalte: Quelle, Spaltenzahl, Zeilenzahl, Zeitraum."""
    parts = [f"Bericht „{name}“" if name else "Ad-hoc-Bericht", f"Quelle {catalog.SOURCES[outcome.plan.source]}"]
    parts.append(f"{len(outcome.plan.columns)} Spalten, {len(outcome.rows)} Zeilen")
    if outcome.date_from is not None and outcome.date_to is not None:
        parts.append(f"Zeitraum {outcome.date_from:%d.%m.%Y}–{outcome.date_to:%d.%m.%Y}")
    if outcome.plan.omitted:
        parts.append(f"{len(outcome.plan.omitted)} Spalten ausgelassen")
    return ", ".join(parts)[:500]
