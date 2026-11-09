"""Abteilungen (hierarchisch) und Organigramm.

Abteilungen pflegen Admin und HR; sehen dürfen sie alle mit Verwaltungsrolle. Das Organigramm baut
auf der Führungskraft je Mitarbeiter auf (Employee.supervisor_id) und zeigt Name, Position und
Abteilung der aktiven Mitarbeiter – für Verwaltungsrollen immer, für Mitarbeiter nur mit der
Einstellung „Organigramm für Mitarbeiter“.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, Department, Employee
from app.schemas.department import DepartmentCreateRequest, DepartmentResponse, DepartmentUpdateRequest, OrgChartPerson
from app.services.audit_service import log_action
from app.services.settings_service import get_or_create_settings

router = APIRouter(tags=["departments"])


async def _department(db: AsyncSession, department_id: int, tenant_id: int) -> Department:
    department = await db.get(Department, department_id)
    if department is None or department.tenant_id != tenant_id:
        raise AppError(404, "DEPARTMENT_NOT_FOUND", "Abteilung nicht gefunden.")
    return department


async def _check_parent(db: AsyncSession, department: Department | None, parent_id: int, tenant_id: int) -> None:
    """Übergeordnete Abteilung muss zur Firma gehören und darf nicht darunter liegen (kein Kreis)."""
    parent = await _department(db, parent_id, tenant_id)
    seen: set[int] = set()
    while parent is not None and parent.id not in seen:
        if department is not None and parent.id == department.id:
            raise AppError(400, "DEPARTMENT_CYCLE", "Eine Abteilung kann nicht unter sich selbst hängen.")
        seen.add(parent.id)
        parent = await db.get(Department, parent.parent_id) if parent.parent_id else None


def _audit(db: AsyncSession, actor: Actor, department: Department, detail: str) -> None:
    log_action(
        db, tenant_id=actor.tenant_id, actor_account_id=actor.account_id, action=AuditAction.DEPARTMENT_CHANGED,
        entity_type="department", entity_id=department.id, detail=detail,
    )


async def _responses(db: AsyncSession, tenant_id: int, departments: list[Department]) -> list[DepartmentResponse]:
    counts = dict(
        (
            await db.execute(
                select(Employee.department_id, func.count())
                .where(Employee.tenant_id == tenant_id, Employee.active.is_(True), Employee.department_id.is_not(None))
                .group_by(Employee.department_id)
            )
        ).all()
    )
    return [
        DepartmentResponse(id=d.id, name=d.name, parent_id=d.parent_id, employee_count=counts.get(d.id, 0))
        for d in departments
    ]


@router.get("/departments", response_model=list[DepartmentResponse])
async def list_departments(
    actor: Actor = Depends(get_current_hr_principal), db: AsyncSession = Depends(get_db)
) -> list[DepartmentResponse]:
    rows = (
        await db.execute(select(Department).where(Department.tenant_id == actor.tenant_id).order_by(Department.name))
    ).scalars().all()
    return await _responses(db, actor.tenant_id, list(rows))


@router.post("/departments", response_model=DepartmentResponse, status_code=201)
async def create_department(
    payload: DepartmentCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> DepartmentResponse:
    if payload.parent_id is not None:
        await _check_parent(db, None, payload.parent_id, actor.tenant_id)
    department = Department(tenant_id=actor.tenant_id, name=payload.name.strip(), parent_id=payload.parent_id)
    db.add(department)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "DEPARTMENT_NAME_TAKEN", "Diese Abteilung gibt es schon.") from exc
    _audit(db, actor, department, f"Abteilung „{department.name}“ angelegt")
    await db.commit()
    return (await _responses(db, actor.tenant_id, [department]))[0]


@router.patch("/departments/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: int,
    payload: DepartmentUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> DepartmentResponse:
    department = await _department(db, department_id, actor.tenant_id)
    if payload.parent_id is not None:
        await _check_parent(db, department, payload.parent_id, actor.tenant_id)
        department.parent_id = payload.parent_id
    elif payload.clear_parent_id:
        department.parent_id = None
    if payload.name is not None:
        department.name = payload.name.strip()
    _audit(db, actor, department, f"Abteilung „{department.name}“ geändert")
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "DEPARTMENT_NAME_TAKEN", "Diese Abteilung gibt es schon.") from exc
    return (await _responses(db, actor.tenant_id, [department]))[0]


@router.delete("/departments/{department_id}", status_code=204)
async def delete_department(
    department_id: int,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Nur leere Abteilungen (ohne Mitarbeiter, auch ehemalige, und ohne Unterabteilungen)."""
    department = await _department(db, department_id, actor.tenant_id)
    in_use = await db.scalar(select(func.count()).select_from(Employee).where(Employee.department_id == department.id))
    children = await db.scalar(select(func.count()).select_from(Department).where(Department.parent_id == department.id))
    if in_use or children:
        raise AppError(409, "DEPARTMENT_IN_USE", "Die Abteilung hat noch Mitarbeiter oder Unterabteilungen.")
    _audit(db, actor, department, f"Abteilung „{department.name}“ gelöscht")
    await db.delete(department)
    await db.commit()


@router.get("/org-chart", response_model=list[OrgChartPerson])
async def org_chart(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> list[OrgChartPerson]:
    if actor.account is None or actor.tenant_id is None:
        raise AppError(403, "FORBIDDEN", "Nur für Konten einer Firma.")
    if not actor.is_hr_level:
        if actor.employee is None or not (await get_or_create_settings(db, actor.tenant_id)).org_chart_for_employees:
            raise AppError(403, "ORG_CHART_DISABLED", "Das Organigramm ist für Mitarbeiter nicht freigeschaltet.")
    names = dict(
        (await db.execute(select(Department.id, Department.name).where(Department.tenant_id == actor.tenant_id))).all()
    )
    people = (
        await db.execute(
            select(Employee)
            .where(Employee.tenant_id == actor.tenant_id, Employee.active.is_(True))
            .order_by(Employee.last_name, Employee.first_name)
        )
    ).scalars().all()
    active_ids = {p.id for p in people}
    return [
        OrgChartPerson(
            employee_id=p.id,
            first_name=p.first_name,
            last_name=p.last_name,
            position=p.position,
            department_id=p.department_id,
            department=names.get(p.department_id) if p.department_id else None,
            supervisor_id=p.supervisor_id if p.supervisor_id in active_ids else None,
        )
        for p in people
    ]
