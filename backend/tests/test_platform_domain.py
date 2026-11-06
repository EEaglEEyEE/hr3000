"""Plattform-Domain (TENANT_BASE_DOMAIN): Mandanten unter firma.hr3000.de und
kiosk.firma.hr3000.de – Zertifikats-Freigabe für Caddys On-Demand-TLS, Mandanten-Zuordnung,
Kiosk-Adresse für den QR-Code und Login-Adressen neuer Mandanten."""

import pytest
from starlette.requests import Request

from app.config import settings
from app.models import Device, HrRole, HrUser, Location, Tenant, TenantStatus
from app.services.auth_service import hash_password
from app.services.credentials_mail import login_url
from app.services.platform_domain import kiosk_url_for_host, tenant_subdomain_for_host

ASK = "/internal/tls-allowed"


@pytest.fixture
def base_domain(monkeypatch):
    monkeypatch.setattr(settings, "tenant_base_domain", "hr3000.de")


async def _ask(client, domain: str) -> int:
    response = await client.get(ASK, params={"domain": domain})
    return response.status_code


# --- Zertifikats-Freigabe ------------------------------------------------------------


@pytest.mark.parametrize(
    "domain",
    [
        "musterfirma.hr3000.de",
        "kiosk.musterfirma.hr3000.de",
        "MUSTERFIRMA.HR3000.DE",
        "Kiosk.Musterfirma.hr3000.de.",
    ],
)
async def test_existing_tenant_gets_certificate(client, base_domain, domain):
    assert await _ask(client, domain) == 200


@pytest.mark.parametrize(
    "domain",
    [
        "unbekannt.hr3000.de",  # kein Mandant
        "kiosk.unbekannt.hr3000.de",
        "musterfirma.kiosk.hr3000.de",  # altes Schema unter der Plattform-Domain – gibt es nicht mehr
        "www.musterfirma.hr3000.de",  # nur "kiosk." ist als Vorsatz erlaubt
        "kiosk.kiosk.musterfirma.hr3000.de",
        "kiosk.x.musterfirma.hr3000.de",
        "x.musterfirma.hr3000.de",
        "hr3000.de",  # Apex – kein Mandant
        "www.hr3000.de",
        "kiosk.hr3000.de",  # "kiosk" ist reserviert, nie ein Mandant
        "musterfirma.hr3000xde",  # Punkt der Domain ist kein Platzhalter
        "musterfirma.hr3000.de.evil.example",  # fremde Domain
        "kiosk.musterfirma.evil.example",
        "musterfirma",
        "-musterfirma.hr3000.de",
    ],
)
async def test_other_names_get_no_certificate(client, base_domain, domain):
    assert await _ask(client, domain) == 404


async def test_denial_uses_error_format(client, base_domain):
    response = await client.get(ASK, params={"domain": "unbekannt.hr3000.de"})
    assert response.json()["code"] == "TLS_NOT_ALLOWED"


async def test_suspended_tenant_gets_no_certificate(client, db_session, base_domain):
    db_session.add(Tenant(subdomain="gesperrt", name="Gesperrt GmbH", status=TenantStatus.SUSPENDED))
    db_session.add(Tenant(subdomain="testphase", name="Trial GmbH", status=TenantStatus.TRIAL))
    await db_session.commit()
    assert await _ask(client, "gesperrt.hr3000.de") == 404
    assert await _ask(client, "kiosk.gesperrt.hr3000.de") == 404
    assert await _ask(client, "testphase.hr3000.de") == 200
    assert await _ask(client, "kiosk.testphase.hr3000.de") == 200


async def test_super_admin_host_always_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "tenant_base_domain", None)
    monkeypatch.setattr(settings, "super_admin_hostname", "admin.hr3000.de")
    assert await _ask(client, "admin.hr3000.de") == 200
    assert await _ask(client, "Admin.HR3000.de") == 200
    assert await _ask(client, "kiosk.admin.hr3000.de") == 404


async def test_without_base_domain_tenants_get_no_certificate(client, monkeypatch):
    # Ohne Plattform-Domain gibt es nur die fest eingetragenen Hosts (Zertifikat vorab).
    monkeypatch.setattr(settings, "tenant_base_domain", None)
    assert await _ask(client, "musterfirma.hr3000.de") == 404
    monkeypatch.setattr(settings, "tenant_base_domain", "  ")
    assert await _ask(client, "kiosk.musterfirma.hr3000.de") == 404


