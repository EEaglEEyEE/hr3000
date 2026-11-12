"""Kennzahlen über die Belegschaft: Abwesenheitsquote sowie Köpfe und Vollzeitstellen (FTE) je Monat.

Gerechnet wird in wenigen Sammelabfragen (Mitarbeitende, Fassungen der Arbeitszeit, Feiertage,
Abwesenheiten) und danach im Speicher – keine Abfrage je Mitarbeiter oder Tag.

Annahmen (auch in docs/technik.md):
- Soll-Arbeitstage sind die Tage laut Arbeitszeitmodell ohne Feiertage; ohne Modell und bei flexiblem
  Modell Mo–Fr, „nach Aufwand“ keine. Schnelle Näherung wie bei der Krankheitsquote der Fehlzeiten:
  Tagesausnahmen des Schichtplans und halbe Feiertage bleiben unberücksichtigt.
- Den Stand „aktiv“ gibt es nur für heute. Für frühere Monate zählt, wer laut Ein- und Austritt
  beschäftigt war; deaktivierte Mitarbeitende ohne Austrittsdatum zählen nirgends mit (ihr
  Ende ist unbekannt), anonymisierte ebenfalls nicht.
- Die Abteilung ist die heutige (Abteilungswechsel haben keinen Verlauf).
- Vollzeit sind die Wochenstunden des Standard-Arbeitszeitmodells aus den Einstellungen, sonst 40.
  „Nach Aufwand“ zählt als Kopf mit 0 FTE, ohne Arbeitszeitmodell als Vollzeit (1,0).
"""
import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    AppSettings,
    Department,
    Employee,
    EmployeeDefaultShift,
    Holiday,
    ShiftTemplate,
)
from app.models.shift_template import TargetPeriod
from app.services.holiday_service import location_scope
from app.services.shift_planning_service import version_target

FULL_TIME_FALLBACK_MINUTES = 40 * 60
HolidayScopes = dict[date, list[set[int] | None]]


# --- Bausteine (auch vom Berichts-Builder genutzt) ---------------------------------------------


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def months_between(first: date, last: date) -> list[tuple[int, int]]:
    """Alle Monate (Jahr, Monat), die der Zeitraum berührt."""
    months = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def full_time_week_minutes(settings_row: AppSettings | None) -> tuple[int, bool]:
    """(Wochenminuten einer Vollzeitstelle, aus den Einstellungen?) – Standard-Arbeitszeitmodell der
    Firma, sonst 40 Stunden."""
    raw = settings_row.default_day_minutes if settings_row is not None else None
    if raw:
        total = sum(int(value) for value in raw.split(","))
        if total > 0:
            return total, True
    return FULL_TIME_FALLBACK_MINUTES, False


def weekly_minutes(version: EmployeeDefaultShift, template: ShiftTemplate | None) -> int | None:
    """Wochenminuten einer Fassung der Arbeitszeit; None bei „nach Aufwand“ (kein festes Soll).
    Ein Monatssoll wird auf die Woche umgerechnet (× 12 / 52)."""
    if version.on_demand:
        return None
    total, period = version_target(version, template)
    if version.flexible:
        return total
    rotation = version.rotation_weeks
    if rotation is not None:
        # mehrwöchiges Modell: Durchschnitt über den Turnus
        return round(sum(sum(week) for week in rotation) / len(rotation))
    per_day = version.day_minutes_list
    if per_day is not None:
        return sum(per_day)
    if period == TargetPeriod.MONTHLY:
        return round(total * 12 / 52)
    if period == TargetPeriod.WEEKLY:
        return total
    return total * bin(version.weekdays_mask & 0x7F).count("1")


def version_on(versions: list[EmployeeDefaultShift], day: date) -> EmployeeDefaultShift | None:
    return next((v for v in versions if v.valid_from <= day and (v.valid_to is None or v.valid_to >= day)), None)


def fte_of(version: EmployeeDefaultShift | None, template: ShiftTemplate | None, full_time_minutes: int) -> float:
    """Vollzeitanteil: Wochenminuten / Vollzeit. Ohne Modell 1,0; „nach Aufwand“ 0."""
    if version is None:
        return 1.0
    minutes = weekly_minutes(version, template)
    if minutes is None:
        return 0.0
    return round(minutes / full_time_minutes, 4)


