from app.services.ws_manager import LocationConnectionManager


class FakeWebSocket:
    def __init__(self, fail_send: bool = False) -> None:
        self.accepted = False
        self.sent: list[dict] = []
        self.fail_send = fail_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict) -> None:
        if self.fail_send:
            raise RuntimeError("connection closed")
        self.sent.append(message)


async def test_connect_registers_and_accepts_websocket() -> None:
    manager = LocationConnectionManager()
    ws = FakeWebSocket()

    await manager.connect(1, ws)

    assert ws.accepted is True
    assert ws in manager._connections[1]


async def test_broadcast_sends_to_all_connections_of_location_only() -> None:
    manager = LocationConnectionManager()
    ws_a1 = FakeWebSocket()
    ws_a2 = FakeWebSocket()
    ws_b1 = FakeWebSocket()
    await manager.connect(1, ws_a1)
    await manager.connect(1, ws_a2)
    await manager.connect(2, ws_b1)

    await manager.broadcast(1, {"type": "TEST"})

    assert ws_a1.sent == [{"type": "TEST"}]
    assert ws_a2.sent == [{"type": "TEST"}]
    assert ws_b1.sent == []


async def test_disconnect_removes_websocket() -> None:
    manager = LocationConnectionManager()
    ws = FakeWebSocket()
    await manager.connect(1, ws)

    manager.disconnect(1, ws)

    assert 1 not in manager._connections


async def test_broadcast_drops_dead_connections_without_raising() -> None:
    manager = LocationConnectionManager()
    dead = FakeWebSocket(fail_send=True)
    alive = FakeWebSocket()
    await manager.connect(1, dead)
    await manager.connect(1, alive)

    await manager.broadcast(1, {"type": "TEST"})

    assert alive.sent == [{"type": "TEST"}]
    assert dead not in manager._connections.get(1, set())
