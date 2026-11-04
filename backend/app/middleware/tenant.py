from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Tenant, TenantStatus
from app.services.platform_domain import tenant_subdomain_for_host

# Ohne Mandanten-Kontext: Healthcheck, Zertifikats-Freigabe für Caddy (api/tls.py) und die
# Schnittstellen der Website hr3000.de – Firmensuche, Adress-Prüfung, Registrierung (api/public.py).
_NO_TENANT_PATHS = frozenset(
    {
        "/health",
        "/internal/tls-allowed",
        "/public/tenant-lookup",
        "/public/subdomain-available",
        "/public/signup",
    }
)


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    """Ordnet jeden Request anhand des Host-Headers (Subdomain) genau einem
    Tenant zu, bevor irgendeine Route/Dependency läuft – siehe app/api/deps.py
    get_current_actor für die anschließende Prüfung, dass der authentifizierte
    Actor auch tatsächlich zu request.state.tenant gehört.

    request.state.tenant ist ein Tenant-Objekt, oder None auf dem
    Super-Admin-Hostname (settings.super_admin_hostname) – dort gibt es
    keinen Tenant-Kontext, nur der plattformweite Super-Admin darf dort
    agieren (siehe HrRole.SUPER_ADMIN)."""

    async def dispatch(self, request: Request, call_next):
        # /health wird von Load-Balancern/Uptime-Checks direkt über den
        # Server-Hostnamen abgefragt, nie über eine Mandanten-Subdomain –
        # braucht daher keine Tenant-Auflösung. Ebenso die Zertifikats-Freigabe,
        # die Caddy intern über backend:8000 abfragt (siehe app/api/tls.py).
        if request.url.path in _NO_TENANT_PATHS:
            return await call_next(request)

        host = (request.headers.get("host") or "").split(":")[0].lower()

        if host == settings.super_admin_hostname:
            request.state.tenant = None
            request.state.is_super_admin_host = True
            return await call_next(request)

        request.state.is_super_admin_host = False

        # Dev-Escape-Hatch: nur wenn debug=True, sonst wäre das ein
        # Tenant-Spoofing-Vektor in Produktion.
        subdomain: str | None = None
        if settings.debug:
            subdomain = request.headers.get("x-tenant-subdomain")
        if not subdomain and host:
            # Plattform-Domain: firma.hr3000.de / kiosk.firma.hr3000.de; sonst (fest
            # eingetragene Hosts) wie bisher der erste Hostname-Teil.
            subdomain = tenant_subdomain_for_host(host) or host.split(".")[0]

        tenant = await self._find_tenant(subdomain) if subdomain else None
        if tenant is None and settings.debug:
            tenant = await self._find_tenant(settings.dev_default_tenant_subdomain)

        if tenant is None:
            return JSONResponse(
                status_code=404,
                content={"detail": "Unbekannte Subdomain.", "code": "TENANT_NOT_FOUND"},
            )

        request.state.tenant = tenant
        return await call_next(request)

    @staticmethod
    async def _find_tenant(subdomain: str) -> Tenant | None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Tenant).where(
                    Tenant.subdomain == subdomain, Tenant.status != TenantStatus.SUSPENDED
                )
            )
            return result.scalar_one_or_none()
