from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from lenslet.storage.table.query_coordinator import (
    MAX_QUEUED_ANALYSES,
    MAX_SESSION_ENTRIES,
    SESSION_TTL_SECONDS,
    AnalysisBusy,
    TableQueryCoordinator,
)


def test_identical_subscribers_join_one_execution() -> None:
    async def scenario() -> None:
        started = threading.Event()
        release = threading.Event()
        calls = 0

        def operation(cancel) -> str:
            nonlocal calls
            calls += 1
            started.set()
            assert release.wait(timeout=2)
            assert not cancel()
            return "shared"

        coordinator = TableQueryCoordinator()
        first = asyncio.create_task(coordinator.acquire(
            "filter",
            "same",
            operation,
            client_session="session-a",
            query_revision=1,
        ))
        await asyncio.to_thread(started.wait, 2)
        second = asyncio.create_task(coordinator.acquire(
            "filter",
            "same",
            operation,
            client_session="session-b",
            query_revision=1,
        ))
        release.set()
        first_lease, second_lease = await asyncio.gather(first, second)

        assert calls == 1
        assert first_lease.value == second_lease.value == "shared"
        assert {first_lease.joined, second_lease.joined} == {False, True}
        assert coordinator.diagnostics()["analysis_queued_work"] == 0
        await coordinator.close()

    asyncio.run(scenario())


def test_queue_cache_and_session_state_are_exactly_bounded() -> None:
    async def scenario() -> None:
        clock = [0.0]
        coordinator = TableQueryCoordinator(clock=lambda: clock[0])
        started = threading.Event()
        release = threading.Event()

        def blocking(_cancel) -> str:
            started.set()
            assert release.wait(timeout=2)
            return "active"

        active = asyncio.create_task(coordinator.acquire(
            "request",
            "active",
            blocking,
            client_session="active-session",
            query_revision=1,
        ))
        await asyncio.to_thread(started.wait, 2)
        queued = [
            asyncio.create_task(coordinator.acquire(
                "request",
                f"queued-{index}",
                lambda _cancel, value=index: value,
                client_session=f"queued-session-{index}",
                query_revision=1,
            ))
            for index in range(40)
        ]
        await asyncio.sleep(0)
        assert coordinator.diagnostics()["analysis_queued_work"] == MAX_QUEUED_ANALYSES
        release.set()
        await active
        contention_results = await asyncio.gather(*queued, return_exceptions=True)
        assert sum(isinstance(result, AnalysisBusy) for result in contention_results) == 8

        for index in range(10):
            await coordinator.acquire(
                "filter",
                f"filter-{index}",
                lambda _cancel, value=index: value,
                client_session="cache-session",
                query_revision=1,
            )
            await coordinator.acquire(
                "order",
                f"order-{index}",
                lambda _cancel, value=index: value,
                client_session="cache-session",
                query_revision=1,
            )
        diagnostics = coordinator.diagnostics()
        assert diagnostics["analysis_filter_cache_entries"] == 8
        assert diagnostics["analysis_order_cache_entries"] == 8

        for index in range(MAX_SESSION_ENTRIES + 20):
            await coordinator.acquire(
                "filter",
                "filter-9",
                lambda _cancel: 9,
                client_session=f"hostile-{index}",
                query_revision=1,
            )
        assert coordinator.diagnostics()["analysis_session_entries"] == MAX_SESSION_ENTRIES
        clock[0] = SESSION_TTL_SECONDS + 1
        await coordinator.acquire(
            "filter",
            "filter-9",
            lambda _cancel: 9,
            client_session="after-ttl",
            query_revision=1,
        )
        assert coordinator.diagnostics()["analysis_session_entries"] == 1
        await coordinator.close()

    asyncio.run(scenario())


