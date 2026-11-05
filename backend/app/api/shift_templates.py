from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import BreakMode, EmployeeDefaultShift, Location, ShiftPlanEntry, ShiftTemplate
from app.schemas.break_rule import check_window
from app.services.period_service import ensure_open_from
from app.services.timesheet_service import invalidate_balance
from app.schemas.shift_template import (
    ShiftTemplateCreateRequest,
    ShiftTemplateResponse,
    ShiftTemplateUpdateRequest,
)

router = APIRouter(tags=["shift_templates"])


@router.get("/shift-templates", response_model=list[ShiftTemplateResponse])
async def list_shift_templates(
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[ShiftTemplateResponse]:
    result = await db.execute(
        select(ShiftTemplate)
        .where(ShiftTemplate.tenant_id == actor.tenant_id, ShiftTemplate.archived.is_(False))
        .order_by(ShiftTemplate.name.asc())
    )
    return [ShiftTemplateResponse.model_validate(t) for t in result.scalars().all()]


@router.post("/shift-templates", response_model=ShiftTemplateResponse, status_code=201)
async def create_shift_template(
    payload: ShiftTemplateCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> ShiftTemplateResponse:
    if payload.location_id is not None:
        location = await db.get(Location, payload.location_id)
        if location is None or location.tenant_id != actor.tenant_id:
            raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")

    template = ShiftTemplate(
        tenant_id=actor.tenant_id,
        name=payload.name,
        start_time=payload.start_time,
        end_time=payload.end_time,
        break_mode=payload.break_mode,
        fixed_break_start=payload.fixed_break_start,
        fixed_break_end=payload.fixed_break_end,
        min_break_minutes=payload.min_break_minutes,
        target_minutes=payload.target_minutes,
        target_period=payload.target_period,
        location_id=payload.location_id,
    )
    db.add(template)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "NAME_TAKEN", "Eine Schichtvorlage mit diesem Namen existiert bereits.") from exc

    await db.refresh(template)
    return ShiftTemplateResponse.model_validate(template)


@router.patch("/shift-templates/{template_id}", response_model=ShiftTemplateResponse)
async def update_shift_template(
    template_id: int,
    payload: ShiftTemplateUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> ShiftTemplateResponse:
    template = await db.get(ShiftTemplate, template_id)
    if template is None or template.tenant_id != actor.tenant_id or template.archived:
        raise AppError(404, "SHIFT_TEMPLATE_NOT_FOUND", "Schichtvorlage nicht gefunden.")

    target_changes = (payload.target_minutes is not None and payload.target_minutes != template.target_minutes) or (
        payload.target_period is not None and payload.target_period != template.target_period
    )
    # Pausenänderungen wirken (wie ein geändertes Soll) erst ab Stichtag – vergangene und
    # abgeschlossene Tage rechnen mit der bisherigen Pause.
    break_changes = (
        (payload.break_mode is not None and payload.break_mode != template.break_mode)
        or (payload.fixed_break_start is not None and payload.fixed_break_start != template.fixed_break_start)
        or (payload.fixed_break_end is not None and payload.fixed_break_end != template.fixed_break_end)
        or (payload.min_break_minutes is not None and payload.min_break_minutes != (template.min_break_minutes or 0))
    )
    if target_changes or break_changes:
        template = await _version_for_target_change(db, actor, template, payload.valid_from or date.today())

    if payload.name is not None:
        template.name = payload.name
    if payload.start_time is not None:
        template.start_time = payload.start_time
    if payload.end_time is not None:
        template.end_time = payload.end_time
    if payload.break_mode is not None:
        template.break_mode = payload.break_mode
    if payload.fixed_break_start is not None:
        template.fixed_break_start = payload.fixed_break_start
    if payload.fixed_break_end is not None:
        template.fixed_break_end = payload.fixed_break_end
    if payload.min_break_minutes is not None:
        template.min_break_minutes = payload.min_break_minutes
    if template.break_mode == BreakMode.FIXED:
        try:
            check_window(template.fixed_break_start, template.fixed_break_end)
        except ValueError as exc:
            raise AppError(422, "INVALID_BREAK_WINDOW", str(exc)) from exc
    if payload.target_minutes is not None:
        template.target_minutes = payload.target_minutes
    if payload.target_period is not None:
        template.target_period = payload.target_period
    if payload.location_id is not None:
        location = await db.get(Location, payload.location_id)
        if location is None or location.tenant_id != actor.tenant_id:
            raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")
        template.location_id = payload.location_id
    elif payload.clear_location_id:
        template.location_id = None

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "NAME_TAKEN", "Eine Schichtvorlage mit diesem Namen existiert bereits.") from exc

    await db.refresh(template)
    return ShiftTemplateResponse.model_validate(template)


async def _version_for_target_change(db: AsyncSession, actor: Actor, template: ShiftTemplate, effective: date) -> ShiftTemplate:
    """Soll-Änderung ab Stichtag: Wird die Vorlage schon vor dem Stichtag als Standard-Schicht
    genutzt, bleibt die bisherige Fassung (archiviert, umbenannt) für die Vergangenheit zugeordnet
    und eine neue Fassung mit gleichem Namen übernimmt ab dem Stichtag. Sonst wird direkt geändert."""
    defaults = (
        await db.execute(select(EmployeeDefaultShift).where(EmployeeDefaultShift.shift_template_id == template.id))
    ).scalars().all()
    affected = [d for d in defaults if d.valid_to is None or d.valid_to >= effective]
    for employee_id in {d.employee_id for d in affected}:
        await ensure_open_from(db, employee_id, effective)
        await invalidate_balance(db, employee_id, effective)
    if not any(d.valid_from < effective for d in defaults):
        return template

    new_template = ShiftTemplate(
        tenant_id=template.tenant_id,
        name=template.name,
        start_time=template.start_time,
        end_time=template.end_time,
        break_mode=template.break_mode,
        fixed_break_start=template.fixed_break_start,
        fixed_break_end=template.fixed_break_end,
        min_break_minutes=template.min_break_minutes,
        target_minutes=template.target_minutes,
        target_period=template.target_period,
        location_id=template.location_id,
        is_work_time_model=template.is_work_time_model,
    )
    template.archived = True
    template.name = f"{template.name} (bis {(effective - timedelta(days=1)).strftime('%d.%m.%Y')})"[:100]
    await db.flush()  # Namen freigeben, bevor die neue Fassung ihn übernimmt
    db.add(new_template)
    await db.flush()

    for default in affected:
        if default.valid_from >= effective:
            default.shift_template_id = new_template.id
            continue
        db.add(
            EmployeeDefaultShift(
                employee_id=default.employee_id,
                shift_template_id=new_template.id,
                valid_from=effective,
                valid_to=default.valid_to,
                weekdays_mask=default.weekdays_mask,
            )
        )
        default.valid_to = effective - timedelta(days=1)
    # Künftige Tagesausnahmen zeigen auf die neue Fassung (ihr eigenes Soll bleiben sie behalten).
    entries = (
        await db.execute(
            select(ShiftPlanEntry).where(ShiftPlanEntry.shift_template_id == template.id, ShiftPlanEntry.date >= effective)
        )
    ).scalars().all()
    for entry in entries:
        entry.shift_template_id = new_template.id
    return new_template


@router.delete("/shift-templates/{template_id}", status_code=204)
async def delete_shift_template(
    template_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    template = await db.get(ShiftTemplate, template_id)
    if template is None or template.tenant_id != actor.tenant_id:
        raise AppError(404, "SHIFT_TEMPLATE_NOT_FOUND", "Schichtvorlage nicht gefunden.")

    in_use = (
        await db.execute(select(EmployeeDefaultShift.id).where(EmployeeDefaultShift.shift_template_id == template_id).limit(1))
    ).first() is not None or (
        await db.execute(select(ShiftPlanEntry.id).where(ShiftPlanEntry.shift_template_id == template_id).limit(1))
    ).first() is not None
    if in_use:
        raise AppError(409, "SHIFT_TEMPLATE_IN_USE", "Die Vorlage wird noch verwendet und kann nicht gelöscht werden.")

    await db.delete(template)
    await db.commit()
