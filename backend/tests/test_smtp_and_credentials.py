from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.settings as settings_api
from app.config import settings as app_settings
from app.models import (
    Absence,
    AbsenceApprovalStatus,
    AbsenceType,
    AppSettings,
    Employee,
    HrRole,
    HrUser,
    Location,
)
from app.services import email_service
from app.services.auth_service import hash_password
from app.services.secret_box import decrypt_secret


_REAL_RESOLVE = email_service._resolve_public_ip


class _Recorder:
    """Ersatz für die SMTP-Verbindung (email_service._connect): merkt sich
    Konfiguration, angepinnte IP und gesendete Nachrichten."""

    connections: list[dict] = []
    messages: list = []
    fail = False

    def __init__(self, config, pinned_ip):
        self.info = {"host": config.host, "port": config.port, "security": config.security, "pinned": pinned_ip}
        _Recorder.connections.append(self.info)

    def __enter__(self):
        if _Recorder.fail:
            raise OSError("Verbindung abgelehnt")
        return self

    def __exit__(self, *args):
        return False

    def starttls(self, **kwargs):
        self.info["starttls"] = True

    def login(self, user, password):
        self.info["login"] = (user, password)

    def send_message(self, message):
        _Recorder.messages.append(message)


@pytest.fixture(autouse=True)
def _smtp(monkeypatch):
    _Recorder.connections = []
    _Recorder.messages = []
    _Recorder.fail = False
    monkeypatch.setattr(email_service, "_connect", lambda config, pinned_ip, context: _Recorder(config, pinned_ip))
    # Kein echtes DNS in Tests: jeder Host löst auf eine öffentliche Dokumentations-IP auf.
    monkeypatch.setattr(email_service, "_resolve_public_ip", lambda host: "203.0.113.7")
    originals = (app_settings.smtp_host, app_settings.smtp_user, app_settings.smtp_password)
    app_settings.smtp_host = None
    yield
    app_settings.smtp_host, app_settings.smtp_user, app_settings.smtp_password = originals


@pytest.fixture
def allow_hosts(monkeypatch):
    async def _ok(host: str) -> None:
        return None

    monkeypatch.setattr(settings_api, "ensure_public_smtp_host", _ok)


async def _admin(db_session: AsyncSession, client: AsyncClient, role: HrRole = HrRole.ADMIN):
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    db_session.add(HrUser(email="admin@example.com", password_hash=hash_password("pw"), role=role))
    await db_session.commit()
    await db_session.refresh(location)
    login = await client.post("/auth/hr/login", json={"email": "admin@example.com", "password": "pw"})
    return location, {"Authorization": f"Bearer {login.json()['access_token']}"}


_TENANT_SMTP = {
    "smtp_host": "mail.kunde.de",
    "smtp_port": 465,
    "smtp_user": "hr@kunde.de",
    "smtp_password": "geheim-123",
    "smtp_from": "hr@kunde.de",
    "smtp_security": "SSL",
}


async def test_smtp_settings_saved_encrypted_and_password_never_returned(
    client: AsyncClient, db_session: AsyncSession, allow_hosts
) -> None:
    _, headers = await _admin(db_session, client)

    response = await client.patch("/settings", headers=headers, json=_TENANT_SMTP)

    assert response.status_code == 200
    body = response.json()
    assert body["smtp_host"] == "mail.kunde.de"
    assert body["smtp_security"] == "SSL"
    assert body["smtp_password_set"] is True
    assert "smtp_password" not in body and "geheim-123" not in response.text

    row = (await db_session.execute(select(AppSettings))).scalars().first()
    assert row.smtp_password_encrypted != "geheim-123"
    assert decrypt_secret(row.smtp_password_encrypted) == "geheim-123"

    entries = (await client.get("/audit-log", headers=headers)).json()
    assert all("geheim-123" not in (e["detail"] or "") for e in entries)


