"""
app/plugins/base.py — Plugin base class, PluginManifest, and PluginContext.

Every plugin must:
  1. Define a ``PluginManifest`` describing static metadata.
  2. Subclass ``Plugin``, set ``manifest``, and implement the optional hooks.
  3. Expose a module-level ``plugin`` instance OR a ``get_plugin(context)`` factory.

The core never special-cases individual plugins; it only calls the methods
defined here.  This makes adding future plugins (Home Assistant, MQTT, …)
purely additive — no core changes needed.

PluginContext API (as per PLUGIN_DEVELOPMENT.md §4):

  await ctx.broadcast(type, channel, payload)   — push WS envelope
  await ctx.get_settings() -> dict              — merged settings
  await ctx.set_settings(dict)                  — persist settings
  ctx.db_session()                              — async context manager → AsyncSession
  ctx.http                                      — shared httpx.AsyncClient
  await ctx.get_secret(key) -> Any | None       — Fernet-encrypted secret
  await ctx.set_secret(key, value)              — encrypt and persist secret
  ctx.config                                    — app Settings
  ctx.data_dir                                  — Path to writable data dir
  ctx.logger                                    — namespaced Logger
  ctx.schedule(coro_fn, interval_seconds,       — register periodic task;
               run_immediately=False)             auto-cancelled on stop()
  ctx.register_capability(name, callable)       — publish a named callable
  ctx.resolve_capability(name) -> callable|None — look up a named callable
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter
    from httpx import AsyncClient

    from app.config import Settings


# ── PluginManifest ─────────────────────────────────────────────────────────────

@dataclass
class PluginManifest:
    """Static metadata declared by each plugin.

    Attributes:
        name: Unique snake_case plugin identifier (e.g. ``"weather"``).
        version: SemVer string (e.g. ``"1.0.0"``).
        description: One-line human-readable description shown in the UI.
        frontend_component: Name registered in the frontend plugin registry,
            or ``None`` if the plugin has no UI widget.
        settings_schema: JSON-Schema-shaped dict that drives the auto-generated
            settings form.  ``None`` if no settings.
        default_settings: Values merged underneath persisted settings on every
            ``get_settings()`` call, so new keys are always present.
        requires_secrets: Secret key names this plugin reads — informational
            only (documentation, future capabilities UI).
    """

    name: str
    version: str
    description: str
    frontend_component: str | None = None
    settings_schema: dict[str, Any] | None = None
    default_settings: dict[str, Any] = field(default_factory=dict)
    requires_secrets: list[str] = field(default_factory=list)


# ── CapabilityRegistry ────────────────────────────────────────────────────────

class CapabilityRegistry:
    """Shared registry of named callables published by plugins.

    Decouples the core (events router, calendar router) from specific plugin
    packages: a router resolves ``"calendar.create_event"`` rather than
    importing ``calendar_plugin``.  Plugins register capabilities in
    ``start()`` and they are automatically removed in ``stop()``.
    """

    def __init__(self) -> None:
        self._caps: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, callable_: Callable[..., Any]) -> None:
        self._caps[name] = callable_

    def deregister(self, name: str) -> None:
        self._caps.pop(name, None)

    def resolve(self, name: str) -> Callable[..., Any] | None:
        return self._caps.get(name)


# Module-level capability registry shared by all plugins and the app.
capabilities = CapabilityRegistry()


# ── PluginContext ──────────────────────────────────────────────────────────────

class PluginContext:
    """Runtime context injected into plugins at ``start()`` time.

    This is the **only** interface a plugin needs to the core — keeping plugins
    fully decoupled from internal implementation details.

    Background tasks registered via ``ctx.schedule(...)`` are tracked per-plugin
    and automatically cancelled when the plugin is stopped.
    """

    def __init__(
        self,
        *,
        config: Settings,
        data_dir: Any,                   # pathlib.Path
        http: AsyncClient,
        broadcast_fn: Callable[..., Coroutine[Any, Any, None]],
        get_settings_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
        set_settings_fn: Callable[..., Coroutine[Any, Any, None]],
        db_session_fn: Callable[[], Any],  # returns an async context manager
        get_secret_fn: Callable[..., Coroutine[Any, Any, Any]],
        set_secret_fn: Callable[..., Coroutine[Any, Any, None]],
        capability_registry: CapabilityRegistry,
        plugin_name: str,
    ) -> None:
        self.config = config
        self.data_dir = data_dir
        self.http = http
        self.logger: logging.Logger = logging.getLogger(f"plugin.{plugin_name}")

        self._plugin_name = plugin_name
        self._broadcast_fn = broadcast_fn
        self._get_settings_fn = get_settings_fn
        self._set_settings_fn = set_settings_fn
        self._db_session_fn = db_session_fn
        self._get_secret_fn = get_secret_fn
        self._set_secret_fn = set_secret_fn
        self._capability_registry = capability_registry

        # Scheduled task names registered by this plugin instance; used for
        # auto-cancellation in _cancel_scheduled_tasks().
        self._scheduled_task_names: list[str] = []
        # Capability names registered by this plugin; cleared on stop().
        self._registered_capabilities: list[str] = []

    # ── WebSocket ────────────────────────────────────────────────────────────

    async def broadcast(self, type_: str, channel: str, payload: Any) -> None:
        """Push a WebSocket message envelope to all subscribed clients.

        See ARCHITECTURE.md §4 for channel/type conventions.
        """
        await self._broadcast_fn(type_, channel, payload)

    # ── Settings ─────────────────────────────────────────────────────────────

    async def get_settings(self) -> dict[str, Any]:
        """Return this plugin's persisted settings merged over ``default_settings``."""
        return await self._get_settings_fn()

    async def set_settings(self, settings: dict[str, Any]) -> None:
        """Persist settings for this plugin.  Broadcasts ``settings.updated``."""
        await self._set_settings_fn(settings)

    # ── Secrets ──────────────────────────────────────────────────────────────

    async def get_secret(self, key: str) -> Any | None:
        """Return the decrypted value for ``key``, or ``None`` if absent.

        Secrets are Fernet-encrypted at rest and never exposed to the frontend.
        Use namespaced keys, e.g. ``"oauth.google"`` or ``"caldav.source-id"``.
        """
        return await self._get_secret_fn(key)

    async def set_secret(self, key: str, value: Any) -> None:
        """Encrypt and persist ``value`` under ``key``.

        Any JSON-serialisable value is accepted (dict, list, str, …).
        """
        await self._set_secret_fn(key, value)

    # ── Database ─────────────────────────────────────────────────────────────

    def db_session(self) -> Any:
        """Return an async context manager that yields an ``AsyncSession``.

        Usage::

            async with ctx.db_session() as session:
                result = await session.execute(select(Event))
        """
        return self._db_session_fn()

    # ── Scheduling ───────────────────────────────────────────────────────────

    def schedule(
        self,
        coro_fn: Callable[[], Coroutine[Any, Any, None]],
        interval_seconds: float,
        *,
        run_immediately: bool = False,
    ) -> None:
        """Register a periodic background task with the shared scheduler.

        Tasks registered this way are automatically cancelled when the plugin's
        ``stop()`` is called (via ``_cancel_scheduled_tasks()``).

        Args:
            coro_fn: Zero-argument async callable to run at each interval.
            interval_seconds: Seconds between invocations.
            run_immediately: If ``True``, run ``coro_fn`` once right away
                before the first scheduled interval.
        """
        from app.core.scheduler import scheduler

        # Build a unique task name to allow targeted cancellation.
        task_name = f"plugin.{self._plugin_name}.{coro_fn.__name__}"

        if run_immediately:
            # Wrap the callback so the first call fires immediately, then
            # every interval_seconds thereafter.
            original_fn = coro_fn

            async def _run_immediately_first() -> None:
                await original_fn()

            asyncio.create_task(_run_immediately_first(), name=f"{task_name}:immediate")

        scheduler.register(task_name, coro_fn, interval_seconds=interval_seconds)
        self._scheduled_task_names.append(task_name)
        self.logger.debug("Scheduled task %r (interval=%.0fs).", task_name, interval_seconds)

    # ── Capabilities ─────────────────────────────────────────────────────────

    def register_capability(self, name: str, callable_: Callable[..., Any]) -> None:
        """Publish a named callable to the shared capability registry.

        Other parts of the app (routers, other plugins) can resolve it by name
        without importing from the plugin package directly — keeping the core
        fully decoupled.

        Example::

            ctx.register_capability("calendar.create_event", self._service.write_event)
            ctx.register_capability("calendar.sync_all", self._service.sync_all)

        Capabilities registered here are automatically deregistered when the
        plugin is stopped.
        """
        self._capability_registry.register(name, callable_)
        self._registered_capabilities.append(name)
        self.logger.debug("Registered capability %r.", name)

    def resolve_capability(self, name: str) -> Callable[..., Any] | None:
        """Return the callable registered under ``name``, or ``None``."""
        return self._capability_registry.resolve(name)

    def _deregister_capabilities(self) -> None:
        """Remove all capabilities this plugin registered.

        Called automatically by the loader when the plugin is stopped.
        """
        for name in self._registered_capabilities:
            self._capability_registry.deregister(name)
            self.logger.debug("Deregistered capability %r.", name)
        self._registered_capabilities.clear()

    def _cancel_scheduled_tasks(self) -> None:
        """Unregister all tasks that were registered via ``ctx.schedule()``.

        Called automatically by the loader when the plugin is stopped.
        """
        from app.core.scheduler import scheduler

        for name in self._scheduled_task_names:
            scheduler.unregister(name)
            self.logger.debug("Unregistered scheduled task %r.", name)
        self._scheduled_task_names.clear()


