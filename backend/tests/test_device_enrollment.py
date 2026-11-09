"""Tablets per MDM verteilen: Registrierungsschlüssel, Selbstregistrierung, Freigabe."""
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    Account,
    AuditAction,
    AuditLogEntry,
    Device,
    DeviceEnrollment,
    DeviceEnrollmentKey,
    HrRole,
    Location,
    Notification,
    NotificationType,
    Tenant,
)
from app.services.auth_service import hash_password
from app.services.pairing_service import token_hash

INSTALL_A = "installation-a-0123456789"
INSTALL_B = "installation-b-0123456789"


async def _setup(db_session: AsyncSession, client: AsyncClient):
    location = Location(name="Frankfurt", timezone="UTC")
    other = Location(name="Viernheim", timezone="UTC")
    db_session.add_all([location, other])
    await db_session.commit()
    db_session.add_all(
        [
            Account(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR),
            Account(email="sv@example.com", password_hash=hash_password("pw"), role=HrRole.SUPERVISOR),
        ]
    )
    await db_session.commit()
    token = (await client.post("/auth/login", json={"email": "hr@example.com", "password": "pw"})).json()["access_token"]
    return location, other, {"Authorization": f"Bearer {token}"}


async def _new_key(client: AsyncClient, hr: dict, location_id: int, valid_days: int | None = 30) -> str:
    r = await client.post("/devices/enrollment-keys", headers=hr, json={"location_id": location_id, "valid_days": valid_days})
    assert r.status_code == 201, r.text
    return r.json()["key"]


async def _enroll(client: AsyncClient, key: str, installation: str = INSTALL_A, name: str | None = "NB-FRA-01"):
    body = {"key": key, "installation_id": installation}
    if name is not None:
        body["name"] = name
    return await client.post("/auth/device/enroll", json=body)


async def _login(client: AsyncClient, device_token: str, installation: str = INSTALL_A):
    return await client.post("/auth/device/login", json={"device_token": device_token, "installation_id": installation})


async def test_key_is_shown_once_and_stored_hashed(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    r = await client.post("/devices/enrollment-keys", headers=hr, json={"location_id": location.id})
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["key"]) >= 40 and body["expires_at"] is not None
    row = (await db_session.execute(select(DeviceEnrollmentKey))).scalar_one()
    assert row.key_hash == token_hash(body["key"]) and body["key"] not in row.key_hash

    listed = (await client.get("/devices/enrollment-keys", headers=hr)).json()
    assert listed == [
        {"location_id": location.id, "created_at": listed[0]["created_at"], "expires_at": listed[0]["expires_at"], "last_used_at": None}
    ]
    assert "key" not in listed[0]

    # Erneuern ersetzt den alten Schlüssel sofort
    second = await _new_key(client, hr, location.id, valid_days=None)
    assert (await _enroll(client, body["key"])).json()["code"] == "ENROLLMENT_KEY_INVALID"
    assert (await _enroll(client, second)).status_code == 200
    rows = (await db_session.execute(select(DeviceEnrollmentKey))).scalars().all()
    assert len(rows) == 1 and rows[0].expires_at is None

    # Sperren
    assert (await client.delete(f"/devices/enrollment-keys/{location.id}", headers=hr)).status_code == 204
    assert (await _enroll(client, second, INSTALL_B)).json()["code"] == "ENROLLMENT_KEY_INVALID"
    assert (await client.delete(f"/devices/enrollment-keys/{location.id}", headers=hr)).status_code == 404
    actions = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.DEVICE_ENROLLMENT))).scalars().all()
    assert any("gesperrt" in a.detail for a in actions) and any("erneuert" in a.detail for a in actions)


