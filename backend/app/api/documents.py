from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Actor,
    get_current_actor,
    get_current_admin_principal,
    get_current_full_hr_principal,
    get_current_hr_or_self,
)
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, DocumentCategoryDefinition, Employee, EmployeeDocument, NotificationType, PeriodClosure
from app.models.document import DocumentCategory
from app.schemas.document import (
    DocumentCategoryRequest,
    DocumentCategoryResponse,
    DocumentCategoryUpdateRequest,
    DocumentResponse,
    DocumentUpdateRequest,
)
from app.services.notification_service import _notify_accounts, full_hr_recipients
from app.services.audit_service import log_action
from app.services.document_service import delete_document_file, read_document_bytes, store_document
from app.config import settings

router = APIRouter(tags=["documents"])


async def _employee_in_tenant(db: AsyncSession, employee_id: int, tenant_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    return employee


def _is_self(actor: Actor, employee_id: int) -> bool:
    """Die eigene Akte – auch für Mitarbeiter mit HR-/Supervisor-Rolle gelten dort die
    Mitarbeiter-Regeln (nur freigegebene Dokumente). Ausnahme: Administratoren."""
    return actor.employee is not None and actor.employee.id == employee_id and not actor.is_admin_level


def _check_read_scope(actor: Actor, employee_id: int) -> None:
    """Personalakte: Admin/HR (voll) und der Mitarbeiter selbst – Supervisor
    bewusst nicht (auch nicht für den eigenen Bereich), wohl aber für die eigene Akte."""
    if _is_self(actor, employee_id):
        return
    if actor.is_supervisor_level:
        raise AppError(403, "HR_PERMISSION_REQUIRED", "Keine Berechtigung für die Personalakte.")
    if not actor.is_hr_level:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")


def _visible_to(actor: Actor, document: EmployeeDocument) -> bool:
    if _is_self(actor, document.employee_id):
        return document.employee_visible and not document.confidential
    if document.confidential:
        return actor.is_admin_level
    return True


def _audit(db: AsyncSession, actor: Actor, action: AuditAction, document: EmployeeDocument, detail: str) -> None:
    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_account_id=actor.account_id,
        action=action,
        entity_type="employee",
        entity_id=document.employee_id,
        detail=detail,
    )


