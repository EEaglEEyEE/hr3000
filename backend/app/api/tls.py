"""Freigabe für Caddys On-Demand-TLS (Caddyfile: ``on_demand_tls { ask ... }``).

Mandanten sind automatisch unter ``<subdomain>.<TENANT_BASE_DOMAIN>`` (HR-Webapp) und
``<subdomain>.kiosk.<TENANT_BASE_DOMAIN>`` (Kiosk) erreichbar, ohne dass jede Adresse
einzeln in der .env stehen muss. Caddy holt das Zertifikat erst beim ersten Aufruf und
fragt vorher hier nach (``?domain=...``): Nur bestehende, nicht gesperrte Mandanten und
der Super-Admin-Host bekommen 200. Sonst könnte jeder über beliebige Subdomains
Zertifikate anfordern lassen und das Let's-Encrypt-Kontingent der Domain aufbrauchen.

Nur für Caddy gedacht (direkt an backend:8000). Von außen blockt das Caddyfile
``/api/internal/*``; die Mandanten-Middleware lässt den Pfad ohne Mandanten-Kontext durch.
"""

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models import Tenant, TenantStatus
from app.services.platform_domain import tenant_subdomain_for_host

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


@router.get("/tls-allowed")
async def tls_allowed(
    domain: str = Query(min_length=1, max_length=253),
    db: AsyncSession = Depends(get_db),
) -> Response:
    host = domain.strip().lower().rstrip(".")
    if host == settings.super_admin_hostname.lower():
        return Response(status_code=200)
    staging = (settings.staging_base_domain or "").strip().lower().rstrip(".")
    if staging and host.endswith("." + staging):
        # Testumgebung: nur deren Backend kennt die dortigen Firmen (siehe scripts/staging.sh).
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                answer = await client.get(settings.staging_tls_ask_url, params={"domain": host})
            if answer.status_code == 200:
                return Response(status_code=200)
        except httpx.HTTPError:
            pass
    subdomain = tenant_subdomain_for_host(host)
    if subdomain is not None:
        tenant_id = await db.scalar(
            select(Tenant.id).where(
                Tenant.subdomain == subdomain, Tenant.status != TenantStatus.SUSPENDED
            )
        )
        if tenant_id is not None:
            return Response(status_code=200)
    return JSONResponse(
        status_code=404,
        content={"detail": "Für diese Adresse wird kein Zertifikat ausgestellt.", "code": "TLS_NOT_ALLOWED"},
    )
