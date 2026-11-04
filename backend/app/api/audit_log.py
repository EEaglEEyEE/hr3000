from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal
from app.db import get_db
from app.models import AuditLogEntry, Employee, HrUser
from app.schemas.audit_log import AuditLogEntryResponse

router = APIRouter(tags=["audit_log"])

_MAX_LIMIT = 500


@router.get("/audit-log", response_model=list[AuditLogEntryResponse])
async def list_audit_log(
    entity_type: str | None = Query(default=None),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, le=_MAX_LIMIT),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogEntryResponse]:
    """Sicherheits-/compliancerelevante Änderungen (Stempel-Korrekturen/
    -Löschungen, Rollenänderungen, Urlaubsentscheidungen) – auf ADMIN/HR/
    SUPER_ADMIN beschränkt (siehe get_current_full_hr_principal), da ein
    Supervisor damit auch Aktionen außerhalb der eigenen Teams einsehen
    könnte."""
    stmt = select(AuditLogEntry).where(AuditLogEntry.tenant_id == actor.tenant_id)
    if entity_type is not None:
        stmt = stmt.where(AuditLogEntry.entity_type == entity_type)
    if date_from is not None:
        stmt = stmt.where(AuditLogEntry.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        stmt = stmt.where(AuditLogEntry.created_at <= datetime.combine(date_to, datetime.max.time()))
    stmt = stmt.order_by(AuditLogEntry.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    entries = result.scalars().all()

    hr_user_ids = {e.actor_hr_user_id for e in entries if e.actor_hr_user_id is not None}
    employee_ids = {e.actor_employee_id for e in entries if e.actor_employee_id is not None}

    hr_users: dict[int, HrUser] = {}
    if hr_user_ids:
        result = await db.execute(select(HrUser).where(HrUser.id.in_(hr_user_ids)))
        hr_users = {u.id: u for u in result.scalars().all()}

    employees: dict[int, Employee] = {}
    if employee_ids:
        result = await db.execute(select(Employee).where(Employee.id.in_(employee_ids)))
        employees = {e.id: e for e in result.scalars().all()}

    def _actor_label(entry: AuditLogEntry) -> str:
        if entry.actor_hr_user_id is not None:
            user = hr_users.get(entry.actor_hr_user_id)
            return user.email if user else "Unbekannt"
        if entry.actor_employee_id is not None:
            employee = employees.get(entry.actor_employee_id)
            return f"{employee.first_name} {employee.last_name}" if employee else "Unbekannt"
        return "System"

    return [
        AuditLogEntryResponse(
            id=entry.id,
            actor_label=_actor_label(entry),
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            detail=entry.detail,
            created_at=entry.created_at,
        )
        for entry in entries
    ]
