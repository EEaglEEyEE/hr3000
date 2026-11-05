import calendar
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Absence,
    AbsenceTypeDefinition,
    AppSettings,
    BalanceAdjustment,
    AbsenceApprovalStatus,
    AbsenceType,
    BreakRule,
    DailySummary,
    Employee,
    EmployeeLocationPeriod,
    Location,
    OvertimeBalance,
    Punch,
    PunchSource,
    PunchType,
    SummaryStatus,
)
from app.services.absence_type_service import CATEGORY_LABELS, absence_day_values
from app.services.holiday_service import is_holiday_for_location
from app.services.shift_planning_service import MAX_DAILY_WORKING_MINUTES, resolve_effective_shift


@dataclass
class DayCalculation:
    work_date: date
    actual_minutes: int | None
    target_minutes: int | None
    status: SummaryStatus
    absence_type: AbsenceType | None = None
    # ArbZG §3: TATSÄCHLICH gearbeitete Zeit über der harten 10h-Grenze –
    # rein informativ (siehe check_max_daily_working_time in
    # shift_planning_service.py für die präventive Prüfung der GEPLANTEN
    # Schichtdauer). Ein Verstoß hier lässt sich nicht mehr verhindern, nur
    # nachträglich für HR sichtbar machen.
    exceeds_max_daily_minutes: bool = False
    # Sonderfälle, die HR klären/bestätigen soll (siehe DayFlag) – der Tag zählt trotzdem.
    flags: list[str] = field(default_factory=list)
    has_punches: bool = False
    # Flexibles Modell: Anteil des Wochensolls an diesem Kalendertag (Wochensoll / 7) –
    # das Gleitzeitkonto rechnet für solche Tage wochenweise ab (siehe rebuild_balance).
    flexible_share: float = 0.0
    # Eigene Abwesenheitsart des Mandanten (Name/Farbe), None = Standardart der Kategorie
    absence_type_id: int | None = None
    # Abwesenheitsanteile des Tages je Kategorie (1.0 = ganzer Tag, 0.5 = halber Tag) – für
    # Urlaubs-/Krankheitstage in Monatsnachweis und Lohn-Export.
    absence_parts: list[tuple[AbsenceType, float]] = field(default_factory=list)
    # Anzeige bei halben Tagen, z.B. "½ Urlaub" oder "½ Sonderurlaub + ½ Urlaub"
    absence_label: str | None = None
    # Anteil unbezahlter Abwesenheit (senkt bei flexiblen Modellen das Wochensoll)
    unpaid_portion: float = 0.0


class DayFlag:
    """Gründe, warum ein Tag trotz gültiger Stempelung unter "Zu klären" erscheint."""

    UNPLANNED_WORK = "UNPLANNED_WORK"  # gestempelt, obwohl laut Plan frei
    WORK_DURING_ABSENCE = "WORK_DURING_ABSENCE"  # gestempelt trotz Urlaub/Krankheit/Sonderurlaub
    HOLIDAY_WORK = "HOLIDAY_WORK"  # gestempelt an einem Feiertag
    OUTSIDE_EMPLOYMENT = "OUTSIDE_EMPLOYMENT"  # vor Eintritt / nach Austritt gestempelt
    OVER_MAX_DAILY = "OVER_MAX_DAILY"  # mehr als 10 Std. gearbeitet (§3 ArbZG)
    LATE_ARRIVAL = "LATE_ARRIVAL"  # nach Schicht-/Kernzeitbeginn (+ Toleranz) gekommen
    EARLY_LEAVE = "EARLY_LEAVE"  # vor Schicht-/Kernzeitende (− Toleranz) gegangen
    OUTSIDE_FLEX_FRAME = "OUTSIDE_FLEX_FRAME"  # vor/nach dem Gleitzeit-Rahmen gestempelt


DAY_FLAGS = [
    DayFlag.UNPLANNED_WORK,
    DayFlag.WORK_DURING_ABSENCE,
    DayFlag.HOLIDAY_WORK,
    DayFlag.OUTSIDE_EMPLOYMENT,
    DayFlag.OVER_MAX_DAILY,
    DayFlag.LATE_ARRIVAL,
    DayFlag.EARLY_LEAVE,
    DayFlag.OUTSIDE_FLEX_FRAME,
]


def week_start(work_date: date) -> date:
    """Montag der Kalenderwoche, in der work_date liegt – wird nur noch für
    die Wochen-Iteration in app/api/timesheets.py::get_weekly_balance
    gebraucht (rechnet live über calculate_day, kein persistiertes
    Wochenmodell mehr, siehe unten)."""
    return work_date - timedelta(days=work_date.weekday())


async def employee_timezone(db: AsyncSession, employee: Employee) -> ZoneInfo:
    location = await db.get(Location, employee.location_id)
    return ZoneInfo(location.timezone)


def today_in(tz: ZoneInfo) -> date:
    """Heutiges Datum in der Zeitzone des Standorts – Auswertungen gehen nie über heute hinaus."""
    return datetime.now(tz).date()


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    aware = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return aware.astimezone(tz).date()


async def calculate_day(
    db: AsyncSession, employee: Employee, work_date: date, tz: ZoneInfo
) -> DayCalculation:
    """Ist-Zeit, Soll-Zeit und Status für einen Tag. Soll kommt jetzt direkt aus
    der Schichtplanung (siehe app/services/shift_planning_service.py
    resolve_effective_shift) statt aus einem wochenbasierten Arbeitszeitmodell
    – der Vergleich findet daher wieder pro Tag statt, nicht mehr pro Woche
    (siehe app/models/overtime_balance.py).

    Reihenfolge: zuerst die Arbeitstag-Auflösung – ist der Tag laut Plan gar
    kein Arbeitstag, spielt es keine Rolle, ob er ein Feiertag ist (Feiertag an
    einem ohnehin freien Tag hat keinen Effekt). Erst danach Feiertag, dann
    genehmigte Absenz (beide werden mit dem vollen Tagesziel neutral
    gutgeschrieben, kein Stempeln nötig), erst zuletzt die normale
    Punch-Paarung.

    Ein Mitarbeiter/Tag ohne jede Schichtplanung (plan_exists=False) ist
    NICHT dasselbe wie ein expliziter freier Tag – er wird wie bisher ohne
    Arbeitszeitmodell behandelt: normales Stempeln, nur kein Soll (target
    bleibt None). Nur ein tatsächlich existierender Plan, der "kein
    Arbeitstag" sagt, führt zu PLANNED_OFF."""
    calculation = await _calculate_day_core(db, employee, work_date, tz)
    if calculation.has_punches and (
        (employee.hire_date is not None and work_date < employee.hire_date)
        or (employee.termination_date is not None and work_date > employee.termination_date)
    ):
        calculation.flags.append(DayFlag.OUTSIDE_EMPLOYMENT)
    if calculation.exceeds_max_daily_minutes:
        calculation.flags.append(DayFlag.OVER_MAX_DAILY)
    if calculation.flags:
        # Mandant kann einzelne Sonderfälle abschalten (Einstellungen) – der Tag zählt dann normal.
        _, disabled = await _tenant_rules(db, employee.tenant_id)
        calculation.flags = [f for f in calculation.flags if f not in disabled]
    return calculation


