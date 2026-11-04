from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor
from app.errors import AppError
from app.models import Employee, SupervisorTeamAssignment


async def supervisor_team_ids(db: AsyncSession, actor: Actor) -> set[int] | None:
    """None bedeutet uneingeschränkt (Admin/HR/Super-Admin). Für einen
    Supervisor die Menge seiner zugeordneten team_id – leer, falls (noch)
    keinem Team zugeordnet."""
    if not actor.is_supervisor_level:
        return None

    stmt = select(SupervisorTeamAssignment.team_id)
    if actor.hr_user is not None:
        stmt = stmt.where(SupervisorTeamAssignment.hr_user_id == actor.hr_user.id)
    else:
        stmt = stmt.where(SupervisorTeamAssignment.employee_id == actor.employee.id)
    result = await db.execute(stmt)
    return set(result.scalars().all())


async def ensure_employee_visible(db: AsyncSession, actor: Actor, employee: Employee) -> None:
    """Wirft 404 (nicht 403 – kein Leak, ob der Mitarbeiter überhaupt
    existiert, konsistent mit dem Cross-Tenant-Muster in app/api/deps.py),
    wenn ein Supervisor auf einen Mitarbeiter außerhalb seiner Teams
    zugreifen will. Admin/HR/Super-Admin sind uneingeschränkt."""
    team_ids = await supervisor_team_ids(db, actor)
    if team_ids is None:
        return
    if employee.team_id is None or employee.team_id not in team_ids:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
