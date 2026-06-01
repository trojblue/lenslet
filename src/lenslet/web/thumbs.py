from __future__ import annotations

from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass, field
from threading import Condition, Thread
from typing import Callable, Deque, Generic, Literal, TypeVar


T = TypeVar("T")
CancelState = Literal["queued", "inflight", "none"]


@dataclass
class _ThumbnailJob(Generic[T]):
    key: str
    fn: Callable[[], T]
    waiters: set[Future[T]] = field(default_factory=set)


class ThumbnailScheduler(Generic[T]):
    """LIFO thumbnail worker pool with in-flight deduplication."""

    def __init__(self, max_workers: int = 4, name: str = "lenslet-thumb") -> None:
        self._max_workers = max(1, max_workers)
        self._name = name
        self._queue: Deque[_ThumbnailJob[T]] = deque()
        self._inflight: dict[str, _ThumbnailJob[T]] = {}
        self._cond = Condition()
        self._closed = False
        self._started = False
        self._threads: list[Thread] = []

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

    def submit(self, key: str, fn: Callable[[], T]) -> Future[T]:
        self.start()
        with self._cond:
            if self._closed:
                raise RuntimeError("thumbnail scheduler is closed")
            waiter: Future[T] = Future()
            job = self._inflight.get(key)
            if job is not None:
                job.waiters.add(waiter)
                return waiter
            job = _ThumbnailJob(key=key, fn=fn)
            job.waiters.add(waiter)
            self._inflight[key] = job
            self._queue.append(job)
            self._cond.notify()
            return waiter

    def _job_in_queue(self, job: _ThumbnailJob[T]) -> bool:
        return any(queued_job is job for queued_job in self._queue)

    def _remove_queued_job(self, job: _ThumbnailJob[T]) -> None:
        self._queue = deque(queued_job for queued_job in self._queue if queued_job is not job)

    def _release_inflight(self, key: str, job: _ThumbnailJob[T]) -> None:
        if self._inflight.get(key) is job:
            self._inflight.pop(key, None)

    def cancel(self, key: str, fut: Future[T]) -> CancelState:
        with self._cond:
            job = self._inflight.get(key)
            if job is None or fut not in job.waiters:
                return "none"
            job.waiters.remove(fut)
            fut.cancel()
            if job.waiters:
                return "none"
            was_queued = self._job_in_queue(job)
            if was_queued:
                self._remove_queued_job(job)
                self._release_inflight(key, job)
            return "queued" if was_queued else "inflight"

    def _take_waiters(self, job: _ThumbnailJob[T]) -> tuple[Future[T], ...]:
        with self._cond:
            waiters = tuple(job.waiters)
            job.waiters.clear()
            self._release_inflight(job.key, job)
        return waiters

    def _finish_job_success(self, job: _ThumbnailJob[T], result: T) -> None:
        for waiter in self._take_waiters(job):
            if not waiter.done():
                waiter.set_result(result)

    def _finish_job_error(self, job: _ThumbnailJob[T], exc: Exception) -> None:
        for waiter in self._take_waiters(job):
            if not waiter.done():
                waiter.set_exception(exc)

    def _worker(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                job = self._queue.pop()

            if not job.waiters:
                with self._cond:
                    self._release_inflight(job.key, job)
                continue

            try:
                result = job.fn()
            except Exception as exc:
                self._finish_job_error(job, exc)
            else:
                self._finish_job_success(job, result)

    def stats(self) -> dict[str, int]:
        with self._cond:
            return {
                "queued": len(self._queue),
                "inflight": len(self._inflight),
                "waiters": sum(len(job.waiters) for job in self._inflight.values()),
            }

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