async def test_key_management_needs_full_hr_and_valid_input(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    sv_token = (await client.post("/auth/login", json={"email": "sv@example.com", "password": "pw"})).json()["access_token"]
    sv = {"Authorization": f"Bearer {sv_token}"}
    assert (await client.post("/devices/enrollment-keys", headers=sv, json={"location_id": location.id})).status_code == 403
    assert (await client.get("/devices/enrollments", headers=sv)).status_code == 403
    assert (await client.post("/devices/enrollment-keys", json={"location_id": location.id})).status_code in (401, 403)
    for days in (0, 366, "viele"):
        r = await client.post("/devices/enrollment-keys", headers=hr, json={"location_id": location.id, "valid_days": days})
        assert r.status_code == 422, days
    assert (await client.post("/devices/enrollment-keys", headers=hr, json={"location_id": 999})).status_code == 404


async def test_prepared_device_binds_without_approval(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    r = await client.post("/devices", headers=hr, json={"location_id": location.id, "name": "Eingang", "mdm_name": " NB-FRA-01 "})
    assert r.status_code == 201 and r.json()["mdm_name"] == "NB-FRA-01"
    key = await _new_key(client, hr, location.id)

    r = await _enroll(client, key, name="nb-fra-01")  # Groß-/Kleinschreibung egal
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "BOUND" and r.json()["verify_code"] is None
    login = await _login(client, r.json()["device_token"])
    assert login.status_code == 200 and login.json()["device_name"] == "Eingang"
    # Ein anderes Gerät mit demselben Token bleibt draußen (Bindung an die Installation)
    assert (await _login(client, r.json()["device_token"], INSTALL_B)).json()["code"] == "DEVICE_IN_USE"

    alerts = (await db_session.execute(select(Notification).where(Notification.type == NotificationType.DEVICE_ALERT))).scalars().all()
    assert any("per MDM als Tablet „Eingang“" in n.message for n in alerts)
    key_row = (await db_session.execute(select(DeviceEnrollmentKey))).scalar_one()
    assert key_row.last_used_at is not None


async def test_used_device_is_never_taken_over_by_key(client: AsyncClient, db_session: AsyncSession) -> None:
    """Auch nach „Kopplung aufheben“ übernimmt der Schlüssel einen benutzten Eintrag nicht – sonst
    käme ein verlorenes Gerät mit der MDM-URL von selbst wieder rein."""
    location, _, hr = await _setup(db_session, client)
    device = Device(location_id=location.id, name="Eingang", token_hash=token_hash("tok"), mdm_name="NB-FRA-01")
    db_session.add(device)
    await db_session.commit()
    assert (await _login(client, "tok")).status_code == 200  # benutzt (last_seen gesetzt)
    assert (await client.patch(f"/devices/{device.id}", headers=hr, json={"regenerate_token": True})).status_code == 200

    key = await _new_key(client, hr, location.id)
    r = await _enroll(client, key, INSTALL_B, name="NB-FRA-01")
    assert r.json()["status"] == "PENDING"
    pending = (await client.get("/devices/enrollments", headers=hr)).json()
    assert pending[0]["conflict_device_name"] == "Eingang"
    alerts = (await db_session.execute(select(Notification))).scalars().all()
    assert any("bereits in Benutzung" in n.message for n in alerts)


async def test_pending_device_waits_for_approval_as_new_tablet(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)

    r = await _enroll(client, key, name="NB-FRA-07")
    assert r.status_code == 200 and r.json()["status"] == "PENDING"
    token, code = r.json()["device_token"], r.json()["verify_code"]
    assert len(code) == 7 and code[3] == "-"
    login = await _login(client, token)
    assert login.status_code == 403 and login.json()["code"] == "DEVICE_PENDING" and code in login.json()["detail"]
    # Fremde Installation mit dem Token: kein Hinweis auf die Anfrage
    assert (await _login(client, token, INSTALL_B)).json()["code"] == "INVALID_DEVICE_TOKEN"

    # Gleiches Gerät startet neu: dieselbe Anfrage (gleicher Prüfcode), neues Token
    again = await _enroll(client, key, name="NB-FRA-07")
    assert again.json()["verify_code"] == code
    assert (await _login(client, token)).json()["code"] == "INVALID_DEVICE_TOKEN"
    token = again.json()["device_token"]

    pending = (await client.get("/devices/enrollments", headers=hr)).json()
    assert len(pending) == 1 and pending[0]["reported_name"] == "NB-FRA-07" and pending[0]["verify_code"] == code
    assert pending[0]["conflict_device_name"] is None
    alerts = (await db_session.execute(select(Notification))).scalars().all()
    assert sum(code in n.message for n in alerts) == 1  # nur eine Benachrichtigung je Anfrage

    r = await client.post(f"/devices/enrollments/{pending[0]['id']}/approve", headers=hr, json={})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "NB-FRA-07" and r.json()["mdm_name"] == "NB-FRA-07" and r.json()["bound_at"]
    assert (await _login(client, token)).status_code == 200
    assert (await client.get("/devices/enrollments", headers=hr)).json() == []
    audit = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.DEVICE_ENROLLMENT))).scalars().all()
    assert any("freigegeben" in a.detail and code in a.detail for a in audit)


