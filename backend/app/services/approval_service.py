"""Genehmigungsketten für Abwesenheitsanträge (je Abwesenheitsart, AbsenceTypeDefinition.approval_chain).

Schritte:
- TEAM: Teamleitung des Teams (Konto mit Rolle Führungskraft, SupervisorTeamAssignment) – bisheriges
  Verhalten, Standard („DEFAULT“).
- SUPERVISOR: die Führungskraft der Person (Employee.supervisor_id), wenn sie eine Verwaltungsrolle und
  einen Zugang hat. Ist sie heute abwesend und hat eine Vertretung bei Genehmigungen
  (approval_delegate_id), entscheidet die Vertretung. Ohne geeignete Führungskraft: Admin/HR.
- HR: Admin oder HR.

Admin und HR dürfen jeden Schritt entscheiden (z. B. wenn die Führungskraft länger fehlt).
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor
from app.errors import AppError
from app.models import Absence, AbsenceApprovalStatus, AbsenceType, AbsenceTypeDefinition, Employee
from app.services.team_scope_service import ensure_employee_visible

CHAINS: dict[str, list[str]] = {
    "DEFAULT": ["TEAM"],
    "SUPERVISOR": ["SUPERVISOR"],
    "SUPERVISOR_HR": ["SUPERVISOR", "HR"],
    "HR": ["HR"],
}
STEP_LABELS = {"TEAM": "Teamleitung", "SUPERVISOR": "Führungskraft", "HR": "Admin/HR"}


async def chain_for(db: AsyncSession, absence: Absence) -> list[str]:
    definition = await db.get(AbsenceTypeDefinition, absence.absence_type_id) if absence.absence_type_id else None
    return CHAINS.get(definition.approval_chain if definition else "DEFAULT", CHAINS["DEFAULT"])


def current_step(chain: list[str], absence: Absence) -> tuple[int, str]:
    """(Schrittnummer ab 1, Art) – geklammert, falls die Kette inzwischen kürzer ist."""
    number = min(max(absence.approval_step or 1, 1), len(chain))
    return number, chain[number - 1]


def _can_approve_as_person(employee: Employee | None) -> bool:
    account = employee.account if employee is not None else None
    return (
        employee is not None
        and employee.active
        and account is not None
        and account.role is not None
        and account.email is not None
        and account.password_hash is not None
    )


async def _absent_today(db: AsyncSession, employee_id: int, today: date) -> bool:
    return (
        await db.execute(
            select(Absence.id).where(
                Absence.employee_id == employee_id,
                Absence.approval_status == AbsenceApprovalStatus.APPROVED,
                Absence.type != AbsenceType.WORK_TIME,
                Absence.date_from <= today,
                Absence.date_to >= today,
            )
        )
    ).first() is not None


async def supervisor_approver(db: AsyncSession, employee: Employee, today: date | None = None) -> Employee | None:
    """Wer als Führungskraft entscheidet (oder deren Vertretung) – None heißt: Admin/HR."""
    if employee.supervisor_id is None:
        return None
    supervisor = await db.get(Employee, employee.supervisor_id)
    if supervisor is None or not supervisor.active:
        return None
    today = today or date.today()
    if supervisor.approval_delegate_id is not None and await _absent_today(db, supervisor.id, today):
        delegate = await db.get(Employee, supervisor.approval_delegate_id)
        if delegate is not None and delegate.id != employee.id and _can_approve_as_person(delegate):
            return delegate
    if _can_approve_as_person(supervisor):
        return supervisor
    return None


async def can_decide(db: AsyncSession, actor: Actor, absence: Absence, employee: Employee) -> bool:
    if actor.is_full_hr_level:
        return True
    _, step = current_step(await chain_for(db, absence), absence)
    if step == "TEAM":
        if not actor.is_supervisor_level:
            return False
        try:
            await ensure_employee_visible(db, actor, employee)
        except AppError:
            return False
        return True
    if step == "SUPERVISOR":
        approver = await supervisor_approver(db, employee)
        return approver is not None and actor.employee is not None and actor.employee.id == approver.id
    return False


async def waiting_for(db: AsyncSession, absence: Absence, employee: Employee) -> str | None:
    """Für die Anzeige: bei wem der offene Antrag gerade liegt (z. B. „Führungskraft: Bea Test“)."""
    if absence.approval_status != AbsenceApprovalStatus.PENDING:
        return None
    chain = await chain_for(db, absence)
    number, step = current_step(chain, absence)
    prefix = f"Schritt {number} von {len(chain)}: " if len(chain) > 1 else ""
    if step == "SUPERVISOR":
        approver = await supervisor_approver(db, employee)
        if approver is None:
            return f"{prefix}Admin/HR (keine Führungskraft mit Zugang)"
        return f"{prefix}Führungskraft {approver.first_name} {approver.last_name}"
    return prefix + STEP_LABELS[step]


async def step_recipients(db: AsyncSession, absence: Absence, employee: Employee) -> list[tuple[int, str | None]] | None:
    """Wer über den aktuellen Schritt benachrichtigt wird; None = bisherige Regel (Teamleitungen,
    sonst Admin/HR)."""
    from app.services.notification_service import full_hr_recipients

    _, step = current_step(await chain_for(db, absence), absence)
    if step == "TEAM":
        return None
    if step == "SUPERVISOR":
        approver = await supervisor_approver(db, employee)
        if approver is not None:
            return [(approver.account.id, approver.account.email)]
    return await full_hr_recipients(db, employee.tenant_id, exclude_employee_id=employee.id)
