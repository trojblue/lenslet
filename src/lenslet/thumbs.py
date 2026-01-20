from __future__ import annotations

from collections import deque
from concurrent.futures import Future
from threading import Condition, Thread
from typing import Callable, Deque, Generic, TypeVar


T = TypeVar("T")


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

    def cancel(self, key: str, fut: Future[T]) -> None:
        if fut.cancel():
            with self._cond:
                if self._inflight.get(key) is fut:
                    self._inflight.pop(key, None)

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
                    if self._inflight.get(key) is fut:
                        self._inflight.pop(key, None)
                continue

            try:
                result = fn()
            except Exception as exc:
                fut.set_exception(exc)
            else:
                fut.set_result(result)
            finally:
                with self._cond:
                    if self._inflight.get(key) is fut:
                        self._inflight.pop(key, None)

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
