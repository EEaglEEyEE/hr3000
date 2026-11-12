"""Test-Helfer für das Recruiting: Firma mit Konten je Rolle, Stellen und Bewerbungen."""
from dataclasses import dataclass, field
from datetime import datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AppSettings, Department, Employee, HrRole, Location, Tenant, TenantPlan
from app.services.auth_service import hash_password

PDF = b"%PDF-1.4\n%test\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
HTML = b"<html><script>alert(1)</script></html>"


@dataclass
class Company:
    location: Location
    department: Department
    headers: dict[str, dict[str, str]] = field(default_factory=dict)
    accounts: dict[str, Account] = field(default_factory=dict)


async def login(client: AsyncClient, email: str, subdomain: str | None = None) -> dict[str, str]:
    extra = {"X-Tenant-Subdomain": subdomain} if subdomain else {}
    response = await client.post("/auth/login", json={"email": email, "password": "pw"}, headers=extra)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}", **extra}


async def settings_row(db_session: AsyncSession, tenant_id: int = 1) -> AppSettings:
    return (await db_session.execute(select(AppSettings).where(AppSettings.tenant_id == tenant_id))).scalar_one()


async def enable(db_session: AsyncSession, tenant_id: int = 1, **values) -> AppSettings:
    row = await settings_row(db_session, tenant_id)
    row.recruiting_enabled = True
    for key, value in values.items():
        setattr(row, key, value)
    await db_session.commit()
    return row


async def company(
    db_session: AsyncSession, client: AsyncClient, *, enabled: bool = True, plan: TenantPlan = TenantPlan.UNLIMITED
) -> Company:
    """Firma 1 mit Admin, HR (mit/ohne Lohn-Berechtigung), Führungskraft und Mitarbeiter (ohne Rolle,
    mit Konto) – alle mit Passwort „pw“. Tarif ohne Mitarbeitergrenze (sonst greift sie bei der Übernahme)."""
    (await db_session.get(Tenant, 1)).plan = plan
    location = Location(name="Zentrale", timezone="Europe/Berlin")
    department = Department(name="Vertrieb")
    db_session.add_all([location, department])
    await db_session.flush()
    people = {}
    for key, role, payroll in (
        ("admin", HrRole.ADMIN, False),
        ("hr", HrRole.HR, False),
        ("payroll", HrRole.HR, True),
        ("lead", HrRole.SUPERVISOR, False),
        ("staff", None, False),
        ("other", None, False),
    ):
        employee = Employee(
            location_id=location.id, first_name=key.capitalize(), last_name="Muster", employee_number=f"N-{key}"
        )
        db_session.add(employee)
        await db_session.flush()
        account = Account(
            email=f"{key}@example.com", password_hash=hash_password("pw"), role=role, payroll_access=payroll,
            employee=employee,
        )
        db_session.add(account)
        people[key] = account
    await db_session.commit()
    if enabled:
        await enable(db_session)
    result = Company(location=location, department=department, accounts=people)
    for key in people:
        result.headers[key] = await login(client, f"{key}@example.com")
    return result


async def other_company(db_session: AsyncSession, client: AsyncClient, *, enabled: bool = True) -> dict[str, str]:
    """Firma 2 („acme“) mit eigenem Admin; gibt dessen Header zurück."""
    db_session.add(Tenant(id=2, subdomain="acme", name="Acme GmbH"))
    await db_session.flush()
    db_session.add(AppSettings(tenant_id=2, recruiting_enabled=enabled))
    db_session.add(Account(tenant_id=2, email="admin@acme.example.com", password_hash=hash_password("pw"), role=HrRole.ADMIN))
    await db_session.commit()
    return await login(client, "admin@acme.example.com", "acme")


def job_payload(**overrides) -> dict:
    payload = {
        "title": "Sachbearbeiter (m/w/d) Buchhaltung",
        "employment_type": "FULL_TIME",
        "description": "Wir suchen Verstärkung.\n\n- Buchhaltung\n- Ablage",
        "status": "PUBLISHED",
        "member_account_ids": [],
    }
    payload.update(overrides)
    return payload


async def create_job(client: AsyncClient, headers: dict[str, str], **overrides) -> dict:
    response = await client.post("/recruiting/jobs", json=job_payload(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def create_application(client: AsyncClient, headers: dict[str, str], job_id: int, **overrides) -> dict:
    payload = {"job_id": job_id, "first_name": "Bea", "last_name": "Bewerber", "email": "bea@example.com"}
    payload.update(overrides)
    response = await client.post("/recruiting/applications", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def apply_form(**overrides) -> dict:
    data = {
        "first_name": "Clara",
        "last_name": "Kandidat",
        "email": "clara@example.com",
        "privacy_acknowledged": "true",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


async def apply(client: AsyncClient, job_id: int, *, data: dict | None = None, files=None, headers=None):
    return await client.post(
        f"/public/careers/jobs/{job_id}/applications", data=data if data is not None else apply_form(),
        files=files, headers=headers or {},
    )


def closed_at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0)
