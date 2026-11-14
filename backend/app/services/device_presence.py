"""Live-Status der Tablets (HR-Webapp → „Tablets“) und Warnung bei längerem Ausfall.

Der Server kann ein Tablet nicht von sich aus erreichen – die Kiosk-App ist eine Webseite im Browser des
Tablets. Deshalb meldet sie sich selbst (POST /device/heartbeat), solange sie angemeldet ist:

- im Ruhezustand alle 15 Minuten (presence_watch.IDLE_SECONDS) – genug für die Warnung „länger als eine
  Stunde offline“;
- alle 15 Sekunden (WATCH_SECONDS), solange jemand die Seite „Tablets“ offen hat. Dass die Seite offen
  ist, erfährt das Tablet mit seiner nächsten Konfigurations-Abfrage (GET /device/config, alle 30 s) oder
  Meldung: Beide Antworten nennen den Abstand bis zur nächsten Meldung.

Zustand je Tablet, solange die Seite offen ist:
- ONLINE: letzte Meldung höchstens ONLINE_WINDOW alt – die Kiosk-App läuft, ist angemeldet und erreicht den
  Server, kann also Stempelungen liefern;
- CHECKING: noch keine frische Meldung, aber die Seite ist erst seit weniger als CHECK_WINDOW offen (das
  Tablet hat vom schnellen Takt vielleicht noch nichts erfahren);
- OFFLINE: auch danach keine Meldung.

Zeitpunkt und Warteschlange stehen in der Datenbank (devices.last_seen, queued_punches, failed_punches)."""
import asyncio
import logging
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import AppSettings, Device, Location, Tenant
from app.schemas.device import DevicePresence, DevicePresenceListResponse
from app.services import presence_watch
from app.services.notification_service import notify_device_offline
from app.services.presence_watch import WATCH_SECONDS
from app.services.settings_service import get_or_create_settings

logger = logging.getLogger(__name__)

# Letzte Meldung höchstens so alt = online (drei Abstände im schnellen Takt: zwei Meldungen dürfen ausfallen)
ONLINE_WINDOW = timedelta(seconds=3 * WATCH_SECONDS)
# So lange nach dem Öffnen der Seite gilt ein stilles Tablet als „wird abgefragt“ statt als offline:
# Konfigurations-Abfrage alle 30 s, während eines Stempelvorgangs (höchstens 30 s) pausiert, plus Laufzeit.
CHECK_WINDOW = timedelta(seconds=75)
# Warnung an Admin/HR, wenn ein Tablet so lange keine Meldung geschickt hat
OFFLINE_ALERT_AFTER = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _naive_utc(value: datetime | None) -> datetime | None:
    """Zeitstempel als naives UTC (die Anmeldung schreibt last_seen mit Zeitzone, die Spalte ist naiv)."""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def is_online(device: Device, now: datetime | None = None) -> bool:
    seen = _naive_utc(device.last_seen)
    return seen is not None and seen >= (now or _now()) - ONLINE_WINDOW


def presence_state(device: Device, watching_since: datetime, now: datetime) -> str:
    if is_online(device, now):
        return "ONLINE"
    return "CHECKING" if now - watching_since < CHECK_WINDOW else "OFFLINE"


async def record_heartbeat(db: AsyncSession, device: Device, queued_punches: int, failed_punches: int) -> int:
    """Meldung der Kiosk-App festhalten; committet. Gibt den Abstand bis zur nächsten Meldung zurück."""
    device.last_seen = _now()
    device.queued_punches = queued_punches
    device.failed_punches = failed_punches
    await db.commit()
    return presence_watch.heartbeat_seconds(device.tenant_id)


# --- Bildschirmzeiten ----------------------------------------------------------------------------------


def within_screen_hours(start: time | None, end: time | None, local: time) -> bool:
    """Liegt die Ortszeit im Bildschirm-Zeitfenster [start, end)? start > end = über Mitternacht. Ohne
    Fenster oder bei gleichem Beginn und Ende: immer an (wie kiosk-app/src/screenHours.ts)."""
    if start is None or end is None or start == end:
        return True
    return start <= local < end if start < end else local >= start or local < end


def _screen_window(settings_row: AppSettings, device: Device) -> tuple[time | None, time | None]:
    """Bildschirm-Zeitfenster des Tablets (Gerät vor Mandant); (None, None) = immer an."""
    if device.screen_hours_mode == "ALWAYS":
        return None, None
    if device.screen_hours_mode == "CUSTOM":
        start, end = device.screen_on_from, device.screen_on_until
    else:
        start, end = settings_row.kiosk_screen_on_from, settings_row.kiosk_screen_on_until
    if start is None or end is None or start == end:
        return None, None
    return start, end


def _zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Berlin")


def screen_off(settings_row: AppSettings, device: Device, timezone: str, now: datetime | None = None) -> bool:
    """Hält das Tablet seinen Bildschirm gerade planmäßig nicht wach? Dann schläft es meist und meldet
    sich nicht – „offline“ ist dann kein Störfall."""
    start, end = _screen_window(settings_row, device)
    local = (now or _now()).replace(tzinfo=UTC).astimezone(_zone(timezone)).time()
    return not within_screen_hours(start, end, local)


