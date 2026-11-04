from fastapi import WebSocket


class LocationConnectionManager:
    """Hält die verbundenen Kiosk-WebSockets pro Standort für Live-Updates
    (z.B. Saldo-Push nach einer Stempelung), siehe docs/konzept.md Abschnitt 5."""

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}

    async def connect(self, location_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(location_id, set()).add(websocket)

    def disconnect(self, location_id: int, websocket: WebSocket) -> None:
        connections = self._connections.get(location_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(location_id, None)

    async def broadcast(self, location_id: int, message: dict) -> None:
        for websocket in list(self._connections.get(location_id, set())):
            try:
                await websocket.send_json(message)
            except Exception:
                self.disconnect(location_id, websocket)


manager = LocationConnectionManager()
