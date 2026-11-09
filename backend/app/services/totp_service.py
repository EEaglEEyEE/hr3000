"""Zwei-Faktor-Anmeldung mit einer Authenticator-App (TOTP nach RFC 6238: HMAC-SHA1, 6 Ziffern,
30 Sekunden) – nur mit der Standardbibliothek, ohne Zusatzpaket.

Das Geheimnis liegt verschlüsselt am Konto (secret_box), Wiederherstellungscodes nur als SHA-256.
Ein Code gilt einmal: verify() liefert den Zeitschritt, der als totp_last_step gespeichert wird;
ältere oder gleiche Schritte werden abgelehnt (kein zweites Einlösen desselben Codes).
"""
import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1  # ein Zeitschritt vor/zurück (Uhren von Handy und Server weichen leicht ab)
RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # ohne leicht verwechselbare Zeichen
_clock = time.time  # in Tests ersetzbar


def new_secret() -> str:
    """160 Bit Zufall, Base32 ohne Auffüllzeichen (so erwarten es die Authenticator-Apps)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((_clock() if now is None else now) // STEP_SECONDS)


def code_at(secret: str, step: int) -> str:
    return _code(secret, step)


def verify(secret: str, code: str, last_step: int | None, now: float | None = None) -> int | None:
    """Zeitschritt des passenden Codes oder None (falsch, abgelaufen oder schon benutzt)."""
    code = re.sub(r"\s", "", code or "")
    if not re.fullmatch(rf"\d{{{DIGITS}}}", code):
        return None
    step = current_step(now)
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if last_step is not None and candidate <= last_step:
            continue
        if hmac.compare_digest(_code(secret, candidate), code):
            return candidate
    return None


def otpauth_uri(secret: str, account_label: str, issuer: str = "HR3000") -> str:
    """Inhalt des QR-Codes zum Einrichten in der Authenticator-App."""
    label = quote(f"{issuer}:{account_label}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP_SECONDS}"


def new_recovery_codes() -> list[str]:
    """Einmal-Codes für den Fall, dass das Handy fehlt (Format abcd-efgh)."""
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def normalize_recovery_code(code: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (code or "").lower())


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(normalize_recovery_code(code).encode("ascii", "ignore")).hexdigest()
