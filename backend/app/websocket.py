"""
app/websocket.py — WebSocket connection manager and broadcast hub.

Implements the protocol described in ARCHITECTURE.md §4:
- Server → client: JSON envelope { type, channel, payload, ts }
- Client → server: { "type": "ping" } → pong; { "type": "subscribe", "channels": [...] }
- Clients that do not subscribe are subscribed to all channels by default.

LAN limits (LOW-3):
- MAX_CONNECTIONS: maximum simultaneous WebSocket clients.  This is a LAN-only
  family dashboard — 50 is generous.  New connections beyond this cap are closed
  with 1008 (policy violation).
- MAX_MESSAGE_BYTES: inbound message size limit.  Client messages are tiny
  (ping / subscribe JSON).  4 KB is far more than needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

MAX_CONNECTIONS: int = 50
MAX_MESSAGE_BYTES: int = 4 * 1024   # 4 KB


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class _ClientState:
    """Per-connection state: the WebSocket handle and optional channel filter."""

    __slots__ = ("ws", "subscriptions")

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        # None means "subscribe to all channels"
        self.subscriptions: set[str] | None = None


class ConnectionManager:
    """Thread-safe WebSocket broadcast hub.

    Exposed to plugins via ``PluginContext.broadcast()``.

    Usage (in the /ws endpoint)::

        manager = ConnectionManager()

        @app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket):
            await manager.connect(websocket)
            try:
                await manager.handle(websocket)
            finally:
                manager.disconnect(websocket)
    """

    def __init__(self) -> None:
        self._clients: dict[int, _ClientState] = {}   # id(ws) → state
        self._lock = asyncio.Lock()

    # ── Connection lifecycle ─────────────────────────────────────────────────

    async def connect(self, ws: WebSocket) -> None:
        """Accept the WebSocket and register the client.

        Rejects new connections with 1008 (Policy Violation) when
        ``MAX_CONNECTIONS`` is already reached.
        """
        # Check before accepting so the handshake is never completed for
        # connections we intend to reject.
        if len(self._clients) >= MAX_CONNECTIONS:
            await ws.close(code=1008, reason="Too many connections")
            logger.warning("WS connection rejected: MAX_CONNECTIONS (%d) reached.", MAX_CONNECTIONS)
            raise WebSocketDisconnect(code=1008)

        await ws.accept()
        async with self._lock:
            self._clients[id(ws)] = _ClientState(ws)
        logger.debug("WS client connected (%d total)", len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        """Unregister the client (call in a finally block)."""
        self._clients.pop(id(ws), None)
        logger.debug("WS client disconnected (%d remaining)", len(self._clients))

    @property
    def client_count(self) -> int:
        return len(self._clients)

    # ── Message handling ─────────────────────────────────────────────────────

    async def handle(self, ws: WebSocket) -> None:
        """Drive the receive loop for a single client connection.

        Handles ``ping`` and ``subscribe`` messages; ignores unknown types.
        Raises ``WebSocketDisconnect`` when the client closes the connection.
        """
        while True:
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                logger.warning("WS receive error: %s", exc)
                break

            # Enforce inbound message size limit.
            if len(raw.encode()) > MAX_MESSAGE_BYTES:
                logger.warning(
                    "WS message exceeds MAX_MESSAGE_BYTES (%d); closing connection.",
                    MAX_MESSAGE_BYTES,
                )
                await ws.close(code=1009, reason="Message too large")
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.debug("WS received non-JSON message, ignoring")
                continue

            msg_type = msg.get("type")

            if msg_type == "ping":
                await self._send_one(ws, "pong", "system", {})

            elif msg_type == "subscribe":
                channels = msg.get("channels")
                if isinstance(channels, list):
                    async with self._lock:
                        state = self._clients.get(id(ws))
                        if state:
                            state.subscriptions = set(channels)
                    logger.debug("WS client subscribed to %s", channels)

            else:
                logger.debug("WS unknown message type %r, ignoring", msg_type)

    # ── Broadcasting ─────────────────────────────────────────────────────────

    async def broadcast(self, type_: str, channel: str, payload: Any) -> None:
        """Send a message to all clients subscribed to ``channel``.

        Clients that have not called ``subscribe`` receive all messages.
        Dead connections are silently removed.
        """
        envelope = json.dumps({
            "type": type_,
            "channel": channel,
            "payload": payload,
            "ts": _now_iso(),
        })

        dead: list[int] = []

        async with self._lock:
            snapshot = list(self._clients.items())

        for cid, state in snapshot:
            # Deliver if the client is subscribed to this channel or all.
            if state.subscriptions is None or channel in state.subscriptions:
                try:
                    await state.ws.send_text(envelope)
                except Exception as exc:
                    logger.debug("WS send failed (client %d): %s — removing", cid, exc)
                    dead.append(cid)

        if dead:
            async with self._lock:
                for cid in dead:
                    self._clients.pop(cid, None)

    # ── Convenience senders ──────────────────────────────────────────────────

    async def _send_one(
        self, ws: WebSocket, type_: str, channel: str, payload: Any
    ) -> None:
        """Send a message to a single WebSocket client."""
        envelope = json.dumps({
            "type": type_,
            "channel": channel,
            "payload": payload,
            "ts": _now_iso(),
        })
        try:
            await ws.send_text(envelope)
        except Exception as exc:
            logger.debug("WS single send failed: %s", exc)


# Module-level singleton shared by main.py and plugins.
manager = ConnectionManager()
