"""Wen eine Führungskraft sehen und für wen sie entscheiden darf: sich selbst und alle direkt und
indirekt Unterstellten (app/services/org_service.py). Admin/HR/Super-Admin sind uneingeschränkt.

Stellvertretungen handeln wie eine zusätzliche Leitung ihrer Abteilung – je nach ihren Rechten:

| Rechte  | sieht die Abteilung                   | entscheidet (und wird benachrichtigt) |
|---------|---------------------------------------|---------------------------------------|
| FULL    | immer                                 | immer                                 |
| STANDBY | immer                                 | wenn keine Leitung verfügbar ist      |
| ABSENCE | wenn keine Leitung verfügbar ist      | wenn keine Leitung verfügbar ist      |

„Verfügbar“ ist eine Leitung, die aktiv ist, einen Zugang mit Verwaltungsrolle hat und heute nicht
(genehmigt) abwesend ist. Eine Abteilung ohne Leitung hat nie eine verfügbare.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor
from app.errors import AppError
from app.models import Absence, AbsenceApprovalStatus, AbsenceType, Account, Employee
from app.models.department import DEPUTY_FULL, DEPUTY_STANDBY
from app.services.org_service import ExtraHeads, OrgSnapshot, load_org

VIEW = "view"
DECIDE = "decide"


async def able_to_decide(db: AsyncSession, employee_ids: set[int]) -> set[int]:
    """Wer davon als Person entscheiden kann: aktiv, mit Login und Verwaltungsrolle."""
    if not employee_ids:
        return set()
    rows = (
        await db.execute(
            select(Account.employee_id)
            .join(Employee, Employee.id == Account.employee_id)
            .where(
                Account.employee_id.in_(employee_ids),
                Account.role.is_not(None),
                Account.email.is_not(None),
                Account.password_hash.is_not(None),
                Employee.active.is_(True),
            )
        )
    ).scalars().all()
    return set(rows)


async def absent_on(db: AsyncSession, employee_ids: set[int], day: date) -> set[int]:
    """Wer davon an diesem Tag genehmigt abwesend ist (ohne Arbeitszeit-Einträge wie Dienstreise)."""
    if not employee_ids:
        return set()
    rows = (
        await db.execute(
            select(Absence.employee_id).where(
                Absence.employee_id.in_(employee_ids),
                Absence.approval_status == AbsenceApprovalStatus.APPROVED,
                Absence.type != AbsenceType.WORK_TIME,
                Absence.date_from <= day,
                Absence.date_to >= day,
            )
        )
    ).scalars().all()
    return set(rows)


async def available_leaders(db: AsyncSession, employee_ids: set[int], day: date) -> set[int]:
    """Entscheiden können und heute nicht abwesend."""
    able = await able_to_decide(db, employee_ids)
    return able - await absent_on(db, able, day)


async def acting_deputies(
    db: AsyncSession, org: OrgSnapshot, day: date, purpose: str, only: int | None = None
) -> ExtraHeads:
    """Abteilung -> Stellvertretungen, die gerade wie eine Leitung gelten (für Sicht: VIEW, für
    Entscheidungen: DECIDE). only = nur diese Person betrachten."""
    candidates: list[tuple[int, int, str]] = [
        (department_id, employee_id, rights)
        for department_id in org.leaders
        for employee_id, rights in org.deputies(department_id)
        if only is None or employee_id == only
    ]
    always = {DEPUTY_FULL, DEPUTY_STANDBY} if purpose == VIEW else {DEPUTY_FULL}
    conditional = [(d, e) for d, e, rights in candidates if rights not in always]
    extra: ExtraHeads = {}
    for department_id, employee_id, rights in candidates:
        if rights in always:
            extra.setdefault(department_id, set()).add(employee_id)
    if conditional:
        heads = {h for d, _ in conditional for h in org.heads(d)}
        available = await available_leaders(db, heads, day)
        for department_id, employee_id in conditional:
            if not any(h in available for h in org.heads(department_id)):
                extra.setdefault(department_id, set()).add(employee_id)
    return extra


async def _scope(db: AsyncSession, actor: Actor, purpose: str, day: date | None) -> set[int] | None:
    if not actor.is_supervisor_level:
        return None
    if actor.employee is None or actor.tenant_id is None:
        return set()
    org = await load_org(db, actor.tenant_id)
    me = actor.employee.id
    extra = await acting_deputies(db, org, day or date.today(), purpose, only=me)
    return org.reports(me, extra) | {me}


async def visible_employee_ids(db: AsyncSession, actor: Actor, day: date | None = None) -> set[int] | None:
    """None = uneingeschränkt. Für eine Führungskraft: sie selbst und ihre Unterstellten (auch als
    Stellvertretung, je nach Rechten); ohne zugehörigen Mitarbeiter niemand."""
    return await _scope(db, actor, VIEW, day)


async def decidable_employee_ids(db: AsyncSession, actor: Actor, day: date | None = None) -> set[int] | None:
    """Wie visible_employee_ids, aber für Entscheidungen (Stellvertretung STANDBY/ABSENCE nur, wenn
    keine Leitung ihrer Abteilung verfügbar ist). Enthält die Person selbst."""
    return await _scope(db, actor, DECIDE, day)


async def ensure_employee_visible(db: AsyncSession, actor: Actor, employee: Employee) -> None:
    """Wirft 404 (nicht 403 – kein Hinweis, ob es den Mitarbeiter gibt, wie das Cross-Tenant-Muster in
    app/api/deps.py), wenn eine Führungskraft auf jemanden außerhalb ihres Bereichs zugreifen will."""
    visible = await visible_employee_ids(db, actor)
    if visible is None:
        return
    if employee.id not in visible:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")

