from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_hr_or_self
from app.db import get_db
from app.errors import AppError
from app.models import (
    PROFILE_START,
    AuditAction,
    BreakMode,
    Employee,
    EmployeeDefaultShift,
    ShiftTemplate,
    TargetPeriod,
    WorkTimeProfile,
    WorkTimeProfileVersion,
)
from app.models.rotation import monday_of, serialize_rotation
from app.schemas.break_rule import fixed_break_windows, serialize_break_windows
from app.schemas.core_time import describe_day_windows, day_windows, serialize_core_time_days, serialize_day_windows
from app.schemas.work_time_model import (
    WorkTimeModelInput,
    WorkTimeModelResponse,
    WorkTimeModelSetRequest,
    WorkTimeModelVersion,
    WorkTimeProfileAssignRequest,
)
from app.services.work_time_profile_service import get_profile_in_tenant, materialize, sync_employee
from app.services.audit_service import log_action
from app.services.shift_planning_service import (
    check_max_daily_working_time,
    check_rest_period_for_default,
    version_target,
)
from app.services.scope_service import ensure_employee_visible
from app.services.period_service import ensure_open_from, ensure_range_open
from app.services.timesheet_service import invalidate_balance

router = APIRouter(tags=["work_time_model"])

_WEEKDAY_LABELS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_ALL_DAYS = 0b1111111


def _mask_to_weekdays(mask: int) -> list[int]:
    return [day for day in range(7) if mask & (1 << day)]


def _weekdays_to_mask(weekdays: list[int]) -> int:
    return sum(1 << day for day in weekdays)


