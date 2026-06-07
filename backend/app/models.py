"""
app/models.py — SQLModel table definitions.

All tables map 1-to-1 with the JSON shapes specified in ARCHITECTURE.md §3.
Secrets (OAuth tokens, CalDAV passwords) live in the ``Secret`` table,
Fernet-encrypted at rest, and are NEVER serialised to the frontend.

``profile_ids`` on Event is stored as a JSON column (list of ints) to keep the
schema simple while matching the DTO shape exactly.  The column is accessed as
``profile_ids_json`` in SQLModel; the schema layer converts it to a real list
before responding to the frontend.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel

# ── Utilities ────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


# ── Profile ──────────────────────────────────────────────────────────────────

class Profile(SQLModel, table=True):
    """A family member profile.

    JSON shape::

        { id, name, color, emoji, created_at }
    """

    __tablename__ = "profile"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, nullable=False)
    color: str = Field(default="#6366f1")    # hex colour, e.g. "#6366f1"
    emoji: str = Field(default="👤")
    created_at: datetime = Field(default_factory=_now_utc)


# ── Event ────────────────────────────────────────────────────────────────────

class Event(SQLModel, table=True):
    """A calendar event, unified across all calendar sources.

    ``profile_ids_json`` stores a JSON list of profile IDs (e.g. ``"[1,3]"``).
    Use the ``get_profile_ids()`` / ``set_profile_ids()`` helpers on this class
    or let the schema layer (EventRead) handle conversion.

    JSON shape::

        { id, uid, source, calendar_id, title, description, location,
          start, end, all_day, profile_ids, color, created_at, updated_at }
    """

    __tablename__ = "event"

    id: int | None = Field(default=None, primary_key=True)

    # Stable UID from the originating calendar system (used for deduplication
    # during sync).  Local events use a generated UUID.
    uid: str = Field(index=True, nullable=False, unique=True)

    # One of: local, google, caldav, outlook
    source: str = Field(default="local", nullable=False)

    # Identifier of the source calendar (e.g. Google calendar ID, CalDAV URL)
    calendar_id: str = Field(default="local", nullable=False)

    title: str = Field(nullable=False)
    description: str | None = Field(default=None)
    location: str | None = Field(default=None)

    start: datetime = Field(nullable=False)
    end: datetime = Field(nullable=False)
    all_day: bool = Field(default=False)

    # JSON list of profile IDs, e.g. "[1, 3]".
    # Use get_profile_ids() / set_profile_ids() for typed access.
    profile_ids_json: str = Field(
        default="[]",
        sa_column=Column("profile_ids", Text, nullable=False, server_default="[]"),
    )

    # Resolved display colour (first tagged profile's colour or source default)
    color: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)

    # ── profile_ids helpers ──────────────────────────────────────────────────

    def get_profile_ids(self) -> list[int]:
        """Deserialise and return the profile_ids list."""
        try:
            return json.loads(self.profile_ids_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    def set_profile_ids(self, value: list[int]) -> None:
        """Serialise and store the profile_ids list."""
        self.profile_ids_json = json.dumps(value or [])


# ── Setting ──────────────────────────────────────────────────────────────────

class Setting(SQLModel, table=True):
    """Generic key/value settings store.

    Values are serialised as JSON strings so any JSON-serialisable type
    (string, number, object, array) can be stored.

    JSON shape::

        { key, value, updated_at }
    """

    __tablename__ = "setting"

    key: str = Field(primary_key=True, nullable=False)

    # JSON-encoded value; decoded by the settings store before returning.
    value_json: str = Field(
        default="null",
        sa_column=Column("value", Text, nullable=False, server_default="null"),
    )

    updated_at: datetime = Field(default_factory=_now_utc)

    # ── value helpers ────────────────────────────────────────────────────────

    @property
    def value(self) -> Any:
        """Deserialise and return the stored value."""
        try:
            return json.loads(self.value_json or "null")
        except (json.JSONDecodeError, TypeError):
            return None

    @value.setter
    def value(self, v: Any) -> None:
        self.value_json = json.dumps(v)


# ── CalendarSourceState ──────────────────────────────────────────────────────

class CalendarSourceState(SQLModel, table=True):
    """Persisted state for a configured calendar source.

    The ``extra_json`` column holds arbitrary source-specific data (e.g. Google
    Calendar list, CalDAV principal URL) without requiring schema changes.

    JSON shape::

        { id, kind, label, enabled, primary, status, last_sync, last_error }
    """

    __tablename__ = "calendar_source"

    id: str = Field(primary_key=True)   # e.g. "google", "caldav:uuid", "outlook"
    kind: str = Field(nullable=False)   # google | caldav | outlook
    label: str = Field(nullable=False)
    enabled: bool = Field(default=True)
    primary: bool = Field(default=False)

    # One of: ok, error, syncing, unconfigured
    status: str = Field(default="unconfigured")

    last_sync: datetime | None = Field(default=None)
    last_error: str | None = Field(default=None)

    # Arbitrary extra data for the source; not exposed to the frontend.
    extra_json: str = Field(
        default="{}",
        sa_column=Column("extra", Text, nullable=False, server_default="{}"),
    )

    def get_extra(self) -> dict[str, Any]:
        try:
            return json.loads(self.extra_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_extra(self, v: dict[str, Any]) -> None:
        self.extra_json = json.dumps(v)


# ── PluginConfig ─────────────────────────────────────────────────────────────

class PluginConfig(SQLModel, table=True):
    """Enabled/disabled flag + JSON settings blob for each discovered plugin.

    JSON shape (PluginInfo DTO adds runtime fields)::

        { name, enabled, settings_json }
    """

    __tablename__ = "plugin_config"

    name: str = Field(primary_key=True)
    enabled: bool = Field(default=True)

    # Plugin-specific settings serialised as JSON.
    settings_json: str = Field(
        default="{}",
        sa_column=Column("settings", Text, nullable=False, server_default="{}"),
    )

    def get_settings(self) -> dict[str, Any]:
        try:
            return json.loads(self.settings_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_settings(self, v: dict[str, Any]) -> None:
        self.settings_json = json.dumps(v)


# ── Secret ───────────────────────────────────────────────────────────────────

class Secret(SQLModel, table=True):
    """Encrypted-at-rest secret store.

    The ``value`` column contains a Fernet-encrypted UTF-8 byte string that
    decrypts to a JSON-serialised value.  Use ``core.crypto.SecretStore`` for
    all access — never read/write this table directly.

    This table is NEVER serialised to the frontend.
    """

    __tablename__ = "secret"

    key: str = Field(primary_key=True)        # e.g. "oauth.google", "caldav.uuid"
    value: str = Field(nullable=False)         # Fernet token (base64 string)
    updated_at: datetime = Field(default_factory=_now_utc)
