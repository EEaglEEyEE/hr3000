import time
from collections import defaultdict, deque

from app.errors import AppError

# Einfacher In-Memory-Gleitfenster-Zähler (pro Prozess). Reicht für den
# Betrieb mit einem uvicorn-Worker hinter Caddy; bei mehreren Workern/Servern
# müsste der Zustand in Redis o.ä. wandern.
_failures: dict[str, deque[float]] = defaultdict(deque)
_MAX_KEYS = 20000


def _prune(key: str, window_seconds: int, now: float) -> deque[float]:
    events = _failures[key]
    while events and now - events[0] > window_seconds:
        events.popleft()
    return events


def check_rate_limit(key: str, limit: int, window_seconds: int, code: str = "TOO_MANY_ATTEMPTS") -> None:
    """Wirft 429, wenn für diesen Schlüssel schon `limit` Fehlversuche im
    Zeitfenster registriert sind."""
    now = time.monotonic()
    if len(_failures) > _MAX_KEYS:
        for stale in [k for k, v in _failures.items() if not v or now - v[-1] > window_seconds]:
            _failures.pop(stale, None)
    if len(_prune(key, window_seconds, now)) >= limit:
        raise AppError(429, code, "Zu viele Fehlversuche. Bitte später erneut versuchen.")


def record_failure(key: str) -> None:
    _failures[key].append(time.monotonic())


def reset(key: str) -> None:
    _failures.pop(key, None)


def clear_all() -> None:
    _failures.clear()