async def _calculate_day_core(db: AsyncSession, employee: Employee, work_date: date, tz: ZoneInfo) -> DayCalculation:
    day_punches = await punches_for_day(db, employee, work_date, tz)
    calculation = await _resolve_day(db, employee, work_date, tz, day_punches)
    calculation.has_punches = bool(day_punches)
    if day_punches and employee.core_time_mode != "NONE":
        calculation.flags.extend(await _punctuality_flags(db, employee, work_date, tz, calculation, day_punches))
    return calculation


async def _punctuality_flags(
    db: AsyncSession, employee: Employee, work_date: date, tz: ZoneInfo, calculation: DayCalculation, day_punches: list[Punch]
) -> list[str]:
    """Kernarbeitszeit/Gleitzeit (Einstellungen, je Mitarbeiter änderbar): zu spät gekommen, zu früh
    gegangen, außerhalb des Gleitzeit-Rahmens gestempelt. Nur an normalen Arbeitstagen mit Soll –
    nicht bei Abwesenheit (auch halbtags), Feiertag, außerplanmäßiger Arbeit oder widersprüchlichen
    Buchungen. Reine Hinweise für "Zu klären": an den Stunden ändert sich nichts."""
    if (
        not calculation.target_minutes
        or calculation.absence_type is not None
        or calculation.status in (SummaryStatus.ERROR, SummaryStatus.HOLIDAY, SummaryStatus.ABSENCE)
        or DayFlag.UNPLANNED_WORK in calculation.flags
        or DayFlag.HOLIDAY_WORK in calculation.flags
    ):
        return []
    rules = (
        await db.execute(
            select(
                AppSettings.core_time_start,
                AppSettings.core_time_end,
                AppSettings.punctuality_check,
                AppSettings.late_tolerance_minutes,
                AppSettings.flex_frame_start,
                AppSettings.flex_frame_end,
            ).where(AppSettings.tenant_id == employee.tenant_id)
        )
    ).first()
    if rules is None:
        return []
    core_start, core_end, check, tolerance, frame_start, frame_end = rules
    if employee.core_time_mode == "CUSTOM":
        core_start, core_end = employee.core_time_start, employee.core_time_end

    comes = [p for p in day_punches if p.punch_type == PunchType.COME]
    goes = [p for p in day_punches if p.punch_type == PunchType.GO]
    if not comes:
        return []

    def local(punch: Punch) -> datetime:
        return _naive_utc(punch.timestamp_utc).replace(tzinfo=UTC).astimezone(tz)

    def at(clock: time, next_day: bool = False) -> datetime:
        return datetime.combine(work_date + timedelta(days=1 if next_day else 0), clock, tzinfo=tz)

    flags: list[str] = []
    first_come = local(comes[0])
    last_go = local(goes[-1]) if goes and calculation.status == SummaryStatus.COMPLETE else None

    if check:
        # Schicht mit Uhrzeiten (Schichtplanung) hat Vorrang vor der Kernzeit.
        plan = await resolve_effective_shift(db, employee.id, work_date)
        start, end = (plan.start_time, plan.end_time) if plan.start_time and plan.end_time else (core_start, core_end)
        grace = timedelta(minutes=tolerance or 0)
        if start is not None and first_come > at(start) + grace:
            flags.append(DayFlag.LATE_ARRIVAL)
        if start is not None and end is not None and last_go is not None:
            # Nachtschicht (Ende vor Beginn) endet am Folgetag.
            if last_go < at(end, next_day=end <= start) - grace:
                flags.append(DayFlag.EARLY_LEAVE)

    if frame_start is not None and frame_end is not None:
        if first_come < at(frame_start) or (last_go is not None and last_go > at(frame_end)):
            flags.append(DayFlag.OUTSIDE_FLEX_FRAME)
    return flags


async def _resolve_flexible_day(
    db: AsyncSession, employee: Employee, work_date: date, tz: ZoneInfo, day_punches: list[Punch], weekly_minutes: int
) -> DayCalculation:
    """Aushilfe ohne feste Tage: kein Tagessoll, nie "fehlt"/"außerplanmäßig". Feiertage und
    genehmigte Abwesenheiten an Mo–Fr werden mit Wochensoll / 5 gutgeschrieben (6 Wochen Urlaub
    = 6 Wochensolls)."""
    credit = round(weekly_minutes / 5) if work_date.weekday() < 5 else 0
    worked, status = (await _pair_punches(db, employee, work_date, tz, day_punches)) if day_punches else (None, SummaryStatus.OPEN_MISSING_PUNCH)
    if await _is_holiday(db, employee, work_date):
        flags = [DayFlag.HOLIDAY_WORK] if day_punches else []
        if day_punches and status != SummaryStatus.COMPLETE:
            return DayCalculation(work_date, None, None, status, flags=flags)
        # Stundenangaben am Feiertag (z.B. "Feiertag (GfB)" mit 3 Std.) kommen zur Gutschrift dazu.
        hours = await _absence_day(db, employee, work_date)
        extra, label = (hours.duration_credit(), hours.label) if hours and hours.durations else (0, None)
        return DayCalculation(
            work_date, credit + extra + (worked or 0), None, SummaryStatus.HOLIDAY, flags=flags, absence_label=label
        )
    absence_day = await _absence_day(db, employee, work_date)
    if absence_day is not None:
        credited, _ = absence_day.values(None, credit)
        common = absence_day.fields()
        if absence_day.portion >= 1 and day_punches:
            return DayCalculation(work_date, worked, None, status, flags=[DayFlag.WORK_DURING_ABSENCE], **common)
        if not day_punches:
            # Ohne Tagessoll muss die andere Hälfte eines halben Tages nicht gestempelt werden.
            return DayCalculation(work_date, credited, None, SummaryStatus.ABSENCE, **common)
        return DayCalculation(work_date, None if worked is None else worked + credited, None, status, **common)
    return DayCalculation(
        work_date, worked, None, status, exceeds_max_daily_minutes=worked is not None and worked > MAX_DAILY_WORKING_MINUTES
    )


