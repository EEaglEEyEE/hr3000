"""Tarife: kostenlos bis config.free_employee_limit aktive Mitarbeiter, darüber nur mit Abo.

Gezählt werden aktive Mitarbeiter (Employee.active) – nicht HR-Konten oder Tablets. Geprüft wird
überall, wo ein Mitarbeiter aktiv wird: Anlegen, CSV-Import, Reaktivieren."""
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import AppError
from app.models import Employee
from app.models.tenant import Tenant, TenantPlan


@dataclass
class PlanStatus:
    plan: TenantPlan
    active_employees: int
    # None = keine Grenze
    limit: int | None

    @property
    def remaining(self) -> int | None:
        return None if self.limit is None else max(self.limit - self.active_employees, 0)


async def active_employee_count(db: AsyncSession, tenant_id: int) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(Employee).where(Employee.tenant_id == tenant_id, Employee.active.is_(True))
        )
    ).scalar_one()


async def plan_status(db: AsyncSession, tenant_id: int) -> PlanStatus:
    tenant = await db.get(Tenant, tenant_id)
    plan = tenant.plan if tenant is not None else TenantPlan.FREE
    limit = settings.free_employee_limit if plan == TenantPlan.FREE else None
    return PlanStatus(plan=plan, active_employees=await active_employee_count(db, tenant_id), limit=limit)


def limit_error(limit: int) -> AppError:
    return AppError(
        402,
        "PLAN_LIMIT_REACHED",
        f"Der kostenlose Tarif umfasst bis zu {limit} aktive Mitarbeiter. Für weitere Mitarbeiter bitte ein Abo "
        "abschließen (Einstellungen → Tarif) oder einen anderen Mitarbeiter deaktivieren.",
    )


async def ensure_can_activate(db: AsyncSession, tenant_id: int, additional: int = 1) -> None:
    """Wirft PLAN_LIMIT_REACHED, wenn durch `additional` neue aktive Mitarbeiter die Grenze des
    kostenlosen Tarifs überschritten würde."""
    status = await plan_status(db, tenant_id)
    if status.limit is not None and status.active_employees + additional > status.limit:
        raise limit_error(status.limit)
