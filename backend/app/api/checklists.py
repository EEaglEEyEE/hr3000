from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import (
    AuditAction,
    ChecklistKind,
    ChecklistRole,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Employee,
    EmployeeChecklist,
    EmployeeChecklistItem,
)
from app.schemas.checklist import (
    ChecklistItemResponse,
    ChecklistItemUpdateRequest,
    ChecklistResponse,
    ChecklistStartRequest,
    OpenChecklistItem,
    TemplateCreateRequest,
    TemplateItemInput,
    TemplateResponse,
    TemplateUpdateRequest,
)
from app.services.audit_service import log_action

router = APIRouter(tags=["checklists"])

_DEFAULTS: dict[ChecklistKind, tuple[str, list[tuple[str, ChecklistRole, int]]]] = {
    ChecklistKind.ONBOARDING: (
        "Standard-Onboarding",
        [
            ("Arbeitsvertrag unterschrieben zurückerhalten", ChecklistRole.HR, -7),
            ("Personalfragebogen und Bankverbindung erfassen", ChecklistRole.EMPLOYEE, -3),
            ("Sozialversicherungsnachweis / Steuer-ID erfassen", ChecklistRole.HR, -3),
            ("Arbeitsplatz, Zugänge und Technik vorbereiten", ChecklistRole.IT, -2),
            ("Zeiterfassung (PIN/Karte) einrichten", ChecklistRole.HR, 0),
            ("Einweisung durch Vorgesetzten / Einarbeitungsplan", ChecklistRole.SUPERVISOR, 0),
            ("Belehrungen (Arbeitsschutz, Datenschutz) dokumentieren", ChecklistRole.HR, 7),
            ("Probezeitgespräch führen", ChecklistRole.SUPERVISOR, 90),
        ],
    ),
    ChecklistKind.OFFBOARDING: (
        "Standard-Offboarding",
        [
            ("Kündigung / Aufhebungsvertrag ablegen", ChecklistRole.HR, -30),
            ("Resturlaub und Überstunden klären", ChecklistRole.HR, -14),
            ("Übergabe der Aufgaben organisieren", ChecklistRole.SUPERVISOR, -7),
            ("Arbeitsmittel (Laptop, Schlüssel, Karte) zurücknehmen", ChecklistRole.IT, 0),
            ("Zugänge und Konten sperren", ChecklistRole.IT, 0),
            ("Arbeitszeugnis erstellen", ChecklistRole.HR, 7),
            ("Abmeldung Sozialversicherung / Abrechnung veranlassen", ChecklistRole.HR, 7),
            ("Mitarbeiter deaktivieren bzw. nach Fristen anonymisieren", ChecklistRole.HR, 30),
        ],
    ),
}