async def _resolve_day(
    db: AsyncSession, employee: Employee, work_date: date, tz: ZoneInfo, day_punches: list[Punch]
) -> DayCalculation:
    plan = await resolve_effective_shift(db, employee.id, work_date)

    if plan.flexible_weekly_minutes is not None:
        calculation = await _resolve_flexible_day(db, employee, work_date, tz, day_punches, plan.flexible_weekly_minutes)
        calculation.flexible_share = plan.flexible_weekly_minutes / 7
        if calculation.unpaid_portion and work_date.weekday() < 5:
            # Unbezahlte Abwesenheit senkt das Wochensoll um einen Tagesanteil (Wochensoll / 5, halber Tag: die Hälfte).
            calculation.flexible_share -= plan.flexible_weekly_minutes / 5 * calculation.unpaid_portion
        return calculation

    if plan.plan_exists and not plan.is_workday:
        if not day_punches:
            return DayCalculation(work_date, None, None, SummaryStatus.PLANNED_OFF)
        # Außerplanmäßig gestempelt: zählt als Anwesenheit/Mehrarbeit (Soll 0), aber "zu klären".
        actual, status = await _pair_punches(db, employee, work_date, tz, day_punches)
        return DayCalculation(
            work_date, actual, 0, status,
            exceeds_max_daily_minutes=actual is not None and actual > MAX_DAILY_WORKING_MINUTES,
            flags=[DayFlag.UNPLANNED_WORK],
        )

    # Ohne Plan (plan_exists=False) bleibt die Ist-Zeit an Feiertag/Absenz-
    # Tagen wie bisher 0 statt "= Soll" – es gibt kein Soll, das gutgeschrieben
    # werden könnte, und 0 erhält das bisherige Verhalten für Mitarbeiter ohne
    # Schichtplanung exakt.
    if await _is_holiday(db, employee, work_date):
        credited = plan.target_minutes if plan.plan_exists else 0
        # Stundenangaben am Feiertag (z.B. "Feiertag (GfB)" für Aushilfen ohne Soll) zählen zusätzlich.
        hours = await _absence_day(db, employee, work_date)
        holiday_label = None
        if hours and hours.durations:
            credited = (credited or 0) + hours.duration_credit()
            holiday_label = hours.label
        if not day_punches:
            return DayCalculation(work_date, credited, plan.target_minutes, SummaryStatus.HOLIDAY, absence_label=holiday_label)
        # Gearbeitet an einem Feiertag: Gutschrift + gearbeitete Zeit (-> Saldo/Feiertagszuschlag).
        # Unvollständige Buchungen zeigen den Stempelstatus (anwesend/offen) statt "Feiertag".
        worked, worked_status = await _pair_punches(db, employee, work_date, tz, day_punches)
        if worked_status == SummaryStatus.COMPLETE:
            return DayCalculation(
                work_date, (credited or 0) + (worked or 0), plan.target_minutes, SummaryStatus.HOLIDAY,
                exceeds_max_daily_minutes=(worked or 0) > MAX_DAILY_WORKING_MINUTES,
                flags=[DayFlag.HOLIDAY_WORK],
                absence_label=holiday_label,
            )
        return DayCalculation(work_date, None, plan.target_minutes, worked_status, flags=[DayFlag.HOLIDAY_WORK])

    absence_day = await _absence_day(db, employee, work_date)
    if absence_day is not None:
        # Kategorie der Abwesenheitsart: bezahlt = Soll gutschreiben, unbezahlt = kein Soll,
        # Freizeitausgleich = Soll ohne Gutschrift (siehe absence_type_service) – bei halben
        # Tagen jeweils zur Hälfte.
        credited, target = absence_day.values(plan.target_minutes, plan.target_minutes if plan.plan_exists else 0)
        common = absence_day.fields()
        if absence_day.portion >= 1:
            if not day_punches:
                return DayCalculation(work_date, credited, target, SummaryStatus.ABSENCE, **common)
            # Gestempelt trotz genehmigter Abwesenheit: die gearbeitete Zeit zählt (keine doppelte
            # Gutschrift), HR klärt, ob die Abwesenheit für den Tag storniert werden muss.
            actual, status = await _pair_punches(db, employee, work_date, tz, day_punches)
            return DayCalculation(
                work_date, actual, target, status,
                exceeds_max_daily_minutes=actual is not None and actual > MAX_DAILY_WORKING_MINUTES,
                flags=[DayFlag.WORK_DURING_ABSENCE],
                **common,
            )
        # Halber Tag: die andere Hälfte wird ganz normal gestempelt (Gutschrift + gearbeitete Zeit).
        # Ohne Stempelung fehlt die andere Hälfte -> wie jeder Arbeitstag ohne Stempelung "zu klären".
        # Nur Stundenangaben (z.B. 3 Std. Homeoffice): HR hat genau erfasst, was war -> der Tag ist
        # damit erledigt (Rest des Solls belastet das Gleitzeitkonto).
        if not day_punches:
            status = SummaryStatus.ABSENCE if absence_day.portion == 0 else SummaryStatus.OPEN_MISSING_PUNCH
            return DayCalculation(work_date, credited, target, status, **common)
        worked, status = await _pair_punches(db, employee, work_date, tz, day_punches)
        return DayCalculation(
            work_date, None if worked is None else worked + credited, target, status,
            exceeds_max_daily_minutes=worked is not None and worked > MAX_DAILY_WORKING_MINUTES,
            **common,
        )

    actual_minutes, status = await _pair_punches(db, employee, work_date, tz, day_punches)
    exceeds_max_daily = actual_minutes is not None and actual_minutes > MAX_DAILY_WORKING_MINUTES
    return DayCalculation(
        work_date, actual_minutes, plan.target_minutes, status, exceeds_max_daily_minutes=exceeds_max_daily
    )