def screen_on_since(settings_row: AppSettings, device: Device, timezone: str, now: datetime) -> datetime | None:
    """Beginn des laufenden Bildschirm-Zeitfensters (naives UTC). None = gerade außerhalb des Fensters;
    datetime.min = ohne Fenster (immer an)."""
    start, end = _screen_window(settings_row, device)
    if start is None or end is None:
        return datetime.min
    zone = _zone(timezone)
    local_now = now.replace(tzinfo=UTC).astimezone(zone)
    if not within_screen_hours(start, end, local_now.time()):
        return None
    begin = local_now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    if begin > local_now:  # Fenster über Mitternacht: hat gestern begonnen
        begin -= timedelta(days=1)
    return begin.astimezone(UTC).replace(tzinfo=None)


# --- Auskunft für die HR-Webapp ------------------------------------------------------------------------


async def _devices_with_timezone(db: AsyncSession, tenant_id: int) -> list[tuple[Device, str, str]]:
    rows = (
        await db.execute(
            select(Device, Location.timezone, Location.name)
            .join(Location, Location.id == Device.location_id)
            .where(Device.tenant_id == tenant_id, Location.tenant_id == tenant_id)
            .order_by(Device.name.asc(), Device.id.asc())
        )
    ).all()
    return [(device, timezone, location_name) for device, timezone, location_name in rows]


async def tenant_presence(db: AsyncSession, tenant_id: int) -> DevicePresenceListResponse:
    """Aktueller Stand aller Tablets des Mandanten. Jede Abfrage hält den schnellen Takt der Tablets
    weitere presence_watch.WATCH_TTL aufrecht."""
    now = _now()
    watching_since = presence_watch.touch(tenant_id, now)
    settings_row = await get_or_create_settings(db, tenant_id)
    devices = [
        DevicePresence(
            device_id=device.id,
            state=presence_state(device, watching_since, now),
            last_seen=_naive_utc(device.last_seen),
            queued_punches=device.queued_punches,
            failed_punches=device.failed_punches,
            screen_off=screen_off(settings_row, device, timezone, now),
        )
        for device, timezone, _ in await _devices_with_timezone(db, tenant_id)
    ]
    return DevicePresenceListResponse(
        checked_at=now,
        watching_since=watching_since,
        heartbeat_seconds=WATCH_SECONDS,
        online_window_seconds=int(ONLINE_WINDOW.total_seconds()),
        devices=devices,
    )


# --- Warnung bei längerem Ausfall ----------------------------------------------------------------------


def offline_alert_due(settings_row: AppSettings, device: Device, timezone: str, now: datetime) -> bool:
    """Soll für dieses Tablet jetzt gewarnt werden? Ja, wenn

    - ein Gerät damit verbunden ist und die Kiosk-App sich schon einmal gemeldet hat (ältere Versionen
      ohne Meldung würden sonst nach jeder Anmeldung als ausgefallen gelten),
    - die letzte Meldung länger als OFFLINE_ALERT_AFTER zurückliegt,
    - das Tablet laut Bildschirmzeiten gerade wach sein soll und sich in diesem Zeitfenster schon gemeldet
      hat (nachts schläft es planmäßig; ein morgens noch nicht gewecktes Tablet ist kein Ausfall),
    - für diesen Ausfall noch nicht gewarnt wurde (eine Warnung je Ausfall, nicht jede Stunde eine)."""
    seen = _naive_utc(device.last_seen)
    if device.installation_hash is None or device.queued_punches is None or seen is None:
        return False
    if seen > now - OFFLINE_ALERT_AFTER:
        return False
    if device.offline_alerted_at is not None and device.offline_alerted_at >= seen:
        return False
    window_start = screen_on_since(settings_row, device, timezone, now)
    return window_start is not None and seen >= window_start


async def send_offline_alerts(db: AsyncSession, tenant_id: int, now: datetime | None = None) -> int:
    """Admin/HR warnen, wenn Tablets des Mandanten länger als eine Stunde offline sind. Nur mit
    AppSettings.device_offline_alert. Committet; gibt die Zahl der gemeldeten Tablets zurück."""
    now = now or _now()
    settings_row = await get_or_create_settings(db, tenant_id)
    if not settings_row.device_offline_alert:
        return 0
    count = 0
    for device, timezone, location_name in await _devices_with_timezone(db, tenant_id):
        if not offline_alert_due(settings_row, device, timezone, now):
            continue
        seen = _naive_utc(device.last_seen)
        local_seen = seen.replace(tzinfo=UTC).astimezone(_zone(timezone))
        await notify_device_offline(db, device, location_name, local_seen, device.queued_punches or 0)
        device.offline_alerted_at = now
        count += 1
    await db.commit()
    return count


async def run_offline_alerts(session_factory: async_sessionmaker, interval_seconds: int) -> None:
    """Hintergrundschleife (main.lifespan): prüft alle interval_seconds alle Mandanten. Die erste Prüfung
    kommt erst nach einem Abstand: Nach einem Neustart (oder längerem Stillstand des Servers) sollen sich
    die Tablets erst wieder melden können – sie versuchen es nach einem Fehler jede Minute."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with session_factory() as db:
                tenant_ids = (await db.execute(select(Tenant.id).order_by(Tenant.id))).scalars().all()
            for tenant_id in tenant_ids:
                async with session_factory() as db:
                    await send_offline_alerts(db, tenant_id)
        except Exception:
            logger.exception("Offline-Warnung für Tablets konnte nicht geprüft werden.")
