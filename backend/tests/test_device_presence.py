"""Live-Status der Tablets: Meldung der Kiosk-App (POST /device/heartbeat), Auskunft für die HR-Webapp
(GET /devices/presence), Takt (15 Min. im Ruhezustand, 15 s bei offener Seite) und Bildschirmzeiten."""
from datetime import UTC, datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.device_presence as presence
from app.models import Account, AppSettings, Device, HrRole, Location, Tenant
from app.services import presence_watch
from app.services.auth_service import hash_password
from app.services.device_presence import (
    CHECK_WINDOW,
    ONLINE_WINDOW,
    is_online,
    presence_state,
    screen_off,
    screen_on_since,
    within_screen_hours,
)
from app.services.pairing_service import token_hash
from app.services.presence_watch import IDLE_SECONDS, WATCH_SECONDS, WATCH_TTL
from tests.test_device_pairing import _setup

TOKEN = "long-device-token-123456"
TABLET = "tablet-a-0123456789"
NOON = datetime(2026, 11, 14, 12, 0, 0)


async def _device_headers(client: AsyncClient, token: str = TOKEN, installation: str = TABLET) -> dict[str, str]:
    login = await client.post("/auth/device/login", json={"device_token": token, "installation_id": installation})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _presence(client: AsyncClient, hr: dict[str, str]) -> dict:
    response = await client.get("/devices/presence", headers=hr)
    assert response.status_code == 200, response.text
    return response.json()


