"""
app/plugins/loader.py — Plugin discovery, loading, and lifecycle management.

Scans ``backend/plugins/`` for packages, imports each, reads the enabled flag
from the DB (``PluginConfig``), mounts any routers onto the FastAPI app, and
drives the plugin lifecycle (start / stop) during app startup / shutdown and
when plugins are toggled at runtime.

Plugin package layout::

    backend/plugins/<pkg>/
        __init__.py        # must expose `plugin = SomePlugin()` OR
                           #              `def get_plugin(ctx): ...`

The loader never special-cases any plugin by name.  All knowledge of a plugin
comes from its ``PluginManifest``.
"""

from __future__ import annotations

import importlib
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.plugins.base import Plugin, PluginContext, capabilities
from app.plugins.registry import registry

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.config import Settings

logger = logging.getLogger(__name__)

# Directory that contains built-in plugin packages.
_PLUGINS_ROOT = Path(__file__).parent.parent.parent / "plugins"


def _make_plugin_guard(plugin_name: str, disabled_set: set) -> Any:
    """Return a FastAPI dependency that returns 404 when the plugin is disabled.

    Defined at module level so FastAPI's dependency injection resolves the
    ``Request`` annotation correctly (local aliases are not recognised).
    """
    async def _guard(request: Request) -> None:  # noqa: ARG001
        if plugin_name in disabled_set:
            raise HTTPException(
                status_code=404,
                detail=f"Plugin {plugin_name!r} is disabled",
            )
    return _guard


