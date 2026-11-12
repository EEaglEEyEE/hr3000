from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_full_hr_principal
from app.db import get_db
from app.models import Account, AuditLogEntry
from app.schemas.audit_log import AuditLogEntryResponse
from app.services.whistle_service import ENTITY_TYPE as WHISTLE_ENTITY_TYPE

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
    # Einträge zu Meldungen des Hinweisgebersystems gehören nicht hierher: Schon „Meldung X angesehen“
    # würde Admins und HR verraten, dass es eine Meldung gibt. Die Meldestelle sieht sie am Vorgang.
    stmt = select(AuditLogEntry).where(
        AuditLogEntry.tenant_id == actor.tenant_id, AuditLogEntry.entity_type != WHISTLE_ENTITY_TYPE
    )
    if entity_type is not None:
        stmt = stmt.where(AuditLogEntry.entity_type == entity_type)
    if date_from is not None:
        stmt = stmt.where(AuditLogEntry.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        stmt = stmt.where(AuditLogEntry.created_at <= datetime.combine(date_to, datetime.max.time()))
    stmt = stmt.order_by(AuditLogEntry.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    entries = result.scalars().all()

    account_ids = {e.actor_account_id for e in entries if e.actor_account_id is not None}
    accounts: dict[int, Account] = {}
    if account_ids:
        result = await db.execute(select(Account).where(Account.id.in_(account_ids)))
        accounts = {a.id: a for a in result.scalars().all()}

    def _actor_label(entry: AuditLogEntry) -> str:
        if entry.actor_account_id is None:
            return "System"
        account = accounts.get(entry.actor_account_id)
        return account.display_name if account else "Unbekannt"

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
