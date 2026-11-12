"""Änderungen eigener Daten vorschlagen (Mitarbeiter, „Mein Bereich“ → „Meine Daten“) und unter
„Zu klären“ → „Datenänderungen“ übernehmen oder ablehnen (Admin/HR; Bank/Steuer/SV nur mit
„Vergütung & Lohn-Export“).
"""
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.role_permissions import Area
from app.api.attributes import set_value
from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal
from app.api.personal_data import _LABELS
from app.db import get_db
from app.errors import AppError
from app.models import (
    AttributeDefinition,
    AttributeSection,
    AuditAction,
    DataChangeRequest,
    Employee,
    NotificationType,
)
from app.schemas.change_request import ChangeDecision, ChangeItem, ChangeProposal, ChangeRequestResponse
from app.schemas.personal_data import PAYROLL_FIELDS
from app.services import attribute_service, personal_data_service
from app.services.audit_service import log_action
from app.services.notification_service import _notify_accounts, _notify_employee, full_hr_recipients
from app.services.secret_box import decrypt_secret, encrypt_secret

router = APIRouter(tags=["change_requests"])


def _changes(row: DataChangeRequest) -> dict:
    return json.loads(decrypt_secret(row.changes) or "{}")


async def _items(db: AsyncSession, row: DataChangeRequest, show_payroll: bool) -> list[ChangeItem]:
    changes = _changes(row)
    current = await personal_data_service.load(db, row.employee_id)
    items = []
    for key, new in changes.get("personal", {}).items():
        hidden = key in PAYROLL_FIELDS and not show_payroll
        items.append(ChangeItem(
            field=key, label=_LABELS.get(key, key),
            old=None if hidden else (None if current.get(key) is None else str(current.get(key))),
            new="•••" if hidden else (None if new is None else str(new)),
        ))
    values = await attribute_service.values_for(db, row.employee_id)
    for attribute_id, new in changes.get("attributes", {}).items():
        definition = await db.get(AttributeDefinition, int(attribute_id))
        if definition is None:
            continue
        now = attribute_service.current(values.get(definition.id, []))
        items.append(ChangeItem(
            field=f"attribute:{definition.id}", label=definition.label,
            old=await attribute_service.display(db, definition, now.value if now else None),
            new=await attribute_service.display(db, definition, new),
        ))
    return items


async def _response(db: AsyncSession, row: DataChangeRequest, show_payroll: bool) -> ChangeRequestResponse:
    employee = await db.get(Employee, row.employee_id)
    return ChangeRequestResponse(
        id=row.id, employee_id=row.employee_id, employee_name=f"{employee.first_name} {employee.last_name}",
        status=row.status, created_at=row.created_at, decided_at=row.decided_at, decision_note=row.decision_note,
        note=_changes(row).get("note"), contains_payroll=row.contains_payroll,
        items=await _items(db, row, show_payroll),
    )


@router.post("/me/change-requests", response_model=ChangeRequestResponse, status_code=201)
async def propose_change(
    payload: ChangeProposal, actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)
) -> ChangeRequestResponse:
    employee = actor.employee
    if employee is None:
        raise AppError(403, "FORBIDDEN", "Nur für Mitarbeiter mit eigenem Login.")
    personal = payload.personal.model_dump(exclude_unset=True)
    attributes: dict[str, str | None] = {}
    for attribute_id, value in payload.attributes.items():
        definition = await db.get(AttributeDefinition, attribute_id)
        section = await db.get(AttributeSection, definition.section_id) if definition else None
        if (
            definition is None or definition.tenant_id != actor.tenant_id or definition.archived
            or section is None or section.employee_access != "EDIT" or section.archived
        ):
            raise AppError(400, "ATTRIBUTE_NOT_EDITABLE", "Dieses Feld kann nicht vorgeschlagen werden.")
        attributes[str(attribute_id)] = await attribute_service.normalize(db, definition, value, actor.tenant_id)
    if not personal and not attributes:
        raise AppError(400, "NOTHING_CHANGED", "Bitte mindestens ein Feld ändern.")
    row = DataChangeRequest(
        tenant_id=actor.tenant_id, employee_id=employee.id,
        changes=encrypt_secret(json.dumps({"personal": personal, "attributes": attributes, "note": payload.note}, ensure_ascii=False)),
        contains_payroll=bool(PAYROLL_FIELDS & personal.keys()),
    )
    db.add(row)
    await db.flush()
    await _notify_accounts(
        db, actor.tenant_id, await full_hr_recipients(db, actor.tenant_id, exclude_employee_id=employee.id, area=Area.EMPLOYEES),
        NotificationType.DATA_CHANGE_REQUESTED,
        f"{employee.first_name} {employee.last_name} schlägt eine Änderung der eigenen Daten vor (Zu klären → Datenänderungen).",
        "Datenänderung vorgeschlagen",
    )
    await db.commit()
    return await _response(db, row, True)