@router.get("/employees/{employee_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    employee_id: int,
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    await _employee_in_tenant(db, employee_id, actor.tenant_id)
    _check_read_scope(actor, employee_id)
    result = await db.execute(
        select(EmployeeDocument)
        .where(EmployeeDocument.employee_id == employee_id)
        .order_by(EmployeeDocument.created_at.desc(), EmployeeDocument.id.desc())
    )
    return [DocumentResponse.model_validate(d) for d in result.scalars().all() if _visible_to(actor, d)]


@router.post("/employees/{employee_id}/documents", response_model=DocumentResponse, status_code=201)
async def upload_document(
    employee_id: int,
    file: UploadFile = File(...),
    category: DocumentCategory = Form(...),
    title: str = Form(..., min_length=1, max_length=200),
    employee_visible: bool = Form(False),
    confidential: bool = Form(False),
    retention_until: date | None = Form(None),
    category_id: int | None = Form(None),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    await _employee_in_tenant(db, employee_id, actor.tenant_id)
    if category_id is not None:
        await _category(db, category_id, actor.tenant_id)
        category = DocumentCategory.OTHER
    if confidential and not actor.is_admin_level:
        raise AppError(403, "ADMIN_PERMISSION_REQUIRED", "Vertrauliche Dokumente dürfen nur Administratoren ablegen.")
    if confidential and employee_visible:
        raise AppError(400, "CONFIDENTIAL_NOT_VISIBLE", "Ein vertrauliches Dokument kann nicht für den Mitarbeiter sichtbar sein.")

    data = await file.read(settings.max_document_bytes + 1)
    document = await store_document(
        db,
        tenant_id=actor.tenant_id,
        employee_id=employee_id,
        data=data,
        filename=file.filename or "dokument",
        category=category,
        title=title,
        employee_visible=employee_visible,
        confidential=confidential,
        retention_until=retention_until,
        uploaded_by_account_id=actor.account_id,
    )
    document.category_id = category_id
    await db.flush()
    _audit(db, actor, AuditAction.DOCUMENT_UPLOADED, document, f"{document.category.value}: {document.title}")
    await db.commit()
    await db.refresh(document)
    return DocumentResponse.model_validate(document)


async def _get_document(db: AsyncSession, actor: Actor, employee_id: int, document_id: int) -> EmployeeDocument:
    await _employee_in_tenant(db, employee_id, actor.tenant_id)
    _check_read_scope(actor, employee_id)
    document = await db.get(EmployeeDocument, document_id)
    if document is None or document.employee_id != employee_id or not _visible_to(actor, document):
        raise AppError(404, "DOCUMENT_NOT_FOUND", "Dokument nicht gefunden.")
    return document


@router.get("/employees/{employee_id}/documents/{document_id}/download")
async def download_document(
    employee_id: int,
    document_id: int,
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> Response:
    document = await _get_document(db, actor, employee_id, document_id)
    data = await read_document_bytes(document.storage_key)
    if data is None:
        raise AppError(410, "DOCUMENT_FILE_MISSING", "Die Datei ist nicht mehr verfügbar.")
    if actor.is_hr_level:
        _audit(db, actor, AuditAction.DOCUMENT_ACCESSED, document, f"{document.category.value}: {document.title}")
        await db.commit()
    return Response(
        content=data,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.original_filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.patch("/employees/{employee_id}/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    employee_id: int,
    document_id: int,
    payload: DocumentUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    document = await _get_document(db, actor, employee_id, document_id)
    if payload.confidential is not None:
        if not actor.is_admin_level:
            raise AppError(403, "ADMIN_PERMISSION_REQUIRED", "Nur Administratoren dürfen die Vertraulichkeit ändern.")
        document.confidential = payload.confidential
    if payload.title is not None:
        document.title = payload.title
    if payload.category is not None:
        document.category = payload.category
        document.category_id = None
    if payload.category_id is not None:
        await _category(db, payload.category_id, actor.tenant_id)
        document.category = DocumentCategory.OTHER
        document.category_id = payload.category_id
    elif payload.clear_category_id:
        document.category_id = None
    if payload.employee_visible is not None:
        document.employee_visible = payload.employee_visible
    shortens = (payload.clear_retention_until and payload.retention_until is None and document.retention_until is not None) or (
        payload.retention_until is not None
        and document.retention_until is not None
        and payload.retention_until < document.retention_until
    )
    if shortens and not actor.is_admin_level:
        raise AppError(403, "ADMIN_PERMISSION_REQUIRED", "Aufbewahrungsfristen dürfen nur Administratoren verkürzen.")
    if payload.retention_until is not None:
        document.retention_until = payload.retention_until
    elif payload.clear_retention_until:
        document.retention_until = None
    if document.confidential and document.employee_visible:
        raise AppError(400, "CONFIDENTIAL_NOT_VISIBLE", "Ein vertrauliches Dokument kann nicht für den Mitarbeiter sichtbar sein.")

    _audit(db, actor, AuditAction.DOCUMENT_UPDATED, document, f"{document.category.value}: {document.title}")
    await db.commit()
    await db.refresh(document)
    return DocumentResponse.model_validate(document)


@router.delete("/employees/{employee_id}/documents/{document_id}", status_code=204)
async def delete_document(
    employee_id: int,
    document_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    document = await _get_document(db, actor, employee_id, document_id)
    referenced = (
        await db.execute(select(PeriodClosure.id).where(PeriodClosure.document_id == document.id).limit(1))
    ).first()
    if referenced is not None:
        raise AppError(
            409,
            "DOCUMENT_PART_OF_PERIOD_CLOSURE",
            "Das Dokument ist der Nachweis eines Monatsabschlusses und kann nicht gelöscht werden.",
        )
    if document.retention_until is not None and document.retention_until >= date.today():
        raise AppError(
            409,
            "DOCUMENT_UNDER_RETENTION",
            f"Das Dokument unterliegt bis {document.retention_until.isoformat()} der Aufbewahrungsfrist und kann nicht gelöscht werden.",
        )
    _audit(db, actor, AuditAction.DOCUMENT_DELETED, document, f"{document.category.value}: {document.title}")
    await delete_document_file(document.storage_key)
    await db.delete(document)
    await db.commit()


# --- Eigene Dokumentkategorien und Upload durch Mitarbeiter ---------------------------------------


async def _category(db: AsyncSession, category_id: int, tenant_id: int) -> DocumentCategoryDefinition:
    category = await db.get(DocumentCategoryDefinition, category_id)
    if category is None or category.tenant_id != tenant_id:
        raise AppError(404, "CATEGORY_NOT_FOUND", "Kategorie nicht gefunden.")
    return category


@router.get("/document-categories", response_model=list[DocumentCategoryResponse])
async def list_document_categories(
    actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)
) -> list[DocumentCategoryResponse]:
    """Admin/HR: alle; Mitarbeiter: die, in die sie selbst hochladen dürfen."""
    if actor.account is None or actor.tenant_id is None:
        raise AppError(403, "FORBIDDEN", "Nur für Konten einer Firma.")
    stmt = select(DocumentCategoryDefinition).where(DocumentCategoryDefinition.tenant_id == actor.tenant_id)
    if not actor.is_full_hr_level:
        stmt = stmt.where(DocumentCategoryDefinition.employee_upload.is_(True), DocumentCategoryDefinition.archived.is_(False))
    rows = (await db.execute(stmt.order_by(DocumentCategoryDefinition.name))).scalars().all()
    return [DocumentCategoryResponse.model_validate(r) for r in rows]


@router.post("/document-categories", response_model=DocumentCategoryResponse, status_code=201)
async def create_document_category(
    payload: DocumentCategoryRequest, actor: Actor = Depends(get_current_admin_principal), db: AsyncSession = Depends(get_db)
) -> DocumentCategoryResponse:
    if payload.confidential and (payload.employee_visible or payload.employee_upload):
        raise AppError(400, "CONFIDENTIAL_NOT_VISIBLE", "Vertrauliche Kategorien sind für Mitarbeiter weder sichtbar noch hochladbar.")
    category = DocumentCategoryDefinition(tenant_id=actor.tenant_id, archived=False, **payload.model_dump())
    db.add(category)
    await db.commit()
    return DocumentCategoryResponse.model_validate(category)


@router.patch("/document-categories/{category_id}", response_model=DocumentCategoryResponse)
async def update_document_category(
    category_id: int,
    payload: DocumentCategoryUpdateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> DocumentCategoryResponse:
    category = await _category(db, category_id, actor.tenant_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(category, key, value)
    if category.confidential and (category.employee_visible or category.employee_upload):
        raise AppError(400, "CONFIDENTIAL_NOT_VISIBLE", "Vertrauliche Kategorien sind für Mitarbeiter weder sichtbar noch hochladbar.")
    await db.commit()
    return DocumentCategoryResponse.model_validate(category)


@router.post("/me/documents", response_model=DocumentResponse, status_code=201)
async def upload_own_document(
    file: UploadFile = File(...),
    category_id: int = Form(...),
    title: str = Form(..., min_length=1, max_length=200),
    checklist_item_id: int | None = Form(None),
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Mitarbeiter lädt selbst ein Dokument in eine freigegebene Kategorie hoch (z. B. Bescheinigungen).
    Es ist für ihn sichtbar; Admin und HR werden benachrichtigt."""
    employee = actor.employee
    if employee is None:
        raise AppError(403, "FORBIDDEN", "Nur für Mitarbeiter mit eigenem Login.")
    category = await _category(db, category_id, actor.tenant_id)
    item = None
    if checklist_item_id is not None:
        # Onboarding-Aufgabe „Dokument hochladen“: genau in die vorgegebene Kategorie
        from app.api.checklists import own_open_item

        item = await own_open_item(db, actor, checklist_item_id)
        if item.action != "UPLOAD_DOCUMENT" or item.action_category_id != category.id:
            raise AppError(400, "WRONG_CATEGORY", "Diese Aufgabe verlangt ein Dokument in einer anderen Kategorie.")
    if item is None and (not category.employee_upload or category.archived):
        raise AppError(403, "UPLOAD_NOT_ALLOWED", "In diese Kategorie können Mitarbeiter nicht hochladen.")
    data = await file.read(settings.max_document_bytes + 1)
    document = await store_document(
        db, tenant_id=actor.tenant_id, employee_id=employee.id, data=data, filename=file.filename or "dokument",
        category=DocumentCategory.OTHER, title=title, employee_visible=True, confidential=False, retention_until=None,
        uploaded_by_account_id=actor.account_id,
    )
    document.category_id = category.id
    if item is not None:
        from app.api.checklists import mark_done

        mark_done(item, actor)
    await db.flush()
    _audit(db, actor, AuditAction.DOCUMENT_UPLOADED, document, f"{category.name}: {document.title} (selbst hochgeladen)")
    await _notify_accounts(
        db, actor.tenant_id, await full_hr_recipients(db, actor.tenant_id, exclude_employee_id=employee.id),
        NotificationType.DOCUMENT_UPLOADED,
        f"{employee.first_name} {employee.last_name} hat „{document.title}“ ({category.name}) hochgeladen.",
        "Dokument hochgeladen",
    )
    await db.commit()
    await db.refresh(document)
    return DocumentResponse.model_validate(document)
