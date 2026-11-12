"""Zeiten selbst eintragen (Stundenzettel in „Mein Bereich“), siehe services/time_entry_service.py.

Nur der Mitarbeiter selbst; HR bucht direkt (Zeiterfassung → „Stempelung nachtragen“) und entscheidet
Anträge unter „Zu klären“ → „Korrekturanträge“ (PATCH /punch-correction-requests/{id}/decide).
"""
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.db import get_db
from app.errors import AppError
from app.models import (
    AuditAction,
    CorrectionRequestKind,
    CorrectionRequestStatus,
    Employee,
    Punch,
    PunchCorrectionRequest,
    PunchSource,
    PunchType,
    SummaryStatus,
)
from app.schemas.time_entry import (
    PendingTimeEntry,
    TimeEntryCreate,
    TimeEntryDay,
    TimeEntryResult,
    TimeEntryWeek,
    TimeSpanOut,
)
from app.schemas.project import ProjectOption
from app.services import project_service
from app.services import time_entry_service as entries
from app.services import timesheet_service as ts
from app.services.audit_service import log_action
from app.services.notification_service import notify_time_entry_requested
from app.services.period_service import ensure_period_open, locked_months
from app.services.settings_service import get_or_create_settings

router = APIRouter(tags=["time_entries"])

_MAX_RANGE_DAYS = 31


def _employee(actor: Actor) -> Employee:
    if actor.employee is None or actor.device is not None:
        raise AppError(403, "FORBIDDEN", "Zeiten trägt der Mitarbeiter selbst ein.")
    return actor.employee


async def _rules(db: AsyncSession, actor: Actor) -> entries.EntryRules:
    rules = entries.rules_of(await get_or_create_settings(db, actor.tenant_id))
    if not rules.enabled:
        raise AppError(403, "SELF_TIME_ENTRY_DISABLED", "Zeiten selbst eintragen ist nicht freigeschaltet.")
    return rules


def _spans_from_punches(
    punches: list[Punch], *, deletable_window: bool
) -> list[TimeSpanOut]:
    """Kommen–Gehen und Pausen eines Tages als Spannen (offenes Ende = None)."""
    spans: list[TimeSpanOut] = []
    open_spans: dict[PunchType, TimeSpanOut] = {}
    starts = {PunchType.COME: "WORK", PunchType.BREAK_START: "BREAK"}
    ends = {PunchType.GO: PunchType.COME, PunchType.BREAK_END: PunchType.BREAK_START}
    for punch in punches:
        if punch.punch_type in starts:
            span = TimeSpanOut(
                kind=starts[punch.punch_type], start=punch.timestamp_utc, end=None, source=punch.source, punch_id=punch.id,
                project_id=punch.project_id, note=punch.activity_note,
                deletable=deletable_window and punch.punch_type == PunchType.COME and punch.source == PunchSource.SELF_ENTRY
                and not punch.corrected,
            )
            spans.append(span)
            open_spans[punch.punch_type] = span
        elif punch.punch_type in ends and ends[punch.punch_type] in open_spans:
            span = open_spans.pop(ends[punch.punch_type])
            span.end = punch.timestamp_utc
            if punch.source != PunchSource.SELF_ENTRY or punch.corrected:
                span.deletable = False
    return spans


