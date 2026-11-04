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


def normalize_pairing_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def pairing_code_hash(code: str) -> str:
    return hashlib.sha256(normalize_pairing_code(code).encode()).hexdigest()
