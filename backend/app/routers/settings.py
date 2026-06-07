"""
app/routers/settings.py — Generic key/value settings API.

Routes:
  GET  /api/settings          → { [key]: value }  (secrets redacted)
  GET  /api/settings/{key}    → { key, value }
  PUT  /api/settings/{key}    → { key, value }     body: { value: any }
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings_store import SettingsStore
from app.database import get_session
from app.schemas import SettingRead, SettingWrite
from app.websocket import manager

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=dict[str, Any])
async def get_all_settings(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return all settings as a flat dict.  Secret values are redacted."""
    store = SettingsStore(session)
    return await store.all(redact=True)


@router.get("/{key}", response_model=SettingRead)
async def get_setting(
    key: str,
    session: AsyncSession = Depends(get_session),
) -> SettingRead:
    """Return a single setting by key."""
    store = SettingsStore(session)
    row = await store.get_row(key)

    if row is None:
        raise HTTPException(status_code=404, detail=f"Setting {key!r} not found")

    return SettingRead(key=row.key, value=row.value, updated_at=row.updated_at)


@router.put("/{key}", response_model=SettingRead)
async def put_setting(
    key: str,
    body: SettingWrite,
    session: AsyncSession = Depends(get_session),
) -> SettingRead:
    """Create or update a setting.  Broadcasts a settings.updated WebSocket event."""
    store = SettingsStore(session)
    row = await store.set(key, body.value)

    # Notify connected clients that this key changed.
    await manager.broadcast("settings.updated", "settings", {"key": key})

    return SettingRead(key=row.key, value=row.value, updated_at=row.updated_at)
