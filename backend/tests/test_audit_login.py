"""Anmeldungen landen im Audit-Protokoll (ohne IP-Adresse), Fehlversuche nicht."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLogEntry
from tests.test_absence_types import _setup


async def test_logins_are_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)  # meldet den Admin an
    assert (await client.post("/auth/login", json={"email": "erika@example.com", "password": "falsch"})).status_code == 401
    assert (await client.post("/auth/login", json={"email": "erika@example.com", "password": "pw123456"})).status_code == 200

    entries = (
        await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.LOGIN).order_by(AuditLogEntry.id))
    ).scalars().all()
    assert [(e.entity_type, e.detail) for e in entries] == [("account", "Anmeldung"), ("account", "Anmeldung")]
    assert entries[1].actor_account_id == employee.account.id

    listed = (await client.get("/audit-log", headers=headers)).json()
    assert {row["action"] for row in listed} >= {"LOGIN"}