class PluginLoader:
    """Discovers and manages the full lifecycle of all plugins.

    An instance of this class is created by the app factory (``main.py``)
    during startup and holds shared state (shared httpx client, session
    factory, etc.) needed to build ``PluginContext`` objects.
    """

    def __init__(
        self,
        app: FastAPI,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        broadcast_fn: Any,   # ConnectionManager.broadcast
    ) -> None:
        self._app = app
        self._settings = settings
        self._session_factory = session_factory
        self._broadcast_fn = broadcast_fn

        # Shared HTTP client — all plugins reuse the same connection pool.
        self._http = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "FamilyCal/1.0"},
        )

        # Track mounted router prefixes so we can gate disabled plugins.
        self._mounted_prefixes: dict[str, str] = {}

        # Names of plugins whose routers are currently disabled (return 404).
        # Stored as a set so route guards can check membership in O(1).
        self._disabled_plugins: set[str] = set()

        # Track the PluginContext built for each started plugin so we can
        # cancel its scheduled tasks on stop.
        self._plugin_contexts: dict[str, PluginContext] = {}

    # ── Public lifecycle API ──────────────────────────────────────────────────

    async def load_all(self) -> None:
        """Discover and load all plugin packages.

        1. Scan ``_PLUGINS_ROOT`` for packages (directories with __init__.py).
        2. Import each package and extract the Plugin instance.
        3. Read the DB ``PluginConfig`` row; create defaults if absent.
        4. If enabled, mount router and call ``start()``.
        """
        if not _PLUGINS_ROOT.exists():
            logger.warning("Plugins directory not found: %s", _PLUGINS_ROOT)
            return

        for pkg_dir in sorted(_PLUGINS_ROOT.iterdir()):
            if not pkg_dir.is_dir() or not (pkg_dir / "__init__.py").exists():
                continue

            pkg_name = pkg_dir.name
            try:
                await self._load_one(pkg_name)
            except Exception as exc:
                logger.error("Failed to load plugin %r: %s", pkg_name, exc, exc_info=True)

    async def _load_one(self, pkg_name: str) -> None:
        """Import a single plugin package and register it."""
        # Packages live under backend/plugins/, which must be on sys.path (see main.py).
        module_name = pkg_name

        if module_name in sys.modules:
            module = sys.modules[module_name]
        else:
            module = importlib.import_module(module_name)

        # Extract the plugin instance.
        plugin: Plugin | None = None

        if hasattr(module, "plugin") and isinstance(module.plugin, Plugin):
            plugin = module.plugin
        elif hasattr(module, "get_plugin"):
            plugin = module.get_plugin(None)
        else:
            logger.warning(
                "Plugin package %r has no `plugin` instance or `get_plugin` factory — skipping.",
                pkg_name,
            )
            return

        registry.register(plugin)
        logger.info("Loaded plugin: %s v%s", plugin.name, plugin.manifest.version)

        # Ensure a DB config row exists.
        enabled = await self._ensure_plugin_config(plugin)

        if enabled:
            await self._start_plugin(plugin)

    async def _ensure_plugin_config(self, plugin: Plugin) -> bool:
        """Create a PluginConfig row with defaults if absent; return enabled flag."""
        from sqlmodel import select

        from app.models import PluginConfig

        async with self._session_factory() as session:
            result = await session.execute(
                select(PluginConfig).where(PluginConfig.name == plugin.name)
            )
            row: PluginConfig | None = result.scalar_one_or_none()

            if row is None:
                row = PluginConfig(name=plugin.name, enabled=True)
                row.set_settings(plugin.manifest.default_settings.copy())
                session.add(row)
                await session.commit()
                logger.debug("Created default PluginConfig for %r", plugin.name)

            return row.enabled

    async def _start_plugin(self, plugin: Plugin) -> None:
        """Build the context, mount the router (first time only), and call plugin.start()."""
        ctx = self._build_context(plugin)

        # Mount the plugin's router once on first start.  On subsequent enables
        # (after a disable), the route is already in the app's route table; we
        # simply remove the plugin from _disabled_plugins so requests flow through.
        router = plugin.register_router()
        if router is not None:
            prefix = f"/api/plugins/{plugin.name}"
            if plugin.name not in self._mounted_prefixes:
                # Inject a guard dependency into every route on this router so
                # that when the plugin is disabled, all its endpoints return 404.
                guard = _make_plugin_guard(plugin.name, self._disabled_plugins)
                self._app.include_router(
                    router,
                    prefix=prefix,
                    dependencies=[Depends(guard)],
                )
                self._mounted_prefixes[plugin.name] = prefix
                logger.debug("Mounted router for plugin %r at %s", plugin.name, prefix)
            # Re-enabling — lift the 404 guard.
            self._disabled_plugins.discard(plugin.name)

        try:
            await plugin.start(ctx)
            self._plugin_contexts[plugin.name] = ctx
            logger.info("Plugin %r started.", plugin.name)
        except Exception as exc:
            logger.error("Plugin %r failed to start: %s", plugin.name, exc, exc_info=True)
            return

    async def _stop_plugin(self, plugin: Plugin) -> None:
        """Cancel scheduled tasks, deregister capabilities, then call plugin.stop()."""
        ctx = self._plugin_contexts.pop(plugin.name, None)
        if ctx is not None:
            ctx._cancel_scheduled_tasks()
            ctx._deregister_capabilities()

        try:
            await plugin.stop()
            logger.info("Plugin %r stopped.", plugin.name)
        except Exception as exc:
            logger.error("Plugin %r failed to stop cleanly: %s", plugin.name, exc)

    async def stop_all(self) -> None:
        """Stop all loaded plugins and close the shared HTTP client."""
        for plugin in registry.all():
            await self._stop_plugin(plugin)

        await self._http.aclose()
        logger.info("Plugin HTTP client closed.")

    # ── Runtime enable / disable ──────────────────────────────────────────────

    async def enable_plugin(self, name: str) -> bool:
        """Enable a plugin at runtime and start it.  Returns False if unknown."""
        plugin = registry.get(name)
        if plugin is None:
            return False

        await self._set_plugin_enabled(name, True)
        await self._start_plugin(plugin)
        await self._broadcast_fn("plugin.state", "system", {"name": name, "enabled": True})
        return True

    async def disable_plugin(self, name: str) -> bool:
        """Disable a plugin at runtime, stop it, and gate its router to 404."""
        plugin = registry.get(name)
        if plugin is None:
            return False

        await self._set_plugin_enabled(name, False)
        # Mark router disabled BEFORE stopping so any in-flight requests that
        # hit the route after this point get 404 rather than a broken state.
        if name in self._mounted_prefixes:
            self._disabled_plugins.add(name)
        await self._stop_plugin(plugin)
        await self._broadcast_fn("plugin.state", "system", {"name": name, "enabled": False})
        return True

    async def _set_plugin_enabled(self, name: str, enabled: bool) -> None:
        """Persist the enabled flag in the DB."""
        from sqlmodel import select

        from app.models import PluginConfig

        async with self._session_factory() as session:
            result = await session.execute(
                select(PluginConfig).where(PluginConfig.name == name)
            )
            row: PluginConfig | None = result.scalar_one_or_none()
            if row is not None:
                row.enabled = enabled
                await session.commit()

    # ── Public plugin settings API ────────────────────────────────────────────

    def is_plugin_disabled(self, name: str) -> bool:
        """Return True if the plugin's router should return 404."""
        return name in self._disabled_plugins

    async def get_plugin_settings(self, name: str) -> dict[str, Any]:
        """Return current settings for plugin ``name`` (merged with defaults)."""
        plugin = registry.get(name)
        if plugin is None:
            raise ValueError(f"Unknown plugin: {name!r}")
        ctx = self._build_context(plugin)
        return await ctx.get_settings()

    async def set_plugin_settings(self, name: str, settings: dict[str, Any]) -> dict[str, Any]:
        """Persist settings for plugin ``name`` and broadcast settings.updated.

        Returns the merged settings after persisting.
        """
        plugin = registry.get(name)
        if plugin is None:
            raise ValueError(f"Unknown plugin: {name!r}")
        ctx = self._build_context(plugin)
        await ctx.set_settings(settings)
        # Broadcast so the frontend knows the plugin's config changed.
        await self._broadcast_fn("settings.updated", "settings", {"key": f"plugin.{name}"})
        return await ctx.get_settings()

    # ── Context factory ───────────────────────────────────────────────────────

    def _build_context(self, plugin: Plugin) -> PluginContext:
        """Build a PluginContext wired to this loader's shared resources.

        Provides all PluginContext API members documented in PLUGIN_DEVELOPMENT.md §4:
        broadcast, get_settings, set_settings, db_session, http, get_secret,
        set_secret, config, data_dir, logger, schedule.
        """
        plugin_name = plugin.name

        # ── settings callbacks ────────────────────────────────────────────────

        async def get_settings_fn() -> dict[str, Any]:
            from sqlmodel import select

            from app.models import PluginConfig

            async with self._session_factory() as session:
                result = await session.execute(
                    select(PluginConfig).where(PluginConfig.name == plugin_name)
                )
                row: PluginConfig | None = result.scalar_one_or_none()
                if row is None:
                    return plugin.manifest.default_settings.copy()
                stored = row.get_settings()
                return {**plugin.manifest.default_settings, **stored}

        async def set_settings_fn(settings: dict[str, Any]) -> None:
            from sqlmodel import select

            from app.models import PluginConfig

            async with self._session_factory() as session:
                result = await session.execute(
                    select(PluginConfig).where(PluginConfig.name == plugin_name)
                )
                row: PluginConfig | None = result.scalar_one_or_none()
                if row is None:
                    row = PluginConfig(name=plugin_name)
                    session.add(row)
                row.set_settings(settings)
                await session.commit()

        # ── secret callbacks ──────────────────────────────────────────────────

        async def get_secret_fn(key: str) -> Any | None:
            from app.core.crypto import SecretStore

            async with self._session_factory() as session:
                store = SecretStore(session)
                return await store.get(key)

        async def set_secret_fn(key: str, value: Any) -> None:
            from app.core.crypto import SecretStore

            async with self._session_factory() as session:
                store = SecretStore(session)
                await store.set(key, value)

        # ── db session context manager ────────────────────────────────────────

        @asynccontextmanager
        async def db_session_fn():
            async with self._session_factory() as session:
                yield session

        return PluginContext(
            config=self._settings,
            data_dir=self._settings.data_dir,
            http=self._http,
            broadcast_fn=self._broadcast_fn,
            get_settings_fn=get_settings_fn,
            set_settings_fn=set_settings_fn,
            db_session_fn=db_session_fn,
            get_secret_fn=get_secret_fn,
            set_secret_fn=set_secret_fn,
            capability_registry=capabilities,
            plugin_name=plugin_name,
        )

    # ── Info helpers ──────────────────────────────────────────────────────────

    async def get_plugin_info_list(self) -> list[dict[str, Any]]:
        """Return serialisable PluginInfo dicts for all registered plugins."""
        from sqlmodel import select

        from app.models import PluginConfig

        infos: list[dict[str, Any]] = []

        async with self._session_factory() as session:
            result = await session.execute(select(PluginConfig))
            configs: dict[str, PluginConfig] = {
                row.name: row for row in result.scalars().all()
            }

        for plugin in registry.all():
            cfg = configs.get(plugin.name)
            infos.append({
                "name": plugin.manifest.name,
                "version": plugin.manifest.version,
                "description": plugin.manifest.description,
                "enabled": cfg.enabled if cfg else False,
                "has_router": plugin.register_router() is not None,
                "has_background_tasks": plugin.has_background_tasks,
                "frontend_component": plugin.manifest.frontend_component,
                "settings_schema": plugin.manifest.settings_schema,
            })

        return infos