def is_planned_workday(versions: list[EmployeeDefaultShift], scopes: HolidayScopes, location_id: int, day: date) -> bool:
    """Soll-Arbeitstag laut Arbeitszeitmodell (siehe Modulkommentar)."""
    if any(scope is None or location_id in scope for scope in scopes.get(day, [])):
        return False
    version = version_on(versions, day)
    if version is None or version.flexible:
        return not (version is not None and version.on_demand) and day.weekday() < 5
    if version.on_demand:
        return False
    per_day = version.day_minutes_on(day)  # mehrwöchiges Modell: Turnus-Woche des Tages
    if per_day is not None:
        return per_day[day.weekday()] > 0
    return bool(version.weekdays_mask & (1 << day.weekday()))


def employed_on(employee: Employee, day: date) -> bool:
    """Laut Ein- und Austritt an diesem Tag beschäftigt (ohne Eintrittsdatum: von Anfang an)."""
    if employee.hire_date is not None and employee.hire_date > day:
        return False
    return employee.termination_date is None or employee.termination_date >= day


def counts_in_history(employee: Employee) -> bool:
    """Deaktiviert ohne Austrittsdatum: Ende unbekannt, zählt in keiner Monatsauswertung."""
    return employee.active or employee.termination_date is not None


def absence_day_weight(absence: Absence) -> float:
    """Ein Tag dieser Abwesenheit: 1, halber Tag 0,5; Stundenangaben sind keine Abwesenheitstage."""
    if absence.duration_minutes is not None:
        return 0.0
    return 0.5 if absence.half_day else 1.0


async def load_versions(db: AsyncSession, employee_ids: list[int], until: date) -> dict[int, list[EmployeeDefaultShift]]:
    """Fassungen der Arbeitszeit aller genannten Mitarbeitenden (eine Abfrage)."""
    grouped: dict[int, list[EmployeeDefaultShift]] = {employee_id: [] for employee_id in employee_ids}
    if not employee_ids:
        return grouped
    rows = await db.execute(
        select(EmployeeDefaultShift)
        .where(EmployeeDefaultShift.employee_id.in_(employee_ids), EmployeeDefaultShift.valid_from <= until)
        .order_by(EmployeeDefaultShift.valid_from)
    )
    for version in rows.scalars().all():
        grouped[version.employee_id].append(version)
    return grouped


async def load_templates(db: AsyncSession, tenant_id: int) -> dict[int, ShiftTemplate]:
    rows = await db.execute(select(ShiftTemplate).where(ShiftTemplate.tenant_id == tenant_id))
    return {template.id: template for template in rows.scalars().all()}


async def load_holiday_scopes(db: AsyncSession, tenant_id: int, first: date, last: date) -> HolidayScopes:
    rows = await db.execute(select(Holiday).where(Holiday.tenant_id == tenant_id, Holiday.date >= first, Holiday.date <= last))
    scopes: HolidayScopes = {}
    for holiday in rows.scalars().all():
        scopes.setdefault(holiday.date, []).append(location_scope(holiday))
    return scopes


async def load_department_names(db: AsyncSession, tenant_id: int) -> dict[int, str]:
    rows = await db.execute(select(Department.id, Department.name).where(Department.tenant_id == tenant_id))
    return {department_id: name for department_id, name in rows.all()}


async def _history_employees(db: AsyncSession, tenant_id: int) -> list[Employee]:
    rows = await db.execute(
        select(Employee)
        .where(Employee.tenant_id == tenant_id, Employee.anonymized_at.is_(None))
        .order_by(Employee.last_name, Employee.first_name)
    )
    return [employee for employee in rows.scalars().all() if counts_in_history(employee)]


# --- Abwesenheitsquote ---------------------------------------------------------------------------


@dataclass
class RateCell:
    absence_days: float = 0.0
    workdays: int = 0

    @property
    def rate_percent(self) -> float | None:
        return round(self.absence_days / self.workdays * 100, 2) if self.workdays else None


@dataclass
class AbsenceRate:
    months: dict[str, RateCell]
    total: RateCell
    # Abteilung (None = ohne Abteilung) -> Monat -> Zelle
    departments: dict[int | None, dict[str, RateCell]]
    department_names: dict[int, str]
    # bis zu diesem Tag gerechnet (heute, wenn der Zeitraum in die Zukunft reicht); None = nichts
    through: date | None