@router.get("/me/change-requests", response_model=list[ChangeRequestResponse])
async def my_change_requests(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> list[ChangeRequestResponse]:
    if actor.employee is None:
        raise AppError(403, "FORBIDDEN", "Nur für Mitarbeiter mit eigenem Login.")
    rows = (
        await db.execute(
            select(DataChangeRequest)
            .where(DataChangeRequest.employee_id == actor.employee.id)
            .order_by(DataChangeRequest.created_at.desc(), DataChangeRequest.id.desc())
            .limit(20)
        )
    ).scalars().all()
    return [await _response(db, row, True) for row in rows]


@router.get("/change-requests", response_model=list[ChangeRequestResponse])
async def list_change_requests(
    status: str = Query(default="PENDING", pattern="^(PENDING|APPROVED|REJECTED)$"),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[ChangeRequestResponse]:
    rows = (
        await db.execute(
            select(DataChangeRequest)
            .where(DataChangeRequest.tenant_id == actor.tenant_id, DataChangeRequest.status == status)
            .order_by(DataChangeRequest.created_at.asc())
            .limit(200)
        )
    ).scalars().all()
    return [await _response(db, row, actor.has_payroll_access) for row in rows]


@router.post("/change-requests/{request_id}/decide", response_model=ChangeRequestResponse)
async def decide_change_request(
    request_id: int,
    payload: ChangeDecision,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> ChangeRequestResponse:
    row = await db.get(DataChangeRequest, request_id)
    if row is None or row.tenant_id != actor.tenant_id:
        raise AppError(404, "CHANGE_REQUEST_NOT_FOUND", "Vorschlag nicht gefunden.")
    if row.status != "PENDING":
        raise AppError(400, "NOT_PENDING", "Dieser Vorschlag wurde bereits entschieden.")
    if row.contains_payroll and not actor.can_edit_payroll:
        raise AppError(403, "PAYROLL_PERMISSION_REQUIRED", "Bank, Steuer und Sozialversicherung nur mit „Vergütung & Lohn-Export“.")
    employee = await db.get(Employee, row.employee_id)
    if actor.employee is not None and actor.employee.id == employee.id:
        raise AppError(403, "FOUR_EYES", "Eigene Vorschläge übernimmt jemand anderes.")
    response_before = await _response(db, row, True)
    if payload.approve:
        changes = _changes(row)
        if changes.get("personal"):
            data = await personal_data_service.load(db, employee.id)
            data.update(changes["personal"])
            await personal_data_service.save(db, employee, data)
        details = []
        for attribute_id, value in changes.get("attributes", {}).items():
            definition = await db.get(AttributeDefinition, int(attribute_id))
            if definition is not None and not definition.archived:
                details.append(await set_value(db, actor.account_id, employee, definition, value, None))
        labels = ", ".join(item.label for item in response_before.items)
        log_action(
            db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.PERSONAL_DATA_CHANGED,
            entity_type="employee", entity_id=employee.id,
            detail=f"Vorschlag von {employee.first_name} {employee.last_name} übernommen: {labels}"[:500],
        )
    row.status = "APPROVED" if payload.approve else "REJECTED"
    row.decided_by_account_id = actor.account_id
    row.decided_at = datetime.now(UTC).replace(tzinfo=None)
    row.decision_note = payload.note
    outcome = "übernommen" if payload.approve else "abgelehnt"
    await _notify_employee(
        db, actor.tenant_id, employee, NotificationType.DATA_CHANGE_DECIDED,
        f"Dein Vorschlag zu deinen Daten wurde {outcome}." + (f" Hinweis: {payload.note}" if payload.note else ""),
        "Datenänderung entschieden",
    )
    await db.commit()
    return await _response(db, row, actor.has_payroll_access)
