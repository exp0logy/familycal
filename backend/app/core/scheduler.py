"""
app/core/scheduler.py — Async periodic task scheduler.

Provides a simple ``Scheduler`` that runs named coroutine callbacks at fixed
intervals.  Designed to be exception-resilient: if a callback raises, the
error is logged and the scheduler continues running — one failure never kills
the loop or other scheduled tasks.

Used by:
  - calendar sync (every CALENDAR_SYNC_INTERVAL_MINUTES)
  - weather refresh (every N minutes, configured per plugin)
  - any future plugin that needs a background heartbeat

Usage::

    scheduler = Scheduler()

    @scheduler.every(minutes=15, name="calendar_sync")
    async def sync():
        await calendar_plugin.sync_all()

    await scheduler.start()   # spawns tasks; call during lifespan startup
    await scheduler.stop()    # cancels all tasks; call during lifespan shutdown
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)


# Type alias for a zero-argument async callable.
AsyncCallback = Callable[[], Coroutine[Any, Any, None]]


class _ScheduledTask:
    """Internal record for one registered periodic task."""

    __slots__ = ("name", "callback", "interval", "_task")

    def __init__(self, name: str, callback: AsyncCallback, interval: float) -> None:
        self.name = name
        self.callback = callback
        self.interval = interval          # seconds between invocations
        self._task: asyncio.Task[None] | None = None

    async def _run_loop(self) -> None:
        """Drive the periodic callback, catching and logging all exceptions."""
        logger.debug("Scheduler: task %r starting (interval=%.0fs).", self.name, self.interval)
        while True:
            try:
                await self.callback()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Scheduler: task %r raised an exception (will retry in %.0fs): %s",
                    self.name,
                    self.interval,
                    exc,
                    exc_info=True,
                )
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                logger.debug("Scheduler: task %r cancelled during sleep.", self.name)
                raise

    def start(self) -> None:
        """Spawn the background asyncio task."""
        if self._task is not None and not self._task.done():
            logger.warning("Scheduler: task %r is already running.", self.name)
            return
        self._task = asyncio.create_task(self._run_loop(), name=f"scheduler:{self.name}")

    def stop(self) -> None:
        """Cancel the background asyncio task."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            self._task = None


class Scheduler:
    """Registry and manager of periodic async tasks.

    Typical usage::

        scheduler = Scheduler()
        scheduler.register("my_task", my_coroutine_fn, interval_seconds=60)
        await scheduler.start()   # during app lifespan startup
        ...
        await scheduler.stop()    # during app lifespan shutdown
    """

    def __init__(self) -> None:
        self._tasks: dict[str, _ScheduledTask] = {}
        self._running = False

    # ── Registration ─────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        callback: AsyncCallback,
        *,
        interval_seconds: float,
    ) -> None:
        """Register a named periodic task.

        If the scheduler is already running (hot-register), the task is
        started immediately.
        """
        if name in self._tasks:
            logger.warning("Scheduler: replacing existing task %r.", name)
            self._tasks[name].stop()

        task = _ScheduledTask(name=name, callback=callback, interval=interval_seconds)
        self._tasks[name] = task

        if self._running:
            task.start()

    def unregister(self, name: str) -> None:
        """Stop and remove a task by name."""
        task = self._tasks.pop(name, None)
        if task is not None:
            task.stop()

    # ── Decorator helper ─────────────────────────────────────────────────────

    def every(
        self, *, seconds: float = 0, minutes: float = 0, name: str | None = None
    ) -> Callable[[AsyncCallback], AsyncCallback]:
        """Decorator that registers the decorated function as a periodic task.

        Example::

            @scheduler.every(minutes=15, name="sync")
            async def sync():
                ...
        """
        interval = seconds + minutes * 60

        def decorator(fn: AsyncCallback) -> AsyncCallback:
            task_name = name or fn.__name__
            self.register(task_name, fn, interval_seconds=interval)
            return fn

        return decorator

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start all registered tasks."""
        if self._running:
            logger.warning("Scheduler is already running.")
            return
        self._running = True
        for task in self._tasks.values():
            task.start()
        logger.info("Scheduler started (%d tasks).", len(self._tasks))

    async def stop(self) -> None:
        """Cancel all running tasks and wait for them to finish."""
        if not self._running:
            return
        self._running = False

        tasks_to_await: list[asyncio.Task[None]] = []
        for st in self._tasks.values():
            if st._task is not None and not st._task.done():
                tasks_to_await.append(st._task)
            st.stop()

        if tasks_to_await:
            # Give tasks a moment to acknowledge cancellation.
            await asyncio.gather(*tasks_to_await, return_exceptions=True)

        logger.info("Scheduler stopped.")

    # ── Introspection ────────────────────────────────────────────────────────

    def task_names(self) -> list[str]:
        """Return the names of all registered tasks."""
        return list(self._tasks.keys())

    def is_running(self) -> bool:
        return self._running


# Module-level singleton used by the app and plugins.
scheduler = Scheduler()
