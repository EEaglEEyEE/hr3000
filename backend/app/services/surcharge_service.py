from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, Punch, PunchType, SummaryStatus, SurchargeKind, SurchargeRule
from app.services.timesheet_service import (
    _is_holiday,
    _required_break_minutes,
    calculate_day,
    employee_timezone,
    punches_for_day,
    today_in,
)

_ONE_DAY = timedelta(days=1)
Interval = tuple[datetime, datetime]


@dataclass
class SurchargeTotal:
    rule: SurchargeRule
    minutes: int

    @property
    def equivalent_minutes(self) -> float:
        """Minuten x Prozentsatz – die "Zuschlagsstunden" in Normalstunden umgerechnet."""
        return self.minutes * float(self.rule.percent) / 100


async def active_rules(db: AsyncSession, tenant_id: int) -> list[SurchargeRule]:
    return list(
        (
            await db.execute(
                select(SurchargeRule)
                .where(SurchargeRule.tenant_id == tenant_id, SurchargeRule.active.is_(True))
                .order_by(SurchargeRule.id)
            )
        ).scalars().all()
    )


def _local_naive(dt: datetime, tz: ZoneInfo) -> datetime:
    aware = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return aware.astimezone(tz).replace(tzinfo=None)


async def work_intervals(db: AsyncSession, employee: Employee, work_date: date, tz: ZoneInfo) -> list[Interval]:
    """Reine Arbeitsintervalle (lokale, naive Zeit) des Tages: Kommen..Gehen abzüglich der
    gestempelten Pausen. Nur bei sauberer Buchungsfolge – sonst leer. Fehlt gegenüber der
    gesetzlichen Mindestpause noch Pause, wird der Rest (wie bei der automatischen Pause)
    am Tagesende abgezogen."""
    # Schicht über Mitternacht: die Intervalle reichen dann in den Folgetag hinein.
    punches = await punches_for_day(db, employee, work_date, tz)

    shifts: list[Interval] = []
    breaks: list[Interval] = []
    open_come: datetime | None = None
    open_break: datetime | None = None
    for punch in punches:
        at = _local_naive(punch.timestamp_utc, tz)
        if punch.punch_type == PunchType.COME:
            if open_come is not None:
                return []
            open_come = at
        elif punch.punch_type == PunchType.GO:
            if open_come is None or open_break is not None:
                return []
            shifts.append((open_come, at))
            open_come = None
        elif punch.punch_type == PunchType.BREAK_START:
            if open_come is None or open_break is not None:
                return []
            open_break = at
        elif punch.punch_type == PunchType.BREAK_END:
            if open_break is None:
                return []
            breaks.append((open_break, at))
            open_break = None
    if open_come is not None or open_break is not None or not shifts:
        return []

    pieces: list[Interval] = []
    for start, end in shifts:
        cursor = start
        for b_start, b_end in sorted(b for b in breaks if b[0] < end and b[1] > start):
            if b_start > cursor:
                pieces.append((cursor, min(b_start, end)))
            cursor = max(cursor, b_end)
        if cursor < end:
            pieces.append((cursor, end))

    gross = sum((end - start).total_seconds() for start, end in shifts) / 60
    break_minutes = sum((end - start).total_seconds() for start, end in breaks) / 60
    # Unterbrechungen zwischen mehreren Kommen/Gehen zählen als Pause (ab 15 Min., wie timesheet_service).
    break_minutes += sum(
        gap
        for gap in (
            (shifts[i + 1][0] - shifts[i][1]).total_seconds() / 60 for i in range(len(shifts) - 1)
        )
        if gap >= 15
    )
    shortfall = max(await _required_break_minutes(db, employee.tenant_id, gross, work_date) - break_minutes, 0.0)
    while shortfall > 0 and pieces:
        start, end = pieces[-1]
        length = (end - start).total_seconds() / 60
        if length > shortfall:
            pieces[-1] = (start, end - timedelta(minutes=shortfall))
            shortfall = 0
        else:
            pieces.pop()
            shortfall -= length
    return pieces


