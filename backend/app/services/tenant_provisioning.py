"""Neue Firma (Mandant) einrichten – gemeinsam für den Super-Admin (api/tenants.py) und die
Selbstregistrierung auf der Website (api/public.py), damit beide Wege identisch einrichten."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Account, HrRole, Tenant, TenantPlan
from app.services.auth_service import hash_password
from app.services.settings_service import get_or_create_settings, seed_default_break_rules

# Fassung der Nutzungsbedingungen + des AV-Vertrags (website/agb, website/avv). Bei jeder
# inhaltlichen Änderung der Texte hochzählen – gespeichert wird, welcher Fassung zugestimmt wurde.
TERMS_VERSION = "2026-11-04"


async def provision_tenant(
    db: AsyncSession,
    *,
    subdomain: str,
    name: str,
    admin_email: str,
    admin_password: str,
    plan: TenantPlan = TenantPlan.FREE,
    contact_email: str | None = None,
    contact_name: str | None = None,
    self_signup: bool = False,
    admin_email_verification_pending: bool = False,
) -> Tenant:
    """Mandant, Standard-Einstellungen, gesetzliche §4-ArbZG-Pausenstaffel und Erst-Admin in
    EINER Transaktion – ganz oder gar nicht, sonst bliebe ein Mandant ohne Admin und mit
    belegter Subdomain zurück. 409 SUBDOMAIN_TAKEN, wenn die Adresse schon vergeben ist."""
    tenant = Tenant(
        subdomain=subdomain,
        name=name,
        contact_email=contact_email,
        contact_name=contact_name,
        plan=plan,
        self_signup=self_signup,
        terms_accepted_at=datetime.now(UTC).replace(tzinfo=None) if self_signup else None,
        terms_version=TERMS_VERSION if self_signup else None,
    )
    db.add(tenant)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "SUBDOMAIN_TAKEN", "Diese Subdomain wird bereits verwendet.") from exc

    await get_or_create_settings(db, tenant.id, commit=False)
    await seed_default_break_rules(db, tenant.id, commit=False)
    db.add(
        Account(
            tenant_id=tenant.id,
            email=admin_email,
            password_hash=hash_password(admin_password),
            role=HrRole.ADMIN,
            email_verification_pending=admin_email_verification_pending,
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "TENANT_PROVISIONING_FAILED", "Der Mandant konnte nicht angelegt werden.") from exc
    await db.refresh(tenant)
    return tenant
