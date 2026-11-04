from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Absence, AbsenceApprovalStatus, AbsenceType, Employee, EmployeeDefaultShift, LeaveEntitlement
from app.services.settings_service import get_or_create_settings


async def is_leave_day(db: AsyncSession, employee: Employee, day: date) -> bool:
    """Zählt ein Abwesenheitstag als Urlaubs-/Fehltag? Nur an Tagen, an denen der Mitarbeiter laut
    Arbeitszeitmodell/Schichtplan arbeiten würde (Teilzeit: z.B. nur Mo–Mi) und die kein Feiertag
    sind. Ohne jede Planung gilt wie bisher: Mo–Sa."""
    from app.services.shift_planning_service import resolve_effective_shift
    from app.services.timesheet_service import _is_holiday

    if await _is_holiday(db, employee, day):
        return False
    plan = await resolve_effective_shift(db, employee.id, day)
    if plan.flexible_weekly_minutes is not None:
        return day.weekday() < 5  # Aushilfe ohne feste Tage: Urlaubstage Mo–Fr
    if plan.plan_exists:
        return plan.is_workday and (plan.target_minutes or 0) > 0
    return day.weekday() != 6


async def vacation_days_between(db: AsyncSession, employee_id: int, start: date, end: date) -> float:
    """Verbrauchte Urlaubstage (genehmigte Abwesenheiten der Kategorie VACATION) im Zeitraum.
    Gezählt werden nur Arbeitstage des Mitarbeiters (siehe is_leave_day) – eine Teilzeitkraft mit
    3 Arbeitstagen verbraucht für eine ganze Urlaubswoche 3 Tage, nicht 5."""
    result = await db.execute(
        select(Absence).where(
            Absence.employee_id == employee_id,
            Absence.type == AbsenceType.VACATION,
            Absence.approval_status == AbsenceApprovalStatus.APPROVED,
            Absence.date_from <= end,
            Absence.date_to >= start,
        )
    )
    absences = result.scalars().all()
    if not absences:
        return 0.0

    employee = await db.get(Employee, employee_id)
    total_days = 0.0
    for absence in absences:
        current = max(absence.date_from, start)
        last = min(absence.date_to, end)
        while current <= last:
            if await is_leave_day(db, employee, current):
                total_days += 0.5 if absence.half_day else 1
            current += timedelta(days=1)
    return total_days


async def used_vacation_days(db: AsyncSession, employee_id: int, year: int) -> float:
    """Verbrauchte Urlaubstage im Kalenderjahr, nur APPROVED zählt gegen den Resturlaub."""
    return await vacation_days_between(db, employee_id, date(year, 1, 1), date(year, 12, 31))


@dataclass
class LeaveBalance:
    entitled_days: float
    carried_over_days: float
    # Übertrag automatisch aus dem Vorjahr berechnet (False = von HR eingetragen)
    carried_over_auto: bool
    used_days: float
    # Übertrag, der nach dem Stichtag nicht genommen war und deshalb verfallen ist
    expired_days: float
    # Übertrag, der zum Stichtag verfällt, wenn er bis dahin nicht genommen wird
    expiring_days: float
    expiry_date: date | None
    remaining_days: float


def _expiry_date(settings_row, year: int) -> date | None:
    if not settings_row.vacation_carry_over_expiry:
        return None
    month, day = (int(v) for v in settings_row.vacation_carry_over_expiry.split("-"))
    try:
        return date(year, month, day)
    except ValueError:  # 29.02. in Nicht-Schaltjahren
        return date(year, month, 28)


async def leave_balance(
    db: AsyncSession, employee_id: int, year: int, entitlement: LeaveEntitlement | None = None, *, _depth: int = 0
) -> LeaveBalance:
    """Urlaubskonto eines Jahres: Anspruch + Übertrag − Verfall − genommen.

    Automatischer Übertrag (Einstellung): Resturlaub des Vorjahres, höchstens die eingestellte
    Obergrenze – solange HR den Übertrag nicht selbst eingetragen hat. Verfall: übertragene Tage,
    die bis zum Stichtag (z.B. 31.03.) nicht genommen sind, verfallen danach; genommener Urlaub
    zählt zuerst gegen den Übertrag."""
    employee = await db.get(Employee, employee_id)
    settings_row = await get_or_create_settings(db, employee.tenant_id)
    if entitlement is None:
        entitlement = (
            await db.execute(
                select(LeaveEntitlement).where(LeaveEntitlement.employee_id == employee_id, LeaveEntitlement.year == year)
            )
        ).scalar_one_or_none()
    entitled = float(entitlement.entitled_days) if entitlement else float(settings_row.default_annual_vacation_days)
    used = await used_vacation_days(db, employee_id, year)

    auto = settings_row.vacation_carry_over_auto and not (entitlement is not None and entitlement.carried_over_manual)
    if auto:
        carried = 0.0
        previous_exists = (
            await db.execute(
                select(LeaveEntitlement.id).where(LeaveEntitlement.employee_id == employee_id, LeaveEntitlement.year == year - 1)
            )
        ).first() is not None
        if previous_exists and _depth < 10:
            previous = await leave_balance(db, employee_id, year - 1, _depth=_depth + 1)
            carried = max(0.0, previous.remaining_days)
            if settings_row.vacation_carry_over_max_days is not None:
                carried = min(carried, float(settings_row.vacation_carry_over_max_days))
    else:
        carried = float(entitlement.carried_over_days) if entitlement else 0.0

    expiry = _expiry_date(settings_row, year)
    expiring = expired = 0.0
    if expiry is not None and carried > 0:
        used_until_expiry = await vacation_days_between(db, employee_id, date(year, 1, 1), expiry)
        expiring = max(0.0, carried - used_until_expiry)
        if date.today() > expiry:
            expired, expiring = expiring, 0.0

    return LeaveBalance(
        entitled_days=entitled,
        carried_over_days=carried,
        carried_over_auto=auto,
        used_days=used,
        expired_days=expired,
        expiring_days=expiring,
        expiry_date=expiry if carried > 0 else None,
        remaining_days=entitled + carried - expired - used,
    )