async def test_internal_smtp_host_is_rejected(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(email_service, "_resolve_public_ip", _REAL_RESOLVE)  # echte Prüfung (IP-Literale, kein DNS)
    _, headers = await _admin(db_session, client)

    for host in ("127.0.0.1", "10.0.0.5", "169.254.169.254"):
        response = await client.patch("/settings", headers=headers, json={"smtp_host": host})
        assert response.status_code == 400, host
        assert response.json()["code"] == "SMTP_HOST_NOT_ALLOWED"


async def test_invalid_smtp_input_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _admin(db_session, client)

    for payload in (
        {"smtp_host": "bad host!"},
        {"smtp_port": 0},
        {"smtp_port": 70000},
        {"smtp_from": "keine-mail"},
        {"smtp_security": "TLS13"},
    ):
        response = await client.patch("/settings", headers=headers, json=payload)
        assert response.status_code == 422, payload


async def test_smtp_test_uses_tenant_server_and_reports_failure(
    client: AsyncClient, db_session: AsyncSession, allow_hosts
) -> None:
    _, headers = await _admin(db_session, client)
    await client.patch("/settings", headers=headers, json=_TENANT_SMTP)

    ok = await client.post("/settings/smtp-test", headers=headers, json={})
    assert ok.status_code == 200
    assert ok.json()["sent_to"] == "admin@example.com"
    connection = _Recorder.connections[-1]
    assert connection["host"] == "mail.kunde.de" and connection["port"] == 465
    assert connection["security"] == "SSL"
    assert connection["pinned"] == "203.0.113.7"  # Mandanten-Server: direkt auf die geprüfte IP verbunden
    assert connection["login"] == ("hr@kunde.de", "geheim-123")

    _Recorder.fail = True
    failed = await client.post("/settings/smtp-test", headers=headers, json={})
    assert failed.status_code == 400
    assert failed.json()["code"] == "SMTP_TEST_FAILED"
    # Allgemeine Meldung, keine Interna der Verbindung
    assert "abgelehnt" not in failed.json()["detail"]
    assert "SMTP-Server" in failed.json()["detail"]


async def test_smtp_test_without_any_server_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _admin(db_session, client)

    response = await client.post("/settings/smtp-test", headers=headers, json={})

    assert response.status_code == 400
    assert response.json()["code"] == "EMAIL_NOT_CONFIGURED"


async def test_notification_mails_can_be_switched_off(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    app_settings.smtp_host = "smtp.platform.example"
    employee = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1",
        login_email="erika@example.com",
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)

    async def decide() -> None:
        absence = Absence(
            employee_id=employee.id, type=AbsenceType.VACATION, date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 10), approval_status=AbsenceApprovalStatus.PENDING,
        )
        db_session.add(absence)
        await db_session.commit()
        await db_session.refresh(absence)
        result = await client.patch(f"/absences/{absence.id}/decide", headers=headers, json={"approve": True})
        assert result.status_code == 200

    await decide()
    assert len(_Recorder.messages) == 1  # Standard: Mail an den Antragsteller

    await client.patch("/settings", headers=headers, json={"email_notifications_enabled": False})
    await decide()
    assert len(_Recorder.messages) == 1  # ausgeschaltet: keine weitere Mail


async def _employee_with_login(db_session: AsyncSession, location: Location) -> Employee:
    employee = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E1",
        login_email="erika@example.com", password_hash=hash_password("alt"),
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def test_employee_password_reset_shown_once(client: AsyncClient, db_session: AsyncSession) -> None:
    location, headers = await _admin(db_session, client)
    employee = await _employee_with_login(db_session, location)

    response = await client.post(
        f"/employees/{employee.id}/reset-password", headers=headers, json={"send_email": False}
    )

    assert response.status_code == 200
    new_password = response.json()["new_password"]
    assert response.json()["emailed"] is False and new_password
    login = await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": new_password})
    assert login.status_code == 200
    assert not _Recorder.messages


async def test_employee_password_reset_by_email(
    client: AsyncClient, db_session: AsyncSession, allow_hosts
) -> None:
    location, headers = await _admin(db_session, client)
    employee = await _employee_with_login(db_session, location)
    await client.patch("/settings", headers=headers, json=_TENANT_SMTP)

    response = await client.post(
        f"/employees/{employee.id}/reset-password", headers=headers, json={"send_email": True}
    )

    assert response.status_code == 200
    assert response.json() == {"emailed": True, "new_password": None}
    assert len(_Recorder.messages) == 1
    mail = _Recorder.messages[0]
    assert mail["To"] == "erika@example.com"
    body = mail.get_payload(decode=True).decode("utf-8")
    password = next(line.split(":", 1)[1].strip() for line in body.splitlines() if line.startswith("Einmalpasswort"))
    login = await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": password})
    assert login.status_code == 200
    entries = (await client.get("/audit-log", headers=headers)).json()
    assert any(e["action"] == "EMPLOYEE_PASSWORD_RESET" and "per E-Mail" in e["detail"] for e in entries)
    assert all(password not in (e["detail"] or "") for e in entries)


