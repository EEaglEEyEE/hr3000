"""Eigene Felder der Personalakte (Abschnitte, Felder, Werte mit Verlauf) und die
Mitarbeitendenhistorie.

Felder anlegen und ändern: Admins. Werte pflegen: Admin und HR. Mitarbeiter sehen Abschnitte mit
„VIEW“/„EDIT“ in „Mein Bereich“ (Vorschläge zu „EDIT“: app/api/change_requests.py).
"""
import json
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_admin_principal, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import Account, AttributeDefinition, AttributeSection, AttributeValue, AuditAction, AuditLogEntry, Employee
from app.schemas.attribute import (
    AttributeDefinitionRequest,
    AttributeDefinitionResponse,
    AttributeDefinitionUpdateRequest,
    AttributeHistoryEntry,
    AttributeSectionRequest,
    AttributeSectionResponse,
    AttributeSectionUpdateRequest,
    AttributeValueRequest,
    EmployeeAttributeValue,
    EmployeeHistoryEntry,
)
from app.services import attribute_service
from app.services.audit_service import log_action

router = APIRouter(tags=["attributes"])


def _definition_response(d: AttributeDefinition) -> AttributeDefinitionResponse:
    return AttributeDefinitionResponse(
        id=d.id, section_id=d.section_id, label=d.label, field_type=d.field_type,
        options=attribute_service.options_of(d), dated=d.dated, sort_order=d.sort_order, archived=d.archived,
    )


async def _sections(db: AsyncSession, tenant_id: int, include_archived: bool) -> list[AttributeSectionResponse]:
    sections = (
        await db.execute(
            select(AttributeSection)
            .where(AttributeSection.tenant_id == tenant_id)
            .order_by(AttributeSection.sort_order, AttributeSection.name)
        )
    ).scalars().all()
    definitions = (
        await db.execute(
            select(AttributeDefinition)
            .where(AttributeDefinition.tenant_id == tenant_id)
            .order_by(AttributeDefinition.sort_order, AttributeDefinition.label)
        )
    ).scalars().all()
    result = []
    for section in sections:
        if section.archived and not include_archived:
            continue
        attributes = [
            _definition_response(d) for d in definitions
            if d.section_id == section.id and (include_archived or not d.archived)
        ]
        result.append(AttributeSectionResponse.model_validate(section).model_copy(update={"attributes": attributes}))
    return result


