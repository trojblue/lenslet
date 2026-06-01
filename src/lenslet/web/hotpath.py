from __future__ import annotations

import threading

from fastapi import FastAPI

from ..storage.base import S3DiagnosticsStorage
from .models import HotpathHealthPayload, HotpathTimerPayload


class HotpathTelemetry:
    """Lightweight in-process counters/timers for hot-path visibility."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._timers: dict[str, tuple[int, float]] = {}

    def increment(self, key: str, amount: int = 1) -> None:
        if amount == 0:
            return
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + amount

    def observe_ms(self, key: str, duration_ms: float) -> None:
        if duration_ms < 0:
            duration_ms = 0
        with self._lock:
            count, total = self._timers.get(key, (0, 0.0))
            self._timers[key] = (count + 1, total + duration_ms)

    def snapshot(self, storage: S3DiagnosticsStorage | None = None) -> HotpathHealthPayload:
        with self._lock:
            counters = dict(self._counters)
            timers = {
                key: HotpathTimerPayload(
                    count=count,
                    total_ms=round(total_ms, 3),
                    avg_ms=round(total_ms / count, 3) if count else 0.0,
                )
                for key, (count, total_ms) in self._timers.items()
            }
        s3_creations = _storage_s3_client_creations(storage)
        if s3_creations is not None:
            counters["s3_client_create_total"] = s3_creations
        return HotpathHealthPayload(counters=counters, timers_ms=timers)


def build_hotpath_metrics(app: FastAPI) -> HotpathTelemetry:
    _ = app
    return HotpathTelemetry()


def _storage_s3_client_creations(storage: S3DiagnosticsStorage | None) -> int | None:
    try:
        value = storage.s3_client_creations()
    except Exception:
        return None
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
