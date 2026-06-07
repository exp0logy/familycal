"""
tests/test_events.py — Event CRUD, agenda, and profile-tag filtering tests.
"""

from __future__ import annotations

from datetime import UTC

import pytest
from httpx import AsyncClient

_EVENT_BASE = {
    "title": "Team Lunch",
    "start": "2026-07-01T12:00:00+00:00",
    "end": "2026-07-01T13:00:00+00:00",
}


@pytest.mark.asyncio
async def test_create_and_list_events(app_client: AsyncClient) -> None:
    r = await app_client.post("/api/events", json=_EVENT_BASE)
    assert r.status_code == 201
    event = r.json()
    assert event["title"] == "Team Lunch"
    assert event["source"] == "local"
    assert event["uid"] is not None
    assert event["profile_ids"] == []

    r_list = await app_client.get("/api/events")
    assert r_list.status_code == 200
    titles = [e["title"] for e in r_list.json()]
    assert "Team Lunch" in titles


@pytest.mark.asyncio
async def test_create_event_with_profile_ids(app_client: AsyncClient) -> None:
    # Create a profile first.
    r_prof = await app_client.post(
        "/api/profiles",
        json={"name": "Dana", "color": "#abc123", "emoji": "👩"},
    )
    profile_id = r_prof.json()["id"]

    r = await app_client.post(
        "/api/events",
        json={**_EVENT_BASE, "profile_ids": [profile_id], "title": "Dana's Event"},
    )
    assert r.status_code == 201
    assert r.json()["profile_ids"] == [profile_id]


@pytest.mark.asyncio
async def test_update_event(app_client: AsyncClient) -> None:
    r = await app_client.post("/api/events", json=_EVENT_BASE)
    event_id = r.json()["id"]

    r_update = await app_client.patch(
        f"/api/events/{event_id}",
        json={"title": "Updated Lunch", "location": "Cafe"},
    )
    assert r_update.status_code == 200
    assert r_update.json()["title"] == "Updated Lunch"
    assert r_update.json()["location"] == "Cafe"


@pytest.mark.asyncio
async def test_delete_event(app_client: AsyncClient) -> None:
    r = await app_client.post("/api/events", json=_EVENT_BASE)
    event_id = r.json()["id"]

    r_del = await app_client.delete(f"/api/events/{event_id}")
    assert r_del.status_code == 204

    r_del2 = await app_client.delete(f"/api/events/{event_id}")
    assert r_del2.status_code == 404


@pytest.mark.asyncio
async def test_event_uid_uniqueness(app_client: AsyncClient) -> None:
    r1 = await app_client.post(
        "/api/events",
        json={**_EVENT_BASE, "uid": "unique-uid-001"},
    )
    assert r1.status_code == 201

    r2 = await app_client.post(
        "/api/events",
        json={**_EVENT_BASE, "uid": "unique-uid-001"},
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_agenda_returns_upcoming_events(app_client: AsyncClient) -> None:
    # Create an event within the next 365 days.
    from datetime import datetime, timedelta

    soon = datetime.now(UTC) + timedelta(days=30)
    soon_end = soon + timedelta(hours=1)
    near_future = {
        "title": "Near Future Event",
        "start": soon.isoformat(),
        "end": soon_end.isoformat(),
    }
    await app_client.post("/api/events", json=near_future)

    r = await app_client.get("/api/events/agenda?days=60")
    assert r.status_code == 200
    titles = [e["title"] for e in r.json()]
    assert "Near Future Event" in titles


@pytest.mark.asyncio
async def test_events_date_filter(app_client: AsyncClient) -> None:
    await app_client.post(
        "/api/events",
        json={
            "title": "July Event",
            "start": "2026-07-15T10:00:00+00:00",
            "end": "2026-07-15T11:00:00+00:00",
        },
    )
    await app_client.post(
        "/api/events",
        json={
            "title": "August Event",
            "start": "2026-08-15T10:00:00+00:00",
            "end": "2026-08-15T11:00:00+00:00",
        },
    )

    r = await app_client.get(
        "/api/events",
        params={"start": "2026-07-01T00:00:00+00:00", "end": "2026-07-31T23:59:59+00:00"},
    )
    assert r.status_code == 200
    titles = [e["title"] for e in r.json()]
    assert "July Event" in titles
    assert "August Event" not in titles


@pytest.mark.asyncio
async def test_event_end_before_start_rejected(app_client: AsyncClient) -> None:
    r = await app_client.post(
        "/api/events",
        json={
            "title": "Bad Times",
            "start": "2026-07-01T12:00:00+00:00",
            "end": "2026-07-01T11:00:00+00:00",   # end before start
        },
    )
    assert r.status_code == 422