def _workdays_of(default: EmployeeDefaultShift) -> int:
    if default.on_demand:
        return 0  # nach Aufwand: keine festen Arbeitstage, Urlaub legt HR fest
    if default.flexible:
        return 5  # flexibel: Urlaub in Tagen der 5-Tage-Woche, Gutschrift je Tag = Wochensoll / 5
    per_day = default.day_minutes_list
    if per_day is not None:
        return sum(1 for m in per_day if m > 0)
    return bin(default.weekdays_mask).count("1")


async def workdays_per_week(db: AsyncSession, employee_id: int, on: date) -> int | None:
    """Arbeitstage pro Woche laut Arbeitszeitmodell an einem Stichtag (None = kein Modell)."""
    rows = (
        await db.execute(
            select(EmployeeDefaultShift).where(
                EmployeeDefaultShift.employee_id == employee_id, EmployeeDefaultShift.valid_from <= on
            )
        )
    ).scalars().all()
    active = [d for d in rows if d.valid_to is None or d.valid_to >= on]
    return _workdays_of(active[0]) if active and not active[0].on_demand else None


async def suggested_entitlement(db: AsyncSession, employee_id: int, year: int, full_time_days: float) -> float | None:
    """Anteiliger Jahresurlaub für Teilzeit: Vollzeit-Anspruch (bezogen auf die 5-Tage-Woche) x
    Arbeitstage pro Woche / 5, bei Wechsel des Modells im Jahr tagesgenau gewichtet. Zeiten ohne
    Arbeitszeitmodell zählen wie Vollzeit. Auf halbe Tage gerundet."""
    first, last = date(year, 1, 1), date(year, 12, 31)
    days_in_year = (last - first).days + 1
    rows = (
        await db.execute(
            select(EmployeeDefaultShift).where(
                EmployeeDefaultShift.employee_id == employee_id,
                EmployeeDefaultShift.valid_from <= last,
            )
        )
    ).scalars().all()
    if any(d.on_demand and (d.valid_to is None or d.valid_to >= first) for d in rows):
        return None  # Aushilfe nach Aufwand: kein ableitbarer Anspruch, HR trägt ihn ein
    weighted = 0.0
    covered = 0
    for default in rows:
        start = max(default.valid_from, first)
        end = min(default.valid_to or last, last)
        if start > end:
            continue
        days = (end - start).days + 1
        covered += days
        weighted += days * _workdays_of(default) / 5
    factor = (weighted + (days_in_year - covered)) / days_in_year
    return round(full_time_days * factor * 2) / 2


async def get_or_create_entitlement(
    db: AsyncSession, employee_id: int, year: int, tenant_id: int
) -> LeaveEntitlement:
    """tenant_id wird nur für den Standardwert beim Erstanlegen gebraucht
    (AppSettings.default_annual_vacation_days) – ein bereits bestehender
    Eintrag wird nie nachträglich mit dem aktuellen Standard überschrieben."""
    result = await db.execute(
        select(LeaveEntitlement).where(
            LeaveEntitlement.employee_id == employee_id, LeaveEntitlement.year == year
        )
    )
    entitlement = result.scalar_one_or_none()
    if entitlement is None:
        settings_row = await get_or_create_settings(db, tenant_id)
        entitlement = LeaveEntitlement(
            employee_id=employee_id,
            year=year,
            # Teilzeit: anteilig nach Arbeitstagen pro Woche (Standardwert gilt für die 5-Tage-Woche),
            # sofern der Mandant das nicht abgeschaltet hat.
            entitled_days=(
                (await suggested_entitlement(db, employee_id, year, float(settings_row.default_annual_vacation_days)) or 0)
                if settings_row.prorate_part_time_vacation
                else settings_row.default_annual_vacation_days
            ),
        )
        db.add(entitlement)
        await db.commit()
        await db.refresh(entitlement)
    return entitlement
