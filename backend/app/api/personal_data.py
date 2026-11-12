"""Persönliche Daten und Kostenstellen eines Mitarbeiters (Personalakte → „Stammdaten“).

Lesen und ändern: Admin und HR (Führungskräfte nicht). Bank, Steuer und Sozialversicherung nur mit
„Vergütung & Lohn-Export“. Die Person selbst sieht ihre Daten in „Mein Bereich“.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, CostCenter, Employee, EmployeeCostCenter
from app.schemas.personal_data import (
    PAYROLL_FIELDS,
    CostCenterCreateRequest,
    CostCenterResponse,
    CostCenterShare,
    CostCenterUpdateRequest,
    PersonalData,
    PersonalDataResponse,
)
from app.services import personal_data_service
from app.services.audit_service import log_action

router = APIRouter(tags=["personal_data"])

_LABELS = {
    "private_email": "private E-Mail", "phone": "Telefon", "street": "Straße", "zip_code": "PLZ", "city": "Ort",
    "country": "Land", "nationality": "Staatsangehörigkeit", "birth_place": "Geburtsort", "birth_name": "Geburtsname",
    "children_count": "Kinder", "child_allowance": "Kinderfreibeträge", "iban": "IBAN", "bic": "BIC",
    "account_holder": "Kontoinhaber", "tax_id": "Steuer-ID", "tax_class": "Steuerklasse", "church_tax": "Konfession",
    "social_security_number": "SV-Nummer", "health_insurance": "Krankenkasse",
}


async def _employee(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


def _response(data: dict, payroll_visible: bool) -> PersonalDataResponse:
    shown = {k: v for k, v in data.items() if payroll_visible or k not in PAYROLL_FIELDS}
    return PersonalDataResponse(**shown, payroll_visible=payroll_visible)


@router.get("/employees/{employee_id}/personal-data", response_model=PersonalDataResponse)
async def get_personal_data(
    employee_id: int, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> PersonalDataResponse:
    await _employee(db, employee_id, actor.tenant_id)
    return _response(await personal_data_service.load(db, employee_id), actor.has_payroll_access)


@router.patch("/employees/{employee_id}/personal-data", response_model=PersonalDataResponse)
async def update_personal_data(
    employee_id: int,
    payload: PersonalData,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> PersonalDataResponse:
    """Nur mitgeschickte Felder ändern sich (null bzw. "" löscht ein Feld)."""
    employee = await _employee(db, employee_id, actor.tenant_id)
    if employee.anonymized_at is not None:
        raise AppError(400, "ALREADY_ANONYMIZED", "Anonymisierte Mitarbeiter können nicht mehr bearbeitet werden.")
    changes = payload.model_dump(exclude_unset=True)
    if PAYROLL_FIELDS & changes.keys() and not actor.can_edit_payroll:
        raise AppError(403, "PAYROLL_PERMISSION_REQUIRED", "Bank, Steuer und Sozialversicherung nur mit „Vergütung & Lohn-Export“.")
    data = await personal_data_service.load(db, employee_id)
    changed = [key for key, value in changes.items() if data.get(key) != value]
    data.update(changes)
    await personal_data_service.save(db, employee, data)
    if changed:
        log_action(
            db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.PERSONAL_DATA_CHANGED,
            entity_type="employee", entity_id=employee.id,
            detail=f"{employee.first_name} {employee.last_name}: " + ", ".join(_LABELS.get(k, k) for k in changed),
        )
    await db.commit()
    return _response(data, actor.has_payroll_access)


@router.get("/me/personal-data", response_model=PersonalDataResponse)
async def get_own_personal_data(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> PersonalDataResponse:
    if actor.employee is None:
        raise AppError(403, "FORBIDDEN", "Nur für Mitarbeiter mit eigenem Login.")
    return _response(await personal_data_service.load(db, actor.employee.id), True)


# --- Kostenstellen ---------------------------------------------------------------------------


@router.get("/cost-centers", response_model=list[CostCenterResponse])
async def list_cost_centers(
    include_archived: bool = False, actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[CostCenterResponse]:
    stmt = select(CostCenter).where(CostCenter.tenant_id == actor.tenant_id)
    if not include_archived:
        stmt = stmt.where(CostCenter.archived.is_(False))
    return [CostCenterResponse.model_validate(c) for c in (await db.execute(stmt.order_by(CostCenter.code))).scalars()]


async def _cost_center(db: AsyncSession, cost_center_id: int, tenant_id: int) -> CostCenter:
    cost_center = await db.get(CostCenter, cost_center_id)
    if cost_center is None or cost_center.tenant_id != tenant_id:
        raise AppError(404, "COST_CENTER_NOT_FOUND", "Kostenstelle nicht gefunden.")
    return cost_center


@router.post("/cost-centers", response_model=CostCenterResponse, status_code=201)
async def create_cost_center(
    payload: CostCenterCreateRequest, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> CostCenterResponse:
    cost_center = CostCenter(tenant_id=actor.tenant_id, code=payload.code.strip(), name=payload.name.strip())
    db.add(cost_center)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "COST_CENTER_CODE_TAKEN", "Diese Kostenstellen-Nummer gibt es schon.") from exc
    return CostCenterResponse.model_validate(cost_center)


@router.patch("/cost-centers/{cost_center_id}", response_model=CostCenterResponse)
async def update_cost_center(
    cost_center_id: int,
    payload: CostCenterUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> CostCenterResponse:
    cost_center = await _cost_center(db, cost_center_id, actor.tenant_id)
    if payload.code is not None:
        cost_center.code = payload.code.strip()
    if payload.name is not None:
        cost_center.name = payload.name.strip()
    if payload.archived is not None:
        cost_center.archived = payload.archived
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "COST_CENTER_CODE_TAKEN", "Diese Kostenstellen-Nummer gibt es schon.") from exc
    return CostCenterResponse.model_validate(cost_center)


@router.delete("/cost-centers/{cost_center_id}", status_code=204)
async def delete_cost_center(
    cost_center_id: int, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> None:
    """Nur unbenutzte; benutzte bitte archivieren (bleiben bei den Mitarbeitern stehen)."""
    cost_center = await _cost_center(db, cost_center_id, actor.tenant_id)
    used = await db.scalar(
        select(func.count()).select_from(EmployeeCostCenter).where(EmployeeCostCenter.cost_center_id == cost_center.id)
    )
    if used:
        raise AppError(409, "COST_CENTER_IN_USE", "Die Kostenstelle ist Mitarbeitern zugeordnet – bitte archivieren.")
    await db.delete(cost_center)
    await db.commit()


@router.put("/employees/{employee_id}/cost-centers", response_model=list[CostCenterShare])
async def set_employee_cost_centers(
    employee_id: int,
    payload: list[CostCenterShare],
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[CostCenterShare]:
    """Aufteilung in Prozent; zusammen 100 (leere Liste = keine Kostenstelle)."""
    employee = await _employee(db, employee_id, actor.tenant_id)
    if len(payload) > 10:
        raise AppError(400, "COST_CENTERS_INVALID", "Höchstens 10 Kostenstellen je Mitarbeiter.")
    if payload and sum(share.percent for share in payload) != 100:
        raise AppError(400, "COST_CENTERS_INVALID", "Die Anteile müssen zusammen 100 % ergeben.")
    if len({share.cost_center_id for share in payload}) != len(payload):
        raise AppError(400, "COST_CENTERS_INVALID", "Jede Kostenstelle nur einmal.")
    labels = []
    for share in payload:
        cost_center = await _cost_center(db, share.cost_center_id, actor.tenant_id)
        existing = any(c.cost_center_id == share.cost_center_id for c in employee.cost_centers)
        if cost_center.archived and not existing:
            raise AppError(400, "COST_CENTER_ARCHIVED", f"Kostenstelle {cost_center.code} ist archiviert.")
        labels.append(f"{cost_center.code} {share.percent} %")
    employee.cost_centers = [EmployeeCostCenter(cost_center_id=s.cost_center_id, percent=s.percent) for s in payload]
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.COST_CENTERS_CHANGED,
        entity_type="employee", entity_id=employee.id,
        detail=f"{employee.first_name} {employee.last_name}: " + (", ".join(labels) or "keine"),
    )
    await db.commit()
    return [CostCenterShare.model_validate(c) for c in employee.cost_centers]
