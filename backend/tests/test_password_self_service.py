"""Passwort selbst ändern, "Passwort vergessen" (Link per E-Mail) und E-Mail-Bestätigung bei der
Selbstregistrierung (api/auth.py, api/public.py, services/account_tokens.py, services/signup_mail.py)."""

import re
from datetime import datetime, timedelta

import pytest
from sqlalchemy import update

import app.api.auth as auth_api
import app.api.branding as branding_api
import app.services.signup_mail as signup_mail
from app.config import settings
from app.models import AccountToken, Device, Employee, HrRole, Account, Location
from app.services.auth_service import hash_password
from app.services.tenant_provisioning import provision_tenant
from app.services.pairing_service import token_hash

HOST = {"Host": "musterfirma.hr3000.de"}
PW = "altes-passwort-1"


@pytest.fixture(autouse=True)
def _platform(monkeypatch):
    monkeypatch.setattr(settings, "tenant_base_domain", "hr3000.de")


@pytest.fixture
def mails(monkeypatch):
    """Mailversand eingerichtet – verschickte Mails werden mitgeschnitten statt versendet."""
    sent: list[dict] = []

    async def fake_send(to, subject, body, config=None, raise_errors=False):
        sent.append({"to": to, "subject": subject, "body": body})
        return True

    async def fake_config(db, tenant_id):
        return object()

    for module in (auth_api, signup_mail):
        monkeypatch.setattr(module, "send_email", fake_send)
        monkeypatch.setattr(module, "resolve_smtp_config", fake_config)
    monkeypatch.setattr(branding_api, "resolve_smtp_config", fake_config)
    return sent


def _token_from(mail: dict) -> str:
    return re.search(r"#token=([A-Za-z0-9_-]+)", mail["body"]).group(1)


async def _hr(db_session, email="hr@musterfirma.example", password=PW) -> Account:
    user = Account(email=email, password_hash=hash_password(password), role=HrRole.ADMIN)
    db_session.add(user)
    await db_session.commit()
    return user


async def _employee(db_session, email="erika@musterfirma.example", password=PW) -> Employee:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    employee = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="E-1",
        login_email=email, password_hash=hash_password(password),
    )
    db_session.add(employee)
    await db_session.commit()
    return employee


async def _login(client, email, password, kind="hr", host=HOST):
    return await client.post("/auth/login", json={"email": email, "password": password}, headers=host)


def _auth(token: str) -> dict:
    return {**HOST, "Authorization": f"Bearer {token}"}


# --- Passwort selbst ändern -------------------------------------------------------------------


async def test_hr_user_changes_password_and_other_sessions_end(client, db_session):
    await _hr(db_session)
    old_tokens = (await _login(client, "hr@musterfirma.example", PW)).json()

    wrong = await client.post("/auth/change-password", json={"current_password": "falsch", "new_password": "neues-passwort-1"}, headers=_auth(old_tokens["access_token"]))
    assert wrong.status_code == 400 and wrong.json()["code"] == "PASSWORD_WRONG"
    same = await client.post("/auth/change-password", json={"current_password": PW, "new_password": PW}, headers=_auth(old_tokens["access_token"]))
    assert same.status_code == 400 and same.json()["code"] == "PASSWORD_UNCHANGED"
    for bad in ("kurz", "ä" * 37):  # zu kurz / über 72 Byte
        r = await client.post("/auth/change-password", json={"current_password": PW, "new_password": bad}, headers=_auth(old_tokens["access_token"]))
        assert r.status_code == 422

    ok = await client.post("/auth/change-password", json={"current_password": PW, "new_password": "neues-passwort-1"}, headers=_auth(old_tokens["access_token"]))
    assert ok.status_code == 200, ok.text
    new_tokens = ok.json()
    # Alte Sitzung (auch auf anderen Geräten) ist beendet, die neue funktioniert.
    assert (await client.get("/plan", headers=_auth(old_tokens["access_token"]))).status_code == 401
    assert (await client.post("/auth/refresh", json={"refresh_token": old_tokens["refresh_token"]}, headers=HOST)).status_code == 401
    assert (await client.get("/plan", headers=_auth(new_tokens["access_token"]))).status_code == 200
    assert (await _login(client, "hr@musterfirma.example", PW)).status_code == 401
    assert (await _login(client, "hr@musterfirma.example", "neues-passwort-1")).status_code == 200


async def test_employee_changes_password(client, db_session):
    await _employee(db_session)
    token = (await _login(client, "erika@musterfirma.example", PW, kind="employee")).json()["access_token"]
    ok = await client.post("/auth/change-password", json={"current_password": PW, "new_password": "neues-passwort-1"}, headers=_auth(token))
    assert ok.status_code == 200, ok.text
    assert (await _login(client, "erika@musterfirma.example", "neues-passwort-1", kind="employee")).status_code == 200


