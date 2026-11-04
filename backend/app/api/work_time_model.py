from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_hr_or_self
from app.api.employee_default_shifts import create_default_shift
from app.db import get_db
from app.errors import AppError
from app.models import (
    AuditAction,
    BreakMode,
    Employee,
    EmployeeDefaultShift,
    ShiftTemplate,
    TargetPeriod,
)
from app.schemas.employee_default_shift import EmployeeDefaultShiftCreateRequest
from app.schemas.work_time_model import (
    WorkTimeModelInput,
    WorkTimeModelResponse,
    WorkTimeModelSetRequest,
    WorkTimeModelVersion,
)
from app.services.audit_service import log_action
from app.services.team_scope_service import ensure_employee_visible
from app.services.period_service import ensure_open_from, ensure_range_open
from app.services.timesheet_service import invalidate_balance

router = APIRouter(tags=["work_time_model"])

_WEEKDAY_LABELS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _mask_to_weekdays(mask: int) -> list[int]:
    return [day for day in range(7) if mask & (1 << day)]


def _weekdays_to_mask(weekdays: list[int]) -> int:
    return sum(1 << day for day in weekdays)


async def _get_employee_in_tenant(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


async def _ensure_model_template(db: AsyncSession, tenant_id: int, name: str, weekly_minutes: int) -> ShiftTemplate:
    """Findet bzw. legt die zeitlose Wochenstunden-Vorlage an. Trägt eine manuell
    angelegte Vorlage bereits diesen Namen, wird mit Zusatz "[Modell]" ausgewichen
    (statt am eindeutigen Namen zu scheitern)."""
    candidates = (
        await db.execute(
            select(ShiftTemplate).where(
                ShiftTemplate.tenant_id == tenant_id, ShiftTemplate.name.in_([name, f"{name} [Modell]"])
            )
        )
    ).scalars().all()
    for template in candidates:
        if template.is_work_time_model:
            return template
    taken = {template.name for template in candidates}
    free_name = name if name not in taken else f"{name} [Modell]"
    if free_name in taken:
        raise AppError(409, "TEMPLATE_NAME_CONFLICT", "Es existiert bereits eine Vorlage mit diesem Namen.")

    template = ShiftTemplate(
        tenant_id=tenant_id,
        name=free_name,
        break_mode=BreakMode.FLEXIBLE,
        target_minutes=weekly_minutes,
        target_period=TargetPeriod.WEEKLY,
        is_work_time_model=True,
    )
    db.add(template)
    try:
        await db.commit()
    except IntegrityError as exc:  # paralleler Request hat dieselbe Vorlage soeben angelegt
        await db.rollback()
        raise AppError(409, "TEMPLATE_NAME_CONFLICT", "Bitte erneut versuchen.") from exc
    await db.refresh(template)
    return template


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
        return WorkTimeModelResponse(
            employee_id=employee_id,
            configured=False,
            is_work_time_model=False,
            template_name=None,
            weekly_minutes=None,
            daily_minutes=None,
            weekdays=[],
            valid_from=None,
        )

    default = active[0]
    template = await db.get(ShiftTemplate, default.shift_template_id)
    return WorkTimeModelResponse(
        employee_id=employee_id,
        configured=True,
        is_work_time_model=template.is_work_time_model,
        template_name=template.name,
        valid_from=default.valid_from,
        **_describe(default, template),
    )


def _describe(default: EmployeeDefaultShift, template: ShiftTemplate) -> dict:
    """Soll einer Modell-Fassung: Wochen-/Tagesminuten, Arbeitstage, Minuten je Wochentag."""
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
    if default.flexible:
        return dict(weekly_minutes=template.target_minutes, daily_minutes=None, weekdays=[], day_minutes=None, flexible=True)
    if per_day is not None:
        uneven = len(set(m for m in per_day if m > 0)) > 1
        return dict(
            weekly_minutes=sum(per_day),
            daily_minutes=None if uneven else max(per_day),
            weekdays=[d for d, m in enumerate(per_day) if m > 0],
            day_minutes=per_day,
            uneven=uneven,
        )
    weekly_minutes = daily_minutes = None
    if template.target_period == TargetPeriod.WEEKLY:
        weekly_minutes = template.target_minutes
        daily_minutes = round(weekly_minutes / len(weekdays)) if weekdays else None
    elif template.target_period == TargetPeriod.DAILY:
        daily_minutes = template.target_minutes
        weekly_minutes = template.target_minutes * len(weekdays)
    return dict(
        weekly_minutes=weekly_minutes,
        daily_minutes=daily_minutes,
        weekdays=weekdays,
        day_minutes=[daily_minutes if d in weekdays else 0 for d in range(7)] if daily_minutes is not None else None,
    )


async def _template_for(db: AsyncSession, tenant_id: int, payload: WorkTimeModelInput) -> tuple[ShiftTemplate, str]:
    if payload.on_demand:
        return await _ensure_model_template(db, tenant_id, "Nach Aufwand (ohne Soll)", 0), "0"
    weekly_minutes = round(payload.weekly_hours * 60)
    if payload.exceeds_daily_maximum:
        raise AppError(
            400,
            "MAX_DAILY_WORKING_TIME_EXCEEDED",
            "Das ergibt mehr als 10 Stunden pro Arbeitstag und überschreitet die gesetzliche "
            "Höchstarbeitszeit (§3 ArbZG). Bitte mehr Arbeitstage wählen oder die Stunden senken.",
        )
    hours_label = f"{weekly_minutes / 60:g}"
    name = f"{'Flexibel' if payload.flexible else 'Arbeitszeitmodell'} {hours_label} h/Woche"
    return await _ensure_model_template(db, tenant_id, name, weekly_minutes), hours_label


def _days_label(payload: WorkTimeModelInput) -> str:
    if payload.on_demand:
        cap = f", Monatsgrenze {payload.monthly_cap_hours:g} h" if payload.monthly_cap_hours else ""
        return f"nach Aufwand ohne Soll{cap}"
    if payload.flexible:
        return "flexibel ohne feste Tage"
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
    """Setzt das Arbeitszeitmodell ab einem Stichtag (Effective-Dating wie bei
    Standard-Schichten): legt bei Bedarf eine zeitlose Wochenstunden-Vorlage an
    (ShiftTemplate.is_work_time_model) und ordnet sie dem Mitarbeiter als neue
    Standard-Zuordnung zu – die bisherige läuft zum Vortag aus."""
    await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    await ensure_open_from(db, employee_id, payload.valid_from)

    template, hours_label = await _template_for(db, actor.tenant_id, payload)

    mask = (_weekdays_to_mask(payload.weekdays) or 0b1111111)
    # "Ab Stichtag" ersetzt alles ab diesem Tag (auch rückwirkend, solange der Monat offen ist):
    # spätere Zuordnungen entfallen, eine laufende endet am Vortag.
    rows = (
        await db.execute(select(EmployeeDefaultShift).where(EmployeeDefaultShift.employee_id == employee_id))
    ).scalars().all()
    for row in rows:
        if row.valid_from >= payload.valid_from:
            await db.delete(row)
        elif row.valid_to is None or row.valid_to >= payload.valid_from:
            row.valid_to = payload.valid_from - timedelta(days=1)
    await db.flush()
    await create_default_shift(
        employee_id,
        EmployeeDefaultShiftCreateRequest(
            shift_template_id=template.id,
            valid_from=payload.valid_from,
            valid_to=None,
            weekdays_mask=mask,
            day_minutes=payload.day_minutes,
            flexible=payload.flexible,
            on_demand=payload.on_demand,
            monthly_cap_minutes=payload.monthly_cap_minutes,
        ),
        actor,
        db,
    )

    days = _days_label(payload)
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.EMPLOYEE_WORK_TIME_MODEL_SET,
        entity_type="employee",
        entity_id=employee_id,
        detail=f"{hours_label} h/Woche an {days} ab {payload.valid_from.isoformat()}",
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
    result = []
    for version in reversed(await _versions(db, employee_id)):
        template = await db.get(ShiftTemplate, version.shift_template_id)
        result.append(
            WorkTimeModelVersion(
                id=version.id,
                valid_from=version.valid_from,
                valid_to=version.valid_to,
                template_name=template.name,
                is_work_time_model=template.is_work_time_model,
                **_describe(version, template),
            )
        )
    return result


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
    """Ändert eine bestehende Fassung nachträglich (Stunden, Tage, Beginn). Ein verschobener
    Beginn passt das Ende der vorherigen Fassung an; das Ende bleibt (Beginn der nächsten)."""
    await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    versions = await _versions(db, employee_id)
    version = next((v for v in versions if v.id == version_id), None)
    if version is None:
        raise AppError(404, "VERSION_NOT_FOUND", "Fassung nicht gefunden.")
    template_old = await db.get(ShiftTemplate, version.shift_template_id)
    if not template_old.is_work_time_model:
        raise AppError(400, "SHIFT_TEMPLATE_VERSION", "Diese Fassung ist eine Schichtvorlage – bitte unter Schichtplanung ändern.")
    previous = next((v for v in reversed(versions) if v.valid_from < version.valid_from), None)
    if previous is not None and payload.valid_from <= previous.valid_from:
        raise AppError(400, "INVALID_RANGE", "Der Beginn muss nach dem Beginn der vorherigen Fassung liegen.")
    if version.valid_to is not None and payload.valid_from > version.valid_to:
        raise AppError(400, "INVALID_RANGE", "Der Beginn darf nicht nach dem Ende der Fassung liegen.")
    start = min(version.valid_from, payload.valid_from)
    await _ensure_unlocked(db, employee_id, start, version.valid_to)

    template, hours_label = await _template_for(db, actor.tenant_id, payload)
    old_from = version.valid_from
    version.shift_template_id = template.id
    version.weekdays_mask = (_weekdays_to_mask(payload.weekdays) or 0b1111111)
    version.day_minutes = ",".join(str(m) for m in payload.day_minutes) if payload.day_minutes else None
    version.flexible = payload.flexible
    version.on_demand = payload.on_demand
    version.monthly_cap_minutes = payload.monthly_cap_minutes
    version.valid_from = payload.valid_from
    if previous is not None:
        previous.valid_to = payload.valid_from - timedelta(days=1)
    await invalidate_balance(db, employee_id, start)
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.EMPLOYEE_WORK_TIME_MODEL_SET,
        entity_type="employee",
        entity_id=employee_id,
        detail=(
            f"Fassung ab {old_from.isoformat()} geändert: {hours_label} h/Woche an {_days_label(payload)} "
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
    await invalidate_balance(db, employee_id, version.valid_from)
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.EMPLOYEE_WORK_TIME_MODEL_SET,
        entity_type="employee",
        entity_id=employee_id,
        detail=f"Fassung ab {version.valid_from.isoformat()} gelöscht",
    )
    await db.delete(version)
    await db.commit()
