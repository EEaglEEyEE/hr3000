"""Webhooks: Ereignisse in die Ausgangswarteschlange schreiben und zustellen.

- `emit` schreibt je passendem Webhook eine Zustellung (ohne commit, gehört zur Transaktion der
  Änderung). Die Nutzlast enthält nur IDs und Status; Details holt der Empfänger über die API.
- `run_deliveries` (Hintergrundaufgabe in main.lifespan) stellt fällige Zustellungen zu: POST mit
  JSON, Kopfzeilen X-HR3000-Event/-Delivery/-Timestamp und X-HR3000-Signature
  (`sha256=` + HMAC-SHA256 über "<timestamp>.<body>" mit dem Secret des Webhooks).
  Fehlschläge: neuer Versuch nach 1, 5, 30 Minuten, 2 und 6 Stunden, danach FAILED.
- Schutz vor Anfragen ins interne Netz (SSRF): nur https, keine Weiterleitungen, und jede Adresse,
  auf die der Name auflöst, muss öffentlich sein.
"""
import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.errors import AppError
from app.models import Webhook, WebhookDelivery
from app.services.secret_box import decrypt_secret

logger = logging.getLogger(__name__)

BACKOFF = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2), timedelta(hours=6))
TIMEOUT_SECONDS = 10


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def validate_url(url: str) -> str:
    """Beim Anlegen: https, Hostname vorhanden, kein privater/lokaler IP-Literal."""
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise AppError(400, "WEBHOOK_URL_INVALID", "Bitte eine https-Adresse ohne Zugangsdaten angeben.")
    try:
        if not ipaddress.ip_address(parts.hostname).is_global:
            raise AppError(400, "WEBHOOK_URL_INVALID", "Interne Adressen sind nicht erlaubt.")
    except ValueError:
        if parts.hostname.lower() in ("localhost",) or parts.hostname.lower().endswith((".local", ".internal", ".localhost")):
            raise AppError(400, "WEBHOOK_URL_INVALID", "Interne Adressen sind nicht erlaubt.") from None
    return url.strip()


async def _resolves_publicly(host: str, port: int) -> bool:
    try:
        infos = await asyncio.get_running_loop().run_in_executor(None, socket.getaddrinfo, host, port)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos}
    return bool(addresses) and all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses)


def emit(db: AsyncSession, webhooks: list[Webhook], event: str, data: dict) -> None:
    """Zustellungen für ein Ereignis anlegen (webhooks: die aktiven der Firma, siehe active_webhooks)."""
    for webhook in webhooks:
        if event not in webhook.events.split(","):
            continue
        payload = {"event": event, "occurred_at": _now().isoformat() + "Z", "data": data}
        db.add(WebhookDelivery(
            tenant_id=webhook.tenant_id, webhook_id=webhook.id, event=event,
            payload=json.dumps(payload, ensure_ascii=False), status="PENDING", attempts=0, next_attempt_at=_now(),
        ))


async def active_webhooks(db: AsyncSession, tenant_id: int) -> list[Webhook]:
    return list(
        (await db.execute(select(Webhook).where(Webhook.tenant_id == tenant_id, Webhook.active.is_(True)))).scalars().all()
    )


async def emit_event(db: AsyncSession, tenant_id: int, event: str, data: dict) -> None:
    emit(db, await active_webhooks(db, tenant_id), event, data)


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


async def deliver(db: AsyncSession, delivery: WebhookDelivery, client: httpx.AsyncClient) -> None:
    webhook = await db.get(Webhook, delivery.webhook_id)
    delivery.attempts += 1
    error = None
    status = None
    if webhook is None or not webhook.active:
        delivery.status = "FAILED"
        delivery.last_error = "Webhook gelöscht oder pausiert"
        return
    parts = urlsplit(webhook.url)
    secret = decrypt_secret(webhook.secret) or ""
    if not await _resolves_publicly(parts.hostname or "", parts.port or 443):
        error = "Adresse nicht öffentlich erreichbar"
    else:
        body = delivery.payload.encode()
        timestamp = str(int(time.time()))
        try:
            response = await client.post(
                webhook.url, content=body, follow_redirects=False, timeout=TIMEOUT_SECONDS,
                headers={
                    "Content-Type": "application/json", "User-Agent": "HR3000-Webhooks/1",
                    "X-HR3000-Event": delivery.event, "X-HR3000-Delivery": str(delivery.id),
                    "X-HR3000-Timestamp": timestamp, "X-HR3000-Signature": sign(secret, timestamp, body),
                },
            )
            status = response.status_code
            if not 200 <= status < 300:
                error = f"Antwort {status}"
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}"
    delivery.response_status = status
    webhook.last_delivery_at = _now()
    if error is None:
        delivery.status = "SENT"
        delivery.last_error = None
        webhook.last_status = f"OK ({status})"
        return
    delivery.last_error = error[:300]
    webhook.last_status = f"Fehler: {error}"[:200]
    if delivery.attempts > len(BACKOFF):
        delivery.status = "FAILED"
    else:
        delivery.next_attempt_at = _now() + BACKOFF[delivery.attempts - 1]


async def deliver_due(db: AsyncSession, client: httpx.AsyncClient, limit: int = 50) -> int:
    rows = (
        await db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.status == "PENDING", WebhookDelivery.next_attempt_at <= _now())
            .order_by(WebhookDelivery.id)
            .limit(limit)
        )
    ).scalars().all()
    for row in rows:
        await deliver(db, row, client)
        await db.commit()
    return len(rows)


async def run_deliveries(session_factory: async_sessionmaker, interval_seconds: int) -> None:
    async with httpx.AsyncClient() as client:
        while True:
            try:
                async with session_factory() as db:
                    await deliver_due(db, client)
            except Exception:
                logger.exception("Webhooks konnten nicht zugestellt werden.")
            await asyncio.sleep(interval_seconds)
