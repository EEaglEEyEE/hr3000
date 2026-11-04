from typing import Annotated

from pydantic import AfterValidator, Field


def _bcrypt_limit(value: str) -> str:
    # bcrypt verarbeitet maximal 72 Byte – längere Eingaben würden abgeschnitten (bzw. scheitern).
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Das Passwort darf höchstens 72 Byte lang sein.")
    return value


# Für neu gesetzte Passwörter (nicht für Logins – dort würde eine Richtlinie nur Hinweise geben).
NewPassword = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(_bcrypt_limit)]


def normalize_card_uid(value: str | None) -> str | None:
    """Karten-/Chipnummer vereinheitlichen: Web-NFC liefert "04:a2:3b:…", USB-Leser oft "04A23B…"
    – Trennzeichen und Groß-/Kleinschreibung spielen für den Abgleich keine Rolle."""
    if value is None:
        return None
    cleaned = "".join(ch for ch in value.strip().lower() if ch not in ": -")
    return cleaned
