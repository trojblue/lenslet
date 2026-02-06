from __future__ import annotations

from collections import deque
from concurrent.futures import Future
from threading import Condition, Thread
from typing import Callable, Deque, Generic, Literal, TypeVar


T = TypeVar("T")
CancelState = Literal["queued", "inflight", "none"]


class ThumbnailScheduler(Generic[T]):
    """LIFO thumbnail worker pool with in-flight deduplication."""

    def __init__(self, max_workers: int = 4, name: str = "lenslet-thumb") -> None:
        self._max_workers = max(1, max_workers)
        self._queue: Deque[tuple[str, Callable[[], T], Future[T]]] = deque()
        self._inflight: dict[str, Future[T]] = {}
        self._cond = Condition()
        self._closed = False
        self._threads = [
            Thread(target=self._worker, name=f"{name}-{idx}", daemon=True)
            for idx in range(self._max_workers)
        ]
        for thread in self._threads:
            thread.start()

    def submit(self, key: str, fn: Callable[[], T]) -> Future[T]:
        with self._cond:
            existing = self._inflight.get(key)
            if existing is not None:
                return existing
            fut: Future[T] = Future()
            self._inflight[key] = fut
            self._queue.append((key, fn, fut))
            self._cond.notify()
            return fut

    def _future_in_queue(self, fut: Future[T]) -> bool:
        return any(queued_fut is fut for _, _, queued_fut in self._queue)

    def _remove_queued_future(self, fut: Future[T]) -> None:
        self._queue = deque(
            (queued_key, queued_fn, queued_fut)
            for queued_key, queued_fn, queued_fut in self._queue
            if queued_fut is not fut
        )

    def _release_inflight(self, key: str, fut: Future[T]) -> None:
        if self._inflight.get(key) is fut:
            self._inflight.pop(key, None)

    def cancel(self, key: str, fut: Future[T]) -> CancelState:
        with self._cond:
            if self._inflight.get(key) is not fut:
                return "none"
            was_queued = self._future_in_queue(fut)
            if not fut.cancel():
                return "none"
            if was_queued:
                self._remove_queued_future(fut)
            self._release_inflight(key, fut)
            return "queued" if was_queued else "inflight"

    def _worker(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                key, fn, fut = self._queue.pop()

            if fut.cancelled():
                with self._cond:
                    self._release_inflight(key, fut)
                continue

            try:
                result = fn()
            except Exception as exc:
                if not fut.cancelled():
                    fut.set_exception(exc)
            else:
                if not fut.cancelled():
                    fut.set_result(result)
            finally:
                with self._cond:
                    self._release_inflight(key, fut)

    def stats(self) -> dict[str, int]:
        with self._cond:
            return {
                "queued": len(self._queue),
                "inflight": len(self._inflight),
            }

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
