"""
tests/test_websocket.py — WebSocket ping/pong and broadcast tests.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient

from app.websocket import ConnectionManager


@pytest.mark.asyncio
async def test_connection_manager_broadcast() -> None:
    """Test that broadcast delivers messages to connected clients."""
    manager = ConnectionManager()

    # Mock WebSocket.
    received: list[str] = []

    class MockWS:
        async def accept(self) -> None:
            pass

        async def send_text(self, text: str) -> None:
            received.append(text)

        async def receive_text(self) -> str:
            # Simulate a ping then disconnect.
            raise Exception("test disconnect")

    ws = MockWS()
    await manager.connect(ws)

    assert manager.client_count == 1

    await manager.broadcast("events.updated", "events", {"count": 5})

    assert len(received) == 1
    envelope = json.loads(received[0])
    assert envelope["type"] == "events.updated"
    assert envelope["channel"] == "events"
    assert envelope["payload"]["count"] == 5
    assert "ts" in envelope

    manager.disconnect(ws)
    assert manager.client_count == 0


@pytest.mark.asyncio
async def test_connection_manager_channel_filtering() -> None:
    """Clients with subscriptions only receive messages on their channels."""
    manager = ConnectionManager()

    events_received: list[str] = []
    weather_received: list[str] = []

    class SubscribedWS:
        def __init__(self, channels: list[str], received_list: list[str]) -> None:
            self._channels = set(channels)
            self._received = received_list

        async def accept(self) -> None:
            pass

        async def send_text(self, text: str) -> None:
            self._received.append(text)

    ws_events = SubscribedWS(["events"], events_received)
    ws_weather = SubscribedWS(["weather"], weather_received)

    await manager.connect(ws_events)
    await manager.connect(ws_weather)

    # Set subscriptions.
    manager._clients[id(ws_events)].subscriptions = {"events"}
    manager._clients[id(ws_weather)].subscriptions = {"weather"}

    await manager.broadcast("events.updated", "events", {"count": 3})
    await manager.broadcast("weather.updated", "weather", {"temp": 22})

    assert len(events_received) == 1
    assert len(weather_received) == 1

    manager.disconnect(ws_events)
    manager.disconnect(ws_weather)


@pytest.mark.asyncio
async def test_connection_manager_dead_client_removed() -> None:
    """Dead connections (send raises) are silently removed from the registry."""
    manager = ConnectionManager()

    class DeadWS:
        async def accept(self) -> None:
            pass

        async def send_text(self, text: str) -> None:
            raise ConnectionError("client gone")

    ws = DeadWS()
    await manager.connect(ws)
    assert manager.client_count == 1

    # Broadcast should not raise and should clean up the dead client.
    await manager.broadcast("test.event", "test", {})
    assert manager.client_count == 0


@pytest.mark.asyncio
async def test_websocket_endpoint_ping_pong(app_client: AsyncClient) -> None:
    """Test the /ws endpoint ping/pong via Starlette's synchronous test client.

    httpx does not support WebSocket; we use Starlette's TestClient for this.
    """
    from app.main import create_app

    test_app = create_app()

    # Starlette TestClient handles WebSockets synchronously.
    with TestClient(test_app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "ping"})
        msg = ws.receive_json()
        assert msg["type"] == "pong"
        assert msg["channel"] == "system"
        assert "ts" in msg
