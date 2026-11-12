"""Lokale Entwicklungs-Datenbank (SQLite) mit Testdaten anlegen – NUR für lokale Tests.

Legt das Schema per create_all an (keine Alembic-Migrationen) und befüllt es mit einem Testmandanten
"musterfirma", Admin admin@example.com, drei Mitarbeitern (Erika mit eigenem Login
erika@example.com) und einem Tablet (Token "local-test-device-token"). Das Passwort wird zufällig
erzeugt und nur in die Datei CREDENTIALS_FILE geschrieben (nie ins Repo).

Aufruf (aus backend/):
  DATABASE_URL=sqlite+aiosqlite:////tmp/hr3000-dev.db DEBUG=true JWT_SECRET_KEY=<lokal> \\
  CREDENTIALS_FILE=/tmp/hr3000-dev-credentials.txt python scripts/seed_local_dev.py
"""
import asyncio
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, engine  # noqa: E402
from app.models import Account, AppSettings, Base, Device, Employee, HrRole, Location, Tenant  # noqa: E402
from app.services.auth_service import hash_password  # noqa: E402
from app.services.pairing_service import token_hash  # noqa: E402


async def main() -> None:
    if not settings.database_url.startswith("sqlite"):
        raise SystemExit("Nur für lokale SQLite-Datenbanken gedacht.")
    credentials_file = os.environ.get("CREDENTIALS_FILE")
    if not credentials_file:
        raise SystemExit("Bitte CREDENTIALS_FILE (außerhalb des Repos) angeben.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    password = secrets.token_urlsafe(10)
    async with AsyncSessionLocal() as db:
        tenant = Tenant(subdomain="musterfirma", name="Testfirma")
        db.add(tenant)
        await db.flush()
        location = Location(tenant_id=tenant.id, name="Zentrale", timezone="Europe/Berlin")
        db.add(location)
        await db.flush()
        db.add(Account(tenant_id=tenant.id, email="admin@example.com", password_hash=hash_password(password), role=HrRole.ADMIN))
        for index, (first, last) in enumerate([("Erika", "Muster"), ("Max", "Beispiel"), ("Anna", "Zeit")]):
            db.add(
                Employee(
                    tenant_id=tenant.id,
                    location_id=location.id,
                    first_name=first,
                    last_name=last,
                    employee_number=f"T{index + 1}",
                    login_email="erika@example.com" if index == 0 else None,
                    password_hash=hash_password(password) if index == 0 else None,
                )
            )
        db.add(Device(tenant_id=tenant.id, name="Test-Tablet", location_id=location.id, token_hash=token_hash("local-test-device-token")))
        db.add(AppSettings(tenant_id=tenant.id))
        await db.commit()
    with open(credentials_file, "w") as fh:
        fh.write(f"admin@example.com / erika@example.com : {password}\n")
    print("seeded")


asyncio.run(main())
