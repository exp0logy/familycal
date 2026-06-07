"""
app/core/settings_store.py — Async get/set for the ``setting`` table.

Provides a thin typed wrapper around the Setting model with JSON value
serialisation and a **redact-by-default** helper used by GET /api/settings.

Redaction strategy (LOW-1 fix)
────────────────────────────────
Rather than pattern-matching against a keyword blocklist (which can silently
miss new secret keys), ``all(redact=True)`` now uses an explicit *allowlist*
of key prefixes that are safe to expose to the frontend.  Any key not on the
allowlist is returned as ``"<redacted>"``.

Add an entry to ``_SAFE_PREFIXES`` only for settings that are genuinely public
(display preferences, layout config, non-secret plugin settings, etc.).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import Setting

logger = logging.getLogger(__name__)

# ── Redaction allowlist ───────────────────────────────────────────────────────
# Keys whose prefix appears here are returned as-is in GET /api/settings.
# All other keys are redacted.  Prefix matching is case-sensitive and uses
# str.startswith() — so "display." covers "display.brightness", etc.
#
# Rule: only add a prefix when you are certain the value contains no secrets.
_SAFE_PREFIXES: tuple[str, ...] = (
    "display.",       # display preferences (brightness, orientation)
    "layout.",        # dashboard layout choices
    "theme.",         # colour scheme, font size
    "weather.",       # location label, units — no API keys
    "slideshow.",     # transition speed, duration — no API keys
    "calendar.sync_interval",   # numeric setting, not a secret
    "calendar.primary_source",  # source ID string, not a secret
    "app.",           # generic app-level non-secret config
    "ui.",            # UI preferences
)


def _is_safe_key(key: str) -> bool:
    """Return True if the key is on the explicit non-secret allowlist."""
    return key.startswith(_SAFE_PREFIXES)


class SettingsStore:
    """Async wrapper around the Setting table.

    Usage::

        store = SettingsStore(session)
        await store.set("display.brightness", 80)
        value = await store.get("display.brightness", default=100)
        all_settings = await store.all(redact=True)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str, *, default: Any = None) -> Any:
        """Return the value for ``key``, or ``default`` if absent."""
        result = await self._session.execute(
            select(Setting).where(Setting.key == key)
        )
        row: Setting | None = result.scalar_one_or_none()

        if row is None:
            return default

        return row.value

    async def set(self, key: str, value: Any) -> Setting:
        """Persist ``value`` under ``key`` (upsert).  Returns the updated row."""
        result = await self._session.execute(
            select(Setting).where(Setting.key == key)
        )
        row: Setting | None = result.scalar_one_or_none()

        if row is None:
            row = Setting(key=key)
            self._session.add(row)

        row.value = value                              # uses the property setter
        row.updated_at = datetime.now(UTC)

        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def delete(self, key: str) -> bool:
        """Remove ``key`` from the settings table.  Returns True if deleted."""
        result = await self._session.execute(
            select(Setting).where(Setting.key == key)
        )
        row: Setting | None = result.scalar_one_or_none()

        if row is None:
            return False

        await self._session.delete(row)
        await self._session.commit()
        return True

    async def all(self, *, redact: bool = False) -> dict[str, Any]:
        """Return all settings as a flat dict.

        If ``redact=True`` (the default for API responses), keys not in
        ``_SAFE_PREFIXES`` are replaced with ``"<redacted>"``.
        """
        result = await self._session.execute(select(Setting))
        rows: list[Setting] = result.scalars().all()

        out: dict[str, Any] = {}
        for row in rows:
            if redact and not _is_safe_key(row.key):
                out[row.key] = "<redacted>"
            else:
                out[row.key] = row.value

        return out

    async def get_row(self, key: str) -> Setting | None:
        """Return the raw Setting row (with timestamps), or None if absent."""
        result = await self._session.execute(
            select(Setting).where(Setting.key == key)
        )
        return result.scalar_one_or_none()