async def test_approve_replaces_existing_tablet(client: AsyncClient, db_session: AsyncSession) -> None:
    location, other, hr = await _setup(db_session, client)
    old = Device(location_id=location.id, name="Kasse", token_hash=token_hash("old-token"))
    elsewhere = Device(location_id=other.id, name="Woanders", token_hash=token_hash("x"))
    db_session.add_all([old, elsewhere])
    await db_session.commit()
    assert (await _login(client, "old-token", INSTALL_B)).status_code == 200
    key = await _new_key(client, hr, location.id)
    r = await _enroll(client, key, name=None)
    token = r.json()["device_token"]
    enrollment_id = (await client.get("/devices/enrollments", headers=hr)).json()[0]["id"]

    url = f"/devices/enrollments/{enrollment_id}/approve"
    assert (await client.post(url, headers=hr, json={"device_id": elsewhere.id})).json()["code"] == "LOCATION_MISMATCH"
    assert (await client.post(url, headers=hr, json={"device_id": 999})).status_code == 404
    r = await client.post(url, headers=hr, json={"device_id": old.id})
    assert r.status_code == 200 and r.json()["id"] == old.id and r.json()["mdm_name"] is None
    assert (await _login(client, token)).status_code == 200
    # Das bisherige Gerät ist abgemeldet
    assert (await _login(client, "old-token", INSTALL_B)).json()["code"] == "INVALID_DEVICE_TOKEN"
    audit = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.DEVICE_ENROLLMENT))).scalars().all()
    assert any("ersetzt das bisherige Gerät" in a.detail for a in audit)


