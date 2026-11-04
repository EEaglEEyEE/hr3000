"""E-Mail-Bestätigung bei der Selbstregistrierung (nur wenn Mailversand eingerichtet ist).

Der Link führt auf die Website (``https://<plattform-domain>/bestaetigen/#token=…``); die Seite
schickt das Token an ``POST /public/verify-email``. Wer sich vor der Bestätigung anmelden will,
bekommt den Link erneut (höchstens alle 10 Minuten).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountTokenPurpose, HrUser, Tenant
from app.services import rate_limiter
from app.services.account_tokens import EMAIL_VERIFY_TTL, issue_token
from app.services.email_service import resolve_smtp_config, send_email
from app.services.platform_domain import base_domain

_RESEND_WINDOW_SECONDS = 600


async def signup_verification_possible(db: AsyncSession, tenant_id: int | None = None) -> bool:
    return base_domain() is not None and await resolve_smtp_config(db, tenant_id) is not None


async def send_verification_mail(db: AsyncSession, tenant: Tenant, user: HrUser, contact_name: str | None = None) -> bool:
    """Neuen Bestätigungslink ausstellen und verschicken (committet das Token). False, wenn kein
    Mailversand eingerichtet ist oder der letzte Versand weniger als 10 Minuten her ist."""
    base = base_domain()
    config = await resolve_smtp_config(db, tenant.id)
    if base is None or config is None:
        return False
    key = f"verify-mail:{user.id}"
    try:
        rate_limiter.check_rate_limit(key, 1, _RESEND_WINDOW_SECONDS)
    except Exception:  # AppError 429 – bewusst still: nicht öfter als alle 10 Minuten
        return False
    raw = await issue_token(
        db, tenant_id=tenant.id, purpose=AccountTokenPurpose.EMAIL_VERIFY, ttl=EMAIL_VERIFY_TTL, hr_user=user
    )
    await db.commit()
    rate_limiter.record_failure(key)
    greeting = f"Hallo {contact_name}," if contact_name else "Hallo,"
    return await send_email(
        user.email,
        "HR3000 – bitte E-Mail-Adresse bestätigen",
        (
            f"{greeting}\n\n"
            f"danke für deine Registrierung von „{tenant.name}“ bei HR3000.\n"
            "Bitte bestätige deine E-Mail-Adresse mit diesem Link (7 Tage gültig):\n\n"
            f"https://{base}/bestaetigen/#token={raw}\n\n"
            f"Danach meldest du dich unter https://{tenant.subdomain}.{base}/ an.\n"
            "Ohne Bestätigung wird die Registrierung nach 7 Tagen automatisch gelöscht.\n\n"
            "Wenn du dich nicht registriert hast, kannst du diese E-Mail ignorieren.\n"
        ),
        config=config,
    )
