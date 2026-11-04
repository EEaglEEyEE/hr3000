import pytest

from app.config import settings
from app.services import email_service


@pytest.fixture(autouse=True)
def _reset_smtp_settings():
    original = (
        settings.smtp_host,
        settings.smtp_port,
        settings.smtp_user,
        settings.smtp_password,
        settings.smtp_from,
        settings.smtp_use_tls,
    )
    yield
    (
        settings.smtp_host,
        settings.smtp_port,
        settings.smtp_user,
        settings.smtp_password,
        settings.smtp_from,
        settings.smtp_use_tls,
    ) = original


def test_is_email_configured_false_by_default():
    settings.smtp_host = None
    assert email_service.is_email_configured() is False


def test_is_email_configured_true_when_host_set():
    settings.smtp_host = "smtp.example.com"
    assert email_service.is_email_configured() is True


async def test_send_email_without_smtp_host_does_not_touch_smtplib(monkeypatch):
    settings.smtp_host = None
    called = False

    def _fake_smtp(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("smtplib.SMTP darf ohne konfigurierten Host nicht aufgerufen werden.")

    monkeypatch.setattr(email_service.smtplib, "SMTP", _fake_smtp)

    await email_service.send_email("erika@example.com", "Betreff", "Text")

    assert called is False


async def test_send_email_uses_configured_smtp_server(monkeypatch):
    settings.smtp_host = "smtp.example.com"
    settings.smtp_port = 587
    settings.smtp_user = "hrapp"
    settings.smtp_password = "secret"
    settings.smtp_from = "no-reply@hrapp3000.local"
    settings.smtp_use_tls = True

    sent_messages = []

    class _FakeServer:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, **kwargs):
            self.starttls_context = kwargs.get("context")

        def login(self, user, password):
            self.login_args = (user, password)

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeServer)

    await email_service.send_email("erika@example.com", "Urlaubsantrag entschieden", "Genehmigt.")

    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "erika@example.com"
    assert sent_messages[0]["Subject"] == "Urlaubsantrag entschieden"


async def test_send_email_swallows_smtp_errors(monkeypatch):
    settings.smtp_host = "smtp.example.com"

    def _raise(*args, **kwargs):
        raise OSError("Verbindung fehlgeschlagen")

    monkeypatch.setattr(email_service.smtplib, "SMTP", _raise)

    # Darf keine Exception werfen – best effort.
    await email_service.send_email("erika@example.com", "Betreff", "Text")


async def test_tenant_server_is_pinned_to_checked_ip_and_tls_is_verified(monkeypatch):
    import ssl

    events = {}

    class _Server:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, **kwargs):
            events["context"] = kwargs.get("context")

        def login(self, *args):
            pass

        def send_message(self, message):
            events["sent"] = True

    def _connect(config, pinned_ip, context):
        events["pinned"] = pinned_ip
        return _Server()

    monkeypatch.setattr(email_service, "_connect", _connect)
    monkeypatch.setattr(email_service, "_resolve_public_ip", lambda host: "203.0.113.9")
    config = email_service.SmtpConfig(host="mail.kunde.de", enforce_public=True)

    await email_service.send_email("a@b.de", "Betreff", "Text", config=config, raise_errors=True)

    assert events["pinned"] == "203.0.113.9"
    context = events["context"]
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True


async def test_platform_server_is_not_pinned(monkeypatch):
    seen = {}

    class _Server:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, **kwargs):
            pass

        def send_message(self, message):
            pass

    monkeypatch.setattr(email_service, "_connect", lambda config, pinned_ip, context: seen.setdefault("pinned", pinned_ip) or _Server())
    monkeypatch.setattr(email_service, "_resolve_public_ip", lambda host: (_ for _ in ()).throw(AssertionError("darf nicht aufgelöst werden")))

    def _connect(config, pinned_ip, context):
        seen["pinned"] = pinned_ip
        return _Server()

    monkeypatch.setattr(email_service, "_connect", _connect)
    await email_service.send_email("a@b.de", "B", "T", config=email_service.SmtpConfig(host="smtp.plattform.de"), raise_errors=True)

    assert seen["pinned"] is None


def test_resolve_public_ip_rejects_mixed_and_private_results(monkeypatch):
    import socket

    def fake_getaddrinfo(results):
        return lambda host, port, type=None: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in results]

    monkeypatch.setattr(email_service.socket, "getaddrinfo", fake_getaddrinfo(["93.184.216.34"]))
    assert email_service._resolve_public_ip("ok.example") == "93.184.216.34"

    for bad in (["10.0.0.5"], ["93.184.216.34", "10.0.0.5"], ["127.0.0.1"], ["169.254.169.254"], ["::1"]):
        monkeypatch.setattr(email_service.socket, "getaddrinfo", fake_getaddrinfo(bad))
        with pytest.raises(ValueError):
            email_service._resolve_public_ip("x.example")


def test_error_descriptions_are_generic():
    import smtplib

    assert "Anmeldung" in email_service.describe_smtp_error(smtplib.SMTPAuthenticationError(535, b"secret banner"))
    assert "Verbindung" in email_service.describe_smtp_error(OSError("[Errno 111] Connection refused 10.0.0.5:3306"))
    assert "10.0.0.5" not in email_service.describe_smtp_error(OSError("Connection refused 10.0.0.5"))
    assert email_service.describe_smtp_error(RuntimeError("boom")) == "Der E-Mail-Versand ist fehlgeschlagen."
