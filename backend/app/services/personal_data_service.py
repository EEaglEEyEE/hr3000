"""Persönliche Daten (verschlüsseltes JSON) und Status „Auszeit“ für Listen."""
import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Absence, AbsenceApprovalStatus, AbsenceType, Employee, EmployeePersonalData
from app.services.secret_box import decrypt_secret, encrypt_secret

# Abwesenheiten, die als „Auszeit“ zählen (Status LEAVE)
LEAVE_CATEGORIES = (AbsenceType.PARENTAL_LEAVE, AbsenceType.CARE_LEAVE)


async def load(db: AsyncSession, employee_id: int) -> dict:
    row = (
        await db.execute(select(EmployeePersonalData).where(EmployeePersonalData.employee_id == employee_id))
    ).scalar_one_or_none()
    if row is None:
        return {}
    plain = decrypt_secret(row.data)
    return json.loads(plain) if plain else {}


async def save(db: AsyncSession, employee: Employee, data: dict) -> None:
    row = (
        await db.execute(select(EmployeePersonalData).where(EmployeePersonalData.employee_id == employee.id))
    ).scalar_one_or_none()
    cleaned = {key: value for key, value in data.items() if value is not None}
    if row is None:
        row = EmployeePersonalData(tenant_id=employee.tenant_id, employee_id=employee.id, data="")
        db.add(row)
    row.data = encrypt_secret(json.dumps(cleaned, ensure_ascii=False))


async def delete(db: AsyncSession, employee_id: int) -> None:
    row = (
        await db.execute(select(EmployeePersonalData).where(EmployeePersonalData.employee_id == employee_id))
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)


async def mark_leave(db: AsyncSession, employees: list[Employee], today: date | None = None) -> None:
    """Setzt für Employee.employment_status, wer heute in Elternzeit/Pflegezeit ist (eine Abfrage)."""
    if not employees:
        return
    today = today or date.today()
    on_leave = set(
        (
            await db.execute(
                select(Absence.employee_id).where(
                    Absence.employee_id.in_([e.id for e in employees]),
                    Absence.type.in_(LEAVE_CATEGORIES),
                    Absence.approval_status == AbsenceApprovalStatus.APPROVED,
                    Absence.date_from <= today,
                    Absence.date_to >= today,
                )
            )
        ).scalars().all()
    )
    for employee in employees:
        employee._on_leave = employee.id in on_leave
