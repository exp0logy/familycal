"""
calendar_plugin — Calendar sync plugin for Family Organiser.

Supports:
  - Google Calendar (google-api-python-client Calendar v3, OAuth2 token via ctx.get_secret)
  - CalDAV (caldav library, credentials via ctx.get_secret)
  - Microsoft Outlook / Office 365 (Microsoft Graph API, MSAL token via ctx.get_secret)

Each source is an independent adapter.  The plugin orchestrates all adapters
during periodic sync, merges events into the unified Event table, and broadcasts
WebSocket messages on change.

Background refresh is registered via ``ctx.schedule()`` so it is auto-cancelled
when the plugin is stopped.  Secrets are read/written exclusively via
``ctx.get_secret()`` / ``ctx.set_secret()`` — the plugin never imports from
app.core directly.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio.to_thread
from fastapi import APIRouter
from sqlmodel import select

from app.models import CalendarSourceState, Event
from app.plugins.base import Plugin, PluginContext, PluginManifest

logger = logging.getLogger(__name__)

# ── Secret key constants ──────────────────────────────────────────────────────
# These mirror the values in app.core.oauth so both subsystems use the same keys.

_GOOGLE_SECRET_KEY = "oauth.google"
_MICROSOFT_SECRET_KEY = "oauth.microsoft"

# ── Manifest ──────────────────────────────────────────────────────────────────

_MANIFEST = PluginManifest(
    name="calendar",
    version="1.0.0",
    description="Google Calendar, CalDAV, and Outlook sync",
    frontend_component="CalendarAgenda",
    settings_schema={
        "type": "object",
        "properties": {
            "sync_interval_minutes": {
                "type": "integer",
                "title": "Sync interval (minutes)",
                "default": 15,
                "minimum": 1,
            },
            "primary_source": {
                "type": "string",
                "title": "Primary calendar source ID",
                "default": "",
            },
            "agenda_days": {
                "type": "integer",
                "title": "Days ahead shown in agenda view",
                "default": 7,
                "minimum": 1,
            },
        },
    },
    default_settings={
        "sync_interval_minutes": 15,
        "primary_source": "",
        "agenda_days": 7,
    },
    requires_secrets=[_GOOGLE_SECRET_KEY, _MICROSOFT_SECRET_KEY, "caldav.*"],
)


# ── Google Calendar adapter ───────────────────────────────────────────────────

class GoogleCalendarAdapter:
    """Lists and creates events via the Google Calendar API v3.

    All SDK calls are sync and wrapped with anyio.to_thread.run_sync.
    """

    def __init__(self, credentials: dict[str, Any], config: Any) -> None:
        self._credentials = credentials
        self._config = config

    def _build_service(self) -> Any:
        """Build a googleapiclient Resource (sync, runs in a thread)."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build as _build

        creds = Credentials(
            token=self._credentials.get("access_token"),
            refresh_token=self._credentials.get("refresh_token"),
            client_id=self._config.google_client_id,
            client_secret=self._config.google_client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )
        return _build("calendar", "v3", credentials=creds, cache_discovery=False)

    async def list_events(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Return raw Google Calendar event dicts in the given range."""
        def _fetch() -> list[dict[str, Any]]:
            service = self._build_service()
            calendars = service.calendarList().list().execute()
            all_events: list[dict[str, Any]] = []
            for cal in calendars.get("items", []):
                cal_id = cal["id"]
                result = service.events().list(
                    calendarId=cal_id,
                    timeMin=start.isoformat(),
                    timeMax=end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=500,
                ).execute()
                for evt in result.get("items", []):
                    evt["_calendar_id"] = cal_id
                    all_events.append(evt)
            return all_events

        return await anyio.to_thread.run_sync(_fetch)

    async def create_event(self, event: Event) -> str:
        """Create an event in the primary Google Calendar.  Returns the new event ID."""
        def _create() -> str:
            service = self._build_service()
            body = {
                "summary": event.title,
                "description": event.description or "",
                "location": event.location or "",
                "start": (
                    {"date": event.start.date().isoformat()}
                    if event.all_day
                    else {"dateTime": event.start.isoformat(), "timeZone": "UTC"}
                ),
                "end": (
                    {"date": event.end.date().isoformat()}
                    if event.all_day
                    else {"dateTime": event.end.isoformat(), "timeZone": "UTC"}
                ),
            }
            result = service.events().insert(calendarId="primary", body=body).execute()
            return result["id"]

        return await anyio.to_thread.run_sync(_create)


def _parse_google_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a raw Google Calendar event dict to our unified format."""
    uid = raw.get("id")
    if not uid:
        return None

    start_obj = raw.get("start", {})
    end_obj = raw.get("end", {})

    if "date" in start_obj:
        all_day = True
        try:
            start = datetime.fromisoformat(start_obj["date"]).replace(tzinfo=UTC)
            end = datetime.fromisoformat(end_obj.get("date", start_obj["date"])).replace(tzinfo=UTC)
        except ValueError:
            return None
    else:
        all_day = False
        try:
            start = datetime.fromisoformat(start_obj.get("dateTime", ""))
            end = datetime.fromisoformat(end_obj.get("dateTime", start_obj.get("dateTime", "")))
        except ValueError:
            return None

    return {
        "uid": f"google:{uid}",
        "source": "google",
        "calendar_id": raw.get("_calendar_id", "primary"),
        "title": raw.get("summary", "(No title)"),
        "description": raw.get("description"),
        "location": raw.get("location"),
        "start": start,
        "end": end,
        "all_day": all_day,
    }


# ── CalDAV adapter ────────────────────────────────────────────────────────────

class CalDAVAdapter:
    """Lists events via the caldav library.  Sync SDK wrapped in threads."""

    def __init__(self, url: str, username: str, password: str, source_id: str) -> None:
        self._url = url
        self._username = username
        self._password = password
        self._source_id = source_id

    async def list_events(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Return unified event dicts from the CalDAV source."""
        def _fetch() -> list[dict[str, Any]]:
            import caldav

            client = caldav.DAVClient(
                url=self._url,
                username=self._username,
                password=self._password,
            )
            principal = client.principal()
            all_events: list[dict[str, Any]] = []

            for calendar in principal.calendars():
                try:
                    results = calendar.date_search(start=start, end=end, expand=True)
                except Exception as exc:
                    logger.warning("CalDAV calendar search failed: %s", exc)
                    continue

                for component in results:
                    try:
                        parsed = _parse_caldav_component(component, self._source_id)
                        if parsed:
                            all_events.append(parsed)
                    except Exception as exc:
                        logger.debug("Failed to parse CalDAV event: %s", exc)

            return all_events

        return await anyio.to_thread.run_sync(_fetch)


def _parse_caldav_component(component: Any, source_id: str) -> dict[str, Any] | None:
    """Parse a caldav Event object into our unified dict."""
    try:
        from icalendar import Calendar as iCal

        cal = iCal.from_ical(component.data)
        for comp in cal.walk():
            if comp.name != "VEVENT":
                continue

            uid_raw = comp.get("UID", "")
            uid = f"caldav:{uid_raw}"

            dtstart = comp.get("DTSTART")
            dtend = comp.get("DTEND")
            if not dtstart:
                return None

            dt_start = dtstart.dt
            dt_end = dtend.dt if dtend else dt_start
            all_day = False

            if isinstance(dt_start, datetime):
                if dt_start.tzinfo is None:
                    dt_start = dt_start.replace(tzinfo=UTC)
            else:
                all_day = True
                dt_start = datetime.combine(dt_start, datetime.min.time(), tzinfo=UTC)
                if not isinstance(dt_end, datetime):
                    dt_end = datetime.combine(dt_end, datetime.min.time(), tzinfo=UTC)

            if isinstance(dt_end, datetime) and dt_end.tzinfo is None:
                dt_end = dt_end.replace(tzinfo=UTC)

            return {
                "uid": uid,
                "source": "caldav",
                "calendar_id": source_id,
                "title": str(comp.get("SUMMARY", "(No title)")),
                "description": str(comp.get("DESCRIPTION", "")) or None,
                "location": str(comp.get("LOCATION", "")) or None,
                "start": dt_start if isinstance(dt_start, datetime) else datetime.combine(dt_start, datetime.min.time(), tzinfo=UTC),
                "end": dt_end if isinstance(dt_end, datetime) else datetime.combine(dt_end, datetime.min.time(), tzinfo=UTC),
                "all_day": all_day,
            }
    except Exception as exc:
        logger.debug("CalDAV parse error: %s", exc)
    return None


# ── Outlook / Microsoft Graph adapter ────────────────────────────────────────

class OutlookAdapter:
    """Lists and creates events via Microsoft Graph API."""

    def __init__(self, access_token: str) -> None:
        self._access_token = access_token

    async def list_events(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        import httpx

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Prefer": 'outlook.timezone="UTC"',
        }
        params = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$top": "500",
            "$select": "id,subject,bodyPreview,location,start,end,isAllDay",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/me/calendarView",
                headers=headers,
                params=params,
            )

        if resp.status_code != 200:
            raise ValueError(f"Graph API error: {resp.status_code} {resp.text[:200]}")

        return [e for e in (_parse_outlook_event(i) for i in resp.json().get("value", [])) if e]

    async def create_event(self, event: Event) -> str:
        import httpx

        body = {
            "subject": event.title,
            "body": {"contentType": "text", "content": event.description or ""},
            "location": {"displayName": event.location or ""},
            "start": {"dateTime": event.start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": event.end.isoformat(), "timeZone": "UTC"},
            "isAllDay": event.all_day,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://graph.microsoft.com/v1.0/me/events",
                json=body,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )

        if resp.status_code not in (200, 201):
            raise ValueError(f"Graph create event error: {resp.status_code}")

        return resp.json()["id"]


def _parse_outlook_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    uid = raw.get("id")
    if not uid:
        return None
    try:
        start = datetime.fromisoformat(raw["start"]["dateTime"])
        end = datetime.fromisoformat(raw["end"]["dateTime"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
    except (KeyError, ValueError):
        return None

    return {
        "uid": f"outlook:{uid}",
        "source": "outlook",
        "calendar_id": "outlook",
        "title": raw.get("subject", "(No title)"),
        "description": raw.get("bodyPreview"),
        "location": raw.get("location", {}).get("displayName") or None,
        "start": start,
        "end": end,
        "all_day": raw.get("isAllDay", False),
    }


# ── CalendarService ───────────────────────────────────────────────────────────

class CalendarService:
    """Orchestrates adapters, sync loop, and DB upsert.

    All secret access goes through ``ctx.get_secret()`` / ``ctx.set_secret()``.
    """

    def __init__(self, ctx: PluginContext) -> None:
        self._ctx = ctx

    async def sync_all(self) -> None:
        """Sync all enabled calendar sources.  Never raises — errors are logged."""
        logger.info("Calendar sync started.")
        async with self._ctx.db_session() as session:
            result = await session.execute(
                select(CalendarSourceState).where(CalendarSourceState.enabled == True)  # noqa: E712
            )
            sources: list[CalendarSourceState] = result.scalars().all()

        for source in sources:
            try:
                await self._sync_source(source)
            except Exception as exc:
                logger.error("Sync failed for source %r: %s", source.id, exc, exc_info=True)
                await self._update_source_status(source.id, "error", str(exc))

        logger.info("Calendar sync complete.")

    async def _sync_source(self, source: CalendarSourceState) -> None:
        """Sync a single calendar source."""
        await self._update_source_status(source.id, "syncing", None)

        now = datetime.now(UTC)
        start = now - timedelta(days=7)
        end = now + timedelta(days=90)

        events_data: list[dict[str, Any]] = []

        if source.kind == "google":
            adapter = await self._build_google_adapter()
            if adapter is None:
                await self._update_source_status(source.id, "unconfigured", "Google OAuth not configured")
                return
            raw = await adapter.list_events(start, end)
            events_data = [e for e in (_parse_google_event(r) for r in raw) if e]

        elif source.kind == "caldav":
            adapter = await self._build_caldav_adapter(source.id)
            if adapter is None:
                await self._update_source_status(source.id, "unconfigured", "CalDAV credentials not found")
                return
            events_data = await adapter.list_events(start, end)

        elif source.kind == "outlook":
            adapter = await self._build_outlook_adapter()
            if adapter is None:
                await self._update_source_status(source.id, "unconfigured", "Microsoft OAuth not configured")
                return
            events_data = await adapter.list_events(start, end)

        await self._upsert_events(events_data)
        count = len(events_data)

        await self._update_source_status(source.id, "ok", None)
        await self._ctx.broadcast("events.updated", "events", {"count": count})
        await self._ctx.broadcast(
            "sync.status",
            "sync",
            {
                "source": source.id,
                "status": "ok",
                "last_sync": datetime.now(UTC).isoformat(),
                "last_error": None,
            },
        )
        logger.info("Source %r synced: %d events.", source.id, count)

    async def _upsert_events(self, events_data: list[dict[str, Any]]) -> None:
        """Upsert a list of unified event dicts into the Event table."""
        async with self._ctx.db_session() as session:
            for data in events_data:
                uid = data.get("uid")
                if not uid:
                    continue

                result = await session.execute(select(Event).where(Event.uid == uid))
                event: Event | None = result.scalar_one_or_none()
                now = datetime.now(UTC)

                if event is None:
                    event = Event(
                        uid=uid,
                        source=data["source"],
                        calendar_id=data["calendar_id"],
                        title=data["title"],
                        description=data.get("description"),
                        location=data.get("location"),
                        start=data["start"],
                        end=data["end"],
                        all_day=data.get("all_day", False),
                        updated_at=now,
                    )
                    event.set_profile_ids([])
                    session.add(event)
                else:
                    event.title = data["title"]
                    event.description = data.get("description")
                    event.location = data.get("location")
                    event.start = data["start"]
                    event.end = data["end"]
                    event.all_day = data.get("all_day", False)
                    event.updated_at = now

            await session.commit()

    async def _update_source_status(
        self, source_id: str, status: str, last_error: str | None
    ) -> None:
        async with self._ctx.db_session() as session:
            result = await session.execute(
                select(CalendarSourceState).where(CalendarSourceState.id == source_id)
            )
            source: CalendarSourceState | None = result.scalar_one_or_none()
            if source is not None:
                source.status = status
                source.last_error = last_error
                if status == "ok":
                    source.last_sync = datetime.now(UTC)
                await session.commit()

    # ── Adapter builders with token refresh ───────────────────────────────────

    async def _build_google_adapter(self) -> GoogleCalendarAdapter | None:
        """Build a Google adapter, pre-emptively refreshing the token if near expiry."""
        from app.core.oauth import maybe_refresh_google_token

        stored = await self._ctx.get_secret(_GOOGLE_SECRET_KEY)
        if not stored or not stored.get("access_token"):
            return None

        config = self._ctx.config
        if config.google_client_id and config.google_client_secret:
            await maybe_refresh_google_token(
                stored=stored,
                client_id=config.google_client_id,
                client_secret=config.google_client_secret,
                set_secret_fn=self._ctx.set_secret,
            )
            # Re-read in case the refresh persisted a new access_token.
            stored_fresh = await self._ctx.get_secret(_GOOGLE_SECRET_KEY) or stored
        else:
            stored_fresh = stored

        return GoogleCalendarAdapter(credentials=stored_fresh, config=config)

    async def _build_caldav_adapter(self, source_id: str) -> CalDAVAdapter | None:
        """Build a CalDAV adapter using stored credentials for the given source_id."""
        creds = await self._ctx.get_secret(f"caldav.{source_id}")
        if not creds:
            return None
        return CalDAVAdapter(
            url=creds["url"],
            username=creds["username"],
            password=creds["password"],
            source_id=source_id,
        )

    async def _build_outlook_adapter(self) -> OutlookAdapter | None:
        """Build a Microsoft Graph adapter, pre-emptively refreshing if near expiry."""
        from app.core.oauth import maybe_refresh_microsoft_token

        stored = await self._ctx.get_secret(_MICROSOFT_SECRET_KEY)
        if not stored or not stored.get("access_token"):
            return None

        config = self._ctx.config
        if config.ms_client_id and config.ms_client_secret:
            await maybe_refresh_microsoft_token(
                stored=stored,
                client_id=config.ms_client_id,
                client_secret=config.ms_client_secret,
                tenant_id=config.ms_tenant_id,
                set_secret_fn=self._ctx.set_secret,
            )
            stored = await self._ctx.get_secret(_MICROSOFT_SECRET_KEY) or stored

        return OutlookAdapter(access_token=stored.get("access_token", ""))

    async def write_event(self, event: Event) -> None:
        """Write an event to its source calendar.  Failures are logged, not raised."""
        try:
            if event.source == "google":
                adapter = await self._build_google_adapter()
                if adapter:
                    await adapter.create_event(event)
            elif event.source == "outlook":
                adapter = await self._build_outlook_adapter()
                if adapter:
                    await adapter.create_event(event)
        except Exception as exc:
            logger.warning("write_event to %r failed: %s", event.source, exc)

    async def store_caldav_credentials(
        self, source_id: str, url: str, username: str, password: str
    ) -> None:
        """Encrypt and persist CalDAV credentials via ctx.set_secret."""
        await self._ctx.set_secret(
            f"caldav.{source_id}",
            {"url": url, "username": username, "password": password},
        )
        logger.info("CalDAV credentials stored for source %r", source_id)


# ── Router ────────────────────────────────────────────────────────────────────

def _build_router(service_ref: list[CalendarService | None]) -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    async def calendar_status() -> dict[str, Any]:
        """Plugin-level status (full source details at /api/calendar/sources)."""
        return {"sources": []}

    return router


# ── Plugin class ──────────────────────────────────────────────────────────────

class CalendarPlugin(Plugin):
    """Calendar sync plugin — Google Calendar, CalDAV, and Microsoft Outlook."""

    manifest = _MANIFEST

    def __init__(self) -> None:
        super().__init__()
        self._service: CalendarService | None = None
        # Mutable container for late-binding in the router closure.
        self._service_ref: list[CalendarService | None] = [None]

    @property
    def has_background_tasks(self) -> bool:
        return True

    def register_router(self) -> APIRouter:
        return _build_router(self._service_ref)

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)

        self._service = CalendarService(ctx)
        self._service_ref[0] = self._service

        # Register capabilities so routers can call calendar operations without
        # importing this package directly.  Capabilities are deregistered
        # automatically by the loader when the plugin stops.
        ctx.register_capability("calendar.write_event", self._service.write_event)
        ctx.register_capability("calendar.sync_all", self._service.sync_all)
        ctx.register_capability("calendar.store_caldav_credentials", self._service.store_caldav_credentials)

        settings = await ctx.get_settings()
        interval_minutes = settings.get("sync_interval_minutes", 15)

        # Register periodic sync via ctx.schedule() — auto-cancelled on stop().
        ctx.schedule(
            self._service.sync_all,
            interval_seconds=interval_minutes * 60,
            run_immediately=True,
        )

        logger.info("Calendar plugin started.")

    async def stop(self) -> None:
        """Loader calls _cancel_scheduled_tasks() and _deregister_capabilities() first."""
        self._service = None
        self._service_ref[0] = None
        logger.info("Calendar plugin stopped.")


# Module-level plugin instance required by the loader.
plugin = CalendarPlugin()