async def test_wrong_current_password_is_rate_limited(client, db_session):
    await _hr(db_session)
    headers = _auth((await _login(client, "hr@musterfirma.example", PW)).json()["access_token"])
    for _ in range(5):
        assert (await client.post("/auth/change-password", json={"current_password": "falsch", "new_password": "neues-passwort-1"}, headers=headers)).status_code == 400
    blocked = await client.post("/auth/change-password", json={"current_password": PW, "new_password": "neues-passwort-1"}, headers=headers)
    assert blocked.status_code == 429


async def test_tablets_cannot_change_passwords(client, db_session):
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    db_session.add(Device(name="Tablet", location_id=location.id, token_hash=token_hash("tok-pw-test")))
    await db_session.commit()
    token = (await client.post("/auth/device/login", json={"device_token": "tok-pw-test"}, headers=HOST)).json()["access_token"]
    r = await client.post("/auth/change-password", json={"current_password": "x", "new_password": "neues-passwort-1"}, headers=_auth(token))
    assert r.status_code == 403


# --- Passwort vergessen ----------------------------------------------------------------------


async def test_password_reset_for_hr_user(client, db_session, mails):
    await _hr(db_session)
    r = await client.post("/auth/password-reset/request", json={"email": "HR@musterfirma.example"}, headers=HOST)
    assert r.status_code == 202
    assert len(mails) == 1 and mails[0]["to"] == "hr@musterfirma.example"
    assert "https://musterfirma.hr3000.de/passwort-zuruecksetzen#token=" in mails[0]["body"].replace("http://", "https://")
    token = _token_from(mails[0])

    bad = await client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "kurz"}, headers=HOST)
    assert bad.status_code == 422
    ok = await client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "neues-passwort-1"}, headers=HOST)
    assert ok.status_code == 204, ok.text
    assert (await _login(client, "hr@musterfirma.example", "neues-passwort-1")).status_code == 200
    # Einmal-Link: zweites Mal ungültig.
    again = await client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "noch-ein-passwort"}, headers=HOST)
    assert again.status_code == 400 and again.json()["code"] == "TOKEN_INVALID"


async def test_password_reset_for_employee(client, db_session, mails):
    await _employee(db_session)
    assert (await client.post("/auth/password-reset/request", json={"email": "erika@musterfirma.example"}, headers=HOST)).status_code == 202
    token = _token_from(mails[0])
    assert (await client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "neues-passwort-1"}, headers=HOST)).status_code == 204
    assert (await _login(client, "erika@musterfirma.example", "neues-passwort-1", kind="employee")).status_code == 200


async def test_unknown_address_gets_same_answer_and_no_mail(client, db_session, mails):
    await _hr(db_session)
    known = await client.post("/auth/password-reset/request", json={"email": "hr@musterfirma.example"}, headers=HOST)
    unknown = await client.post("/auth/password-reset/request", json={"email": "niemand@musterfirma.example"}, headers=HOST)
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(mails) == 1


async def test_without_mail_nothing_is_sent(client, db_session):
    await _hr(db_session)
    r = await client.post("/auth/password-reset/request", json={"email": "hr@musterfirma.example"}, headers=HOST)
    assert r.status_code == 202
    assert (await client.get("/branding", headers=HOST)).json()["password_reset_available"] is False


async def test_branding_offers_reset_when_mail_is_configured(client, mails):
    assert (await client.get("/branding", headers=HOST)).json()["password_reset_available"] is True


async def test_expired_superseded_and_foreign_tokens_are_rejected(client, db_session, mails):
    await _hr(db_session)
    await provision_tenant(db_session, subdomain="zweite", name="Zweite", admin_email="b@zweite.example", admin_password="sehr-geheim-123")
    await client.post("/auth/password-reset/request", json={"email": "hr@musterfirma.example"}, headers=HOST)
    first = _token_from(mails[-1])
    await client.post("/auth/password-reset/request", json={"email": "hr@musterfirma.example"}, headers=HOST)
    second = _token_from(mails[-1])
    # Ein neuer Link macht den alten ungültig.
    assert (await client.post("/auth/password-reset/confirm", json={"token": first, "new_password": "neues-passwort-1"}, headers=HOST)).status_code == 400
    # Link einer Firma gilt nicht unter der Adresse einer anderen.
    assert (await client.post("/auth/password-reset/confirm", json={"token": second, "new_password": "neues-passwort-1"}, headers={"Host": "zweite.hr3000.de"})).status_code == 400
    # Abgelaufen.
    await db_session.execute(update(AccountToken).values(expires_at=datetime.utcnow() - timedelta(minutes=1)))
    await db_session.commit()
    assert (await client.post("/auth/password-reset/confirm", json={"token": second, "new_password": "neues-passwort-1"}, headers=HOST)).status_code == 400


async def test_reset_links_per_address_are_limited(client, db_session, mails):
    await _hr(db_session)
    for _ in range(5):
        assert (await client.post("/auth/password-reset/request", json={"email": "hr@musterfirma.example"}, headers=HOST)).status_code == 202
    assert len(mails) == 3  # höchstens 3 Links je Adresse und Stunde


