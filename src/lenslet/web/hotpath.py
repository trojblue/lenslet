from __future__ import annotations

import asyncio
import threading
from typing import Literal

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..diagnostics import RequestPhaseTimings, bind_request_phase_timings
from ..storage.base import S3DiagnosticsStorage
from .models import HotpathHealthPayload, HotpathTimerPayload


AnalysisEvent = Literal["started", "completed", "joined", "superseded", "cancelled"]
_SERVER_TIMING_ORDER = (
    "queue",
    "analysis",
    "ordering",
    "facet",
    "projection",
    "serialize",
    "thumbnail",
    "mutation",
    "writer",
)


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

    def record_analysis(self, event: AnalysisEvent) -> None:
        self.increment(f"analysis_{event}_total")

    def observe_request_timings(self, timings_ms: dict[str, float]) -> None:
        for phase, duration_ms in timings_ms.items():
            self.observe_ms(f"request_phase_{phase}", duration_ms)

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


class HotpathTimingMiddleware:
    def __init__(self, app: ASGIApp, telemetry: HotpathTelemetry) -> None:
        self.app = app
        self.telemetry = telemetry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        timings = RequestPhaseTimings()
        terminal_outcome: Literal["completed", "failed", "abandoned"] | None = None

        def record_terminal_outcome(outcome: Literal["completed", "failed", "abandoned"]) -> None:
            nonlocal terminal_outcome
            if terminal_outcome is not None:
                return
            terminal_outcome = outcome
            self.telemetry.increment(f"http_request_{outcome}_total")

        async def send_with_timing(message: Message) -> None:
            if message["type"] == "http.response.start":
                measured = timings.finalize()
                if measured:
                    headers = MutableHeaders(scope=message)
                    headers.append("Server-Timing", _server_timing_header(measured))
                    self.telemetry.observe_request_timings(measured)
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                record_terminal_outcome("completed")

        try:
            with bind_request_phase_timings(timings):
                await self.app(scope, receive, send_with_timing)
        except asyncio.CancelledError:
            record_terminal_outcome("abandoned")
            raise
        except Exception:
            record_terminal_outcome("failed")
            raise
        finally:
            record_terminal_outcome("abandoned")


def install_hotpath_timing_middleware(
    app: FastAPI,
    telemetry: HotpathTelemetry,
) -> None:
    app.add_middleware(HotpathTimingMiddleware, telemetry=telemetry)


def _server_timing_header(timings_ms: dict[str, float]) -> str:
    ordered = [phase for phase in _SERVER_TIMING_ORDER if phase in timings_ms]
    ordered.extend(sorted(set(timings_ms) - set(ordered)))
    return ", ".join(f"{phase};dur={timings_ms[phase]:.3f}" for phase in ordered)


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
