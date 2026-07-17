from __future__ import annotations

from collections import deque
from collections.abc import Callable, Hashable
from concurrent.futures import Future
from dataclasses import dataclass, field
import logging
from threading import Condition, Thread
from typing import Any, Deque, Generic, Literal, TypeVar, cast


MAX_THUMBNAIL_WORKERS = 4
MAX_QUEUED_THUMBNAILS = 128
MAX_INFLIGHT_THUMBNAILS = 256

logger = logging.getLogger(__name__)

T = TypeVar("T")
CancelState = Literal["queued", "inflight", "none"]


class ThumbnailBusy(RuntimeError):
    """Raised when bounded thumbnail work cannot be admitted."""


@dataclass(slots=True)
class _ThumbnailJob:
    key: Hashable
    operation: Callable[[], Any]
    waiters: set[Future[Any]] = field(default_factory=set)
    background: bool = False
    started: bool = False


class ThumbnailScheduler(Generic[T]):
    """Bounded dedicated worker pool with per-key work deduplication."""

    def __init__(
        self,
        max_workers: int = MAX_THUMBNAIL_WORKERS,
        *,
        max_queue_size: int = MAX_QUEUED_THUMBNAILS,
        max_inflight_entries: int = MAX_INFLIGHT_THUMBNAILS,
        name: str = "lenslet-thumb",
    ) -> None:
        self._max_workers = min(MAX_THUMBNAIL_WORKERS, max(1, int(max_workers)))
        self._max_queue_size = min(MAX_QUEUED_THUMBNAILS, max(1, int(max_queue_size)))
        self._max_inflight_entries = min(
            MAX_INFLIGHT_THUMBNAILS,
            max(1, int(max_inflight_entries)),
        )
        self._name = name
        self._queue: Deque[_ThumbnailJob] = deque()
        self._inflight: dict[Hashable, _ThumbnailJob] = {}
        self._cond = Condition()
        self._closed = False
        self._started = False
        self._threads: list[Thread] = []
        self._background_dropped = 0
        self._active_background = 0

    def start(self) -> None:
        with self._cond:
            if self._closed or self._started:
                return
            self._threads = [
                Thread(target=self._worker, name=f"{self._name}-{idx}", daemon=True)
                for idx in range(self._max_workers)
            ]
            self._started = True
            for thread in self._threads:
                thread.start()

    def submit(self, key: Hashable, operation: Callable[[], T]) -> Future[T]:
        self.start()
        with self._cond:
            self._ensure_open()
            job = self._inflight.get(key)
            waiter: Future[Any] = Future()
            if job is not None:
                if job.background:
                    raise ThumbnailBusy("thumbnail key is occupied by background work")
                job.waiters.add(waiter)
                return cast(Future[T], waiter)
            self._ensure_capacity(prefer_foreground=True)
            job = _ThumbnailJob(key=key, operation=operation)
            job.waiters.add(waiter)
            self._inflight[key] = job
            self._queue.append(job)
            self._cond.notify()
            return cast(Future[T], waiter)

    def submit_background(self, key: Hashable, operation: Callable[[], Any]) -> bool:
        """Admit best-effort work without creating an unobserved Future."""
        self.start()
        with self._cond:
            if self._closed:
                return False
            if key in self._inflight:
                return True
            try:
                self._ensure_capacity(prefer_foreground=False)
            except ThumbnailBusy:
                return False
            job = _ThumbnailJob(key=key, operation=operation, background=True)
            self._inflight[key] = job
            self._queue.appendleft(job)
            self._cond.notify()
            return True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("thumbnail scheduler is closed")

    def _ensure_capacity(self, *, prefer_foreground: bool) -> None:
        if prefer_foreground:
            while (
                len(self._queue) >= self._max_queue_size
                or len(self._inflight) >= self._max_inflight_entries
            ) and self._drop_queued_background():
                pass
        if len(self._queue) >= self._max_queue_size:
            raise ThumbnailBusy("thumbnail queue is full")
        if len(self._inflight) >= self._max_inflight_entries:
            raise ThumbnailBusy("thumbnail deduplication table is full")

    def _drop_queued_background(self) -> bool:
        for job in self._queue:
            if not job.background:
                continue
            self._remove_queued_job(job)
            self._release_inflight(job)
            self._background_dropped += 1
            logger.warning("thumbnail background work dropped for foreground admission")
            return True
        return False

    def cancel(self, key: Hashable, future: Future[T]) -> CancelState:
        with self._cond:
            job = self._inflight.get(key)
            if job is None or future not in job.waiters:
                return "none"
            job.waiters.remove(future)
            future.cancel()
            if job.waiters:
                return "none"
            if not job.started:
                self._remove_queued_job(job)
                self._release_inflight(job)
                return "queued"
            return "inflight"

    def _remove_queued_job(self, job: _ThumbnailJob) -> None:
        self._queue = deque(queued_job for queued_job in self._queue if queued_job is not job)

    def _release_inflight(self, job: _ThumbnailJob) -> None:
        if self._inflight.get(job.key) is job:
            self._inflight.pop(job.key, None)

    def _finish_job(
        self,
        job: _ThumbnailJob,
        *,
        result: Any = None,
        error: BaseException | None = None,
    ) -> None:
        with self._cond:
            waiters = tuple(job.waiters)
            job.waiters.clear()
            self._release_inflight(job)
            if job.background:
                self._active_background -= 1
                self._cond.notify_all()
        for waiter in waiters:
            if waiter.done():
                continue
            if error is None:
                waiter.set_result(result)
            else:
                waiter.set_exception(error)

    def _worker(self) -> None:
        while True:
            with self._cond:
                job = self._take_next_job()
                while job is None and not self._closed:
                    self._cond.wait()
                    job = self._take_next_job()
                if job is None:
                    return

            if not job.background and not job.waiters:
                self._finish_job(job)
                continue
            try:
                result = job.operation()
            except Exception as exc:
                self._finish_job(job, error=exc)
            else:
                self._finish_job(job, result=result)

    def _take_next_job(self) -> _ThumbnailJob | None:
        if not self._queue:
            return None
        if self._queue[-1].background:
            if self._active_background:
                return None
            self._active_background += 1
        job = self._queue.pop()
        job.started = True
        return job

    def stats(self) -> dict[str, int]:
        with self._cond:
            return {
                "workers": self._max_workers,
                "queued": len(self._queue),
                "active": sum(job.started for job in self._inflight.values()),
                "inflight": len(self._inflight),
                "waiters": sum(len(job.waiters) for job in self._inflight.values()),
                "queue_capacity": self._max_queue_size,
                "inflight_capacity": self._max_inflight_entries,
                "background_dropped": self._background_dropped,
                "active_background": self._active_background,
            }

    def diagnostics(self) -> dict[str, int]:
        stats = self.stats()
        return {
            "thumbnail_workers": stats["workers"],
            "thumbnail_active_work": stats["active"],
            "thumbnail_queued_work": stats["queued"],
            "thumbnail_inflight_entries": stats["inflight"],
            "thumbnail_waiters": stats["waiters"],
            "thumbnail_background_dropped_total": stats["background_dropped"],
            "thumbnail_active_background_work": stats["active_background"],
        }

    def close(self) -> None:
        with self._cond:
            if self._closed:
                return
            self._closed = True
            queued = tuple(self._queue)
            self._queue.clear()
            for job in queued:
                self._release_inflight(job)
            self._cond.notify_all()
            threads = tuple(self._threads)
        error = RuntimeError("thumbnail scheduler is closed")
        for job in queued:
            for waiter in tuple(job.waiters):
                if not waiter.done():
                    waiter.set_exception(error)
            job.waiters.clear()
        for thread in threads:
            thread.join()