# ── Plugin base class ──────────────────────────────────────────────────────────

class Plugin:
    """Abstract base class for all Family Organiser plugins.

    Subclasses must set the ``manifest`` class attribute and may override any
    of the lifecycle hooks.  Only ``manifest`` is required.

    Lifecycle::

        loader.load()   → __init__()                (module import time)
        app startup     → start(ctx)                (background tasks begin)
        app shutdown    → stop()                    (clean up tasks)
        PATCH enable    → start(ctx) or stop()      (runtime toggle)

    Background tasks should be registered via ``ctx.schedule()`` in ``start()``
    — they are auto-cancelled when ``stop()`` is called by the loader.  For
    tasks that need more control (e.g. long-lived connections), spawn them with
    ``asyncio.create_task()`` and cancel them manually in ``stop()``.
    """

    # Must be overridden by each plugin subclass.
    manifest: PluginManifest

    def __init__(self) -> None:
        # Set by the loader before start() is called.
        self._ctx: PluginContext | None = None

    # ── Lifecycle hooks ──────────────────────────────────────────────────────

    def register_router(self) -> APIRouter | None:
        """Return an ``APIRouter`` mounted under ``/api/plugins/<name>``.

        Return ``None`` (the default) if the plugin has no HTTP endpoints.
        """
        return None

    async def start(self, ctx: PluginContext) -> None:
        """Called when the plugin is enabled (app start or runtime toggle).

        Register background tasks via ``ctx.schedule()``.  Store ``ctx`` on
        ``self`` for use in those tasks.  Must not block.
        """
        self._ctx = ctx

    async def stop(self) -> None:
        """Called when the plugin is disabled (app shutdown or runtime toggle).

        The loader calls ``ctx._cancel_scheduled_tasks()`` before this method,
        so tasks registered via ``ctx.schedule()`` are already cancelled.
        Override to cancel manually spawned tasks or close connections.
        """

    # ── Convenience properties ───────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def has_router(self) -> bool:
        return self.register_router() is not None

    @property
    def has_background_tasks(self) -> bool:
        """True if this plugin registers background tasks in ``start()``.

        Override to return ``True``; used by the system status endpoint.
        """
        return False
