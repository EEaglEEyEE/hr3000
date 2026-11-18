"""Integrationstests für GET /metrics (app/api/metrics.py, app/services/monitoring.py) und die
HTTP-Middleware in app/main.py: Schutz (Proxy-Header, Token), Kennzahlen mehrerer Mandanten,
Datenbankfehler, OpenAPI und Zählung nach Routenvorlage."""
import re
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.monitoring as monitoring
from app import metrics
from app.config import settings
from app.db import get_db
from app.main import app
from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    CorrectionRequestKind,
    CorrectionRequestStatus,
    DataChangeRequest,
    Device,
    Employee,
    Location,
    Punch,
    PunchCorrectionRequest,
    Tenant,
)
from app.models.punch import PunchSource, PunchType
from app.services import email_service

NOW = datetime(2026, 11, 18, 12, 0, 0)


@pytest.fixture(autouse=True)
def _metrics_state(monkeypatch: pytest.MonkeyPatch):
    metrics.reset()
    monkeypatch.setattr(settings, "metrics_token", None)
    monkeypatch.setattr(monitoring, "_utcnow", lambda: NOW)
    yield
    metrics.reset()


def _samples(text: str) -> dict[str, float]:
    """Messwertzeilen als {'name{labels}': wert}."""
    result: dict[str, float] = {}
    for line in text.strip().split("\n"):
        if line.startswith("#") or not line:
            continue
        key, value = line.rsplit(" ", 1)
        result[key] = float(value.replace("+Inf", "inf"))
    return result


async def _seed(db: AsyncSession) -> None:
    """Zwei weitere Mandanten neben „musterfirma“ (id 1, aus conftest): „acme“ (2) und „leer“ (3)."""
    db.add_all([Tenant(id=2, subdomain="acme", name="Acme GmbH"), Tenant(id=3, subdomain="leer", name="Leer")])
    await db.flush()
    db.add_all([
        Location(id=1, tenant_id=1, name="Zentrale", timezone="Europe/Berlin"),
        Location(id=2, tenant_id=2, name="Werk", timezone="Europe/Berlin"),
    ])
    await db.flush()
    db.add_all([
        Employee(id=1, tenant_id=1, location_id=1, first_name="Anna", last_name="A", employee_number="1"),
        Employee(id=2, tenant_id=1, location_id=1, first_name="Bernd", last_name="B", employee_number="2"),
        Employee(id=3, tenant_id=1, location_id=1, first_name="Carla", last_name="C", employee_number="3", active=False),
        Employee(id=4, tenant_id=2, location_id=2, first_name="Dora", last_name="D", employee_number="1"),
    ])
    db.add_all([
        Device(id=10, tenant_id=1, location_id=1, token_hash="a" * 64, name="Eingang", last_seen=NOW - timedelta(seconds=90)),
        Device(id=11, tenant_id=1, location_id=1, token_hash="b" * 64, name="Nie gemeldet"),
        Device(id=20, tenant_id=2, location_id=2, token_hash="c" * 64, name="Halle",
               last_seen=NOW - timedelta(hours=2)),
    ])
    await db.flush()

    def punch(employee_id: int, tenant_id: int, location_id: int, at: datetime) -> Punch:
        return Punch(tenant_id=tenant_id, employee_id=employee_id, location_id=location_id, punch_type=PunchType.COME,
                     timestamp_utc=at, source=PunchSource.KIOSK)

    db.add_all([
        punch(1, 1, 1, NOW - timedelta(hours=1)),
        punch(2, 1, 1, NOW - timedelta(hours=23, minutes=59)),
        punch(1, 1, 1, NOW - timedelta(hours=24, minutes=1)),  # zu alt
        punch(2, 1, 1, NOW + timedelta(hours=1)),  # Zukunft zählt nicht
        punch(4, 2, 2, NOW - timedelta(minutes=5)),
    ])

    def absence(employee_id: int, status: AbsenceApprovalStatus) -> Absence:
        return Absence(employee_id=employee_id, type=AbsenceType.VACATION, date_from=date(2026, 12, 1),
                       date_to=date(2026, 12, 2), approval_status=status)

    db.add_all([
        absence(1, AbsenceApprovalStatus.PENDING),
        absence(2, AbsenceApprovalStatus.PENDING),
        absence(2, AbsenceApprovalStatus.APPROVED),
        absence(4, AbsenceApprovalStatus.REJECTED),
    ])

    def correction(tenant_id: int, employee_id: int, kind: CorrectionRequestKind,
                   status: CorrectionRequestStatus) -> PunchCorrectionRequest:
        return PunchCorrectionRequest(tenant_id=tenant_id, employee_id=employee_id, work_date=date(2026, 11, 17),
                                      kind=kind, items="[]", reason="vergessen", status=status)

    db.add_all([
        correction(1, 1, CorrectionRequestKind.CORRECTION, CorrectionRequestStatus.PENDING),
        correction(1, 2, CorrectionRequestKind.CORRECTION, CorrectionRequestStatus.APPROVED),
        correction(2, 4, CorrectionRequestKind.CORRECTION, CorrectionRequestStatus.PENDING),
        correction(2, 4, CorrectionRequestKind.TIME_ENTRY, CorrectionRequestStatus.PENDING),
        correction(2, 4, CorrectionRequestKind.TIME_ENTRY, CorrectionRequestStatus.PENDING),
    ])
    db.add_all([
        DataChangeRequest(tenant_id=2, employee_id=4, changes="x", status="PENDING"),
        DataChangeRequest(tenant_id=2, employee_id=4, changes="x", status="REJECTED"),
    ])
    await db.commit()


