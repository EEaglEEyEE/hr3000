from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_hr_or_self
from app.db import get_db
from app.errors import AppError
from app.models import Employee, EmployeeDefaultShift, ShiftTemplate
from app.schemas.employee_default_shift import (
    EmployeeDefaultShiftCreateRequest,
    EmployeeDefaultShiftResponse,
    EmployeeDefaultShiftUpdateRequest,
)
from app.services.shift_planning_service import check_max_daily_working_time, check_rest_period_for_default
from app.services.team_scope_service import ensure_employee_visible
from app.services.period_service import ensure_open_from, ensure_range_open
from app.services.timesheet_service import invalidate_balance

router = APIRouter(tags=["employee_default_shifts"])


async def _get_employee_in_tenant(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


async def _get_template_in_tenant(db: AsyncSession, template_id: int, tenant_id: int) -> ShiftTemplate:
    template = await db.get(ShiftTemplate, template_id)
    if template is None or template.tenant_id != tenant_id:
        raise AppError(404, "SHIFT_TEMPLATE_NOT_FOUND", "Schichtvorlage nicht gefunden.")
    return template


@router.get(
    "/employees/{employee_id}/default-shifts", response_model=list[EmployeeDefaultShiftResponse]
)
async def list_default_shifts(
    employee_id: int,
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[EmployeeDefaultShiftResponse]:
    employee = await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)

    result = await db.execute(
        select(EmployeeDefaultShift)
        .where(EmployeeDefaultShift.employee_id == employee_id)
        .order_by(EmployeeDefaultShift.valid_from.desc())
    )
    return [EmployeeDefaultShiftResponse.model_validate(d) for d in result.scalars().all()]


@router.post(
    "/employees/{employee_id}/default-shifts",
    response_model=EmployeeDefaultShiftResponse,
    status_code=201,
    deprecated=True,
)
async def create_default_shift(
    employee_id: int,
    payload: EmployeeDefaultShiftCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> EmployeeDefaultShiftResponse:
    """Ältere Zuordnung "Standard-Schicht" (Soll und Pause aus der Schichtvorlage). Neu: PUT
    /employees/{id}/work-time-model mit optionaler Schichtvorlage für die Uhrzeiten.

    Effective-dated: ein neuer Default, der nach dem Start des aktuell offenen Defaults beginnt,
    schließt diesen automatisch zum Vortag ab. Zusätzlich: ArbZG-Ruhezeitprüfung über die
    gesamte Laufzeit (siehe check_rest_period_for_default), da ein Default im Gegensatz zu einem
    ShiftPlanEntry sofort und unbegrenzt in die Zukunft wirkt. Die Kernzeit übernimmt er von der
    bisher gültigen Fassung."""
    await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    template = await _get_template_in_tenant(db, payload.shift_template_id, actor.tenant_id)
    if payload.valid_to is not None and payload.valid_to < payload.valid_from:
        raise AppError(400, "INVALID_RANGE", "'valid_to' darf nicht vor 'valid_from' liegen.")
    await _ensure_default_unlocked(db, employee_id, payload.valid_from, payload.valid_to)

    result = await db.execute(
        select(EmployeeDefaultShift).where(EmployeeDefaultShift.employee_id == employee_id)
    )
    existing = result.scalars().all()
    open_default = next((d for d in existing if d.valid_to is None), None)
    before = sorted((d for d in existing if d.valid_from <= payload.valid_from), key=lambda d: d.valid_from)
    inherit = before[-1] if before else None

    if open_default is not None and payload.valid_from > open_default.valid_from:
        open_default.valid_to = payload.valid_from - timedelta(days=1)
        others = [d for d in existing if d is not open_default]
    else:
        others = existing

    new_end = payload.valid_to or date.max
    for other in others:
        other_end = other.valid_to or date.max
        if other.valid_from <= new_end and payload.valid_from <= other_end:
            raise AppError(
                400,
                "OVERLAPPING_PERIOD",
                "Der Zeitraum überlappt mit einer bestehenden Standard-Schicht.",
            )

    check_max_daily_working_time(template.start_time, template.end_time)
    await check_rest_period_for_default(
        db, employee_id, template, payload.weekdays_mask, payload.valid_from, payload.valid_to
    )

    default = EmployeeDefaultShift(
        employee_id=employee_id,
        shift_template_id=payload.shift_template_id,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        weekdays_mask=payload.weekdays_mask,
        day_minutes=",".join(str(m) for m in payload.day_minutes) if payload.day_minutes else None,
        flexible=payload.flexible,
        on_demand=payload.on_demand,
        monthly_cap_minutes=payload.monthly_cap_minutes if payload.on_demand else None,
        core_time_mode=inherit.core_time_mode if inherit else None,
        core_time_start=inherit.core_time_start if inherit else None,
        core_time_end=inherit.core_time_end if inherit else None,
        core_time_days=inherit.core_time_days if inherit else None,
    )
    db.add(default)
    await invalidate_balance(db, employee_id, payload.valid_from)
    await db.commit()
    await db.refresh(default)
    return EmployeeDefaultShiftResponse.model_validate(default)


@router.patch(
    "/employees/{employee_id}/default-shifts/{default_id}",
    response_model=EmployeeDefaultShiftResponse,
    deprecated=True,
)
async def update_default_shift(
    employee_id: int,
    default_id: int,
    payload: EmployeeDefaultShiftUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> EmployeeDefaultShiftResponse:
    await _get_employee_in_tenant(db, employee_id, actor.tenant_id)

    default = await db.get(EmployeeDefaultShift, default_id)
    if default is None or default.employee_id != employee_id:
        raise AppError(404, "DEFAULT_SHIFT_NOT_FOUND", "Standard-Schicht nicht gefunden.")
    await _ensure_default_unlocked(db, employee_id, default.valid_from, default.valid_to)

    if payload.shift_template_id is not None:
        await _get_template_in_tenant(db, payload.shift_template_id, actor.tenant_id)
        default.shift_template_id = payload.shift_template_id
    if payload.weekdays_mask is not None:
        default.weekdays_mask = payload.weekdays_mask
    if payload.valid_to is not None:
        if payload.valid_to < default.valid_from:
            raise AppError(400, "INVALID_RANGE", "'valid_to' darf nicht vor 'valid_from' liegen.")
        default.valid_to = payload.valid_to
    elif payload.clear_valid_to:
        default.valid_to = None

    if default.shift_template_id is not None:
        template = await db.get(ShiftTemplate, default.shift_template_id)
        check_max_daily_working_time(template.start_time, template.end_time)
        await check_rest_period_for_default(
            db, employee_id, template, default.weekdays_mask, default.valid_from, default.valid_to
        )
    # Auch der neue Zeitraum (z.B. verlängertes/geöffnetes Ende) darf keinen gesperrten Monat berühren.
    await _ensure_default_unlocked(db, employee_id, default.valid_from, default.valid_to)
    await invalidate_balance(db, employee_id, default.valid_from)

    await db.commit()
    await db.refresh(default)
    return EmployeeDefaultShiftResponse.model_validate(default)


@router.delete("/employees/{employee_id}/default-shifts/{default_id}", status_code=204, deprecated=True)
async def delete_default_shift(
    employee_id: int,
    default_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_employee_in_tenant(db, employee_id, actor.tenant_id)

    default = await db.get(EmployeeDefaultShift, default_id)
    if default is None or default.employee_id != employee_id:
        raise AppError(404, "DEFAULT_SHIFT_NOT_FOUND", "Standard-Schicht nicht gefunden.")
    await _ensure_default_unlocked(db, employee_id, default.valid_from, default.valid_to)

    await db.delete(default)
    await invalidate_balance(db, employee_id, default.valid_from)
    await db.commit()


async def _ensure_default_unlocked(db: AsyncSession, employee_id: int, valid_from: date, valid_to: date | None) -> None:
    """Eine Standard-Schicht wirkt auf jeden Tag ihrer Laufzeit – sie darf keinen
    abgeschlossenen/vorgelegten Monat berühren."""
    if valid_to is None:
        await ensure_open_from(db, employee_id, valid_from)
    else:
        await ensure_range_open(db, employee_id, valid_from, valid_to)
