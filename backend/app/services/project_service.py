"""Projektzeiterfassung (Einstellung „Projektzeiten“): Projekte prüfen und Projektzeiten auswerten.

Ein Projekt hängt am „Kommen“ einer Spanne (Punch.project_id) und gilt bis zum nächsten „Gehen“.
Projektzeit einer Spanne = Gehen − Kommen − Pausen darin (gestempelte, eingetragene und automatische
Pausen). Die gesetzliche Mindestpause, die die Tagesberechnung ggf. zusätzlich abzieht, wird nicht
auf Projekte verteilt – die Summe der Projektzeiten kann deshalb über der Ist-Zeit liegen.
Offene Spannen (Kommen ohne Gehen) zählen nicht. Keine Rundung: Minuten werden erst je Zeile auf
ganze Minuten gebracht.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import CostCenter, Customer, Employee, Punch, PunchType, Project
from app.services import timesheet_service as ts


def project_label(project: Project, customer_name: str | None = None) -> str:
    label = f"{project.number} {project.name}" if project.number else project.name
    return f"{label} ({customer_name})" if customer_name else label


def valid_on(project: Project, day: date) -> bool:
    return (project.valid_from is None or project.valid_from <= day) and (project.valid_to is None or day <= project.valid_to)


async def selectable_projects(db: AsyncSession, tenant_id: int) -> list[tuple[Project, str | None]]:
    """Aktive Projekte, deren Kunde (falls vorhanden) aktiv ist – mit Kundennamen."""
    rows = await db.execute(
        select(Project, Customer.name)
        .outerjoin(Customer, Customer.id == Project.customer_id)
        .where(Project.tenant_id == tenant_id, Project.active.is_(True))
        .where((Project.customer_id.is_(None)) | (Customer.active.is_(True)))
    )
    return sorted(((project, customer) for project, customer in rows.all()), key=lambda row: sort_key(row[0]))


def sort_key(project: Project) -> tuple:
    """Projekte mit Nummer zuerst (nach Nummer), dann nach Name."""
    return (project.number is None, project.number or "", project.name.lower(), project.id)


async def ensure_project_usable(db: AsyncSession, tenant_id: int, project_id: int, day: date) -> Project:
    """Für das Eintragen: Projekt der Firma, aktiv, Kunde aktiv und am Tag gültig – sonst 422."""
    project = await db.get(Project, project_id)
    if project is None or project.tenant_id != tenant_id:
        raise AppError(422, "PROJECT_INVALID", "Dieses Projekt gibt es nicht.")
    customer = await db.get(Customer, project.customer_id) if project.customer_id is not None else None
    if not project.active or (customer is not None and not customer.active):
        raise AppError(422, "PROJECT_INVALID", f"Das Projekt „{project.name}“ ist nicht mehr aktiv.")
    if not valid_on(project, day):
        raise AppError(422, "PROJECT_INVALID", f"Auf das Projekt „{project.name}“ lässt sich an diesem Tag nicht buchen.")
    return project


async def existing_project_ids(db: AsyncSession, tenant_id: int, ids: set[int]) -> set[int]:
    if not ids:
        return set()
    rows = await db.execute(select(Project.id).where(Project.tenant_id == tenant_id, Project.id.in_(ids)))
    return set(rows.scalars().all())


async def project_names(db: AsyncSession, tenant_id: int, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = await db.execute(
        select(Project, Customer.name)
        .outerjoin(Customer, Customer.id == Project.customer_id)
        .where(Project.tenant_id == tenant_id, Project.id.in_(ids))
    )
    return {project.id: project_label(project, customer) for project, customer in rows.all()}


def project_seconds(day_punches: list[Punch]) -> dict[int, float]:
    """Sekunden je Projekt aus den Stempelungen eines Arbeitstags (in Tagesreihenfolge)."""
    result: dict[int, float] = defaultdict(float)
    start: datetime | None = None
    project_id: int | None = None
    break_start: datetime | None = None
    breaks = 0.0
    for punch in day_punches:
        moment = ts._naive_utc(punch.timestamp_utc)
        if punch.punch_type == PunchType.COME:
            start, project_id, break_start, breaks = moment, punch.project_id, None, 0.0
        elif start is None:
            continue
        elif punch.punch_type == PunchType.BREAK_START:
            break_start = moment
        elif punch.punch_type == PunchType.BREAK_END and break_start is not None:
            breaks += (moment - break_start).total_seconds()
            break_start = None
        elif punch.punch_type == PunchType.GO:
            if project_id is not None:
                result[project_id] += max((moment - start).total_seconds() - breaks, 0.0)
            start, project_id = None, None
    return dict(result)


@dataclass
class ProjectTime:
    employee: Employee
    project: Project
    customer: Customer | None
    cost_center: CostCenter | None
    minutes: int


async def project_times(
    db: AsyncSession,
    tenant_id: int,
    first: date,
    last: date,
    *,
    visible: set[int] | None = None,
    employee_id: int | None = None,
    project_id: int | None = None,
    customer_id: int | None = None,
) -> list[ProjectTime]:
    """Projektzeiten je Mitarbeiter und Projekt im Zeitraum (Arbeitstag der Spanne zählt).
    visible = sichtbare Mitarbeiter (Führungskraft), None = alle der Firma."""
    stmt = select(func.distinct(Punch.employee_id)).where(
        Punch.tenant_id == tenant_id,
        Punch.project_id.is_not(None),
        Punch.timestamp_utc >= datetime.combine(first - timedelta(days=1), time.min),
        Punch.timestamp_utc < datetime.combine(last + timedelta(days=2), time.min),
    )
    candidates = set((await db.execute(stmt)).scalars().all())
    if visible is not None:
        candidates &= visible
    if employee_id is not None:
        candidates &= {employee_id}
    if not candidates:
        return []
    employees = (
        await db.execute(select(Employee).where(Employee.tenant_id == tenant_id, Employee.id.in_(candidates)))
    ).scalars().all()
    projects = {
        p.id: p for p in (await db.execute(select(Project).where(Project.tenant_id == tenant_id))).scalars().all()
    }
    customers = {
        c.id: c for c in (await db.execute(select(Customer).where(Customer.tenant_id == tenant_id))).scalars().all()
    }
    cost_centers = {
        c.id: c for c in (await db.execute(select(CostCenter).where(CostCenter.tenant_id == tenant_id))).scalars().all()
    }
    result: list[ProjectTime] = []
    for employee in employees:
        tz = await ts.employee_timezone(db, employee)
        totals: dict[int, float] = defaultdict(float)
        for day_punches in (await ts.punches_by_day(db, employee, first, last, tz)).values():
            for pid, seconds in project_seconds(day_punches).items():
                totals[pid] += seconds
        for pid, seconds in totals.items():
            project = projects.get(pid)
            if project is None or (project_id is not None and pid != project_id):
                continue
            if customer_id is not None and project.customer_id != customer_id:
                continue
            result.append(
                ProjectTime(
                    employee=employee,
                    project=project,
                    customer=customers.get(project.customer_id) if project.customer_id else None,
                    cost_center=cost_centers.get(project.cost_center_id) if project.cost_center_id else None,
                    minutes=round(seconds / 60),
                )
            )
    result.sort(key=lambda r: ((r.project.number or ""), r.project.name, r.employee.last_name, r.employee.first_name))
    return result


async def project_in_use(db: AsyncSession, project_id: int) -> bool:
    return (await db.execute(select(Punch.id).where(Punch.project_id == project_id).limit(1))).first() is not None
