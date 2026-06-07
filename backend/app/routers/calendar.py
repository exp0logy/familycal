"""
app/routers/calendar.py — Calendar source management and sync control.

Routes:
  GET    /api/calendar/sources              → CalendarSource[]
  PATCH  /api/calendar/sources/{id}         → CalendarSource
  POST   /api/calendar/sync                 → { started: true }
  POST   /api/calendar/sources/caldav       → CalendarSource

Calendar operations (sync, credential storage) are dispatched via the
capability registry so this router never imports from the calendar plugin
package directly.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.models import CalendarSourceState
from app.schemas import CalDAVCreate, CalendarSourceRead, CalendarSourceUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


def _source_to_read(src: CalendarSourceState) -> CalendarSourceRead:
    return CalendarSourceRead(
        id=src.id,
        kind=src.kind,
        label=src.label,
        enabled=src.enabled,
        primary=src.primary,
        status=src.status,
        last_sync=src.last_sync,
        last_error=src.last_error,
    )


def _resolve(request: Request, capability: str):
    """Return the callable registered under ``capability``, or None."""
    cap_registry = getattr(request.app.state, "capabilities", None)
    return cap_registry.resolve(capability) if cap_registry else None


@router.get("/sources", response_model=list[CalendarSourceRead])
async def list_sources(
    session: AsyncSession = Depends(get_session),
) -> list[CalendarSourceRead]:
    """Return all configured calendar sources."""
    result = await session.execute(select(CalendarSourceState).order_by(CalendarSourceState.kind))
    sources = result.scalars().all()
    return [_source_to_read(s) for s in sources]


@router.patch("/sources/{source_id}", response_model=CalendarSourceRead)
async def update_source(
    source_id: str,
    body: CalendarSourceUpdate,
    session: AsyncSession = Depends(get_session),
) -> CalendarSourceRead:
    """Toggle enabled / primary on a calendar source."""
    result = await session.execute(
        select(CalendarSourceState).where(CalendarSourceState.id == source_id)
    )
    source: CalendarSourceState | None = result.scalar_one_or_none()

    if source is None:
        raise HTTPException(status_code=404, detail="Calendar source not found")

    if body.enabled is not None:
        source.enabled = body.enabled
    if body.primary is not None:
        source.primary = body.primary

    await session.commit()
    await session.refresh(source)
    return _source_to_read(source)


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(request: Request) -> dict[str, bool]:
    """Trigger an immediate background calendar sync via the capability registry.

    Returns ``{started: true}`` regardless of whether the calendar plugin is
    loaded — if not loaded, no sync runs but the app remains stable.
    """
    sync_fn = _resolve(request, "calendar.sync_all")
    if sync_fn is not None:
        asyncio.create_task(sync_fn())
        logger.info("Manual calendar sync triggered.")
    else:
        logger.debug("calendar.sync_all capability not registered; sync ignored.")

    return {"started": True}


@router.post("/sources/caldav", response_model=CalendarSourceRead, status_code=status.HTTP_201_CREATED)
async def add_caldav_source(
    body: CalDAVCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> CalendarSourceRead:
    """Register a new CalDAV source and store credentials encrypted.

    Raises 503 if SECRET_KEY is not configured (fail-closed).
    Raises 422 if the CalDAV URL fails validation (SSRF guard).
    """
    source_id = f"caldav:{uuid.uuid4().hex[:8]}"
    label = body.label or body.url

    source = CalendarSourceState(
        id=source_id,
        kind="caldav",
        label=label,
        enabled=True,
        primary=False,
        status="unconfigured",   # updated to "ok" after first sync
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)

    store_fn = _resolve(request, "calendar.store_caldav_credentials")
    if store_fn is not None:
        try:
            await store_fn(
                source_id=source_id,
                url=body.url,
                username=body.username,
                password=body.password,
            )
        except RuntimeError as exc:
            # SecretStore.set() raises RuntimeError when SECRET_KEY is absent.
            # Roll back the source row so we don't leave an uncredentialed stub.
            await session.delete(source)
            await session.commit()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Failed to store CalDAV credentials for %r: %s", source_id, exc)
            source.status = "error"
            source.last_error = str(exc)
            await session.commit()
    else:
        logger.warning(
            "calendar.store_caldav_credentials capability not registered; "
            "CalDAV credentials NOT stored for %r.", source_id
        )

    return _source_to_read(source)
