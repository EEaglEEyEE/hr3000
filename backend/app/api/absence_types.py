from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_admin_principal
from app.db import get_db
from app.errors import AppError
from app.models import Absence, AbsenceType, AuditAction, AbsenceTypeDefinition
from app.schemas.absence_type import AbsenceTypeCreateRequest, AbsenceTypeResponse, AbsenceTypeUpdateRequest
from app.services.absence_type_service import list_absence_types
from app.services.audit_service import log_action
from app.services.period_service import ensure_range_open
from app.services.absence_type_service import CATEGORY_LABELS
from app.services.timesheet_service import invalidate_balance

router = APIRouter(tags=["absence_types"])


async def _get_in_tenant(db: AsyncSession, type_id: int, tenant_id: int) -> AbsenceTypeDefinition:
    row = await db.get(AbsenceTypeDefinition, type_id)
    if row is None or row.tenant_id != tenant_id:
        raise AppError(404, "ABSENCE_TYPE_NOT_FOUND", "Abwesenheitsart nicht gefunden.")
    return row


async def _ensure_unique_name(db: AsyncSession, tenant_id: int, name: str, exclude_id: int | None = None) -> None:
    stmt = select(AbsenceTypeDefinition.id).where(
        AbsenceTypeDefinition.tenant_id == tenant_id, AbsenceTypeDefinition.name == name
    )
    if exclude_id is not None:
        stmt = stmt.where(AbsenceTypeDefinition.id != exclude_id)
    if (await db.execute(stmt)).first() is not None:
        raise AppError(409, "ABSENCE_TYPE_EXISTS", "Eine Abwesenheitsart mit diesem Namen gibt es schon.")


def _audit(db: AsyncSession, actor: Actor, row: AbsenceTypeDefinition, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.SETTINGS_CHANGED,
        entity_type="absence_type",
        entity_id=row.id,
        detail=detail,
    )


@router.get("/absence-types", response_model=list[AbsenceTypeResponse])
async def get_absence_types(
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[AbsenceTypeResponse]:
    """Für alle Anmeldungen lesbar (Kalenderfarben, Antragsformular im Self-Service)."""
    if actor.device is not None:
        raise AppError(403, "FORBIDDEN", "Kein Zugriff auf diese Daten.")
    rows = await list_absence_types(db, actor.tenant_id)
    await db.commit()
    return [AbsenceTypeResponse.model_validate(r) for r in rows]


@router.post("/absence-types", response_model=AbsenceTypeResponse, status_code=201)
async def create_absence_type(
    payload: AbsenceTypeCreateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> AbsenceTypeResponse:
    await list_absence_types(db, actor.tenant_id)  # Standardarten zuerst anlegen
    await _ensure_unique_name(db, actor.tenant_id, payload.name)
    row = AbsenceTypeDefinition(tenant_id=actor.tenant_id, active=True, **payload.model_dump())
    db.add(row)
    await db.flush()
    _audit(db, actor, row, f"Abwesenheitsart angelegt: {row.name} ({row.category.value})")
    await db.commit()
    await db.refresh(row)
    return AbsenceTypeResponse.model_validate(row)


async def _change_category(db: AsyncSession, actor: Actor, row: AbsenceTypeDefinition, category: AbsenceType) -> None:
    absences = (await db.execute(select(Absence).where(Absence.absence_type_id == row.id))).scalars().all()
    if category == AbsenceType.VACATION and any(a.duration_minutes is not None for a in absences):
        raise AppError(
            409,
            "DURATION_NOT_FOR_VACATION",
            "Es gibt Einträge dieser Art mit Stundenangabe – Urlaub zählt nur in ganzen oder halben Tagen.",
        )
    earliest: dict[int, object] = {}
    for absence in absences:
        # Abgeschlossene/vorgelegte Monate dürfen sich nicht nachträglich ändern.
        await ensure_range_open(db, absence.employee_id, absence.date_from, absence.date_to)
        absence.type = category
        earliest[absence.employee_id] = min(earliest.get(absence.employee_id, absence.date_from), absence.date_from)
    for employee_id, from_date in earliest.items():
        await invalidate_balance(db, employee_id, from_date)
    _audit(
        db,
        actor,
        row,
        f"Kategorie geändert: {row.name} {CATEGORY_LABELS[row.category]} → {CATEGORY_LABELS[category]} "
        f"({len(absences)} Einträge neu berechnet)",
    )
    row.category = category


@router.patch("/absence-types/{type_id}", response_model=AbsenceTypeResponse)
async def update_absence_type(
    type_id: int,
    payload: AbsenceTypeUpdateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> AbsenceTypeResponse:
    """Eine geänderte Kategorie gilt auch für bestehende Einträge dieser Art: sie werden neu
    berechnet (Gleitzeitkonto, Urlaubskonto) – außer ein Eintrag liegt in einem abgeschlossenen
    bzw. vorgelegten Monat, dann wird die Änderung abgelehnt. Statt Löschen gibt es Deaktivieren."""
    row = await _get_in_tenant(db, type_id, actor.tenant_id)
    if payload.category is not None and payload.category != row.category:
        await _change_category(db, actor, row, payload.category)
    if payload.name is not None and payload.name != row.name:
        await _ensure_unique_name(db, actor.tenant_id, payload.name, exclude_id=row.id)
        row.name = payload.name
    if payload.color is not None:
        row.color = payload.color
    if payload.requires_approval is not None:
        row.requires_approval = payload.requires_approval
    if payload.employee_can_request is not None:
        row.employee_can_request = payload.employee_can_request
    if payload.clear_certificate_from_day:
        row.certificate_from_day = None
    elif payload.certificate_from_day is not None:
        row.certificate_from_day = payload.certificate_from_day
    if payload.active is not None:
        row.active = payload.active
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    _audit(db, actor, row, f"Abwesenheitsart geändert: {row.name}")
    await db.commit()
    await db.refresh(row)
    return AbsenceTypeResponse.model_validate(row)
