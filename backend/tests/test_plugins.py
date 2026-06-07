"""
tests/test_plugins.py — Plugin system: list, enable/disable, settings.

Tests use a minimal fake plugin injected directly into the registry to avoid
importing real plugin packages or starting a full lifespan.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.plugins.base import Plugin, PluginManifest
from app.plugins.registry import registry


def _register_fake_plugin(name: str = "testplugin") -> Plugin:
    """Create and register a minimal plugin, returning the instance."""
    manifest = PluginManifest(
        name=name,
        version="0.1.0",
        description="Fake plugin for testing",
        default_settings={"key": "default"},
    )

    class FakePlugin(Plugin):
        pass

    FakePlugin.manifest = manifest
    fake = FakePlugin()

    # Register into the module system so the loader can find it by name.
    mod = ModuleType(name)
    mod.plugin = fake
    sys.modules[name] = mod

    registry.register(fake)
    return fake


async def _ensure_plugin_config(name: str, default_settings: dict) -> None:
    """Insert a PluginConfig row for the given plugin if absent."""
    from sqlmodel import select

    import app.database as db_module
    from app.database import get_engine, init_db
    from app.models import PluginConfig

    if db_module._engine is None:
        await init_db()

    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(
            select(PluginConfig).where(PluginConfig.name == name)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = PluginConfig(name=name, enabled=True)
            row.set_settings(default_settings)
            session.add(row)
            await session.commit()


def _make_loader_for_app(app: Any) -> Any:
    """Attach a minimal PluginLoader to app.state so plugin routes work."""
    from app.config import get_settings
    from app.database import get_engine
    from app.plugins.loader import PluginLoader
    from app.websocket import manager

    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    loader = PluginLoader(
        app=app,
        settings=get_settings(),
        session_factory=factory,
        broadcast_fn=manager.broadcast,
    )
    app.state.plugin_loader = loader
    return loader


@pytest.mark.asyncio
async def test_plugin_list_returns_array(app_client: AsyncClient) -> None:
    r = await app_client.get("/api/plugins")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_plugin_settings_get_and_put() -> None:
    """Test plugin settings GET and PUT using a loader wired to a test app."""
    from httpx import ASGITransport, AsyncClient

    import app.database as db_module
    from app.database import close_db, init_db
    from app.main import create_app

    # Fresh DB for this test.
    db_module._engine = None
    db_module._session_factory = None
    from app.config import get_settings
    get_settings.cache_clear()
    registry._plugins.clear()

    await init_db()

    # Register the fake plugin (return value not needed — side-effect only).
    _register_fake_plugin("settingsplugin2")
    await _ensure_plugin_config("settingsplugin2", {"key": "default"})

    test_app = create_app()
    _make_loader_for_app(test_app)

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as client:
        r = await client.get("/api/plugins/settingsplugin2/settings")
        assert r.status_code == 200
        assert r.json()["key"] == "default"

        r_put = await client.put(
            "/api/plugins/settingsplugin2/settings",
            json={"key": "updated_value", "new_key": 42},
        )
        assert r_put.status_code == 200
        assert r_put.json()["key"] == "updated_value"
        assert r_put.json()["new_key"] == 42

    await close_db()


@pytest.mark.asyncio
async def test_plugin_not_found(app_client: AsyncClient) -> None:
    r = await app_client.get("/api/plugins/doesnotexist/settings")
    assert r.status_code == 404
