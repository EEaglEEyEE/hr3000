"""Test-Helfer für das Hinweisgebersystem: Firma mit Schalter, Konten aller Rollen, Beauftragte:r."""
from dataclasses import dataclass

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AppSettings, Employee, HrRole, Location, Tenant, WhistleOfficer
from app.services.auth_service import hash_password
from app.services.whistle_service import now_utc

PDF = b"%PDF-1.4\n%test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
REPORT = {
    "category": "CORRUPTION",
    "description": "Geheimer Sachverhalt: Rechnungen werden doppelt bezahlt.",
    "anonymous": True,
}
OTHER = {"X-Tenant-Subdomain": "acme"}


@dataclass
class Company:
    officer: dict
    officer_id: int
    admin: dict
    admin_id: int
    hr: dict
    supervisor: dict
    employee: dict
    employee_account_id: int
    no_login_account_id: int


async def set_enabled(db: AsyncSession, enabled: bool, tenant_id: int = 1) -> None:
    row = await db.scalar(select(AppSettings).where(AppSettings.tenant_id == tenant_id))
    row.whistleblowing_enabled = enabled
    await db.commit()


async def login(client: AsyncClient, email: str, headers: dict | None = None) -> dict:
    response = await client.post("/auth/login", headers=headers or {}, json={"email": email, "password": "pw"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}", **(headers or {})}


def _account(email: str, role: HrRole | None, tenant_id: int = 1) -> Account:
    return Account(tenant_id=tenant_id, email=email, password_hash=hash_password("pw"), role=role)


async def appoint(db: AsyncSession, account_id: int, tenant_id: int = 1) -> None:
    db.add(WhistleOfficer(tenant_id=tenant_id, account_id=account_id, created_at=now_utc()))
    await db.commit()


async def company(db: AsyncSession, client: AsyncClient, *, enabled: bool = True, with_officer: bool = True) -> Company:
    """Firma 1: Beauftragte:r ist ein Mitarbeiterkonto ohne Verwaltungsrolle (jede Person mit Zugang
    kann benannt werden); Admin, HR, Führungskraft und Mitarbeiter sind nicht benannt."""
    location = Location(name="Standort A", timezone="Europe/Berlin")
    db.add(location)
    await db.commit()
    officer_employee = Employee(
        location_id=location.id, first_name="Olga", last_name="Ombud", employee_number="W1",
        login_email="olga@example.com", password_hash=hash_password("pw"),
    )
    employee = Employee(
        location_id=location.id, first_name="Erik", last_name="Einfach", employee_number="W2",
        login_email="erik@example.com", password_hash=hash_password("pw"),
    )
    db.add_all([officer_employee, employee])
    admin, hr, supervisor = (
        _account("admin@example.com", HrRole.ADMIN),
        _account("hr@example.com", HrRole.HR),
        _account("lead@example.com", HrRole.SUPERVISOR),
    )
    no_login = Account(tenant_id=1, email=None, password_hash=None, role=None)
    db.add_all([admin, hr, supervisor, no_login])
    await db.commit()
    officer_account = await db.scalar(select(Account).where(Account.email == "olga@example.com"))
    employee_account = await db.scalar(select(Account).where(Account.email == "erik@example.com"))
    if with_officer:
        await appoint(db, officer_account.id)
    await set_enabled(db, enabled)
    return Company(
        officer=await login(client, "olga@example.com"),
        officer_id=officer_account.id,
        admin=await login(client, "admin@example.com"),
        admin_id=admin.id,
        hr=await login(client, "hr@example.com"),
        supervisor=await login(client, "lead@example.com"),
        employee=await login(client, "erik@example.com"),
        employee_account_id=employee_account.id,
        no_login_account_id=no_login.id,
    )


async def other_company(db: AsyncSession, client: AsyncClient, *, enabled: bool = True) -> dict:
    """Firma 2 („acme“) mit eigener:m Beauftragten; gibt deren Anmeldung zurück."""
    db.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db.flush()
    db.add(AppSettings(tenant_id=2, whistleblowing_enabled=enabled))
    account = _account("ombud@example.com", HrRole.ADMIN, tenant_id=2)
    db.add(account)
    await db.commit()
    await appoint(db, account.id, tenant_id=2)
    return await login(client, "ombud@example.com", OTHER)


async def report(client: AsyncClient, headers: dict | None = None, **overrides) -> dict:
    response = await client.post("/public/whistle/reports", headers=headers or {}, json={**REPORT, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def access(created: dict) -> dict:
    return {"case_number": created["case_number"], "access_code": created["access_code"]}


async def table_text(db: AsyncSession, *tables: str) -> str:
    """Alle Zeilen der Tabellen als ein Text – um zu prüfen, dass ein Klartext darin nicht vorkommt."""
    parts = []
    for table in tables:
        for row in (await db.execute(text(f"SELECT * FROM {table}"))).all():
            parts.append(" ".join(str(value) for value in row))
    return "\n".join(parts)


ALL_TABLES = ("whistle_cases", "whistle_messages", "whistle_attachments", "whistle_officers", "audit_log_entries", "notifications")
