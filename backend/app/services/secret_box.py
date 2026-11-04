import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    if settings.encryption_key:
        return Fernet(settings.encryption_key.encode("utf-8"))
    # Fallback: stabil aus dem JWT-Secret abgeleitet, damit es ohne zusätzliche
    # Konfiguration funktioniert (siehe Hinweis an Settings.encryption_key).
    digest = hashlib.sha256(("hr3000-secret-box:" + settings.jwt_secret_key).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes | None:
    try:
        return _fernet().decrypt(token)
    except InvalidToken:
        return None


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str | None:
    """None, wenn der Wert nicht (mehr) entschlüsselbar ist (z.B. Schlüssel
    gewechselt) – der Aufrufer behandelt das wie "kein Passwort hinterlegt"."""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
