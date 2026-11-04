import asyncio
import ipaddress
import logging
import smtplib
import socket
import ssl
from dataclasses import dataclass
from email.mime.text import MIMEText

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.secret_box import decrypt_secret
from app.services.settings_service import get_or_create_settings

logger = logging.getLogger(__name__)


@dataclass
class SmtpConfig:
    host: str
    port: int = 587
    user: str | None = None
    password: str | None = None
    from_address: str | None = None
    # NONE | STARTTLS | SSL
    security: str = "STARTTLS"
    # True bei vom Mandanten konfigurierten Servern: der Host muss beim Verbindungs-
    # aufbau selbst (nicht nur beim Speichern) auf eine öffentliche IP zeigen.
    enforce_public: bool = False


def platform_smtp_config() -> SmtpConfig | None:
    """Plattformweiter SMTP aus den Umgebungsvariablen (SMTP_HOST …) – gilt für
    Mandanten ohne eigenen Server und für Mails ohne Mandantenbezug (z.B.
    Zugangsdaten eines neu angelegten Mandanten)."""
    if not settings.smtp_host:
        return None
    return SmtpConfig(
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=settings.smtp_user,
        password=settings.smtp_password,
        from_address=settings.smtp_from,
        security="STARTTLS" if settings.smtp_use_tls else "NONE",
    )


def is_email_configured() -> bool:
    return platform_smtp_config() is not None


async def resolve_smtp_config(db: AsyncSession, tenant_id: int | None) -> SmtpConfig | None:
    """Eigener SMTP-Server des Mandanten, sonst der Plattform-SMTP, sonst None."""
    if tenant_id is not None:
        row = await get_or_create_settings(db, tenant_id)
        if row.smtp_host:
            password = decrypt_secret(row.smtp_password_encrypted) if row.smtp_password_encrypted else None
            return SmtpConfig(
                host=row.smtp_host,
                port=row.smtp_port,
                user=row.smtp_user,
                password=password,
                from_address=row.smtp_from,
                security=row.smtp_security,
                enforce_public=True,
            )
    return platform_smtp_config()


def _resolve_public_ip(host: str) -> str:
    """Löst den Host JETZT auf und liefert eine öffentliche IP. Alle Antworten
    müssen öffentlich sein (sonst ValueError) – verhindert, dass ein Host mit
    gemischten oder später umgebogenen DNS-Einträgen (DNS-Rebinding) ins interne
    Netz zeigt. Die Verbindung geht anschließend direkt auf diese IP."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Der Host konnte nicht aufgelöst werden.") from exc
    addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addresses or not all(address.is_global for address in addresses):
        raise ValueError("Der Host zeigt auf eine interne/nicht öffentliche Adresse und ist nicht erlaubt.")
    return str(addresses[0])


def _connect(config: SmtpConfig, pinned_ip: str | None, context: ssl.SSLContext) -> smtplib.SMTP:
    """Öffnet die SMTP-Verbindung. Mit pinned_ip wird direkt zu dieser (geprüften)
    IP verbunden, das TLS-Zertifikat aber gegen den Hostnamen validiert."""
    if pinned_ip is None:
        if config.security == "SSL":
            return smtplib.SMTP_SSL(config.host, config.port, timeout=10, context=context)
        return smtplib.SMTP(config.host, config.port, timeout=10)

    smtp = smtplib.SMTP(timeout=10)  # ohne Host: keine automatische Verbindung
    raw = socket.create_connection((pinned_ip, config.port), timeout=10)
    smtp.sock = context.wrap_socket(raw, server_hostname=config.host) if config.security == "SSL" else raw
    smtp.getreply()  # Begrüßung lesen
    smtp._host = config.host  # für die Hostnamen-Prüfung bei STARTTLS
    return smtp


def _send_sync(config: SmtpConfig, to: str, subject: str, body: str) -> None:
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = config.from_address or config.user or "noreply@hr3000.local"
    message["To"] = to

    # Zertifikat und Hostname werden immer geprüft (smtplib würde sonst einen
    # ungeprüften Standard-Kontext verwenden).
    context = ssl.create_default_context()
    pinned_ip = _resolve_public_ip(config.host) if config.enforce_public else None
    with _connect(config, pinned_ip, context) as server:
        if config.security == "STARTTLS":
            server.starttls(context=context)
        if config.user:
            server.login(config.user, config.password or "")
        server.send_message(message)


def describe_smtp_error(exc: Exception) -> str:
    """Kurze, bewusst allgemeine Fehlerbeschreibung für die Oberfläche – Details
    (Banner, Serverantworten) stehen nur im Log und dienen nicht als Orakel, um
    interne Dienste auszuhorchen."""
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "Die Anmeldung am SMTP-Server ist fehlgeschlagen (Benutzername/Passwort prüfen)."
    if isinstance(exc, ssl.SSLError):
        return "Die TLS-Verbindung oder das Zertifikat des SMTP-Servers konnte nicht geprüft werden."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "Der Server hat die Empfängeradresse abgelehnt."
    if isinstance(exc, (OSError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return "Die Verbindung zum SMTP-Server ist fehlgeschlagen (Host, Port und Verschlüsselung prüfen)."
    return "Der E-Mail-Versand ist fehlgeschlagen."


async def send_email(
    to: str,
    subject: str,
    body: str,
    config: SmtpConfig | None = None,
    raise_errors: bool = False,
) -> bool:
    """E-Mail-Versand über den übergebenen SMTP (sonst den Plattform-SMTP).

    Standard ist best effort: ohne SMTP-Konfiguration wird nur geloggt, ein
    Fehler beim Versand ebenfalls – der aufrufende Vorgang (Urlaubsentscheidung,
    Digest, ...) wird nie blockiert. Mit raise_errors=True (Testmail, explizit
    angeforderter Versand von Zugangsdaten) wird der Fehler dagegen
    weitergereicht, damit die Oberfläche ihn anzeigen kann. Rückgabe: ob
    tatsächlich versendet wurde."""
    config = config or platform_smtp_config()
    if config is None:
        logger.info("E-Mail nicht versendet (kein SMTP konfiguriert): an=%s betreff=%s", to, subject)
        return False
    try:
        await asyncio.to_thread(_send_sync, config, to, subject, body)
        return True
    except Exception:
        logger.exception("E-Mail-Versand fehlgeschlagen: an=%s betreff=%s", to, subject)
        if raise_errors:
            raise
        return False


async def ensure_public_smtp_host(host: str) -> None:
    """Frühe Prüfung beim Speichern bzw. Testen (Rückmeldung an den Admin). Die
    maßgebliche Prüfung passiert beim Verbindungsaufbau selbst, siehe
    _resolve_public_ip. Wirft ValueError mit Meldung für die Oberfläche."""
    await asyncio.to_thread(_resolve_public_ip, host)