async def _employee(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


async def _template(db: AsyncSession, template_id: int, tenant_id: int) -> ChecklistTemplate:
    template = await db.get(ChecklistTemplate, template_id)
    if template is None or template.tenant_id != tenant_id:
        raise AppError(404, "CHECKLIST_TEMPLATE_NOT_FOUND", "Checklisten-Vorlage nicht gefunden.")
    return template


async def _template_response(db: AsyncSession, template: ChecklistTemplate) -> TemplateResponse:
    items = (
        await db.execute(
            select(ChecklistTemplateItem)
            .where(ChecklistTemplateItem.template_id == template.id)
            .order_by(ChecklistTemplateItem.position)
        )
    ).scalars().all()
    return TemplateResponse(
        id=template.id,
        kind=template.kind,
        name=template.name,
        items=[
            dict(id=i.id, position=i.position, title=i.title, description=i.description, responsible=i.responsible, due_offset_days=i.due_offset_days)
            for i in items
        ],
    )


def _add_items(db: AsyncSession, template_id: int, items: list[TemplateItemInput]) -> None:
    for position, item in enumerate(items):
        db.add(
            ChecklistTemplateItem(
                template_id=template_id,
                position=position,
                title=item.title,
                description=item.description,
                responsible=item.responsible,
                due_offset_days=item.due_offset_days,
            )
        )


# --- Vorlagen ----------------------------------------------------------------------------------


@router.get("/checklist-templates", response_model=list[TemplateResponse])
async def list_templates(
    actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[TemplateResponse]:
    templates = (
        await db.execute(select(ChecklistTemplate).where(ChecklistTemplate.tenant_id == actor.tenant_id).order_by(ChecklistTemplate.kind, ChecklistTemplate.name))
    ).scalars().all()
    return [await _template_response(db, t) for t in templates]


@router.post("/checklist-templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    payload: TemplateCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    template = ChecklistTemplate(tenant_id=actor.tenant_id, kind=payload.kind, name=payload.name)
    db.add(template)
    await db.flush()
    _add_items(db, template.id, payload.items)
    await db.commit()
    return await _template_response(db, template)


@router.post("/checklist-templates/defaults", response_model=list[TemplateResponse], status_code=201)
async def create_default_templates(
    actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[TemplateResponse]:
    if (await db.execute(select(ChecklistTemplate.id).where(ChecklistTemplate.tenant_id == actor.tenant_id))).first():
        raise AppError(409, "CHECKLIST_TEMPLATES_EXIST", "Es sind bereits Vorlagen vorhanden.")
    created = []
    for kind, (name, items) in _DEFAULTS.items():
        template = ChecklistTemplate(tenant_id=actor.tenant_id, kind=kind, name=name)
        db.add(template)
        await db.flush()
        _add_items(db, template.id, [TemplateItemInput(title=t, responsible=r, due_offset_days=o) for t, r, o in items])
        created.append(template)
    await db.commit()
    return [await _template_response(db, t) for t in created]


@router.patch("/checklist-templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    payload: TemplateUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    template = await _template(db, template_id, actor.tenant_id)
    if payload.name is not None:
        template.name = payload.name
    if payload.items is not None:
        for old in (await db.execute(select(ChecklistTemplateItem).where(ChecklistTemplateItem.template_id == template.id))).scalars().all():
            await db.delete(old)
        await db.flush()
        _add_items(db, template.id, payload.items)
    await db.commit()
    return await _template_response(db, template)


@router.delete("/checklist-templates/{template_id}", status_code=204)
async def delete_template(
    template_id: int, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> None:
    template = await _template(db, template_id, actor.tenant_id)
    for item in (await db.execute(select(ChecklistTemplateItem).where(ChecklistTemplateItem.template_id == template.id))).scalars().all():
        await db.delete(item)
    await db.delete(template)
    await db.commit()


# --- Checklisten am Mitarbeiter -----------------------------------------------------------------


async def _checklist_response(db: AsyncSession, checklist: EmployeeChecklist) -> ChecklistResponse:
    items = (
        await db.execute(
            select(EmployeeChecklistItem)
            .where(EmployeeChecklistItem.checklist_id == checklist.id)
            .order_by(EmployeeChecklistItem.position)
        )
    ).scalars().all()
    return ChecklistResponse(
        id=checklist.id,
        employee_id=checklist.employee_id,
        kind=checklist.kind,
        name=checklist.name,
        anchor_date=checklist.anchor_date,
        items=[ChecklistItemResponse.model_validate(i) for i in items],
    )


@router.get("/employees/{employee_id}/checklists", response_model=list[ChecklistResponse])
async def list_employee_checklists(
    employee_id: int, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[ChecklistResponse]:
    await _employee(db, employee_id, actor.tenant_id)
    checklists = (
        await db.execute(select(EmployeeChecklist).where(EmployeeChecklist.employee_id == employee_id).order_by(EmployeeChecklist.id.desc()))
    ).scalars().all()
    return [await _checklist_response(db, c) for c in checklists]


@router.post("/employees/{employee_id}/checklists", response_model=ChecklistResponse, status_code=201)
async def start_checklist(
    employee_id: int,
    payload: ChecklistStartRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> ChecklistResponse:
    employee = await _employee(db, employee_id, actor.tenant_id)
    template = await _template(db, payload.template_id, actor.tenant_id)
    anchor = payload.anchor_date
    if anchor is None:
        anchor = (employee.hire_date if template.kind == ChecklistKind.ONBOARDING else employee.termination_date) or date.today()

    checklist = EmployeeChecklist(
        tenant_id=actor.tenant_id, employee_id=employee_id, kind=template.kind, name=template.name, anchor_date=anchor
    )
    db.add(checklist)
    await db.flush()
    items = (
        await db.execute(
            select(ChecklistTemplateItem).where(ChecklistTemplateItem.template_id == template.id).order_by(ChecklistTemplateItem.position)
        )
    ).scalars().all()
    for item in items:
        db.add(
            EmployeeChecklistItem(
                checklist_id=checklist.id,
                position=item.position,
                title=item.title,
                description=item.description,
                responsible=item.responsible,
                due_date=anchor + timedelta(days=item.due_offset_days),
            )
        )
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.CHECKLIST_STARTED,
        entity_type="employee",
        entity_id=employee_id,
        detail=f"{template.name} gestartet (Stichtag {anchor.isoformat()})",
    )
    await db.commit()
    return await _checklist_response(db, checklist)


@router.patch("/checklists/{checklist_id}/items/{item_id}", response_model=ChecklistItemResponse)
async def update_checklist_item(
    checklist_id: int,
    item_id: int,
    payload: ChecklistItemUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> ChecklistItemResponse:
    checklist = await db.get(EmployeeChecklist, checklist_id)
    item = await db.get(EmployeeChecklistItem, item_id)
    if checklist is None or checklist.tenant_id != actor.tenant_id or item is None or item.checklist_id != checklist_id:
        raise AppError(404, "CHECKLIST_ITEM_NOT_FOUND", "Aufgabe nicht gefunden.")
    if payload.done is not None and payload.done != item.done:
        item.done = payload.done
        item.done_at = datetime.now(UTC).replace(tzinfo=None) if payload.done else None
        item.done_by_hr_user_id = actor.audit_hr_user_id if payload.done else None
        item.done_by_employee_id = actor.audit_employee_id if payload.done else None
    if payload.note is not None:
        item.note = payload.note.strip() or None
    await db.commit()
    await db.refresh(item)
    return ChecklistItemResponse.model_validate(item)


@router.delete("/checklists/{checklist_id}", status_code=204)
async def delete_checklist(
    checklist_id: int, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> None:
    checklist = await db.get(EmployeeChecklist, checklist_id)
    if checklist is None or checklist.tenant_id != actor.tenant_id:
        raise AppError(404, "CHECKLIST_NOT_FOUND", "Checkliste nicht gefunden.")
    for item in (await db.execute(select(EmployeeChecklistItem).where(EmployeeChecklistItem.checklist_id == checklist_id))).scalars().all():
        await db.delete(item)
    await db.delete(checklist)
    await db.commit()


@router.get("/checklists/open-items", response_model=list[OpenChecklistItem])
async def open_items(
    actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[OpenChecklistItem]:
    """Alle offenen Aufgaben über alle Mitarbeiter, nach Fälligkeit sortiert."""
    rows = await db.execute(
        select(EmployeeChecklistItem, EmployeeChecklist, Employee)
        .join(EmployeeChecklist, EmployeeChecklist.id == EmployeeChecklistItem.checklist_id)
        .join(Employee, Employee.id == EmployeeChecklist.employee_id)
        .where(EmployeeChecklist.tenant_id == actor.tenant_id, EmployeeChecklistItem.done.is_(False))
        .order_by(EmployeeChecklistItem.due_date, Employee.last_name)
    )
    today = date.today()
    return [
        OpenChecklistItem(
            employee_id=employee.id,
            first_name=employee.first_name,
            last_name=employee.last_name,
            checklist_id=checklist.id,
            checklist_name=checklist.name,
            kind=checklist.kind,
            item_id=item.id,
            title=item.title,
            responsible=item.responsible,
            due_date=item.due_date,
            overdue=item.due_date < today,
        )
        for item, checklist, employee in rows.all()
    ]
