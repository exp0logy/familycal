"""
tests/test_scheduler.py — Async scheduler tests.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.scheduler import Scheduler


@pytest.mark.asyncio
async def test_scheduler_runs_task() -> None:
    calls: list[int] = []
    scheduler = Scheduler()

    async def task() -> None:
        calls.append(1)

    scheduler.register("t", task, interval_seconds=0.05)
    await scheduler.start()
    await asyncio.sleep(0.2)
    await scheduler.stop()

    assert len(calls) >= 3


@pytest.mark.asyncio
async def test_scheduler_continues_after_exception() -> None:
    """A task that raises must not kill the scheduler loop."""
    calls: list[int] = []
    scheduler = Scheduler()

    async def failing_task() -> None:
        calls.append(1)
        if len(calls) <= 2:
            raise RuntimeError("expected test error")

    scheduler.register("failing", failing_task, interval_seconds=0.05)
    await scheduler.start()
    await asyncio.sleep(0.3)
    await scheduler.stop()

    # Should have run multiple times despite failures.
    assert len(calls) >= 3


@pytest.mark.asyncio
async def test_scheduler_stop_cancels_tasks() -> None:
    blocker_active = False
    scheduler = Scheduler()

    async def long_task() -> None:
        nonlocal blocker_active
        blocker_active = True
        await asyncio.sleep(9999)

    scheduler.register("long", long_task, interval_seconds=1)
    await scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    # After stop, no tasks should be running.
    assert not scheduler.is_running()


@pytest.mark.asyncio
async def test_scheduler_hot_register() -> None:
    """Tasks registered while the scheduler is running start immediately."""
    calls: list[int] = []
    scheduler = Scheduler()

    await scheduler.start()

    async def late_task() -> None:
        calls.append(1)

    scheduler.register("late", late_task, interval_seconds=0.05)
    await asyncio.sleep(0.2)
    await scheduler.stop()

    assert len(calls) >= 2
