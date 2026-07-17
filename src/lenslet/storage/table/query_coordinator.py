from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable, Hashable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import threading
from time import monotonic
from typing import Any, Generic, Literal, TypeVar, cast


MAX_QUEUED_ANALYSES = 32
MAX_FILTER_CACHE_ENTRIES = 8
MAX_ORDER_CACHE_ENTRIES = 8
MAX_SESSION_ENTRIES = 256
SESSION_TTL_SECONDS = 5 * 60.0

AnalysisKind = Literal["filter", "order", "generic", "request"]
T = TypeVar("T")


class AnalysisBusy(RuntimeError):
    """Raised when bounded analysis admission cannot safely accept more work."""


class AnalysisSuperseded(asyncio.CancelledError):
    """Raised when a newer semantic revision replaces this subscriber."""


@dataclass(frozen=True, slots=True)
class AnalysisLease(Generic[T]):
    value: T
    joined: bool = False
    cached: bool = False


@dataclass(slots=True)
class _Subscriber:
    token: int
    session: str
    revision: int
    future: asyncio.Future[Any]


@dataclass(slots=True)
class _Job:
    kind: AnalysisKind
    key: Hashable
    operation: Callable[[Callable[[], bool]], Any]
    owner_session: str
    subscribers: dict[int, _Subscriber] = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    started: bool = False

    @property
    def identity(self) -> tuple[AnalysisKind, Hashable]:
        return self.kind, self.key


@dataclass(slots=True)
class _SessionState:
    revision: int
    touched_at: float


