from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import AppSettings, Employee, EmployeeDefaultShift, ShiftPlanEntry, ShiftTemplate, TargetPeriod

REST_PERIOD_MINUTES = 11 * 60
# ArbZG §3: harte Obergrenze, die nie überschritten werden darf (unabhängig
# von einem sonst möglichen Ausgleich) – siehe check_max_daily_working_time.
MAX_DAILY_WORKING_MINUTES = 10 * 60


@dataclass
class EffectiveDayPlan:
    # False nur, wenn TATSÄCHLICH eine Planung existiert und "kein
    # Arbeitstag" sagt (expliziter freier Tag oder Wochentag außerhalb der
    # Default-Maske) – siehe plan_exists.
    is_workday: bool
    # Ob überhaupt eine Schichtplanung für diesen Mitarbeiter/Tag existiert
    # (ShiftPlanEntry ODER greifender EmployeeDefaultShift). Wenn False, ist
    # der Tag schlicht unkonfiguriert – calculate_day behandelt das wie
    # bisher ohne WorkTimeModel (normales Stempeln, kein Soll), NICHT wie
    # einen expliziten freien Tag (PLANNED_OFF). Das erhält das Verhalten
    # für Mitarbeiter/Mandanten, die noch keine Schichtplanung eingerichtet
    # haben.
    plan_exists: bool
    target_minutes: int | None
    shift_template_id: int | None
    start_time: time | None
    end_time: time | None
    # Ob dieser Tag durch eine explizite ShiftPlanEntry-Ausnahme bestimmt
    # wird (True) oder durch den EmployeeDefaultShift/unkonfiguriert (False)
    # – für die Kalenderansicht: nur Ausnahme-Tage sind per Drag&Drop
    # verschiebbar, siehe app/api/shift_plan_entries.py list_effective_shifts.
    from_entry: bool
    # Flexibles Modell: Wochensoll ohne feste Tage (Tagessoll None, Abrechnung je Woche).
    flexible_weekly_minutes: int | None = None
    # Nach Aufwand: Stempelungen zählen als Ist, es gibt kein Soll (wie ohne Planung, aber gewollt).
    on_demand: bool = False


_UNCONFIGURED = EffectiveDayPlan(True, False, None, None, None, None, False)


def _distribute_period_minutes(total_minutes: int, rank: int, count: int) -> int:
    """Verteilt total_minutes gleichmäßig auf `count` Vorkommen – die ersten
    `total_minutes % count` (nach `rank` sortiert) bekommen eine Minute mehr,
    damit die Summe exakt total_minutes ergibt (keine Rundungsdrift)."""
    if count == 0:
        return 0
    base, remainder = divmod(total_minutes, count)
    return base + (1 if rank < remainder else 0)


def _weekday_rank_in_mask(weekday: int, weekdays_mask: int) -> tuple[int, int]:
    """0-indexierter Rang von `weekday` (0=Montag) unter den in
    weekdays_mask gesetzten Wochentagen (Mo->So-Reihenfolge) sowie deren
    Gesamtzahl. Für WEEKLY-Vorlagen: hängt nur von der Maske ab, nicht vom
    konkreten Kalenderdatum, da sich die Wochenmaske jede Woche identisch
    wiederholt."""
    count = bin(weekdays_mask).count("1")
    rank = bin(weekdays_mask & ((1 << weekday) - 1)).count("1")
    return rank, count


def _weekday_rank_in_month(work_date: date, weekdays_mask: int) -> tuple[int, int]:
    """0-indexierter Rang von `work_date` unter allen Tagen desselben
    Kalendermonats, deren Wochentag in weekdays_mask gesetzt ist, sowie
    deren Gesamtzahl in diesem Monat. Bewusste Vereinfachung: zählt den
    ganzen Kalendermonat, unabhängig von valid_from/valid_to der
    konkreten EmployeeDefaultShift-Zuordnung – ein Monatssoll ist als Wert
    pro Kalendermonat gedacht, nicht anteilig zur Zuordnungsdauer."""
    first_of_month = work_date.replace(day=1)
    if work_date.month == 12:
        next_month = work_date.replace(year=work_date.year + 1, month=1, day=1)
    else:
        next_month = work_date.replace(month=work_date.month + 1, day=1)
    matching_days = []
    current = first_of_month
    while current < next_month:
        if (1 << current.weekday()) & weekdays_mask:
            matching_days.append(current)
        current += timedelta(days=1)
    return matching_days.index(work_date), len(matching_days)


