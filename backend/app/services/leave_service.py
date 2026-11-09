import calendar
import math
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    Employee,
    EmployeeDefaultShift,
    EmploymentContract,
    LeaveAdjustment,
    LeaveEntitlement,
)
from app.services.settings_service import get_or_create_settings


async def is_leave_day(db: AsyncSession, employee: Employee, day: date) -> bool:
    """Zählt ein Abwesenheitstag als Urlaubs-/Fehltag? Nur an Tagen, an denen der Mitarbeiter laut
    Arbeitszeitmodell/Schichtplan arbeiten würde (Teilzeit: z.B. nur Mo–Mi) und die kein Feiertag
    sind. Ohne feste Tage (flexibel, nach Aufwand) und ohne jede Planung: Mo–Fr – passend zum
    Urlaubsanspruch, der sich auf die 5-Tage-Woche bezieht."""
    from app.services.shift_planning_service import resolve_effective_shift
    from app.services.timesheet_service import _is_holiday

    if await _is_holiday(db, employee, day):
        return False
    plan = await resolve_effective_shift(db, employee.id, day)
    if plan.plan_exists and plan.flexible_weekly_minutes is None:
        return plan.is_workday and (plan.target_minutes or 0) > 0
    return day.weekday() < 5


async def leave_day_weight(db: AsyncSession, employee: Employee, day: date) -> float:
    """Wie viel ein ganzer Abwesenheitstag an diesem Tag zählt: 1, an einem halben Feiertag 0,5,
    an Tagen ohne Arbeitspflicht (siehe is_leave_day) 0."""
    from app.services.timesheet_service import _half_holiday

    if not await is_leave_day(db, employee, day):
        return 0.0
    return 0.5 if await _half_holiday(db, employee, day) else 1.0


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
            weight = await leave_day_weight(db, employee, current)
            total_days += weight * (0.5 if absence.half_day else 1)
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
    # Summe der Korrekturen (LeaveAdjustment) des Jahres, auch verfallene
    adjustment_days: float = 0.0


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
    if entitlement is not None and entitlement.entitled_manual:
        entitled = float(entitlement.entitled_days)
    else:
        computed = await computed_entitlement(db, employee, year)
        entitled = computed if computed is not None else (float(entitlement.entitled_days) if entitlement else 0.0)
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
    adjustments = (
        await db.execute(select(LeaveAdjustment).where(LeaveAdjustment.employee_id == employee_id, LeaveAdjustment.year == year))
    ).scalars().all()
    adjustment_days = sum(float(a.days) for a in adjustments)
    # Verfallende Töpfe – Übertrag und positive Korrekturen mit Verfallsdatum – in der Reihenfolge
    # ihres Verfalls: genommener Urlaub bis zum jeweiligen Stichtag zählt zuerst gegen den frühesten.
    pools: list[tuple[date, float, bool]] = []
    if expiry is not None and carried > 0:
        pools.append((expiry, carried, True))
    pools += [(a.expires_on, float(a.days), False) for a in adjustments if a.expires_on is not None and float(a.days) > 0]
    pools.sort(key=lambda pool: pool[0])
    expiring = expired = 0.0
    consumed = 0.0
    for when, amount, is_carry in pools:
        used_until = await vacation_days_between(db, employee_id, date(year, 1, 1), when)
        take = min(amount, max(0.0, used_until - consumed))
        consumed += take
        leftover = amount - take
        if date.today() > when:
            expired += leftover
        elif is_carry:
            expiring = leftover

    return LeaveBalance(
        entitled_days=entitled,
        carried_over_days=carried,
        carried_over_auto=auto,
        used_days=used,
        expired_days=expired,
        expiring_days=expiring,
        expiry_date=expiry if carried > 0 else None,
        remaining_days=entitled + carried + adjustment_days - expired - used,
        adjustment_days=adjustment_days,
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


# § 3 BUrlG: 24 Werktage (6-Tage-Woche) = 20 Arbeitstage bei der 5-Tage-Woche
STATUTORY_DAYS_5 = 20.0


def round_vacation(days: float) -> float:
    """Nie zu Lasten des Mitarbeiters runden: Bruchteile ab einem halben Tag auf volle Tage (§ 5
    Abs. 2 BUrlG), kleinere auf den nächsten halben Tag."""
    whole = math.floor(days + 1e-9)
    fraction = days - whole
    if fraction < 1e-6:
        return float(whole)
    return whole + 1.0 if fraction >= 0.5 - 1e-6 else whole + 0.5


async def annual_vacation_base(db: AsyncSession, employee: Employee, on: date, default: float) -> float:
    """Jahresurlaub laut Vertragsabschnitt an diesem Tag, sonst Standard der Firma."""
    contracts = (
        await db.execute(
            select(EmploymentContract).where(EmploymentContract.employee_id == employee.id, EmploymentContract.valid_from <= on)
        )
    ).scalars().all()
    current = [c for c in contracts if (c.valid_to is None or c.valid_to >= on) and c.annual_vacation_days is not None]
    return float(max(current, key=lambda c: c.valid_from).annual_vacation_days) if current else default


def waiting_period_end(hire: date) -> date:
    """Letzter Tag der sechsmonatigen Wartezeit (§ 4 BUrlG, Fristende nach § 188 BGB)."""
    index = hire.month - 1 + 6
    year, month = hire.year + index // 12, index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day) if hire.day > last_day else date(year, month, hire.day) - timedelta(days=1)


def full_statutory_leave(employee: Employee, year: int) -> bool:
    """Voller gesetzlicher Urlaub im Jahr (§ 5 Abs. 1 BUrlG): Wartezeit spätestens in diesem Jahr
    erfüllt, nicht vor ihrem Ende ausgeschieden und kein Austritt im ersten Halbjahr."""
    waiting_end = waiting_period_end(employee.hire_date) if employee.hire_date else None
    termination = employee.termination_date
    return (
        (waiting_end is None or waiting_end <= date(year, 12, 31))
        and (termination is None or waiting_end is None or termination >= waiting_end)
        and (termination is None or termination > date(year, 6, 30))
    )


async def computed_entitlement(db: AsyncSession, employee: Employee, year: int) -> float | None:
    """Anspruch eines Jahres aus dem Jahresurlaub laut Vertrag (bzw. Firmenstandard, bezogen auf die
    5-Tage-Woche), tagesgenau anteilig für Teilzeit (Arbeitstage je Woche ÷ 5) und für Ein- und
    Austritt im Jahr (Teilurlaub) – beides je nach Einstellung. Beim Teilurlaub bleibt der
    gesetzliche Mindesturlaub erhalten, wenn er voll zusteht (full_statutory_leave). Ohne
    hinterlegten Jahresurlaub (Standard 0) bleibt es bei 0. None = nach Aufwand (kein ableitbarer
    Anspruch, HR trägt ihn ein)."""
    settings_row = await get_or_create_settings(db, employee.tenant_id)
    default = float(settings_row.default_annual_vacation_days or 0)
    first, last = date(year, 1, 1), date(year, 12, 31)
    employed_from = max(first, employee.hire_date or first)
    employed_to = min(last, employee.termination_date or last)
    if employed_from > employed_to:
        return 0.0  # im ganzen Jahr nicht beschäftigt
    partial = settings_row.prorate_partial_year_vacation
    # Ohne Teilurlaub zählt das ganze Jahr (wie bisher), sonst nur die Beschäftigungszeit.
    start, end = (employed_from, employed_to) if partial else (first, last)
    versions = (
        await db.execute(
            select(EmployeeDefaultShift).where(
                EmployeeDefaultShift.employee_id == employee.id, EmployeeDefaultShift.valid_from <= end
            )
        )
    ).scalars().all()
    versions = [v for v in versions if v.valid_to is None or v.valid_to >= start]
    if settings_row.prorate_part_time_vacation and any(v.on_demand for v in versions):
        # Aushilfe nach Aufwand: kein ableitbarer Anteil, HR trägt den Anspruch ein. Ohne
        # Teilzeit-Anteil gilt (wie bisher) der volle Jahresurlaub.
        return None
    contracts = (
        await db.execute(
            select(EmploymentContract).where(EmploymentContract.employee_id == employee.id, EmploymentContract.valid_from <= end)
        )
    ).scalars().all()
    days_in_year = (last - first).days + 1
    extra = seniority_extra_days(settings_row.seniority_leave_rules, employee.hire_date, year)
    total = 0.0
    factor_sum = 0.0
    employed_days = 0
    day = start
    while day <= end:
        version = next((v for v in versions if v.valid_from <= day and (v.valid_to is None or v.valid_to >= day)), None)
        factor = _workdays_of(version) / 5 if version is not None and settings_row.prorate_part_time_vacation else 1.0
        contract = max(
            (c for c in contracts if c.valid_from <= day and (c.valid_to is None or c.valid_to >= day) and c.annual_vacation_days is not None),
            key=lambda c: c.valid_from,
            default=None,
        )
        base = float(contract.annual_vacation_days) if contract is not None else default
        if base > 0:
            base += extra  # Zusatzurlaub nach Betriebszugehörigkeit (nur mit hinterlegtem Jahresurlaub)
        total += base * factor / days_in_year
        factor_sum += factor
        employed_days += 1
        day += timedelta(days=1)
    if partial and total > 0 and employed_days and full_statutory_leave(employee, year):
        # gesetzlicher Mindesturlaub für das ganze Jahr (bei Teilzeit anteilig) – nur, wenn überhaupt
        # ein Jahresurlaub hinterlegt ist (Standard 0 = HR trägt den Anspruch selbst ein)
        total = max(total, STATUTORY_DAYS_5 * factor_sum / employed_days)
    if settings_row.reduce_vacation_parental_leave and total > 0:
        # § 17 BEEG: je vollem Kalendermonat Elternzeit 1/12 des Jahresurlaubs (auch des gesetzlichen).
        months = await full_parental_leave_months(db, employee.id, year)
        if months:
            yearly = total * days_in_year / max(1, (end - start).days + 1) if partial else total
            total = max(0.0, total - yearly * months / 12)
    return round_vacation(total)


def seniority_extra_days(rules: str | None, hire_date: date | None, year: int) -> float:
    """Zusatzurlaub (Tage, 5-Tage-Woche) der höchsten Stufe, deren Jahre im Kalenderjahr vollendet
    werden – z. B. "5:1,10:2", Eintritt 01.08.2020: ab 2025 +1, ab 2030 +2."""
    if not rules or hire_date is None:
        return 0.0
    completed = year - hire_date.year  # im Lauf des Jahres vollendete Jahre
    extra = 0.0
    for part in rules.split(","):
        years, days = part.split(":", 1)
        if completed >= int(years):
            extra = float(days)
    return extra


async def full_parental_leave_months(db: AsyncSession, employee_id: int, year: int) -> int:
    """Volle Kalendermonate des Jahres, die ganz von genehmigter Elternzeit (Kategorie
    „Mutterschutz/Elternzeit“) abgedeckt sind."""
    absences = (
        await db.execute(
            select(Absence.date_from, Absence.date_to).where(
                Absence.employee_id == employee_id,
                Absence.type == AbsenceType.PARENTAL_LEAVE,
                Absence.approval_status == AbsenceApprovalStatus.APPROVED,
                Absence.date_from <= date(year, 12, 31),
                Absence.date_to >= date(year, 1, 1),
            )
        )
    ).all()
    covered = set()
    for date_from, date_to in absences:
        day = max(date_from, date(year, 1, 1))
        while day <= min(date_to, date(year, 12, 31)):
            covered.add(day)
            day += timedelta(days=1)
    months = 0
    for month in range(1, 13):
        last_day = calendar.monthrange(year, month)[1]
        if all(date(year, month, d) in covered for d in range(1, last_day + 1)):
            months += 1
    return months


async def suggested_entitlement(db: AsyncSession, employee_id: int, year: int, full_time_days: float | None = None) -> float | None:
    """Kompatibilität: berechneter Anspruch (siehe computed_entitlement)."""
    employee = await db.get(Employee, employee_id)
    return await computed_entitlement(db, employee, year) if employee is not None else None


async def get_or_create_entitlement(
    db: AsyncSession, employee_id: int, year: int, tenant_id: int
) -> LeaveEntitlement:
    """Konto-Eintrag eines Jahres (für Übertrag und fest eingetragenen Anspruch). Der Anspruch selbst
    wird berechnet, solange er nicht fest eingetragen ist (entitled_manual)."""
    result = await db.execute(
        select(LeaveEntitlement).where(
            LeaveEntitlement.employee_id == employee_id, LeaveEntitlement.year == year
        )
    )
    entitlement = result.scalar_one_or_none()
    if entitlement is None:
        # Anspruch wird berechnet (entitled_manual False); gespeichert wird der Stand beim Anlegen.
        entitlement = LeaveEntitlement(
            employee_id=employee_id,
            year=year,
            entitled_days=await suggested_entitlement(db, employee_id, year) or 0,
            entitled_manual=False,
        )
        db.add(entitlement)
        await db.commit()
        await db.refresh(entitlement)
    return entitlement
