"""
app/routers/events.py — CRUD and query for calendar events.

Routes:
  GET    /api/events?start=<iso>&end=<iso>&profile_id=<id>  → Event[]
  GET    /api/events/agenda?days=<n>                         → Event[]
  POST   /api/events                                         → Event
  PATCH  /api/events/{id}                                    → Event
  DELETE /api/events/{id}                                    → 204

POSTing a non-local event delegates to the calendar plugin's write_event()
service if available, so external calendars stay in sync.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.models import Event
from app.schemas import EventCreate, EventRead, EventUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["events"])


def _event_to_read(event: Event) -> EventRead:
    """Convert an Event model to the EventRead DTO (handling profile_ids_json)."""
    return EventRead(
        id=event.id,
        uid=event.uid,
        source=event.source,
        calendar_id=event.calendar_id,
        title=event.title,
        description=event.description,
        location=event.location,
        start=event.start,
        end=event.end,
        all_day=event.all_day,
        profile_ids=event.get_profile_ids(),
        color=event.color,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


@router.get("", response_model=list[EventRead])
async def list_events(
    start: str | None = Query(default=None, description="ISO8601 start bound"),
    end: str | None = Query(default=None, description="ISO8601 end bound"),
    profile_id: int | None = Query(default=None, description="Filter by profile ID"),
    session: AsyncSession = Depends(get_session),
) -> list[EventRead]:
    """Return events within the optional date range, optionally filtered by profile."""
    stmt = select(Event).order_by(Event.start)

    if start:
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError as err:
            raise HTTPException(status_code=422, detail="Invalid `start` ISO8601 datetime") from err
        stmt = stmt.where(Event.start >= start_dt)

    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except ValueError as err:
            raise HTTPException(status_code=422, detail="Invalid `end` ISO8601 datetime") from err
        stmt = stmt.where(Event.end <= end_dt)

    result = await session.execute(stmt)
    events = result.scalars().all()

    if profile_id is not None:
        # Filter in Python — JSON column search is not portable across DB backends.
        events = [e for e in events if profile_id in e.get_profile_ids()]

    return [_event_to_read(e) for e in events]


@router.get("/agenda", response_model=list[EventRead])
async def get_agenda(
    days: int = Query(default=7, ge=1, le=365, description="Days ahead to include"),
    session: AsyncSession = Depends(get_session),
) -> list[EventRead]:
    """Return events from today through today + days, ordered by start time."""
    now = datetime.now(UTC)
    end_dt = now + timedelta(days=days)

    stmt = (
        select(Event)
        .where(Event.start >= now)
        .where(Event.start <= end_dt)
        .order_by(Event.start)
    )
    result = await session.execute(stmt)
    events = result.scalars().all()
    return [_event_to_read(e) for e in events]


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: EventCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> EventRead:
    """Create a new event.

    If ``source != "local"``, attempts to delegate the write to the calendar
    plugin's ``write_event()`` service so the external calendar stays in sync.
    If the plugin is unavailable the event is still saved locally.
    """
    # Auto-generate UID for new events.
    uid = body.uid or str(uuid.uuid4())

    # Check for UID collision.
    existing = await session.execute(select(Event).where(Event.uid == uid))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Event with uid={uid!r} already exists")

    event = Event(
        uid=uid,
        source=body.source,
        calendar_id=body.calendar_id,
        title=body.title,
        description=body.description,
        location=body.location,
        start=body.start,
        end=body.end,
        all_day=body.all_day,
        color=body.color,
    )
    event.set_profile_ids(body.profile_ids)

    session.add(event)
    await session.commit()
    await session.refresh(event)

    # Delegate to calendar plugin if this is a non-local event.
    if body.source != "local":
        await _write_to_source(request, event, body)

    return _event_to_read(event)


async def _write_to_source(request: Request, event: Event, body: EventCreate) -> None:
    """Try to write the event to its source calendar via the capability registry.

    The calendar plugin registers ``"calendar.write_event"`` in start(); the
    core resolves it here without importing the plugin package.  Failures are
    logged but do not propagate — the local copy is always preserved.
    """
    try:
        cap_registry = getattr(request.app.state, "capabilities", None)
        write_fn = cap_registry.resolve("calendar.write_event") if cap_registry else None
        if write_fn is not None:
            await write_fn(event)
        else:
            logger.debug(
                "calendar.write_event capability not registered; "
                "event %r saved locally only.", event.uid
            )
    except Exception as exc:
        logger.warning("Failed to write event %r to source %r: %s", event.uid, event.source, exc)


@router.patch("/{event_id}", response_model=EventRead)
async def update_event(
    event_id: int,
    body: EventUpdate,
    session: AsyncSession = Depends(get_session),
) -> EventRead:
    """Update mutable fields on an existing event."""
    result = await session.execute(select(Event).where(Event.id == event_id))
    event: Event | None = result.scalar_one_or_none()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if body.title is not None:
        event.title = body.title
    if body.description is not None:
        event.description = body.description
    if body.location is not None:
        event.location = body.location
    if body.start is not None:
        event.start = body.start
    if body.end is not None:
        event.end = body.end
    if body.all_day is not None:
        event.all_day = body.all_day
    if body.profile_ids is not None:
        event.set_profile_ids(body.profile_ids)
    if body.color is not None:
        event.color = body.color

    event.updated_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(event)
    return _event_to_read(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete an event by ID."""
    result = await session.execute(select(Event).where(Event.id == event_id))
    event: Event | None = result.scalar_one_or_none()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    await session.delete(event)
    await session.commit()
