from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_super_admin_principal
from app.db import get_db
from app.errors import AppError
from app.models import Account, AuditAction, Employee, HrRole, Tenant
from app.schemas.tenant import (
    TenantAdminEmailUpdateRequest,
    TenantAdminEmailUpdateResponse,
    TenantAdminPasswordResetRequest,
    TenantAdminPasswordResetResponse,
    TenantCreateRequest,
    TenantCreateResponse,
    TenantPurgeRequest,
    TenantPurgeResponse,
    TenantResponse,
    TenantUpdateRequest,
)
from app.services.audit_service import log_action
from app.services.auth_service import generate_one_time_password, hash_password
from app.services.credentials_mail import login_url, send_credentials_email
from app.services import tenant_lifecycle
from app.services.tenant_provisioning import provision_tenant

router = APIRouter(tags=["tenants"])


async def _get_oldest_tenant_admin(db: AsyncSession, tenant_id: int) -> Account:
    """Es gibt aktuell keine Nutzerverwaltung pro Mandant, daher wirken
    admin-email-Änderung und Passwort-Reset auf den ältesten ADMIN-Account
    des Mandanten (in aller Regel der Erst-Admin aus create_tenant)."""
    result = await db.execute(
        select(Account)
        .where(Account.tenant_id == tenant_id, Account.role == HrRole.ADMIN, Account.email.is_not(None))
        .order_by(Account.id.asc())
        .limit(1)
    )
    admin = result.scalar_one_or_none()
    if admin is None:
        raise AppError(404, "ADMIN_NOT_FOUND", "Für diesen Mandanten existiert kein Admin-Account.")
    return admin