def _resolve_target_minutes(template: ShiftTemplate, work_date: date, weekdays_mask: int) -> int:
    """target_minutes eines EmployeeDefaultShift-Tages, abhängig vom
    Bezugszeitraum der Vorlage (siehe TargetPeriod) – DAILY unverändert,
    WEEKLY/MONTHLY verteilen den Vorlagenwert gleichmäßig auf die
    zutreffenden Wochentage."""
    if template.target_period == TargetPeriod.WEEKLY:
        rank, count = _weekday_rank_in_mask(work_date.weekday(), weekdays_mask)
    elif template.target_period == TargetPeriod.MONTHLY:
        rank, count = _weekday_rank_in_month(work_date, weekdays_mask)
    else:
        return template.target_minutes
    return _distribute_period_minutes(template.target_minutes, rank, count)


async def shift_planning_enabled_for_employee(db: AsyncSession, employee_id: int) -> bool:
    """Ob der Mandant des Mitarbeiters die Schichtplanung aktiviert hat
    (AppSettings.shift_planning_enabled). Ohne Einstellungszeile gilt: aus."""
    result = await db.execute(
        select(AppSettings.shift_planning_enabled)
        .join(Employee, Employee.tenant_id == AppSettings.tenant_id)
        .where(Employee.id == employee_id)
    )
    return bool(result.scalar_one_or_none())


async def resolve_effective_shift(db: AsyncSession, employee_id: int, work_date: date) -> EffectiveDayPlan:
    """Zentrale Auflösung der Tagesplanung: ShiftPlanEntry für das exakte
    Datum falls vorhanden, sonst der zu diesem Wochentag passende
    EmployeeDefaultShift, sonst "unkonfiguriert" (siehe plan_exists oben).
    Wird von calculate_day UND von den Ruhezeit-Prüfungen unten verwendet –
    eine Auflösung, keine drei Kopien der Logik."""
    entry = None
    # Tagesausnahmen/Dienstplan-Einträge wirken nur bei aktivierter Schichtplanung;
    # bereits gespeicherte bleiben erhalten, werden aber ignoriert, solange aus.
    if await shift_planning_enabled_for_employee(db, employee_id):
        result = await db.execute(
            select(ShiftPlanEntry).where(
                ShiftPlanEntry.employee_id == employee_id, ShiftPlanEntry.date == work_date
            )
        )
        entry = result.scalar_one_or_none()
    if entry is not None:
        if not entry.is_workday:
            return EffectiveDayPlan(False, True, None, None, None, None, True)
        template = (
            await db.get(ShiftTemplate, entry.shift_template_id)
            if entry.shift_template_id is not None
            else None
        )
        return EffectiveDayPlan(
            True,
            True,
            entry.target_minutes,
            entry.shift_template_id,
            template.start_time if template else None,
            template.end_time if template else None,
            True,
        )

    result = await db.execute(
        select(EmployeeDefaultShift).where(
            EmployeeDefaultShift.employee_id == employee_id,
            EmployeeDefaultShift.valid_from <= work_date,
        )
    )
    # Es gibt zu jedem Zeitpunkt höchstens eine aktive Default-Zuordnung pro
    # Mitarbeiter (siehe app/api/employee_default_shifts.py Overlap-Check) –
    # daher hier keine weitere Auswahl nötig, nur die Gültigkeit filtern.
    candidates = [
        d for d in result.scalars().all() if d.valid_to is None or d.valid_to >= work_date
    ]
    default = candidates[0] if candidates else None
    if default is None:
        return _UNCONFIGURED

    if default.on_demand:
        # plan_exists=False: kein Soll, kein "frei laut Plan", kein "außerplanmäßig".
        return EffectiveDayPlan(True, False, None, default.shift_template_id, None, None, False, on_demand=True)

    if default.flexible:
        template = await db.get(ShiftTemplate, default.shift_template_id)
        return EffectiveDayPlan(
            True, True, None, template.id, None, None, False, flexible_weekly_minutes=template.target_minutes
        )

    weekday_bit = 1 << work_date.weekday()
    per_day = default.day_minutes_list
    if not (default.weekdays_mask & weekday_bit) or (per_day is not None and per_day[work_date.weekday()] <= 0):
        return EffectiveDayPlan(False, True, None, None, None, None, False)

    template = await db.get(ShiftTemplate, default.shift_template_id)
    target_minutes = (
        per_day[work_date.weekday()]
        if per_day is not None
        else _resolve_target_minutes(template, work_date, default.weekdays_mask)
    )
    return EffectiveDayPlan(
        True, True, target_minutes, template.id, template.start_time, template.end_time, False
    )


