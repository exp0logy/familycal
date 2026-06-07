"""
tests/conftest.py — Shared pytest fixtures for the backend test suite.

All tests use an in-memory/temp SQLite database and an httpx AsyncClient
with an ASGI transport.  No real OAuth or internet access is required.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure backend/plugins is importable before any app code is imported.
_PLUGINS_DIR = str(Path(__file__).parent.parent / "plugins")
if _PLUGINS_DIR not in sys.path:
    sys.path.insert(0, _PLUGINS_DIR)


@pytest.fixture(scope="session", autouse=True)
def _tmp_data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a session-scoped temp directory and set required env vars.

    Sets DATA_DIR and a deterministic SECRET_KEY so SecretStore.set() works
    in tests without a real .env file.  The key is test-only — never use in
    production.
    """
    data_dir = tmp_path_factory.mktemp("familycal_data")
    os.environ["DATA_DIR"] = str(data_dir)
    (data_dir / "photos").mkdir(parents=True, exist_ok=True)

    # Valid Fernet key (test-only).  Set before any crypto import so that
    # _get_fernet_for_encrypt() doesn't raise during tests.
    if not os.environ.get("SECRET_KEY"):
        from cryptography.fernet import Fernet
        os.environ["SECRET_KEY"] = Fernet.generate_key().decode()

    # Reset the cached Fernet instance so it picks up the key we just set.
    import app.core.crypto as _crypto_mod
    _crypto_mod._fernet = None
    _crypto_mod._fernet_ok = False

    return data_dir


@pytest.fixture(scope="session", autouse=True)
def _clear_settings_cache(_tmp_data_dir: Path) -> None:
    """Force pydantic-settings to re-read env after we set DATA_DIR."""
    from app.config import get_settings
    get_settings.cache_clear()


@pytest_asyncio.fixture(scope="function")
async def app_client() -> AsyncGenerator[AsyncClient, None]:
    """Yield an httpx AsyncClient with the full app initialised (DB + plugins).

    Each test function gets a fresh database by resetting the engine global
    before init_db and clearing the settings cache.
    """
    # Reset DB globals so each test gets a clean database.
    import app.database as db_module

    db_module._engine = None
    db_module._session_factory = None

    from app.config import get_settings
    get_settings.cache_clear()

    # Re-read DATA_DIR from the environment.
    import importlib
    importlib.reload(db_module)

    # Also reset the plugin registry between tests.
    from app.plugins.registry import registry
    registry._plugins.clear()

    # Reset the scheduler.
    from app.core.scheduler import scheduler
    scheduler._tasks.clear()
    scheduler._running = False

    from app.database import close_db, init_db

    await init_db()

    from app.main import create_app
    test_app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as client:
        yield client

    await close_db()
