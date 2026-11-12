"""Zeiten selbst eintragen (Stundenzettel, Einstellung „Zeiten selbst eintragen“).

Mitarbeiter tragen in „Mein Bereich“ für einen Tag Zeitspannen ein (Arbeit, optional Pausen darin).
Es gibt dafür kein zweites Datenmodell: Eine Spanne wird zu den bekannten Stempelungen Kommen/Gehen
(Pause Start/Ende) mit der Quelle SELF_ENTRY – die Tagesberechnung, Pausenregeln, „Zu klären“, Konto,
Monatsabschluss, Lohn-Export und API sehen sie wie jede andere Stempelung.

- Ohne Genehmigung entstehen die Stempelungen sofort (Audit TIME_ENTRY_CREATED).
- Mit Genehmigung entsteht ein Korrekturantrag der Art TIME_ENTRY mit denselben Stempelungen als
  Positionen; erst „Übernehmen“ unter „Zu klären“ legt sie an (app/api/punch_correction_requests.py).
  Bis dahin zählt der Antrag nirgends (Soll/Ist/Konto, API).

Abgelehnt werden (422): Tage in der Zukunft oder vor dem erlaubten Zeitraum, Spannen, die noch nicht
vorbei sind, außerhalb der Beschäftigung, länger als die maximale Schichtlänge, Überschneidungen mit
vorhandenen Stempelungen oder offenen Anträgen. Abgeschlossene Monate: 409 wie überall.
Keine Rundung, kein Schätzen: eingetragen wird genau, was der Mitarbeiter angibt.
"""
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import (
    AppSettings,
    CorrectionRequestKind,
    CorrectionRequestStatus,
    Employee,
    Punch,
    PunchCorrectionRequest,
    PunchSource,
    PunchType,
    SummaryStatus,
)
from app.schemas.time_entry import TimeSpanIn
from app.services import project_service
from app.services import timesheet_service as ts
from app.services.period_service import ensure_period_open

MAX_BACKDATE_DAYS = 62
NOTE_MAX_LENGTH = 200

Interval = tuple[datetime, datetime]

_PAIRS = {
    PunchType.COME: (PunchType.GO, "WORK"),
    PunchType.BREAK_START: (PunchType.BREAK_END, "BREAK"),
}


@dataclass(frozen=True)
class EntryRules:
    enabled: bool
    approval: bool
    backdate_days: int


def rules_of(settings_row: AppSettings) -> EntryRules:
    days = settings_row.self_time_entry_backdate_days
    days = 7 if days is None else max(0, min(int(days), MAX_BACKDATE_DAYS))
    return EntryRules(
        enabled=bool(settings_row.self_time_entry_enabled),
        approval=settings_row.self_time_entry_approval is not False,
        backdate_days=days,
    )


def earliest_date(rules: EntryRules, today: date) -> date:
    return today - timedelta(days=rules.backdate_days)


