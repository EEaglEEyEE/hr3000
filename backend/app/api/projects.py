"""Projektzeiterfassung: Kunden und Projekte (Einstellungen, Admin/HR, Bereich „Stammdaten der Firma“)
und die feste Auswertung „Projektzeiten“ (Analysen; Führungskräfte nur ihr Bereich)."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, CostCenter, Customer, Project
from app.schemas.project import (
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectTimeRow,
    ProjectTimesResponse,
    ProjectUpdate,
)
from app.services import project_service
from app.services.audit_service import log_action
from app.services.scope_service import visible_employee_ids
from app.services.settings_service import get_or_create_settings

router = APIRouter(tags=["projects"])

_MAX_RANGE_DAYS = 366


def _audit(db: AsyncSession, actor: Actor, entity_type: str, entity_id: int, detail: str) -> None:
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.PROJECT_CHANGED,
        entity_type=entity_type, entity_id=entity_id, detail=detail,
    )


# --- Kunden ----------------------------------------------------------------------------------------


async def _customer(db: AsyncSession, customer_id: int, tenant_id: int) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        raise AppError(404, "CUSTOMER_NOT_FOUND", "Kunde nicht gefunden.")
    return customer


async def _project_counts(db: AsyncSession, tenant_id: int) -> dict[int, int]:
    rows = await db.execute(
        select(Project.customer_id, func.count(Project.id))
        .where(Project.tenant_id == tenant_id, Project.customer_id.is_not(None))
        .group_by(Project.customer_id)
    )
    return {customer_id: count for customer_id, count in rows.all()}


@router.get("/customers", response_model=list[CustomerResponse])
async def list_customers(actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)) -> list[CustomerResponse]:
    counts = await _project_counts(db, actor.tenant_id)
    rows = (await db.execute(select(Customer).where(Customer.tenant_id == actor.tenant_id).order_by(Customer.name))).scalars()
    return [CustomerResponse(id=c.id, name=c.name, active=c.active, project_count=counts.get(c.id, 0)) for c in rows]


@router.post("/customers", response_model=CustomerResponse, status_code=201)
async def create_customer(
    payload: CustomerCreate, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> CustomerResponse:
    customer = Customer(tenant_id=actor.tenant_id, name=payload.name, active=payload.active)
    db.add(customer)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "CUSTOMER_NAME_TAKEN", "Diesen Kunden gibt es schon.") from exc
    _audit(db, actor, "customer", customer.id, f"Kunde angelegt: {customer.name}")
    await db.commit()
    return CustomerResponse(id=customer.id, name=customer.name, active=customer.active)


@router.patch("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    customer = await _customer(db, customer_id, actor.tenant_id)
    if payload.name is not None:
        customer.name = payload.name
    if payload.active is not None:
        customer.active = payload.active
    _audit(db, actor, "customer", customer.id, f"Kunde geändert: {customer.name}{'' if customer.active else ' (inaktiv)'}")
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "CUSTOMER_NAME_TAKEN", "Diesen Kunden gibt es schon.") from exc
    counts = await _project_counts(db, actor.tenant_id)
    return CustomerResponse(id=customer.id, name=customer.name, active=customer.active, project_count=counts.get(customer.id, 0))


@router.delete("/customers/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: int, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> None:
    """Nur ohne Projekte; sonst deaktivieren (409)."""
    customer = await _customer(db, customer_id, actor.tenant_id)
    if (await _project_counts(db, actor.tenant_id)).get(customer.id):
        raise AppError(409, "CUSTOMER_IN_USE", "Der Kunde hat Projekte – bitte deaktivieren statt löschen.")
    _audit(db, actor, "customer", customer.id, f"Kunde gelöscht: {customer.name}")
    await db.delete(customer)
    await db.commit()


# --- Projekte --------------------------------------------------------------------------------------


async def _project(db: AsyncSession, project_id: int, tenant_id: int) -> Project:
    project = await db.get(Project, project_id)
    if project is None or project.tenant_id != tenant_id:
        raise AppError(404, "PROJECT_NOT_FOUND", "Projekt nicht gefunden.")
    return project


async def _check_refs(db: AsyncSession, tenant_id: int, customer_id: int | None, cost_center_id: int | None) -> None:
    if customer_id is not None:
        await _customer(db, customer_id, tenant_id)
    if cost_center_id is not None:
        cost_center = await db.get(CostCenter, cost_center_id)
        if cost_center is None or cost_center.tenant_id != tenant_id:
            raise AppError(404, "COST_CENTER_NOT_FOUND", "Kostenstelle nicht gefunden.")


async def _response(db: AsyncSession, project: Project) -> ProjectResponse:
    customer = await db.get(Customer, project.customer_id) if project.customer_id else None
    cost_center = await db.get(CostCenter, project.cost_center_id) if project.cost_center_id else None
    return ProjectResponse(
        id=project.id,
        name=project.name,
        number=project.number,
        customer_id=project.customer_id,
        customer_name=customer.name if customer else None,
        cost_center_id=project.cost_center_id,
        cost_center_label=f"{cost_center.code} {cost_center.name}" if cost_center else None,
        billable=project.billable,
        active=project.active,
        valid_from=project.valid_from,
        valid_to=project.valid_to,
        in_use=await project_service.project_in_use(db, project.id),
    )


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)) -> list[ProjectResponse]:
    rows = (await db.execute(select(Project).where(Project.tenant_id == actor.tenant_id))).scalars().all()
    return [await _response(db, project) for project in sorted(rows, key=project_service.sort_key)]


def _taken(exc: IntegrityError) -> AppError:
    return AppError(409, "PROJECT_NUMBER_TAKEN", "Diese Projektnummer gibt es schon.")


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    payload: ProjectCreate, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> ProjectResponse:
    await _check_refs(db, actor.tenant_id, payload.customer_id, payload.cost_center_id)
    project = Project(tenant_id=actor.tenant_id, **payload.model_dump())
    db.add(project)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _taken(exc) from exc
    _audit(db, actor, "project", project.id, f"Projekt angelegt: {project_service.project_label(project)}")
    await db.commit()
    return await _response(db, project)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    payload: ProjectUpdate,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    project = await _project(db, project_id, actor.tenant_id)
    changes = {key: getattr(payload, key) for key in payload.model_fields_set}
    for key in ("name", "billable", "active"):
        if key in changes and changes[key] is None:
            raise AppError(422, "PROJECT_INVALID", "Name, abrechenbar und aktiv lassen sich nicht leeren.")
    await _check_refs(db, actor.tenant_id, changes.get("customer_id"), changes.get("cost_center_id"))
    valid_from = changes.get("valid_from", project.valid_from)
    valid_to = changes.get("valid_to", project.valid_to)
    if valid_from is not None and valid_to is not None and valid_from > valid_to:
        raise AppError(422, "PROJECT_INVALID", "„Gültig von“ muss vor „Gültig bis“ liegen.")
    for key, value in changes.items():
        setattr(project, key, value)
    _audit(db, actor, "project", project.id, f"Projekt geändert: {project_service.project_label(project)} ({', '.join(sorted(changes)) or '-'})")
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _taken(exc) from exc
    return await _response(db, project)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: int, actor: Actor = Depends(get_current_full_hr_principal), db: AsyncSession = Depends(get_db)
) -> None:
    """Nur ohne zugeordnete Zeiten; sonst deaktivieren (409)."""
    project = await _project(db, project_id, actor.tenant_id)
    if await project_service.project_in_use(db, project.id):
        raise AppError(409, "PROJECT_IN_USE", "Dem Projekt sind schon Zeiten zugeordnet – bitte deaktivieren statt löschen.")
    _audit(db, actor, "project", project.id, f"Projekt gelöscht: {project_service.project_label(project)}")
    await db.delete(project)
    await db.commit()


# --- Auswertung ------------------------------------------------------------------------------------


@router.get("/reports/project-times", response_model=ProjectTimesResponse)
async def report_project_times(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    employee_id: int | None = Query(default=None, ge=1),
    project_id: int | None = Query(default=None, ge=1),
    customer_id: int | None = Query(default=None, ge=1),
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> ProjectTimesResponse:
    """Projektzeiten je Mitarbeiter und Projekt im Zeitraum (höchstens 366 Tage). Führungskräfte sehen
    nur ihren Bereich."""
    if not (await get_or_create_settings(db, actor.tenant_id)).project_times_enabled:
        raise AppError(403, "PROJECT_TIMES_DISABLED", "Projektzeiten sind nicht eingeschaltet.")
    if date_to < date_from or (date_to - date_from).days >= _MAX_RANGE_DAYS:
        raise AppError(400, "INVALID_RANGE", "Bitte einen Zeitraum von höchstens 366 Tagen wählen.")
    rows = await project_service.project_times(
        db, actor.tenant_id, date_from, date_to,
        visible=await visible_employee_ids(db, actor),
        employee_id=employee_id, project_id=project_id, customer_id=customer_id,
    )
    result = [
        ProjectTimeRow(
            employee_id=r.employee.id,
            first_name=r.employee.first_name,
            last_name=r.employee.last_name,
            employee_number=r.employee.employee_number,
            project_id=r.project.id,
            project_name=r.project.name,
            project_number=r.project.number,
            customer_id=r.customer.id if r.customer else None,
            customer_name=r.customer.name if r.customer else None,
            cost_center=f"{r.cost_center.code} {r.cost_center.name}" if r.cost_center else None,
            billable=r.project.billable,
            minutes=r.minutes,
        )
        for r in rows
    ]
    billable = sum(r.minutes for r in result if r.billable)
    total = sum(r.minutes for r in result)
    return ProjectTimesResponse(
        date_from=date_from, date_to=date_to, rows=result,
        total_minutes=total, billable_minutes=billable, non_billable_minutes=total - billable,
    )