@router.get("/attribute-sections", response_model=list[AttributeSectionResponse])
async def list_sections(
    include_archived: bool = False,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[AttributeSectionResponse]:
    return await _sections(db, actor.tenant_id, include_archived)


@router.post("/attribute-sections", response_model=AttributeSectionResponse, status_code=201)
async def create_section(
    payload: AttributeSectionRequest, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> AttributeSectionResponse:
    section = AttributeSection(tenant_id=actor.tenant_id, **payload.model_dump())
    db.add(section)
    await db.commit()
    return AttributeSectionResponse.model_validate(section)


async def _section(db: AsyncSession, section_id: int, tenant_id: int) -> AttributeSection:
    section = await db.get(AttributeSection, section_id)
    if section is None or section.tenant_id != tenant_id:
        raise AppError(404, "SECTION_NOT_FOUND", "Abschnitt nicht gefunden.")
    return section


@router.patch("/attribute-sections/{section_id}", response_model=AttributeSectionResponse)
async def update_section(
    section_id: int,
    payload: AttributeSectionUpdateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> AttributeSectionResponse:
    section = await _section(db, section_id, actor.tenant_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(section, key, value)
    await db.commit()
    return AttributeSectionResponse.model_validate(section)


@router.post("/attributes", response_model=AttributeDefinitionResponse, status_code=201)
async def create_attribute(
    payload: AttributeDefinitionRequest, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> AttributeDefinitionResponse:
    await _section(db, payload.section_id, actor.tenant_id)
    definition = AttributeDefinition(
        tenant_id=actor.tenant_id, section_id=payload.section_id, label=payload.label.strip(),
        field_type=payload.field_type, options=json.dumps(payload.options, ensure_ascii=False) if payload.options else None,
        dated=payload.dated, sort_order=payload.sort_order,
    )
    db.add(definition)
    await db.commit()
    return _definition_response(definition)


async def _definition(db: AsyncSession, attribute_id: int, tenant_id: int) -> AttributeDefinition:
    definition = await db.get(AttributeDefinition, attribute_id)
    if definition is None or definition.tenant_id != tenant_id:
        raise AppError(404, "ATTRIBUTE_NOT_FOUND", "Feld nicht gefunden.")
    return definition


@router.patch("/attributes/{attribute_id}", response_model=AttributeDefinitionResponse)
async def update_attribute(
    attribute_id: int,
    payload: AttributeDefinitionUpdateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> AttributeDefinitionResponse:
    """Art und Verlauf lassen sich nachträglich nicht ändern (bestehende Werte würden ungültig)."""
    definition = await _definition(db, attribute_id, actor.tenant_id)
    if payload.label is not None:
        definition.label = payload.label.strip()
    if payload.options is not None:
        options = [o.strip() for o in payload.options if o.strip()]
        if definition.field_type == "SELECT" and not options:
            raise AppError(400, "ATTRIBUTE_INVALID", "Für eine Auswahl bitte mindestens einen Wert angeben.")
        definition.options = json.dumps(options, ensure_ascii=False)
    if payload.sort_order is not None:
        definition.sort_order = payload.sort_order
    if payload.archived is not None:
        definition.archived = payload.archived
    await db.commit()
    return _definition_response(definition)


async def _employee(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


async def employee_values(
    db: AsyncSession, tenant_id: int, employee_id: int, section_filter=None
) -> list[EmployeeAttributeValue]:
    definitions = (
        await db.execute(select(AttributeDefinition).where(AttributeDefinition.tenant_id == tenant_id))
    ).scalars().all()
    sections = {s.id: s for s in (await db.execute(select(AttributeSection).where(AttributeSection.tenant_id == tenant_id))).scalars()}
    grouped = await attribute_service.values_for(db, employee_id)
    result = []
    for definition in definitions:
        section = sections.get(definition.section_id)
        if section_filter is not None and (section is None or not section_filter(section)):
            continue
        rows = grouped.get(definition.id, [])
        now = attribute_service.current(rows)
        result.append(
            EmployeeAttributeValue(
                attribute_id=definition.id,
                value=now.value if now else None,
                display=await attribute_service.display(db, definition, now.value if now else None),
                history=[
                    AttributeHistoryEntry(id=r.id, value=r.value, valid_from=r.valid_from, created_at=r.created_at)
                    for r in sorted(rows, key=lambda r: (r.valid_from or date.min, r.id), reverse=True)
                ] if definition.dated else [],
            )
        )
    return result


@router.get("/employees/{employee_id}/attributes", response_model=list[EmployeeAttributeValue])
async def get_employee_attributes(
    employee_id: int, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[EmployeeAttributeValue]:
    await _employee(db, employee_id, actor.tenant_id)
    return await employee_values(db, actor.tenant_id, employee_id)


async def set_value(
    db: AsyncSession, actor_account_id: int | None, employee: Employee, definition: AttributeDefinition,
    value: str | None, valid_from: date | None,
) -> str:
    """Speichert (ohne commit) und gibt eine Beschreibung fürs Audit zurück."""
    normalized = await attribute_service.normalize(db, definition, value, employee.tenant_id)
    if definition.dated:
        effective = valid_from or date.today()
        existing = (
            await db.execute(
                select(AttributeValue).where(
                    AttributeValue.employee_id == employee.id,
                    AttributeValue.attribute_id == definition.id,
                    AttributeValue.valid_from == effective,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.value = normalized
        else:
            db.add(AttributeValue(
                tenant_id=employee.tenant_id, employee_id=employee.id, attribute_id=definition.id, value=normalized,
                valid_from=effective, created_by_account_id=actor_account_id,
            ))
        shown = await attribute_service.display(db, definition, normalized)
        return f"{definition.label}: {shown or 'leer'} ab {effective:%d.%m.%Y}"
    existing = (
        await db.execute(
            select(AttributeValue).where(AttributeValue.employee_id == employee.id, AttributeValue.attribute_id == definition.id)
        )
    ).scalars().first()
    if existing is not None:
        existing.value = normalized
    else:
        db.add(AttributeValue(
            tenant_id=employee.tenant_id, employee_id=employee.id, attribute_id=definition.id, value=normalized,
            created_by_account_id=actor_account_id,
        ))
    return f"{definition.label}: {await attribute_service.display(db, definition, normalized) or 'leer'}"


@router.put("/employees/{employee_id}/attributes/{attribute_id}", response_model=list[EmployeeAttributeValue])
async def put_employee_attribute(
    employee_id: int,
    attribute_id: int,
    payload: AttributeValueRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[EmployeeAttributeValue]:
    employee = await _employee(db, employee_id, actor.tenant_id)
    definition = await _definition(db, attribute_id, actor.tenant_id)
    if definition.archived:
        raise AppError(400, "ATTRIBUTE_ARCHIVED", "Das Feld ist archiviert.")
    detail = await set_value(db, actor.account_id, employee, definition, payload.value, payload.valid_from)
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.ATTRIBUTE_CHANGED,
        entity_type="employee", entity_id=employee.id, detail=detail[:500],
    )
    await db.commit()
    return await employee_values(db, actor.tenant_id, employee_id)


@router.delete("/employees/{employee_id}/attributes/values/{value_id}", response_model=list[EmployeeAttributeValue])
async def delete_attribute_value(
    employee_id: int, value_id: int, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[EmployeeAttributeValue]:
    """Einen Eintrag im Verlauf entfernen (z. B. falsch erfasst)."""
    employee = await _employee(db, employee_id, actor.tenant_id)
    row = await db.get(AttributeValue, value_id)
    if row is None or row.employee_id != employee.id:
        raise AppError(404, "VALUE_NOT_FOUND", "Eintrag nicht gefunden.")
    definition = await db.get(AttributeDefinition, row.attribute_id)
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.ATTRIBUTE_CHANGED,
        entity_type="employee", entity_id=employee.id,
        detail=f"{definition.label}: Eintrag {row.valid_from:%d.%m.%Y} entfernt" if row.valid_from else f"{definition.label}: geleert",
    )
    await db.delete(row)
    await db.commit()
    return await employee_values(db, actor.tenant_id, employee_id)


@router.get("/me/attributes", response_model=list[AttributeSectionResponse])
async def my_attribute_sections(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> list[AttributeSectionResponse]:
    """Abschnitte, die Mitarbeiter sehen dürfen (Werte über /me/attribute-values)."""
    if actor.employee is None:
        raise AppError(403, "FORBIDDEN", "Nur für Mitarbeiter mit eigenem Login.")
    return [s for s in await _sections(db, actor.tenant_id, False) if s.employee_access != "NONE"]


@router.get("/me/attribute-values", response_model=list[EmployeeAttributeValue])
async def my_attribute_values(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> list[EmployeeAttributeValue]:
    if actor.employee is None:
        raise AppError(403, "FORBIDDEN", "Nur für Mitarbeiter mit eigenem Login.")
    return await employee_values(
        db, actor.tenant_id, actor.employee.id, section_filter=lambda s: s.employee_access != "NONE" and not s.archived
    )


@router.get("/employees/{employee_id}/history", response_model=list[EmployeeHistoryEntry])
async def employee_history(
    employee_id: int, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[EmployeeHistoryEntry]:
    """Mitarbeitendenhistorie: Änderungen am Mitarbeiter aus dem Audit-Protokoll (neueste zuerst, höchstens
    300). Vergütung erscheint nur mit „Vergütung & Lohn-Export“."""
    await _employee(db, employee_id, actor.tenant_id)
    entries = (
        await db.execute(
            select(AuditLogEntry)
            .where(
                AuditLogEntry.tenant_id == actor.tenant_id,
                AuditLogEntry.entity_type == "employee",
                AuditLogEntry.entity_id == employee_id,
            )
            .order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
            .limit(300)
        )
    ).scalars().all()
    hidden = set() if actor.has_payroll_access else {AuditAction.COMPENSATION_CHANGED, AuditAction.COMPENSATION_VIEWED}
    account_ids = {e.actor_account_id for e in entries if e.actor_account_id}
    accounts = {
        a.id: a for a in (await db.execute(select(Account).where(Account.id.in_(account_ids or {0})))).scalars()
    }
    return [
        EmployeeHistoryEntry(
            at=e.created_at,
            what=e.detail or e.action.value,
            by=accounts[e.actor_account_id].display_name if e.actor_account_id in accounts else None,
        )
        for e in entries
        if e.action not in hidden
    ]