async def test_employee_password_reset_email_failure_keeps_old_password(
    client: AsyncClient, db_session: AsyncSession, allow_hosts
) -> None:
    location, headers = await _admin(db_session, client)
    employee = await _employee_with_login(db_session, location)
    await client.patch("/settings", headers=headers, json=_TENANT_SMTP)
    _Recorder.fail = True

    response = await client.post(
        f"/employees/{employee.id}/reset-password", headers=headers, json={"send_email": True}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "EMAIL_SEND_FAILED"
    still_old = await client.post("/auth/employee/login", json={"email": "erika@example.com", "password": "alt"})
    assert still_old.status_code == 200


async def test_employee_password_reset_requires_smtp_login_and_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    location, headers = await _admin(db_session, client)
    employee = await _employee_with_login(db_session, location)
    no_login = Employee(location_id=location.id, first_name="Max", last_name="Ohne", employee_number="E2")
    db_session.add(no_login)
    await db_session.commit()
    await db_session.refresh(no_login)

    no_smtp = await client.post(f"/employees/{employee.id}/reset-password", headers=headers, json={"send_email": True})
    assert no_smtp.json()["code"] == "EMAIL_NOT_CONFIGURED"
    missing_login = await client.post(f"/employees/{no_login.id}/reset-password", headers=headers, json={})
    assert missing_login.json()["code"] == "NO_LOGIN"

    db_session.add(HrUser(email="hr@example.com", password_hash=hash_password("pw"), role=HrRole.HR))
    await db_session.commit()
    hr_login = await client.post("/auth/hr/login", json={"email": "hr@example.com", "password": "pw"})
    hr_headers = {"Authorization": f"Bearer {hr_login.json()['access_token']}"}
    forbidden = await client.post(f"/employees/{employee.id}/reset-password", headers=hr_headers, json={})
    assert forbidden.status_code == 403


async def test_tenant_credentials_sent_by_email_via_platform_smtp(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    app_settings.smtp_host = "smtp.platform.example"
    db_session.add(
        HrUser(tenant_id=None, email="super@example.com", password_hash=hash_password("sp"), role=HrRole.SUPER_ADMIN)
    )
    await db_session.commit()
    host = {"Host": app_settings.super_admin_hostname}
    login = await client.post("/auth/hr/login", headers=host, json={"email": "super@example.com", "password": "sp"})
    headers = {**host, "Authorization": f"Bearer {login.json()['access_token']}"}

    created = await client.post(
        "/tenants",
        headers=headers,
        json={"subdomain": "kunde", "name": "Kunde GmbH", "admin_email": "chef@kunde.de", "send_credentials_email": True},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["credentials_emailed"] is True
    mail = _Recorder.messages[-1]
    text = mail.get_payload(decode=True).decode("utf-8")
    assert mail["To"] == "chef@kunde.de"
    assert body["initial_admin_password"] in text
    assert "kunde." in text  # Mandanten-Subdomain im Anmeldelink

    reset = await client.post(
        f"/tenants/{body['id']}/reset-admin-password", headers=headers, json={"send_email": True}
    )
    assert reset.json()["emailed"] is True
    assert reset.json()["new_password"] in _Recorder.messages[-1].get_payload(decode=True).decode("utf-8")

    plain = await client.post(f"/tenants/{body['id']}/reset-admin-password", headers=headers)
    assert plain.status_code == 200 and plain.json()["emailed"] is False


async def test_tenant_credentials_not_emailed_without_smtp(client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(
        HrUser(tenant_id=None, email="super@example.com", password_hash=hash_password("sp"), role=HrRole.SUPER_ADMIN)
    )
    await db_session.commit()
    host = {"Host": app_settings.super_admin_hostname}
    login = await client.post("/auth/hr/login", headers=host, json={"email": "super@example.com", "password": "sp"})
    headers = {**host, "Authorization": f"Bearer {login.json()['access_token']}"}

    created = await client.post(
        "/tenants",
        headers=headers,
        json={"subdomain": "kunde", "name": "Kunde GmbH", "admin_email": "chef@kunde.de", "send_credentials_email": True},
    )

    assert created.status_code == 201
    assert created.json()["credentials_emailed"] is False
    assert created.json()["initial_admin_password"]
