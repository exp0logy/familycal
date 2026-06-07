"""
tests/test_settings.py — Settings endpoint tests.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_all_settings_empty(app_client: AsyncClient) -> None:
    r = await app_client.get("/api/settings")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


@pytest.mark.asyncio
async def test_set_and_get_setting(app_client: AsyncClient) -> None:
    r = await app_client.put("/api/settings/display.brightness", json={"value": 75})
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "display.brightness"
    assert body["value"] == 75

    r_get = await app_client.get("/api/settings/display.brightness")
    assert r_get.status_code == 200
    assert r_get.json()["value"] == 75


@pytest.mark.asyncio
async def test_set_setting_with_object_value(app_client: AsyncClient) -> None:
    r = await app_client.put(
        "/api/settings/theme.config",
        json={"value": {"mode": "dark", "accent": "#6366f1"}},
    )
    assert r.status_code == 200
    assert r.json()["value"]["mode"] == "dark"


@pytest.mark.asyncio
async def test_get_missing_setting_returns_404(app_client: AsyncClient) -> None:
    r = await app_client.get("/api/settings/does.not.exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_secret_key_is_redacted_in_list(app_client: AsyncClient) -> None:
    """Redact-by-default: only keys matching _SAFE_PREFIXES are returned as-is."""
    # A key NOT on the safe prefix list should be redacted.
    await app_client.put("/api/settings/oauth.google_secret", json={"value": "super_secret_value"})
    # A key on the safe prefix list should be visible.
    await app_client.put("/api/settings/display.brightness", json={"value": 80})

    r = await app_client.get("/api/settings")
    body = r.json()

    # Not on allowlist → redacted regardless of whether the name looks secret.
    assert body.get("oauth.google_secret") == "<redacted>"
    # On allowlist → returned as-is.
    assert body.get("display.brightness") == 80


@pytest.mark.asyncio
async def test_update_setting_overwrites_value(app_client: AsyncClient) -> None:
    await app_client.put("/api/settings/update.test", json={"value": "first"})
    await app_client.put("/api/settings/update.test", json={"value": "second"})

    r = await app_client.get("/api/settings/update.test")
    assert r.json()["value"] == "second"
