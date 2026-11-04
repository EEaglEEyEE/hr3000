from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Employee, HrRole, HrUser


async def count_other_admins(
    db: AsyncSession,
    tenant_id: int,
    exclude_employee_id: int | None = None,
    exclude_hr_user_id: int | None = None,
) -> int:
    """Anzahl der Administratoren eines Mandanten ohne den ausgenommenen: HR-User
    mit ADMIN sowie aktive Mitarbeiter mit hr_role=ADMIN und Login."""
    user_filter = [HrUser.tenant_id == tenant_id, HrUser.role == HrRole.ADMIN]
    if exclude_hr_user_id is not None:
        user_filter.append(HrUser.id != exclude_hr_user_id)
    admin_users = (await db.execute(select(func.count()).select_from(HrUser).where(*user_filter))).scalar_one()

    employee_filter = [
        Employee.tenant_id == tenant_id,
        Employee.hr_role == HrRole.ADMIN,
        Employee.active.is_(True),
        Employee.login_email.is_not(None),
    ]
    if exclude_employee_id is not None:
        employee_filter.append(Employee.id != exclude_employee_id)
    admin_employees = (
        await db.execute(select(func.count()).select_from(Employee).where(*employee_filter))
    ).scalar_one()
    return admin_users + admin_employees


async def ensure_not_last_admin(
    db: AsyncSession,
    tenant_id: int,
    exclude_employee_id: int | None = None,
    exclude_hr_user_id: int | None = None,
) -> None:
    """Ein Mandant darf nie ohne Administrator dastehen (Rolle entziehen,
    deaktivieren, anonymisieren, löschen)."""
    if await count_other_admins(db, tenant_id, exclude_employee_id, exclude_hr_user_id) == 0:
        raise AppError(
            400,
            "LAST_ADMIN",
            "Das ist der letzte Administrator des Mandanten – bitte zuerst einen weiteren Admin ernennen.",
        )
