"""Zwei-Faktor-Anmeldung (TOTP): Einrichten, zweistufiger Login, Wiederherstellungscodes, Pflicht je
Firma (Einrichten direkt beim Login), Abschalten und Zurücksetzen durch Admins."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AppSettings, AuditAction, AuditLogEntry, Employee, HrRole, Location
from app.services import totp_service
from app.services.auth_service import hash_password

PW = "pw123456"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """Uhr der Authenticator-Codes; jeder Aufruf von tick() geht einen Zeitschritt (30 s) weiter."""
    now = {"t": 1_800_000_000.0}
    monkeypatch.setattr(totp_service, "_clock", lambda: now["t"])

    def tick() -> None:
        now["t"] += totp_service.STEP_SECONDS

    return tick


def _code(secret: str) -> str:
    return totp_service.code_at(secret, totp_service.current_step())


async def _setup(db_session: AsyncSession) -> tuple[Account, Employee]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    admin = Account(email="chefin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN)
    erika = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="1",
        login_email="erika@example.com", password_hash=hash_password(PW), hr_role=HrRole.HR,
    )
    db_session.add_all([admin, erika])
    await db_session.commit()
    return admin, erika


async def _login(client: AsyncClient, email: str):
    return await client.post("/auth/login", json={"email": email, "password": PW})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _enable(client: AsyncClient, access_token: str) -> tuple[str, dict]:
    setup = await client.post("/auth/2fa/setup", json={}, headers=_bearer(access_token))
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/HR3000")
    enabled = await client.post("/auth/2fa/enable", json={"code": _code(secret)}, headers=_bearer(access_token))
    assert enabled.status_code == 200
    return secret, enabled.json()


async def test_setup_and_two_step_login(client: AsyncClient, db_session: AsyncSession, clock) -> None:
    await _setup(db_session)
    first = (await _login(client, "chefin@example.com")).json()
    assert first["two_factor"] is None and first["access_token"]

    secret, enabled = await _enable(client, first["access_token"])
    assert len(enabled["recovery_codes"]) == 10
    # Einschalten beendet bisherige Sitzungen; die neue gilt
    assert (await client.get("/auth/2fa", headers=_bearer(first["access_token"]))).status_code == 401
    status = (await client.get("/auth/2fa", headers=_bearer(enabled["access_token"]))).json()
    assert status == {"enabled": True, "required": False, "recovery_codes_left": 10}

    clock()
    step1 = (await _login(client, "chefin@example.com")).json()
    assert step1["two_factor"] == "required" and step1["access_token"] is None
    challenge = step1["challenge_token"]
    # Das Challenge-Token ist kein Zugang
    assert (await client.get("/employees", headers=_bearer(challenge))).status_code == 401
    wrong = await client.post("/auth/login/2fa", json={"challenge_token": challenge, "code": "000000"})
    assert wrong.status_code == 400 and wrong.json()["code"] == "TWO_FACTOR_CODE_INVALID"
    code = _code(secret)
    ok = await client.post("/auth/login/2fa", json={"challenge_token": challenge, "code": code})
    assert ok.status_code == 200
    assert (await client.get("/employees", headers=_bearer(ok.json()["access_token"]))).status_code == 200
    # Derselbe Code gilt nur einmal
    again = await client.post("/auth/login/2fa", json={"challenge_token": challenge, "code": code})
    assert again.status_code == 400

    logins = (
        await db_session.execute(select(AuditLogEntry.detail).where(AuditLogEntry.action == AuditAction.LOGIN))
    ).scalars().all()
    assert "Anmeldung (Zwei-Faktor)" in logins


async def test_recovery_code_works_once(client: AsyncClient, db_session: AsyncSession, clock) -> None:
    await _setup(db_session)
    _, enabled = await _enable(client, (await _login(client, "chefin@example.com")).json()["access_token"])
    recovery = enabled["recovery_codes"][0]

    challenge = (await _login(client, "chefin@example.com")).json()["challenge_token"]
    ok = await client.post("/auth/login/2fa", json={"challenge_token": challenge, "code": recovery.upper()})
    assert ok.status_code == 200
    status = (await client.get("/auth/2fa", headers=_bearer(ok.json()["access_token"]))).json()
    assert status["recovery_codes_left"] == 9
    challenge = (await _login(client, "chefin@example.com")).json()["challenge_token"]
    assert (await client.post("/auth/login/2fa", json={"challenge_token": challenge, "code": recovery})).status_code == 400


async def test_wrong_codes_are_rate_limited(client: AsyncClient, db_session: AsyncSession, clock) -> None:
    await _setup(db_session)
    secret, _ = await _enable(client, (await _login(client, "chefin@example.com")).json()["access_token"])
    clock()
    challenge = (await _login(client, "chefin@example.com")).json()["challenge_token"]
    for _ in range(5):
        assert (await client.post("/auth/login/2fa", json={"challenge_token": challenge, "code": "123456"})).status_code == 400
    blocked = await client.post("/auth/login/2fa", json={"challenge_token": challenge, "code": _code(secret)})
    assert blocked.status_code == 429


async def test_required_by_company_setup_during_login(client: AsyncClient, db_session: AsyncSession, clock) -> None:
    _, erika = await _setup(db_session)
    settings_row = (await db_session.execute(select(AppSettings))).scalar_one()
    settings_row.two_factor_roles = "HR"
    await db_session.commit()

    step1 = (await _login(client, "erika@example.com")).json()
    assert step1["two_factor"] == "setup" and step1["access_token"] is None
    challenge = step1["challenge_token"]
    # Setup-Challenge taugt nicht für den Code-Schritt
    assert (await client.post("/auth/login/2fa", json={"challenge_token": challenge, "code": "123456"})).status_code == 401
    setup = await client.post("/auth/2fa/setup", json={"challenge_token": challenge})
    assert setup.status_code == 200
    enabled = await client.post("/auth/2fa/enable", json={"challenge_token": challenge, "code": _code(setup.json()["secret"])})
    assert enabled.status_code == 200
    token = enabled.json()["access_token"]
    assert (await client.get("/employees", headers=_bearer(token))).status_code == 200
    # Pflicht: selbst abschalten geht nicht
    disable = await client.post("/auth/2fa/disable", json={"password": PW}, headers=_bearer(token))
    assert disable.status_code == 400 and disable.json()["code"] == "TWO_FACTOR_REQUIRED"


async def _set_roles(db_session: AsyncSession, roles: str | None) -> None:
    settings_row = (await db_session.execute(select(AppSettings))).scalar_one()
    settings_row.two_factor_roles = roles
    await db_session.commit()


async def test_required_only_for_chosen_roles(client: AsyncClient, db_session: AsyncSession, clock) -> None:
    """Pflicht nur für Admin: Admin richtet beim Login ein, HR (Erika) meldet sich wie bisher an."""
    await _setup(db_session)
    await _set_roles(db_session, "ADMIN")
    assert (await _login(client, "chefin@example.com")).json()["two_factor"] == "setup"
    erika = (await _login(client, "erika@example.com")).json()
    assert erika["two_factor"] is None and erika["access_token"]
    status = await client.get("/auth/2fa", headers=_bearer(erika["access_token"]))
    assert status.json()["required"] is False


async def test_required_for_employees_without_role(client: AsyncClient, db_session: AsyncSession, clock) -> None:
    """„Mitarbeiter“ (Konten ohne Rolle): Einrichten beim Login, danach nicht selbst abschaltbar; Admin frei."""
    await _setup(db_session)
    location = (await db_session.execute(select(Location))).scalar_one()
    db_session.add(Employee(
        location_id=location.id, first_name="Tom", last_name="Ohnerolle", employee_number="2",
        login_email="tom@example.com", password_hash=hash_password(PW),
    ))
    await db_session.commit()
    await _set_roles(db_session, "EMPLOYEE")

    assert (await _login(client, "chefin@example.com")).json()["access_token"]
    step1 = (await _login(client, "tom@example.com")).json()
    assert step1["two_factor"] == "setup" and step1["access_token"] is None
    challenge = step1["challenge_token"]
    setup = await client.post("/auth/2fa/setup", json={"challenge_token": challenge})
    enabled = await client.post("/auth/2fa/enable", json={"challenge_token": challenge, "code": _code(setup.json()["secret"])})
    assert enabled.status_code == 200
    token = enabled.json()["access_token"]
    assert (await client.get("/auth/2fa", headers=_bearer(token))).json()["required"] is True
    disable = await client.post("/auth/2fa/disable", json={"password": PW}, headers=_bearer(token))
    assert disable.status_code == 400 and disable.json()["code"] == "TWO_FACTOR_REQUIRED"


async def test_settings_two_factor_roles(client: AsyncClient, db_session: AsyncSession) -> None:
    """Einstellung: feste Reihenfolge ohne Doppelte, [] = keine Pflicht, Unbekanntes abgelehnt, Audit."""
    await _setup(db_session)
    headers = _bearer((await _login(client, "chefin@example.com")).json()["access_token"])
    r = await client.patch("/settings", headers=headers, json={"two_factor_roles": ["EMPLOYEE", "HR", "ADMIN", "HR"]})
    assert r.status_code == 200, r.text
    assert r.json()["two_factor_roles"] == ["ADMIN", "HR", "EMPLOYEE"]
    assert (await db_session.execute(select(AppSettings.two_factor_roles))).scalar_one() == "ADMIN,HR,EMPLOYEE"
    assert (await client.get("/settings", headers=headers)).json()["two_factor_roles"] == ["ADMIN", "HR", "EMPLOYEE"]
    assert (await client.patch("/settings", headers=headers, json={"two_factor_roles": ["SUPER_ADMIN"]})).status_code == 422
    r = await client.patch("/settings", headers=headers, json={"two_factor_roles": []})
    assert r.json()["two_factor_roles"] == []
    details = (await db_session.execute(
        select(AuditLogEntry.detail).where(AuditLogEntry.action == AuditAction.SETTINGS_CHANGED)
    )).scalars().all()
    assert any("two_factor_roles=ADMIN,HR,EMPLOYEE" in d for d in details)
    assert any("two_factor_roles=keine" in d for d in details)


async def test_disable_and_admin_reset(client: AsyncClient, db_session: AsyncSession, clock) -> None:
    _, erika = await _setup(db_session)
    _, erika_enabled = await _enable(client, (await _login(client, "erika@example.com")).json()["access_token"])
    erika_token = erika_enabled["access_token"]

    wrong = await client.post("/auth/2fa/disable", json={"password": "falsch"}, headers=_bearer(erika_token))
    assert wrong.status_code == 400
    # Admin setzt zurück (Handy verloren); HR darf das nicht, sich selbst zurücksetzen auch nicht
    clock()
    admin_token = (await _login(client, "chefin@example.com")).json()["access_token"]
    assert (await client.post(f"/employees/{erika.id}/2fa-reset", headers=_bearer(erika_token))).status_code == 403
    assert (await client.get(f"/employees/{erika.id}", headers=_bearer(admin_token))).json()["two_factor_enabled"] is True
    assert (await client.post(f"/employees/{erika.id}/2fa-reset", headers=_bearer(admin_token))).status_code == 204
    assert (await client.get(f"/employees/{erika.id}", headers=_bearer(admin_token))).json()["two_factor_enabled"] is False
    assert (await _login(client, "erika@example.com")).json()["access_token"]
    admin_account_id = (await db_session.execute(select(Account.id).where(Account.email == "chefin@example.com"))).scalar_one()
    assert (await client.post(f"/hr-users/{admin_account_id}/2fa-reset", headers=_bearer(admin_token))).status_code == 400
    audit = (
        await db_session.execute(select(AuditLogEntry.detail).where(AuditLogEntry.action == AuditAction.TWO_FACTOR_CHANGED))
    ).scalars().all()
    assert "Zwei-Faktor-Anmeldung von Erika Muster zurückgesetzt" in audit

    # selbst abschalten mit Passwort
    _, again = await _enable(client, (await _login(client, "erika@example.com")).json()["access_token"])
    off = await client.post("/auth/2fa/disable", json={"password": PW}, headers=_bearer(again["access_token"]))
    assert off.status_code == 200 and off.json()["enabled"] is False
    assert (await _login(client, "erika@example.com")).json()["two_factor"] is None
