"""Freigabeliste der Tablets (Verteilung per MDM): Herkunft der Anfrage, „wartet gerade“ gegenüber
„meldet sich nicht mehr“, Verfall nach 24 Stunden, „Alle entfernen“ und die Obergrenze je Standort.

Hintergrund (13.11.2026): Nach dem Veröffentlichen der Start-URL kamen Anfragen an, hinter denen kein
Gerät vor Ort stand. Sie melden sich nach kurzer Zeit nicht mehr und sollen die Liste nicht füllen."""
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLogEntry, DeviceEnrollment
from app.services import device_enrollment as de
from app.services import role_permissions as rp
from app.services.device_enrollment import describe_client, enrollment_active
from tests.test_device_enrollment import _login, _new_key, _setup

TABLET_UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _enroll(client: AsyncClient, key: str, installation: str, user_agent: str | None = TABLET_UA):
    headers = {"User-Agent": user_agent} if user_agent is not None else {}
    return await client.post(
        "/auth/device/enroll", json={"key": key, "installation_id": f"installation-{installation}-0123456789"}, headers=headers
    )


async def _rows(db: AsyncSession) -> list[DeviceEnrollment]:
    db.expire_all()
    return list((await db.execute(select(DeviceEnrollment).order_by(DeviceEnrollment.id))).scalars().all())


async def _age(db: AsyncSession, enrollment_id: int, delta: timedelta) -> None:
    """Letzte Meldung der Anfrage in die Vergangenheit legen."""
    row = await db.get(DeviceEnrollment, enrollment_id)
    row.last_seen_at = _now() - delta
    await db.commit()


async def _audit(db: AsyncSession) -> list[str]:
    rows = await db.execute(
        select(AuditLogEntry.detail).where(AuditLogEntry.action == AuditAction.DEVICE_ENROLLMENT).order_by(AuditLogEntry.id)
    )
    return [detail for (detail,) in rows.all()]


# --- Kurzform der Browser-Kennung (Einheit) ----------------------------------------------------------


