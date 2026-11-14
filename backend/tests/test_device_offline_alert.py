"""Warnung an Admin/HR, wenn ein Tablet länger als eine Stunde offline ist (abschaltbar unter
Einstellungen → Kiosk): eine Warnung je Ausfall, nicht außerhalb der Bildschirmzeiten, nicht für Tablets,
die sich noch nie gemeldet haben."""
import asyncio
from datetime import datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.device_presence as presence
from app.models import Account, AppSettings, AuditLogEntry, Device, HrRole, Location, Notification, NotificationType, Tenant
from app.services.auth_service import hash_password
from app.services.device_presence import offline_alert_due, send_offline_alerts
from app.services.pairing_service import token_hash
from tests.test_device_pairing import _setup

NOON = datetime(2026, 11, 14, 12, 0, 0)


def _device(**overrides) -> Device:
    values = dict(
        name="Eingang", installation_hash="x" * 64, queued_punches=0, failed_punches=0,
        last_seen=NOON - timedelta(hours=2), offline_alerted_at=None, screen_hours_mode=None,
    )
    return Device(**(values | overrides))


def _hours(start: time | None = None, end: time | None = None) -> AppSettings:
    return AppSettings(kiosk_screen_on_from=start, kiosk_screen_on_until=end, device_offline_alert=True)


async def _alerts(db_session: AsyncSession) -> list[Notification]:
    rows = await db_session.execute(select(Notification).where(Notification.type == NotificationType.DEVICE_ALERT).order_by(Notification.id))
    return list(rows.scalars().all())


async def _bound_device(db_session: AsyncSession, client: AsyncClient, last_seen: datetime, **overrides):
    device, hr = await _setup(db_session, client)
    device.installation_hash = token_hash("tablet-a-0123456789")
    device.queued_punches = 0
    device.failed_punches = 0
    device.last_seen = last_seen
    for key, value in overrides.items():
        setattr(device, key, value)
    await db_session.commit()
    return device, hr


# --- Regel -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("minutes_ago", "due"),
    [(0, False), (15, False), (59, False), (60, True), (61, True), (24 * 60, True)],
)
def test_alert_after_one_hour_without_contact(minutes_ago: int, due: bool) -> None:
    device = _device(last_seen=NOON - timedelta(minutes=minutes_ago))
    assert offline_alert_due(_hours(), device, "Europe/Berlin", NOON) is due


def test_no_alert_for_entries_without_a_reporting_tablet() -> None:
    settings = _hours()
    assert offline_alert_due(settings, _device(installation_hash=None), "UTC", NOON) is False  # kein Gerät verbunden
    assert offline_alert_due(settings, _device(queued_punches=None), "UTC", NOON) is False  # Kiosk-App ohne Meldung
    assert offline_alert_due(settings, _device(last_seen=None), "UTC", NOON) is False  # nie gesehen


def test_one_alert_per_outage() -> None:
    settings = _hours()
    seen = NOON - timedelta(hours=3)
    # Schon gewarnt und seither nicht zurückgekommen: keine zweite Warnung
    assert offline_alert_due(settings, _device(last_seen=seen, offline_alerted_at=seen + timedelta(hours=1)), "UTC", NOON) is False
    # Nach der Warnung wieder gemeldet und erneut ausgefallen: neue Warnung
    back = NOON - timedelta(hours=1, minutes=5)
    assert offline_alert_due(settings, _device(last_seen=back, offline_alerted_at=back - timedelta(hours=4)), "UTC", NOON) is True


def test_no_alert_outside_screen_hours_or_before_the_tablet_woke_up() -> None:
    settings = _hours(time(6, 0), time(21, 0))  # Standort UTC
    evening = datetime(2026, 11, 14, 20, 50)
    # Nachts: Das Tablet schläft planmäßig
    assert offline_alert_due(settings, _device(last_seen=evening), "UTC", datetime(2026, 11, 14, 23, 0)) is False
    assert offline_alert_due(settings, _device(last_seen=evening), "UTC", datetime(2026, 11, 15, 5, 59)) is False
    # Morgens im Zeitfenster, aber heute noch nicht geweckt (letzte Meldung von gestern Abend): kein Ausfall
    assert offline_alert_due(settings, _device(last_seen=evening), "UTC", datetime(2026, 11, 15, 9, 0)) is False
    # Heute im Zeitfenster gemeldet und dann weg: Ausfall
    morning = datetime(2026, 11, 15, 6, 0)
    assert offline_alert_due(settings, _device(last_seen=morning), "UTC", datetime(2026, 11, 15, 7, 0)) is True
    assert offline_alert_due(settings, _device(last_seen=morning), "UTC", datetime(2026, 11, 15, 6, 59)) is False
    # Eigene Bildschirmzeiten des Tablets haben Vorrang
    always = _device(last_seen=evening, screen_hours_mode="ALWAYS")
    assert offline_alert_due(settings, always, "UTC", datetime(2026, 11, 14, 23, 0)) is True
    custom = _device(last_seen=evening, screen_hours_mode="CUSTOM", screen_on_from=time(20, 0), screen_on_until=time(4, 0))
    assert offline_alert_due(settings, custom, "UTC", datetime(2026, 11, 14, 23, 0)) is True
    assert offline_alert_due(settings, custom, "UTC", datetime(2026, 11, 15, 5, 0)) is False


