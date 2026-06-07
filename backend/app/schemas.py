"""
app/schemas.py — Pydantic request/response DTOs.

These are the shapes that cross the HTTP boundary.  They intentionally differ
from the SQLModel table classes so we can control exactly what fields are
serialised (e.g. secrets are excluded from all response models).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ── Utilities ────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(UTC)


# ══════════════════════════════════════════════════════════════════════════════
# Profile DTOs
# ══════════════════════════════════════════════════════════════════════════════

class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")
    emoji: str = Field(default="👤", max_length=8)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    emoji: str | None = Field(default=None, max_length=8)


class ProfileRead(BaseModel):
    id: int
    name: str
    color: str
    emoji: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════════
# Event DTOs
# ══════════════════════════════════════════════════════════════════════════════

class EventCreate(BaseModel):
    uid: str | None = None                   # auto-generated if absent
    source: str = Field(default="local")
    calendar_id: str = Field(default="local")
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    location: str | None = None
    start: datetime
    end: datetime
    all_day: bool = False
    profile_ids: list[int] = Field(default_factory=list)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$|^$")

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, end: datetime, info: Any) -> datetime:
        start = info.data.get("start")
        if start and end < start:
            raise ValueError("end must be >= start")
        return end


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    location: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool | None = None
    profile_ids: list[int] | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$|^$")


class EventRead(BaseModel):
    id: int
    uid: str
    source: str
    calendar_id: str
    title: str
    description: str | None
    location: str | None
    start: datetime
    end: datetime
    all_day: bool
    profile_ids: list[int]
    color: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════════
# Setting DTOs
# ══════════════════════════════════════════════════════════════════════════════

class SettingRead(BaseModel):
    key: str
    value: Any
    updated_at: datetime

    model_config = {"from_attributes": True}


class SettingWrite(BaseModel):
    """Body for PUT /api/settings/{key}."""
    value: Any


# ══════════════════════════════════════════════════════════════════════════════
# CalendarSource DTOs
# ══════════════════════════════════════════════════════════════════════════════

class CalendarSourceRead(BaseModel):
    id: str
    kind: str
    label: str
    enabled: bool
    primary: bool
    status: str
    last_sync: datetime | None
    last_error: str | None

    model_config = {"from_attributes": True}


class CalendarSourceUpdate(BaseModel):
    enabled: bool | None = None
    primary: bool | None = None


class CalDAVCreate(BaseModel):
    """Body for POST /api/calendar/sources/caldav.

    URL validation rules (SSRF guard):
    - Scheme must be http or https.
    - Link-local addresses (169.254.0.0/16) are blocked — these are cloud
      metadata endpoints (AWS IMDSv1, GCP, Azure) that must never be reachable.
    - RFC 1918 private ranges (10.x, 172.16–31.x, 192.168.x) are explicitly
      ALLOWED: connecting to a family NAS running Nextcloud or Radicale on the
      local LAN is the primary CalDAV use case for this app.
    """
    url: str = Field(..., description="CalDAV principal or calendar URL (http/https)")
    username: str
    password: str
    label: str | None = None

    @field_validator("url")
    @classmethod
    def _validate_caldav_url(cls, v: str) -> str:
        import ipaddress
        import socket
        import urllib.parse

        parsed = urllib.parse.urlparse(v)

        # Scheme must be http or https.
        if parsed.scheme not in ("http", "https"):
            raise ValueError("CalDAV URL must use http or https scheme.")

        hostname = parsed.hostname
        if not hostname:
            raise ValueError("CalDAV URL must include a hostname.")

        # Resolve the hostname to an IP so we can inspect the address family.
        try:
            resolved = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
            ip_strings = {info[4][0] for info in resolved}
        except socket.gaierror:
            # DNS failure at validation time — allow it; the adapter will fail
            # at sync time with a clear connection error.
            return v

        for ip_str in ip_strings:
            try:
                addr = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            # Block link-local only: 169.254.0.0/16 (cloud metadata endpoints).
            # RFC 1918 private ranges are intentionally allowed for LAN CalDAV
            # servers (Nextcloud, Radicale on a family NAS).
            if addr in ipaddress.ip_network("169.254.0.0/16"):
                raise ValueError(
                    f"CalDAV URL resolves to a link-local address ({addr}), "
                    "which is not permitted."
                )

        return v


# ══════════════════════════════════════════════════════════════════════════════
# Plugin DTOs
# ══════════════════════════════════════════════════════════════════════════════

class PluginInfo(BaseModel):
    """Runtime info about a discovered plugin.  Serialised for GET /api/plugins."""
    name: str
    version: str
    description: str
    enabled: bool
    has_router: bool
    has_background_tasks: bool
    frontend_component: str | None
    settings_schema: dict[str, Any] | None

    model_config = {"from_attributes": True}


class PluginUpdate(BaseModel):
    enabled: bool


# ══════════════════════════════════════════════════════════════════════════════
# System DTOs
# ══════════════════════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    time: datetime = Field(default_factory=_now_utc)


class SyncStatusEntry(BaseModel):
    source: str
    status: str
    last_sync: datetime | None
    last_error: str | None


class SystemStatusResponse(BaseModel):
    sync: list[SyncStatusEntry]
    plugins: list[PluginInfo]
    websocket_clients: int


# ══════════════════════════════════════════════════════════════════════════════
# OAuth DTOs
# ══════════════════════════════════════════════════════════════════════════════

class OAuthAuthorizeResponse(BaseModel):
    url: str


class OAuthStatusResponse(BaseModel):
    connected: bool
    account: str | None = None


class OAuthCredentialsIn(BaseModel):
    """Client app credentials entered via the web GUI."""
    client_id: str
    client_secret: str
    tenant_id: str | None = None   # Microsoft only


class OAuthConfigResponse(BaseModel):
    """Non-secret view of a provider's OAuth app configuration for the UI."""
    provider: str
    configured: bool               # client id + secret are present (gui or env)
    source: str                    # "gui" | "env" | "none"
    redirect_uri: str              # the exact URI to register with the provider
    client_id_hint: str | None = None
    tenant_id: str | None = None


# ══════════════════════════════════════════════════════════════════════════════
# WebSocket envelope
# ══════════════════════════════════════════════════════════════════════════════

class WSEnvelope(BaseModel):
    """Server → client WebSocket message envelope."""
    type: str
    channel: str
    payload: Any
    ts: datetime = Field(default_factory=_now_utc)