async def absence_rate(
    db: AsyncSession, tenant_id: int, first: date, last: date, categories: set[AbsenceType], today: date | None = None
) -> AbsenceRate:
    """Abwesenheitstage / Soll-Arbeitstage je Monat, gesamt und je Abteilung. Gezählt werden
    genehmigte Abwesenheiten der gewählten Kategorien an Soll-Arbeitstagen, höchstens bis heute
    (sonst stünden den Arbeitstagen künftiger Wochen noch keine Krankmeldungen gegenüber)."""
    today = today or date.today()
    keys = [month_key(*m) for m in months_between(first, last)]
    names = await load_department_names(db, tenant_id)
    months = {key: RateCell() for key in keys}
    departments: dict[int | None, dict[str, RateCell]] = {}
    upto = min(last, today)
    if upto < first:
        return AbsenceRate(months, RateCell(), departments, names, None)

    employees = await _history_employees(db, tenant_id)
    ids = [e.id for e in employees]
    versions = await load_versions(db, ids, upto)
    scopes = await load_holiday_scopes(db, tenant_id, first, upto)

    def cell(employee: Employee, day: date) -> tuple[RateCell, RateCell]:
        key = month_key(day.year, day.month)
        per_department = departments.setdefault(employee.department_id, {k: RateCell() for k in keys})
        return months[key], per_department[key]

    by_id = {e.id: e for e in employees}
    for employee in employees:
        day = first
        while day <= upto:
            if employed_on(employee, day) and is_planned_workday(versions[employee.id], scopes, employee.location_id, day):
                for target in cell(employee, day):
                    target.workdays += 1
            day += timedelta(days=1)

    if ids and categories:
        rows = await db.execute(
            select(Absence).where(
                Absence.employee_id.in_(ids),
                Absence.type.in_(categories),
                Absence.approval_status == AbsenceApprovalStatus.APPROVED,
                Absence.date_from <= upto,
                Absence.date_to >= first,
            )
        )
        for absence in rows.scalars().all():
            employee = by_id[absence.employee_id]
            weight = absence_day_weight(absence)
            day = max(absence.date_from, first)
            end = min(absence.date_to, upto)
            while weight and day <= end:
                if employed_on(employee, day) and is_planned_workday(versions[employee.id], scopes, employee.location_id, day):
                    for target in cell(employee, day):
                        target.absence_days += weight
                day += timedelta(days=1)

    total = RateCell(sum(c.absence_days for c in months.values()), sum(c.workdays for c in months.values()))
    return AbsenceRate(months, total, departments, names, upto)


# --- Köpfe und Vollzeitstellen -------------------------------------------------------------------


@dataclass
class HeadcountCell:
    headcount: int = 0
    fte: float = 0.0


@dataclass
class HeadcountMonth:
    month: str
    as_of: date
    total: HeadcountCell = field(default_factory=HeadcountCell)
    joiners: int = 0
    leavers: int = 0
    departments: dict[int | None, HeadcountCell] = field(default_factory=dict)


@dataclass
class Headcount:
    months: list[HeadcountMonth]
    department_names: dict[int, str]
    full_time_minutes: int
    full_time_from_settings: bool


async def headcount(db: AsyncSession, tenant_id: int, settings_row: AppSettings | None, first: date, last: date) -> Headcount:
    """Je Monatsende: beschäftigte Mitarbeitende (Köpfe) und ihre Vollzeitanteile, gesamt und je
    Abteilung; dazu Zugänge (Eintritt im Monat) und Abgänge (Austritt im Monat)."""
    full_time, from_settings = full_time_week_minutes(settings_row)
    employees = await _history_employees(db, tenant_id)
    versions = await load_versions(db, [e.id for e in employees], month_end(last.year, last.month))
    templates = await load_templates(db, tenant_id)
    months: list[HeadcountMonth] = []
    for year, month in months_between(first, last):
        start, end = date(year, month, 1), month_end(year, month)
        row = HeadcountMonth(month=month_key(year, month), as_of=end)
        for employee in employees:
            if employee.hire_date is not None and start <= employee.hire_date <= end:
                row.joiners += 1
            if employee.termination_date is not None and start <= employee.termination_date <= end:
                row.leavers += 1
            if not employed_on(employee, end):
                continue
            version = version_on(versions[employee.id], end)
            fte = fte_of(version, templates.get(version.shift_template_id) if version is not None else None, full_time)
            for target in (row.total, row.departments.setdefault(employee.department_id, HeadcountCell())):
                target.headcount += 1
                target.fte += fte
        months.append(row)
    return Headcount(months, await load_department_names(db, tenant_id), full_time, from_settings)
