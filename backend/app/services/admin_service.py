from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Account, Employee, HrRole


async def count_other_admins(
    db: AsyncSession,
    tenant_id: int,
    exclude_employee_id: int | None = None,
    exclude_account_id: int | None = None,
) -> int:
    """Anzahl der Administratoren eines Mandanten ohne den ausgenommenen: Konten mit Rolle ADMIN und
    Zugang (E-Mail gesetzt); ist das Konto mit einem Mitarbeiter verknüpft, muss dieser aktiv sein."""
    stmt = (
        select(func.count())
        .select_from(Account)
        .outerjoin(Employee, Employee.id == Account.employee_id)
        .where(
            Account.tenant_id == tenant_id,
            Account.role == HrRole.ADMIN,
            Account.email.is_not(None),
            Account.password_hash.is_not(None),
            or_(Account.employee_id.is_(None), Employee.active.is_(True)),
        )
    )
    if exclude_account_id is not None:
        stmt = stmt.where(Account.id != exclude_account_id)
    if exclude_employee_id is not None:
        stmt = stmt.where(or_(Account.employee_id.is_(None), Account.employee_id != exclude_employee_id))
    return (await db.execute(stmt)).scalar_one()


async def ensure_not_last_admin(
    db: AsyncSession,
    tenant_id: int,
    exclude_employee_id: int | None = None,
    exclude_account_id: int | None = None,
) -> None:
    """Ein Mandant darf nie ohne Administrator dastehen (Rolle entziehen,
    deaktivieren, anonymisieren, löschen)."""
    if await count_other_admins(db, tenant_id, exclude_employee_id, exclude_account_id) == 0:
        raise AppError(
            400,
            "LAST_ADMIN",
            "Das ist der letzte Administrator des Mandanten – bitte zuerst einen weiteren Admin ernennen.",
        )
