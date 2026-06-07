"""
app/database.py — Async SQLAlchemy engine + session dependency.

Engine is created once, data directory is created if absent, and all tables
are created via SQLModel.metadata.create_all() during app lifespan startup.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.config import get_settings

logger = logging.getLogger(__name__)

# Module-level engine; initialised in create_db_and_tables() during lifespan.
_engine: create_async_engine | None = None  # type: ignore[type-arg]
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> create_async_engine:  # type: ignore[type-arg]
    """Return the async engine, raising if not yet initialised."""
    if _engine is None:
        raise RuntimeError("Database engine not initialised — call init_db() first.")
    return _engine


async def init_db() -> None:
    """Create the data directory, async engine, and all tables.

    Safe to call multiple times (idempotent — SQLModel only creates tables
    that do not yet exist).
    """
    global _engine, _session_factory

    settings = get_settings()

    # Ensure the data directory exists.
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    # Import models so their metadata is registered before create_all.
    import app.models  # noqa: F401  — side-effect import to register tables

    logger.info("Initialising database at %s", settings.db_url)

    _engine = create_async_engine(
        settings.db_url,
        echo=False,   # set True to log SQL queries during development
        # No connect_args needed: check_same_thread is a pysqlite/sync arg and
        # has no effect under aiosqlite's async driver.
    )

    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,  # keep objects usable after commit
    )

    # Create all tables that do not yet exist.
    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    logger.info("Database ready.")


async def close_db() -> None:
    """Dispose the engine connection pool on app shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        logger.info("Database engine disposed.")
        _engine = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session per request.

    Usage::

        @router.get("/example")
        async def example(session: AsyncSession = Depends(get_session)):
            ...
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first.")

    async with _session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
