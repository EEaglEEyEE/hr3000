from datetime import timedelta

from fastapi import WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.ws import location_ws
from app.models import Device, Location
from app.services.auth_service import create_token
from app.services.pairing_service import token_hash


class FakeWebSocket:
    def __init__(self, token: str | None = None) -> None:
        self.query_params: dict[str, str] = {"token": token} if token is not None else {}
        self.accepted = False
        self.close_code: int | None = None
        self._receive_calls = 0

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int | None = None) -> None:
        self.close_code = code

    async def receive_text(self) -> str:
        self._receive_calls += 1
        raise WebSocketDisconnect()


async def _create_device(db_session: AsyncSession, token: str = "device-1") -> Device:
    location = Location(name="Standort A", timezone="UTC")
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)

    device = Device(location_id=location.id, token_hash=token_hash(token), name="Kiosk A1")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


async def test_ws_rejects_missing_token(db_session: AsyncSession) -> None:
    ws = FakeWebSocket(token=None)

    await location_ws(ws, location_id=1, db=db_session)

    assert ws.accepted is False
    assert ws.close_code == status.WS_1008_POLICY_VIOLATION


async def test_ws_rejects_invalid_token(db_session: AsyncSession) -> None:
    ws = FakeWebSocket(token="not-a-real-token")

    await location_ws(ws, location_id=1, db=db_session)

    assert ws.accepted is False
    assert ws.close_code == status.WS_1008_POLICY_VIOLATION


async def test_ws_rejects_hr_access_token(db_session: AsyncSession) -> None:
    token = create_token("1", "access", timedelta(minutes=5), {"role": "HR"})
    ws = FakeWebSocket(token=token)

    await location_ws(ws, location_id=1, db=db_session)

    assert ws.accepted is False
    assert ws.close_code == status.WS_1008_POLICY_VIOLATION


async def test_ws_rejects_device_for_wrong_location(db_session: AsyncSession) -> None:
    device = await _create_device(db_session)
    token = create_token(
        str(device.id), "device", timedelta(hours=1), {"location_id": device.location_id}
    )
    ws = FakeWebSocket(token=token)

    await location_ws(ws, location_id=device.location_id + 999, db=db_session)

    assert ws.accepted is False
    assert ws.close_code == status.WS_1008_POLICY_VIOLATION


async def test_ws_accepts_valid_device_and_disconnects_cleanly(db_session: AsyncSession) -> None:
    device = await _create_device(db_session)
    token = create_token(
        str(device.id), "device", timedelta(hours=1), {"location_id": device.location_id}
    )
    ws = FakeWebSocket(token=token)

    await location_ws(ws, location_id=device.location_id, db=db_session)

    assert ws.accepted is True
    assert ws.close_code is None
