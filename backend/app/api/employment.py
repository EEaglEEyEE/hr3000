from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, Compensation, ContractType, Employee, EmploymentContract
from app.schemas.employment import (
    CompensationCreateRequest,
    CompensationResponse,
    ContractCreateRequest,
    ContractResponse,
    ContractUpdateRequest,
)
from app.services.audit_service import log_action
from app.services.effective_dating import apply_new_period

router = APIRouter(tags=["employment"])


async def _employee_in_tenant(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


def _audit(db: AsyncSession, actor: Actor, action: AuditAction, employee: Employee, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=action,
        entity_type="employee",
        entity_id=employee.id,
        detail=detail,
    )


# --- Vertragsdaten (Admin/HR) ---------------------------------------------------------------


@router.get("/employees/{employee_id}/contracts", response_model=list[ContractResponse])
async def list_contracts(
    employee_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[ContractResponse]:
    await _employee_in_tenant(db, employee_id, actor.tenant_id)
    result = await db.execute(
        select(EmploymentContract)
        .where(EmploymentContract.employee_id == employee_id)
        .order_by(EmploymentContract.valid_from.desc())
    )
    return [ContractResponse.model_validate(c) for c in result.scalars().all()]


@router.post("/employees/{employee_id}/contracts", response_model=ContractResponse, status_code=201)
async def create_contract(
    employee_id: int,
    payload: ContractCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> ContractResponse:
    employee = await _employee_in_tenant(db, employee_id, actor.tenant_id)
    existing = list(
        (await db.execute(select(EmploymentContract).where(EmploymentContract.employee_id == employee_id)))
        .scalars()
        .all()
    )
    apply_new_period(existing, payload.valid_from, payload.valid_to, "Der Zeitraum überlappt mit einem bestehenden Vertrag.")

    contract = EmploymentContract(tenant_id=actor.tenant_id, employee_id=employee_id, **payload.model_dump())
    db.add(contract)
    _audit(db, actor, AuditAction.CONTRACT_CHANGED, employee, f"Vertrag angelegt ({payload.contract_type.value}) ab {payload.valid_from.isoformat()}")
    await db.commit()
    await db.refresh(contract)
    return ContractResponse.model_validate(contract)


@router.patch("/employees/{employee_id}/contracts/{contract_id}", response_model=ContractResponse)
async def update_contract(
    employee_id: int,
    contract_id: int,
    payload: ContractUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> ContractResponse:
    employee = await _employee_in_tenant(db, employee_id, actor.tenant_id)
    contract = await db.get(EmploymentContract, contract_id)
    if contract is None or contract.employee_id != employee_id:
        raise AppError(404, "CONTRACT_NOT_FOUND", "Vertrag nicht gefunden.")

    if payload.job_title is not None:
        contract.job_title = payload.job_title or None
    if payload.notice_period is not None:
        contract.notice_period = payload.notice_period or None
    if payload.notes is not None:
        contract.notes = payload.notes or None
    if payload.probation_end is not None:
        contract.probation_end = payload.probation_end
    elif payload.clear_probation_end:
        contract.probation_end = None
    if payload.fixed_term_end is not None:
        contract.fixed_term_end = payload.fixed_term_end
    elif payload.clear_fixed_term_end:
        if contract.contract_type == ContractType.FIXED_TERM:
            raise AppError(400, "FIXED_TERM_END_REQUIRED", "Bei einem befristeten Vertrag ist ein Befristungsende erforderlich.")
        contract.fixed_term_end = None
    if payload.valid_to is not None:
        if payload.valid_to < contract.valid_from:
            raise AppError(400, "INVALID_RANGE", "'valid_to' darf nicht vor 'valid_from' liegen.")
        contract.valid_to = payload.valid_to
    elif payload.clear_valid_to:
        contract.valid_to = None

    # Verlängern/Öffnen darf keinen Zeitraum eines anderen Vertrags überdecken.
    new_end = contract.valid_to or date.max
    others = (
        await db.execute(
            select(EmploymentContract).where(
                EmploymentContract.employee_id == employee_id, EmploymentContract.id != contract.id
            )
        )
    ).scalars().all()
    if any(o.valid_from <= new_end and contract.valid_from <= (o.valid_to or date.max) for o in others):
        raise AppError(400, "OVERLAPPING_PERIOD", "Der Zeitraum überlappt mit einem bestehenden Vertrag.")

    _audit(db, actor, AuditAction.CONTRACT_CHANGED, employee, f"Vertrag geändert (ab {contract.valid_from.isoformat()})")
    await db.commit()
    await db.refresh(contract)
    return ContractResponse.model_validate(contract)


@router.delete("/employees/{employee_id}/contracts/{contract_id}", status_code=204)
async def delete_contract(
    employee_id: int,
    contract_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    employee = await _employee_in_tenant(db, employee_id, actor.tenant_id)
    contract = await db.get(EmploymentContract, contract_id)
    if contract is None or contract.employee_id != employee_id:
        raise AppError(404, "CONTRACT_NOT_FOUND", "Vertrag nicht gefunden.")
    _audit(db, actor, AuditAction.CONTRACT_CHANGED, employee, f"Vertrag gelöscht (ab {contract.valid_from.isoformat()})")
    await db.delete(contract)
    await db.commit()


# --- Vergütung (nur Admin) ------------------------------------------------------------------


@router.get("/employees/{employee_id}/compensation", response_model=list[CompensationResponse])
async def list_compensation(
    employee_id: int,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> list[CompensationResponse]:
    employee = await _employee_in_tenant(db, employee_id, actor.tenant_id)
    result = await db.execute(
        select(Compensation).where(Compensation.employee_id == employee_id).order_by(Compensation.valid_from.desc())
    )
    _audit(db, actor, AuditAction.COMPENSATION_VIEWED, employee, "Vergütung eingesehen")
    await db.commit()
    return [CompensationResponse.model_validate(c) for c in result.scalars().all()]


@router.post("/employees/{employee_id}/compensation", response_model=CompensationResponse, status_code=201)
async def create_compensation(
    employee_id: int,
    payload: CompensationCreateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> CompensationResponse:
    employee = await _employee_in_tenant(db, employee_id, actor.tenant_id)
    existing = list(
        (await db.execute(select(Compensation).where(Compensation.employee_id == employee_id))).scalars().all()
    )
    apply_new_period(existing, payload.valid_from, payload.valid_to, "Der Zeitraum überlappt mit einer bestehenden Vergütung.")

    compensation = Compensation(tenant_id=actor.tenant_id, employee_id=employee_id, **payload.model_dump())
    db.add(compensation)
    # Bewusst ohne Betrag: der Audit-Log ist auch für HR lesbar.
    _audit(db, actor, AuditAction.COMPENSATION_CHANGED, employee, f"Vergütung angelegt ({payload.pay_type.value}) ab {payload.valid_from.isoformat()}")
    await db.commit()
    await db.refresh(compensation)
    return CompensationResponse.model_validate(compensation)


@router.delete("/employees/{employee_id}/compensation/{compensation_id}", status_code=204)
async def delete_compensation(
    employee_id: int,
    compensation_id: int,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    employee = await _employee_in_tenant(db, employee_id, actor.tenant_id)
    compensation = await db.get(Compensation, compensation_id)
    if compensation is None or compensation.employee_id != employee_id:
        raise AppError(404, "COMPENSATION_NOT_FOUND", "Vergütung nicht gefunden.")
    _audit(db, actor, AuditAction.COMPENSATION_CHANGED, employee, f"Vergütung gelöscht (ab {compensation.valid_from.isoformat()})")
    await db.delete(compensation)
    await db.commit()
