"""Erinnerungen: Probezeit-, Befristungsende und Austritt an Admin/HR, einmal pro Tag, nur wenn an."""
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ContractType, EmploymentContract, Notification, NotificationType
from app.services.reminder_service import send_due_reminders
from tests.test_absence_types import _setup

TODAY = date(2026, 11, 7)


async def test_reminders_for_hr(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    employee.termination_date = TODAY + timedelta(days=14)
    db_session.add(
        EmploymentContract(
            tenant_id=employee.tenant_id, employee_id=employee.id, valid_from=date(2026, 6, 1),
            contract_type=ContractType.PERMANENT, probation_end=TODAY + timedelta(days=14),
            fixed_term_end=TODAY + timedelta(days=30),
        )
    )
    await db_session.commit()

    assert await send_due_reminders(db_session, employee.tenant_id, TODAY) == 0  # Standard aus

    assert (await client.patch("/settings", headers=headers, json={"reminders_enabled": True})).status_code == 200
    assert await send_due_reminders(db_session, employee.tenant_id, TODAY) == 3
    messages = sorted(
        (await db_session.execute(select(Notification.message).where(Notification.type == NotificationType.REMINDER))).scalars()
    )
    assert any("Probezeit von Erika Muster endet am 21.11.2026" in m for m in messages)
    assert any("Befristung von Erika Muster endet am 07.12.2026" in m for m in messages)
    assert any("scheidet am 21.11.2026 aus" in m for m in messages)

    assert await send_due_reminders(db_session, employee.tenant_id, TODAY) == 0  # nur einmal pro Tag
    assert await send_due_reminders(db_session, employee.tenant_id, TODAY + timedelta(days=1)) == 0  # nichts fällig
