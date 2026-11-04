"""Öffentliche Schnittstellen der Website (hr3000.de) – ohne Mandanten-Kontext.

- ``GET /public/tenant-lookup?subdomain=firma``: Die Login-Seite der Website (hr3000.de/login)
  fragt hier, ob es die Firma gibt, und leitet dann auf ``https://firma.hr3000.de/`` weiter.
  Fehlversuche sind je IP begrenzt (Durchprobieren von Firmennamen ausbremsen); gefundene
  Firmen zählen nicht. Gesperrte Mandanten gelten als nicht vorhanden.
- ``GET /public/subdomain-available?subdomain=firma``: Live-Prüfung im Registrierungsformular.
- ``POST /public/signup``: Selbstregistrierung (hr3000.de/registrieren) – legt Firma und
  Erst-Admin mit selbst gewähltem Passwort an, Tarif "Kostenlos". Begrenzt je IP und
  plattformweit pro Tag (settings.self_signup_*), damit Bots weder Datenmüll noch massenhaft
  Zertifikate erzeugen. Eine E-Mail-Bestätigung gibt es noch nicht (kein Plattform-SMTP);
  ist SMTP eingerichtet, geht eine Willkommensmail ohne Zugangsdaten raus.

Alle Pfade stehen in middleware/tenant._NO_TENANT_PATHS und landen nicht im Zugriffsprotokoll
(main.SkipPublicAccessLog) – so steht es in der Datenschutzerklärung der Website.
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.models import Tenant, TenantPlan, TenantStatus
from app.schemas.tenant import (
    RESERVED_SUBDOMAINS,
    SUBDOMAIN_PATTERN,
    SignupRequest,
    SignupResponse,
    SubdomainAvailabilityResponse,
    TenantLookupResponse,
)
from app.services import rate_limiter
from app.services.email_service import send_email
from app.services.platform_domain import base_domain
from app.services.tenant_provisioning import provision_tenant

_LOOKUP_MISS_LIMIT = 20
_LOOKUP_WINDOW_SECONDS = 300
_AVAILABILITY_LIMIT = 60
_DAY_SECONDS = 24 * 3600

router = APIRouter(prefix="/public", tags=["public"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/tenant-lookup", response_model=TenantLookupResponse)
async def tenant_lookup(
    request: Request,
    subdomain: str = Query(min_length=1, max_length=63, pattern=SUBDOMAIN_PATTERN),
    db: AsyncSession = Depends(get_db),
) -> TenantLookupResponse:
    key = f"tenant-lookup:{_client_ip(request)}"
    rate_limiter.check_rate_limit(key, _LOOKUP_MISS_LIMIT, _LOOKUP_WINDOW_SECONDS, code="TOO_MANY_LOOKUPS")
    base = base_domain()
    tenant_id = await db.scalar(
        select(Tenant.id).where(Tenant.subdomain == subdomain, Tenant.status != TenantStatus.SUSPENDED)
    )
    if tenant_id is None or base is None:
        rate_limiter.record_failure(key)
        raise AppError(404, "TENANT_NOT_FOUND", "Diese Firma gibt es bei HR3000 nicht.")
    return TenantLookupResponse(login_url=f"https://{subdomain}.{base}/")


def _ensure_signup_open() -> str:
    base = base_domain()
    if not settings.self_signup_enabled or base is None:
        raise AppError(404, "SIGNUP_DISABLED", "Die Registrierung ist derzeit nicht möglich.")
    return base


@router.get("/subdomain-available", response_model=SubdomainAvailabilityResponse)
async def subdomain_available(
    request: Request,
    subdomain: str = Query(min_length=1, max_length=63, pattern=SUBDOMAIN_PATTERN),
    db: AsyncSession = Depends(get_db),
) -> SubdomainAvailabilityResponse:
    _ensure_signup_open()
    key = f"subdomain-available:{_client_ip(request)}"
    rate_limiter.check_rate_limit(key, _AVAILABILITY_LIMIT, _LOOKUP_WINDOW_SECONDS, code="TOO_MANY_LOOKUPS")
    rate_limiter.record_failure(key)  # jede Abfrage zählt
    if subdomain in RESERVED_SUBDOMAINS:
        return SubdomainAvailabilityResponse(available=False, reason="RESERVED")
    # Auch gesperrte Mandanten belegen ihre Adresse weiter.
    taken = await db.scalar(select(Tenant.id).where(Tenant.subdomain == subdomain))
    if taken is not None:
        return SubdomainAvailabilityResponse(available=False, reason="TAKEN")
    return SubdomainAvailabilityResponse(available=True)


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(payload: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)) -> SignupResponse:
    base = _ensure_signup_open()
    ip_key = f"signup:{_client_ip(request)}"
    global_key = "signup:all"
    rate_limiter.check_rate_limit(ip_key, settings.self_signup_per_ip_per_day, _DAY_SECONDS, code="TOO_MANY_SIGNUPS")
    rate_limiter.check_rate_limit(global_key, settings.self_signup_per_day, _DAY_SECONDS, code="TOO_MANY_SIGNUPS")

    tenant = await provision_tenant(
        db,
        subdomain=payload.subdomain,
        name=payload.company_name,
        admin_email=str(payload.email),
        admin_password=payload.password,
        plan=TenantPlan.FREE,
        contact_email=str(payload.email),
        contact_name=payload.contact_name,
        self_signup=True,
    )
    # Nur erfolgreiche Registrierungen zählen (Tippfehler bei der Adresse sollen nicht sperren).
    rate_limiter.record_failure(ip_key)
    rate_limiter.record_failure(global_key)

    url = f"https://{tenant.subdomain}.{base}/"
    await send_email(
        str(payload.email),
        "Willkommen bei HR3000",
        (
            f"Hallo {payload.contact_name},\n\n"
            f"deine Firma „{tenant.name}“ ist bei HR3000 eingerichtet.\n\n"
            f"Anmeldung: {url}\n"
            f"Benutzer:  {payload.email}\n"
            f"Passwort:  das bei der Registrierung gewählte\n\n"
            f"Tablet-App für den Eingang: https://kiosk.{tenant.subdomain}.{base}/\n\n"
            "Viel Erfolg mit HR3000!\n"
        ),
    )
    return SignupResponse(subdomain=tenant.subdomain, login_url=url)
