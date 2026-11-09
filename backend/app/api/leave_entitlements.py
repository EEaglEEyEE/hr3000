from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal, get_current_hr_or_self
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, Employee, LeaveAdjustment, LeaveEntitlement
from app.schemas.leave_entitlement import (
    LeaveAdjustmentCreateRequest,
    LeaveAdjustmentResponse,
    LeaveEntitlementResponse,
    LeaveEntitlementUpdateRequest,
)
from app.services.audit_service import log_action
from app.services.leave_service import (
    annual_vacation_base,
    computed_entitlement,
    get_or_create_entitlement,
    leave_balance,
    workdays_per_week,
)
from app.services.settings_service import get_or_create_settings
from app.services.scope_service import ensure_employee_visible

router = APIRouter(tags=["leave_entitlements"])


async def _to_response(db: AsyncSession, employee: Employee, entitlement: LeaveEntitlement) -> LeaveEntitlementResponse:
    balance = await leave_balance(db, employee.id, entitlement.year, entitlement)
    settings_row = await get_or_create_settings(db, employee.tenant_id)
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
        suggested_entitled_days=await computed_entitlement(db, employee, entitlement.year),
        entitled_manual=entitlement.entitled_manual,
        # Jahresurlaub, der in diesem Jahr gilt (heute bzw. am nächstgelegenen Tag des Jahres)
        annual_vacation_days=await annual_vacation_base(
            db,
            employee,
            min(max(date.today(), date(entitlement.year, 1, 1)), date(entitlement.year, 12, 31)),
            float(settings_row.default_annual_vacation_days or 0),
        ),
        workdays_per_week=await workdays_per_week(db, employee.id, date.today()),
        adjustment_days=balance.adjustment_days,
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
        entitlement.entitled_manual = True
    if payload.entitled_auto:
        entitlement.entitled_manual = False
    if payload.carried_over_days is not None:
        entitlement.carried_over_days = payload.carried_over_days
        entitlement.carried_over_manual = True
    if payload.carried_over_auto:
        entitlement.carried_over_manual = False
    await db.commit()
    await db.refresh(entitlement)

    return await _to_response(db, employee, entitlement)


async def _adjustment_employee(db: AsyncSession, actor: Actor, employee_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)
    elif actor.employee is None or actor.employee.id != employee_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


@router.get("/employees/{employee_id}/leave-adjustments", response_model=list[LeaveAdjustmentResponse])
async def list_leave_adjustments(
    employee_id: int,
    year: int = Query(..., ge=2000, le=2100),
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[LeaveAdjustmentResponse]:
    """Korrekturen am Urlaubskonto eines Jahres (auch für den Mitarbeiter selbst lesbar)."""
    await _adjustment_employee(db, actor, employee_id)
    rows = await db.execute(
        select(LeaveAdjustment)
        .where(LeaveAdjustment.employee_id == employee_id, LeaveAdjustment.year == year)
        .order_by(LeaveAdjustment.created_at, LeaveAdjustment.id)
    )
    return [LeaveAdjustmentResponse.model_validate(r) for r in rows.scalars().all()]


@router.post("/employees/{employee_id}/leave-adjustments", response_model=LeaveAdjustmentResponse, status_code=201)
async def create_leave_adjustment(
    employee_id: int,
    payload: LeaveAdjustmentCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> LeaveAdjustmentResponse:
    """„Kontostand anpassen“ fürs Urlaubskonto: ± Tage, optional mit Verfallsdatum."""
    employee = await _adjustment_employee(db, actor, employee_id)
    adjustment = LeaveAdjustment(
        tenant_id=actor.tenant_id, employee_id=employee_id, year=payload.year, days=payload.days,
        expires_on=payload.expires_on, note=payload.note,
        created_by_account_id=actor.account_id,    )
    db.add(adjustment)
    await db.flush()
    expiry = f", verfällt am {payload.expires_on:%d.%m.%Y}" if payload.expires_on else ""
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id,        action=AuditAction.LEAVE_ADJUSTED, entity_type="employee", entity_id=employee.id,
        detail=f"Urlaubskonto {payload.year}: {payload.days:+g} Tage{expiry} – {payload.note}"[:500],
    )
    await db.commit()
    await db.refresh(adjustment)
    return LeaveAdjustmentResponse.model_validate(adjustment)


@router.delete("/employees/{employee_id}/leave-adjustments/{adjustment_id}", status_code=204)
async def delete_leave_adjustment(
    employee_id: int,
    adjustment_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    employee = await _adjustment_employee(db, actor, employee_id)
    adjustment = await db.get(LeaveAdjustment, adjustment_id)
    if adjustment is None or adjustment.employee_id != employee_id:
        raise AppError(404, "LEAVE_ADJUSTMENT_NOT_FOUND", "Korrektur nicht gefunden.")
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id,        action=AuditAction.LEAVE_ADJUSTED, entity_type="employee", entity_id=employee.id,
        detail=f"Urlaubskonto {adjustment.year}: Korrektur {float(adjustment.days):+g} Tage gelöscht ({adjustment.note})"[:500],
    )
    await db.delete(adjustment)
    await db.commit()
