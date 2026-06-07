"""
app/routers/system.py — Health and status endpoints.

Routes:
  GET  /api/system/health   → { status, version, time }
  GET  /api/system/status   → { sync, plugins, websocket_clients }
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.schemas import HealthResponse, PluginInfo, SyncStatusEntry, SystemStatusResponse
from app.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])

APP_VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Simple liveness check — always returns 200 if the app is running."""
    return HealthResponse(version=APP_VERSION)


@router.get("/status", response_model=SystemStatusResponse)
async def status(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> SystemStatusResponse:
    """Dashboard health snapshot: sync status, plugin list, WebSocket connections."""
    # ── Sync status ──────────────────────────────────────────────────────────
    sync_entries: list[SyncStatusEntry] = []
    try:
        from app.models import CalendarSourceState

        result = await session.execute(select(CalendarSourceState))
        sources = result.scalars().all()
        for src in sources:
            sync_entries.append(SyncStatusEntry(
                source=src.id,
                status=src.status,
                last_sync=src.last_sync,
                last_error=src.last_error,
            ))
    except Exception as exc:
        logger.warning("system/status: could not read calendar sources: %s", exc)

    # ── Plugin list ──────────────────────────────────────────────────────────
    plugin_infos: list[PluginInfo] = []
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is not None:
        try:
            raw = await loader.get_plugin_info_list()
            plugin_infos = [PluginInfo(**p) for p in raw]
        except Exception as exc:
            logger.warning("system/status: could not fetch plugin list: %s", exc)

    return SystemStatusResponse(
        sync=sync_entries,
        plugins=plugin_infos,
        websocket_clients=manager.client_count,
    )
