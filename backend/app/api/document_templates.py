"""Dokumentvorlagen (Admins pflegen, Admin/HR erzeugen) – PDF mit Platzhaltern in die Personalakte."""
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal, get_current_full_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, DocumentCategoryDefinition, DocumentTemplate, Employee
from app.models.document import DocumentCategory
from app.schemas.document import DocumentResponse
from app.services import document_template_service
from app.services.audit_service import log_action
from app.services.document_service import store_document

router = APIRouter(tags=["document_templates"])


class DocumentTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=20000)
    category: DocumentCategory = DocumentCategory.OTHER
    category_id: int | None = None
    employee_visible: bool = False


class DocumentTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    category: DocumentCategory | None = None
    category_id: int | None = None
    clear_category_id: bool = False
    employee_visible: bool | None = None
    archived: bool | None = None


class DocumentTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    body: str
    category: DocumentCategory
    category_id: int | None
    employee_visible: bool
    archived: bool


class Placeholder(BaseModel):
    key: str
    label: str


class GenerateRequest(BaseModel):
    template_id: int
    title: str | None = Field(default=None, max_length=200)


async def _template(db: AsyncSession, template_id: int, tenant_id: int) -> DocumentTemplate:
    template = await db.get(DocumentTemplate, template_id)
    if template is None or template.tenant_id != tenant_id:
        raise AppError(404, "TEMPLATE_NOT_FOUND", "Vorlage nicht gefunden.")
    return template


async def _check_category(db: AsyncSession, category_id: int | None, tenant_id: int) -> None:
    if category_id is None:
        return
    category = await db.get(DocumentCategoryDefinition, category_id)
    if category is None or category.tenant_id != tenant_id:
        raise AppError(404, "CATEGORY_NOT_FOUND", "Kategorie nicht gefunden.")


@router.get("/document-templates/placeholders", response_model=list[Placeholder])
async def list_placeholders(_: Actor = Depends(get_current_full_hr_principal)) -> list[Placeholder]:
    return [Placeholder(key=k, label=v) for k, v in document_template_service.PLACEHOLDERS.items()]


@router.get("/document-templates", response_model=list[DocumentTemplateResponse])
async def list_templates(actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)) -> list[DocumentTemplateResponse]:
    rows = (
        await db.execute(select(DocumentTemplate).where(DocumentTemplate.tenant_id == actor.tenant_id).order_by(DocumentTemplate.name))
    ).scalars().all()
    return [DocumentTemplateResponse.model_validate(r) for r in rows]


@router.post("/document-templates", response_model=DocumentTemplateResponse, status_code=201)
async def create_template(
    payload: DocumentTemplateRequest, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> DocumentTemplateResponse:
    await _check_category(db, payload.category_id, actor.tenant_id)
    template = DocumentTemplate(tenant_id=actor.tenant_id, archived=False, **payload.model_dump())
    if template.category_id is not None:
        template.category = DocumentCategory.OTHER
    db.add(template)
    await db.commit()
    return DocumentTemplateResponse.model_validate(template)


@router.patch("/document-templates/{template_id}", response_model=DocumentTemplateResponse)
async def update_template(
    template_id: int,
    payload: DocumentTemplateUpdateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> DocumentTemplateResponse:
    template = await _template(db, template_id, actor.tenant_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.pop("clear_category_id", False):
        template.category_id = None
    await _check_category(db, changes.get("category_id"), actor.tenant_id)
    for key, value in changes.items():
        if value is not None:
            setattr(template, key, value)
    if template.category_id is not None:
        template.category = DocumentCategory.OTHER
    await db.commit()
    return DocumentTemplateResponse.model_validate(template)


async def _employee(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


@router.get("/employees/{employee_id}/document-templates/{template_id}/preview")
async def preview(
    employee_id: int, template_id: int, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> Response:
    """Vorschau als PDF, ohne es abzulegen."""
    employee = await _employee(db, employee_id, actor.tenant_id)
    template = await _template(db, template_id, actor.tenant_id)
    pdf, _ = await document_template_service.render_pdf(db, employee, template.body)
    filename = f"{template.name}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}", "Cache-Control": "no-store"},
    )


@router.post("/employees/{employee_id}/documents/from-template", response_model=DocumentResponse, status_code=201)
async def generate_document(
    employee_id: int, payload: GenerateRequest, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> DocumentResponse:
    """Vorlage für den Mitarbeiter füllen und als PDF in die Personalakte legen. Unbekannte Platzhalter
    brechen ab, damit kein halbfertiges Dokument entsteht."""
    employee = await _employee(db, employee_id, actor.tenant_id)
    template = await _template(db, payload.template_id, actor.tenant_id)
    if template.archived:
        raise AppError(400, "TEMPLATE_ARCHIVED", "Die Vorlage ist archiviert.")
    pdf, unknown = await document_template_service.render_pdf(db, employee, template.body)
    if unknown:
        raise AppError(400, "UNKNOWN_PLACEHOLDER", "Unbekannte Platzhalter: " + ", ".join(sorted(set(unknown))))
    title = (payload.title or "").strip() or f"{template.name} {date.today():%d.%m.%Y}"
    document = await store_document(
        db, tenant_id=actor.tenant_id, employee_id=employee.id, data=pdf, filename=f"{template.name}.pdf",
        category=template.category, title=title, employee_visible=template.employee_visible, confidential=False,
        retention_until=None, uploaded_by_account_id=actor.account_id,
    )
    document.category_id = template.category_id
    await db.flush()
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.DOCUMENT_UPLOADED,
        entity_type="employee", entity_id=employee.id, detail=f"Aus Vorlage „{template.name}“: {title}",
    )
    await db.commit()
    await db.refresh(document)
    return DocumentResponse.model_validate(document)
