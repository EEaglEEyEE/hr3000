"""Wer sieht gerade auf die Seite „Tablets“? Solange die HR-Webapp den Live-Status abfragt, melden sich
die Tablets dieses Mandanten im schnellen Takt, sonst nur selten (siehe device_presence).

Bewusst nur im Speicher des Prozesses: Das Backend läuft als ein Uvicorn-Prozess, und der Stand heilt
sich selbst – nach einem Neustart setzt ihn die nächste Abfrage der Webapp (alle paar Sekunden) neu.
Mit mehreren Prozessen müsste er in die Datenbank oder einen gemeinsamen Speicher.

Eigenes Modul ohne weitere Abhängigkeiten, weil settings_service (Kiosk-Konfiguration) und
device_presence es beide brauchen."""
from datetime import UTC, datetime, timedelta

# Abstand der Meldungen ohne Zuschauer bzw. solange jemand die Seite „Tablets“ offen hat
IDLE_SECONDS = 900
WATCH_SECONDS = 15
# So lange nach der letzten Abfrage der Webapp gilt die Seite noch als offen (sie fragt alle 5 s)
WATCH_TTL = timedelta(seconds=30)

# tenant_id -> (offen seit, gilt bis)
_watches: dict[int, tuple[datetime, datetime]] = {}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def touch(tenant_id: int, now: datetime | None = None) -> datetime:
    """Die Webapp hat den Live-Status abgefragt. Gibt zurück, seit wann die Seite durchgehend offen ist."""
    now = now or _now()
    current = _watches.get(tenant_id)
    since = current[0] if current is not None and current[1] >= now else now
    _watches[tenant_id] = (since, now + WATCH_TTL)
    return since


def watching(tenant_id: int, now: datetime | None = None) -> bool:
    current = _watches.get(tenant_id)
    if current is None:
        return False
    if current[1] < (now or _now()):
        _watches.pop(tenant_id, None)
        return False
    return True


def heartbeat_seconds(tenant_id: int, now: datetime | None = None) -> int:
    """So viele Sekunden soll ein Tablet dieses Mandanten bis zur nächsten Meldung warten."""
    return WATCH_SECONDS if watching(tenant_id, now) else IDLE_SECONDS


def clear_all() -> None:
    _watches.clear()
