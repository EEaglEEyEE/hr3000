"""Abteilungen (hierarchisch) und Organigramm.

Abteilungen pflegen Admin und HR (auch direkt im Organigramm); sehen dürfen sie alle mit
Verwaltungsrolle. Jede Abteilung kann mehrere Leitungen und Stellvertretungen haben – die Leitungen
sind die Führungskräfte der Mitarbeiter darin, Stellvertretungen handeln je nach ihren Rechten
(app/services/org_service.py, scope_service.py). Das Organigramm ist der Abteilungsbaum mit Leitungen
und aktiven Mitarbeitern – für Verwaltungsrollen immer, für Mitarbeiter nur mit der Einstellung
„Organigramm für Mitarbeiter“.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_current_full_hr_principal, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, Department, DepartmentLeader, Employee
from app.models.department import DEPUTY_STANDBY, LEADER_DEPUTY, LEADER_HEAD
from app.schemas.department import (
    DepartmentCreateRequest,
    DepartmentLeaderInput,
    DepartmentLeaderResponse,
    DepartmentMembersRequest,
    DepartmentMembersResponse,
    DepartmentResponse,
    DepartmentUpdateRequest,
    OrgChartDepartment,
    OrgChartLeader,
    OrgChartPerson,
    OrgChartResponse,
)
from app.services import webhook_service
from app.services.audit_service import log_action
from app.services.org_service import check_no_supervisor_cycle, load_org
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


RIGHTS_LABELS = {"STANDBY": "entscheidet bei Abwesenheit", "FULL": "gleiche Rechte", "ABSENCE": "nur bei Abwesenheit"}


async def _set_leaders(
    db: AsyncSession, department: Department, leaders: list[DepartmentLeaderInput], tenant_id: int
) -> str:
    """Ersetzt Leitungen und Stellvertretungen der Abteilung; gibt den Text fürs Protokoll zurück."""
    ids = [leader.employee_id for leader in leaders]
    people = (
        {
            e.id: e
            for e in (await db.execute(select(Employee).where(Employee.id.in_(ids), Employee.tenant_id == tenant_id))).scalars()
        }
        if ids
        else {}
    )
    missing = [i for i in ids if i not in people]
    if missing:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Leitung oder Stellvertretung nicht gefunden (eine Person der Firma wählen).")
    for row in (await db.execute(select(DepartmentLeader).where(DepartmentLeader.department_id == department.id))).scalars():
        await db.delete(row)
    await db.flush()
    for position, leader in enumerate(leaders):
        db.add(
            DepartmentLeader(
                department_id=department.id,
                employee_id=leader.employee_id,
                role=leader.role,
                deputy_rights=leader.deputy_rights if leader.role == LEADER_DEPUTY else DEPUTY_STANDBY,
                position=position,
            )
        )
    await db.flush()

    def name(employee_id: int) -> str:
        return f"{people[employee_id].first_name} {people[employee_id].last_name}"

    heads = [name(l.employee_id) for l in leaders if l.role == LEADER_HEAD]
    deputies = [f"{name(l.employee_id)} ({RIGHTS_LABELS[l.deputy_rights]})" for l in leaders if l.role == LEADER_DEPUTY]
    parts = [f"Leitung {', '.join(heads)}" if heads else "ohne Leitung"]
    if deputies:
        parts.append(f"Stellvertretung {', '.join(deputies)}")
    return ", " + "; ".join(parts)


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
    leaders: dict[int, list[DepartmentLeaderResponse]] = {}
    ids = [d.id for d in departments]
    if ids:
        rows = (
            await db.execute(
                select(DepartmentLeader, Employee)
                .join(Employee, Employee.id == DepartmentLeader.employee_id)
                .where(DepartmentLeader.department_id.in_(ids))
                .order_by(DepartmentLeader.department_id, DepartmentLeader.position, DepartmentLeader.id)
            )
        ).all()
        for leader, person in rows:
            leaders.setdefault(leader.department_id, []).append(
                DepartmentLeaderResponse(
                    employee_id=person.id,
                    name=f"{person.first_name} {person.last_name}",
                    role=leader.role,
                    deputy_rights=leader.deputy_rights,
                    active=bool(person.active),
                )
            )
    return [
        DepartmentResponse(
            id=d.id, name=d.name, parent_id=d.parent_id, leaders=leaders.get(d.id, []), employee_count=counts.get(d.id, 0)
        )
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
    leading = ""
    if payload.leaders:
        try:
            leading = await _set_leaders(db, department, payload.leaders, actor.tenant_id)
            await check_no_supervisor_cycle(db, actor.tenant_id)
        except AppError:
            await db.rollback()
            raise
    _audit(db, actor, department, f"Abteilung „{department.name}“ angelegt{leading}")
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
    head_note = ""
    try:
        if payload.leaders is not None:
            head_note = await _set_leaders(db, department, payload.leaders, actor.tenant_id)
        if payload.leaders is not None or payload.parent_id is not None or payload.clear_parent_id:
            await db.flush()
            await check_no_supervisor_cycle(db, actor.tenant_id)
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "DEPARTMENT_NAME_TAKEN", "Diese Abteilung gibt es schon.") from exc
    except AppError:
        await db.rollback()
        raise
    _audit(db, actor, department, f"Abteilung „{department.name}“ geändert{head_note}")
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "DEPARTMENT_NAME_TAKEN", "Diese Abteilung gibt es schon.") from exc
    return (await _responses(db, actor.tenant_id, [department]))[0]


AUDIT_DETAIL_MAX = 500  # Länge von audit_log.detail


def _members_note(department: Department, moved: list[tuple[Employee, str | None]]) -> str:
    """Protokolltext: wer aus welcher Abteilung kam – zu lang für die Spalte wird gekürzt."""
    people = ", ".join(
        f"{e.first_name} {e.last_name} (bisher {f'„{before}“' if before else 'ohne Abteilung'})" for e, before in moved
    )
    text = f"{len(moved)} Mitarbeiter in Abteilung „{department.name}“ aufgenommen: {people}"
    return text if len(text) <= AUDIT_DETAIL_MAX else text[: AUDIT_DETAIL_MAX - 1] + "…"


@router.post("/departments/{department_id}/members", response_model=DepartmentMembersResponse)
async def add_department_members(
    department_id: int,
    payload: DepartmentMembersRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> DepartmentMembersResponse:
    """Mehrere Mitarbeiter auf einmal in die Abteilung aufnehmen (Organigramm „Mitarbeiter hinzufügen“).
    Alles oder nichts: Fehlt eine Person, ist sie anonymisiert oder entstünde ein Kreis in den
    Führungskräften, ändert sich keiner."""
    department = await _department(db, department_id, actor.tenant_id)
    people = {
        e.id: e
        for e in (
            await db.execute(
                select(Employee).where(Employee.id.in_(payload.employee_ids), Employee.tenant_id == actor.tenant_id)
            )
        ).scalars()
    }
    if any(i not in people for i in payload.employee_ids):
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if any(people[i].anonymized_at is not None for i in payload.employee_ids):
        raise AppError(400, "ALREADY_ANONYMIZED", "Anonymisierte Mitarbeiter können nicht mehr bearbeitet werden.")
    names = dict(
        (await db.execute(select(Department.id, Department.name).where(Department.tenant_id == actor.tenant_id))).all()
    )
    moved: list[tuple[Employee, str | None]] = []
    for employee_id in payload.employee_ids:
        employee = people[employee_id]
        if employee.department_id == department.id:
            continue
        moved.append((employee, names.get(employee.department_id) if employee.department_id else None))
        employee.department_id = department.id
    if moved:
        await db.flush()
        try:
            await check_no_supervisor_cycle(db, actor.tenant_id)
        except AppError:
            await db.rollback()
            raise
        for employee, _ in moved:
            await webhook_service.emit_event(db, actor.tenant_id, "employee.updated", {"employee_id": employee.id})
        _audit(db, actor, department, _members_note(department, moved))
        await db.commit()
    return DepartmentMembersResponse(department=(await _responses(db, actor.tenant_id, [department]))[0], added=len(moved))


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
    for row in (await db.execute(select(DepartmentLeader).where(DepartmentLeader.department_id == department.id))).scalars():
        await db.delete(row)
    await db.delete(department)
    await db.commit()


@router.get("/org-chart", response_model=OrgChartResponse)
async def org_chart(actor: Actor = Depends(get_current_actor), db: AsyncSession = Depends(get_db)) -> OrgChartResponse:
    if actor.account is None or actor.tenant_id is None:
        raise AppError(403, "FORBIDDEN", "Nur für Konten einer Firma.")
    if not actor.is_hr_level:
        if actor.employee is None or not (await get_or_create_settings(db, actor.tenant_id)).org_chart_for_employees:
            raise AppError(403, "ORG_CHART_DISABLED", "Das Organigramm ist für Mitarbeiter nicht freigeschaltet.")
    departments = (
        await db.execute(select(Department).where(Department.tenant_id == actor.tenant_id).order_by(Department.name))
    ).scalars().all()
    names = {d.id: d.name for d in departments}
    people = (
        await db.execute(
            select(Employee)
            .where(Employee.tenant_id == actor.tenant_id, Employee.active.is_(True))
            .order_by(Employee.last_name, Employee.first_name)
        )
    ).scalars().all()
    active_ids = {p.id for p in people}
    org = await load_org(db, actor.tenant_id)
    return OrgChartResponse(
        departments=[
            OrgChartDepartment(
                id=d.id,
                name=d.name,
                parent_id=d.parent_id,
                leaders=[
                    OrgChartLeader(employee_id=e, role=role, deputy_rights=rights)
                    for e, role, rights in org.leaders.get(d.id, [])
                    if e in active_ids
                ],
            )
            for d in departments
        ],
        people=[
            OrgChartPerson(
                employee_id=p.id,
                first_name=p.first_name,
                last_name=p.last_name,
                position=p.position,
                department_id=p.department_id,
                department=names.get(p.department_id) if p.department_id else None,
                supervisor_ids=[s for s in org.supervisors(p.id) if s in active_ids],
            )
            for p in people
        ],
    )
