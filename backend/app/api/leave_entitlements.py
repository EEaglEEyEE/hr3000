from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import Employee, LeaveEntitlement
from app.schemas.leave_entitlement import LeaveEntitlementResponse, LeaveEntitlementUpdateRequest
from app.services.leave_service import (
    get_or_create_entitlement,
    leave_balance,
    suggested_entitlement,
    workdays_per_week,
)
from app.services.settings_service import get_or_create_settings
from app.services.team_scope_service import ensure_employee_visible

router = APIRouter(tags=["leave_entitlements"])


async def _to_response(db: AsyncSession, employee: Employee, entitlement: LeaveEntitlement) -> LeaveEntitlementResponse:
    balance = await leave_balance(db, employee.id, entitlement.year, entitlement)
    settings_row = await get_or_create_settings(db, employee.tenant_id)
    full_time = float(settings_row.default_annual_vacation_days)
    return LeaveEntitlementResponse(
        employee_id=entitlement.employee_id,
        year=entitlement.year,
        entitled_days=balance.entitled_days,
        carried_over_days=balance.carried_over_days,
        used_days=balance.used_days,
        remaining_days=balance.remaining_days,
        carried_over_auto=balance.carried_over_auto,
        expired_days=balance.expired_days,
        expiring_days=balance.expiring_days,
        expiry_date=balance.expiry_date,
        suggested_entitled_days=(
            await suggested_entitlement(db, employee.id, entitlement.year, full_time)
            if full_time and settings_row.prorate_part_time_vacation
            else None
        ),
        workdays_per_week=await workdays_per_week(db, employee.id, date.today()),
    )


@router.get("/employees/{employee_id}/leave-entitlement", response_model=LeaveEntitlementResponse)
async def get_leave_entitlement(
    employee_id: int,
    year: int = Query(..., ge=2000, le=2100),
    # get_current_actor statt get_current_hr_or_self: auch der Kiosk darf dies lesen,
    # um Resturlaub bei der Mitarbeiterauswahl anzuzeigen (siehe overtime-balance).
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> LeaveEntitlementResponse:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.device is not None and employee.location_id != actor.device.location_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.device is not None and not (await get_or_create_settings(db, actor.tenant_id)).kiosk_show_vacation:
        raise AppError(403, "KIOSK_VACATION_HIDDEN", "Der Resturlaub wird am Tablet nicht angezeigt.")
    if actor.employee is not None and not actor.is_hr_level and actor.employee.id != employee_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)

    entitlement = await get_or_create_entitlement(db, employee_id, year, employee.tenant_id)
    return await _to_response(db, employee, entitlement)


@router.patch("/employees/{employee_id}/leave-entitlement", response_model=LeaveEntitlementResponse)
async def update_leave_entitlement(
    employee_id: int,
    payload: LeaveEntitlementUpdateRequest,
    year: int = Query(..., ge=2000, le=2100),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> LeaveEntitlementResponse:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    await ensure_employee_visible(db, actor, employee)

    entitlement = await get_or_create_entitlement(db, employee_id, year, employee.tenant_id)
    if payload.entitled_days is not None:
        entitlement.entitled_days = payload.entitled_days
    if payload.carried_over_days is not None:
        entitlement.carried_over_days = payload.carried_over_days
        entitlement.carried_over_manual = True
    if payload.carried_over_auto:
        entitlement.carried_over_manual = False
    await db.commit()
    await db.refresh(entitlement)

    return await _to_response(db, employee, entitlement)