def _set_now(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    monkeypatch.setattr(presence, "_now", lambda: now)
    monkeypatch.setattr(presence_watch, "_now", lambda: now)


def test_constants_match_the_agreed_rhythm() -> None:
    """Johannes, 14.11.2026: alle 15 s nur bei offener Seite, sonst alle 15 Min."""
    assert (WATCH_SECONDS, IDLE_SECONDS) == (15, 900)
    assert ONLINE_WINDOW == timedelta(seconds=45)
    assert WATCH_TTL == timedelta(seconds=30) and CHECK_WINDOW == timedelta(seconds=75)
    assert presence.OFFLINE_ALERT_AFTER == timedelta(hours=1)


# --- Meldung der Kiosk-App ---------------------------------------------------------------------------


async def test_heartbeat_marks_tablet_online_with_queue_state(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)
    tablet = await _device_headers(client)

    response = await client.post("/device/heartbeat", headers=tablet, json={"queued_punches": 3, "failed_punches": 1})
    assert response.status_code == 200, response.text
    assert response.json() == {"interval_seconds": IDLE_SECONDS}  # niemand sieht zu: Ruhetakt

    body = await _presence(client, hr)
    assert body["heartbeat_seconds"] == WATCH_SECONDS
    assert body["online_window_seconds"] == 45
    assert len(body["devices"]) == 1
    row = body["devices"][0]
    assert row["device_id"] == device.id
    assert row["state"] == "ONLINE"
    assert row["queued_punches"] == 3 and row["failed_punches"] == 1
    assert row["last_seen"] is not None and row["screen_off"] is False


async def test_heartbeat_without_body_fields_means_empty_queue(client: AsyncClient, db_session: AsyncSession) -> None:
    _, hr = await _setup(db_session, client)
    tablet = await _device_headers(client)
    assert (await client.post("/device/heartbeat", headers=tablet, json={})).status_code == 200
    row = (await _presence(client, hr))["devices"][0]
    assert (row["queued_punches"], row["failed_punches"]) == (0, 0)


async def test_later_heartbeat_replaces_queue_state(client: AsyncClient, db_session: AsyncSession) -> None:
    _, hr = await _setup(db_session, client)
    tablet = await _device_headers(client)
    await client.post("/device/heartbeat", headers=tablet, json={"queued_punches": 5, "failed_punches": 2})
    await client.post("/device/heartbeat", headers=tablet, json={"queued_punches": 0, "failed_punches": 0})
    row = (await _presence(client, hr))["devices"][0]
    assert (row["queued_punches"], row["failed_punches"]) == (0, 0)


@pytest.mark.parametrize(
    "body",
    [
        {"queued_punches": -1},
        {"queued_punches": 100_001},
        {"queued_punches": 1, "failed_punches": -1},
        {"queued_punches": 1, "failed_punches": 2},  # mehr abgelehnt als wartend
        {"queued_punches": "viele"},
        {"queued_punches": 1.5},
        {"queued_punches": None},
        {"queued_punches": 1, "battery": 80},  # unbekannte Felder werden abgelehnt
    ],
)
async def test_heartbeat_rejects_invalid_values(client: AsyncClient, db_session: AsyncSession, body: dict) -> None:
    _, hr = await _setup(db_session, client)
    tablet = await _device_headers(client)
    response = await client.post("/device/heartbeat", headers=tablet, json=body)
    assert response.status_code == 422, response.text
    # Nichts gespeichert
    row = (await _presence(client, hr))["devices"][0]
    assert row["queued_punches"] is None and row["failed_punches"] is None


async def test_heartbeat_accepts_upper_bound(client: AsyncClient, db_session: AsyncSession) -> None:
    _, hr = await _setup(db_session, client)
    tablet = await _device_headers(client)
    body = {"queued_punches": 100_000, "failed_punches": 100_000}
    assert (await client.post("/device/heartbeat", headers=tablet, json=body)).status_code == 200
    assert (await _presence(client, hr))["devices"][0]["queued_punches"] == 100_000


async def test_heartbeat_requires_a_tablet_session(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)
    assert (await client.post("/device/heartbeat", json={})).status_code in (401, 403)
    assert (await client.post("/device/heartbeat", headers={"Authorization": "Bearer kaputt"}, json={})).status_code == 401
    # Ein HR-Konto ist kein Tablet
    as_hr = await client.post("/device/heartbeat", headers=hr, json={})
    assert as_hr.status_code == 403 and as_hr.json()["code"] == "DEVICE_REQUIRED"
    await db_session.refresh(device)
    assert device.last_seen is None and device.queued_punches is None


async def test_heartbeat_ends_after_unpairing(client: AsyncClient, db_session: AsyncSession) -> None:
    """„Kopplung aufheben“ beendet die Sitzung: Das alte Gerät kann sich nicht mehr online melden, und der
    Stand seiner Warteschlange verschwindet."""
    device, hr = await _setup(db_session, client)
    tablet = await _device_headers(client)
    assert (await client.post("/device/heartbeat", headers=tablet, json={"queued_punches": 2})).status_code == 200

    assert (await client.patch(f"/devices/{device.id}", headers=hr, json={"regenerate_token": True})).status_code == 200
    assert (await client.post("/device/heartbeat", headers=tablet, json={"queued_punches": 2})).status_code == 401
    row = (await _presence(client, hr))["devices"][0]
    assert row["queued_punches"] is None and row["failed_punches"] is None


async def test_pairing_another_tablet_clears_queue_state(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)
    tablet = await _device_headers(client)
    await client.post("/device/heartbeat", headers=tablet, json={"queued_punches": 4, "failed_punches": 4})
    code = (await client.post(f"/devices/{device.id}/pairing-code", headers=hr, json={"replace_bound": True})).json()["code"]
    assert (await client.post("/auth/device/pair", json={"code": code, "installation_id": "tablet-b-9876543210"})).status_code == 200
    row = (await _presence(client, hr))["devices"][0]
    assert row["queued_punches"] is None and row["failed_punches"] is None


# --- Takt: 15 Minuten im Ruhezustand, 15 Sekunden bei offener Seite -----------------------------------


async def test_tablets_report_fast_only_while_the_page_is_open(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, hr = await _setup(db_session, client)
    _set_now(monkeypatch, NOON)
    tablet = await _device_headers(client)

    async def interval() -> int:
        return (await client.post("/device/heartbeat", headers=tablet, json={})).json()["interval_seconds"]

    async def config_interval() -> int:
        return (await client.get("/device/config", headers=tablet)).json()["heartbeat_seconds"]

    # Niemand auf der Seite „Tablets“: Ruhetakt – in der Meldung wie in der Konfiguration
    assert await interval() == 900 and await config_interval() == 900

    # Seite geöffnet: schneller Takt, das Tablet erfährt es mit der nächsten Konfigurations-Abfrage
    await _presence(client, hr)
    assert await config_interval() == 15 and await interval() == 15

    # Solange die Webapp weiter abfragt (alle 5 s), bleibt es dabei
    _set_now(monkeypatch, NOON + timedelta(seconds=25))
    await _presence(client, hr)
    _set_now(monkeypatch, NOON + timedelta(seconds=50))
    assert await interval() == 15

    # Seite geschlossen: 30 s nach der letzten Abfrage wieder Ruhetakt
    _set_now(monkeypatch, NOON + timedelta(seconds=25) + WATCH_TTL)
    assert await interval() == 15  # Grenze zählt noch
    _set_now(monkeypatch, NOON + timedelta(seconds=26) + WATCH_TTL)
    assert await interval() == 900 and await config_interval() == 900


async def test_login_response_carries_the_heartbeat_interval(client: AsyncClient, db_session: AsyncSession) -> None:
    _, hr = await _setup(db_session, client)
    login = await client.post("/auth/device/login", json={"device_token": TOKEN, "installation_id": TABLET})
    assert login.json()["heartbeat_seconds"] == 900
    await _presence(client, hr)
    login = await client.post("/auth/device/login", json={"device_token": TOKEN, "installation_id": TABLET})
    assert login.json()["heartbeat_seconds"] == 15


async def test_watching_one_company_does_not_speed_up_another(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _setup(db_session, client)
    other = Tenant(name="Andere Firma", subdomain="andere")
    db_session.add(other)
    await db_session.commit()
    presence_watch.touch(other.id)
    tablet = await _device_headers(client)
    assert (await client.post("/device/heartbeat", headers=tablet, json={})).json()["interval_seconds"] == 900
    assert presence_watch.heartbeat_seconds(other.id) == 15


def test_watch_keeps_its_start_while_polled_and_restarts_after_a_gap() -> None:
    assert presence_watch.watching(7, NOON) is False
    assert presence_watch.touch(7, NOON) == NOON
    assert presence_watch.touch(7, NOON + timedelta(seconds=5)) == NOON  # durchgehend offen
    assert presence_watch.touch(7, NOON + timedelta(seconds=35)) == NOON  # 30 s nach der letzten Abfrage: gilt noch
    assert presence_watch.watching(7, NOON + timedelta(seconds=65)) is True
    assert presence_watch.watching(7, NOON + timedelta(seconds=66)) is False
    # Nach der Lücke beginnt eine neue Beobachtung
    later = NOON + timedelta(minutes=10)
    assert presence_watch.touch(7, later) == later
    presence_watch.clear_all()
    assert presence_watch.watching(7, later) is False


# --- Zustände ------------------------------------------------------------------------------------------


async def test_silent_tablet_is_checked_first_and_offline_after_the_check_window(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Beim Öffnen der Seite weiß der Server noch nichts Frisches: erst „wird abgefragt“, offline erst,
    wenn das Tablet auch nach 75 s nichts geschickt hat."""
    device, hr = await _setup(db_session, client)
    device.last_seen = NOON - timedelta(minutes=9)  # letzte Meldung im Ruhetakt
    device.queued_punches = 0
    await db_session.commit()

    _set_now(monkeypatch, NOON)
    body = await _presence(client, hr)
    assert body["devices"][0]["state"] == "CHECKING"
    assert body["checked_at"].startswith("2026-11-14T12:00:00") and body["watching_since"].startswith("2026-11-14T12:00:00")

    _set_now(monkeypatch, NOON + timedelta(seconds=25))
    assert (await _presence(client, hr))["devices"][0]["state"] == "CHECKING"
    _set_now(monkeypatch, NOON + timedelta(seconds=50))
    assert (await _presence(client, hr))["devices"][0]["state"] == "CHECKING"
    _set_now(monkeypatch, NOON + timedelta(seconds=74))
    assert (await _presence(client, hr))["devices"][0]["state"] == "CHECKING"
    _set_now(monkeypatch, NOON + timedelta(seconds=75))
    body = await _presence(client, hr)
    assert body["devices"][0]["state"] == "OFFLINE"
    assert body["watching_since"].startswith("2026-11-14T12:00:00")  # Seite war durchgehend offen
    assert body["devices"][0]["last_seen"].startswith("2026-11-14T11:51:00")


async def test_tablet_answers_and_later_drops_out(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    device, hr = await _setup(db_session, client)
    tablet = await _device_headers(client)
    device.last_seen = NOON  # die Anmeldung nimmt die echte Uhr
    await db_session.commit()
    _set_now(monkeypatch, NOON + timedelta(minutes=10))
    assert (await _presence(client, hr))["devices"][0]["state"] == "CHECKING"

    _set_now(monkeypatch, NOON + timedelta(minutes=10, seconds=20))
    await client.post("/device/heartbeat", headers=tablet, json={"queued_punches": 1})
    assert (await _presence(client, hr))["devices"][0]["state"] == "ONLINE"

    # Meldungen bleiben aus (WLAN weg): 45 s nach der letzten Meldung nicht mehr online. Offline heißt es
    # erst, wenn die Seite auch 75 s offen ist – bis dahin könnte das Tablet noch im Ruhetakt sein.
    for seconds, state in ((40, "ONLINE"), (65, "ONLINE"), (66, "CHECKING"), (75, "OFFLINE"), (100, "OFFLINE")):
        _set_now(monkeypatch, NOON + timedelta(minutes=10, seconds=seconds))
        # Die Webapp fragt in Wirklichkeit alle 5 s; hier genügt, dass die Beobachtung nicht abreißt
        presence_watch.touch(1, NOON + timedelta(minutes=10, seconds=seconds - 1))
        row = (await _presence(client, hr))["devices"][0]
        assert row["state"] == state, seconds
    # Der letzte Stand bleibt sichtbar
    assert row["last_seen"].startswith("2026-11-14T12:10:20") and row["queued_punches"] == 1


@pytest.mark.parametrize(
    ("seconds_ago", "watching_for", "state"),
    [
        (0, 0, "ONLINE"),
        (45, 0, "ONLINE"),
        (45, 500, "ONLINE"),
        (46, 0, "CHECKING"),
        (46, 74, "CHECKING"),
        (46, 75, "OFFLINE"),
        (3600, 300, "OFFLINE"),
    ],
)
def test_presence_state(seconds_ago: int, watching_for: int, state: str) -> None:
    device = Device(last_seen=NOON - timedelta(seconds=seconds_ago))
    assert presence_state(device, NOON - timedelta(seconds=watching_for), NOON) == state


def test_presence_state_of_a_tablet_never_seen() -> None:
    assert presence_state(Device(last_seen=None), NOON, NOON) == "CHECKING"
    assert presence_state(Device(last_seen=None), NOON - CHECK_WINDOW, NOON) == "OFFLINE"


async def test_never_seen_tablet_has_no_data(client: AsyncClient, db_session: AsyncSession) -> None:
    _, hr = await _setup(db_session, client)
    row = (await _presence(client, hr))["devices"][0]
    assert row == {
        "device_id": row["device_id"], "state": "CHECKING", "last_seen": None,
        "queued_punches": None, "failed_punches": None, "screen_off": False,
    }


async def test_login_alone_counts_as_contact(client: AsyncClient, db_session: AsyncSession) -> None:
    """Auch eine ältere Kiosk-Version ohne Meldung ist direkt nach der Anmeldung kurz online."""
    _, hr = await _setup(db_session, client)
    await _device_headers(client)
    row = (await _presence(client, hr))["devices"][0]
    assert row["state"] == "ONLINE" and row["queued_punches"] is None


def test_is_online_handles_timezone_aware_timestamps() -> None:
    """Die Anmeldung schreibt last_seen mit Zeitzone – der Vergleich darf daran nicht scheitern."""
    assert is_online(Device(last_seen=datetime(2026, 11, 14, 11, 59, 30, tzinfo=UTC)), NOON) is True
    assert is_online(Device(last_seen=datetime(2026, 11, 14, 11, 58, 0, tzinfo=UTC)), NOON) is False
    assert is_online(Device(last_seen=None), NOON) is False


# --- Mandanten, Rechte, mehrere Tablets --------------------------------------------------------------


async def test_presence_lists_all_tablets_sorted_by_name(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)  # „Tablet“
    second = Location(name="Lager", timezone="Europe/Berlin")
    db_session.add(second)
    await db_session.commit()
    db_session.add_all(
        [
            Device(name="Eingang", location_id=second.id, token_hash=token_hash("zweites-token-1234567890")),
            Device(name="Werkstatt", location_id=device.location_id, token_hash=token_hash("drittes-token-1234567890")),
        ]
    )
    await db_session.commit()
    await client.post("/device/heartbeat", headers=await _device_headers(client, "zweites-token-1234567890", "tablet-b-9876543210"), json={})

    rows = (await _presence(client, hr))["devices"]
    assert len(rows) == 3
    assert [row["state"] for row in rows] == ["ONLINE", "CHECKING", "CHECKING"]  # Eingang, Tablet, Werkstatt


async def test_presence_is_separated_by_tenant(client: AsyncClient, db_session: AsyncSession) -> None:
    _, hr = await _setup(db_session, client)
    other = Tenant(name="Andere Firma", subdomain="andere")
    db_session.add(other)
    await db_session.commit()
    location = Location(name="Fremd", timezone="UTC", tenant_id=other.id)
    db_session.add(location)
    await db_session.commit()
    db_session.add(
        Device(name="Fremdes Tablet", location_id=location.id, tenant_id=other.id, token_hash=token_hash("fremd-token-1234567890"),
               last_seen=datetime.now(UTC).replace(tzinfo=None), queued_punches=9)
    )
    await db_session.commit()

    rows = (await _presence(client, hr))["devices"]
    assert len(rows) == 1 and rows[0]["queued_punches"] is None
    assert presence_watch.watching(other.id) is False  # nur die eigene Firma wird beobachtet


async def test_presence_needs_hr_login(client: AsyncClient, db_session: AsyncSession) -> None:
    await _setup(db_session, client)
    assert (await client.get("/devices/presence")).status_code in (401, 403)
    # Ein Tablet darf den Stand der anderen Tablets nicht lesen
    tablet = await _device_headers(client)
    assert (await client.get("/devices/presence", headers=tablet)).status_code in (401, 403)
    assert presence_watch.watching(1) is False  # abgewiesene Abfragen beschleunigen nichts


async def test_presence_denied_for_supervisor(client: AsyncClient, db_session: AsyncSession) -> None:
    """Führungskräfte haben keinen vollen HR-Zugriff – Tablets verwalten nur Admin und HR."""
    await _setup(db_session, client)
    db_session.add(Account(email="fk@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR))
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "fk@example.com", "password": "pw"})).json()["access_token"]
    assert (await client.get("/devices/presence", headers={"Authorization": f"Bearer {token}"})).status_code == 403


async def test_presence_without_tablets(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _setup(db_session, client)
    assert (await client.delete(f"/devices/{device.id}", headers=hr)).status_code == 204
    assert (await _presence(client, hr))["devices"] == []


# --- Bildschirmzeiten --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "local", "expected"),
    [
        (None, None, time(3, 0), True),  # kein Fenster: immer an
        (time(6, 0), None, time(3, 0), True),
        (time(6, 0), time(6, 0), time(3, 0), True),  # gleich = immer an
        (time(6, 0), time(21, 0), time(5, 59), False),
        (time(6, 0), time(21, 0), time(6, 0), True),  # Beginn zählt
        (time(6, 0), time(21, 0), time(20, 59), True),
        (time(6, 0), time(21, 0), time(21, 0), False),  # Ende zählt nicht mehr
        (time(22, 0), time(6, 0), time(23, 30), True),  # über Mitternacht
        (time(22, 0), time(6, 0), time(5, 59), True),
        (time(22, 0), time(6, 0), time(6, 0), False),
        (time(22, 0), time(6, 0), time(12, 0), False),
    ],
)
def test_within_screen_hours(start: time | None, end: time | None, local: time, expected: bool) -> None:
    assert within_screen_hours(start, end, local) is expected


def test_screen_off_resolves_device_before_tenant_and_uses_location_time() -> None:
    tenant_hours = AppSettings(kiosk_screen_on_from=time(6, 0), kiosk_screen_on_until=time(21, 0))
    no_hours = AppSettings(kiosk_screen_on_from=None, kiosk_screen_on_until=None)
    night_utc = datetime(2026, 11, 14, 21, 30)  # 22:30 in Berlin, 21:30 in UTC
    noon_utc = datetime(2026, 11, 14, 11, 0)

    default = Device(screen_hours_mode=None)
    assert screen_off(tenant_hours, default, "Europe/Berlin", night_utc) is True
    assert screen_off(tenant_hours, default, "Europe/Berlin", noon_utc) is False
    assert screen_off(no_hours, default, "Europe/Berlin", night_utc) is False
    # Standort-Zeitzone zählt: 20:30 UTC ist in Berlin 21:30 (aus), in UTC noch im Fenster
    assert screen_off(tenant_hours, default, "Europe/Berlin", datetime(2026, 11, 14, 20, 30)) is True
    assert screen_off(tenant_hours, default, "UTC", datetime(2026, 11, 14, 20, 30)) is False

    always = Device(screen_hours_mode="ALWAYS")
    assert screen_off(tenant_hours, always, "Europe/Berlin", night_utc) is False

    custom = Device(screen_hours_mode="CUSTOM", screen_on_from=time(20, 0), screen_on_until=time(4, 0))
    assert screen_off(tenant_hours, custom, "Europe/Berlin", night_utc) is False  # eigenes Fenster über Mitternacht
    assert screen_off(tenant_hours, custom, "Europe/Berlin", noon_utc) is True

    # Unbekannte Zeitzone: Europe/Berlin statt Absturz
    assert screen_off(tenant_hours, default, "Mars/Olympus", night_utc) is True


def test_screen_on_since_gives_the_start_of_the_running_window() -> None:
    hours = AppSettings(kiosk_screen_on_from=time(6, 0), kiosk_screen_on_until=time(21, 0))
    default = Device(screen_hours_mode=None)
    # 11:00 UTC = 12:00 Berlin (Winterzeit): Fenster läuft seit 06:00 Berlin = 05:00 UTC
    assert screen_on_since(hours, default, "Europe/Berlin", datetime(2026, 11, 14, 11, 0)) == datetime(2026, 11, 14, 5, 0)
    # Sommerzeit: 06:00 Berlin = 04:00 UTC
    assert screen_on_since(hours, default, "Europe/Berlin", datetime(2026, 7, 14, 11, 0)) == datetime(2026, 7, 14, 4, 0)
    # Außerhalb des Fensters
    assert screen_on_since(hours, default, "Europe/Berlin", datetime(2026, 11, 14, 22, 0)) is None
    assert screen_on_since(hours, default, "Europe/Berlin", datetime(2026, 11, 14, 4, 59)) is None
    # Ohne Fenster: immer an
    assert screen_on_since(AppSettings(), default, "Europe/Berlin", NOON) == datetime.min
    assert screen_on_since(hours, Device(screen_hours_mode="ALWAYS"), "Europe/Berlin", NOON) == datetime.min
    # Über Mitternacht (22–06 Uhr, Standort UTC): um 02:00 läuft das Fenster seit gestern 22:00
    night = Device(screen_hours_mode="CUSTOM", screen_on_from=time(22, 0), screen_on_until=time(6, 0))
    assert screen_on_since(hours, night, "UTC", datetime(2026, 11, 14, 2, 0)) == datetime(2026, 11, 13, 22, 0)
    assert screen_on_since(hours, night, "UTC", datetime(2026, 11, 14, 23, 0)) == datetime(2026, 11, 14, 22, 0)
    assert screen_on_since(hours, night, "UTC", datetime(2026, 11, 14, 12, 0)) is None


async def test_presence_reports_screen_off_outside_screen_hours(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    device, hr = await _setup(db_session, client)  # Standort in UTC
    db_session.add(Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    admin_token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    patched = await client.patch(
        "/settings", headers={"Authorization": f"Bearer {admin_token}"},
        json={"kiosk_screen_on_from": "06:00", "kiosk_screen_on_until": "21:00"},
    )
    assert patched.status_code == 200, patched.text

    _set_now(monkeypatch, datetime(2026, 11, 14, 23, 0))
    assert (await _presence(client, hr))["devices"][0]["screen_off"] is True
    _set_now(monkeypatch, datetime(2026, 11, 14, 12, 0))
    assert (await _presence(client, hr))["devices"][0]["screen_off"] is False

    # Eigene Einstellung des Tablets „immer an“ hat Vorrang
    assert (await client.patch(f"/devices/{device.id}", headers=hr, json={"screen_hours_mode": "ALWAYS"})).status_code == 200
    _set_now(monkeypatch, datetime(2026, 11, 14, 23, 0))
    assert (await _presence(client, hr))["devices"][0]["screen_off"] is False
