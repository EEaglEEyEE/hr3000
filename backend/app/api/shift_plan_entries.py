from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_hr_or_self
from app.db import get_db
from app.errors import AppError
from app.models import Employee, ShiftPlanEntry, ShiftTemplate, TargetPeriod
from app.schemas.shift_plan_entry import (
    EffectiveShiftDayResponse,
    ShiftPlanEntryResponse,
    ShiftPlanEntryUpsertRequest,
)
from app.services.shift_planning_service import (
    check_max_daily_working_time,
    check_rest_period_for_entry,
    resolve_effective_shift,
    shift_planning_enabled_for_employee,
)
from app.services.scope_service import ensure_employee_visible
from app.services.period_service import ensure_period_open
from app.services.timesheet_service import invalidate_balance

router = APIRouter(tags=["shift_plan_entries"])

# Kalenderansicht/Druck/PDF-Export fragen typischerweise eine Woche oder
# einen Monat ab – dieses Limit ist eine Missbrauchsbremse, kein fachlicher
# Wert (resolve_effective_shift läuft pro Tag, kein Bulk-Query).
_MAX_EFFECTIVE_SHIFT_RANGE_DAYS = 62


async def _get_employee_in_tenant(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


@router.get(
    "/employees/{employee_id}/shift-plan-entries", response_model=list[ShiftPlanEntryResponse]
)
async def list_shift_plan_entries(
    employee_id: int,
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[ShiftPlanEntryResponse]:
    employee = await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)

    result = await db.execute(
        select(ShiftPlanEntry)
        .where(
            ShiftPlanEntry.employee_id == employee_id,
            ShiftPlanEntry.date >= date_from,
            ShiftPlanEntry.date <= date_to,
        )
        .order_by(ShiftPlanEntry.date.asc())
    )
    return [ShiftPlanEntryResponse.model_validate(e) for e in result.scalars().all()]


@router.get(
    "/employees/{employee_id}/effective-shifts", response_model=list[EffectiveShiftDayResponse]
)
async def list_effective_shifts(
    employee_id: int,
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[EffectiveShiftDayResponse]:
    """Aufgelöste Tagesplanung für Kalenderansicht/Druckansicht/PDF-Export –
    im Gegensatz zu list_shift_plan_entries auch Tage, die nur über den
    EmployeeDefaultShift oder gar nicht konfiguriert sind (siehe
    resolve_effective_shift)."""
    employee = await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)
    if date_to < date_from:
        raise AppError(400, "INVALID_RANGE", "'to' darf nicht vor 'from' liegen.")
    if (date_to - date_from).days > _MAX_EFFECTIVE_SHIFT_RANGE_DAYS:
        raise AppError(
            400,
            "RANGE_TOO_LARGE",
            f"Zeitraum darf maximal {_MAX_EFFECTIVE_SHIFT_RANGE_DAYS} Tage umfassen.",
        )

    days: list[EffectiveShiftDayResponse] = []
    current = date_from
    while current <= date_to:
        plan = await resolve_effective_shift(db, employee_id, current)
        days.append(
            EffectiveShiftDayResponse(
                date=current,
                is_workday=plan.is_workday,
                plan_exists=plan.plan_exists,
                from_entry=plan.from_entry,
                shift_template_id=plan.shift_template_id,
                target_minutes=plan.target_minutes,
                flexible=plan.flexible_weekly_minutes is not None,
                on_demand=plan.on_demand,
            )
        )
        current += timedelta(days=1)
    return days


@router.put(
    "/employees/{employee_id}/shift-plan-entries/{entry_date}",
    response_model=ShiftPlanEntryResponse,
)
async def upsert_shift_plan_entry(
    employee_id: int,
    entry_date: date,
    payload: ShiftPlanEntryUpsertRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> ShiftPlanEntryResponse:
    await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    await ensure_period_open(db, employee_id, entry_date)
    if not await shift_planning_enabled_for_employee(db, employee_id):
        raise AppError(
            400,
            "SHIFT_PLANNING_DISABLED",
            "Die Schichtplanung ist in den Einstellungen deaktiviert.",
        )

    template = None
    if payload.shift_template_id is not None:
        template = await db.get(ShiftTemplate, payload.shift_template_id)
        if template is None or template.tenant_id != actor.tenant_id:
            raise AppError(404, "SHIFT_TEMPLATE_NOT_FOUND", "Schichtvorlage nicht gefunden.")
        if template.target_period != TargetPeriod.DAILY:
            # Ein Wochen-/Monatssoll ergibt nur im Kontext einer wiederkehrenden
            # Wochentagsmaske (EmployeeDefaultShift) einen Sinn – ein einzelner
            # Ausnahme-Tag kann kein Wochen-/Monats-Total repräsentieren.
            raise AppError(
                400,
                "SHIFT_TEMPLATE_NOT_DAILY",
                "Diese Schichtvorlage hat ein Wochen- oder Monatssoll und passt nicht auf einen "
                "einzelnen Tag. Wochen- und Monatsstunden gehören ins Arbeitszeitmodell.",
            )

    target_minutes = payload.target_minutes
    if payload.is_workday:
        if target_minutes is None and template is not None:
            target_minutes = template.target_minutes
        if target_minutes is None:
            raise AppError(
                400, "TARGET_MINUTES_REQUIRED", "Für einen Arbeitstag muss ein Soll angegeben werden."
            )
    else:
        # Ein expliziter freier Tag hat kein Soll und keine Schicht.
        target_minutes = None
        template = None

    if payload.is_workday and template is not None:
        check_max_daily_working_time(template.start_time, template.end_time)
        await check_rest_period_for_entry(db, employee_id, entry_date, template.start_time, template.end_time)

    result = await db.execute(
        select(ShiftPlanEntry).where(
            ShiftPlanEntry.employee_id == employee_id, ShiftPlanEntry.date == entry_date
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        entry = ShiftPlanEntry(
            employee_id=employee_id,
            date=entry_date,
            planned_by_account_id=actor.account_id,
        )
        db.add(entry)

    entry.is_workday = payload.is_workday
    entry.shift_template_id = template.id if template is not None else None
    entry.target_minutes = target_minutes
    await invalidate_balance(db, employee_id, entry_date)

    await db.commit()
    await db.refresh(entry)
    return ShiftPlanEntryResponse.model_validate(entry)


@router.delete("/employees/{employee_id}/shift-plan-entries/{entry_date}", status_code=204)
async def delete_shift_plan_entry(
    employee_id: int,
    entry_date: date,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_employee_in_tenant(db, employee_id, actor.tenant_id)
    await ensure_period_open(db, employee_id, entry_date)

    result = await db.execute(
        select(ShiftPlanEntry).where(
            ShiftPlanEntry.employee_id == employee_id, ShiftPlanEntry.date == entry_date
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise AppError(404, "SHIFT_PLAN_ENTRY_NOT_FOUND", "Planungseintrag nicht gefunden.")

    await db.delete(entry)
    await invalidate_balance(db, employee_id, entry_date)
    await db.commit()
