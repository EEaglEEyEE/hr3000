"""``GET /metrics`` im Prometheus-Textformat – nur für den Monitoring-Agenten im Docker-Netz.

Schutz in drei Stufen:
1. Caddy beantwortet ``/metrics`` und ``/api/metrics`` auf allen Hosts mit 404 (Caddyfile).
2. Kommt eine Anfrage trotzdem über einen Proxy (``X-Forwarded-*``/``Forwarded`` gesetzt – Caddys
   ``reverse_proxy`` setzt sie immer), antwortet der Endpunkt mit 404.
3. Optional ``Authorization: Bearer <METRICS_TOKEN>``; leer = kein Token nötig.

Nicht im OpenAPI-Schema; ohne Mandanten-Kontext (``_NO_TENANT_PATHS`` in app/middleware/tenant.py).
"""

import hmac

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import metrics
from app.config import settings
from app.db import get_db
from app.services import monitoring

router = APIRouter(include_in_schema=False)

PATH = "/metrics"
PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "forwarded", "x-real-ip")


def came_through_proxy(request: Request) -> bool:
    return any(request.headers.get(name) for name in PROXY_HEADERS)


def token_ok(authorization: str | None, token: str | None) -> bool:
    """Ohne konfiguriertes Token ist jeder Abruf erlaubt; sonst Vergleich in konstanter Zeit."""
    if not token:
        return True
    expected = f"Bearer {token}".encode()
    return hmac.compare_digest((authorization or "").encode(), expected)


@router.get(PATH)
async def prometheus_metrics(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    if came_through_proxy(request):
        return Response(status_code=404)
    if not token_ok(request.headers.get("authorization"), settings.metrics_token):
        return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
    body = metrics.render(await monitoring.database_gauges(db))
    return PlainTextResponse(body, media_type=metrics.CONTENT_TYPE)