# --- E-Mail-Bestätigung bei der Selbstregistrierung ------------------------------------------

SIGNUP = {
    "company_name": "Neue Firma GmbH", "subdomain": "neue-firma", "contact_name": "Nina Neu",
    "email": "nina@neue-firma.example", "password": "sehr-geheim-123", "is_business": True, "accept_terms": True,
}


async def test_signup_with_mail_requires_confirmation(client, db_session, mails):
    r = await client.post("/public/signup", json=SIGNUP, headers={"Host": "hr3000.de"})
    assert r.status_code == 201, r.text
    assert r.json()["verification_required"] is True
    assert len(mails) == 1 and "https://hr3000.de/bestaetigen/#token=" in mails[0]["body"]
    new_host = {"Host": "neue-firma.hr3000.de"}

    blocked = await _login(client, "nina@neue-firma.example", "sehr-geheim-123", host=new_host)
    assert blocked.status_code == 403 and blocked.json()["code"] == "EMAIL_NOT_VERIFIED"
    wrong_pw = await _login(client, "nina@neue-firma.example", "falsch-falsch", host=new_host)
    assert wrong_pw.status_code == 401  # ohne richtiges Passwort wird nichts verraten

    verified = await client.post("/public/verify-email", json={"token": _token_from(mails[0])}, headers={"Host": "hr3000.de"})
    assert verified.status_code == 200, verified.text
    assert verified.json() == {"login_url": "https://neue-firma.hr3000.de/"}
    assert (await _login(client, "nina@neue-firma.example", "sehr-geheim-123", host=new_host)).status_code == 200
    again = await client.post("/public/verify-email", json={"token": _token_from(mails[0])}, headers={"Host": "hr3000.de"})
    assert again.status_code == 400


async def test_login_resends_the_confirmation_link_at_most_every_ten_minutes(client, db_session, mails):
    from app.services import rate_limiter

    await client.post("/public/signup", json=SIGNUP, headers={"Host": "hr3000.de"})
    new_host = {"Host": "neue-firma.hr3000.de"}
    await _login(client, "nina@neue-firma.example", "sehr-geheim-123", host=new_host)
    assert len(mails) == 1  # direkt nach der Registrierung kein zweiter Link
    rate_limiter.clear_all()  # 10 Minuten später
    await _login(client, "nina@neue-firma.example", "sehr-geheim-123", host=new_host)
    assert len(mails) == 2
    # Nur der neueste Link gilt.
    assert (await client.post("/public/verify-email", json={"token": _token_from(mails[0])}, headers={"Host": "hr3000.de"})).status_code == 400
    assert (await client.post("/public/verify-email", json={"token": _token_from(mails[1])}, headers={"Host": "hr3000.de"})).status_code == 200


@pytest.mark.parametrize("token", ["x" * 19, "kein-gueltiges-token-abcdefghijk"])
async def test_invalid_confirmation_links(client, token):
    r = await client.post("/public/verify-email", json={"token": token}, headers={"Host": "hr3000.de"})
    assert r.status_code in (400, 422)


async def test_password_reset_also_confirms_the_address(client, db_session, mails):
    await client.post("/public/signup", json=SIGNUP, headers={"Host": "hr3000.de"})
    new_host = {"Host": "neue-firma.hr3000.de"}
    await client.post("/auth/password-reset/request", json={"email": "nina@neue-firma.example"}, headers=new_host)
    token = _token_from(mails[-1])
    assert (await client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "neues-passwort-1"}, headers=new_host)).status_code == 204
    assert (await _login(client, "nina@neue-firma.example", "neues-passwort-1", host=new_host)).status_code == 200


async def test_super_admin_reset_unblocks_unconfirmed_admin(client, db_session, mails):
    await client.post("/public/signup", json=SIGNUP, headers={"Host": "hr3000.de"})
    db_session.add(Account(tenant_id=None, email="chef@example.com", password_hash=hash_password("sehr-geheim-123"), role=HrRole.SUPER_ADMIN))
    await db_session.commit()
    admin_host = {"Host": settings.super_admin_hostname}
    sa = (await client.post("/auth/login", json={"email": "chef@example.com", "password": "sehr-geheim-123"}, headers=admin_host)).json()["access_token"]
    tenants = (await client.get("/tenants", headers={**admin_host, "Authorization": f"Bearer {sa}"})).json()
    tenant_id = next(t["id"] for t in tenants if t["subdomain"] == "neue-firma")
    reset = await client.post(f"/tenants/{tenant_id}/reset-admin-password", headers={**admin_host, "Authorization": f"Bearer {sa}"})
    assert reset.status_code == 200, reset.text
    login = await _login(client, "nina@neue-firma.example", reset.json()["new_password"], host={"Host": "neue-firma.hr3000.de"})
    assert login.status_code == 200
