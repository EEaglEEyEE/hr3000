"""Website-Login (hr3000.de/login): Firma über ihr Kürzel finden und weiterleiten."""

import pytest

from app.config import settings
from app.models import Tenant, TenantStatus

LOOKUP = "/public/tenant-lookup"
WEBSITE = {"Host": "hr3000.de"}


@pytest.fixture
def platform(monkeypatch):
    monkeypatch.setattr(settings, "tenant_base_domain", "hr3000.de")
    # Ohne Debug-Modus: kein Rückfall auf den Standard-Mandanten, die Website hat keinen.
    monkeypatch.setattr(settings, "debug", False)


async def test_existing_tenant_returns_login_url(client, platform):
    response = await client.get(LOOKUP, params={"subdomain": "musterfirma"}, headers=WEBSITE)
    assert response.status_code == 200, response.text
    assert response.json() == {"login_url": "https://musterfirma.hr3000.de/"}


async def test_works_from_www_and_without_host(client, platform):
    for host in ("www.hr3000.de", "backend:8000"):
        response = await client.get(LOOKUP, params={"subdomain": "musterfirma"}, headers={"Host": host})
        assert response.status_code == 200, (host, response.text)


@pytest.mark.parametrize("subdomain", ["unbekannt", "admin", "www", "kiosk"])
async def test_unknown_or_reserved_name_is_not_found(client, platform, subdomain):
    response = await client.get(LOOKUP, params={"subdomain": subdomain}, headers=WEBSITE)
    assert response.status_code == 404
    assert response.json()["code"] == "TENANT_NOT_FOUND"


async def test_suspended_tenant_is_not_found(client, db_session, platform):
    db_session.add(Tenant(subdomain="gesperrt", name="Gesperrt GmbH", status=TenantStatus.SUSPENDED))
    db_session.add(Tenant(subdomain="testphase", name="Trial GmbH", status=TenantStatus.TRIAL))
    await db_session.commit()
    assert (await client.get(LOOKUP, params={"subdomain": "gesperrt"}, headers=WEBSITE)).status_code == 404
    assert (await client.get(LOOKUP, params={"subdomain": "testphase"}, headers=WEBSITE)).status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"subdomain": ""},
        {"subdomain": "Musterfirma"},  # die Website schreibt klein, der Server nimmt nur Kleinbuchstaben
        {"subdomain": "musterfirma.hr3000.de"},
        {"subdomain": "-musterfirma"},
        {"subdomain": "a" * 64},
        {"subdomain": "evil/../x"},
    ],
)
async def test_invalid_input_is_rejected(client, platform, params):
    response = await client.get(LOOKUP, params=params, headers=WEBSITE)
    assert response.status_code == 422


async def test_without_platform_domain_nothing_is_found(client, monkeypatch, platform):
    monkeypatch.setattr(settings, "tenant_base_domain", None)
    response = await client.get(LOOKUP, params={"subdomain": "musterfirma"}, headers=WEBSITE)
    assert response.status_code == 404


async def test_guessing_is_rate_limited_but_hits_do_not_count(client, platform):
    for _ in range(30):  # Treffer zählen nicht
        assert (await client.get(LOOKUP, params={"subdomain": "musterfirma"}, headers=WEBSITE)).status_code == 200
    for i in range(20):
        assert (await client.get(LOOKUP, params={"subdomain": f"rate{i}"}, headers=WEBSITE)).status_code == 404
    blocked = await client.get(LOOKUP, params={"subdomain": "musterfirma"}, headers=WEBSITE)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "TOO_MANY_LOOKUPS"


async def test_other_api_paths_stay_closed_on_website_host(client, platform):
    # Die Website ist kein Mandant – alles außer der Firmen-Suche bleibt dort zu.
    response = await client.get("/branding", headers=WEBSITE)
    assert response.status_code == 404
    assert response.json()["code"] == "TENANT_NOT_FOUND"


def test_public_calls_are_not_written_to_access_log():
    # Datenschutzerklärung der Website: Firmensuche ohne IP im Zugriffsprotokoll.
    import logging

    from app.main import SkipPublicAccessLog

    def record(path: str) -> logging.LogRecord:
        return logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
            ("203.0.113.7:5000", "GET", path, "1.1", 200), None,
        )

    log_filter = SkipPublicAccessLog()
    assert log_filter.filter(record("/public/tenant-lookup?subdomain=lassner")) is False
    assert log_filter.filter(record("/employees")) is True
    assert log_filter.filter(record("/internal/tls-allowed?domain=x")) is True
    assert any(isinstance(f, SkipPublicAccessLog) for f in logging.getLogger("uvicorn.access").filters)
