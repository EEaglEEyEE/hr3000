"""Ein Konto je Person (docs/konzept-konten.md): ein Login für Verwaltung und Mitarbeiter, E-Mail
eindeutig über alle Konten der Firma, Admin mit eigenem Mitarbeiter (stempelt selbst), entfernte
Zugänge bleiben für den Verlauf erhalten."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AppSettings, AuditAction, AuditLogEntry, Employee, HrRole, Location
from app.services.auth_service import decode_token, hash_password

PW = "pw123456"


async def _setup(db_session: AsyncSession) -> tuple[Location, Account, Employee]:
    location = Location(name="Zentrale", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    admin = Account(email="chefin@example.com", password_hash=hash_password(PW), role=HrRole.ADMIN)
    erika = Employee(
        location_id=location.id, first_name="Erika", last_name="Muster", employee_number="1",
        login_email="erika@example.com", password_hash=hash_password(PW),
    )
    db_session.add_all([admin, erika])
    settings_row = (await db_session.execute(select(AppSettings))).scalar_one()
    settings_row.portal_punching_enabled = True
    await db_session.commit()
    return location, admin, erika


async def _login(client: AsyncClient, email: str, password: str = PW):
    return await client.post("/auth/login", json={"email": email, "password": password})


def _auth(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_one_login_for_admin_accounts_and_employees(client: AsyncClient, db_session: AsyncSession) -> None:
    _, admin, erika = await _setup(db_session)

    admin_login = await _login(client, "chefin@example.com")
    assert admin_login.status_code == 200
    claims = decode_token(admin_login.json()["access_token"])
    assert (claims["type"], claims["sub"], claims["role"], claims["emp"]) == ("account_access", str(admin.id), "ADMIN", None)

    erika_login = await _login(client, "ERIKA@example.com")  # Groß-/Kleinschreibung egal
    assert erika_login.status_code == 200
    claims = decode_token(erika_login.json()["access_token"])
    assert (claims["role"], claims["emp"]) == (None, erika.id)

    # „Mein Bereich“ nur mit Mitarbeiter, Verwaltung nur mit Rolle
    assert (await client.post("/me/punches", headers=_auth(admin_login), json={"punch_type": "COME"})).status_code == 403
    assert (await client.post("/me/punches", headers=_auth(erika_login), json={"punch_type": "COME"})).status_code == 201
    assert (await client.get("/employees", headers=_auth(erika_login))).status_code == 403


async def test_admin_with_own_employee_has_both(client: AsyncClient, db_session: AsyncSession) -> None:
    """Der Fall der früher doppelten Adresse: Admin-Konto mit verknüpftem Mitarbeiter."""
    location, _, _ = await _setup(db_session)
    johannes = Employee(
        location_id=location.id, first_name="Johannes", last_name="Admin", employee_number="2",
        login_email="johannes@example.com", password_hash=hash_password(PW), hr_role=HrRole.ADMIN,
    )
    db_session.add(johannes)
    await db_session.commit()

    login = await _login(client, "johannes@example.com")
    claims = decode_token(login.json()["access_token"])
    assert (claims["role"], claims["emp"], claims["payroll"]) == ("ADMIN", johannes.id, True)
    assert (await client.get("/hr-users", headers=_auth(login))).status_code == 200
    punch = await client.post("/me/punches", headers=_auth(login), json={"punch_type": "COME"})
    assert punch.status_code == 201
    assert punch.json()["created_by_account_id"] == johannes.account.id


async def test_email_is_unique_across_all_accounts(client: AsyncClient, db_session: AsyncSession) -> None:
    location, _, _ = await _setup(db_session)
    admin = _auth(await _login(client, "chefin@example.com"))

    taken = await client.post(
        "/employees", headers=admin,
        json={"location_id": location.id, "first_name": "Neu", "last_name": "X", "employee_number": "9",
              "login_email": "chefin@example.com", "password": "startpasswort-1"},
    )
    assert taken.status_code == 409 and taken.json()["code"] == "LOGIN_EMAIL_TAKEN"
    again = await client.post("/hr-users", headers=admin, json={"email": "erika@example.com", "password": "startpasswort-1"})
    assert again.status_code == 409


async def test_inactive_employee_cannot_sign_in_and_loses_sessions(client: AsyncClient, db_session: AsyncSession) -> None:
    _, _, erika = await _setup(db_session)
    session = _auth(await _login(client, "erika@example.com"))
    erika.active = False
    await db_session.commit()

    assert (await _login(client, "erika@example.com")).status_code == 401
    assert (await client.post("/me/punches", headers=session, json={"punch_type": "COME"})).status_code == 401


async def test_removed_admin_account_keeps_history_and_can_be_restored(client: AsyncClient, db_session: AsyncSession) -> None:
    await _setup(db_session)
    admin = _auth(await _login(client, "chefin@example.com"))
    created = await client.post("/hr-users", headers=admin, json={"email": "lohnbuero@example.com", "password": "startpasswort-1", "role": "HR"})
    assert created.status_code == 201
    office_id = created.json()["id"]
    assert (await _login(client, "lohnbuero@example.com", "startpasswort-1")).status_code == 200

    assert (await client.delete(f"/hr-users/{office_id}", headers=admin)).status_code == 204
    assert (await _login(client, "lohnbuero@example.com", "startpasswort-1")).status_code == 401
    assert [u["email"] for u in (await client.get("/hr-users", headers=admin)).json()] == ["chefin@example.com"]
    # Verlauf: die Anmeldung bleibt dem Lohnbüro zugeordnet
    logins = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.LOGIN, AuditLogEntry.actor_account_id == office_id)
        )
    ).scalars().all()
    assert len(logins) == 1
    labels = {row["actor_label"] for row in (await client.get("/audit-log", headers=admin)).json()}
    assert "lohnbuero@example.com" in labels

    restored = await client.post("/hr-users", headers=admin, json={"email": "lohnbuero@example.com", "password": "neues-passwort-1", "role": "HR"})
    assert restored.status_code == 201 and restored.json()["id"] == office_id
    assert (await _login(client, "lohnbuero@example.com", "neues-passwort-1")).status_code == 200