async def test_base_domain_is_normalised(client, monkeypatch):
    monkeypatch.setattr(settings, "tenant_base_domain", " HR3000.de. ")
    assert await _ask(client, "kiosk.musterfirma.hr3000.de") == 200


@pytest.mark.parametrize("params", [{}, {"domain": ""}, {"domain": "a" * 254}])
async def test_invalid_query_is_rejected(client, base_domain, params):
    response = await client.get(ASK, params=params)
    assert response.status_code == 422


async def test_ask_works_without_tenant_context(client, monkeypatch, base_domain):
    # Caddy fragt intern über backend:8000 – dieser Host ist kein Mandant. Ohne Debug-Modus
    # würde die Mandanten-Middleware sonst mit "Unbekannte Subdomain" abbrechen.
    monkeypatch.setattr(settings, "debug", False)
    response = await client.get(ASK, params={"domain": "musterfirma.hr3000.de"}, headers={"Host": "backend:8000"})
    assert response.status_code == 200
    other = await client.get("/employees", headers={"Host": "backend:8000"})
    assert other.json()["code"] == "TENANT_NOT_FOUND"


# --- Mandanten-Zuordnung über den Host --------------------------------------------------


@pytest.fixture
async def two_tenants(db_session, monkeypatch, base_domain):
    # Ohne Debug-Modus gibt es keinen Rückfall auf den Standard-Mandanten – jede Zuordnung
    # muss wirklich über den Host laufen.
    monkeypatch.setattr(settings, "debug", False)
    db_session.add(Tenant(subdomain="lassner", name="Lassner KG"))
    await db_session.commit()


@pytest.mark.parametrize(
    ("host", "name"),
    [
        ("lassner.hr3000.de", "Lassner KG"),
        ("kiosk.lassner.hr3000.de", "Lassner KG"),
        ("musterfirma.hr3000.de", "Musterfirma"),
        ("kiosk.musterfirma.hr3000.de", "Musterfirma"),
        ("KIOSK.Lassner.hr3000.de:443", "Lassner KG"),
        # Fest eingetragene Hosts außerhalb der Plattform-Domain: weiter erster Hostname-Teil.
        ("lassner.hr.lassners.de", "Lassner KG"),
        ("lassner.kiosk.hr.lassners.de", "Lassner KG"),
    ],
)
async def test_host_resolves_tenant(client, two_tenants, host, name):
    response = await client.get("/branding", headers={"Host": host})
    assert response.status_code == 200, response.text
    assert response.json()["tenant_name"] == name


@pytest.mark.parametrize("host", ["kiosk.unbekannt.hr3000.de", "kiosk.hr3000.de", "unbekannt.hr3000.de"])
async def test_unknown_platform_host_is_rejected(client, two_tenants, host):
    response = await client.get("/branding", headers={"Host": host})
    assert response.status_code == 404
    assert response.json()["code"] == "TENANT_NOT_FOUND"