@pytest.mark.parametrize(
    "user_agent, expected",
    [
        (TABLET_UA, "Chrome 157 auf Android"),
        ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/126.0.0.0 Safari/537.36", "Chrome ohne Bildschirm 126 auf Linux"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0", "Edge 157 auf Windows"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0", "Firefox 140 auf Windows"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.1 Safari/605.1.15", "Safari 19 auf macOS"),
        ("Mozilla/5.0 (iPad; CPU OS 19_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.1 Mobile/15E148 Safari/604.1", "Safari 19 auf iOS"),
        ("Mozilla/5.0 (Linux; Android 16; SM-X210) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/29.0 Chrome/140.0.0.0 Safari/537.36", "Samsung Internet 29 auf Android"),
        ("Mozilla/5.0 (X11; CrOS x86_64 16000.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36", "Chrome 157 auf ChromeOS"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 OPR/120.0.0.0", "Opera 120 auf Windows"),
        ("curl/8.7.1", "curl/8.7.1"),
        ("Mozilla/5.0 (Windows NT 10.0)", "Windows"),
        ("x" * 200, "x" * 60),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_describe_client(user_agent: str | None, expected: str | None) -> None:
    assert describe_client(user_agent) == expected


def test_enrollment_active_window() -> None:
    now = datetime(2026, 11, 13, 13, 0)
    fresh = DeviceEnrollment(last_seen_at=now - timedelta(minutes=2), created_at=now - timedelta(hours=5))
    old = DeviceEnrollment(last_seen_at=now - timedelta(minutes=4), created_at=now - timedelta(hours=5))
    edge = DeviceEnrollment(last_seen_at=now - de.ACTIVE_WINDOW, created_at=now)
    never_seen = DeviceEnrollment(last_seen_at=None, created_at=now - timedelta(minutes=1))
    never_seen_old = DeviceEnrollment(last_seen_at=None, created_at=now - timedelta(minutes=10))
    assert enrollment_active(fresh, now) and enrollment_active(edge, now) and enrollment_active(never_seen, now)
    assert not enrollment_active(old, now) and not enrollment_active(never_seen_old, now)
    assert not enrollment_active(DeviceEnrollment(last_seen_at=None, created_at=None), now)


def test_route_rule_for_cleanup() -> None:
    path = "/devices/enrollments/remove-inactive"
    assert rp.decide("POST", path, rp.normalize({"MASTER_DATA": "EDIT"}), has_employee=False) == rp.Decision.ALLOW
    assert rp.decide("POST", path, rp.normalize({"MASTER_DATA": "VIEW"}), has_employee=False) != rp.Decision.ALLOW
    assert rp.decide("POST", path, rp.normalize({"TIME": "EDIT"}), has_employee=False) != rp.Decision.ALLOW


# --- Herkunft und „wartet gerade“ ------------------------------------------------------------------


async def test_list_shows_origin_and_waiting_state(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    assert (await _enroll(client, key, "a")).json()["status"] == "PENDING"

    listed = (await client.get("/devices/enrollments", headers=hr)).json()
    assert len(listed) == 1
    assert listed[0]["active"] is True
    assert listed[0]["client"] == "Chrome 157 auf Android"
    assert listed[0]["client_ip"]  # Adresse des Test-Clients
    row = (await _rows(db_session))[0]
    assert row.user_agent == TABLET_UA and row.client_ip == listed[0]["client_ip"]


async def test_origin_is_optional_and_truncated(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    await _enroll(client, key, "a", user_agent="   ")
    await _enroll(client, key, "b", user_agent="A" * 500)
    first, second = await _rows(db_session)
    assert first.user_agent is None
    assert second.user_agent == "A" * 300
    listed = (await client.get("/devices/enrollments", headers=hr)).json()
    assert [item["client"] for item in listed] == [None, "A" * 60]


async def test_repeated_enrollment_of_same_installation_updates_origin(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    first = (await _enroll(client, key, "a")).json()
    again = (await _enroll(client, key, "a", user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/150.0.0.0")).json()
    assert again["verify_code"] == first["verify_code"]  # dieselbe Anfrage
    rows = await _rows(db_session)
    assert len(rows) == 1 and rows[0].user_agent.endswith("Chrome/150.0.0.0")


async def test_waiting_devices_come_first_and_orphans_are_marked(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    for installation in ("a", "b", "c"):
        await _enroll(client, key, installation)
    first, second, third = await _rows(db_session)
    await _age(db_session, first.id, timedelta(minutes=10))
    await _age(db_session, third.id, timedelta(hours=2))

    listed = (await client.get("/devices/enrollments", headers=hr)).json()
    assert [(item["id"], item["active"]) for item in listed] == [(second.id, True), (first.id, False), (third.id, False)]


async def test_pending_login_marks_device_as_waiting(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    token = (await _enroll(client, key, "a")).json()["device_token"]
    row = (await _rows(db_session))[0]
    await _age(db_session, row.id, timedelta(minutes=10))
    assert (await client.get("/devices/enrollments", headers=hr)).json()[0]["active"] is False

    # Die Kiosk-App versucht die Anmeldung jede Minute: Das zählt als Meldung.
    waiting = await _login(client, token, "installation-a-0123456789")
    assert waiting.status_code == 403 and waiting.json()["code"] == "DEVICE_PENDING"
    assert row.verify_code in waiting.json()["detail"]
    assert (await client.get("/devices/enrollments", headers=hr)).json()[0]["active"] is True

    # Ein fremdes Gerät mit demselben Token zählt nicht.
    await _age(db_session, row.id, timedelta(minutes=10))
    assert (await _login(client, token, "installation-x-0123456789")).status_code == 401
    assert (await client.get("/devices/enrollments", headers=hr)).json()[0]["active"] is False


async def test_pending_login_writes_at_most_every_30_seconds(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    token = (await _enroll(client, key, "a")).json()["device_token"]
    row = (await _rows(db_session))[0]
    await _age(db_session, row.id, timedelta(seconds=10))
    before = (await _rows(db_session))[0].last_seen_at
    assert (await _login(client, token, "installation-a-0123456789")).status_code == 403
    assert (await _rows(db_session))[0].last_seen_at == before


# --- Verfall und Aufräumen ----------------------------------------------------------------------------


async def test_orphans_expire_after_24_hours(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    token = (await _enroll(client, key, "a")).json()["device_token"]
    await _enroll(client, key, "b")
    old, recent = await _rows(db_session)
    old_code = old.verify_code
    await _age(db_session, old.id, timedelta(hours=25))
    await _age(db_session, recent.id, timedelta(hours=23))

    listed = (await client.get("/devices/enrollments", headers=hr)).json()
    assert [item["id"] for item in listed] == [recent.id]
    assert any("nach 24 Stunden ohne Meldung verfallen" in detail and old_code in detail for detail in await _audit(db_session))
    # Das Token der verfallenen Anfrage gilt nicht mehr.
    assert (await _login(client, token, "installation-a-0123456789")).status_code == 401
    # Meldet sich dasselbe Gerät später wieder, entsteht eine neue Anfrage.
    again = await _enroll(client, key, "a")
    assert again.json()["status"] == "PENDING" and again.json()["verify_code"] != old_code


async def test_expiry_also_runs_when_a_new_device_enrolls(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    await _enroll(client, key, "a")
    await _age(db_session, (await _rows(db_session))[0].id, timedelta(hours=30))
    await _enroll(client, key, "b")
    rows = await _rows(db_session)
    assert len(rows) == 1 and rows[0].installation_hash != ""
    assert sum("verfallen" in detail for detail in await _audit(db_session)) == 1


async def test_enrollment_without_last_seen_expires_by_creation_time(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    await _enroll(client, key, "a")
    row = (await _rows(db_session))[0]
    row.last_seen_at = None
    row.created_at = _now() - timedelta(hours=30)
    await db_session.commit()
    assert await de.purge_stale_enrollments(db_session, row.tenant_id) == 1
    await db_session.commit()
    assert await _rows(db_session) == []
    assert await de.purge_stale_enrollments(db_session, 1) == 0  # nichts mehr zu tun, kein weiterer Eintrag
    assert sum("verfallen" in detail for detail in await _audit(db_session)) == 1


async def test_remove_inactive_keeps_waiting_devices(client: AsyncClient, db_session: AsyncSession) -> None:
    location, other, hr = await _setup(db_session, client)
    key, other_key = await _new_key(client, hr, location.id), await _new_key(client, hr, other.id)
    await _enroll(client, key, "a")
    await _enroll(client, key, "b")
    await _enroll(client, other_key, "c")
    first, second, third = await _rows(db_session)
    await _age(db_session, first.id, timedelta(minutes=5))
    await _age(db_session, third.id, timedelta(hours=3))
    codes = (first.verify_code, third.verify_code)

    removed = await client.post("/devices/enrollments/remove-inactive", headers=hr)
    assert removed.status_code == 200 and removed.json() == {"removed": 2}
    assert [row.id for row in await _rows(db_session)] == [second.id]
    entry = (await _audit(db_session))[-1]
    assert "2 offene Registrierung(en) entfernt" in entry and all(code in entry for code in codes)
    actor = (
        await db_session.execute(select(AuditLogEntry.actor_account_id).order_by(AuditLogEntry.id.desc()).limit(1))
    ).scalar_one()
    assert actor is not None

    # Nichts mehr zu entfernen: 0 und kein weiterer Protokolleintrag
    count = len(await _audit(db_session))
    assert (await client.post("/devices/enrollments/remove-inactive", headers=hr)).json() == {"removed": 0}
    assert len(await _audit(db_session)) == count


async def test_remove_inactive_needs_hr(client: AsyncClient, db_session: AsyncSession) -> None:
    await _setup(db_session, client)
    assert (await client.post("/devices/enrollments/remove-inactive")).status_code == 401
    token = (await client.post("/auth/login", json={"email": "sv@example.com", "password": "pw"})).json()["access_token"]
    response = await client.post("/devices/enrollments/remove-inactive", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


# --- Obergrenze je Standort ---------------------------------------------------------------------------


async def test_orphans_do_not_block_a_real_device(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(de, "PENDING_LIMIT_PER_LOCATION", 3)
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    for installation in ("a", "b", "c"):
        await _enroll(client, key, installation)
    first, second, third = await _rows(db_session)
    await _age(db_session, first.id, timedelta(minutes=30))
    await _age(db_session, second.id, timedelta(minutes=20))

    # Voll, aber zwei Anfragen melden sich nicht mehr: die älteste macht Platz.
    assert (await _enroll(client, key, "d")).json()["status"] == "PENDING"
    assert [row.id for row in await _rows(db_session)][:2] == [second.id, third.id]
    assert any("um Platz für eine neue Anfrage zu machen" in detail for detail in await _audit(db_session))


async def test_limit_still_holds_when_all_devices_are_waiting(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(de, "PENDING_LIMIT_PER_LOCATION", 2)
    location, other, hr = await _setup(db_session, client)
    key, other_key = await _new_key(client, hr, location.id), await _new_key(client, hr, other.id)
    await _enroll(client, key, "a")
    await _enroll(client, key, "b")
    blocked = await _enroll(client, key, "c")
    assert blocked.status_code == 429 and blocked.json()["code"] == "TOO_MANY_PENDING_ENROLLMENTS"
    # Die wartende Anfrage selbst darf sich weiter melden, und andere Standorte sind nicht betroffen.
    assert (await _enroll(client, key, "a")).status_code == 200
    assert (await _enroll(client, other_key, "c")).status_code == 200
    assert len(await _rows(db_session)) == 3