def test_screen_hours_follow_the_location_time_zone() -> None:
    settings = _hours(time(6, 0), time(21, 0))
    seen = datetime(2026, 11, 14, 18, 30)  # 19:30 in Berlin
    now = datetime(2026, 11, 14, 20, 15)  # 21:15 in Berlin: Bildschirm aus; in UTC noch im Fenster
    assert offline_alert_due(settings, _device(last_seen=seen), "Europe/Berlin", now) is False
    assert offline_alert_due(settings, _device(last_seen=seen), "UTC", now) is True


# --- Versand -----------------------------------------------------------------------------------------


async def test_offline_tablet_is_reported_once_to_admin_and_hr(client: AsyncClient, db_session: AsyncSession) -> None:
    device, _ = await _bound_device(db_session, client, NOON - timedelta(hours=2), queued_punches=3)
    db_session.add(Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    db_session.add(Account(email="fk@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR))
    await db_session.commit()

    assert await send_offline_alerts(db_session, 1, NOON) == 1
    alerts = await _alerts(db_session)
    assert len(alerts) == 2  # HR und Admin, nicht die Führungskraft
    message = alerts[0].message
    assert "„Tablet“" in message and "„Zentrale“" in message
    assert "14.11.2026, 10:00 Uhr" in message  # Ortszeit des Standorts (UTC)
    assert "3 Stempelung(en)" in message
    await db_session.refresh(device)
    assert device.offline_alerted_at == NOON

    # Spätere Prüfungen warnen für denselben Ausfall nicht erneut
    assert await send_offline_alerts(db_session, 1, NOON + timedelta(minutes=5)) == 0
    assert await send_offline_alerts(db_session, 1, NOON + timedelta(hours=6)) == 0
    assert len(await _alerts(db_session)) == 2


async def test_message_uses_the_location_time_and_omits_an_empty_queue(client: AsyncClient, db_session: AsyncSession) -> None:
    device, _ = await _bound_device(db_session, client, NOON - timedelta(hours=2))
    location = await db_session.get(Location, device.location_id)
    location.timezone = "Europe/Berlin"
    await db_session.commit()
    assert await send_offline_alerts(db_session, 1, NOON) == 1
    message = (await _alerts(db_session))[0].message
    assert "14.11.2026, 11:00 Uhr" in message and "Stempelung(en)" not in message


async def test_tablet_that_came_back_is_reported_again_on_the_next_outage(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    device, _ = await _bound_device(db_session, client, NOON - timedelta(hours=2))
    assert await send_offline_alerts(db_session, 1, NOON) == 1

    # Das Tablet meldet sich wieder …
    back = NOON + timedelta(minutes=30)
    monkeypatch.setattr(presence, "_now", lambda: back)
    login = await client.post("/auth/device/login", json={"device_token": "long-device-token-123456", "installation_id": "tablet-a-0123456789"})
    tablet = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.post("/device/heartbeat", headers=tablet, json={})).status_code == 200
    assert await send_offline_alerts(db_session, 1, back + timedelta(minutes=59)) == 0
    # … und fällt wieder aus
    assert await send_offline_alerts(db_session, 1, back + timedelta(minutes=61)) == 1
    assert len(await _alerts(db_session)) == 2


async def test_switch_turns_the_alert_off(client: AsyncClient, db_session: AsyncSession) -> None:
    device, hr = await _bound_device(db_session, client, NOON - timedelta(hours=2))
    db_session.add(Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    admin = {"Authorization": f"Bearer {(await client.post('/auth/login', json={'email': 'admin@example.com', 'password': 'pw'})).json()['access_token']}"}

    current = await client.get("/settings", headers=admin)
    assert current.json()["device_offline_alert"] is True  # Standard: an

    off = await client.patch("/settings", headers=admin, json={"device_offline_alert": False})
    assert off.status_code == 200 and off.json()["device_offline_alert"] is False
    assert await send_offline_alerts(db_session, 1, NOON) == 0
    assert await _alerts(db_session) == []
    await db_session.refresh(device)
    assert device.offline_alerted_at is None  # nichts vermerkt: beim Einschalten wird der laufende Ausfall gemeldet

    on = await client.patch("/settings", headers=admin, json={"device_offline_alert": True})
    assert on.json()["device_offline_alert"] is True
    assert await send_offline_alerts(db_session, 1, NOON) == 1

    details = " ".join(
        entry.detail or "" for entry in (await db_session.execute(select(AuditLogEntry))).scalars().all()
    )
    assert "device_offline_alert" in details  # Änderung steht im Audit-Protokoll


async def test_switch_rejects_non_boolean_and_is_admin_only(client: AsyncClient, db_session: AsyncSession) -> None:
    _, hr = await _bound_device(db_session, client, NOON)
    db_session.add(Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    admin = {"Authorization": f"Bearer {(await client.post('/auth/login', json={'email': 'admin@example.com', 'password': 'pw'})).json()['access_token']}"}
    assert (await client.patch("/settings", headers=admin, json={"device_offline_alert": "vielleicht"})).status_code == 422
    assert (await client.patch("/settings", headers=hr, json={"device_offline_alert": False})).status_code == 403


async def test_only_the_affected_tablets_of_the_own_company_are_reported(client: AsyncClient, db_session: AsyncSession) -> None:
    device, _ = await _bound_device(db_session, client, NOON - timedelta(minutes=10))  # meldet sich: kein Ausfall
    other_location = Location(name="Lager", timezone="UTC")
    db_session.add(other_location)
    other = Tenant(name="Andere Firma", subdomain="andere")
    db_session.add(other)
    await db_session.commit()
    foreign_location = Location(name="Fremd", timezone="UTC", tenant_id=other.id)
    db_session.add(foreign_location)
    await db_session.commit()
    common = dict(installation_hash="y" * 64, queued_punches=0, failed_punches=0, last_seen=NOON - timedelta(hours=5))
    db_session.add_all(
        [
            Device(name="Lager-Tablet", location_id=other_location.id, token_hash=token_hash("lager-token-1234567890"), **common),
            Device(name="Vorbereitet", location_id=other_location.id, token_hash=token_hash("leer-token-1234567890")),
            Device(name="Fremdes Tablet", location_id=foreign_location.id, tenant_id=other.id, token_hash=token_hash("fremd-token-1234567890"), **common),
        ]
    )
    await db_session.commit()

    assert await send_offline_alerts(db_session, 1, NOON) == 1
    alerts = await _alerts(db_session)
    assert len(alerts) == 1 and "„Lager-Tablet“" in alerts[0].message and alerts[0].tenant_id == 1
    # Die andere Firma hat keine Empfänger, ihr Tablet wird aber als gemeldet vermerkt
    assert await send_offline_alerts(db_session, other.id, NOON) == 1
    assert len(await _alerts(db_session)) == 1


async def test_no_alert_at_night_with_screen_hours(client: AsyncClient, db_session: AsyncSession) -> None:
    await _bound_device(db_session, client, datetime(2026, 11, 14, 20, 55))
    settings_row = (await db_session.execute(select(AppSettings).where(AppSettings.tenant_id == 1))).scalar_one()
    settings_row.kiosk_screen_on_from, settings_row.kiosk_screen_on_until = time(6, 0), time(21, 0)
    await db_session.commit()
    assert await send_offline_alerts(db_session, 1, datetime(2026, 11, 14, 23, 30)) == 0
    assert await send_offline_alerts(db_session, 1, datetime(2026, 11, 15, 8, 0)) == 0  # morgens noch nicht geweckt
    assert await _alerts(db_session) == []


# --- Hintergrundschleife -----------------------------------------------------------------------------


async def test_background_loop_checks_every_company_and_survives_errors(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_session.add(Tenant(name="Andere Firma", subdomain="andere"))
    await db_session.commit()
    calls: list[int] = []
    sleeps: list[int] = []

    async def fake_alerts(db, tenant_id, now=None):
        calls.append(tenant_id)
        if len(calls) == 2:
            raise RuntimeError("Datenbank kurz weg")  # darf die Schleife nicht beenden
        return 0

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise asyncio.CancelledError  # Schleife nach dem zweiten Durchlauf beenden
        assert len(calls) == 2 * (len(sleeps) - 1)  # erst warten, dann prüfen – auch beim Start

    monkeypatch.setattr(presence, "send_offline_alerts", fake_alerts)
    monkeypatch.setattr(presence.asyncio, "sleep", fake_sleep)

    class Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *args):
            return False

    with pytest.raises(asyncio.CancelledError):
        await presence.run_offline_alerts(Factory(), 300)
    assert calls == [1, 2, 1, 2] and sleeps == [300, 300, 300]