@router.get("/me/time-entries", response_model=TimeEntryWeek)
async def list_own_time_entries(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> TimeEntryWeek:
    """Stundenzettel für einen Zeitraum (höchstens 31 Tage, z. B. eine Woche Mo–So): je Tag die
    wirksamen Spannen (mit Quelle), offene Anträge und die Ist-Zeit."""
    employee = _employee(actor)
    if date_to < date_from or (date_to - date_from).days >= _MAX_RANGE_DAYS:
        raise AppError(400, "INVALID_RANGE", "Bitte einen Zeitraum von höchstens 31 Tagen wählen.")
    rules = entries.rules_of(await get_or_create_settings(db, actor.tenant_id))
    tz = await ts.employee_timezone(db, employee)
    today = ts.today_in(tz)
    earliest = entries.earliest_date(rules, today)
    locked = await locked_months(db, employee.id)
    by_day = await ts.punches_by_day(db, employee, date_from, date_to, tz)
    pending_rows = (
        await db.execute(
            select(PunchCorrectionRequest)
            .where(
                PunchCorrectionRequest.employee_id == employee.id,
                PunchCorrectionRequest.kind == CorrectionRequestKind.TIME_ENTRY,
                PunchCorrectionRequest.status == CorrectionRequestStatus.PENDING,
                PunchCorrectionRequest.work_date >= date_from,
                PunchCorrectionRequest.work_date <= date_to,
            )
            .order_by(PunchCorrectionRequest.id)
        )
    ).scalars().all()

    days: list[TimeEntryDay] = []
    day = date_from
    while day <= date_to:
        employed = (employee.hire_date is None or day >= employee.hire_date) and (
            employee.termination_date is None or day <= employee.termination_date
        )
        in_window = earliest <= day <= today
        open_period = (day.year, day.month) not in locked
        can_enter = rules.enabled and in_window and employed and open_period
        punches = by_day.get(day, [])
        actual = None
        if punches and day <= today:
            calculation = await ts.calculate_day(db, employee, day, tz)
            actual = calculation.actual_minutes if calculation.status == SummaryStatus.COMPLETE else None
        pending = [
            PendingTimeEntry(
                request_id=row.id,
                comment=row.reason or None,
                created_at=row.created_at,
                spans=[
                    TimeSpanOut(kind=kind, start=start, end=end, project_id=item.get("project_id"), note=item.get("note"))
                    for kind, (start, end), item in entries.items_to_intervals(row.work_date, json.loads(row.items), tz)
                ],
            )
            for row in pending_rows
            if row.work_date == day
        ]
        days.append(
            TimeEntryDay(
                work_date=day,
                can_enter=can_enter,
                spans=_spans_from_punches(
punches, deletable_window=can_enter and not rules.approval),
                pending=pending,
                actual_minutes=actual,
            )
        )
        day += timedelta(days=1)
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    options: list[ProjectOption] = []
    names: dict[int, str] = {}
    if settings_row.project_times_enabled:
        options = [
            ProjectOption(id=p.id, label=project_service.project_label(p, customer), valid_from=p.valid_from, valid_to=p.valid_to)
            for p, customer in await project_service.selectable_projects(db, actor.tenant_id)
        ]
        used = {s.project_id for d in days for s in [*d.spans, *(x for p in d.pending for x in p.spans)] if s.project_id}
        names = await project_service.project_names(db, actor.tenant_id, used)
    return TimeEntryWeek(
        projects_enabled=settings_row.project_times_enabled,
        project_required=settings_row.project_times_enabled and settings_row.project_required,
        projects=options,
        project_names=names,
        enabled=rules.enabled,
        approval_required=rules.approval,
        backdate_days=rules.backdate_days,
        earliest_date=earliest,
        today=today,
        timezone=tz.key,
        days=days,
    )


@router.post("/me/time-entries", response_model=TimeEntryResult, status_code=201)
async def create_own_time_entry(
    payload: TimeEntryCreate,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> TimeEntryResult:
    """Spannen eines Tages eintragen: mit Genehmigung als Antrag (zählt erst nach „Übernehmen“), sonst
    sofort wirksam (Quelle „selbst eingetragen“, Audit)."""
    employee = _employee(actor)
    rules = await _rules(db, actor)
    items = entries.spans_to_items(payload.spans, await _project_extras(db, actor, payload))
    await entries.check_entry(db, employee, payload.work_date, items, rules=rules)
    tz = await ts.employee_timezone(db, employee)

    if rules.approval:
        row = PunchCorrectionRequest(
            tenant_id=actor.tenant_id,
            employee_id=employee.id,
            work_date=payload.work_date,
            kind=CorrectionRequestKind.TIME_ENTRY,
            items=json.dumps(items),
            reason=payload.comment or "",
            status=CorrectionRequestStatus.PENDING,
        )
        db.add(row)
        await notify_time_entry_requested(db, actor.tenant_id, employee, payload.work_date)
        await db.commit()
        await db.refresh(row)
        return TimeEntryResult(status="PENDING", request_id=row.id)

    try:
        created = await entries.create_punches(
            db, employee, payload.work_date, items, account_id=actor.account_id, reason=payload.comment
        )
    except AppError:
        await db.rollback()
        raise
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.TIME_ENTRY_CREATED,
        entity_type="punch",
        entity_id=created[0].id,
        detail=f"{employee.first_name} {employee.last_name}, {payload.work_date.isoformat()}: "
        f"{entries.describe(payload.work_date, items, tz)}",
    )
    await db.commit()
    punch_ids = [p.id for p in created]
    await entries.after_change(db, employee, payload.work_date)
    return TimeEntryResult(status="APPLIED", punch_ids=punch_ids)


async def _project_extras(db: AsyncSession, actor: Actor, payload: TimeEntryCreate) -> list[dict] | None:
    """Projekt und Tätigkeit je Arbeitszeit prüfen (Schalter, Pflicht, Projekt gültig am Tag)."""
    settings_row = await get_or_create_settings(db, actor.tenant_id)
    work = [s for s in payload.spans if s.kind == "WORK"]
    if not settings_row.project_times_enabled:
        if any(s.project_id is not None or s.note is not None for s in work):
            raise AppError(422, "PROJECT_TIMES_DISABLED", "Projektzeiten sind nicht eingeschaltet.")
        return None
    if settings_row.project_required and any(s.project_id is None for s in work):
        raise AppError(422, "PROJECT_REQUIRED", "Bitte jeder Arbeitszeit ein Projekt zuordnen.")
    for project_id in {s.project_id for s in work if s.project_id is not None}:
        await project_service.ensure_project_usable(db, actor.tenant_id, project_id, payload.work_date)
    return [
        {k: v for k, v in (("project_id", s.project_id), ("note", s.note)) if v is not None} if s.kind == "WORK" else {}
        for s in payload.spans
    ]


@router.delete("/me/time-entries/requests/{request_id}", status_code=204)
async def withdraw_own_time_entry(
    request_id: int,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Eigenen, noch offenen Antrag zurückziehen (er hatte nie Wirkung und verschwindet)."""
    employee = _employee(actor)
    row = await db.get(PunchCorrectionRequest, request_id)
    if row is None or row.employee_id != employee.id or row.kind != CorrectionRequestKind.TIME_ENTRY:
        raise AppError(404, "CORRECTION_NOT_FOUND", "Antrag nicht gefunden.")
    if row.status != CorrectionRequestStatus.PENDING:
        raise AppError(400, "NOT_PENDING", "Dieser Antrag wurde bereits entschieden.")
    await db.delete(row)
    await db.commit()


@router.delete("/me/time-entries/{punch_id}", status_code=204)
async def delete_own_time_entry(
    punch_id: int,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Eine selbst eingetragene Spanne wieder löschen (Kommen samt Gehen und eingetragener Pausen
    darin) – nur ohne Genehmigungspflicht, im erlaubten Zeitraum und solange HR sie nicht korrigiert
    hat. Mit Genehmigungspflicht geht das nur über einen Korrekturantrag."""
    employee = _employee(actor)
    rules = await _rules(db, actor)
    if rules.approval:
        raise AppError(
            403, "TIME_ENTRY_LOCKED", "Genehmigte Zeiten lassen sich nur über einen Korrekturantrag ändern."
        )
    punch = await db.get(Punch, punch_id)
    if (
        punch is None
        or punch.employee_id != employee.id
        or punch.source != PunchSource.SELF_ENTRY
        or punch.punch_type != PunchType.COME
    ):
        raise AppError(404, "PUNCH_NOT_FOUND", "Eintrag nicht gefunden.")
    tz = await ts.employee_timezone(db, employee)
    work_date = await ts.shift_day_of(db, employee, punch, tz)
    today = ts.today_in(tz)
    if work_date < entries.earliest_date(rules, today):
        raise AppError(422, "TIME_ENTRY_TOO_OLD", "Dieser Eintrag liegt außerhalb des Zeitraums, der sich selbst ändern lässt.")
    await ensure_period_open(db, employee.id, work_date)

    day_punches = await ts.punches_for_day(db, employee, work_date, tz)
    index = next(i for i, p in enumerate(day_punches) if p.id == punch.id)
    span = [punch]
    for following in day_punches[index + 1:]:
        if following.punch_type == PunchType.COME:
            break
        span.append(following)
        if following.punch_type == PunchType.GO:
            break
    if any(p.corrected or p.source not in (PunchSource.SELF_ENTRY, PunchSource.AUTO_BREAK) for p in span):
        raise AppError(409, "TIME_ENTRY_CHANGED", "Dieser Eintrag wurde inzwischen von HR geändert und lässt sich nicht mehr selbst löschen.")
    for item in span:
        await db.delete(item)
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.TIME_ENTRY_DELETED,
        entity_type="punch",
        entity_id=punch.id,
        detail=f"{employee.first_name} {employee.last_name}, {work_date.isoformat()}: "
        + ", ".join(f"{p.punch_type.value} {p.timestamp_utc.isoformat(timespec='minutes')}" for p in span),
    )
    await db.commit()
    await entries.after_change(db, employee, work_date)
