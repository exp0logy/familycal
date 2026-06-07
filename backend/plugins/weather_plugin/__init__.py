"""
weather_plugin — Weather plugin for Family Organiser.

Fetches current conditions and a 4-day forecast from Open-Meteo (free, no API
key required) via httpx.  Data is cached in memory and refreshed every 10
minutes.  The full snapshot is broadcast over the WebSocket on each refresh.

Response shape (GET /api/plugins/weather/current and weather.updated WS payload)::

    {
        "current": {
            "temp": float,               # °C or °F — primary temperature alias
            "temperature": float,        # same value; kept for compatibility
            "feels_like": float,
            "humidity": int,             # %
            "precipitation": float,
            "wind_speed": float,
            "wind_direction": int,       # degrees
            "is_day": bool,
            "weather_code": int,         # WMO code
            "weather_label": str,
            "weather_icon": str,
            "units": str,                # "metric" | "imperial"
            "temperature_unit": str,     # "°C" | "°F"
        },
        "daily": [                       # 4 entries: today + 3 days
            {
                "date": str,             # "YYYY-MM-DD"
                "temp_max": float,
                "temp_min": float,
                "precipitation": float,
                "weather_code": int,
                "weather_label": str,
                "weather_icon": str,
                "sunrise": str,
                "sunset": str,
            },
            ...
        ],
        "location": str,
        "fetched_at": iso,
    }

WMO weather-code interpretation follows the Open-Meteo documentation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.plugins.base import Plugin, PluginContext, PluginManifest

logger = logging.getLogger(__name__)

# ── WMO weather code → label/icon mapping ────────────────────────────────────

WMO_CODES: dict[int, dict[str, str]] = {
    0:  {"label": "Clear sky",              "icon": "sun"},
    1:  {"label": "Mainly clear",           "icon": "sun"},
    2:  {"label": "Partly cloudy",          "icon": "cloud-sun"},
    3:  {"label": "Overcast",               "icon": "cloud"},
    45: {"label": "Fog",                    "icon": "smog"},
    48: {"label": "Depositing rime fog",    "icon": "smog"},
    51: {"label": "Light drizzle",          "icon": "cloud-drizzle"},
    53: {"label": "Moderate drizzle",       "icon": "cloud-drizzle"},
    55: {"label": "Dense drizzle",          "icon": "cloud-drizzle"},
    56: {"label": "Freezing light drizzle", "icon": "cloud-drizzle"},
    57: {"label": "Freezing dense drizzle", "icon": "cloud-drizzle"},
    61: {"label": "Slight rain",            "icon": "cloud-rain"},
    63: {"label": "Moderate rain",          "icon": "cloud-rain"},
    65: {"label": "Heavy rain",             "icon": "cloud-showers-heavy"},
    66: {"label": "Freezing light rain",    "icon": "cloud-rain"},
    67: {"label": "Freezing heavy rain",    "icon": "cloud-showers-heavy"},
    71: {"label": "Slight snow",            "icon": "snowflake"},
    73: {"label": "Moderate snow",          "icon": "snowflake"},
    75: {"label": "Heavy snow",             "icon": "snowflake"},
    77: {"label": "Snow grains",            "icon": "snowflake"},
    80: {"label": "Slight rain showers",    "icon": "cloud-sun-rain"},
    81: {"label": "Moderate rain showers",  "icon": "cloud-rain"},
    82: {"label": "Violent rain showers",   "icon": "cloud-showers-heavy"},
    85: {"label": "Slight snow showers",    "icon": "snowflake"},
    86: {"label": "Heavy snow showers",     "icon": "snowflake"},
    95: {"label": "Thunderstorm",           "icon": "bolt"},
    96: {"label": "Thunderstorm w/ hail",   "icon": "bolt"},
    99: {"label": "Thunderstorm w/ heavy hail", "icon": "bolt"},
}


def _wmo_info(code: int) -> dict[str, str]:
    return WMO_CODES.get(code, {"label": "Unknown", "icon": "question"})


# ── Manifest ──────────────────────────────────────────────────────────────────

_MANIFEST = PluginManifest(
    name="weather",
    version="1.0.0",
    description="Current conditions and 4-day forecast via Open-Meteo",
    frontend_component="WeatherWidget",
    settings_schema={
        "type": "object",
        "properties": {
            "latitude":       {"type": "number",  "title": "Latitude",        "default": -37.8136},
            "longitude":      {"type": "number",  "title": "Longitude",       "default": 144.9631},
            "location_label": {"type": "string",  "title": "Location label",  "default": "Melbourne"},
            "units":          {"type": "string",  "title": "Units (metric/imperial)", "default": "metric"},
            "refresh_interval_minutes": {"type": "integer", "title": "Refresh interval (minutes)", "default": 10, "minimum": 1},
        },
    },
    default_settings={
        "latitude": -37.8136,
        "longitude": 144.9631,
        "location_label": "Melbourne",
        "units": "metric",
        "refresh_interval_minutes": 10,
    },
)


# ── Fetch logic ───────────────────────────────────────────────────────────────

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
# Free geocoding API (no key) — turns a town name into coordinates.
OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Variables to request.
_HOURLY_VARS = []
_DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "weathercode",
    "sunrise",
    "sunset",
]
_CURRENT_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "is_day",
    "precipitation",
    "weathercode",
    "wind_speed_10m",
    "wind_direction_10m",
]


async def fetch_weather(
    latitude: float,
    longitude: float,
    units: str,
    http: Any,
) -> dict[str, Any]:
    """Fetch weather data from Open-Meteo and return a structured snapshot."""
    temperature_unit = "celsius" if units == "metric" else "fahrenheit"
    wind_speed_unit = "kmh" if units == "metric" else "mph"

    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(_CURRENT_VARS),
        "daily": ",".join(_DAILY_VARS),
        "timezone": "auto",
        "forecast_days": 4,
        "temperature_unit": temperature_unit,
        "wind_speed_unit": wind_speed_unit,
    }

    response = await http.get(OPEN_METEO_URL, params=params)
    response.raise_for_status()
    raw = response.json()

    return _parse_weather_response(raw, units)


def _parse_weather_response(raw: dict[str, Any], units: str) -> dict[str, Any]:
    """Convert Open-Meteo API response to the locked snapshot shape.

    Top-level keys: ``current``, ``daily`` (4 entries), ``location``,
    ``fetched_at``.  The ``current`` object exposes both ``temp`` (the
    primary field the frontend reads) and ``temperature`` (kept for
    compatibility with any other consumers).
    """
    current_raw = raw.get("current", {})
    current_units = raw.get("current_units", {})
    daily_raw = raw.get("daily", {})

    wmo_code = int(current_raw.get("weathercode", 0) or 0)
    wmo = _wmo_info(wmo_code)
    temperature = current_raw.get("temperature_2m")

    current = {
        # ``temp`` is the primary field consumed by WeatherWidget.
        "temp": temperature,
        # ``temperature`` kept as a compatibility alias.
        "temperature": temperature,
        "feels_like": current_raw.get("apparent_temperature"),
        "humidity": current_raw.get("relative_humidity_2m"),
        "precipitation": current_raw.get("precipitation"),
        "wind_speed": current_raw.get("wind_speed_10m"),
        "wind_direction": current_raw.get("wind_direction_10m"),
        "is_day": bool(current_raw.get("is_day", 1)),
        "weather_code": wmo_code,
        "weather_label": wmo["label"],
        "weather_icon": wmo["icon"],
        "units": units,
        "temperature_unit": current_units.get("temperature_2m", "°C"),
    }

    # Build the 4-day daily array (today + 3 ahead).
    times = daily_raw.get("time", [])
    max_temps = daily_raw.get("temperature_2m_max", [])
    min_temps = daily_raw.get("temperature_2m_min", [])
    precip_sums = daily_raw.get("precipitation_sum", [])
    codes = daily_raw.get("weathercode", [])
    sunrises = daily_raw.get("sunrise", [])
    sunsets = daily_raw.get("sunset", [])

    daily: list[dict[str, Any]] = []
    for i in range(min(4, len(times))):
        code = int(codes[i] if i < len(codes) else 0)
        info = _wmo_info(code)
        daily.append({
            "date": times[i],
            "temp_max": max_temps[i] if i < len(max_temps) else None,
            "temp_min": min_temps[i] if i < len(min_temps) else None,
            "precipitation": precip_sums[i] if i < len(precip_sums) else None,
            "weather_code": code,
            "weather_label": info["label"],
            "weather_icon": info["icon"],
            "sunrise": sunrises[i] if i < len(sunrises) else None,
            "sunset": sunsets[i] if i < len(sunsets) else None,
        })

    return {
        "current": current,
        "daily": daily,           # top-level key is "daily", not "forecast"
        "fetched_at": datetime.now(UTC).isoformat(),
        # "location" is injected by _refresh_weather after this call
    }


# ── Plugin class ──────────────────────────────────────────────────────────────

class WeatherPlugin(Plugin):
    """Weather widget plugin using Open-Meteo (no API key required)."""

    manifest = _MANIFEST

    def __init__(self) -> None:
        super().__init__()
        # In-memory cache of the most recent weather snapshot.
        self._cache: dict[str, Any] | None = None
        self._last_error: str | None = None

    @property
    def has_background_tasks(self) -> bool:
        return True

    def register_router(self) -> APIRouter:
        return _build_router(self)

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)

        settings = await ctx.get_settings()
        interval_minutes = settings.get("refresh_interval_minutes", 10)

        async def _refresh() -> None:
            await self._refresh_weather(ctx)

        # Register via ctx.schedule() — auto-cancelled on stop() by the loader.
        ctx.schedule(
            _refresh,
            interval_seconds=interval_minutes * 60,
            run_immediately=True,
        )

        logger.info("Weather plugin started.")

    async def stop(self) -> None:
        """Scheduled tasks are cancelled by the loader before this is called."""
        logger.info("Weather plugin stopped.")

    async def _refresh_weather(self, ctx: PluginContext) -> None:
        """Fetch fresh weather data and broadcast the snapshot."""
        settings = await ctx.get_settings()
        lat = settings.get("latitude", ctx.config.weather_latitude)
        lon = settings.get("longitude", ctx.config.weather_longitude)
        units = settings.get("units", ctx.config.weather_units)

        try:
            snapshot = await fetch_weather(lat, lon, units, ctx.http)
            snapshot["location"] = settings.get("location_label", ctx.config.weather_location_label)
            self._cache = snapshot
            self._last_error = None
            await ctx.broadcast("weather.updated", "weather", snapshot)
            logger.debug("Weather refreshed for %s.", snapshot.get("location"))
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Weather fetch failed: %s", exc)
            # Serve stale cache if available; do not clear it on error.


def _build_router(plugin_ref: WeatherPlugin) -> APIRouter:
    """Build the plugin's APIRouter with access to the plugin instance."""
    router = APIRouter()

    @router.get("/current")
    async def get_current_weather() -> dict[str, Any]:
        """Return the most recently fetched weather snapshot.

        If no data is available yet (e.g. initial fetch in progress), returns
        an empty dict with a status field so the frontend can show a spinner.
        """
        if plugin_ref._cache is None:
            return {
                "status": "loading" if plugin_ref._last_error is None else "error",
                "error": plugin_ref._last_error,
            }
        return plugin_ref._cache

    @router.get("/geocode")
    async def geocode(
        q: str = Query(..., min_length=1, description="Town / place name to look up"),
    ) -> dict[str, Any]:
        """Resolve a place name to coordinates via Open-Meteo's geocoding API.

        Lets the Settings UI autofill latitude/longitude from a town name, so no
        one has to type signed decimal coordinates on a touchscreen.
        """
        ctx = plugin_ref._ctx
        if ctx is None:
            raise HTTPException(status_code=503, detail="Weather plugin not ready")
        try:
            resp = await ctx.http.get(
                OPEN_METEO_GEOCODE_URL,
                params={"name": q, "count": 5, "language": "en", "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Geocoding failed: {exc}") from exc

        results = []
        for r in data.get("results") or []:
            label = ", ".join(
                p for p in (r.get("name"), r.get("admin1"), r.get("country")) if p
            )
            results.append({
                "label": label,
                "name": r.get("name"),
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "country": r.get("country"),
                "admin1": r.get("admin1"),
                "timezone": r.get("timezone"),
            })
        return {"results": results}

    return router


# Module-level plugin instance required by the loader.
plugin = WeatherPlugin()
