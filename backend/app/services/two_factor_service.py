"""Zwei-Faktor-Anmeldung am Konto: Pflicht je Firma, Zwischenschritt beim Login, Prüfen von Codes.

Ablauf beim Login (api/auth.py): Passwort richtig und 2FA eingeschaltet → statt Tokens ein kurzes
„Challenge“-Token (10 Minuten), mit dem POST /auth/login/2fa den Code prüft. Ist 2FA Pflicht und
noch nicht eingerichtet, dient das Challenge-Token (Zweck „setup“) nur zum Einrichten
(POST /auth/2fa/setup und /enable) – erst danach gibt es Tokens.
"""
import json
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Account
from app.services import rate_limiter, totp_service
from app.services.auth_service import account_can_sign_in, create_token, decode_token, session_fingerprint
from app.services.secret_box import decrypt_secret, encrypt_secret
from app.services.settings_service import get_or_create_settings

CHALLENGE_TTL = timedelta(minutes=10)
_CODE_LIMIT = 5  # Fehlversuche je Konto
_CODE_WINDOW = 15 * 60


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def required_for(roles: str | None, account: Account) -> bool:
    """Gilt die Pflicht (AppSettings.two_factor_roles) für dieses Konto? Konten mit Rolle zählen nach
    ihrer Rolle, Konten ohne Rolle als EMPLOYEE."""
    group = account.role.value if account.role is not None else "EMPLOYEE"
    return group in {r for r in (roles or "").split(",") if r}


async def two_factor_required(db: AsyncSession, account: Account) -> bool:
    """Pflicht je Gruppe, wenn die Firma es eingestellt hat (Super-Admin: freiwillig)."""
    if account.tenant_id is None:
        return False
    return required_for((await get_or_create_settings(db, account.tenant_id)).two_factor_roles, account)


def create_challenge(account: Account, purpose: str) -> str:
    return create_token(
        subject=str(account.id),
        token_type="2fa_challenge",
        expires_delta=CHALLENGE_TTL,
        extra_claims={"purpose": purpose, "pwv": session_fingerprint(account), "tenant_id": account.tenant_id},
    )


async def read_challenge(db: AsyncSession, request: Request, token: str, purpose: str) -> Account:
    claims = decode_token(token)
    if claims.get("type") != "2fa_challenge" or claims.get("purpose") != purpose:
        raise AppError(401, "TOKEN_INVALID", "Die Anmeldung ist abgelaufen. Bitte melde dich neu an.")
    account = await db.get(Account, int(claims["sub"]))
    if account is None or not account_can_sign_in(account) or claims.get("pwv") != session_fingerprint(account):
        raise AppError(401, "TOKEN_INVALID", "Die Anmeldung ist abgelaufen. Bitte melde dich neu an.")
    if account.tenant_id is None:
        host_ok = getattr(request.state, "is_super_admin_host", False)
    else:
        tenant = getattr(request.state, "tenant", None)
        host_ok = tenant is not None and tenant.id == account.tenant_id
    if not host_ok:
        raise AppError(401, "TOKEN_INVALID", "Die Anmeldung ist abgelaufen. Bitte melde dich neu an.")
    return account


def _secret(account: Account) -> str:
    secret = decrypt_secret(account.totp_secret) if account.totp_secret else None
    if secret is None:
        raise AppError(400, "TWO_FACTOR_NOT_SET_UP", "Die Zwei-Faktor-Anmeldung ist nicht eingerichtet.")
    return secret


def start_setup(account: Account) -> tuple[str, str]:
    """Neues Geheimnis (noch nicht aktiv). Gibt (Geheimnis, otpauth-URI für den QR-Code) zurück."""
    if account.totp_enabled_at is not None:
        raise AppError(409, "TWO_FACTOR_ALREADY_ENABLED", "Die Zwei-Faktor-Anmeldung ist bereits eingerichtet.")
    secret = totp_service.new_secret()
    account.totp_secret = encrypt_secret(secret)
    return secret, totp_service.otpauth_uri(secret, account.email or f"Konto {account.id}")


def finish_setup(account: Account, code: str) -> list[str]:
    """Code aus der App bestätigt die Einrichtung; gibt die Wiederherstellungscodes (nur jetzt) zurück."""
    if account.totp_enabled_at is not None:
        raise AppError(409, "TWO_FACTOR_ALREADY_ENABLED", "Die Zwei-Faktor-Anmeldung ist bereits eingerichtet.")
    _check_rate(account)
    step = totp_service.verify(_secret(account), code, None)
    if step is None:
        _failed(account)
    codes = totp_service.new_recovery_codes()
    account.totp_enabled_at = _now()
    account.totp_last_step = step
    account.totp_recovery_hashes = json.dumps([totp_service.hash_recovery_code(c) for c in codes])
    rate_limiter.reset(_rate_key(account))
    return codes


def verify_code(account: Account, code: str) -> bool:
    """Code aus der App oder ein Wiederherstellungscode (wird dabei verbraucht). True = Wiederherstellungscode."""
    _check_rate(account)
    if account.totp_enabled_at is None:
        raise AppError(400, "TWO_FACTOR_NOT_SET_UP", "Die Zwei-Faktor-Anmeldung ist nicht eingerichtet.")
    step = totp_service.verify(_secret(account), code, account.totp_last_step)
    if step is not None:
        account.totp_last_step = step
        rate_limiter.reset(_rate_key(account))
        return False
    hashes = json.loads(account.totp_recovery_hashes or "[]")
    digest = totp_service.hash_recovery_code(code)
    if len(totp_service.normalize_recovery_code(code)) == 8 and digest in hashes:
        hashes.remove(digest)
        account.totp_recovery_hashes = json.dumps(hashes)
        rate_limiter.reset(_rate_key(account))
        return True
    _failed(account)
    return False  # nicht erreicht


def disable(account: Account) -> None:
    account.totp_secret = None
    account.totp_enabled_at = None
    account.totp_last_step = None
    account.totp_recovery_hashes = None


def recovery_codes_left(account: Account) -> int:
    return len(json.loads(account.totp_recovery_hashes or "[]")) if account.totp_enabled_at else 0


def _rate_key(account: Account) -> str:
    return f"2fa:{account.id}"


def _check_rate(account: Account) -> None:
    rate_limiter.check_rate_limit(_rate_key(account), _CODE_LIMIT, _CODE_WINDOW)


def _failed(account: Account) -> None:
    rate_limiter.record_failure(_rate_key(account))
    raise AppError(400, "TWO_FACTOR_CODE_INVALID", "Der Code stimmt nicht. Bitte den aktuellen Code aus der App eingeben.")