async def _get_employee_in_tenant(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


def _contract(payload: WorkTimeModelInput, valid_from: date | None = None) -> tuple[dict, str]:
    """Soll, Arbeitstage und Pause einer Fassung aus der Eingabe – und die Soll-Angabe fürs
    Audit-Protokoll (z.B. "40 h/Woche", "108.5 h/Monat").

    Mehrwöchiges Modell: Woche 1 beginnt am Montag von "Turnus beginnt am", ohne Angabe am Montag
    der Woche von valid_from (Gültig-ab der Fassung; None = heute, z.B. beim Anlegen eines
    Arbeitszeitmodells, dessen erste Fassung "von Anfang an" gilt). Gespeichert wird immer das
    feste Datum."""
    if payload.exceeds_daily_maximum:
        raise AppError(
            400,
            "MAX_DAILY_WORKING_TIME_EXCEEDED",
            "Das ergibt mehr als 10 Stunden pro Arbeitstag und überschreitet die gesetzliche "
            "Höchstarbeitszeit (§3 ArbZG). Bitte mehr Arbeitstage wählen oder die Stunden senken.",
        )
    if payload.on_demand:
        minutes, period, label = 0, TargetPeriod.WEEKLY, "0 h/Woche"
    elif payload.monthly_hours is not None:
        minutes, period = payload.monthly_minutes, TargetPeriod.MONTHLY
        label = f"{minutes / 60:g} h/Monat"
    elif payload.rotation_minutes is not None:
        weeks = payload.rotation_minutes
        minutes, period = round(sum(sum(week) for week in weeks) / len(weeks)), TargetPeriod.WEEKLY
        label = f"im Schnitt {minutes / 60:g} h/Woche"
    else:
        minutes, period = round(payload.weekly_hours * 60), TargetPeriod.WEEKLY
        label = f"{minutes / 60:g} h/Woche"
    rotation = payload.rotation_minutes
    rotation_start = None
    if rotation is not None:
        rotation_start = payload.rotation_start or monday_of(valid_from or date.today())
        payload.rotation_start = rotation_start  # für das Audit-Protokoll (_days_only_label)
    windows = payload.break_window_list
    window = bool(windows)
    fields = dict(
        weekdays_mask=_weekdays_to_mask(payload.weekdays or []) or _ALL_DAYS,
        day_minutes=",".join(str(m) for m in payload.day_minutes) if payload.day_minutes else None,
        rotation_minutes=serialize_rotation(rotation) if rotation is not None else None,
        rotation_start=rotation_start,
        settled_overtime_minutes=payload.settled_overtime_minutes,
        flexible=payload.flexible,
        on_demand=payload.on_demand,
        monthly_cap_minutes=payload.monthly_cap_minutes,
        target_minutes=minutes,
        target_period=period,
        # Eigene Pause (leer = Pause der Schichtvorlage bzw. Pausenregeln)
        break_mode=BreakMode.FIXED if window else BreakMode.FLEXIBLE if payload.break_minutes else None,
        fixed_break_start=windows[0][0] if window else None,
        fixed_break_end=windows[0][1] if window else None,
        fixed_break_windows=serialize_break_windows(windows),
        min_break_minutes=payload.break_minutes,
        min_break_after_minutes=payload.break_after_minutes if payload.break_minutes else 0,
        # Toleranz: eigener Wert nur im Arbeitszeitmodell, individuell wie Einstellungen
        late_tolerance_minutes=getattr(payload, "late_tolerance_minutes", None),
    )
    return fields, label


def _core_time_fields(payload: WorkTimeModelInput, inherit_from: EmployeeDefaultShift | None) -> dict:
    """Kernzeit der Fassung: wie angegeben, ohne Angabe wie die bisherige Fassung."""
    if payload.core_time_mode is None:
        if inherit_from is None:
            return dict(core_time_mode="TENANT", core_time_start=None, core_time_end=None, core_time_days=None)
        return dict(
            core_time_mode=inherit_from.core_time_mode or "TENANT",
            core_time_start=inherit_from.core_time_start,
            core_time_end=inherit_from.core_time_end,
            core_time_days=inherit_from.core_time_days,
        )
    custom = payload.core_time_mode == "CUSTOM"
    days = custom and payload.core_time_days is not None
    return dict(
        core_time_mode=payload.core_time_mode,
        core_time_start=payload.core_time_start if custom and not days else None,
        core_time_end=payload.core_time_end if custom and not days else None,
        core_time_days=serialize_core_time_days(payload.core_time_days) if days else None,
    )


def _flex_frame_fields(payload: WorkTimeModelInput, inherit_from: EmployeeDefaultShift | WorkTimeProfileVersion | None) -> dict:
    """Gleitzeit-Rahmen der Fassung: wie angegeben, ohne Angabe wie die bisherige Fassung."""
    if payload.flex_frame_mode is None:
        source = inherit_from
        return dict(
            flex_frame_mode=source.flex_frame_mode if source else None,
            flex_frame_start=source.flex_frame_start if source else None,
            flex_frame_end=source.flex_frame_end if source else None,
            flex_frame_days=source.flex_frame_days if source else None,
        )
    return dict(
        flex_frame_mode=payload.flex_frame_mode,
        flex_frame_start=payload.flex_frame_start,
        flex_frame_end=payload.flex_frame_end,
        flex_frame_days=serialize_day_windows(payload.flex_frame_days),
    )


def _frame_label(payload: WorkTimeModelInput) -> str:
    """Gleitzeit-Rahmen und abgegoltene Überstunden fürs Audit-Protokoll (leer = nicht angegeben
    bzw. wie Einstellungen)."""
    settled = payload.settled_overtime_minutes
    suffix = f", abgegolten bis {settled / 60:g} h/Monat" if settled else ""
    return _flex_frame_label(payload) + suffix


def _flex_frame_label(payload: WorkTimeModelInput) -> str:
    if payload.flex_frame_mode == "CUSTOM":
        if payload.flex_frame_days is not None:
            days = describe_day_windows(day_windows(payload.flex_frame_days, None, None))
            return f", Gleitzeit-Rahmen je Wochentag ({days})"
        return f", Gleitzeit-Rahmen {payload.flex_frame_start:%H:%M}–{payload.flex_frame_end:%H:%M}"
    if payload.flex_frame_mode == "NONE":
        return ", ohne Gleitzeit-Rahmen"
    return ""


async def _times_template(
    db: AsyncSession, tenant_id: int, template_id: int | None, current_id: int | None = None
) -> ShiftTemplate | None:
    """Schichtvorlage für die Uhrzeiten. Archivierte Fassungen einer Vorlage nur, wenn die Fassung
    der Arbeitszeit sie schon hat (nachträgliche Änderung einer alten Fassung)."""
    if template_id is None:
        return None
    template = await db.get(ShiftTemplate, template_id)
    if template is None or template.tenant_id != tenant_id or (template.archived and template_id != current_id):
        raise AppError(404, "SHIFT_TEMPLATE_NOT_FOUND", "Schichtvorlage nicht gefunden.")
    return template


async def _check_shift_times(
    db: AsyncSession, employee_id: int, template: ShiftTemplate | None, mask: int, valid_from: date, valid_to: date | None
) -> None:
    """ArbZG-Prüfung der Uhrzeiten (Höchstarbeitszeit, Ruhezeit) – nur mit Schichtvorlage."""
    if template is None:
        return
    check_max_daily_working_time(template.start_time, template.end_time)
    await check_rest_period_for_default(db, employee_id, template, mask, valid_from, valid_to)


async def _build_response(db: AsyncSession, employee_id: int) -> WorkTimeModelResponse:
    today = date.today()
    result = await db.execute(
        select(EmployeeDefaultShift).where(
            EmployeeDefaultShift.employee_id == employee_id,
            EmployeeDefaultShift.valid_from <= today,
        )
    )
    active = [d for d in result.scalars().all() if d.valid_to is None or d.valid_to >= today]
    if not active:
        return WorkTimeModelResponse(employee_id=employee_id, configured=False, valid_from=None)

    version = active[0]
    return WorkTimeModelResponse(
        employee_id=employee_id,
        configured=True,
        valid_from=version.valid_from,
        **(await _describe(db, version)),
    )


async def _describe(db: AsyncSession, version: EmployeeDefaultShift | WorkTimeProfileVersion) -> dict:
    """Soll, Pause, Uhrzeiten, Kernzeit, Gleitzeit-Rahmen und Modell einer Fassung (auch einer
    Modell-Fassung)."""
    template = await db.get(ShiftTemplate, version.shift_template_id) if version.shift_template_id is not None else None
    profile = (
        await db.get(WorkTimeProfile, version.profile_id)
        if isinstance(version, EmployeeDefaultShift) and version.profile_id is not None
        else None
    )
    frame = version.flex_frame_mode == "CUSTOM"
    own_break = version.break_mode is not None
    source = version if own_break else template
    fixed = source is not None and source.break_mode == BreakMode.FIXED and source.fixed_break_start is not None
    minutes = None if fixed or source is None else (source.min_break_minutes or None)
    custom = version.core_time_mode == "CUSTOM"
    return {
        **_describe_target(version, template),
        "target_from_template": version.target_minutes is None and template is not None,
        "break_minutes": minutes,
        "break_after_minutes": (source.min_break_after_minutes or 0) if minutes else 0,
        "break_start": source.fixed_break_start if fixed else None,
        "break_windows": [{"start": start, "end": end} for start, end in fixed_break_windows(source)] if fixed else None,
        "break_end": source.fixed_break_end if fixed else None,
        "break_from_template": not own_break and (fixed or minutes is not None),
        "shift_template_id": version.shift_template_id,
        "shift_template_name": template.name if template else None,
        "shift_start": template.start_time if template else None,
        "shift_end": template.end_time if template else None,
        "core_time_mode": version.core_time_mode or "TENANT",
        "core_time_start": version.core_time_start if custom else None,
        "core_time_end": version.core_time_end if custom else None,
        "core_time_days": version.core_time_days if custom else None,
        "flex_frame_mode": version.flex_frame_mode or "TENANT",
        "flex_frame_start": version.flex_frame_start if frame else None,
        "flex_frame_end": version.flex_frame_end if frame else None,
        "flex_frame_days": version.flex_frame_days if frame else None,
        "late_tolerance_minutes": version.late_tolerance_minutes,
        "settled_overtime_minutes": version.settled_overtime_minutes,
        "profile_id": profile.id if profile else None,
        "profile_name": profile.name if profile else None,
    }


def _describe_target(default: EmployeeDefaultShift, template: ShiftTemplate | None) -> dict:
    """Soll einer Fassung: Wochen-/Tagesminuten, Arbeitstage, Minuten je Wochentag."""
    weekdays = _mask_to_weekdays(default.weekdays_mask)
    per_day = default.day_minutes_list
    if default.on_demand:
        return dict(
            weekly_minutes=None,
            daily_minutes=None,
            weekdays=[],
            day_minutes=None,
            on_demand=True,
            monthly_cap_minutes=default.monthly_cap_minutes,
        )
    total, period = version_target(default, template)
    if default.flexible:
        return dict(weekly_minutes=total, daily_minutes=None, weekdays=[], day_minutes=None, flexible=True)
    rotation = default.rotation_weeks
    if rotation is not None:
        # Mehrwöchiges Modell: Wochenminuten = Durchschnitt, Arbeitstage = Tage mit Soll in irgendeiner Woche.
        return dict(
            weekly_minutes=round(sum(sum(week) for week in rotation) / len(rotation)),
            daily_minutes=None,
            weekdays=[d for d in range(7) if any(week[d] > 0 for week in rotation)],
            day_minutes=None,
            rotation_minutes=rotation,
            rotation_start=monday_of(default.rotation_start or default.valid_from),
        )
    if per_day is not None:
        uneven = len(set(m for m in per_day if m > 0)) > 1
        return dict(
            weekly_minutes=sum(per_day),
            daily_minutes=None if uneven else max(per_day),
            weekdays=[d for d, m in enumerate(per_day) if m > 0],
            day_minutes=per_day,
            uneven=uneven,
        )
    if period == TargetPeriod.MONTHLY:
        # Tagessoll schwankt mit der Zahl der Arbeitstage im Monat – daher nur Monatswert und Tage.
        return dict(weekly_minutes=None, daily_minutes=None, weekdays=weekdays, day_minutes=None, monthly_minutes=total)
    if period == TargetPeriod.WEEKLY:
        weekly_minutes = total
        daily_minutes = round(weekly_minutes / len(weekdays)) if weekdays else None
    else:
        daily_minutes = total
        weekly_minutes = total * len(weekdays)
    return dict(
        weekly_minutes=weekly_minutes,
        daily_minutes=daily_minutes,
        weekdays=weekdays,
        day_minutes=[daily_minutes if d in weekdays else 0 for d in range(7)] if daily_minutes is not None else None,
    )


def _days_label(payload: WorkTimeModelInput, template: ShiftTemplate | None = None) -> str:
    shift = f", Schicht {template.name}" if template is not None else ""
    core = {"CUSTOM": ", eigene Kernzeit", "NONE": ", ohne Pünktlichkeitsprüfung", "TENANT": ", Kernzeit wie Einstellungen"}
    return _days_only_label(payload) + payload.break_label + shift + core.get(payload.core_time_mode or "", "")


def _days_only_label(payload: WorkTimeModelInput) -> str:
    if payload.on_demand:
        cap = f", Monatsgrenze {payload.monthly_cap_hours:g} h" if payload.monthly_cap_hours else ""
        return f"nach Aufwand ohne Soll{cap}"
    if payload.flexible:
        return "flexibel ohne feste Tage"
    if payload.rotation_minutes is not None:
        weeks = "; ".join(
            f"Woche {index}: " + (", ".join(f"{_WEEKDAY_LABELS[d]} {m / 60:g} h" for d, m in enumerate(week) if m > 0) or "frei")
            for index, week in enumerate(payload.rotation_minutes, start=1)
        )
        start = f", Woche 1 ab {payload.rotation_start:%d.%m.%Y}" if payload.rotation_start else ""
        return f"Turnus über {len(payload.rotation_minutes)} Wochen ({weeks}){start}"
    if payload.day_minutes:
        return ", ".join(f"{_WEEKDAY_LABELS[d]} {m / 60:g} h" for d, m in enumerate(payload.day_minutes) if m > 0)
    return ", ".join(_WEEKDAY_LABELS[d] for d in payload.weekdays)


@router.get("/employees/{employee_id}/work-time-model", response_model=WorkTimeModelResponse)
async def get_work_time_model(
    employee_id: int,
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> WorkTimeModelResponse:
    employee = await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)
    elif actor.employee is None or actor.employee.id != employee_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return await _build_response(db, employee_id)


@router.put("/employees/{employee_id}/work-time-model", response_model=WorkTimeModelResponse)
async def set_work_time_model(
    employee_id: int,
    payload: WorkTimeModelSetRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> WorkTimeModelResponse:
    """Setzt das Arbeitszeitmodell ab einem Stichtag (Effective-Dating): neue Fassung mit Soll,
    Pause, Kernzeit und optional einer Schichtvorlage für die Uhrzeiten – die bisherige Fassung
    läuft zum Vortag aus, spätere entfallen."""
    await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    await ensure_open_from(db, employee_id, payload.valid_from)
    fields, soll_label = _contract(payload, payload.valid_from)
    template = await _times_template(db, actor.tenant_id, payload.shift_template_id)

    rows = await _versions(db, employee_id)
    # Kernzeit ohne Angabe: wie die Fassung, die bisher an diesem Tag galt.
    inherit = next((v for v in reversed(rows) if v.valid_from <= payload.valid_from), None)
    fields.update(_core_time_fields(payload, inherit))
    fields.update(_flex_frame_fields(payload, inherit))
    # "Ab Stichtag" ersetzt alles ab diesem Tag (auch rückwirkend, solange der Monat offen ist):
    # spätere Fassungen entfallen, eine laufende endet am Vortag.
    for row in rows:
        if row.valid_from >= payload.valid_from:
            await db.delete(row)
        elif row.valid_to is None or row.valid_to >= payload.valid_from:
            row.valid_to = payload.valid_from - timedelta(days=1)
    await db.flush()
    await _check_shift_times(db, employee_id, template, fields["weekdays_mask"], payload.valid_from, None)
    db.add(
        EmployeeDefaultShift(
            employee_id=employee_id,
            shift_template_id=template.id if template else None,
            valid_from=payload.valid_from,
            valid_to=None,
            **fields,
        )
    )
    await db.flush()
    await sync_employee(db, employee_id)  # eine vorher laufende Modell-Zuweisung endet am Vortag
    await invalidate_balance(db, employee_id, payload.valid_from)
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.EMPLOYEE_WORK_TIME_MODEL_SET,
        entity_type="employee",
        entity_id=employee_id,
        detail=f"{soll_label} an {_days_label(payload, template)}{_frame_label(payload)} ab {payload.valid_from.isoformat()}",
    )
    await db.commit()
    return await _build_response(db, employee_id)


@router.put("/employees/{employee_id}/work-time-profile", response_model=WorkTimeModelResponse)
async def assign_work_time_profile(
    employee_id: int,
    payload: WorkTimeProfileAssignRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> WorkTimeModelResponse:
    """Weist ein Arbeitszeitmodell ab Stichtag zu. Wie ein neues Arbeitszeitmodell ersetzt das alles
    ab diesem Tag; die Angaben kommen aus dem Modell und folgen dessen Änderungen."""
    await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    profile = await get_profile_in_tenant(db, payload.profile_id, actor.tenant_id)
    if profile.archived:
        raise AppError(409, "WORK_TIME_PROFILE_ARCHIVED", "Das Arbeitszeitmodell ist archiviert und kann nicht neu zugewiesen werden.")
    if payload.valid_from < PROFILE_START:
        raise AppError(400, "INVALID_RANGE", f"Ein Modell gilt frühestens ab {PROFILE_START:%d.%m.%Y}.")
    await ensure_open_from(db, employee_id, payload.valid_from)

    for row in await _versions(db, employee_id):
        if row.valid_from >= payload.valid_from:
            await db.delete(row)
        elif row.valid_to is None or row.valid_to >= payload.valid_from:
            row.valid_to = payload.valid_from - timedelta(days=1)
    await db.flush()
    new_rows = await materialize(db, employee_id, profile.id, payload.valid_from, None)
    for row in new_rows:
        template = await db.get(ShiftTemplate, row.shift_template_id) if row.shift_template_id is not None else None
        await _check_shift_times(db, employee_id, template, row.weekdays_mask, row.valid_from, row.valid_to)
    db.add_all(new_rows)
    await db.flush()
    changed = await sync_employee(db, employee_id)  # z.B. mit einer direkt vorher laufenden Zuweisung zusammenfassen
    await invalidate_balance(db, employee_id, min(payload.valid_from, changed or payload.valid_from))
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.EMPLOYEE_WORK_TIME_MODEL_SET,
        entity_type="employee",
        entity_id=employee_id,
        detail=f"Arbeitszeitmodell „{profile.name}“ ab {payload.valid_from.isoformat()}",
    )
    await db.commit()
    return await _build_response(db, employee_id)


async def _versions(db: AsyncSession, employee_id: int) -> list[EmployeeDefaultShift]:
    return list(
        (
            await db.execute(
                select(EmployeeDefaultShift)
                .where(EmployeeDefaultShift.employee_id == employee_id)
                .order_by(EmployeeDefaultShift.valid_from)
            )
        ).scalars().all()
    )


async def _ensure_unlocked(db: AsyncSession, employee_id: int, start: date, end: date | None) -> None:
    if end is None:
        await ensure_open_from(db, employee_id, start)
    else:
        await ensure_range_open(db, employee_id, start, end)


@router.get("/employees/{employee_id}/work-time-model/history", response_model=list[WorkTimeModelVersion])
async def get_work_time_model_history(
    employee_id: int,
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[WorkTimeModelVersion]:
    """Alle Fassungen des Arbeitszeitmodells, neueste zuerst."""
    employee = await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)
    elif actor.employee is None or actor.employee.id != employee_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return [
        WorkTimeModelVersion(id=version.id, valid_from=version.valid_from, valid_to=version.valid_to, **(await _describe(db, version)))
        for version in reversed(await _versions(db, employee_id))
    ]


@router.put(
    "/employees/{employee_id}/work-time-model/versions/{version_id}", response_model=list[WorkTimeModelVersion]
)
async def update_work_time_model_version(
    employee_id: int,
    version_id: int,
    payload: WorkTimeModelSetRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[WorkTimeModelVersion]:
    """Ändert eine bestehende Fassung nachträglich (Stunden, Tage, Pause, Schicht, Kernzeit, Beginn).
    Ein verschobener Beginn passt das Ende der vorherigen Fassung an; das Ende bleibt (Beginn der
    nächsten). Eine ältere Standard-Schicht bekommt dabei ihr Soll fest übernommen. Gehörte die
    Fassung zu einem Arbeitszeitmodell, ist sie danach individuell (entweder Modell oder eigene
    Angaben)."""
    await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    versions = await _versions(db, employee_id)
    version = next((v for v in versions if v.id == version_id), None)
    if version is None:
        raise AppError(404, "VERSION_NOT_FOUND", "Fassung nicht gefunden.")
    previous = next((v for v in reversed(versions) if v.valid_from < version.valid_from), None)
    if previous is not None and payload.valid_from <= previous.valid_from:
        raise AppError(400, "INVALID_RANGE", "Der Beginn muss nach dem Beginn der vorherigen Fassung liegen.")
    if version.valid_to is not None and payload.valid_from > version.valid_to:
        raise AppError(400, "INVALID_RANGE", "Der Beginn darf nicht nach dem Ende der Fassung liegen.")
    start = min(version.valid_from, payload.valid_from)
    await _ensure_unlocked(db, employee_id, start, version.valid_to)

    fields, soll_label = _contract(payload, payload.valid_from)
    fields.update(_core_time_fields(payload, version))
    fields.update(_flex_frame_fields(payload, version))
    template = await _times_template(db, actor.tenant_id, payload.shift_template_id, version.shift_template_id)
    old_from = version.valid_from
    for key, value in fields.items():
        setattr(version, key, value)
    version.shift_template_id = template.id if template else None
    version.profile_id = None
    version.valid_from = payload.valid_from
    if previous is not None:
        previous.valid_to = payload.valid_from - timedelta(days=1)
    await db.flush()
    await _check_shift_times(db, employee_id, template, version.weekdays_mask, version.valid_from, version.valid_to)
    # Eine vorherige Modell-Zuweisung mit verschobenem Ende an ihr Modell angleichen.
    changed = await sync_employee(db, employee_id)
    await invalidate_balance(db, employee_id, min(start, changed or start))
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.EMPLOYEE_WORK_TIME_MODEL_SET,
        entity_type="employee",
        entity_id=employee_id,
        detail=(
            f"Fassung ab {old_from.isoformat()} geändert: {soll_label} an {_days_label(payload, template)}{_frame_label(payload)} "
            f"ab {payload.valid_from.isoformat()}"
        ),
    )
    await db.commit()
    return await get_work_time_model_history(employee_id, actor, db)


@router.delete("/employees/{employee_id}/work-time-model/versions/{version_id}", status_code=204)
async def delete_work_time_model_version(
    employee_id: int,
    version_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Entfernt eine Fassung; die vorherige gilt dann bis zum Ende der gelöschten weiter."""
    await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    versions = await _versions(db, employee_id)
    version = next((v for v in versions if v.id == version_id), None)
    if version is None:
        raise AppError(404, "VERSION_NOT_FOUND", "Fassung nicht gefunden.")
    await _ensure_unlocked(db, employee_id, version.valid_from, version.valid_to)
    previous = next((v for v in reversed(versions) if v.valid_from < version.valid_from), None)
    if previous is not None:
        previous.valid_to = version.valid_to
    removed_from = version.valid_from
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.EMPLOYEE_WORK_TIME_MODEL_SET,
        entity_type="employee",
        entity_id=employee_id,
        detail=f"Fassung ab {removed_from.isoformat()} gelöscht",
    )
    await db.delete(version)
    await db.flush()
    # Verlängert sich dadurch eine Modell-Zuweisung, gelten im neuen Zeitraum die Modell-Fassungen.
    changed = await sync_employee(db, employee_id)
    await invalidate_balance(db, employee_id, min(removed_from, changed or removed_from))
    await db.commit()
