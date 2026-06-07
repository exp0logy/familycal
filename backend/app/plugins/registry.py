"""
app/plugins/registry.py — Runtime registry of loaded plugin instances.

The registry is a thin dict wrapper that maps plugin names to their Plugin
instances.  It is populated by the loader and queried by routers and the
health endpoint.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from app.plugins.base import Plugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Holds all loaded Plugin instances, keyed by name.

    Populated exclusively by ``PluginLoader.load_all()``.  Other parts of the
    app read from this registry; only the loader writes to it.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    # ── Mutation (loader-only) ───────────────────────────────────────────────

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance.  Silently replaces an existing entry."""
        if plugin.name in self._plugins:
            logger.warning("Replacing already-registered plugin %r", plugin.name)
        self._plugins[plugin.name] = plugin
        logger.debug("Plugin %r registered.", plugin.name)

    def unregister(self, name: str) -> None:
        """Remove a plugin from the registry (e.g. on disable)."""
        self._plugins.pop(name, None)

    # ── Read access ──────────────────────────────────────────────────────────

    def get(self, name: str) -> Plugin | None:
        """Return the plugin with the given name, or None."""
        return self._plugins.get(name)

    def all(self) -> list[Plugin]:
        """Return all registered plugins in registration order."""
        return list(self._plugins.values())

    def names(self) -> list[str]:
        return list(self._plugins.keys())

    def __iter__(self) -> Iterator[Plugin]:
        return iter(self._plugins.values())

    def __len__(self) -> int:
        return len(self._plugins)

    def __contains__(self, name: str) -> bool:
        return name in self._plugins


# Module-level singleton shared by main.py and routers.
registry = PluginRegistry()
