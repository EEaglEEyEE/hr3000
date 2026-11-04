import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import settings
from app.errors import AppError


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:  # bcrypt-Grenze: kann nie passen, nicht mit einer Exception antworten
        return False
    return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))


def password_fingerprint(password_hash: str | None) -> str:
    """Kurzer Fingerabdruck des aktuellen Passwort-Hashes. Steckt als "pwv"-Claim
    in jedem Token: ändert oder setzt jemand das Passwort zurück, passen alle
    bisher ausgestellten Tokens nicht mehr – bestehende Sitzungen enden sofort."""
    return hashlib.sha256((password_hash or "").encode("utf-8")).hexdigest()[:16]


def generate_one_time_password() -> str:
    """Für Konten, die ohne Self-Signup durch einen Admin angelegt/zurückgesetzt
    werden (Mandanten-Erst-Admin, Passwort-Reset) – wird dem anlegenden Admin
    genau einmal angezeigt, nirgends im Klartext gespeichert."""
    return secrets.token_urlsafe(18)


def create_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict = {"sub": subject, "type": token_type, "iat": now, "exp": now + expires_delta}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AppError(401, "TOKEN_EXPIRED", "Token abgelaufen.") from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(401, "TOKEN_INVALID", "Ungültiges Token.") from exc
