"""Selbstregistrierung auf hr3000.de/registrieren (POST /public/signup, GET /public/subdomain-available)."""

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import AppSettings, BreakRule, HrRole, Account, Tenant, TenantPlan, TenantStatus
from app.services.auth_service import hash_password
from app.services.tenant_provisioning import TERMS_VERSION

SIGNUP = "/public/signup"
AVAILABLE = "/public/subdomain-available"
WEBSITE = {"Host": "hr3000.de"}


@pytest.fixture
def platform(monkeypatch):
    monkeypatch.setattr(settings, "tenant_base_domain", "hr3000.de")
    # Ohne Debug-Modus: keine Rückfall-Firma – Zuordnung nur über den Host.
    monkeypatch.setattr(settings, "debug", False)


def _payload(**overrides) -> dict:
    data = {
        "company_name": "Neue Firma GmbH",
        "subdomain": "neue-firma",
        "contact_name": "Nina Neu",
        "email": "nina@neue-firma.example",
        "password": "sehr-geheim-123",
        "is_business": True,
        "accept_terms": True,
        "website": "",
    }
    data.update(overrides)
    return data


async def _tenant_count(db_session) -> int:
    return await db_session.scalar(select(func.count()).select_from(Tenant))


async def test_signup_creates_ready_to_use_company(client, db_session, platform):
    response = await client.post(SIGNUP, json=_payload(company_name="  Neue Firma GmbH  "), headers=WEBSITE)
    assert response.status_code == 201, response.text
    assert response.json() == {
        "subdomain": "neue-firma",
        "login_url": "https://neue-firma.hr3000.de/",
        "verification_required": False,  # ohne Mailversand sofort nutzbar
    }

    tenant = await db_session.scalar(select(Tenant).where(Tenant.subdomain == "neue-firma"))
    assert tenant.name == "Neue Firma GmbH"  # Leerzeichen entfernt
    assert tenant.plan == TenantPlan.FREE and tenant.status == TenantStatus.ACTIVE
    assert tenant.self_signup is True
    assert tenant.terms_version == TERMS_VERSION and tenant.terms_accepted_at is not None
    assert (tenant.contact_name, tenant.contact_email) == ("Nina Neu", "nina@neue-firma.example")
    # Wie beim Anlegen durch den Super-Admin: Einstellungen und gesetzliche Pausenstaffel.
    assert await db_session.scalar(select(func.count()).select_from(AppSettings).where(AppSettings.tenant_id == tenant.id)) == 1
    assert await db_session.scalar(select(func.count()).select_from(BreakRule).where(BreakRule.tenant_id == tenant.id)) > 0

    # Der Erst-Admin meldet sich mit dem selbst gewählten Passwort an – unter der eigenen Adresse.
    login = await client.post(
        "/auth/login",
        json={"email": "nina@neue-firma.example", "password": "sehr-geheim-123"},
        headers={"Host": "neue-firma.hr3000.de"},
    )
    assert login.status_code == 200, login.text
    # ... aber nicht bei einer anderen Firma.
    other = await client.post(
        "/auth/login",
        json={"email": "nina@neue-firma.example", "password": "sehr-geheim-123"},
        headers={"Host": "musterfirma.hr3000.de"},
    )
    assert other.status_code == 401


async def test_taken_address_is_rejected_without_side_effects(client, db_session, platform):
    before = await _tenant_count(db_session)
    response = await client.post(SIGNUP, json=_payload(subdomain="musterfirma"), headers=WEBSITE)
    assert response.status_code == 409
    assert response.json()["code"] == "SUBDOMAIN_TAKEN"
    assert await _tenant_count(db_session) == before
    assert await db_session.scalar(select(func.count()).select_from(Account).where(Account.email == "nina@neue-firma.example")) == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"subdomain": "admin"},  # reserviert
        {"subdomain": "kiosk"},
        {"subdomain": "www"},
        {"subdomain": "Neue-Firma"},  # nur Kleinbuchstaben
        {"subdomain": "neue.firma"},
        {"subdomain": "-neu"},
        {"subdomain": "a" * 64},
        {"company_name": "X"},
        {"contact_name": ""},
        {"email": "keine-mail"},
        {"password": "kurz12345"},  # 9 Zeichen
        {"password": "ä" * 37},  # 74 Byte > bcrypt-Grenze
        {"is_business": False},
        {"accept_terms": False},
        {"website": "http://spam.example"},  # Honeypot ausgefüllt
    ],
)
async def test_invalid_signup_is_rejected(client, db_session, platform, overrides):
    before = await _tenant_count(db_session)
    response = await client.post(SIGNUP, json=_payload(**overrides), headers=WEBSITE)
    assert response.status_code == 422, (overrides, response.text)
    assert await _tenant_count(db_session) == before


