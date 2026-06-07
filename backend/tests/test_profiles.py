"""
tests/test_profiles.py — Profile CRUD endpoint tests.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_profiles(app_client: AsyncClient) -> None:
    # Create two profiles.
    r1 = await app_client.post(
        "/api/profiles",
        json={"name": "Alice", "color": "#ff0000", "emoji": "👩"},
    )
    assert r1.status_code == 201
    alice = r1.json()
    assert alice["name"] == "Alice"
    assert alice["color"] == "#ff0000"
    assert alice["id"] is not None

    r2 = await app_client.post(
        "/api/profiles",
        json={"name": "Bob", "color": "#0000ff", "emoji": "👦"},
    )
    assert r2.status_code == 201

    # List should return both.
    r_list = await app_client.get("/api/profiles")
    assert r_list.status_code == 200
    names = [p["name"] for p in r_list.json()]
    assert "Alice" in names
    assert "Bob" in names


@pytest.mark.asyncio
async def test_update_profile(app_client: AsyncClient) -> None:
    # Create a profile.
    r = await app_client.post(
        "/api/profiles",
        json={"name": "Charlie", "color": "#00ff00", "emoji": "🧑"},
    )
    assert r.status_code == 201
    profile_id = r.json()["id"]

    # Update its name.
    r_update = await app_client.patch(
        f"/api/profiles/{profile_id}",
        json={"name": "Charles"},
    )
    assert r_update.status_code == 200
    assert r_update.json()["name"] == "Charles"
    # Other fields unchanged.
    assert r_update.json()["color"] == "#00ff00"


@pytest.mark.asyncio
async def test_delete_profile(app_client: AsyncClient) -> None:
    r = await app_client.post(
        "/api/profiles",
        json={"name": "ToDelete", "color": "#ffffff", "emoji": "🗑️"},
    )
    profile_id = r.json()["id"]

    r_del = await app_client.delete(f"/api/profiles/{profile_id}")
    assert r_del.status_code == 204

    # Deleting again returns 404.
    r_del2 = await app_client.delete(f"/api/profiles/{profile_id}")
    assert r_del2.status_code == 404


@pytest.mark.asyncio
async def test_profile_not_found_returns_404(app_client: AsyncClient) -> None:
    r = await app_client.patch("/api/profiles/99999", json={"name": "Ghost"})
    assert r.status_code == 404
    assert "detail" in r.json()


@pytest.mark.asyncio
async def test_create_profile_invalid_color(app_client: AsyncClient) -> None:
    r = await app_client.post(
        "/api/profiles",
        json={"name": "Bad Color", "color": "not-a-hex"},
    )
    assert r.status_code == 422