@router.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(
    actor: Actor = Depends(get_current_super_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> list[TenantResponse]:
    result = await db.execute(select(Tenant).order_by(Tenant.name.asc()))
    counts = dict(
        (
            await db.execute(
                select(Employee.tenant_id, func.count()).where(Employee.active.is_(True)).group_by(Employee.tenant_id)
            )
        ).all()
    )
    return [
        TenantResponse.model_validate(t).model_copy(update={"active_employees": counts.get(t.id, 0)})
        for t in result.scalars().all()
    ]


@router.post("/tenants", response_model=TenantCreateResponse, status_code=201)
async def create_tenant(
    payload: TenantCreateRequest,
    request: Request,
    actor: Actor = Depends(get_current_super_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> TenantCreateResponse:
    # Das Einmalpasswort wird nur in dieser Antwort ausgegeben, nirgends gespeichert.
    initial_password = generate_one_time_password()
    tenant = await provision_tenant(
        db,
        subdomain=payload.subdomain,
        name=payload.name,
        admin_email=payload.admin_email,
        admin_password=initial_password,
        plan=payload.plan,
        contact_email=payload.contact_email,
        contact_name=payload.contact_name,
    )

    credentials_emailed = False
    if payload.send_credentials_email:
        credentials_emailed = await send_credentials_email(
            to=payload.admin_email,
            organisation=tenant.name,
            url=login_url(request, tenant.subdomain),
            login_email=payload.admin_email,
            password=initial_password,
        )

    return TenantCreateResponse(
        id=tenant.id,
        subdomain=tenant.subdomain,
        name=tenant.name,
        status=tenant.status,
        contact_email=tenant.contact_email,
        contact_name=tenant.contact_name,
        admin_email=payload.admin_email,
        initial_admin_password=initial_password,
        credentials_emailed=credentials_emailed,
    )


@router.patch("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: int,
    payload: TenantUpdateRequest,
    actor: Actor = Depends(get_current_super_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise AppError(404, "TENANT_NOT_FOUND", "Mandant nicht gefunden.")

    if payload.name is not None:
        tenant.name = payload.name
    if payload.status is not None:
        tenant.status = payload.status
    if payload.plan is not None:
        tenant.plan = payload.plan
    if payload.contact_email is not None:
        tenant.contact_email = payload.contact_email
    if payload.contact_name is not None:
        tenant.contact_name = payload.contact_name

    await db.commit()
    await db.refresh(tenant)
    return TenantResponse.model_validate(tenant)


@router.post("/tenants/{tenant_id}/reset-admin-password", response_model=TenantAdminPasswordResetResponse)
async def reset_tenant_admin_password(
    tenant_id: int,
    request: Request,
    payload: TenantAdminPasswordResetRequest | None = None,
    actor: Actor = Depends(get_current_super_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> TenantAdminPasswordResetResponse:
    """Setzt das Passwort des (ersten) Tenant-Admins zurück, ohne E-Mail-Versand
    – das neue Einmalpasswort wird nur in dieser Antwort ausgegeben."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise AppError(404, "TENANT_NOT_FOUND", "Mandant nicht gefunden.")

    admin = await _get_oldest_tenant_admin(db, tenant_id)

    new_password = generate_one_time_password()
    admin.password_hash = hash_password(new_password)
    # Der Super-Admin bürgt für die Adresse – eine ausstehende E-Mail-Bestätigung entfällt.
    admin.email_verification_pending = False
    await db.commit()

    emailed = False
    if payload is not None and payload.send_email:
        emailed = await send_credentials_email(
            to=admin.email,
            organisation=tenant.name,
            url=login_url(request, tenant.subdomain),
            login_email=admin.email,
            password=new_password,
        )
    return TenantAdminPasswordResetResponse(
        admin_email=admin.email, new_password=new_password, emailed=emailed
    )


@router.patch("/tenants/{tenant_id}/admin-email", response_model=TenantAdminEmailUpdateResponse)
async def update_tenant_admin_email(
    tenant_id: int,
    payload: TenantAdminEmailUpdateRequest,
    actor: Actor = Depends(get_current_super_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> TenantAdminEmailUpdateResponse:
    """Ändert die Login-E-Mail des (ersten) Tenant-Admins – z.B. wenn die
    ursprüngliche Adresse beim Anlegen falsch war oder der Ansprechpartner
    gewechselt hat."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise AppError(404, "TENANT_NOT_FOUND", "Mandant nicht gefunden.")

    admin = await _get_oldest_tenant_admin(db, tenant_id)

    old_email = admin.email
    admin.email = payload.new_email

    # tenant_id ist bewusst das Ziel-Mandant (nicht actor.tenant_id, das beim
    # Super-Admin None ist) – der Eintrag gehört fachlich zum betroffenen
    # Mandanten, damit dessen Admin ihn im eigenen Audit-Protokoll sieht.
    log_action(
        db,
        tenant_id=tenant_id,
        actor_account_id=actor.account_id,
        action=AuditAction.TENANT_ADMIN_EMAIL_CHANGED,
        entity_type="account",
        entity_id=admin.id,
        detail=f"{old_email} -> {payload.new_email}",
    )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "EMAIL_TAKEN", "Diese E-Mail wird bereits verwendet.") from exc

    return TenantAdminEmailUpdateResponse(admin_email=admin.email)


@router.post("/tenants/{tenant_id}/cancel", response_model=TenantResponse)
async def cancel_tenant(
    tenant_id: int,
    actor: Actor = Depends(get_current_super_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    """Im Namen der Firma kündigen (z.B. nach Kündigung per E-Mail): Vertragsende zum
    Monatsende, Löschung 30 Tage danach (services/tenant_lifecycle.py)."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise AppError(404, "TENANT_NOT_FOUND", "Mandant nicht gefunden.")
    if tenant_lifecycle.cancel(tenant):
        log_action(
            db,
            tenant_id=tenant_id,
            actor_account_id=actor.account_id,
            action=AuditAction.SETTINGS_CHANGED,
            entity_type="tenant",
            entity_id=tenant_id,
            detail=f"Gekündigt (Plattform) zum {tenant.contract_end:%d.%m.%Y}, Löschung am {tenant.deletion_due_on:%d.%m.%Y}",
        )
        await db.commit()
        await db.refresh(tenant)
    return TenantResponse.model_validate(tenant)


@router.post("/tenants/{tenant_id}/cancel/revoke", response_model=TenantResponse)
async def revoke_tenant_cancellation(
    tenant_id: int,
    actor: Actor = Depends(get_current_super_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise AppError(404, "TENANT_NOT_FOUND", "Mandant nicht gefunden.")
    if tenant_lifecycle.revoke_cancellation(tenant):
        log_action(
            db,
            tenant_id=tenant_id,
            actor_account_id=actor.account_id,
            action=AuditAction.SETTINGS_CHANGED,
            entity_type="tenant",
            entity_id=tenant_id,
            detail="Kündigung zurückgenommen (Plattform)",
        )
        await db.commit()
        await db.refresh(tenant)
    return TenantResponse.model_validate(tenant)


@router.post("/tenants/{tenant_id}/purge", response_model=TenantPurgeResponse)
async def purge_tenant_now(
    tenant_id: int,
    payload: TenantPurgeRequest,
    actor: Actor = Depends(get_current_super_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> TenantPurgeResponse:
    """Firma mit ALLEN Daten sofort endgültig löschen (z.B. Spam-Registrierung oder ausdrücklicher
    Wunsch). Nur mit eingetippter Subdomain als Bestätigung; nicht rückgängig zu machen."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise AppError(404, "TENANT_NOT_FOUND", "Mandant nicht gefunden.")
    if payload.confirm_subdomain.lower() != tenant.subdomain:
        raise AppError(400, "CONFIRMATION_MISMATCH", "Die eingegebene Subdomain stimmt nicht überein.")
    counts = await tenant_lifecycle.purge_tenant(db, tenant_id)
    return TenantPurgeResponse(subdomain=payload.confirm_subdomain.lower(), deleted_rows=sum(counts.values()))