async def test_reject_and_reset_device(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    r = await _enroll(client, key)
    token = r.json()["device_token"]
    enrollment_id = (await client.get("/devices/enrollments", headers=hr)).json()[0]["id"]
    assert (await client.delete(f"/devices/enrollments/{enrollment_id}", headers=hr)).status_code == 204
    assert (await _login(client, token)).json()["code"] == "INVALID_DEVICE_TOKEN"
    assert (await client.delete(f"/devices/enrollments/{enrollment_id}", headers=hr)).status_code == 404

    # Freigegebenes Gerät, das sein Token verliert („Tablet zurücksetzen“), bekommt mit derselben
    # Installation wieder seinen Eintrag – ohne neue Freigabe.
    r = await _enroll(client, key)
    enrollment_id = (await client.get("/devices/enrollments", headers=hr)).json()[0]["id"]
    device_id = (await client.post(f"/devices/enrollments/{enrollment_id}/approve", headers=hr, json={"name": "Lager"})).json()["id"]
    r = await _enroll(client, key)
    assert r.json()["status"] == "BOUND"
    login = await _login(client, r.json()["device_token"])
    assert login.status_code == 200 and login.json()["device_name"] == "Lager"
    assert (await db_session.get(Device, device_id)) is not None


async def test_expired_key_pending_limit_and_rate_limit(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    row = (await db_session.execute(select(DeviceEnrollmentKey))).scalar_one()
    row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
    await db_session.commit()
    assert (await _enroll(client, key)).json()["code"] == "ENROLLMENT_KEY_EXPIRED"

    key = await _new_key(client, hr, location.id)
    from app.services import device_enrollment

    monkeypatch.setattr(device_enrollment, "PENDING_LIMIT_PER_LOCATION", 2)
    assert (await _enroll(client, key, "install-1-0123456789")).status_code == 200
    assert (await _enroll(client, key, "install-2-0123456789")).status_code == 200
    r = await _enroll(client, key, "install-3-0123456789")
    assert r.status_code == 429 and r.json()["code"] == "TOO_MANY_PENDING_ENROLLMENTS"
    # Bekanntes Gerät aktualisiert seine Anfrage weiterhin
    assert (await _enroll(client, key, "install-1-0123456789")).status_code == 200

    # Der abgelaufene Schlüssel oben zählt als erster Fehlversuch
    for _ in range(9):
        assert (await _enroll(client, "falscher-schluessel-0123456789", INSTALL_B)).status_code == 401
    assert (await _enroll(client, key, INSTALL_B)).status_code == 429


async def test_enroll_input_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    for body in (
        {"key": "kurz", "installation_id": INSTALL_A},
        {"key": key + "!", "installation_id": INSTALL_A},
        {"key": key, "installation_id": "kurz"},
        {"key": key, "installation_id": INSTALL_A, "name": "<script>"},
        {"key": key, "installation_id": INSTALL_A, "name": "x" * 101},
    ):
        assert (await client.post("/auth/device/enroll", json=body)).status_code == 422, body
    # Nicht ersetzte MDM-Platzhalter zählen als „kein Name“
    r = await _enroll(client, key, name="{{devicename}}")
    assert r.status_code == 200
    assert (await client.get("/devices/enrollments", headers=hr)).json()[0]["reported_name"] is None


async def test_mdm_name_unique_per_tenant(client: AsyncClient, db_session: AsyncSession) -> None:
    location, other, hr = await _setup(db_session, client)
    first = (await client.post("/devices", headers=hr, json={"location_id": location.id, "name": "A", "mdm_name": "NB-01"})).json()
    r = await client.post("/devices", headers=hr, json={"location_id": other.id, "name": "B", "mdm_name": "nb-01"})
    assert r.status_code == 409 and r.json()["code"] == "MDM_NAME_TAKEN"
    second = (await client.post("/devices", headers=hr, json={"location_id": other.id, "name": "B"})).json()
    assert second["mdm_name"] is None
    assert (await client.patch(f"/devices/{second['id']}", headers=hr, json={"mdm_name": "NB-01"})).status_code == 409
    # Eigener Name bleibt erlaubt, leer entfernt ihn, andere Felder lassen ihn in Ruhe
    assert (await client.patch(f"/devices/{first['id']}", headers=hr, json={"mdm_name": "NB-01"})).status_code == 200
    assert (await client.patch(f"/devices/{first['id']}", headers=hr, json={"name": "A2"})).json()["mdm_name"] == "NB-01"
    assert (await client.patch(f"/devices/{first['id']}", headers=hr, json={"mdm_name": ""})).json()["mdm_name"] is None


async def test_key_of_other_tenant_is_useless(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    location, _, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    monkeypatch.setattr(settings, "tenant_base_domain", "hr3000.de")
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.commit()
    r = await client.post(
        "/auth/device/enroll", json={"key": key, "installation_id": INSTALL_A}, headers={"Host": "acme.hr3000.de"}
    )
    assert r.status_code == 401 and r.json()["code"] == "ENROLLMENT_KEY_INVALID"
    assert (await db_session.execute(select(DeviceEnrollment))).scalars().all() == []