async def location_on(db: AsyncSession, employee: Employee, work_date: date) -> int:
    """Standort des Mitarbeiters an diesem Tag (Standort-Historie, sonst der aktuelle)."""
    location_id = (
        await db.execute(
            select(EmployeeLocationPeriod.location_id)
            .where(EmployeeLocationPeriod.employee_id == employee.id, EmployeeLocationPeriod.valid_from <= work_date)
            .order_by(EmployeeLocationPeriod.valid_from.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return location_id or employee.location_id


async def _is_holiday(db: AsyncSession, employee: Employee, work_date: date) -> bool:
    """Ein Feiertag gilt, wenn er keinem Standort zugeordnet ist (= alle) oder
    dem Standort, an dem der Mitarbeiter an diesem Tag war, siehe app/models/holiday.py."""
    return await is_holiday_for_location(db, employee.tenant_id, work_date, await location_on(db, employee, work_date))


async def _approved_absences_covering(db: AsyncSession, employee_id: int, work_date: date) -> list[Absence]:
    """Nur genehmigte Absenzen (approval_status=APPROVED) neutralisieren den
    Tag – eine PENDING/REJECTED-Absenz verlangt weiterhin normales Stempeln,
    siehe app/api/absences.py create_absence."""
    result = await db.execute(
        select(Absence)
        .where(
            Absence.employee_id == employee_id,
            Absence.date_from <= work_date,
            Absence.date_to >= work_date,
            Absence.approval_status == AbsenceApprovalStatus.APPROVED,
        )
        .order_by(Absence.id)
    )
    return list(result.scalars().all())


@dataclass
class AbsenceDay:
    """Genehmigte Abwesenheit(en) eines Tages: ein ganzer Tag, bis zu zwei halbe Tage und/oder
    Stundenangaben (z.B. 3 Std. Homeoffice)."""

    parts: list[tuple[Absence, float]]
    label: str | None
    # Abwesenheiten mit genauer Dauer: (Abwesenheit, Minuten)
    durations: list[tuple[Absence, int]] = field(default_factory=list)

    @property
    def portion(self) -> float:
        """Anteil des Tages aus ganzen/halben Tagen (Stundenangaben zählen nicht als Tagesanteil)."""
        return min(1.0, sum(fraction for _, fraction in self.parts))

    def values(self, target_minutes: int | None, credit_minutes: int | None) -> tuple[int, int | None]:
        """(Gutschrift, Soll) – je ganzem/halbem Anteil wie absence_day_values, Stundenangaben mit
        genau ihrer Dauer (bezahlt: Gutschrift, unbezahlt: weniger Soll, Freizeitausgleich: nichts)."""
        credited = 0.0
        reduction = 0.0
        for absence, fraction in self.parts:
            credit, target = absence_day_values(absence.type, target_minutes, credit_minutes)
            credited += (credit or 0) * fraction
            if target_minutes is not None and target is not None:
                reduction += (target_minutes - target) * fraction
        for absence, minutes in self.durations:
            if absence.type == AbsenceType.UNPAID:
                reduction += minutes if target_minutes is not None else 0
            elif absence.type != AbsenceType.TIME_OFF_IN_LIEU:
                credited += minutes
        target = None if target_minutes is None else max(round(target_minutes - reduction), 0)
        return round(credited), target

    def duration_credit(self) -> int:
        """Gutschrift aus bezahlten Stundenangaben (z.B. "Feiertag (GfB)" an einem Feiertag)."""
        return sum(m for a, m in self.durations if a.type not in (AbsenceType.UNPAID, AbsenceType.TIME_OFF_IN_LIEU))

    def fields(self) -> dict:
        first = (self.parts or self.durations)[0][0]
        return dict(
            absence_type=first.type,
            absence_type_id=first.absence_type_id,
            absence_parts=[(absence.type, fraction) for absence, fraction in self.parts],
            absence_label=self.label,
            unpaid_portion=sum(f for a, f in self.parts if a.type == AbsenceType.UNPAID),
        )


def format_hours(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d} Std."


def describe_absence_parts(halves: list[Absence], durations: list[Absence], names: dict[int, str]) -> str:
    """Anzeige für Teil-Abwesenheiten, z.B. "½ Sonderurlaub + ½ Urlaub" oder "Homeoffice 3:00 Std."."""

    def name(absence: Absence) -> str:
        return names.get(absence.absence_type_id) or CATEGORY_LABELS[absence.type]

    return " + ".join(
        [f"½ {name(a)}" for a in halves] + [f"{name(a)} {format_hours(a.duration_minutes)}" for a in durations]
    )


async def _absence_day(db: AsyncSession, employee: Employee, work_date: date) -> AbsenceDay | None:
    absences = await _approved_absences_covering(db, employee.id, work_date)
    if not absences:
        return None
    full = [a for a in absences if not a.half_day and a.duration_minutes is None]
    # Ganztägig hat Vorrang (ältere, sich überschneidende Einträge: wie bisher der erste);
    # sonst höchstens zwei halbe Tage plus Stundenangaben – das Anlegen verhindert anderes
    # (siehe app/api/absences.py).
    if full:
        return AbsenceDay([(full[0], 1.0)], None)
    halves = [a for a in absences if a.half_day][:2]
    durations = [a for a in absences if a.duration_minutes is not None]
    names = await absence_type_names(db, [a.absence_type_id for a in halves + durations if a.absence_type_id])
    return AbsenceDay(
        [(a, 0.5) for a in halves],
        describe_absence_parts(halves, durations, names),
        [(a, a.duration_minutes) for a in durations],
    )


async def absence_type_names(db: AsyncSession, type_ids: list[int]) -> dict[int, str]:
    if not type_ids:
        return {}
    rows = await db.execute(
        select(AbsenceTypeDefinition.id, AbsenceTypeDefinition.name).where(AbsenceTypeDefinition.id.in_(type_ids))
    )
    return {type_id: name for type_id, name in rows.all()}


def absence_day_counts(calculation: DayCalculation) -> dict[AbsenceType, float]:
    """Abwesenheitstage je Kategorie an diesem Tag (halbe Tage = 0,5). Ganztägige Abwesenheit
    zählt nur, wenn der Tag tatsächlich als Abwesenheit gilt (nicht trotzdem gearbeitet)."""
    counts: dict[AbsenceType, float] = {}
    for category, fraction in calculation.absence_parts:
        if category == AbsenceType.WORK_TIME:
            continue  # Arbeitszeit (z.B. Homeoffice) ist kein Abwesenheitstag
        if fraction >= 1 and calculation.status != SummaryStatus.ABSENCE:
            continue
        counts[category] = counts.get(category, 0.0) + fraction
    return counts


# §4 ArbZG: Ruhepausen zählen erst ab 15 Minuten – kürzere Unterbrechungen sind keine Pause.
MIN_BREAK_BLOCK_MINUTES = 15

# Eine Schicht gehört zum Tag ihres "Kommens" – auch wenn sie über Mitternacht geht (Nachtschicht).
# Folgebuchungen am nächsten Kalendertag zählen nur dann noch zur Schicht, wenn sie innerhalb
# dieser Spanne nach dem Kommen liegen; danach gilt das "Gehen" als vergessen.
MAX_SHIFT_SPAN = timedelta(hours=16)


async def reports_days_without_punches(db: AsyncSession, tenant_id: int) -> bool:
    """Mandanten-Schalter: Arbeitstage ganz ohne Stempelung als "Stempelung fehlt" melden
    (Standard an, siehe AppSettings.report_days_without_punches)."""
    value = (
        await db.execute(select(AppSettings.report_days_without_punches).where(AppSettings.tenant_id == tenant_id))
    ).scalar_one_or_none()
    return True if value is None else bool(value)


def missing_punch_reported(calc: DayCalculation, report_days_without_punches: bool) -> bool:
    """Gilt der Tag als "Stempelung fehlt"? Unvollständig gestempelt immer; ganz ohne Stempelung
    nur an Tagen mit Soll und nur, wenn der Mandant solche Tage melden lässt. (Flexible Modelle und
    Mitarbeiter ohne Modell haben kein Tagessoll – dort fehlt ohne Stempelung nie etwas.)"""
    if calc.status != SummaryStatus.OPEN_MISSING_PUNCH:
        return False
    return calc.has_punches or (bool(calc.target_minutes) and report_days_without_punches)


def _utcnow() -> datetime:
    """Aktuelle Zeit (UTC, naiv) – eigene Funktion, damit Tests den Zeitpunkt festlegen können."""
    return datetime.now(UTC).replace(tzinfo=None)


def _naive_utc(dt: datetime) -> datetime:
    # Frisch angelegte (noch nicht neu geladene) Stempelungen tragen eine Zeitzone, aus der DB gelesene nicht.
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo is not None else dt


async def _tenant_rules(db: AsyncSession, tenant_id: int) -> tuple[timedelta, set[str]]:
    """(maximale Schichtspanne, abgeschaltete Sonderfälle) aus den Mandanten-Einstellungen."""
    row = (
        await db.execute(
            select(AppSettings.max_shift_span_hours, AppSettings.disabled_day_flags).where(AppSettings.tenant_id == tenant_id)
        )
    ).first()
    if row is None:
        return MAX_SHIFT_SPAN, set()
    span_hours, disabled = row
    return timedelta(hours=span_hours or 16), {f for f in (disabled or "").split(",") if f}


def assign_shift_days(punches: list[Punch], tz: ZoneInfo, max_span: timedelta = MAX_SHIFT_SPAN) -> dict[int, date]:
    """Punch-ID -> Arbeitstag. Erwartet chronologisch sortierte Stempelungen."""
    assignment: dict[int, date] = {}
    shift_day: date | None = None
    shift_start: datetime | None = None
    for punch in punches:
        day = local_date(punch.timestamp_utc, tz)
        if punch.punch_type == PunchType.COME:
            shift_day, shift_start = day, punch.timestamp_utc
            assignment[punch.id] = day
            continue
        if shift_day is not None and shift_day != day and _naive_utc(punch.timestamp_utc) - _naive_utc(shift_start) <= max_span:
            assignment[punch.id] = shift_day  # Fortsetzung einer Schicht über Mitternacht
        else:
            assignment[punch.id] = day
            if shift_day is not None and shift_day != day:
                shift_day = None
        if punch.punch_type == PunchType.GO:
            shift_day = None
    return assignment


async def _punch_window(db: AsyncSession, employee_id: int, first: date, last: date) -> list[Punch]:
    # ±2 Tage Puffer: Zeitzonen-Versatz und Schichten über Mitternacht.
    result = await db.execute(
        select(Punch)
        .where(
            Punch.employee_id == employee_id,
            Punch.timestamp_utc >= datetime.combine(first - timedelta(days=2), time.min),
            Punch.timestamp_utc < datetime.combine(last + timedelta(days=3), time.min),
        )
        .order_by(Punch.timestamp_utc.asc(), Punch.id.asc())
    )
    return list(result.scalars().all())


def is_birthday(birth_date: date | None, day: date) -> bool:
    """Geburtstag an diesem Tag? Am 29.02. Geborene feiern in Nicht-Schaltjahren am 28.02."""
    if birth_date is None:
        return False
    if birth_date.month == 2 and birth_date.day == 29 and not calendar.isleap(day.year):
        return day.month == 2 and day.day == 28
    return (day.month, day.day) == (birth_date.month, birth_date.day)


def punch_blocks(punches: list[Punch], tz: ZoneInfo) -> str:
    """Zeitblöcke eines Tages aus Kommen/Gehen, z.B. "08:00–12:00, 13:00–17:00" (offenes Ende "–…")."""
    blocks: list[str] = []
    block_start = None
    for p in punches:
        local = p.timestamp_utc.replace(tzinfo=UTC).astimezone(tz).strftime("%H:%M")
        if p.punch_type == PunchType.COME:
            block_start = local
        elif p.punch_type == PunchType.GO:
            blocks.append(f"{block_start or '?'}–{local}")
            block_start = None
    if block_start:
        blocks.append(f"{block_start}–…")
    return ", ".join(blocks)


async def punches_for_day(db: AsyncSession, employee: Employee, work_date: date, tz: ZoneInfo) -> list[Punch]:
    """Alle Stempelungen, die zum Arbeitstag gehören (inkl. Nachtschicht-Ende am Folgetag)."""
    window = await _punch_window(db, employee.id, work_date, work_date)
    max_span, _ = await _tenant_rules(db, employee.tenant_id)
    assignment = assign_shift_days(window, tz, max_span)
    return [p for p in window if assignment[p.id] == work_date]


async def punches_by_day(db: AsyncSession, employee: Employee, first: date, last: date, tz: ZoneInfo) -> dict[date, list[Punch]]:
    window = await _punch_window(db, employee.id, first, last)
    max_span, _ = await _tenant_rules(db, employee.tenant_id)
    assignment = assign_shift_days(window, tz, max_span)
    grouped: dict[date, list[Punch]] = {}
    for punch in window:
        if first <= assignment[punch.id] <= last:
            grouped.setdefault(assignment[punch.id], []).append(punch)
    return grouped


async def shift_day_of(db: AsyncSession, employee: Employee, punch: Punch, tz: ZoneInfo) -> date:
    """Arbeitstag, zu dem eine Stempelung gehört (bei Nachtschicht ggf. der Vortag)."""
    day = local_date(punch.timestamp_utc, tz)
    window = await _punch_window(db, employee.id, day - timedelta(days=1), day)
    max_span, _ = await _tenant_rules(db, employee.tenant_id)
    return assign_shift_days(window, tz, max_span).get(punch.id, day)


async def _pair_punches(
    db: AsyncSession, employee: Employee, work_date: date, tz: ZoneInfo, day_punches: list[Punch] | None = None
) -> tuple[int | None, SummaryStatus]:
    actual, status, _ = await pair_punches_detail(db, employee, work_date, tz, day_punches)
    return actual, status


async def pair_punches_detail(
    db: AsyncSession, employee: Employee, work_date: date, tz: ZoneInfo, day_punches: list[Punch] | None = None
) -> tuple[int | None, SummaryStatus, int | None]:
    """(Ist, Status, Pausenminuten). Pausen = gestempelte Pausen + Unterbrechungen zwischen Gehen
    und erneutem Kommen + gesetzlich zusätzlich abgezogener Rest; nur bei vollständigem Tag."""
    if day_punches is None:
        day_punches = await punches_for_day(db, employee, work_date, tz)

    if not day_punches:
        return None, SummaryStatus.OPEN_MISSING_PUNCH, None

    open_come: datetime | None = None
    open_break: datetime | None = None
    open_errand = False  # Dienstgang läuft (zählt als Arbeitszeit, kein Abzug)
    last_go: datetime | None = None
    gross_minutes = 0.0
    break_minutes = 0.0
    gap_minutes = 0.0  # Unterbrechungen zwischen Gehen und erneutem Kommen (zählen als Pause)
    malformed = False

    for punch in day_punches:
        if punch.punch_type == PunchType.COME:
            if open_come is not None:
                malformed = True
                break
            if last_go is not None:
                gap = (_naive_utc(punch.timestamp_utc) - _naive_utc(last_go)).total_seconds() / 60
                if gap >= MIN_BREAK_BLOCK_MINUTES:
                    gap_minutes += gap
            open_come = punch.timestamp_utc
        elif punch.punch_type == PunchType.GO:
            if open_come is None or open_break is not None or open_errand:
                malformed = True
                break
            gross_minutes += (punch.timestamp_utc - open_come).total_seconds() / 60
            open_come = None
            last_go = punch.timestamp_utc
        elif punch.punch_type == PunchType.BREAK_START:
            if open_come is None or open_break is not None or open_errand:
                malformed = True
                break
            open_break = punch.timestamp_utc
        elif punch.punch_type == PunchType.ERRAND_START:
            if open_come is None or open_break is not None or open_errand:
                malformed = True
                break
            open_errand = True
        elif punch.punch_type == PunchType.ERRAND_END:
            if not open_errand:
                malformed = True
                break
            open_errand = False
        elif punch.punch_type == PunchType.BREAK_END:
            if open_break is None:
                malformed = True
                break
            break_minutes += (punch.timestamp_utc - open_break).total_seconds() / 60
            open_break = None

    if malformed:
        # Widersprüchliche Buchungsfolge (z.B. doppeltes Kommen, Gehen ohne
        # Kommen, unpassende Pause) – das ist ein echter Datenfehler und keine
        # bloß offene Buchung, daher eigener Status statt OPEN_MISSING_PUNCH.
        return None, SummaryStatus.ERROR, None

    if open_come is not None:
        # Tag noch nicht abgeschlossen (kein GO). Gibt es danach schon Buchungen an
        # einem späteren Tag, hat der Mitarbeiter offensichtlich weitergestempelt und
        # diesen Tag vergessen abzuschließen -> "zu klären". Andernfalls ist das der
        # normale Fall "gerade im Haus" -> PRESENT, bzw. ON_BREAK, falls gerade eine
        # Pause läuft. Bewusst anhand der eigenen Stempelhistorie statt der
        # Systemzeit entschieden, damit das Verhalten unabhängig vom tatsächlichen
        # "heute" korrekt bleibt.
        has_later_punch = (
            await db.execute(
                select(Punch.id)
                .where(Punch.employee_id == employee.id, Punch.timestamp_utc > day_punches[-1].timestamp_utc)
                .limit(1)
            )
        ).first() is not None
        if has_later_punch:
            return None, SummaryStatus.OPEN_MISSING_PUNCH, None
        # Seit dem letzten "Kommen" ist mehr Zeit vergangen, als eine Schicht dauern darf
        # (Einstellungen → maximale Schichtlänge): das "Gehen" wurde vergessen, auch wenn der
        # Mitarbeiter seitdem nicht mehr gestempelt hat (z.B. direkt in den Urlaub).
        max_span, _ = await _tenant_rules(db, employee.tenant_id)
        if _utcnow() - _naive_utc(open_come) > max_span:
            return None, SummaryStatus.OPEN_MISSING_PUNCH, None
        if open_break is not None:
            return None, SummaryStatus.ON_BREAK, None
        if open_errand:
            return None, SummaryStatus.ON_ERRAND, None
        return None, SummaryStatus.PRESENT, None

    required_break = await _required_break_minutes(db, employee.tenant_id, gross_minutes, work_date)
    # Gestempelte Pausen und Unterbrechungen zwischen mehreren Kommen/Gehen erfüllen die
    # gesetzliche Pause; nur ein verbleibender Fehlbetrag wird zusätzlich abgezogen.
    shortfall = max(required_break - break_minutes - gap_minutes, 0.0)
    actual_minutes = max(round(gross_minutes - break_minutes - shortfall), 0)
    return actual_minutes, SummaryStatus.COMPLETE, round(break_minutes + gap_minutes + shortfall)


async def _required_break_minutes(
    db: AsyncSession, tenant_id: int, gross_minutes: float, work_date: date | None = None
) -> float:
    """Gesetzliche Mindestpause nach §4 ArbZG-Staffel (break_rules), falls der
    Mitarbeiter selbst keine oder zu wenig Pause gestempelt hat – mit der Staffel,
    die an diesem Tag galt (effektiv-datiert)."""
    day = work_date or date.today()
    result = await db.execute(
        select(BreakRule).where(
            BreakRule.tenant_id == tenant_id,
            BreakRule.valid_from <= day,
            or_(BreakRule.valid_to.is_(None), BreakRule.valid_to >= day),
        )
    )
    applicable = [r.deduct_minutes for r in result.scalars().all() if gross_minutes > r.min_work_minutes]
    return float(max(applicable)) if applicable else 0.0


async def maybe_auto_insert_break(
    db: AsyncSession, employee: Employee, go_punch: Punch, tz: ZoneInfo
) -> None:
    """Fügt beim Ausstempeln (GO) automatisch BREAK_START/BREAK_END-Punches ein,
    wenn employee.auto_break_enabled gesetzt ist, die ArbZG-Staffel (break_rules)
    für diese Schicht eine Pause verlangt und der Mitarbeiter selbst keine Pause
    gestempelt hat (manuelle Stempelungen haben Vorrang, siehe day_punches-Schleife
    unten). Materialisiert damit den bisher rein rechnerischen Pausenabzug
    (_required_break_minutes) als echte, auditierbare Punches."""
    if not employee.auto_break_enabled:
        return

    work_date = await shift_day_of(db, employee, go_punch, tz)
    day_punches = await punches_for_day(db, employee, work_date, tz)

    # Über ALLE Kommen/Gehen-Paare des Tages bis zu diesem Gehen rechnen: Unterbrechungen
    # zwischen den Paaren zählen als Pause, es wird nur der fehlende Rest automatisch gebucht.
    come_time: datetime | None = None
    last_go: datetime | None = None
    gross_minutes = 0.0
    gap_minutes = 0.0
    for punch in day_punches:
        if punch.id == go_punch.id:
            break
        if punch.punch_type == PunchType.COME:
            if last_go is not None:
                gap = (_naive_utc(punch.timestamp_utc) - _naive_utc(last_go)).total_seconds() / 60
                if gap >= MIN_BREAK_BLOCK_MINUTES:
                    gap_minutes += gap
            come_time = punch.timestamp_utc
        elif punch.punch_type == PunchType.GO:
            if come_time is not None:
                gross_minutes += (_naive_utc(punch.timestamp_utc) - _naive_utc(come_time)).total_seconds() / 60
            come_time = None
            last_go = punch.timestamp_utc
        elif punch.punch_type in (PunchType.BREAK_START, PunchType.BREAK_END):
            return  # manuelle Pause vorhanden -> automatische Stempelung unterbleibt

    if come_time is None:
        return

    last_pair_minutes = (_naive_utc(go_punch.timestamp_utc) - _naive_utc(come_time)).total_seconds() / 60
    gross_minutes += last_pair_minutes
    required_break = await _required_break_minutes(db, employee.tenant_id, gross_minutes, work_date)
    missing = min(required_break - gap_minutes, last_pair_minutes - 1)
    if missing <= 0:
        return

    break_end = go_punch.timestamp_utc - timedelta(seconds=1)
    break_start = break_end - timedelta(minutes=missing)
    idempotency_prefix = f"auto-break-{go_punch.id}"
    db.add(
        Punch(
            employee_id=employee.id,
            location_id=employee.location_id,
            punch_type=PunchType.BREAK_START,
            timestamp_utc=break_start,
            source=PunchSource.AUTO_BREAK,
            idempotency_key=f"{idempotency_prefix}-start",
        )
    )
    db.add(
        Punch(
            employee_id=employee.id,
            location_id=employee.location_id,
            punch_type=PunchType.BREAK_END,
            timestamp_utc=break_end,
            source=PunchSource.AUTO_BREAK,
            idempotency_key=f"{idempotency_prefix}-end",
        )
    )
    await db.commit()


async def recalculate_day(db: AsyncSession, employee: Employee, work_date: date) -> DayCalculation:
    """Nach einer Stempel-Änderung: Tages-Cache und Gleitzeitkonto ab diesem Tag neu berechnen.
    Liegt noch ein als PRESENT/ON_BREAK zwischengespeicherter früherer Tag vor, wird ab dort
    neu gerechnet (er ist durch die neue Buchung ggf. zum vergessenen "Gehen" geworden)."""
    stale = (
        await db.execute(
            select(func.min(DailySummary.work_date)).where(
                DailySummary.employee_id == employee.id,
                DailySummary.status.in_([SummaryStatus.PRESENT, SummaryStatus.ON_BREAK, SummaryStatus.ON_ERRAND]),
                DailySummary.work_date < work_date,
            )
        )
    ).scalar_one_or_none()
    # Vortag mit: eine Nachtschicht, die heute endet, gehört zum Vortag.
    await invalidate_balance(db, employee.id, min(stale or work_date, work_date - timedelta(days=1)))
    await rebuild_balance(db, employee)

    tz = await employee_timezone(db, employee)
    calculation = await calculate_day(db, employee, work_date, tz)
    if work_date > datetime.now(tz).date():
        # Zukünftiger Tag (z.B. vorab erfasste Korrektur): nur den Tages-Cache pflegen.
        await _upsert_daily_summary(db, employee.id, calculation)
        await db.commit()
    return calculation


async def _upsert_daily_summary(db: AsyncSession, employee_id: int, calculation: DayCalculation) -> None:
    result = await db.execute(
        select(DailySummary).where(
            DailySummary.employee_id == employee_id,
            DailySummary.work_date == calculation.work_date,
        )
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        summary = DailySummary(employee_id=employee_id, work_date=calculation.work_date)
        db.add(summary)
    summary.actual_minutes = calculation.actual_minutes
    summary.target_minutes = calculation.target_minutes or 0
    summary.status = calculation.status
    summary.flags = ",".join(calculation.flags) or None


# --- Gleitzeitkonto ------------------------------------------------------------------------------
#
# Das Konto zählt JEDEN Tag mit Soll ab dem Saldo-Beginn bis heute: Ist (Gutschrift bei Urlaub/
# Krank/Feiertag, sonst gestempelte Zeit, 0 ohne Stempelung) minus Soll. Der heutige Tag zählt erst,
# wenn er abgeschlossen ist (nicht während man anwesend ist). Die Zeilen in overtime_balances sind
# ein Cache: Employee.balance_through markiert, bis wohin sie aktuell sind. Jede Änderung, die
# Soll oder Ist verändert (Stempelung, Abwesenheit, Plan, Arbeitszeitmodell, Feiertag, Pausenregel …),
# setzt den Marker zurück (invalidate_*); gelesen wird immer über ensure_balance_current/balance_as_of,
# die ab dem Marker neu rechnen. Manuelle Korrekturbuchungen (BalanceAdjustment) kommen obendrauf.


async def invalidate_balance(db: AsyncSession, employee_id: int, from_date: date | None) -> None:
    """Markiert das Konto ab from_date als veraltet (None = komplett neu). Committet nicht."""
    if from_date is None:
        await db.execute(update(Employee).where(Employee.id == employee_id).values(balance_through=None))
        return
    await db.execute(
        update(Employee)
        .where(Employee.id == employee_id, Employee.balance_through >= from_date)
        .values(balance_through=from_date - timedelta(days=1))
    )


async def invalidate_tenant_balances(db: AsyncSession, tenant_id: int, from_date: date | None) -> None:
    """Für mandantenweite Änderungen (Feiertage, Pausenregeln, Schichtplanung an/aus, Saldo-Beginn)."""
    if from_date is None:
        await db.execute(update(Employee).where(Employee.tenant_id == tenant_id).values(balance_through=None))
        return
    await db.execute(
        update(Employee)
        .where(Employee.tenant_id == tenant_id, Employee.balance_through >= from_date)
        .values(balance_through=from_date - timedelta(days=1))
    )


async def balance_start(db: AsyncSession, employee: Employee) -> date | None:
    """Erster Kontotag, nie vor dem Eintritt.

    Mit Stichtag in den Einstellungen ("Gleitzeitkonten führen ab") beginnt das Konto für alle an
    diesem Tag – auch ohne Stempelung, fehlende Stunden zählen dann ins Minus. Ohne Stichtag
    beginnt es mit der ersten Stempelung (davor wurde das System noch nicht genutzt)."""
    setting = (
        await db.execute(select(AppSettings.balance_start_date).where(AppSettings.tenant_id == employee.tenant_id))
    ).scalar_one_or_none()
    candidates: list[date] = []
    if setting is not None:
        candidates.append(setting)
    else:
        first_punch = (
            await db.execute(select(func.min(Punch.timestamp_utc)).where(Punch.employee_id == employee.id))
        ).scalar_one_or_none()
        if first_punch is None:
            return None
        candidates.append(local_date(first_punch, await employee_timezone(db, employee)))
    if employee.hire_date is not None:
        candidates.append(employee.hire_date)
    return max(candidates)


_RUNNING_STATUSES = (SummaryStatus.PRESENT, SummaryStatus.ON_BREAK, SummaryStatus.ON_ERRAND)


async def rebuild_balance(db: AsyncSession, employee: Employee) -> None:
    """Rechnet das Konto ab dem ersten veralteten Tag (balance_through + 1, bzw. ab Beginn) bis
    heute neu und pflegt dabei den Tages-Cache (daily_summaries). Committet."""
    # Serialisiert parallele Neuberechnungen desselben Mitarbeiters (MySQL: Zeilensperre).
    locked = (await db.execute(select(Employee).where(Employee.id == employee.id).with_for_update())).scalar_one()
    tz = await employee_timezone(db, locked)
    today = datetime.now(tz).date()
    yesterday = today - timedelta(days=1)

    start = await balance_start(db, locked)
    if start is None:
        # Keine einzige Stempelung (mehr) – auch der Tages-Cache ("Zu klären") ist dann leer.
        await db.execute(delete(OvertimeBalance).where(OvertimeBalance.employee_id == locked.id))
        await db.execute(delete(DailySummary).where(DailySummary.employee_id == locked.id))
        locked.balance_through = yesterday
        await db.commit()
        return

    # Tage vor Kontobeginn ohne Stempelung können nach gelöschten Buchungen noch im Tages-Cache
    # stehen (z.B. war die gelöschte die erste Stempelung) – solche Einträge entfernen.
    stale = (
        await db.execute(
            select(DailySummary).where(DailySummary.employee_id == locked.id, DailySummary.work_date < start)
        )
    ).scalars().all()
    if stale:
        max_span, _ = await _tenant_rules(db, locked.tenant_id)
        earliest = min(s.work_date for s in stale)
        stamped = set(assign_shift_days(await _punch_window(db, locked.id, earliest, start), tz, max_span).values())
        for summary in stale:
            if summary.work_date not in stamped:
                await db.delete(summary)

    end = min(today, locked.termination_date) if locked.termination_date else today
    first = start if locked.balance_through is None else max(start, min(locked.balance_through + timedelta(days=1), today))
    # Frühere Tage, die beim letzten Rechnen noch liefen (anwesend/Pause/Dienstgang), können
    # inzwischen über die maximale Schichtlänge hinaus offen sein -> ab dort neu bewerten.
    still_running = (
        await db.execute(
            select(func.min(DailySummary.work_date)).where(
                DailySummary.employee_id == locked.id,
                DailySummary.status.in_(_RUNNING_STATUSES),
                DailySummary.work_date < today,
            )
        )
    ).scalar_one_or_none()
    if still_running is not None:
        first = max(start, min(first, still_running))
    # Flexible Wochensolls werden je Woche abgerechnet -> immer ab Wochenbeginn neu rechnen.
    first = max(start, first - timedelta(days=first.weekday()))

    await db.execute(
        delete(OvertimeBalance).where(
            OvertimeBalance.employee_id == locked.id,
            (OvertimeBalance.balance_date < start) | (OvertimeBalance.balance_date >= first),
        )
    )
    previous = (
        await db.execute(
            select(OvertimeBalance.running_balance_minutes)
            .where(OvertimeBalance.employee_id == locked.id, OvertimeBalance.balance_date < first)
            .order_by(OvertimeBalance.balance_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    running = previous or 0

    max_span, _ = await _tenant_rules(db, locked.tenant_id)
    punch_days = set(assign_shift_days(await _punch_window(db, locked.id, first, end), tz, max_span).values())
    summaries = {
        s.work_date: s
        for s in (
            await db.execute(
                select(DailySummary).where(
                    DailySummary.employee_id == locked.id,
                    DailySummary.work_date >= first,
                    DailySummary.work_date <= end,
                )
            )
        ).scalars().all()
    }

    report_no_punch_days = await reports_days_without_punches(db, locked.tenant_id)
    flex_target = 0.0  # Wochensoll-Anteile flexibler Tage der laufenden Woche
    flex_actual = 0
    day = first
    while day <= end:
        calc = await calculate_day(db, locked, day, tz)
        has_punch = day in punch_days

        # Tages-Cache ("Zu klären"): Tage mit Stempelung sowie vergangene Tage mit Soll – Letztere nur,
        # wenn der Mandant Arbeitstage ohne Stempelung meldet (sonst sind sie nie "zu klären").
        summary = summaries.get(day)
        if has_punch or (calc.target_minutes and day < today and report_no_punch_days):
            if summary is None:
                summary = DailySummary(employee_id=locked.id, work_date=day)
                db.add(summary)
            summary.actual_minutes = calc.actual_minutes
            summary.target_minutes = calc.target_minutes or 0
            summary.status = calc.status
            summary.flags = ",".join(calc.flags) or None
        elif summary is not None:
            await db.delete(summary)

        in_progress = day == today and calc.status not in (
            SummaryStatus.COMPLETE,
            SummaryStatus.HOLIDAY,
            SummaryStatus.ABSENCE,
            SummaryStatus.PLANNED_OFF,
        )
        day_row: OvertimeBalance | None = None
        if calc.target_minutes is not None and not in_progress:
            actual = calc.actual_minutes or 0
            delta = actual - calc.target_minutes
            running += delta
            day_row = OvertimeBalance(
                employee_id=locked.id,
                balance_date=day,
                daily_target_minutes=calc.target_minutes,
                daily_actual_minutes=actual,
                daily_delta_minutes=delta,
                running_balance_minutes=running,
            )
            db.add(day_row)
        if calc.flexible_share:
            flex_target += calc.flexible_share
            flex_actual += calc.actual_minutes or 0
        # Wochenabschluss für flexible Modelle: Sonntag (oder letzter Beschäftigungstag), nur wenn vorbei.
        if flex_target and (day.weekday() == 6 or day == end) and day < today:
            target = round(flex_target)
            delta = flex_actual - target
            running += delta
            if day_row is not None:  # Modellwechsel in der Woche: in die Tageszeile einrechnen
                day_row.daily_target_minutes += target
                day_row.daily_actual_minutes += flex_actual
                day_row.daily_delta_minutes += delta
                day_row.running_balance_minutes = running
            else:
                db.add(
                    OvertimeBalance(
                        employee_id=locked.id,
                        balance_date=day,
                        daily_target_minutes=target,
                        daily_actual_minutes=flex_actual,
                        daily_delta_minutes=delta,
                        running_balance_minutes=running,
                    )
                )
            flex_target, flex_actual = 0.0, 0
        elif day.weekday() == 6:
            flex_target, flex_actual = 0.0, 0
        day += timedelta(days=1)

    locked.balance_through = min(end, yesterday)
    await db.commit()


async def ensure_balance_current(db: AsyncSession, employee: Employee) -> None:
    """Vor jedem Lesen: veraltete Tage nachrechnen (rebuild_balance bewertet den heutigen Tag
    ohnehin immer neu, frühere nur, wenn der Marker zurückgesetzt wurde)."""
    await rebuild_balance(db, employee)


@dataclass
class BalanceInfo:
    running_minutes: int
    adjustment_minutes: int
    last_row: OvertimeBalance | None

    @property
    def total_minutes(self) -> int:
        return self.running_minutes + self.adjustment_minutes


async def balance_as_of(db: AsyncSession, employee: Employee, as_of: date | None = None, *, refresh: bool = True) -> BalanceInfo:
    """Kontostand (gerechnete Tage + Korrekturbuchungen) zum Stichtag (Standard: heute)."""
    if refresh:
        await ensure_balance_current(db, employee)
    stmt = select(OvertimeBalance).where(OvertimeBalance.employee_id == employee.id)
    adj = select(func.coalesce(func.sum(BalanceAdjustment.minutes), 0)).where(BalanceAdjustment.employee_id == employee.id)
    if as_of is not None:
        stmt = stmt.where(OvertimeBalance.balance_date <= as_of)
        adj = adj.where(BalanceAdjustment.effective_date <= as_of)
    last_row = (await db.execute(stmt.order_by(OvertimeBalance.balance_date.desc()).limit(1))).scalar_one_or_none()
    adjustments = int((await db.execute(adj)).scalar_one() or 0)
    return BalanceInfo(last_row.running_balance_minutes if last_row else 0, adjustments, last_row)
