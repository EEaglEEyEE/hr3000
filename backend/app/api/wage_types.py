"""Seite „Lohnarten“: Lohnart je Zeitart (gearbeitete Stunden, Urlaub, Krankheit, …) und der Katalog
der Zulagen- und Einmalzahlungsarten. Lohnarten der Zuschläge stehen an der Zuschlagsregel
(PUT /surcharge-rules/{id}/wage-type). Berechtigung „Vergütung & Lohn-Export“."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_payroll_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, PayComponentType, WageTypeItem
from app.schemas.wage_type import (
    WAGE_TYPE_LABELS,
    PayComponentTypeCreateRequest,
    PayComponentTypeResponse,
    PayComponentTypeUpdateRequest,
    WageTypeItemResponse,
    WageTypesResponse,
    WageTypesUpdateRequest,
)
from app.services.audit_service import log_action
from app.services.wage_type_service import component_type, component_type_usage, set_wage_types, wage_type_map

router = APIRouter(tags=["wage_types"])


def _audit(db: AsyncSession, actor: Actor, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.SETTINGS_CHANGED,
        entity_type="wage_types",
        entity_id=actor.tenant_id,
        detail=detail[:500],
    )


async def _wage_types(db: AsyncSession, tenant_id: int) -> WageTypesResponse:
    mapping = await wage_type_map(db, tenant_id)
    return WageTypesResponse(
        items=[WageTypeItemResponse(item=item, label=WAGE_TYPE_LABELS[item], wage_type=mapping.get(item)) for item in WageTypeItem]
    )


@router.get("/wage-types", response_model=WageTypesResponse)
async def get_wage_types(
    actor: Actor = Depends(get_current_payroll_principal), db: AsyncSession = Depends(get_db)
) -> WageTypesResponse:
    return await _wage_types(db, actor.tenant_id)


@router.put("/wage-types", response_model=WageTypesResponse)
async def update_wage_types(
    payload: WageTypesUpdateRequest,
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> WageTypesResponse:
    """Nur die angegebenen Zeitarten ändern; leer = keine Lohnart."""
    changes = await set_wage_types(db, actor.tenant_id, payload.items)
    if changes:
        _audit(db, actor, "Lohnarten geändert: " + ", ".join(changes))
    await db.commit()
    return await _wage_types(db, actor.tenant_id)


async def _type_response(db: AsyncSession, item: PayComponentType, usage: dict[int, int] | None = None) -> PayComponentTypeResponse:
    usage = usage if usage is not None else await component_type_usage(db, item.tenant_id)
    return PayComponentTypeResponse(
        id=item.id, kind=item.kind, name=item.name, wage_type=item.wage_type, active=item.active, in_use=usage.get(item.id, 0)
    )


@router.get("/pay-component-types", response_model=list[PayComponentTypeResponse])
async def list_pay_component_types(
    actor: Actor = Depends(get_current_payroll_principal), db: AsyncSession = Depends(get_db)
) -> list[PayComponentTypeResponse]:
    items = (
        await db.execute(
            select(PayComponentType).where(PayComponentType.tenant_id == actor.tenant_id).order_by(PayComponentType.kind, PayComponentType.name)
        )
    ).scalars().all()
    usage = await component_type_usage(db, actor.tenant_id)
    return [await _type_response(db, item, usage) for item in items]


@router.post("/pay-component-types", response_model=PayComponentTypeResponse, status_code=201)
async def create_pay_component_type(
    payload: PayComponentTypeCreateRequest,
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> PayComponentTypeResponse:
    item = PayComponentType(tenant_id=actor.tenant_id, kind=payload.kind, name=payload.name, wage_type=payload.wage_type, active=True)
    db.add(item)
    _audit(db, actor, f"Zulagenart angelegt: {payload.name}")
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "NAME_TAKEN", "Diese Art gibt es schon.") from exc
    await db.refresh(item)
    return await _type_response(db, item)


@router.patch("/pay-component-types/{type_id}", response_model=PayComponentTypeResponse)
async def update_pay_component_type(
    type_id: int,
    payload: PayComponentTypeUpdateRequest,
    actor: Actor = Depends(get_current_payroll_principal),
    db: AsyncSession = Depends(get_db),
) -> PayComponentTypeResponse:
    """Name, Lohnart oder aktiv ändern – wirkt auf alle Zulagen dieser Art (auch im nächsten Export
    für vergangene Monate; der Betrag ändert sich dadurch nicht)."""
    item = await component_type(db, actor.tenant_id, type_id)
    changes: list[str] = []
    if payload.name is not None and payload.name != item.name:
        changes.append(f"Name {item.name} → {payload.name}")
        item.name = payload.name
    if payload.wage_type is not None and (payload.wage_type or None) != item.wage_type:
        item.wage_type = payload.wage_type or None
        changes.append(f"Lohnart {item.wage_type or 'leer'}")
    if payload.active is not None and payload.active != item.active:
        item.active = payload.active
        changes.append("aktiv" if payload.active else "inaktiv")
    if changes:
        _audit(db, actor, f"Zulagenart {item.name} geändert: {', '.join(changes)}")
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "NAME_TAKEN", "Diese Art gibt es schon.") from exc
    await db.refresh(item)
    return await _type_response(db, item)


@router.delete("/pay-component-types/{type_id}", status_code=204)
async def delete_pay_component_type(
    type_id: int, actor: Actor = Depends(get_current_payroll_principal), db: AsyncSession = Depends(get_db)
) -> None:
    item = await component_type(db, actor.tenant_id, type_id)
    if (await component_type_usage(db, actor.tenant_id)).get(item.id):
        raise AppError(409, "PAY_COMPONENT_TYPE_IN_USE", "Die Art wird noch verwendet – stattdessen auf inaktiv setzen.")
    _audit(db, actor, f"Zulagenart gelöscht: {item.name}")
    await db.delete(item)
    await db.commit()
