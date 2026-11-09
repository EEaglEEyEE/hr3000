from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_hr_or_self
from app.db import get_db
from app.errors import AppError
from app.models import AdjustmentKind, AuditAction, BalanceAdjustment, Employee
from app.schemas.balance_adjustment import BalanceAdjustmentCreateRequest, BalanceAdjustmentResponse, SetBalanceRequest
from app.services.audit_service import log_action
from app.services.period_service import ensure_period_open
from app.services.scope_service import ensure_employee_visible
from app.services.timesheet_service import balance_as_of

router = APIRouter(tags=["balance-adjustments"])

_KIND_LABELS = {"OPENING_BALANCE": "Anfangskontostand", "PAYOUT": "Auszahlung", "CORRECTION": "Anpassung"}


async def _employee(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


def _audit(db: AsyncSession, actor: Actor, employee_id: int, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.BALANCE_ADJUSTED,
        entity_type="employee",
        entity_id=employee_id,
        detail=detail,
    )


def _hours(minutes: int) -> str:
    sign = "-" if minutes < 0 else "+"
    return f"{sign}{abs(minutes) // 60}:{abs(minutes) % 60:02d} Std."


@router.get("/employees/{employee_id}/balance-adjustments", response_model=list[BalanceAdjustmentResponse])
async def list_adjustments(
    employee_id: int,
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[BalanceAdjustmentResponse]:
    employee = await _employee(db, employee_id, actor.tenant_id)
    is_self = actor.employee is not None and actor.employee.id == employee_id
    if not is_self:
        if not actor.is_hr_level:
            raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
        await ensure_employee_visible(db, actor, employee)
    rows = await db.execute(
        select(BalanceAdjustment)
        .where(BalanceAdjustment.employee_id == employee_id)
        .order_by(BalanceAdjustment.effective_date.desc(), BalanceAdjustment.id.desc())
    )
    return [BalanceAdjustmentResponse.model_validate(r) for r in rows.scalars().all()]


@router.post("/employees/{employee_id}/balance-adjustments", response_model=BalanceAdjustmentResponse, status_code=201)
async def create_adjustment(
    employee_id: int,
    payload: BalanceAdjustmentCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> BalanceAdjustmentResponse:
    await _employee(db, employee_id, actor.tenant_id)
    if payload.effective_date > date.today():
        raise AppError(400, "FUTURE_DATE", "Buchungen sind nur bis heute möglich.")
    await ensure_period_open(db, employee_id, payload.effective_date)
    adjustment = BalanceAdjustment(
        tenant_id=actor.tenant_id,
        employee_id=employee_id,
        effective_date=payload.effective_date,
        minutes=payload.minutes,
        kind=payload.kind,
        note=payload.note,
        payout_factor=payload.payout_factor,
        created_by_account_id=actor.account_id,
    )
    db.add(adjustment)
    factor = f" (Faktor {payload.payout_factor})" if payload.payout_factor is not None else ""
    _audit(db, actor, employee_id, f"{_KIND_LABELS[payload.kind.value]} {_hours(payload.minutes)}{factor} zum {payload.effective_date.isoformat()}: {payload.note}"[:500])
    await db.commit()
    await db.refresh(adjustment)
    return BalanceAdjustmentResponse.model_validate(adjustment)


@router.post("/employees/{employee_id}/balance-adjustments/set-balance", response_model=BalanceAdjustmentResponse, status_code=201)
async def set_balance(
    employee_id: int,
    payload: SetBalanceRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> BalanceAdjustmentResponse:
    """„Neuen Kontostand festlegen“ – bucht die Differenz zum Stand am Ende dieses Tages als
    Anpassung (die Begründung nennt alten und neuen Stand)."""
    employee = await _employee(db, employee_id, actor.tenant_id)
    if payload.effective_date > date.today():
        raise AppError(400, "FUTURE_DATE", "Buchungen sind nur bis heute möglich.")
    await ensure_period_open(db, employee_id, payload.effective_date)
    current = (await balance_as_of(db, employee, payload.effective_date)).total_minutes
    delta = payload.balance_minutes - current
    if delta == 0:
        raise AppError(400, "BALANCE_UNCHANGED", "Der Kontostand hat an diesem Tag schon diesen Wert.")
    note = f"Neuer Kontostand {_hours(payload.balance_minutes)} (vorher {_hours(current)}): {payload.note}"[:300]
    adjustment = BalanceAdjustment(
        tenant_id=actor.tenant_id,
        employee_id=employee_id,
        effective_date=payload.effective_date,
        minutes=delta,
        kind=AdjustmentKind.CORRECTION,
        note=note,
        created_by_account_id=actor.account_id,
    )
    db.add(adjustment)
    _audit(db, actor, employee_id, f"Kontostand festgelegt zum {payload.effective_date.isoformat()}: {note}"[:500])
    await db.commit()
    await db.refresh(adjustment)
    return BalanceAdjustmentResponse.model_validate(adjustment)


@router.delete("/employees/{employee_id}/balance-adjustments/{adjustment_id}", status_code=204)
async def delete_adjustment(
    employee_id: int,
    adjustment_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _employee(db, employee_id, actor.tenant_id)
    adjustment = await db.get(BalanceAdjustment, adjustment_id)
    if adjustment is None or adjustment.employee_id != employee_id or adjustment.tenant_id != actor.tenant_id:
        raise AppError(404, "ADJUSTMENT_NOT_FOUND", "Buchung nicht gefunden.")
    await ensure_period_open(db, employee_id, adjustment.effective_date)
    _audit(db, actor, employee_id, f"Buchung gelöscht: {_KIND_LABELS[adjustment.kind.value]} {_hours(adjustment.minutes)} zum {adjustment.effective_date.isoformat()}")
    await db.delete(adjustment)
    await db.commit()
