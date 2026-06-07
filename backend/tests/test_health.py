"""
tests/test_health.py — Health and system status endpoint tests.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/system/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "time" in body


@pytest.mark.asyncio
async def test_system_status_structure(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "sync" in body
    assert "plugins" in body
    assert "websocket_clients" in body
    assert isinstance(body["sync"], list)
    assert isinstance(body["plugins"], list)
    assert isinstance(body["websocket_clients"], int)
