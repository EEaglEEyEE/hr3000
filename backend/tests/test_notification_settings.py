"""Persönliche Einstellung „E-Mails zu Benachrichtigungen“: Glocke bleibt, Mail entfällt."""
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import notification_service
from tests.test_absence_types import _setup


async def test_employee_turns_off_notification_mails(client: AsyncClient, db_session: AsyncSession) -> None:
    employee, headers = await _setup(db_session, client)
    token = (await client.post("/auth/login", json={"email": "erika@example.com", "password": "pw123456"})).json()["access_token"]
    me = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/notifications/settings", headers=me)).json() == {"email": True}
    assert (await client.put("/notifications/settings", headers=me, json={"email": False})).json() == {"email": False}

    smtp = object()
    with patch.object(notification_service, "resolve_smtp_config", AsyncMock(return_value=smtp)), patch.object(
        notification_service, "send_email", AsyncMock()
    ) as send:
        config = await notification_service._notification_mail_config(db_session, employee.tenant_id)
        assert "erika@example.com" in config.opted_out
        await notification_service._mail(config, "Erika@Example.com", "Betreff", "Text")
        await notification_service._mail(config, "admin@example.com", "Betreff", "Text")
    assert [call.args[0] for call in send.await_args_list] == ["admin@example.com"]