def _shift_start_dt(day: date, start_time: time) -> datetime:
    return datetime.combine(day, start_time)


def _shift_end_dt(day: date, start_time: time, end_time: time) -> datetime:
    """Schicht endet am selben Kalendertag, außer sie überspannt Mitternacht
    (end_time <= start_time, z.B. Nachtschicht 22:00-06:00)."""
    end_dt = datetime.combine(day, end_time)
    if end_time <= start_time:
        end_dt += timedelta(days=1)
    return end_dt


def _raise_rest_period_violation() -> None:
    raise AppError(
        400,
        "REST_PERIOD_VIOLATION",
        "Die gesetzliche Mindestruhezeit von 11 Stunden zwischen zwei Schichten (§5 ArbZG) wird unterschritten.",
    )


def check_max_daily_working_time(start_time: time | None, end_time: time | None) -> None:
    """ArbZG §3: prüft die GEPLANTE Schichtdauer (nicht die tatsächlich
    gestempelte Zeit) gegen die harte 10-Stunden-Grenze – die ist immer
    illegal, unabhängig von einem sonst möglichen Ausgleich. Die weichere
    8h-Grenze (verlängerbar auf 10h bei Ausgleich innerhalb von 6 Monaten)
    wird hier bewusst NICHT durchgesetzt, da sie je nach Ausgleich legal sein
    kann und sich nicht sinnvoll vorab blockieren lässt. Ob TATSÄCHLICH
    gearbeitete Zeit (aus Stempelungen) die 10h-Grenze überschreitet, wird
    separat und rückwirkend sichtbar gemacht, siehe
    app/services/timesheet_service.py calculate_day
    (DayCalculation.exceeds_max_daily_minutes) – ein solcher Verstoß lässt
    sich nicht präventiv verhindern, da die Zeit bereits gearbeitet wurde.

    Ohne Zeiten (z.B. migrierte Platzhalter-Vorlage) ist keine Prüfung
    möglich – wird übersprungen wie bei check_rest_period_for_entry."""
    if start_time is None or end_time is None:
        return

    start_min = start_time.hour * 60 + start_time.minute
    end_min = end_time.hour * 60 + end_time.minute
    if end_time <= start_time:
        end_min += 24 * 60
    duration_minutes = end_min - start_min

    if duration_minutes > MAX_DAILY_WORKING_MINUTES:
        raise AppError(
            400,
            "MAX_DAILY_WORKING_TIME_EXCEEDED",
            "Die Schicht überschreitet die gesetzliche Höchstarbeitszeit von 10 Stunden pro Tag (§3 ArbZG).",
        )


