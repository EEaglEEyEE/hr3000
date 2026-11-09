import hashlib
import secrets
from datetime import timedelta

# Ohne leicht verwechselbare Zeichen (0/O, 1/I/L)
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PAIRING_CODE_TTL = timedelta(minutes=15)


def new_pairing_code() -> str:
    """8 Zeichen (31^8 ≈ 8,5·10^11 Möglichkeiten), angezeigt als XXXX-XXXX."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def new_verify_code() -> str:
    """Prüfcode einer offenen Tablet-Registrierung (steht am Gerät und in der Webapp), z. B. K7Q-4XZ."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(6))
    return f"{raw[:3]}-{raw[3:]}"


def normalize_pairing_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def pairing_code_hash(code: str) -> str:
    return hashlib.sha256(normalize_pairing_code(code).encode()).hexdigest()


def token_hash(value: str) -> str:
    """SHA-256 (hex) für Geräte-Token und Installations-ID – gespeichert wird nur der Hash."""
    return hashlib.sha256(value.encode()).hexdigest()


def new_device_token() -> str:
    return secrets.token_urlsafe(24)


def card_salt(tenant_id: int) -> str:
    return f"hr3000-card:{tenant_id}:"


def card_hash(tenant_id: int, normalized_uid: str) -> str:
    """Chip-UID fürs Tablet nur als Hash – das Tablet vergleicht gescannte UIDs gehasht."""
    return hashlib.sha256(f"{card_salt(tenant_id)}{normalized_uid}".encode()).hexdigest()
