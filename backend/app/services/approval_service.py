"""Genehmigungsketten für Abwesenheitsanträge (je Abwesenheitsart, AbsenceTypeDefinition.approval_chain).

Schritte:
- TEAM (Standard „DEFAULT“, Name aus der Zeit der Teams): jede Führungskraft, die für die Person
  entscheiden darf – ihre Führungskräfte, jemand darüber oder eine handelnde Stellvertretung
  (app/services/scope_service.py).
- SUPERVISOR: die zuständigen Führungskräfte der Person (supervisor_approvers: Ausnahme je Person bzw.
  Leitungen der Abteilung, bei Abwesenheit die Stellvertretungen, app/services/org_service.py) – jede
  davon darf entscheiden, alle werden benachrichtigt. Ohne Führungskraft mit Zugang: Admin/HR.
- HR: Admin oder HR.

Admin und HR dürfen jeden Schritt entscheiden (z. B. wenn die Führungskraft länger fehlt).
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.role_permissions import Area
from app.api.deps import Actor
from app.models import Absence, AbsenceApprovalStatus, AbsenceTypeDefinition, Account, Employee
from app.services.org_service import load_org
from app.services.scope_service import DECIDE, able_to_decide, absent_on, acting_deputies, decidable_employee_ids

CHAINS: dict[str, list[str]] = {
    "DEFAULT": ["TEAM"],
    "SUPERVISOR": ["SUPERVISOR"],
    "SUPERVISOR_HR": ["SUPERVISOR", "HR"],
    "HR": ["HR"],
}
STEP_LABELS = {"TEAM": "Führungskraft", "SUPERVISOR": "Führungskraft", "HR": "Admin/HR"}


async def chain_for(db: AsyncSession, absence: Absence) -> list[str]:
    definition = await db.get(AbsenceTypeDefinition, absence.absence_type_id) if absence.absence_type_id else None
    return CHAINS.get(definition.approval_chain if definition else "DEFAULT", CHAINS["DEFAULT"])


def current_step(chain: list[str], absence: Absence) -> tuple[int, str]:
    """(Schrittnummer ab 1, Art) – geklammert, falls die Kette inzwischen kürzer ist."""
    number = min(max(absence.approval_step or 1, 1), len(chain))
    return number, chain[number - 1]


async def supervisor_approvers(db: AsyncSession, employee: Employee, today: date | None = None) -> list[Employee]:
    """Wer als Führungskraft entscheidet und benachrichtigt wird – leer heißt: Admin/HR.

    1. Ausnahme je Person, wenn sie entscheiden kann und heute da ist.
    2. Sonst die Leitungen nach Abteilung samt Stellvertretungen, die gerade handeln (FULL immer,
       STANDBY/ABSENCE, wenn keine Leitung verfügbar ist) – davon alle, die heute da sind.
    3. Ist niemand da, bleiben die Zuständigen trotzdem zuständig (Ausnahme vor Abteilung), damit der
       Antrag nicht verwaist; Admin/HR können jederzeit entscheiden.
    Die Person selbst entscheidet nie über den eigenen Antrag."""
    today = today or date.today()
    org = await load_org(db, employee.tenant_id)
    override = org.override(employee.id)
    extra = await acting_deputies(db, org, today, DECIDE)
    department = [e for e in org.department_supervisors(employee.id, extra) if e != employee.id]
    candidates = ([override] if override is not None else []) + [e for e in department if e != override]
    able = await able_to_decide(db, set(candidates))
    absent = await absent_on(db, able, today)
    if override is not None and override in able and override not in absent:
        chosen = [override]
    else:
        chosen = [e for e in department if e in able and e not in absent]
        if not chosen:
            chosen = [override] if override is not None and override in able else [e for e in department if e in able]
    people = {p.id: p for p in (await db.execute(select(Employee).where(Employee.id.in_(chosen)))).scalars().all()} if chosen else {}
    return [people[e] for e in chosen if e in people]


async def can_decide(db: AsyncSession, actor: Actor, absence: Absence, employee: Employee) -> bool:
    if actor.is_full_hr_level:
        return True
    if actor.employee is not None and actor.employee.id == employee.id:
        return False  # eigene Anträge nie selbst
    _, step = current_step(await chain_for(db, absence), absence)
    if step == "TEAM":
        if not actor.is_supervisor_level:
            return False
        decidable = await decidable_employee_ids(db, actor)
        return decidable is not None and employee.id in decidable
    if step == "SUPERVISOR":
        if actor.employee is None:
            return False
        return any(approver.id == actor.employee.id for approver in await supervisor_approvers(db, employee))
    return False


async def waiting_for(db: AsyncSession, absence: Absence, employee: Employee) -> str | None:
    """Für die Anzeige: bei wem der offene Antrag gerade liegt (z. B. „Führungskraft Bea Test“)."""
    if absence.approval_status != AbsenceApprovalStatus.PENDING:
        return None
    chain = await chain_for(db, absence)
    number, step = current_step(chain, absence)
    prefix = f"Schritt {number} von {len(chain)}: " if len(chain) > 1 else ""
    if step == "SUPERVISOR":
        approvers = await supervisor_approvers(db, employee)
        if not approvers:
            return f"{prefix}Admin/HR (keine Führungskraft mit Zugang)"
        label = "Führungskraft" if len(approvers) == 1 else "Führungskräfte"
        return f"{prefix}{label} " + ", ".join(f"{a.first_name} {a.last_name}" for a in approvers)
    return prefix + STEP_LABELS[step]


async def approver_recipients(db: AsyncSession, employee: Employee) -> list[tuple[int, str | None]]:
    """Konten der zuständigen Führungskräfte (leer = niemand mit Zugang)."""
    approvers = await supervisor_approvers(db, employee)
    if not approvers:
        return []
    accounts = (
        await db.execute(select(Account).where(Account.employee_id.in_([a.id for a in approvers])))
    ).scalars().all()
    by_employee = {a.employee_id: a for a in accounts}
    return [(by_employee[a.id].id, by_employee[a.id].email) for a in approvers if a.id in by_employee]


async def step_recipients(db: AsyncSession, absence: Absence, employee: Employee) -> list[tuple[int, str | None]] | None:
    """Wer über den aktuellen Schritt benachrichtigt wird; None = Standardregel (zuständige
    Führungskräfte, sonst Admin/HR, siehe notify_absence_requested)."""
    from app.services.notification_service import full_hr_recipients

    _, step = current_step(await chain_for(db, absence), absence)
    if step == "TEAM":
        return None
    if step == "SUPERVISOR":
        recipients = await approver_recipients(db, employee)
        if recipients:
            return recipients
    return await full_hr_recipients(db, employee.tenant_id, exclude_employee_id=employee.id, area=Area.ABSENCES)