def _rule_windows(rule: SurchargeRule, day: date, holidays: set[date]) -> list[Interval]:
    """Zeitfenster der Regel, die die Schicht des Tages `day` berühren können (lokale, naive Zeit).
    Sonntag/Feiertag richten sich nach dem Kalendertag der Minute – eine Nachtschicht von Samstag
    auf Sonntag bekommt ab 0 Uhr Sonntagszuschlag."""
    midnight = lambda d: datetime.combine(d, time.min)  # noqa: E731
    days = (day, day + _ONE_DAY)
    if rule.kind == SurchargeKind.SUNDAY:
        return [(midnight(d), midnight(d + _ONE_DAY)) for d in days if d.weekday() == 6]
    if rule.kind == SurchargeKind.HOLIDAY:
        return [(midnight(d), midnight(d + _ONE_DAY)) for d in days if d in holidays]
    if rule.kind in (SurchargeKind.NIGHT, SurchargeKind.CUSTOM) and rule.start_time and rule.end_time:
        windows: list[Interval] = []
        # Fenster des Vortags (über Mitternacht), des Tages und des Folgetags (Nachtschicht).
        for start_day in (day - _ONE_DAY, day, day + _ONE_DAY):
            if not (rule.weekdays_mask >> start_day.weekday()) & 1:
                continue
            start = datetime.combine(start_day, rule.start_time)
            end = datetime.combine(start_day, rule.end_time)
            if end <= start:
                end += _ONE_DAY
            windows.append((start, end))
        return windows
    return []


def _seconds(left: datetime, right: datetime, tz: ZoneInfo | None) -> float:
    """Echte Dauer zwischen zwei lokalen Zeitpunkten (bei Zeitumstellung ±1 Std. gegenüber der Wanduhr)."""
    if tz is None:
        return (right - left).total_seconds()
    return (right.replace(tzinfo=tz).astimezone(UTC) - left.replace(tzinfo=tz).astimezone(UTC)).total_seconds()


def classify_intervals(
    intervals: list[Interval],
    rules: list[SurchargeRule],
    day: date,
    is_holiday: bool | set[date],
    tz: ZoneInfo | None = None,
) -> dict[int, float]:
    """Sekunden je Regel-ID für die Arbeitsintervalle eines Tages. Zeitbasierte Regeln
    (Nacht/Sonntag/Feiertag/frei) werden über elementare Segmente ausgewertet, damit
    Regeln einer exclusive_group nie doppelt zählen (es gilt je Segment der höchste Satz)."""
    totals: dict[int, float] = {}
    holidays = is_holiday if isinstance(is_holiday, set) else ({day} if is_holiday else set())
    timed = [r for r in rules if r.kind != SurchargeKind.OVERTIME]
    windows = {r.id: _rule_windows(r, day, holidays) for r in timed}

    for start, end in intervals:
        overlaps: list[tuple[SurchargeRule, datetime, datetime]] = []
        for rule in timed:
            for w_start, w_end in windows[rule.id]:
                lo, hi = max(start, w_start), min(end, w_end)
                if lo < hi:
                    overlaps.append((rule, lo, hi))
        if not overlaps:
            continue
        points = sorted({p for _, lo, hi in overlaps for p in (lo, hi)})
        for left, right in zip(points, points[1:], strict=False):
            covering = [r for r, lo, hi in overlaps if lo <= left and hi >= right]
            chosen: dict[str, SurchargeRule] = {}
            for rule in covering:
                if rule.exclusive_group is None:
                    totals[rule.id] = totals.get(rule.id, 0.0) + _seconds(left, right, tz)
                    continue
                best = chosen.get(rule.exclusive_group)
                if best is None or float(rule.percent) > float(best.percent):
                    chosen[rule.exclusive_group] = rule
            for rule in chosen.values():
                totals[rule.id] = totals.get(rule.id, 0.0) + _seconds(left, right, tz)
    return totals


async def compute_surcharges(
    db: AsyncSession,
    employee: Employee,
    date_from: date,
    date_to: date,
    rules: list[SurchargeRule] | None = None,
) -> list[SurchargeTotal]:
    """Zuschlagsminuten je aktiver Regel über den Zeitraum (nur tatsächlich gearbeitete Zeit)."""
    rules = await active_rules(db, employee.tenant_id) if rules is None else rules
    if not rules:
        return []
    tz = await employee_timezone(db, employee)
    seconds: dict[int, float] = {r.id: 0.0 for r in rules}
    overtime_rules = [r for r in rules if r.kind == SurchargeKind.OVERTIME]

    date_to = min(date_to, today_in(tz))  # nur bis heute
    current = date_from
    while current <= date_to:
        intervals = await work_intervals(db, employee, current, tz)
        if intervals:
            holidays = {d for d in (current, current + _ONE_DAY) if await _is_holiday(db, employee, d)}
            for rule_id, secs in classify_intervals(intervals, rules, current, holidays, tz).items():
                seconds[rule_id] += secs
        if overtime_rules:
            calc = await calculate_day(db, employee, current, tz)
            if calc.status == SummaryStatus.COMPLETE and calc.target_minutes is not None:
                extra = max((calc.actual_minutes or 0) - calc.target_minutes, 0) * 60
                for rule in overtime_rules:
                    seconds[rule.id] += extra
        current += _ONE_DAY

    return [SurchargeTotal(rule=r, minutes=round(seconds[r.id] / 60)) for r in rules]