@pytest.mark.parametrize("missing", ["is_business", "accept_terms", "email", "password", "subdomain"])
async def test_required_fields(client, platform, missing):
    data = _payload()
    del data[missing]
    assert (await client.post(SIGNUP, json=data, headers=WEBSITE)).status_code == 422


async def test_password_at_bcrypt_limit_is_accepted(client, platform):
    response = await client.post(SIGNUP, json=_payload(password="ä" * 36), headers=WEBSITE)  # genau 72 Byte
    assert response.status_code == 201, response.text


async def test_signups_per_ip_are_limited_and_failures_do_not_count(client, platform, monkeypatch):
    monkeypatch.setattr(settings, "self_signup_per_ip_per_day", 2)
    assert (await client.post(SIGNUP, json=_payload(subdomain="musterfirma"), headers=WEBSITE)).status_code == 409
    for i in range(2):
        response = await client.post(SIGNUP, json=_payload(subdomain=f"firma-{i}", email=f"a{i}@example.com"), headers=WEBSITE)
        assert response.status_code == 201, response.text
    blocked = await client.post(SIGNUP, json=_payload(subdomain="firma-x", email="x@example.com"), headers=WEBSITE)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "TOO_MANY_SIGNUPS"


async def test_platform_wide_daily_limit(client, platform, monkeypatch):
    monkeypatch.setattr(settings, "self_signup_per_day", 1)
    assert (await client.post(SIGNUP, json=_payload(), headers=WEBSITE)).status_code == 201
    blocked = await client.post(SIGNUP, json=_payload(subdomain="zweite", email="b@example.com"), headers=WEBSITE)
    assert blocked.status_code == 429


async def test_signup_can_be_switched_off(client, db_session, platform, monkeypatch):
    monkeypatch.setattr(settings, "self_signup_enabled", False)
    response = await client.post(SIGNUP, json=_payload(), headers=WEBSITE)
    assert response.status_code == 404 and response.json()["code"] == "SIGNUP_DISABLED"
    assert (await client.get(AVAILABLE, params={"subdomain": "frei"}, headers=WEBSITE)).status_code == 404


async def test_signup_needs_platform_domain(client, platform, monkeypatch):
    monkeypatch.setattr(settings, "tenant_base_domain", None)
    response = await client.post(SIGNUP, json=_payload(), headers=WEBSITE)
    assert response.status_code == 404 and response.json()["code"] == "SIGNUP_DISABLED"


async def test_address_availability(client, db_session, platform):
    db_session.add(Tenant(subdomain="gesperrt", name="Gesperrt GmbH", status=TenantStatus.SUSPENDED))
    await db_session.commit()

    async def check(subdomain: str):
        return await client.get(AVAILABLE, params={"subdomain": subdomain}, headers=WEBSITE)

    assert (await check("noch-frei")).json() == {"available": True, "reason": None}
    assert (await check("musterfirma")).json() == {"available": False, "reason": "TAKEN"}
    assert (await check("gesperrt")).json() == {"available": False, "reason": "TAKEN"}  # bleibt belegt
    assert (await check("admin")).json() == {"available": False, "reason": "RESERVED"}
    assert (await check("Gross")).status_code == 422


async def test_availability_checks_are_rate_limited(client, platform):
    for i in range(60):
        assert (await client.get(AVAILABLE, params={"subdomain": f"name{i}"}, headers=WEBSITE)).status_code == 200
    assert (await client.get(AVAILABLE, params={"subdomain": "noch-einer"}, headers=WEBSITE)).status_code == 429


async def test_super_admin_sees_self_signups(client, db_session, platform):
    db_session.add(Account(tenant_id=None, email="chef@example.com", password_hash=hash_password("pw"), role=HrRole.SUPER_ADMIN))
    await db_session.commit()
    assert (await client.post(SIGNUP, json=_payload(), headers=WEBSITE)).status_code == 201

    admin_host = {"Host": settings.super_admin_hostname}
    token = (
        await client.post("/auth/login", json={"email": "chef@example.com", "password": "pw"}, headers=admin_host)
    ).json()["access_token"]
    tenants = (await client.get("/tenants", headers={**admin_host, "Authorization": f"Bearer {token}"})).json()
    by_subdomain = {t["subdomain"]: t for t in tenants}
    assert by_subdomain["neue-firma"]["self_signup"] is True
    assert by_subdomain["neue-firma"]["created_at"] is not None
    assert by_subdomain["musterfirma"]["self_signup"] is False
