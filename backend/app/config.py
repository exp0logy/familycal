"""
app/config.py — Application configuration via pydantic-settings.

Reads environment variables and .env files. All config is available as a
Settings singleton (get_settings()). The app degrades gracefully when
optional keys (Google, Microsoft, etc.) are absent — plugins detect the
missing values and report "unconfigured" status rather than crashing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object.  All fields have defaults so the app
    boots successfully with an empty .env (features degrade to unconfigured).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore unknown env vars
    )

    # ── Core ────────────────────────────────────────────────────────────────
    app_name: str = "Family Organiser"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"
    data_dir: Path = Path("./data")

    # Fernet key for encrypting secrets at rest.
    # If absent, encryption is disabled and a warning is logged on startup.
    secret_key: str | None = None

    # Public base URL the browser uses to reach the backend (for OAuth redirect URIs).
    public_base_url: str = "http://localhost:8000"

    # ── Background sync ─────────────────────────────────────────────────────
    calendar_sync_interval_minutes: int = 15

    # ── Google ──────────────────────────────────────────────────────────────
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # ── Microsoft / Outlook ─────────────────────────────────────────────────
    ms_client_id: str | None = None
    ms_client_secret: str | None = None
    ms_tenant_id: str = "common"

    # ── Weather (Open-Meteo — no API key required) ──────────────────────────
    weather_latitude: float = -37.8136
    weather_longitude: float = 144.9631
    weather_location_label: str = "Melbourne"
    weather_units: str = "metric"

    # ── Derived helpers ─────────────────────────────────────────────────────
    @property
    def db_url(self) -> str:
        """Async SQLite URL for SQLAlchemy."""
        db_path = self.data_dir / "familycal.db"
        return f"sqlite+aiosqlite:///{db_path}"

    @property
    def cors_origins_list(self) -> list[str]:
        """Split the comma-separated CORS_ORIGINS into a list."""
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("data_dir", mode="before")
    @classmethod
    def _resolve_data_dir(cls, v: object) -> Path:
        return Path(str(v))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton.  Call get_settings.cache_clear()
    in tests to force a fresh read."""
    return Settings()