def _local_to_utc(day: date, minutes: int, tz: ZoneInfo) -> datetime:
    local = datetime.combine(day + timedelta(days=minutes // 1440), time((minutes % 1440) // 60, minutes % 60), tz)
    return local.astimezone(UTC).replace(tzinfo=None)


def spans_to_items(spans: list[TimeSpanIn], extras: list[dict] | None = None) -> list[dict]:
    """Spannen → Stempelungen (Positionen wie bei Korrekturanträgen: Art, "HH:MM", Folgetag), in
    zeitlicher Reihenfolge; zum selben Zeitpunkt ein Ende vor einem Beginn (lückenlose Spannen).
    extras[i] = Zusatzangaben für das "Kommen" der i-ten Spanne (z. B. Projekt)."""
    events: list[tuple[int, int, int, dict]] = []
    for index, span in enumerate(spans):
        start_type, end_type = (
            (PunchType.COME, PunchType.GO) if span.kind == "WORK" else (PunchType.BREAK_START, PunchType.BREAK_END)
        )
        start_item = {"punch_type": start_type.value, **_clock(span.start_minutes())}
        if span.kind == "WORK" and extras is not None and extras[index]:
            start_item.update(extras[index])
        events.append((span.start_minutes(), 1, index, start_item))
        events.append((span.end_minutes(), 0, index, {"punch_type": end_type.value, **_clock(span.end_minutes())}))
    events.sort(key=lambda e: (e[0], e[1], e[2]))
    return [item for *_, item in events]


def _clock(minutes: int) -> dict:
    return {"time": f"{(minutes % 1440) // 60:02d}:{minutes % 60:02d}", "next_day": minutes >= 1440}


def item_minutes(item: dict) -> int:
    hour, minute = (int(v) for v in item["time"].split(":"))
    return hour * 60 + minute + (1440 if item.get("next_day") else 0)


def items_to_intervals(work_date: date, items: list[dict], tz: ZoneInfo) -> list[tuple[str, Interval, dict]]:
    """Positionen → (Art WORK/BREAK, (Beginn, Ende) in naiver UTC, Position des Beginns)."""
    result: list[tuple[str, Interval, dict]] = []
    open_items: dict[PunchType, dict] = {}
    for item in items:
        punch_type = PunchType(item["punch_type"])
        if punch_type in _PAIRS:
            open_items[punch_type] = item
            continue
        for start_type, (end_type, kind) in _PAIRS.items():
            if punch_type == end_type and start_type in open_items:
                start_item = open_items.pop(start_type)
                result.append((
                    kind,
                    (_local_to_utc(work_date, item_minutes(start_item), tz), _local_to_utc(work_date, item_minutes(item), tz)),
                    start_item,
                ))
    return result


async def occupied(
    db: AsyncSession, employee: Employee, work_date: date, *, exclude_request_id: int | None = None
) -> tuple[list[Interval], list[datetime]]:
    """Belegte Zeiten um den Tag herum: Kommen–Gehen aller Stempelungen (ein "Kommen" ohne "Gehen" bis
    zur maximalen Schichtlänge), einzelne Stempelungen außerhalb davon als Zeitpunkte, dazu die
    Arbeitsspannen offener Zeit-Anträge."""
    tz = await ts.employee_timezone(db, employee)
    max_span, _ = await ts._tenant_rules(db, employee.tenant_id)
    punches = await ts._punch_window(db, employee.id, work_date - timedelta(days=1), work_date + timedelta(days=1))
    intervals: list[Interval] = []
    points: list[datetime] = []
    open_start: datetime | None = None
    for punch in punches:
        moment = ts._naive_utc(punch.timestamp_utc)
        if punch.punch_type == PunchType.COME:
            if open_start is not None:
                # "Kommen" ohne "Gehen" und danach erneut "Kommen": belegt höchstens die maximale Schichtlänge
                intervals.append((open_start, min(moment, open_start + max_span)))
            open_start = moment
        elif punch.punch_type == PunchType.GO:
            if open_start is not None:
                intervals.append((open_start, moment))
                open_start = None
            else:
                points.append(moment)
        elif open_start is None:
            points.append(moment)
    if open_start is not None:
        intervals.append((open_start, open_start + max_span))

    stmt = select(PunchCorrectionRequest).where(
        PunchCorrectionRequest.employee_id == employee.id,
        PunchCorrectionRequest.kind == CorrectionRequestKind.TIME_ENTRY,
        PunchCorrectionRequest.status == CorrectionRequestStatus.PENDING,
        PunchCorrectionRequest.work_date >= work_date - timedelta(days=1),
        PunchCorrectionRequest.work_date <= work_date + timedelta(days=1),
    )
    if exclude_request_id is not None:
        stmt = stmt.where(PunchCorrectionRequest.id != exclude_request_id)
    for request in (await db.execute(stmt)).scalars().all():
        for kind, interval, _ in items_to_intervals(request.work_date, json.loads(request.items), tz):
            if kind == "WORK":
                intervals.append(interval)
    return intervals, points


def overlaps(new: Interval, intervals: list[Interval], points: list[datetime]) -> bool:
    """Echte Überschneidung; aneinander anschließende Spannen (Ende = Beginn) sind erlaubt."""
    start, end = new
    return any(start < b and a < end for a, b in intervals) or any(start < p < end for p in points)


def _fmt(moment: datetime, tz: ZoneInfo) -> str:
    return moment.replace(tzinfo=UTC).astimezone(tz).strftime("%H:%M")


async def check_entry(
    db: AsyncSession,
    employee: Employee,
    work_date: date,
    items: list[dict],
    *,
    rules: EntryRules | None,
    exclude_request_id: int | None = None,
) -> list[tuple[str, Interval, dict]]:
    """Prüft einen Eintrag (rules=None: Genehmigung durch HR – dann gilt der Zeitraum nicht mehr, nur
    die harten Regeln). Liefert die Spannen in UTC."""
    tz = await ts.employee_timezone(db, employee)
    today = ts.today_in(tz)
    if work_date > today:
        raise AppError(422, "TIME_ENTRY_IN_FUTURE", "Zeiten lassen sich nur für heute oder vergangene Tage eintragen.")
    if rules is not None and work_date < earliest_date(rules, today):
        limit = "nur für heute" if rules.backdate_days == 0 else f"höchstens {rules.backdate_days} Tage rückwirkend"
        raise AppError(422, "TIME_ENTRY_TOO_OLD", f"Zeiten lassen sich {limit} eintragen.")
    if (employee.hire_date is not None and work_date < employee.hire_date) or (
        employee.termination_date is not None and work_date > employee.termination_date
    ):
        raise AppError(422, "TIME_ENTRY_OUTSIDE_EMPLOYMENT", "An diesem Tag besteht keine Beschäftigung.")
    await ensure_period_open(db, employee.id, work_date)

    spans = items_to_intervals(work_date, items, tz)
    now = ts._utcnow()
    max_span, _ = await ts._tenant_rules(db, employee.tenant_id)
    intervals, points = await occupied(db, employee, work_date, exclude_request_id=exclude_request_id)
    for kind, (start, end), _ in spans:
        if end > now:
            raise AppError(
                422, "TIME_ENTRY_IN_FUTURE",
                f"Die Zeit {_fmt(start, tz)}–{_fmt(end, tz)} ist noch nicht vorbei – bitte erst danach eintragen.",
            )
        if kind != "WORK":
            continue
        if end - start > max_span:
            hours = int(max_span.total_seconds() // 3600)
            raise AppError(422, "TIME_ENTRY_TOO_LONG", f"Eine Spanne darf höchstens {hours} Stunden lang sein.")
        if overlaps((start, end), intervals, points):
            raise AppError(
                422, "TIME_ENTRY_OVERLAP",
                f"{_fmt(start, tz)}–{_fmt(end, tz)} überschneidet sich mit vorhandenen Zeiten oder einem offenen "
                "Antrag an diesem Tag.",
            )
    return spans


async def create_punches(
    db: AsyncSession,
    employee: Employee,
    work_date: date,
    items: list[dict],
    *,
    account_id: int | None,
    reason: str | None = None,
) -> list[Punch]:
    """Legt die Stempelungen eines (geprüften) Eintrags mit der Quelle "selbst eingetragen" an –
    committet nicht. Ergibt der Tag danach eine widersprüchliche Buchungsfolge, die vorher nicht da war,
    wird abgelehnt (422) – der Aufrufer rollt zurück."""
    tz = await ts.employee_timezone(db, employee)
    _, before, _ = await ts.pair_punches_detail(db, employee, work_date, tz)
    known = await project_service.existing_project_ids(
        db, employee.tenant_id, {i["project_id"] for i in items if i.get("project_id") is not None}
    )
    created: list[Punch] = []
    for item in items:
        punch = Punch(
            tenant_id=employee.tenant_id,
            employee_id=employee.id,
            location_id=employee.location_id,
            punch_type=PunchType(item["punch_type"]),
            timestamp_utc=_local_to_utc(work_date, item_minutes(item), tz),
            source=PunchSource.SELF_ENTRY,
            created_by_account_id=account_id,
            correction_reason=reason,
            idempotency_key=str(uuid.uuid4()),
        )
        apply_item_extras(punch, item, known)
        db.add(punch)
        created.append(punch)
    await db.flush()
    _, after, _ = await ts.pair_punches_detail(db, employee, work_date, tz)
    if after == SummaryStatus.ERROR and before != SummaryStatus.ERROR:
        raise AppError(
            422, "TIME_ENTRY_CONFLICT",
            "Die Zeiten passen nicht zu den vorhandenen Stempelungen dieses Tages (widersprüchliche Folge).",
        )
    return created


def apply_item_extras(punch: Punch, item: dict, known_projects: set[int]) -> None:
    """Projekt und Tätigkeitsnotiz einer Position auf das "Kommen" übertragen. Ein inzwischen gelöschtes
    Projekt (offener Antrag) entfällt."""
    if punch.punch_type != PunchType.COME:
        return
    project_id = item.get("project_id")
    punch.project_id = project_id if project_id in known_projects else None
    punch.activity_note = item.get("note") or None


async def after_change(db: AsyncSession, employee: Employee, work_date: date) -> None:
    """Automatische Pausen des Tages neu setzen, Tag und Konto neu rechnen (wie bei HR-Buchungen)."""
    tz = await ts.employee_timezone(db, employee)
    await ts.refresh_auto_breaks(db, employee, work_date, tz)
    await ts.recalculate_day(db, employee, work_date)


def describe(work_date: date, items: list[dict], tz: ZoneInfo) -> str:
    parts = []
    for kind, (start, end), _ in items_to_intervals(work_date, items, tz):
        label = f"{_fmt(start, tz)}–{_fmt(end, tz)}"
        parts.append(label if kind == "WORK" else f"Pause {label}")
    return ", ".join(parts)