async def test_kiosk_host_cannot_reach_other_tenant(client, two_tenants, db_session):
    # Ein Login am Kiosk-Host von Lassner gilt nicht für Musterfirma (Mandantentrennung).
    db_session.add(HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR, tenant_id=1))
    await db_session.commit()
    login = await client.post(
        "/auth/hr/login", json={"email": "hr@example.com", "password": "pw"}, headers={"Host": "kiosk.musterfirma.hr3000.de"}
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    own = await client.get("/employees", headers={"Host": "musterfirma.hr3000.de", "Authorization": f"Bearer {token}"})
    assert own.status_code == 200
    foreign = await client.get("/employees", headers={"Host": "kiosk.lassner.hr3000.de", "Authorization": f"Bearer {token}"})
    assert foreign.status_code in (401, 403)


def test_subdomain_extraction(base_domain):
    assert tenant_subdomain_for_host("firma-1.hr3000.de") == "firma-1"
    assert tenant_subdomain_for_host("kiosk.firma-1.hr3000.de") == "firma-1"
    assert tenant_subdomain_for_host("kiosk.hr3000.de") == "kiosk"  # Format passt, Mandant gibt es nie
    assert tenant_subdomain_for_host("firma-1.kiosk.hr3000.de") is None
    assert tenant_subdomain_for_host("a.b.hr3000.de") is None
    assert tenant_subdomain_for_host("firma.hr3000.de.example") is None


# --- Kiosk-Adresse für den QR-Code -------------------------------------------------------


def test_kiosk_url_for_platform_and_fixed_hosts(base_domain):
    assert kiosk_url_for_host("lassner.hr3000.de") == "https://kiosk.lassner.hr3000.de/"
    assert kiosk_url_for_host("Lassner.HR3000.de:443") == "https://kiosk.lassner.hr3000.de/"
    # Altes Schema für fest eingetragene Hosts – die Tablets dort laufen unverändert weiter.
    assert kiosk_url_for_host("lassner.hr.lassners.de", "https") == "https://lassner.kiosk.hr.lassners.de/"
    # Lokale Entwicklung: keine sinnvolle Adresse -> nur das Token kodieren.
    assert kiosk_url_for_host("localhost:5180", "http") is None


def test_kiosk_url_without_base_domain_keeps_old_scheme(monkeypatch):
    monkeypatch.setattr(settings, "tenant_base_domain", None)
    assert kiosk_url_for_host("lassner.hr3000.de", "https") == "https://lassner.kiosk.hr3000.de/"


async def test_pairing_code_returns_kiosk_url(client, db_session, base_domain):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    device = Device(name="Tablet", location_id=location.id, device_token="long-device-token-123456")
    db_session.add_all([device, HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR)])
    await db_session.commit()
    host = {"Host": "musterfirma.hr3000.de"}
    token = (
        await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"}, headers=host)
    ).json()["access_token"]
    response = await client.post(
        f"/devices/{device.id}/pairing-code", headers={**host, "Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["kiosk_url"] == "https://kiosk.musterfirma.hr3000.de/"


# --- Login-Adressen ----------------------------------------------------------------------


def _request(host: str, scheme: str = "http") -> Request:
    return Request({"type": "http", "scheme": scheme, "headers": [(b"host", host.encode())], "path": "/", "query_string": b""})


def test_login_url_uses_platform_domain(base_domain):
    # Super-Admin legt Mandanten an: Link immer auf die Plattform-Domain, egal von wo.
    assert login_url(_request("admin.hr.lassners.de"), "neu") == "https://neu.hr3000.de"
    assert login_url(_request("admin.hr3000.de", "https"), "neu") == "https://neu.hr3000.de"


def test_login_url_without_platform_domain_keeps_old_behaviour(monkeypatch):
    monkeypatch.setattr(settings, "tenant_base_domain", None)
    assert login_url(_request("admin.hr.lassners.de", "https"), "neu") == "https://neu.hr.lassners.de"


def test_login_url_without_subdomain_is_current_host(base_domain):
    # Zugangsdaten für Mitarbeiter innerhalb eines Mandanten: aktuelle Adresse bleibt.
    assert login_url(_request("lassner.hr.lassners.de", "https")) == "https://lassner.hr.lassners.de"


# --- Testumgebung (scripts/staging.sh): Zertifikate für deren Hosts entscheidet das Staging-Backend ---


async def test_staging_hosts_are_asked_at_the_staging_backend(client, db_session, base_domain, monkeypatch) -> None:
    import types

    import httpx

    import app.api.tls as tls_module

    monkeypatch.setattr(settings, "staging_base_domain", "test.hr3000.de")
    asked: list[str] = []
    down = {"value": False}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def get(self, url, params=None, **kwargs):
            if down["value"]:
                raise httpx.ConnectError("staging down")
            asked.append(params["domain"])
            return httpx.Response(200 if params["domain"] == "demo.test.hr3000.de" else 404)

    monkeypatch.setattr(tls_module, "httpx", types.SimpleNamespace(AsyncClient=FakeClient, HTTPError=httpx.HTTPError))
    assert await _ask(client, "demo.test.hr3000.de") == 200
    assert await _ask(client, "kiosk.fremd.test.hr3000.de") == 404
    assert asked == ["demo.test.hr3000.de", "kiosk.fremd.test.hr3000.de"]
    down["value"] = True
    assert await _ask(client, "demo.test.hr3000.de") == 404  # Testumgebung aus -> kein Zertifikat
    monkeypatch.setattr(settings, "staging_base_domain", None)
    down["value"] = False
    assert await _ask(client, "demo.test.hr3000.de") == 404
    assert asked == ["demo.test.hr3000.de", "kiosk.fremd.test.hr3000.de"]  # ohne Testumgebung nicht gefragt
