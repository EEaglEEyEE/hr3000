from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import AppError
from app.models import Device, Location
from app.services.auth_service import decode_token
from app.services.ws_manager import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/location/{location_id}")
async def location_ws(
    websocket: WebSocket, location_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    """Live-Updates an Kiosks eines Standorts (z.B. Saldo-Push nach Stempelung).
    Authentifizierung über das Device-JWT als Query-Parameter ?token=...,
    da der WebSocket-Handshake keinen Authorization-Header vom Browser/App
    zulässt."""
    token = websocket.query_params.get("token")
    if token is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = decode_token(token)
    except AppError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if payload.get("type") != "device":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Die Tenant-Resolution-Middleware greift nicht für WebSocket-Scopes (Starlettes
    # BaseHTTPMiddleware unterstützt nur "http"), daher gibt es hier kein
    # request.state.tenant. Die Mandantenzugehörigkeit wird stattdessen direkt aus
    # dem Device/Location-Datensatz abgeleitet statt aus dem Host-Header.
    device = await db.get(Device, int(payload["sub"]))
    if device is None or device.location_id != location_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    location = await db.get(Location, location_id)
    if location is None or location.tenant_id != device.tenant_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(location_id, websocket)
    try:
        while True:
            # Kiosk sendet i.d.R. nichts von sich aus; hält die Verbindung offen.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(location_id, websocket)
