"""Standort beim Stempeln im Web-Login (A18) – datenschutzarm.

Ablauf: Ist die Prüfung eingeschaltet, fragt der Browser die Position nur im Moment des Stempelns ab
und schickt sie mit ``POST /me/punches``. Der Server rechnet die Entfernung zu den Kreisen der Firma
aus und speichert an der Stempelung **nur das Ergebnis** (innerhalb/außerhalb/unbekannt und bei
„innerhalb“ den Standort). Die Koordinaten werden nirgends gespeichert, nicht protokolliert, nicht
ins Audit-Log geschrieben und nicht in Fehlermeldungen zurückgegeben (auch nicht in 422-Antworten,
siehe ``strip_position_inputs``).

Regeln:
- Es zählen **alle Standorte der Firma mit Kreis**, nicht nur der Standort des Mitarbeiters (wer an
  einem anderen Standort der Firma stempelt, ist „innerhalb“). Kreise anderer Firmen nie.
- Hat noch kein Standort der Firma einen Kreis, wird nicht geprüft (nichts gespeichert, auch im
  Modus „außerhalb nicht erlauben“ wird nichts abgelehnt) – sonst sperrte ein halb eingerichteter
  Schalter alle aus.
- Genauigkeit (Radius der Ungenauigkeit, den der Browser meldet): Für einen Kreis zählt der gemessene
  Punkt, wenn die Ungenauigkeit nicht größer als dessen Radius ist. Liegt die Position dann im Kreis
  (Entfernung ≤ Radius, auf cm gerundet), ist sie „innerhalb“. Ist die Ungenauigkeit größer, ist die
  Position für diesen Kreis nur dann eindeutig „außerhalb“, wenn selbst der nächstmögliche Punkt
  (Entfernung − Ungenauigkeit) noch außerhalb liegt. Sonst „unbekannt“.
- Ergebnis: innerhalb, sobald ein Kreis „innerhalb“ ergibt (bei mehreren der nächste); außerhalb,
  wenn alle Kreise eindeutig „außerhalb“ ergeben; sonst unbekannt. Ohne Position: unbekannt.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Location, Punch, PunchLocationCheck, PunchType

# Mittlerer Erdradius (IUGG) in Metern – für Kreise bis 5 km ist der Fehler der Kugelnäherung vernachlässigbar.
EARTH_RADIUS_M = 6_371_008.8
# Grenzen für Kreis und Genauigkeitsangabe (Pydantic-Schemas nutzen dieselben Werte).
MIN_RADIUS_M = 50
MAX_RADIUS_M = 5000
MAX_ACCURACY_M = 100_000

MODE_RECORD = "RECORD"
MODE_BLOCK = "BLOCK"

# Gründe hinter dem Ergebnis (für die Meldung im Modus „außerhalb nicht erlauben“)
REASON_INSIDE = "INSIDE"
REASON_OUTSIDE = "OUTSIDE"
REASON_NO_POSITION = "NO_POSITION"
REASON_INACCURATE = "INACCURATE"

_BLOCK_ERRORS = {
    REASON_NO_POSITION: (
        "PUNCH_LOCATION_REQUIRED",
        "Stempeln ist nur am Standort möglich. Bitte die Standortfreigabe im Browser erlauben und erneut stempeln.",
    ),
    REASON_INACCURATE: (
        "PUNCH_LOCATION_INACCURATE",
        "Der Standort ist zu ungenau, um ihn zu prüfen. Bitte kurz warten (z. B. GPS/WLAN einschalten) und erneut stempeln.",
    ),
    REASON_OUTSIDE: (
        "PUNCH_LOCATION_OUTSIDE",
        "Stempeln ist nur am Standort möglich – die aktuelle Position liegt außerhalb.",
    ),
}

LOCATION_CHECK_LABELS = {
    PunchLocationCheck.INSIDE: "innerhalb",
    PunchLocationCheck.OUTSIDE: "außerhalb",
    PunchLocationCheck.UNKNOWN: "Standort unbekannt",
}
_PUNCH_LABELS = {
    PunchType.COME: "Kommen",
    PunchType.GO: "Gehen",
    PunchType.BREAK_START: "Pause Start",
    PunchType.BREAK_END: "Pause Ende",
    PunchType.ERRAND_START: "Dienstgang Start",
    PunchType.ERRAND_END: "Dienstgang Ende",
}


class Position(Protocol):
    latitude: float
    longitude: float
    accuracy_m: float


@dataclass(frozen=True)
class Circle:
    location_id: int
    latitude: float
    longitude: float
    radius_m: int


@dataclass(frozen=True)
class CheckResult:
    result: PunchLocationCheck
    reason: str
    # Standort, in dessen Kreis gestempelt wurde (nur bei „innerhalb“)
    location_id: int | None = None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Großkreis-Entfernung zweier Punkte (Grad) in Metern."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def evaluate(position: Position | None, circles: list[Circle]) -> CheckResult:
    """Ordnet eine Position den Kreisen zu (Regeln siehe Modul-Docstring). Reine Funktion."""
    if position is None:
        return CheckResult(PunchLocationCheck.UNKNOWN, REASON_NO_POSITION)
    accuracy = position.accuracy_m
    best: tuple[float, int] | None = None
    undecided = False
    for circle in circles:
        distance = round(haversine_m(position.latitude, position.longitude, circle.latitude, circle.longitude), 2)
        precise_enough = accuracy <= circle.radius_m
        if precise_enough and distance <= circle.radius_m:
            if best is None or distance < best[0]:
                best = (distance, circle.location_id)
        elif precise_enough or distance - accuracy > circle.radius_m:
            continue  # eindeutig außerhalb dieses Kreises
        else:
            undecided = True
    if best is not None:
        return CheckResult(PunchLocationCheck.INSIDE, REASON_INSIDE, best[1])
    if undecided:
        return CheckResult(PunchLocationCheck.UNKNOWN, REASON_INACCURATE)
    return CheckResult(PunchLocationCheck.OUTSIDE, REASON_OUTSIDE)


async def tenant_circles(db: AsyncSession, tenant_id: int) -> list[Circle]:
    """Alle Standorte der Firma mit vollständigem Kreis."""
    rows = (
        await db.execute(
            select(Location).where(
                Location.tenant_id == tenant_id,
                Location.geo_latitude.is_not(None),
                Location.geo_longitude.is_not(None),
                Location.geo_radius_m.is_not(None),
            )
        )
    ).scalars()
    return [Circle(loc.id, loc.geo_latitude, loc.geo_longitude, loc.geo_radius_m) for loc in rows]


async def check_active(db: AsyncSession, settings_row, tenant_id: int) -> bool:
    """Prüfung eingeschaltet und mindestens ein Standort mit Kreis (sonst wird nicht geprüft)."""
    return bool(settings_row.punch_location_check_enabled) and bool(await tenant_circles(db, tenant_id))


async def check_own_punch(db: AsyncSession, settings_row, tenant_id: int, position: Position | None) -> CheckResult | None:
    """Prüft eine Stempelung im Web-Login. None = keine Prüfung (Schalter aus oder kein Kreis):
    Die Position wird dann nicht einmal ausgewertet und nichts gespeichert. Im Modus „außerhalb nicht
    erlauben“ wird außerhalb/unbekannt mit einer klaren Meldung abgelehnt (ohne Koordinaten)."""
    if not settings_row.punch_location_check_enabled:
        return None
    circles = await tenant_circles(db, tenant_id)
    if not circles:
        return None
    result = evaluate(position, circles)
    if settings_row.punch_location_mode == MODE_BLOCK and result.result != PunchLocationCheck.INSIDE:
        code, message = _BLOCK_ERRORS[result.reason]
        raise AppError(403, code, message)
    return result


def location_remarks(punches: list[Punch], tz: ZoneInfo) -> str:
    """Vermerk für den Monatsnachweis, z. B. "außerhalb: Kommen 08:02 · Standort unbekannt: Gehen 17:01".
    Leer, wenn keine Stempelung des Tages außerhalb oder mit unbekanntem Standort gebucht wurde."""
    parts: dict[PunchLocationCheck, list[str]] = {}
    for punch in punches:
        if punch.location_check in (PunchLocationCheck.OUTSIDE, PunchLocationCheck.UNKNOWN):
            local = punch.timestamp_utc.replace(tzinfo=UTC).astimezone(tz).strftime("%H:%M")
            parts.setdefault(punch.location_check, []).append(f"{_PUNCH_LABELS[punch.punch_type]} {local}")
    return " · ".join(
        f"{LOCATION_CHECK_LABELS[check]}: {', '.join(parts[check])}"
        for check in (PunchLocationCheck.OUTSIDE, PunchLocationCheck.UNKNOWN)
        if check in parts
    )


def strip_position_inputs(errors: list[dict]) -> list[dict]:
    """Validierungsfehler ohne die eingegebenen Werte der Position: Pydantic gibt sonst in 422-Antworten
    das „input“ zurück – Koordinaten sollen auch dort nicht auftauchen."""
    cleaned = []
    for error in errors:
        loc = error.get("loc") or ()
        if "position" in loc:
            error = {key: value for key, value in error.items() if key != "input"}
        cleaned.append(error)
    return cleaned
