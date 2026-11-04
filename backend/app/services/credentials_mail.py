from fastapi import Request

from app.services.email_service import SmtpConfig, send_email
from app.services.platform_domain import base_domain


def login_url(request: Request, subdomain: str | None = None) -> str:
    """Adresse der Anmeldeseite. Mit subdomain und gesetzter Plattform-Domain
    (TENANT_BASE_DOMAIN) immer https://<subdomain>.<domain>; ohne Plattform-Domain
    wird der erste Hostname-Teil der aktuellen Adresse (z.B. "admin" beim
    Super-Admin) durch die Mandanten-Subdomain ersetzt. Ohne subdomain gilt die
    aktuelle Adresse unverändert."""
    base = base_domain()
    if subdomain and base:
        return f"https://{subdomain}.{base}"
    host = request.headers.get("host") or request.url.netloc
    if subdomain:
        labels = host.split(".")
        host = ".".join([subdomain, *labels[1:]]) if len(labels) > 1 else host
    return f"{request.url.scheme}://{host}"


async def send_credentials_email(
    to: str,
    organisation: str,
    url: str,
    login_email: str,
    password: str,
    config: SmtpConfig | None = None,
    raise_errors: bool = False,
) -> bool:
    body = (
        f"Hallo,\n\n"
        f"für {organisation} wurde ein Zugang zu HR3000 eingerichtet bzw. das Passwort zurückgesetzt.\n\n"
        f"Anmeldung:      {url}\n"
        f"Benutzer:       {login_email}\n"
        f"Einmalpasswort: {password}\n\n"
        f"Bitte bewahre die Zugangsdaten sicher auf und gib sie nicht weiter. "
        f"Wenn du diese Nachricht nicht erwartet hast, wende dich bitte an deinen Administrator.\n"
    )
    return await send_email(
        to, "HR3000 – deine Zugangsdaten", body, config=config, raise_errors=raise_errors
    )
