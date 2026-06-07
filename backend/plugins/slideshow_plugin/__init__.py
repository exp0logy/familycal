"""
slideshow_plugin — Google Photos slideshow plugin for Family Organiser.

Fetches media items from one or more Google Photos shared albums via the
Photos Library API, caches originals to DATA_DIR/photos/, and serves a list of
cached URLs + metadata via GET /api/plugins/slideshow/photos.

If Google Photos is unreachable the plugin serves the last cached list
gracefully — the frontend can always show previously downloaded photos.

Requires Google OAuth to be configured and a valid access token stored via
ctx.get_secret("oauth.google") (same token as the calendar plugin).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import anyio.to_thread
from fastapi import APIRouter

from app.plugins.base import Plugin, PluginContext, PluginManifest

logger = logging.getLogger(__name__)

# ── Manifest ──────────────────────────────────────────────────────────────────

_MANIFEST = PluginManifest(
    name="slideshow",
    version="1.0.0",
    description="Google Photos slideshow with local caching",
    frontend_component="PhotoSlideshow",
    settings_schema={
        "type": "object",
        "properties": {
            "album_ids": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Google Photos album IDs to display",
                "default": [],
            },
            "transition_speed_ms": {
                "type": "integer",
                "title": "Transition animation speed (ms)",
                "default": 1200,
                "minimum": 100,
            },
            "display_duration_ms": {
                "type": "integer",
                "title": "Time each photo is shown (ms)",
                "default": 8000,
                "minimum": 1000,
            },
            "refresh_interval_minutes": {
                "type": "integer",
                "title": "Album refresh interval (minutes)",
                "default": 60,
                "minimum": 5,
            },
        },
    },
    default_settings={
        "album_ids": [],
        "transition_speed_ms": 1200,
        "display_duration_ms": 8000,
        "refresh_interval_minutes": 60,
    },
)

# Base URL for Google Photos Library API v1.
_PHOTOS_API = "https://photoslibrary.googleapis.com/v1"


# ── Google Photos fetcher ─────────────────────────────────────────────────────

class GooglePhotosFetcher:
    """Fetches media items from the Google Photos Library API.

    Uses httpx (async).  A valid Google access token is required.
    """

    def __init__(self, access_token: str, http: Any) -> None:
        self._token = access_token
        self._http = http

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def list_albums(self) -> list[dict[str, Any]]:
        """Return a list of albums from the authenticated account."""
        albums: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"pageSize": 50}
            if page_token:
                params["pageToken"] = page_token

            resp = await self._http.get(
                f"{_PHOTOS_API}/albums",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            albums.extend(data.get("albums", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return albums

    async def list_media_items_in_album(
        self, album_id: str
    ) -> list[dict[str, Any]]:
        """Return all media items in the given album."""
        items: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            body: dict[str, Any] = {
                "albumId": album_id,
                "pageSize": 100,
            }
            if page_token:
                body["pageToken"] = page_token

            resp = await self._http.post(
                f"{_PHOTOS_API}/mediaItems:search",
                json=body,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("mediaItems", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return items

    async def download_item(
        self, base_url: str, max_width: int = 1920, max_height: int = 1080
    ) -> bytes:
        """Download a media item at the given base URL with size constraints."""
        download_url = f"{base_url}=w{max_width}-h{max_height}-no"
        resp = await self._http.get(download_url)
        resp.raise_for_status()
        return resp.content


# ── Cache management ──────────────────────────────────────────────────────────

def _safe_filename(item_id: str) -> str:
    """Produce a filesystem-safe filename from a Google Photos item ID."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", item_id)
    return safe[:200]  # limit length


def _load_manifest(photos_dir: Path) -> list[dict[str, Any]]:
    """Load the cached photo manifest from disk."""
    manifest_path = photos_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        return json.loads(manifest_path.read_text())
    except Exception:
        return []


def _save_manifest(photos_dir: Path, entries: list[dict[str, Any]]) -> None:
    """Persist the photo manifest to disk."""
    manifest_path = photos_dir / "manifest.json"
    photos_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(entries, indent=2))


# ── Plugin class ──────────────────────────────────────────────────────────────