# --- Schutz ---------------------------------------------------------------------------------------


async def test_metrics_without_token_configured(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert response.text.endswith("\n")
    assert "hr_up 1" in response.text


async def test_metrics_requires_configured_token(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "metrics_token", "s3cr3t-token-for-tests")
    missing = await client.get("/metrics")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert "hr_up" not in missing.text


@pytest.mark.parametrize(
    "authorization",
    ["Bearer falsch", "Bearer s3cr3t-token-for-test", "s3cr3t-token-for-tests", "Basic s3cr3t-token-for-tests", "Bearer "],
)
async def test_metrics_wrong_token(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, authorization: str) -> None:
    monkeypatch.setattr(settings, "metrics_token", "s3cr3t-token-for-tests")
    response = await client.get("/metrics", headers={"Authorization": authorization})
    assert response.status_code == 401


async def test_metrics_correct_token(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "metrics_token", "s3cr3t-token-for-tests")
    response = await client.get("/metrics", headers={"Authorization": "Bearer s3cr3t-token-for-tests"})
    assert response.status_code == 200
    assert "hr_up 1" in response.text


async def test_empty_token_means_no_token(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "metrics_token", "")
    assert (await client.get("/metrics")).status_code == 200


@pytest.mark.parametrize(
    "header",
    [
        {"X-Forwarded-For": "203.0.113.7"},
        {"X-Forwarded-Host": "firma.hr3000.de"},
        {"X-Forwarded-Proto": "https"},
        {"Forwarded": "for=203.0.113.7;proto=https"},
        {"X-Real-IP": "203.0.113.7"},
    ],
)
async def test_metrics_via_proxy_is_404(client: AsyncClient, header: dict[str, str]) -> None:
    response = await client.get("/metrics", headers=header)
    assert response.status_code == 404
    assert response.text == ""


async def test_proxy_check_before_token(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auch mit richtigem Token kein Abruf über den Proxy (404, nicht 401/200)."""
    monkeypatch.setattr(settings, "metrics_token", "s3cr3t-token-for-tests")
    response = await client.get(
        "/metrics", headers={"Authorization": "Bearer s3cr3t-token-for-tests", "X-Forwarded-For": "203.0.113.7"}
    )
    assert response.status_code == 404


async def test_metrics_without_tenant_context(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Abruf über backend:8000 (kein Mandanten-Host) auch ohne Debug-Fallback auf die Testfirma."""
    monkeypatch.setattr(settings, "debug", False)
    response = await client.get("/metrics", headers={"Host": "backend:8000"})
    assert response.status_code == 200


@pytest.mark.parametrize("method", ["post", "put", "delete"])
async def test_metrics_only_get(client: AsyncClient, method: str) -> None:
    response = await getattr(client, method)("/metrics")
    assert response.status_code == 405


async def test_metrics_not_in_openapi() -> None:
    schema = app.openapi()
    assert "/metrics" not in schema["paths"]
    assert all("metrics" not in path or "server-metrics" in path for path in schema["paths"])


# --- Kennzahlen -----------------------------------------------------------------------------------


async def test_metrics_values_for_several_tenants(client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed(db_session)
    text = (await client.get("/metrics")).text
    values = _samples(text)

    assert values["hr_up"] == 1
    assert values["hr_tenants"] == 3

    assert values['hr_employees_active{tenant="musterfirma"}'] == 2
    assert values['hr_employees_active{tenant="acme"}'] == 1
    assert values['hr_employees_active{tenant="leer"}'] == 0

    assert values['hr_punches_24h{tenant="musterfirma"}'] == 2
    assert values['hr_punches_24h{tenant="acme"}'] == 1
    assert values['hr_punches_24h{tenant="leer"}'] == 0

    assert values['hr_open_requests{tenant="musterfirma",kind="absence"}'] == 2
    assert values['hr_open_requests{tenant="musterfirma",kind="punch_correction"}'] == 1
    assert values['hr_open_requests{tenant="musterfirma",kind="time_entry"}'] == 0
    assert values['hr_open_requests{tenant="musterfirma",kind="data_change"}'] == 0
    assert values['hr_open_requests{tenant="acme",kind="absence"}'] == 0
    assert values['hr_open_requests{tenant="acme",kind="punch_correction"}'] == 1
    assert values['hr_open_requests{tenant="acme",kind="time_entry"}'] == 2
    assert values['hr_open_requests{tenant="acme",kind="data_change"}'] == 1
    assert values['hr_open_requests{tenant="leer",kind="absence"}'] == 0

    assert values['hr_kiosk_last_seen_seconds{tenant="musterfirma",device="10"}'] == 90
    assert values['hr_kiosk_last_seen_seconds{tenant="acme",device="20"}'] == 7200
    assert not any('device="11"' in key for key in values)  # nie gemeldet: keine Zeile

    assert values["hr_mail_failures_total"] == 0


async def test_metrics_contain_no_personal_data(client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed(db_session)
    text = (await client.get("/metrics")).text
    for forbidden in ("Anna", "Bernd", "Dora", "Acme GmbH", "Eingang", "Halle", "vergessen", "Zentrale", "@"):
        assert forbidden not in text


async def test_metrics_format_types_declared_once(client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed(db_session)
    await client.get("/health")
    text = (await client.get("/metrics")).text
    types = re.findall(r"^# TYPE (\S+) (\S+)$", text, flags=re.M)
    names = [name for name, _ in types]
    assert len(names) == len(set(names))
    assert dict(types) == {
        "hr_up": "gauge",
        "hr_tenants": "gauge",
        "hr_employees_active": "gauge",
        "hr_punches_24h": "gauge",
        "hr_open_requests": "gauge",
        "hr_kiosk_last_seen_seconds": "gauge",
        "hr_http_requests_total": "counter",
        "hr_http_request_duration_seconds": "histogram",
        "hr_mail_failures_total": "counter",
    }


async def test_metrics_empty_database(client: AsyncClient, db_session: AsyncSession) -> None:
    """Nur der Standardmandant ohne Daten: Nullwerte statt fehlender Zeilen, keine Tablets."""
    values = _samples((await client.get("/metrics")).text)
    assert values["hr_tenants"] == 1
    assert values['hr_employees_active{tenant="musterfirma"}'] == 0
    assert values['hr_punches_24h{tenant="musterfirma"}'] == 0
    assert not any(key.startswith("hr_kiosk_last_seen_seconds") for key in values)


async def test_kiosk_last_seen_with_timezone(client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(Location(id=1, tenant_id=1, name="Zentrale", timezone="Europe/Berlin"))
    await db_session.flush()
    db_session.add(Device(id=5, tenant_id=1, location_id=1, token_hash="d" * 64, name="T",
                          last_seen=(NOW - timedelta(minutes=10)).replace(tzinfo=UTC)))
    await db_session.commit()
    values = _samples((await client.get("/metrics")).text)
    assert values['hr_kiosk_last_seen_seconds{tenant="musterfirma",device="5"}'] == 600


async def test_tenant_label_is_escaped(client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(Tenant(id=2, subdomain='a"b', name="Komisch"))
    await db_session.commit()
    text = (await client.get("/metrics")).text
    assert 'hr_employees_active{tenant="a\\"b"} 0' in text


class _BrokenSession:
    async def execute(self, *args, **kwargs):
        raise ConnectionError("MySQL weg")


async def test_database_error_reports_up_zero(client: AsyncClient) -> None:
    async def broken_db():
        yield _BrokenSession()

    app.dependency_overrides[get_db] = broken_db
    metrics.MAIL_FAILURES.inc()
    response = await client.get("/metrics")
    assert response.status_code == 200
    values = _samples(response.text)
    assert values["hr_up"] == 0
    assert values["hr_mail_failures_total"] == 1  # Prozesszähler bleiben
    for name in ("hr_tenants", "hr_employees_active", "hr_punches_24h", "hr_open_requests", "hr_kiosk_last_seen"):
        assert name not in response.text


async def test_database_gauges_directly_with_explicit_now(db_session: AsyncSession) -> None:
    await _seed(db_session)
    lines = await monitoring.database_gauges(db_session, now=lambda: NOW + timedelta(seconds=10))
    assert 'hr_kiosk_last_seen_seconds{tenant="musterfirma",device="10"} 100' in lines


# --- Mailfehler -----------------------------------------------------------------------------------


async def test_mail_failure_is_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise OSError("SMTP nicht erreichbar")

    monkeypatch.setattr(email_service, "_send_sync", fail)
    config = email_service.SmtpConfig(host="smtp.example.com")
    assert await email_service.send_email("a@example.com", "Betreff", "Text", config=config) is False
    with pytest.raises(OSError):
        await email_service.send_email("a@example.com", "Betreff", "Text", config=config, raise_errors=True)
    assert metrics.MAIL_FAILURES.value() == 2


async def test_mail_success_and_no_smtp_not_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_service, "_send_sync", lambda *args, **kwargs: None)
    assert await email_service.send_email("a@example.com", "B", "T", config=email_service.SmtpConfig(host="x")) is True
    monkeypatch.setattr(email_service, "platform_smtp_config", lambda: None)
    assert await email_service.send_email("a@example.com", "B", "T") is False
    assert metrics.MAIL_FAILURES.value() == 0


# --- HTTP-Middleware ------------------------------------------------------------------------------


async def test_middleware_counts_route_template(client: AsyncClient) -> None:
    for employee_id in (101, 102, 103):
        await client.get(f"/employees/{employee_id}")
    assert metrics.HTTP_REQUESTS.value(route="/employees/{employee_id}", method="GET", status="401") == 3
    assert metrics.HTTP_SECONDS.count(route="/employees/{employee_id}", method="GET") == 3
    text = (await client.get("/metrics")).text
    assert 'hr_http_requests_total{route="/employees/{employee_id}",method="GET",status="401"} 3' in text
    assert "/employees/101" not in text
    assert 'hr_http_request_duration_seconds_count{route="/employees/{employee_id}",method="GET"} 3' in text


async def test_middleware_counts_health_and_status(client: AsyncClient) -> None:
    await client.get("/health")
    await client.get("/health")
    assert metrics.HTTP_REQUESTS.value(route="/health", method="GET", status="200") == 2


async def test_middleware_unmatched_path(client: AsyncClient) -> None:
    await client.get("/gibt-es-nicht/12345")
    assert metrics.HTTP_REQUESTS.value(route="unmatched", method="GET", status="404") == 1
    assert "12345" not in (await client.get("/metrics")).text


async def test_middleware_counts_unknown_tenant_as_unmatched(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "debug", False)
    response = await client.get("/employees", headers={"Host": "unbekannt.hr3000.de"})
    assert response.status_code == 404
    assert metrics.HTTP_REQUESTS.value(route="unmatched", method="GET", status="404") == 1


async def test_middleware_skips_metrics_endpoint(client: AsyncClient) -> None:
    await client.get("/metrics")
    await client.get("/metrics", headers={"X-Forwarded-For": "203.0.113.7"})
    assert metrics.HTTP_REQUESTS.value(route="/metrics", method="GET", status="200") == 0
    assert metrics.HTTP_REQUESTS.value(route="/metrics", method="GET", status="404") == 0
    assert metrics.HTTP_SECONDS.count(route="/metrics", method="GET") == 0
    text = (await client.get("/metrics")).text
    assert 'route="/metrics"' not in text


async def test_middleware_counts_method_separately(client: AsyncClient) -> None:
    await client.post("/health")
    assert metrics.HTTP_REQUESTS.value(route="/health", method="POST", status="405") == 1


async def test_middleware_counts_exception_as_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ein unbehandelter Fehler in einer Route zählt als 500 unter der Routenvorlage."""
    from app.api import tls

    def boom(*args, **kwargs):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(settings, "super_admin_hostname", "admin.example.com")
    monkeypatch.setattr(tls, "tenant_subdomain_for_host", boom)

    async def no_db():
        yield None

    app.dependency_overrides[get_db] = no_db
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as plain:
            response = await plain.get("/internal/tls-allowed", params={"domain": "x.example.com"})
        assert response.status_code == 500
    finally:
        app.dependency_overrides.clear()
    assert metrics.HTTP_REQUESTS.value(route="/internal/tls-allowed", method="GET", status="500") == 1
