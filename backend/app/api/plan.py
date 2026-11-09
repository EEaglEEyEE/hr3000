from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_admin_principal, get_current_hr_principal
from app.db import get_db
from app.errors import AppError
from app.models import Account, AuditAction, HrRole, Tenant
from app.schemas.plan import CancellationRequest, PlanResponse
from app.services.audit_service import log_action
from app.services.email_service import resolve_smtp_config, send_email
from app.services.plan_service import plan_status
from app.services.tenant_lifecycle import cancel, revoke_cancellation

router = APIRouter(tags=["plan"])


async def _plan_response(db: AsyncSession, tenant_id: int) -> PlanResponse:
    status = await plan_status(db, tenant_id)
    tenant = await db.get(Tenant, tenant_id)
    return PlanResponse(
        plan=status.plan,
        active_employees=status.active_employees,
        limit=status.limit,
        remaining=status.remaining,
        cancelled_at=tenant.cancelled_at,
        contract_end=tenant.contract_end,
        deletion_due_on=tenant.deletion_due_on,
    )


@router.get("/plan", response_model=PlanResponse)
async def get_plan(
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> PlanResponse:
    """Tarif des Mandanten, Auslastung (aktive Mitarbeiter) und ggf. Kündigung."""
    return await _plan_response(db, actor.tenant_id)


def _require_tenant_admin(actor: Actor) -> int:
    if actor.tenant_id is None:
        raise AppError(403, "TENANT_CONTEXT_REQUIRED", "Nur innerhalb einer Firma möglich.")
    return actor.tenant_id


async def _notify_cancellation(db: AsyncSession, tenant: Tenant) -> None:
    """Kündigungsbestätigung in Textform (best effort, nur mit eingerichtetem Mailversand)."""
    config = await resolve_smtp_config(db, tenant.id)
    if config is None:
        return
    to = tenant.contact_email or await db.scalar(
        select(Account.email)
        .where(Account.tenant_id == tenant.id, Account.role == HrRole.ADMIN, Account.email.is_not(None))
        .order_by(Account.id)
    )
    if not to:
        return
    await send_email(
        to,
        "HR3000 – Kündigung bestätigt",
        (
            f"Hallo,\n\nwir bestätigen die Kündigung von HR3000 für „{tenant.name}“.\n\n"
            f"Vertragsende: {tenant.contract_end:%d.%m.%Y}\n"
            f"Bis zum {tenant.deletion_due_on:%d.%m.%Y} könnt ihr alle Daten weiter nutzen und exportieren,\n"
            "danach werden sie endgültig gelöscht.\n\n"
            "Die Kündigung lässt sich bis dahin in den Einstellungen zurücknehmen.\n"
        ),
        config=config,
    )


@router.post("/account/cancel", response_model=PlanResponse)
async def cancel_account(
    payload: CancellationRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> PlanResponse:
    """HR3000 für die eigene Firma kündigen (nur Admins): Vertragsende zum Monatsende, danach
    30 Tage Zugriff zum Exportieren, dann Löschung aller Daten."""
    tenant_id = _require_tenant_admin(actor)
    tenant = await db.get(Tenant, tenant_id)
    if payload.confirm_subdomain.lower() != tenant.subdomain:
        raise AppError(400, "CONFIRMATION_MISMATCH", "Die eingegebene Adresse stimmt nicht mit der Firma überein.")
    if cancel(tenant):
        log_action(
            db,
            tenant_id=tenant_id,
            actor_account_id=actor.account_id,
            action=AuditAction.SETTINGS_CHANGED,
            entity_type="tenant",
            entity_id=tenant_id,
            detail=f"Gekündigt zum {tenant.contract_end:%d.%m.%Y}, Löschung am {tenant.deletion_due_on:%d.%m.%Y}",
        )
        await db.commit()
        await _notify_cancellation(db, tenant)
    return await _plan_response(db, tenant_id)


@router.post("/account/cancel/revoke", response_model=PlanResponse)
async def revoke_account_cancellation(
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> PlanResponse:
    """Kündigung zurücknehmen – bis zur Löschung jederzeit möglich."""
    tenant_id = _require_tenant_admin(actor)
    tenant = await db.get(Tenant, tenant_id)
    if revoke_cancellation(tenant):
        log_action(
            db,
            tenant_id=tenant_id,
            actor_account_id=actor.account_id,
            action=AuditAction.SETTINGS_CHANGED,
            entity_type="tenant",
            entity_id=tenant_id,
            detail="Kündigung zurückgenommen",
        )
        await db.commit()
    return await _plan_response(db, tenant_id)