async def check_rest_period_for_entry(
    db: AsyncSession, employee_id: int, work_date: date, start_time: time | None, end_time: time | None
) -> None:
    """Prüft eine einzelne Tagesplanung (ShiftPlanEntry) gegen den
    aufgelösten Vortag/Folgetag. Ohne Zeiten (z.B. migrierte
    Platzhalter-Vorlage) ist keine Prüfung möglich – wird übersprungen,
    nicht als Verstoß gewertet."""
    if start_time is None or end_time is None:
        return

    this_start = _shift_start_dt(work_date, start_time)
    this_end = _shift_end_dt(work_date, start_time, end_time)

    prev_day = work_date - timedelta(days=1)
    prev = await resolve_effective_shift(db, employee_id, prev_day)
    if prev.is_workday and prev.start_time is not None and prev.end_time is not None:
        prev_end = _shift_end_dt(prev_day, prev.start_time, prev.end_time)
        if (this_start - prev_end).total_seconds() / 60 < REST_PERIOD_MINUTES:
            _raise_rest_period_violation()

    next_day = work_date + timedelta(days=1)
    nxt = await resolve_effective_shift(db, employee_id, next_day)
    if nxt.is_workday and nxt.start_time is not None:
        next_start = _shift_start_dt(next_day, nxt.start_time)
        if (next_start - this_end).total_seconds() / 60 < REST_PERIOD_MINUTES:
            _raise_rest_period_violation()


def _gap_minutes(prev_end_time: time, prev_start_time: time, next_start_time: time) -> float:
    """Ruhezeit zwischen dem Ende einer Schicht und dem Beginn der nächsten
    am Folgetag, unabhängig von echten Kalenderdaten (die Wochenmaske
    wiederholt sich wöchentlich identisch) – Endzeit ggf. über Mitternacht
    hinaus normalisiert (>1440 Minuten), Folgetag-Start bekommt +1440."""
    start_min = prev_start_time.hour * 60 + prev_start_time.minute
    end_min = prev_end_time.hour * 60 + prev_end_time.minute
    if prev_end_time <= prev_start_time:
        end_min += 24 * 60
    next_start_min = 24 * 60 + next_start_time.hour * 60 + next_start_time.minute
    return next_start_min - end_min


async def check_rest_period_for_default(
    db: AsyncSession,
    employee_id: int,
    template: ShiftTemplate,
    weekdays_mask: int,
    valid_from: date,
    valid_to: date | None,
) -> None:
    """Ein neuer EmployeeDefaultShift wirkt sofort und unbegrenzt in die
    Zukunft, ohne je eine ShiftPlanEntry-Zeile anzulegen – reicht es nicht,
    nur bei ShiftPlanEntry-Schreibvorgängen zu prüfen. Prüft:
    (a) jedes Paar aufeinanderfolgender in weekdays_mask gesetzter
        Wochentage (inkl. So->Mo-Übergang) auf Selbstkonsistenz;
    (b) den Tag vor valid_from und nach valid_to gegen das, was dort
        aktuell effektiv gilt.
    Ein Cross-Check gegen ANDERE aktive Defaults desselben Mitarbeiters
    (dritter Punkt einer früheren Designüberlegung) entfällt bewusst: das
    bestehende Overlap-Verbot lässt zu jedem Zeitpunkt ohnehin nur einen
    aktiven Default zu, es kann also keinen zweiten geben, gegen den
    geprüft werden müsste."""
    if template.start_time is None or template.end_time is None:
        return

    flagged = [d for d in range(7) if weekdays_mask & (1 << d)]
    flagged_set = set(flagged)
    for day in flagged:
        next_day = (day + 1) % 7
        if next_day in flagged_set:
            gap = _gap_minutes(template.end_time, template.start_time, template.start_time)
            if gap < REST_PERIOD_MINUTES:
                _raise_rest_period_violation()

    day_before = valid_from - timedelta(days=1)
    before_plan = await resolve_effective_shift(db, employee_id, day_before)
    if (
        before_plan.is_workday
        and before_plan.end_time is not None
        and (valid_from.weekday() in flagged_set)
    ):
        gap = _gap_minutes(before_plan.end_time, before_plan.start_time or before_plan.end_time, template.start_time)
        if gap < REST_PERIOD_MINUTES:
            _raise_rest_period_violation()

    if valid_to is not None:
        day_after = valid_to + timedelta(days=1)
        after_plan = await resolve_effective_shift(db, employee_id, day_after)
        if after_plan.is_workday and after_plan.start_time is not None and (valid_to.weekday() in flagged_set):
            gap = _gap_minutes(template.end_time, template.start_time, after_plan.start_time)
            if gap < REST_PERIOD_MINUTES:
                _raise_rest_period_violation()