def test_ten_rapid_revisions_execute_only_active_and_latest_work() -> None:
    async def scenario() -> None:
        started = threading.Event()
        release = threading.Event()
        executions: list[int] = []

        def operation(revision: int):
            def run(cancel) -> int:
                executions.append(revision)
                if revision == 1:
                    started.set()
                    assert release.wait(timeout=2)
                    if cancel():
                        raise RuntimeError("superseded")
                return revision

            return run

        coordinator = TableQueryCoordinator()
        tasks = [asyncio.create_task(coordinator.acquire(
            "filter",
            "revision-1",
            operation(1),
            client_session="typing-session",
            query_revision=1,
        ))]
        await asyncio.to_thread(started.wait, 2)
        for revision in range(2, 11):
            tasks.append(asyncio.create_task(coordinator.acquire(
                "filter",
                f"revision-{revision}",
                operation(revision),
                client_session="typing-session",
                query_revision=revision,
            )))
            await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)

        assert executions == [1, 10]
        assert sum(getattr(result, "value", None) == 10 for result in results) == 1
        assert coordinator.diagnostics()["analysis_queued_work"] == 0
        await coordinator.close()

    asyncio.run(scenario())


def test_newer_revision_cancels_only_obsolete_session_subscribers() -> None:
    async def scenario() -> None:
        started = threading.Event()
        cancelled = threading.Event()
        release = threading.Event()

        def slow(cancel) -> str:
            started.set()
            while not release.wait(timeout=0.001):
                if cancel():
                    cancelled.set()
                    raise RuntimeError("cancelled at checkpoint")
            return "old"

        coordinator = TableQueryCoordinator()
        old_a = asyncio.create_task(coordinator.acquire(
            "filter",
            "old",
            slow,
            client_session="session-a",
            query_revision=1,
        ))
        old_b = asyncio.create_task(coordinator.acquire(
            "filter",
            "old",
            slow,
            client_session="session-b",
            query_revision=1,
        ))
        await asyncio.to_thread(started.wait, 2)
        new_a = asyncio.create_task(coordinator.acquire(
            "filter",
            "new",
            lambda _cancel: "new",
            client_session="session-a",
            query_revision=2,
        ))
        await asyncio.sleep(0)
        with pytest.raises(asyncio.CancelledError):
            await old_a
        assert not old_b.done()
        release.set()

        assert (await old_b).value == "old"
        assert (await new_a).value == "new"
        assert not cancelled.is_set()
        assert coordinator.diagnostics()["analysis_active_work"] == 0
        await coordinator.close()

    asyncio.run(scenario())


def test_unsubscribed_running_work_observes_cancellation_probe() -> None:
    async def scenario() -> None:
        started = threading.Event()
        observed = threading.Event()

        def slow(cancel) -> None:
            started.set()
            while not cancel():
                pass
            observed.set()

        coordinator = TableQueryCoordinator()
        task: asyncio.Task[Any] = asyncio.create_task(coordinator.acquire(
            "filter",
            "cancel-me",
            slow,
            client_session="session-a",
            query_revision=1,
        ))
        await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await asyncio.to_thread(observed.wait, 1)
        await coordinator.close()

    asyncio.run(scenario())


def test_admitted_sessions_are_scheduled_round_robin() -> None:
    async def scenario() -> None:
        started = threading.Event()
        release = threading.Event()
        order: list[str] = []

        def gate(_cancel) -> None:
            started.set()
            assert release.wait(timeout=2)

        def record(value: str):
            def operation(_cancel) -> str:
                order.append(value)
                return value

            return operation

        coordinator = TableQueryCoordinator()
        active = asyncio.create_task(coordinator.acquire(
            "request",
            "gate",
            gate,
            client_session="gate",
            query_revision=1,
        ))
        await asyncio.to_thread(started.wait, 2)
        tasks = [
            asyncio.create_task(coordinator.acquire(
                "request",
                key,
                record(key),
                client_session=session,
                query_revision=1,
            ))
            for key, session in (("a1", "a"), ("a2", "a"), ("b1", "b"))
        ]
        await asyncio.sleep(0)
        release.set()
        await active
        await asyncio.gather(*tasks)

        assert order == ["a1", "b1", "a2"]
        await coordinator.close()

    asyncio.run(scenario())
