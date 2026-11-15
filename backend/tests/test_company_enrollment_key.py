"""Firmenschlüssel: ein Registrierungsschlüssel für alle Standorte, der Standort wird bei der Freigabe gewählt
(Android-App, MDM mit App-Konfiguration je App statt je Gerät)."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
)
from app.services.auth_service import hash_password
from app.services.pairing_service import token_hash
from tests.test_device_enrollment import INSTALL_A, INSTALL_B, _enroll, _login, _new_key, _setup


async def _company_key(client: AsyncClient, hr: dict, valid_days: int | None = 30) -> dict:
    r = await client.post("/devices/enrollment-keys", headers=hr, json={"location_id": None, "valid_days": valid_days})
    assert r.status_code == 201, r.text
    return r.json()


async def _pending(client: AsyncClient, hr: dict) -> list[dict]:
    r = await client.get("/devices/enrollments", headers=hr)
    assert r.status_code == 200
    return r.json()


async def _audit(db: AsyncSession) -> list[str]:
    rows = await db.execute(
        select(AuditLogEntry.detail).where(AuditLogEntry.action == AuditAction.DEVICE_ENROLLMENT).order_by(AuditLogEntry.id)
    )
    return [detail for (detail,) in rows.all()]


# --- Schlüssel verwalten -------------------------------------------------------------------------


async def test_company_key_is_created_listed_and_stored_hashed(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, hr = await _setup(db_session, client)
    created = await _company_key(client, hr)
    assert created["location_id"] is None and len(created["key"]) >= 40
    rows = (await db_session.execute(select(DeviceEnrollmentKey))).scalars().all()
    assert len(rows) == 1 and rows[0].location_id is None and rows[0].key_hash == token_hash(created["key"])
    listed = (await client.get("/devices/enrollment-keys", headers=hr)).json()
    assert [entry["location_id"] for entry in listed] == [None]
    assert "key" not in listed[0]
    assert any("die ganze Firma (Firmenschlüssel) erzeugt (30 Tage gültig)" in d for d in await _audit(db_session))


async def test_company_key_answer_contains_kiosk_url_for_the_android_app(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, hr = await _setup(db_session, client)
    r = await client.post(
        "/devices/enrollment-keys", headers={**hr, "Host": "lassner.hr.lassners.de"}, json={"location_id": None, "valid_days": None}
    )
    body = r.json()
    assert body["kiosk_url"] == "http://lassner.kiosk.hr.lassners.de"
    assert body["enroll_url"] == f"http://lassner.kiosk.hr.lassners.de/#enroll={body['key']}"
    assert body["expires_at"] is None


async def test_renewing_replaces_only_the_company_key(client: AsyncClient, db_session: AsyncSession) -> None:
    location, other, hr = await _setup(db_session, client)
    location_key = await _new_key(client, hr, location.id)
    old = (await _company_key(client, hr))["key"]
    new = (await _company_key(client, hr))["key"]
    rows = (await db_session.execute(select(DeviceEnrollmentKey))).scalars().all()
    assert sorted((row.location_id or 0) for row in rows) == [0, location.id]
    assert (await _enroll(client, old)).json()["code"] == "ENROLLMENT_KEY_INVALID"
    assert (await _enroll(client, new)).json()["status"] == "PENDING"
    # Der Standort-Schlüssel gilt weiter
    assert (await _enroll(client, location_key, INSTALL_B)).json()["status"] == "PENDING"
    assert any("Firmenschlüssel) erneuert" in d for d in await _audit(db_session))


async def test_create_key_input_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, hr = await _setup(db_session, client)
    for body in (
        {},  # location_id ist Pflicht (null = Firmenschlüssel), sonst entstünde aus Versehen ein Firmenschlüssel
        {"valid_days": 30},
        {"location_id": 0},
        {"location_id": -1},
        {"location_id": "x"},
        {"location_id": None, "valid_days": 0},
        {"location_id": None, "valid_days": 366},
        {"location_id": None, "unbekannt": 1},
    ):
        assert (await client.post("/devices/enrollment-keys", headers=hr, json=body)).status_code == 422, body
    r = await client.post("/devices/enrollment-keys", headers=hr, json={"location_id": 999})
    assert r.status_code == 404 and r.json()["code"] == "LOCATION_NOT_FOUND"


async def test_location_of_other_tenant_is_not_found(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, hr = await _setup(db_session, client)
    from app.models import Tenant

    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.flush()
    foreign = Location(tenant_id=2, name="Fremd", timezone="UTC")
    db_session.add(foreign)
    await db_session.commit()
    r = await client.post("/devices/enrollment-keys", headers=hr, json={"location_id": foreign.id})
    assert r.status_code == 404


async def test_revoke_company_key(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, hr = await _setup(db_session, client)
    key = (await _company_key(client, hr))["key"]
    await _new_key(client, hr, location.id)
    assert (await _enroll(client, key)).json()["status"] == "PENDING"
    assert (await client.delete("/devices/enrollment-keys/company", headers=hr)).status_code == 204
    assert (await _enroll(client, key, INSTALL_B)).json()["code"] == "ENROLLMENT_KEY_INVALID"
    # Offene Anfrage bleibt und kann weiter bearbeitet werden; Standort-Schlüssel bleibt
    assert len(await _pending(client, hr)) == 1
    assert [row.location_id for row in (await db_session.execute(select(DeviceEnrollmentKey))).scalars()] == [location.id]
    r = await client.delete("/devices/enrollment-keys/company", headers=hr)
    assert r.status_code == 404 and r.json()["code"] == "ENROLLMENT_KEY_NOT_FOUND"
    # Die Route mit Standort-ID funktioniert unverändert
    assert (await client.delete(f"/devices/enrollment-keys/{location.id}", headers=hr)).status_code == 204
    assert any("Firmenschlüssel für die Tablet-Registrierung gesperrt" in d for d in await _audit(db_session))


async def test_company_key_management_needs_master_data_rights(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, _ = await _setup(db_session, client)
    token = (await client.post("/auth/login", json={"email": "sv@example.com", "password": "pw"})).json()["access_token"]
    supervisor = {"Authorization": f"Bearer {token}"}
    assert (await client.post("/devices/enrollment-keys", headers=supervisor, json={"location_id": None})).status_code == 403
    assert (await client.delete("/devices/enrollment-keys/company", headers=supervisor)).status_code == 403
    assert (await client.delete("/devices/enrollment-keys/company")).status_code == 401


# --- Registrieren mit dem Firmenschlüssel ----------------------------------------------------------


async def test_new_device_waits_without_location(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, hr = await _setup(db_session, client)
    key = (await _company_key(client, hr))["key"]
    r = await _enroll(client, key, name="Kiosk-HEF")
    assert r.status_code == 200 and r.json()["status"] == "PENDING"
    pending = await _pending(client, hr)
    assert len(pending) == 1 and pending[0]["location_id"] is None and pending[0]["reported_name"] == "Kiosk-HEF"
    message = (await db_session.execute(select(Notification))).scalars().first().message
    assert "mit dem Firmenschlüssel" in message and "Standort wird beim Freigeben gewählt" in message
    assert any("möchte sich mit dem Firmenschlüssel einrichten" in d for d in await _audit(db_session))
    login = await _login(client, r.json()["device_token"])
    assert login.status_code == 403 and login.json()["code"] == "DEVICE_PENDING"


async def test_same_installation_returns_to_its_tablet_at_any_location(client: AsyncClient, db_session: AsyncSession) -> None:
    """Datenverlust am Tablet: Mit dem Firmenschlüssel findet es seinen Eintrag an jedem Standort wieder."""
    _, other, hr = await _setup(db_session, client)
    device = Device(location_id=other.id, name="Kiosk-VH", token_hash=token_hash("alt"))
    db_session.add(device)
    await db_session.commit()
    assert (await _login(client, "alt", INSTALL_A)).status_code == 200  # bindet INSTALL_A
    key = (await _company_key(client, hr))["key"]
    r = await _enroll(client, key, INSTALL_A, name="egal")
    assert r.json()["status"] == "BOUND"
    session = (await _login(client, r.json()["device_token"], INSTALL_A)).json()
    assert (session["device_name"], session["location_id"]) == ("Kiosk-VH", other.id)
    assert await _pending(client, hr) == []
    # Das alte Token gilt nicht mehr
    assert (await _login(client, "alt", INSTALL_A)).json()["code"] == "INVALID_DEVICE_TOKEN"


async def test_location_key_still_only_finds_its_own_location(client: AsyncClient, db_session: AsyncSession) -> None:
    location, other, hr = await _setup(db_session, client)
    db_session.add(Device(location_id=other.id, name="Kiosk-VH", token_hash=token_hash("alt")))
    await db_session.commit()
    assert (await _login(client, "alt", INSTALL_A)).status_code == 200
    key = await _new_key(client, hr, location.id)
    assert (await _enroll(client, key, INSTALL_A)).json()["status"] == "PENDING"
    assert (await _pending(client, hr))[0]["location_id"] == location.id


async def test_prepared_entry_at_any_location_binds_by_device_name(client: AsyncClient, db_session: AsyncSession) -> None:
    _, other, hr = await _setup(db_session, client)
    prepared = Device(location_id=other.id, name="Viernheim", token_hash=token_hash("x"), mdm_name="Kiosk-VH")
    db_session.add(prepared)
    await db_session.commit()
    key = (await _company_key(client, hr))["key"]
    r = await _enroll(client, key, name="kiosk-vh")
    assert r.json()["status"] == "BOUND"
    await db_session.refresh(prepared)
    assert prepared.installation_hash is not None and prepared.location_id == other.id


async def test_used_entry_is_never_taken_over_by_the_company_key(client: AsyncClient, db_session: AsyncSession) -> None:
    _, other, hr = await _setup(db_session, client)
    db_session.add(Device(location_id=other.id, name="Viernheim", token_hash=token_hash("x"), mdm_name="Kiosk-VH"))
    await db_session.commit()
    assert (await _login(client, "x", INSTALL_A)).status_code == 200
    key = (await _company_key(client, hr))["key"]
    assert (await _enroll(client, key, INSTALL_B, name="Kiosk-VH")).json()["status"] == "PENDING"
    assert (await _pending(client, hr))[0]["conflict_device_name"] == "Viernheim"


async def test_pending_limit_counts_company_requests_separately(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    location, _, hr = await _setup(db_session, client)
    from app.services import device_enrollment

    monkeypatch.setattr(device_enrollment, "PENDING_LIMIT_PER_LOCATION", 2)
    company = (await _company_key(client, hr))["key"]
    local = await _new_key(client, hr, location.id)
    assert (await _enroll(client, local, "standort-1-0123456789")).status_code == 200
    assert (await _enroll(client, local, "standort-2-0123456789")).status_code == 200
    assert (await _enroll(client, company, "firma-1-0123456789")).status_code == 200
    assert (await _enroll(client, company, "firma-2-0123456789")).status_code == 200
    r = await _enroll(client, company, "firma-3-0123456789")
    assert r.status_code == 429 and r.json()["code"] == "TOO_MANY_PENDING_ENROLLMENTS"


async def test_known_request_moves_between_keys(client: AsyncClient, db_session: AsyncSession) -> None:
    """Dieselbe Installation meldet sich erst mit dem Standort-, dann mit dem Firmenschlüssel: eine Anfrage."""
    location, _, hr = await _setup(db_session, client)
    local = await _new_key(client, hr, location.id)
    code = (await _enroll(client, local)).json()["verify_code"]
    company = (await _company_key(client, hr))["key"]
    assert (await _enroll(client, company)).json()["verify_code"] == code
    pending = await _pending(client, hr)
    assert len(pending) == 1 and pending[0]["location_id"] is None


# --- Freigeben ---------------------------------------------------------------------------------------


async def test_approve_needs_a_location_for_company_requests(client: AsyncClient, db_session: AsyncSession) -> None:
    _, other, hr = await _setup(db_session, client)
    key = (await _company_key(client, hr))["key"]
    token = (await _enroll(client, key, name="Kiosk-HEF")).json()["device_token"]
    enrollment_id = (await _pending(client, hr))[0]["id"]
    url = f"/devices/enrollments/{enrollment_id}/approve"
    r = await client.post(url, headers=hr, json={})
    assert r.status_code == 400 and r.json()["code"] == "LOCATION_REQUIRED"
    assert (await client.post(url, headers=hr, json={"location_id": 999})).json()["code"] == "LOCATION_NOT_FOUND"
    for body in ({"location_id": 0}, {"location_id": "x"}, {"device_id": 0}, {"standort": other.id}):
        assert (await client.post(url, headers=hr, json=body)).status_code == 422, body
    r = await client.post(url, headers=hr, json={"location_id": other.id})
    assert r.status_code == 200, r.text
    assert r.json()["location_id"] == other.id and r.json()["name"] == "Kiosk-HEF" and r.json()["mdm_name"] == "Kiosk-HEF"
    assert (await _login(client, token)).status_code == 200
    assert await _pending(client, hr) == []


async def test_company_request_may_replace_a_tablet_at_any_location(client: AsyncClient, db_session: AsyncSession) -> None:
    location, other, hr = await _setup(db_session, client)
    old = Device(location_id=other.id, name="Kiosk-Frankfurt", token_hash=token_hash("alt"))
    db_session.add(old)
    await db_session.commit()
    assert (await _login(client, "alt", INSTALL_B)).status_code == 200
    key = (await _company_key(client, hr))["key"]
    token = (await _enroll(client, key, INSTALL_A)).json()["device_token"]
    url = f"/devices/enrollments/{(await _pending(client, hr))[0]['id']}/approve"
    # Widersprüchliche Angaben werden abgewiesen
    r = await client.post(url, headers=hr, json={"device_id": old.id, "location_id": location.id})
    assert r.status_code == 400 and r.json()["code"] == "LOCATION_MISMATCH"
    r = await client.post(url, headers=hr, json={"device_id": old.id, "location_id": other.id})
    assert r.status_code == 200 and r.json()["id"] == old.id and r.json()["location_id"] == other.id
    assert (await _login(client, token, INSTALL_A)).status_code == 200
    assert (await _login(client, "alt", INSTALL_B)).json()["code"] == "INVALID_DEVICE_TOKEN"


async def test_location_request_can_be_moved_to_another_location(client: AsyncClient, db_session: AsyncSession) -> None:
    location, other, hr = await _setup(db_session, client)
    key = await _new_key(client, hr, location.id)
    await _enroll(client, key)
    url = f"/devices/enrollments/{(await _pending(client, hr))[0]['id']}/approve"
    r = await client.post(url, headers=hr, json={"location_id": other.id})
    assert r.status_code == 200 and r.json()["location_id"] == other.id


async def test_location_request_still_cannot_replace_a_tablet_elsewhere(client: AsyncClient, db_session: AsyncSession) -> None:
    location, other, hr = await _setup(db_session, client)
    elsewhere = Device(location_id=other.id, name="Woanders", token_hash=token_hash("x"))
    db_session.add(elsewhere)
    await db_session.commit()
    key = await _new_key(client, hr, location.id)
    await _enroll(client, key)
    url = f"/devices/enrollments/{(await _pending(client, hr))[0]['id']}/approve"
    r = await client.post(url, headers=hr, json={"device_id": elsewhere.id})
    assert r.status_code == 400 and r.json()["code"] == "LOCATION_MISMATCH"


async def test_reject_company_request(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, hr = await _setup(db_session, client)
    key = (await _company_key(client, hr))["key"]
    token = (await _enroll(client, key)).json()["device_token"]
    enrollment_id = (await _pending(client, hr))[0]["id"]
    assert (await client.delete(f"/devices/enrollments/{enrollment_id}", headers=hr)).status_code == 204
    assert (await db_session.execute(select(DeviceEnrollment))).scalars().all() == []
    assert (await _login(client, token)).json()["code"] == "INVALID_DEVICE_TOKEN"
    entry = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.detail.like("%abgelehnt%")).order_by(AuditLogEntry.id.desc())
        )
    ).scalars().first()
    assert entry.entity_type == "tenant"


async def test_hr_with_master_data_area_sees_company_requests(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, hr = await _setup(db_session, client)
    db_session.add(Account(email="admin@example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    key = (await _company_key(client, hr))["key"]
    await _enroll(client, key)
    token = (await client.post("/auth/login", json={"email": "admin@example.com", "password": "pw"})).json()["access_token"]
    assert len(await _pending(client, {"Authorization": f"Bearer {token}"})) == 1
