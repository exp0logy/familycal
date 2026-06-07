"""
app/main.py — FastAPI application factory and lifespan.

Startup sequence:
  1. Create data directory and initialise the async SQLite database.
  2. Discover and load all plugins (backend/plugins/).
  3. Start the background task scheduler.
  4. Mount all API routers under /api.
  5. Start the /ws WebSocket endpoint.

Shutdown sequence:
  1. Stop the scheduler.
  2. Stop all plugins (gracefully).
  3. Close the database engine.

The app boots successfully with an empty .env — unconfigured features degrade
to "unconfigured" status; no exceptions are raised.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.websocket import manager

logger = logging.getLogger(__name__)

# ── Logging configuration ─────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Drive startup and shutdown of all long-lived resources."""
    settings = get_settings()

    # 1. Database
    from app.database import close_db, init_db
    await init_db()

    # 2. Plugin loader — needs a session factory from the live engine
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.scheduler import scheduler
    from app.database import get_engine
    from app.plugins.loader import PluginLoader

    engine = get_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Add the backend/plugins directory to sys.path so plugin packages are importable.
    plugins_dir = Path(__file__).parent.parent / "plugins"
    if str(plugins_dir) not in sys.path:
        sys.path.insert(0, str(plugins_dir))

    from app.plugins.base import capabilities as capability_registry

    loader = PluginLoader(
        app=app,
        settings=settings,
        session_factory=session_factory,
        broadcast_fn=manager.broadcast,
    )
    app.state.plugin_loader = loader
    app.state.scheduler = scheduler
    # Capability registry lets routers resolve plugin callables without
    # importing plugin packages directly (avoids hardcoding plugin names).
    app.state.capabilities = capability_registry

    await loader.load_all()

    # 3. Scheduler — plugins register their tasks during start(); start the
    #    scheduler after all plugins are loaded.
    await scheduler.start()

    logger.info("Family Organiser backend ready. Listening on %s:%s", settings.host, settings.port)

    yield  # ── app is running ───────────────────────────────────────────────

    # Shutdown
    logger.info("Shutting down…")
    await scheduler.stop()
    await loader.stop_all()
    await close_db()
    logger.info("Shutdown complete.")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        # Disable the default OpenAPI schema for production (optional).
        # docs_url=None, redoc_url=None,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    # allow_credentials=False: this app has no cookie/session auth.
    # Pairing allow_origins=["*"] with allow_credentials=True is rejected by
    # browsers and is an auth footgun — never enable both together.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global exception handler ─────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    # ── API routers ──────────────────────────────────────────────────────────
    from app.routers import (
        calendar,
        events,
        oauth,
        plugins,
        profiles,
        system,
    )
    from app.routers import (
        settings as settings_router,
    )

    api_prefix = "/api"
    app.include_router(profiles.router, prefix=api_prefix)
    app.include_router(events.router, prefix=api_prefix)
    app.include_router(settings_router.router, prefix=api_prefix)
    app.include_router(calendar.router, prefix=api_prefix)
    app.include_router(plugins.router, prefix=api_prefix)
    app.include_router(oauth.router, prefix=api_prefix)
    app.include_router(system.router, prefix=api_prefix)

    # ── Static files for cached photos ───────────────────────────────────────
    photos_dir = settings.data_dir / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/photos", StaticFiles(directory=str(photos_dir)), name="photos")

    # ── WebSocket endpoint ───────────────────────────────────────────────────
    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        try:
            await manager.handle(websocket)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.debug("WS endpoint error: %s", exc)
        finally:
            manager.disconnect(websocket)

    return app


# Module-level app instance used by uvicorn.
app = create_app()
