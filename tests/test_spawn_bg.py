"""Tests for tracked background tasks (main._spawn_bg, Upgrade A1).

main registers its tool modules at import time, so ``main`` is imported lazily
inside each test. Async behaviour runs through ``asyncio.run`` because the repo
keeps pytest-asyncio in strict mode.
"""

from __future__ import annotations

import asyncio
import logging
import types


def _import_main() -> types.ModuleType:
    """Import main lazily; tool registration happens at import time."""
    import main

    return main


def _reset_bg_state(main: types.ModuleType) -> None:
    """Isolate shared module state so tests never leak into each other."""
    for task in list(main._BG_TASKS):
        if not task.done():
            task.cancel()
    main._BG_TASKS.clear()
    main._BG_BACKLOG_WARNED = False


async def _wait_until(predicate, timeout: float = 2.0) -> bool:
    """Poll a predicate on the running loop until true or timeout expires."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


def test_spawn_bg_keeps_reference_until_done():
    main = _import_main()

    async def scenario():
        _reset_bg_state(main)
        started = asyncio.Event()
        release = asyncio.Event()

        async def worker():
            started.set()
            await release.wait()

        main._spawn_bg(worker())
        await started.wait()
        assert len(main._BG_TASKS) == 1  # strong reference held while running

        release.set()
        assert await _wait_until(lambda: not main._BG_TASKS), (
            "completed task must be discarded from the tracked set"
        )

    asyncio.run(scenario())


def test_spawn_bg_logs_exception_without_propagating(caplog):
    main = _import_main()

    async def scenario():
        _reset_bg_state(main)

        async def worker():
            raise ValueError("boom inside bg work")

        main._spawn_bg(worker())
        assert await _wait_until(lambda: not main._BG_TASKS), (
            "failed task must still be discarded"
        )

    with caplog.at_level(logging.WARNING):
        asyncio.run(scenario())  # must not raise despite the worker failing

    assert any(
        "bg task failed" in rec.getMessage() and "boom inside bg work" in rec.getMessage()
        for rec in caplog.records
    )


def test_spawn_bg_cancelled_task_logs_nothing(caplog):
    main = _import_main()

    async def scenario():
        _reset_bg_state(main)
        started = asyncio.Event()

        async def worker():
            started.set()
            await asyncio.sleep(30)

        main._spawn_bg(worker())
        await started.wait()
        next(iter(main._BG_TASKS)).cancel()

        assert await _wait_until(lambda: not main._BG_TASKS), (
            "cancelled task must be discarded"
        )

    with caplog.at_level(logging.WARNING):
        asyncio.run(scenario())

    assert not any("bg task failed" in rec.getMessage() for rec in caplog.records)


def test_spawn_bg_backlog_warning_fires_once_per_burst(monkeypatch, caplog):
    main = _import_main()
    monkeypatch.setattr(main, "_BG_MAX_TRACKED", 2)  # lower warn-only threshold

    async def scenario():
        _reset_bg_state(main)

        async def pending():
            await asyncio.sleep(30)

        holders: list[asyncio.Task] = []
        for _ in range(3):  # burst crossing the threshold of 2
            before = set(main._BG_TASKS)
            main._spawn_bg(pending())
            holders.append(next(iter(set(main._BG_TASKS) - before)))

        for task in holders[:2]:
            task.cancel()
        assert await _wait_until(
            lambda: len(main._BG_TASKS) < main._BG_MAX_TRACKED
        ), "tracked count must drop back below the threshold"
        main._BG_BACKLOG_WARNED = False
        assert main._BG_BACKLOG_WARNED is False, "one-shot flag must reset"

        before = set(main._BG_TASKS)
        main._spawn_bg(pending())  # second burst crosses the threshold again
        holders.append(next(iter(set(main._BG_TASKS) - before)))

        for task in holders:
            if not task.done():
                task.cancel()
        assert await _wait_until(lambda: not main._BG_TASKS)

    with caplog.at_level(logging.WARNING):
        asyncio.run(scenario())

    backlog_lines = [
        rec.getMessage() for rec in caplog.records if "bg backlog" in rec.getMessage()
    ]
    assert len(backlog_lines) == 2
    assert "pending memory writes" in backlog_lines[0]


def test_spawn_bg_accepts_to_thread_coroutine():
    main = _import_main()

    async def scenario():
        _reset_bg_state(main)
        ran: list[str] = []

        def blocking_bit() -> None:
            ran.append("exchange-written")

        main._spawn_bg(asyncio.to_thread(blocking_bit))  # mirrors production usage
        assert await _wait_until(lambda: not main._BG_TASKS)
        assert ran == ["exchange-written"]

    asyncio.run(scenario())
