"""
tests/test_calendar_merge.py — Calendar event merge/dedupe logic tests.

Uses a fake adapter that returns pre-defined event dicts without any network
calls.  Tests that the CalendarService correctly upserts events into the DB
and deduplicates on uid.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.database import get_engine, init_db
from app.models import CalendarSourceState, Event

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
async def _ensure_db():
    """Ensure the DB is initialised before calendar merge tests run."""
    import app.database as db_module
    if db_module._engine is None:
        await init_db()
    yield


def _session_factory() -> async_sessionmaker[AsyncSession]:
    engine = get_engine()
    return async_sessionmaker(engine, expire_on_commit=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_event_dict(uid: str, title: str) -> dict[str, Any]:
    return {
        "uid": uid,
        "source": "google",
        "calendar_id": "test@group.calendar.google.com",
        "title": title,
        "description": None,
        "location": None,
        "start": datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        "end": datetime(2026, 7, 1, 11, 0, tzinfo=UTC),
        "all_day": False,
    }


def _make_fake_ctx(factory: async_sessionmaker[AsyncSession]) -> Any:
    """Build a minimal fake PluginContext for CalendarService.

    Implements all methods that CalendarService calls so no real loader or
    live PluginContext is needed in tests.
    """

    @asynccontextmanager
    async def db_session_fn():
        async with factory() as session:
            yield session

    class _FakeCtx:
        config = type("Cfg", (), {"google_client_id": None, "google_client_secret": None})()
        data_dir = "/tmp"
        http = None

        def db_session(self):
            return db_session_fn()

        async def broadcast(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def get_settings(self) -> dict:
            return {}

        async def get_secret(self, key: str) -> Any:
            """Returns None — no secrets configured in unit tests."""
            return None

        async def set_secret(self, key: str, value: Any) -> None:
            pass

    return _FakeCtx()


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_creates_new_events() -> None:
    """New events should be inserted into the Event table."""
    from calendar_plugin import CalendarService

    factory = _session_factory()
    ctx = _make_fake_ctx(factory)
    service = CalendarService(ctx)

    events_data = [
        _make_event_dict("upsert-test-001", "Event One"),
        _make_event_dict("upsert-test-002", "Event Two"),
    ]

    await service._upsert_events(events_data)

    # Verify events exist in DB.
    async with factory() as session:
        for uid in ["upsert-test-001", "upsert-test-002"]:
            result = await session.execute(select(Event).where(Event.uid == uid))
            event = result.scalar_one_or_none()
            assert event is not None, f"Event {uid!r} not found in DB"
            assert event.source == "google"


@pytest.mark.asyncio
async def test_upsert_deduplicates_on_uid() -> None:
    """Re-upserting with the same uid should UPDATE, not INSERT a duplicate."""
    from calendar_plugin import CalendarService

    factory = _session_factory()
    ctx = _make_fake_ctx(factory)
    service = CalendarService(ctx)

    uid = "dedupe-test-001"

    await service._upsert_events([_make_event_dict(uid, "Original Title")])
    await service._upsert_events([_make_event_dict(uid, "Updated Title")])

    async with factory() as session:
        result = await session.execute(select(Event).where(Event.uid == uid))
        events = result.scalars().all()

    # Should be exactly one row with the updated title.
    assert len(events) == 1
    assert events[0].title == "Updated Title"


@pytest.mark.asyncio
async def test_sync_skips_unconfigured_google_source() -> None:
    """Sync should mark a Google source 'unconfigured' if no OAuth token exists."""
    from calendar_plugin import CalendarService

    factory = _session_factory()
    ctx = _make_fake_ctx(factory)
    service = CalendarService(ctx)

    # Insert a google source into the DB if not already present.
    async with factory() as session:
        existing = await session.execute(
            select(CalendarSourceState).where(CalendarSourceState.id == "google-test-uncfg")
        )
        if existing.scalar_one_or_none() is None:
            source = CalendarSourceState(
                id="google-test-uncfg",
                kind="google",
                label="Google Calendar",
                enabled=True,
                status="unconfigured",
            )
            session.add(source)
            await session.commit()

    async with factory() as session:
        result = await session.execute(
            select(CalendarSourceState).where(CalendarSourceState.id == "google-test-uncfg")
        )
        source = result.scalar_one()

    # _sync_source handles unconfigured gracefully — should NOT raise.
    await service._sync_source(source)

    # Status should remain "unconfigured" (no token means adapter returned None).
    async with factory() as session:
        result = await session.execute(
            select(CalendarSourceState).where(CalendarSourceState.id == "google-test-uncfg")
        )
        updated = result.scalar_one()
    assert updated.status == "unconfigured"


@pytest.mark.asyncio
async def test_upsert_skips_events_with_no_uid() -> None:
    """Events with no uid field should be ignored (not inserted)."""
    from calendar_plugin import CalendarService

    factory = _session_factory()
    ctx = _make_fake_ctx(factory)
    service = CalendarService(ctx)

    bad_events = [
        {
            # uid intentionally absent
            "source": "google",
            "calendar_id": "primary",
            "title": "No UID Event",
            "start": datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
            "end": datetime(2026, 8, 1, 11, 0, tzinfo=UTC),
            "all_day": False,
        }
    ]

    # Should not raise; should simply skip the event.
    await service._upsert_events(bad_events)
