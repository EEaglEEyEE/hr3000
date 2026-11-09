from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal
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
        raise AppError(404, "CHECKLIST_TEMPLATE_NOT_FOUND", "Vorlage nicht gefunden.")
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


async def _check_item_categories(db: AsyncSession, items: list[TemplateItemInput], tenant_id: int) -> None:
    from app.models import DocumentCategoryDefinition

    for item in items:
        if item.action_category_id is not None:
            category = await db.get(DocumentCategoryDefinition, item.action_category_id)
            if category is None or category.tenant_id != tenant_id:
                raise AppError(404, "CATEGORY_NOT_FOUND", "Kategorie nicht gefunden.")


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
                action=item.action,
                action_category_id=item.action_category_id,
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
    await _check_item_categories(db, payload.items, actor.tenant_id)
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
        await _check_item_categories(db, payload.items, actor.tenant_id)
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
    created = []
    for item in items:
        row = EmployeeChecklistItem(
            checklist_id=checklist.id,
            position=item.position,
            title=item.title,
            description=item.description,
            responsible=item.responsible,
            due_date=anchor + timedelta(days=item.due_offset_days),
            action=item.action,
            action_category_id=item.action_category_id,
        )
        db.add(row)
        created.append(row)
    for row in created:
        if row.action == "SEND_EMAIL":
            await _send_email_step(db, actor, employee, row)
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
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
        item.done_by_account_id = actor.account_id if payload.done else None
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
        raise AppError(404, "CHECKLIST_NOT_FOUND", "On-/Offboarding nicht gefunden.")
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


# --- Aktionen: E-Mail beim Start, Aufgaben der Person selbst ---------------------------------------


async def _send_email_step(db: AsyncSession, actor: Actor, employee: Employee, item: EmployeeChecklistItem) -> None:
    """E-Mail-Schritt beim Start: Text (mit Platzhaltern) an die Zuständigen; ohne Mailversand bleibt er
    offen mit Hinweis."""
    from app.services import document_template_service, personal_data_service
    from app.services.email_service import resolve_smtp_config, send_email
    from app.services.notification_service import full_hr_recipients

    config = await resolve_smtp_config(db, actor.tenant_id)
    if item.responsible == ChecklistRole.EMPLOYEE:
        private = (await personal_data_service.load(db, employee.id)).get("private_email")
        recipients = [employee.login_email or private]
    elif item.responsible == ChecklistRole.SUPERVISOR:
        supervisor = await db.get(Employee, employee.supervisor_id) if employee.supervisor_id else None
        recipients = [supervisor.login_email if supervisor else None]
    else:
        recipients = [email for _, email in await full_hr_recipients(db, actor.tenant_id)]
    recipients = [r for r in recipients if r]
    if config is None or not recipients:
        item.note = "Nicht verschickt: kein Mailversand eingerichtet." if config is None else "Nicht verschickt: keine E-Mail-Adresse."
        return
    text, _ = document_template_service.fill(item.description or "", await document_template_service.values(db, employee))
    for recipient in recipients:
        await send_email(recipient, item.title, text, config=config)
    item.done = True
    item.done_at = datetime.now(UTC).replace(tzinfo=None)
    item.done_by_account_id = actor.account_id
    item.note = "Verschickt an " + ", ".join(recipients)


@router.get("/me/checklist-items", response_model=list[ChecklistItemResponse])
async def my_checklist_items(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> list[ChecklistItemResponse]:
    """Offene Aufgaben, für die die Person selbst zuständig ist (On-/Offboarding)."""
    if actor.employee is None:
        raise AppError(403, "FORBIDDEN", "Nur für Mitarbeiter mit eigenem Login.")
    rows = (
        await db.execute(
            select(EmployeeChecklistItem)
            .join(EmployeeChecklist, EmployeeChecklist.id == EmployeeChecklistItem.checklist_id)
            .where(
                EmployeeChecklist.employee_id == actor.employee.id,
                EmployeeChecklistItem.responsible == ChecklistRole.EMPLOYEE,
                EmployeeChecklistItem.done.is_(False),
            )
            .order_by(EmployeeChecklistItem.due_date, EmployeeChecklistItem.position)
        )
    ).scalars().all()
    return [ChecklistItemResponse.model_validate(r) for r in rows]


async def own_open_item(db: AsyncSession, actor: Actor, item_id: int) -> EmployeeChecklistItem:
    """Offene Aufgabe der angemeldeten Person (zuständig: Mitarbeiter) – sonst 404."""
    item = await db.get(EmployeeChecklistItem, item_id)
    checklist = await db.get(EmployeeChecklist, item.checklist_id) if item else None
    if (
        item is None or checklist is None or actor.employee is None or checklist.employee_id != actor.employee.id
        or item.responsible != ChecklistRole.EMPLOYEE or item.done
    ):
        raise AppError(404, "CHECKLIST_ITEM_NOT_FOUND", "Aufgabe nicht gefunden.")
    return item


def mark_done(item: EmployeeChecklistItem, actor: Actor) -> None:
    item.done = True
    item.done_at = datetime.now(UTC).replace(tzinfo=None)
    item.done_by_account_id = actor.account_id


@router.post("/me/checklist-items/{item_id}/done", response_model=ChecklistItemResponse)
async def complete_my_item(item_id: int, actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> ChecklistItemResponse:
    """Aufgabe abhaken bzw. nach dem Datenvorschlag erledigen. Hochladen erledigt POST /me/documents."""
    item = await own_open_item(db, actor, item_id)
    if item.action == "UPLOAD_DOCUMENT":
        raise AppError(400, "UPLOAD_REQUIRED", "Diese Aufgabe ist mit dem Hochladen erledigt.")
    mark_done(item, actor)
    await db.commit()
    return ChecklistItemResponse.model_validate(item)