class SlideshowPlugin(Plugin):
    """Google Photos slideshow plugin with local disk cache."""

    manifest = _MANIFEST

    def __init__(self) -> None:
        super().__init__()
        # In-memory list of cached photo metadata.
        self._photos: list[dict[str, Any]] = []
        self._last_error: str | None = None

    @property
    def has_background_tasks(self) -> bool:
        return True

    def register_router(self) -> APIRouter:
        return _build_router(self)

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)

        # Load any previously cached manifest from disk on startup.
        photos_dir = Path(ctx.data_dir) / "photos"
        cached = _load_manifest(photos_dir)
        if cached:
            self._photos = cached
            logger.debug("Loaded %d cached photos from disk.", len(cached))

        settings = await ctx.get_settings()
        interval_minutes = settings.get("refresh_interval_minutes", 60)

        async def _refresh() -> None:
            await self._refresh_photos(ctx)

        # Register via ctx.schedule() — auto-cancelled on stop() by the loader.
        # run_immediately only if album IDs are already configured.
        ctx.schedule(
            _refresh,
            interval_seconds=interval_minutes * 60,
            run_immediately=bool(settings.get("album_ids")),
        )

        logger.info("Slideshow plugin started.")

    async def stop(self) -> None:
        """Scheduled tasks are cancelled by the loader before this is called."""
        logger.info("Slideshow plugin stopped.")

    async def _refresh_photos(self, ctx: PluginContext) -> None:
        """Fetch new media items and cache them to disk."""
        settings = await ctx.get_settings()
        album_ids: list[str] = settings.get("album_ids", [])

        if not album_ids:
            logger.debug("Slideshow: no album IDs configured, skipping refresh.")
            return

        # Retrieve stored Google OAuth token, refreshing if near expiry.
        from app.core.oauth import GOOGLE_SECRET_KEY, maybe_refresh_google_token

        google_creds = await ctx.get_secret(GOOGLE_SECRET_KEY)

        if not google_creds or not google_creds.get("access_token"):
            logger.info("Slideshow: Google OAuth not configured, cannot refresh photos.")
            self._last_error = "Google OAuth not connected"
            return

        config = ctx.config
        if config.google_client_id and config.google_client_secret:
            await maybe_refresh_google_token(
                stored=google_creds,
                client_id=config.google_client_id,
                client_secret=config.google_client_secret,
                set_secret_fn=ctx.set_secret,
            )
            google_creds = await ctx.get_secret(GOOGLE_SECRET_KEY) or google_creds

        fetcher = GooglePhotosFetcher(
            access_token=google_creds["access_token"],
            http=ctx.http,
        )
        photos_dir = Path(ctx.data_dir) / "photos"
        photos_dir.mkdir(parents=True, exist_ok=True)

        new_entries: list[dict[str, Any]] = []

        for album_id in album_ids:
            try:
                items = await fetcher.list_media_items_in_album(album_id)
                logger.info("Slideshow: fetched %d items from album %s", len(items), album_id)

                for item in items:
                    entry = await self._cache_item(item, fetcher, photos_dir)
                    if entry:
                        new_entries.append(entry)

            except Exception as exc:
                logger.warning("Slideshow: failed to fetch album %r: %s", album_id, exc)
                self._last_error = str(exc)

        if new_entries:
            self._photos = new_entries
            self._last_error = None
            _save_manifest(photos_dir, new_entries)
            await ctx.broadcast("photos.updated", "photos", {"count": len(new_entries)})
            logger.info("Slideshow: cached %d photos.", len(new_entries))

    async def _cache_item(
        self,
        item: dict[str, Any],
        fetcher: GooglePhotosFetcher,
        photos_dir: Path,
    ) -> dict[str, Any] | None:
        """Download and cache a single media item if not already cached."""
        item_id = item.get("id", "")
        if not item_id:
            return None

        # Skip videos.
        media_metadata = item.get("mediaMetadata", {})
        if "video" in media_metadata:
            return None

        filename = _safe_filename(item_id) + ".jpg"
        dest = photos_dir / filename
        url_path = f"/photos/{filename}"

        if not dest.exists():
            try:
                base_url = item.get("baseUrl", "")
                if not base_url:
                    return None
                image_bytes = await fetcher.download_item(base_url)
                # Write file in a thread so we don't block the event loop.
                await anyio.to_thread.run_sync(dest.write_bytes, image_bytes)
                logger.debug("Cached photo: %s", filename)
            except Exception as exc:
                logger.warning("Slideshow: failed to download %s: %s", item_id, exc)
                return None

        # Parse creation time.
        creation_time = media_metadata.get("creationTime")
        caption = item.get("description") or item.get("filename", "")

        return {
            "id": item_id,
            "url": url_path,
            "date": creation_time,
            "caption": caption,
            "width": media_metadata.get("width"),
            "height": media_metadata.get("height"),
        }


def _build_router(plugin_ref: SlideshowPlugin) -> APIRouter:
    """Build the slideshow plugin's APIRouter."""
    router = APIRouter()

    @router.get("/photos")
    async def list_photos() -> list[dict[str, Any]]:
        """Return the list of cached photos with URL, date, and caption.

        Always returns cached data (even if Google is unreachable).
        Returns an empty list if no photos have been cached yet.
        """
        return plugin_ref._photos

    @router.get("/status")
    async def slideshow_status() -> dict[str, Any]:
        """Return plugin status and error info."""
        return {
            "photo_count": len(plugin_ref._photos),
            "last_error": plugin_ref._last_error,
            "status": "error" if plugin_ref._last_error else "ok",
        }

    return router


# Module-level plugin instance required by the loader.
plugin = SlideshowPlugin()
