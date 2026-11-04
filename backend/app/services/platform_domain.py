"""Plattform-Domain (TENANT_BASE_DOMAIN, z.B. "hr3000.de"): Mandanten sind darunter
automatisch als ``<subdomain>.<domain>`` (HR-Webapp) und ``kiosk.<subdomain>.<domain>``
(Kiosk) erreichbar – siehe Caddyfile und app/api/tls.py. Ein DNS-Wildcard-Eintrag "*"
deckt beide Ebenen ab.

Außerhalb der Plattform-Domain (fest eingetragene Hosts wie lassner.hr.lassners.de und
lassner.kiosk.hr.lassners.de) bleibt es beim alten Schema: erster Hostname-Teil = Mandant."""

import re

from app.config import settings

# Ein DNS-Label wie im Subdomain-Schema des Mandanten (schemas/tenant.py).
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
KIOSK_PREFIX = "kiosk."


def base_domain() -> str | None:
    """Plattform-Domain in Normalform (klein, ohne abschließenden Punkt) oder None."""
    value = (settings.tenant_base_domain or "").strip().lower().rstrip(".")
    return value or None


def tenant_subdomain_for_host(host: str) -> str | None:
    """``firma.<domain>`` bzw. ``kiosk.firma.<domain>`` -> ``firma``; alles andere -> None
    (auch tiefer verschachtelte Namen, fremde Domains und Hosts ohne Plattform-Domain)."""
    base = base_domain()
    if not base:
        return None
    match = re.fullmatch(rf"(?:kiosk\.)?({_LABEL})\.{re.escape(base)}", host)
    return match.group(1) if match else None


def kiosk_url_for_host(host: str, scheme: str = "https") -> str | None:
    """Kiosk-Adresse zur aktuellen HR-Webapp-Adresse (für den QR-Code beim Einrichten):
    ``firma.hr3000.de`` -> ``https://kiosk.firma.hr3000.de/``; feste Hosts nach altem Schema
    ``lassner.hr.lassners.de`` -> ``https://lassner.kiosk.hr.lassners.de/``. None, wenn sich
    keine sinnvolle Adresse ableiten lässt (z.B. localhost) – dann nur das Token kodieren."""
    host = host.split(":")[0].strip().lower().rstrip(".")
    subdomain = tenant_subdomain_for_host(host)
    if subdomain is not None:
        return f"https://{KIOSK_PREFIX}{subdomain}.{base_domain()}/"
    labels = host.split(".")
    if len(labels) < 3:
        return None
    return f"{scheme}://{labels[0]}.kiosk.{'.'.join(labels[1:])}/"