class TableQueryCoordinator:
    """Globally bounded, subscriber-aware scheduler for browse analysis work."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = monotonic,
        on_analysis_event: Callable[[str], None] | None = None,
    ) -> None:
        self._clock = clock
        self._on_analysis_event = on_analysis_event
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lenslet-query")
        self._state_lock = threading.RLock()
        self._jobs: dict[tuple[AnalysisKind, Hashable], _Job] = {}
        self._owner_queues: dict[str, deque[tuple[AnalysisKind, Hashable]]] = {}
        self._round_robin: deque[str] = deque()
        self._active: _Job | None = None
        self._filter_cache: OrderedDict[Hashable, Any] = OrderedDict()
        self._order_cache: OrderedDict[Hashable, Any] = OrderedDict()
        self._sessions: OrderedDict[str, _SessionState] = OrderedDict()
        self._next_token = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None
        self._worker: asyncio.Task[None] | None = None
        self._closed = False

    async def start(self) -> None:
        self._ensure_worker()

    async def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            jobs = list(self._jobs.values())
            self._jobs.clear()
            self._owner_queues.clear()
            self._round_robin.clear()
            for job in jobs:
                job.cancel_event.set()
            worker = self._worker
            if worker is not None:
                worker.cancel()
        for job in jobs:
            self._finish_subscribers(job, AnalysisSuperseded())
        if worker is not None:
            await asyncio.gather(worker, return_exceptions=True)
        await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=True)

    async def acquire(
        self,
        kind: AnalysisKind,
        key: Hashable,
        operation: Callable[[Callable[[], bool]], T],
        *,
        client_session: str,
        query_revision: int,
        disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AnalysisLease[T]:
        loop = self._ensure_worker()
        future: asyncio.Future[Any] = loop.create_future()
        joined = False
        token = 0
        with self._state_lock:
            self._register_session(client_session, query_revision)
            cache = self._cache_for(kind)
            if cache is not None and key in cache:
                value = cache.pop(key)
                cache[key] = value
                return AnalysisLease(value=cast(T, value), cached=True)

            identity = (kind, key)
            job = self._jobs.get(identity)
            if job is None:
                if self._queued_count_locked() >= MAX_QUEUED_ANALYSES:
                    raise AnalysisBusy("analysis queue is full")
                job = _Job(
                    kind=kind,
                    key=key,
                    operation=cast(Callable[[Callable[[], bool]], Any], operation),
                    owner_session=client_session,
                )
                self._jobs[identity] = job
                self._enqueue_locked(job)
            else:
                joined = True
                self._emit("joined", kind)
            self._next_token += 1
            token = self._next_token
            job.subscribers[token] = _Subscriber(
                token=token,
                session=client_session,
                revision=query_revision,
                future=future,
            )
            self._signal_worker_locked()

        try:
            value = await self._await_result(future, token, disconnected)
            return AnalysisLease(value=cast(T, value), joined=joined)
        finally:
            self._unsubscribe(token)

    def diagnostics(self) -> dict[str, int]:
        with self._state_lock:
            return {
                "analysis_active_work": int(self._active is not None),
                "analysis_queued_work": self._queued_count_locked(),
                "analysis_filter_cache_entries": len(self._filter_cache),
                "analysis_order_cache_entries": len(self._order_cache),
                "analysis_session_entries": len(self._sessions),
            }

    def _ensure_worker(self) -> asyncio.AbstractEventLoop:
        if self._closed:
            raise RuntimeError("analysis coordinator is closed")
        loop = asyncio.get_running_loop()
        with self._state_lock:
            if self._loop is not loop:
                self._reset_loop_locked(loop)
            if self._worker is None or self._worker.done():
                self._worker = loop.create_task(self._run_worker())
            return loop

    def _reset_loop_locked(self, loop: asyncio.AbstractEventLoop) -> None:
        stale_jobs = list(self._jobs.values())
        self._jobs.clear()
        self._owner_queues.clear()
        self._round_robin.clear()
        self._active = None
        for job in stale_jobs:
            job.cancel_event.set()
        self._loop = loop
        self._wake = asyncio.Event()
        self._worker = None

    async def _run_worker(self) -> None:
        while True:
            job = self._take_next_job()
            if job is None:
                wake = self._wake
                if wake is None:
                    return
                await wake.wait()
                wake.clear()
                continue
            self._emit("started", job.kind)
            loop = asyncio.get_running_loop()
            try:
                result = await loop.run_in_executor(
                    self._executor,
                    job.operation,
                    job.cancel_event.is_set,
                )
            except asyncio.CancelledError:
                job.cancel_event.set()
                self._complete_job(job, error=AnalysisSuperseded())
                raise
            except BaseException as exc:
                if job.cancel_event.is_set():
                    self._emit("cancelled", job.kind)
                    self._complete_job(job, error=AnalysisSuperseded())
                else:
                    self._emit("failed", job.kind)
                    self._complete_job(job, error=exc)
            else:
                if job.cancel_event.is_set():
                    self._emit("cancelled", job.kind)
                    self._complete_job(job, error=AnalysisSuperseded())
                else:
                    self._emit("completed", job.kind)
                    self._complete_job(job, result=result)

    def _take_next_job(self) -> _Job | None:
        with self._state_lock:
            while self._round_robin:
                owner = self._round_robin.popleft()
                queue = self._owner_queues.get(owner)
                if queue is None:
                    continue
                while queue:
                    identity = queue.popleft()
                    job = self._jobs.get(identity)
                    if job is None or job.started or not job.subscribers:
                        continue
                    if queue:
                        self._round_robin.append(owner)
                    else:
                        self._owner_queues.pop(owner, None)
                    job.started = True
                    self._active = job
                    return job
                self._owner_queues.pop(owner, None)
            return None

    def _complete_job(
        self,
        job: _Job,
        *,
        result: Any = None,
        error: BaseException | None = None,
    ) -> None:
        with self._state_lock:
            self._jobs.pop(job.identity, None)
            if self._active is job:
                self._active = None
            if error is None and job.subscribers:
                cache = self._cache_for(job.kind)
                if cache is not None:
                    cache[job.key] = result
                    cache.move_to_end(job.key)
                    limit = (
                        MAX_FILTER_CACHE_ENTRIES
                        if job.kind == "filter"
                        else MAX_ORDER_CACHE_ENTRIES
                    )
                    while len(cache) > limit:
                        cache.popitem(last=False)
            self._signal_worker_locked()
        self._finish_subscribers(job, error, result=result)

    @staticmethod
    def _finish_subscribers(
        job: _Job,
        error: BaseException | None,
        *,
        result: Any = None,
    ) -> None:
        subscribers = list(job.subscribers.values())
        job.subscribers.clear()
        for subscriber in subscribers:
            future = subscriber.future
            if future.done() or future.get_loop().is_closed():
                continue
            if error is None:
                future.set_result(result)
            elif isinstance(error, asyncio.CancelledError):
                future.cancel()
            else:
                future.set_exception(error)

    async def _await_result(
        self,
        future: asyncio.Future[Any],
        token: int,
        disconnected: Callable[[], Awaitable[bool]] | None,
    ) -> Any:
        if disconnected is None:
            return await future
        while not future.done():
            done, _pending = await asyncio.wait({future}, timeout=0.01)
            if done:
                break
            if await disconnected():
                self._unsubscribe(token)
                raise asyncio.CancelledError
        return await future

    def _register_session(self, session: str, revision: int) -> None:
        now = self._clock()
        self._prune_sessions_locked(now)
        current = self._sessions.get(session)
        if current is not None and revision < current.revision:
            raise AnalysisSuperseded()
        if current is not None and revision > current.revision:
            self._supersede_locked(session, revision)
        elif current is None and len(self._sessions) >= MAX_SESSION_ENTRIES:
            evicted_session, _state = self._sessions.popitem(last=False)
            self._supersede_locked(evicted_session, revision=None)
        self._sessions[session] = _SessionState(revision=revision, touched_at=now)
        self._sessions.move_to_end(session)

    def _prune_sessions_locked(self, now: float) -> None:
        cutoff = now - SESSION_TTL_SECONDS
        while self._sessions:
            session, state = next(iter(self._sessions.items()))
            if state.touched_at > cutoff:
                break
            self._sessions.pop(session, None)
            self._supersede_locked(session, revision=None)

    def _supersede_locked(self, session: str, revision: int | None) -> None:
        for job in list(self._jobs.values()):
            for token, subscriber in list(job.subscribers.items()):
                if subscriber.session != session:
                    continue
                if revision is not None and subscriber.revision >= revision:
                    continue
                job.subscribers.pop(token, None)
                self._emit("superseded", job.kind)
                if not subscriber.future.done():
                    subscriber.future.cancel()
            if not job.subscribers:
                job.cancel_event.set()
                if not job.started:
                    self._jobs.pop(job.identity, None)

    def _unsubscribe(self, token: int) -> None:
        with self._state_lock:
            for job in list(self._jobs.values()):
                if token not in job.subscribers:
                    continue
                job.subscribers.pop(token, None)
                if not job.subscribers:
                    job.cancel_event.set()
                    if not job.started:
                        self._jobs.pop(job.identity, None)
                return

    def _enqueue_locked(self, job: _Job) -> None:
        queue = self._owner_queues.setdefault(job.owner_session, deque())
        was_empty = not queue
        queue.append(job.identity)
        if was_empty:
            self._round_robin.append(job.owner_session)

    def _queued_count_locked(self) -> int:
        return sum(not job.started for job in self._jobs.values())

    def _cache_for(self, kind: AnalysisKind) -> OrderedDict[Hashable, Any] | None:
        if kind == "filter":
            return self._filter_cache
        if kind == "order":
            return self._order_cache
        return None

    def _signal_worker_locked(self) -> None:
        if self._wake is not None:
            self._wake.set()

    def _emit(self, event: str, kind: AnalysisKind) -> None:
        if self._on_analysis_event is not None and kind != "request":
            self._on_analysis_event(event)
