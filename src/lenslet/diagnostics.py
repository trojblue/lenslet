from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator


@dataclass(slots=True)
class RequestPhaseTimings:
    """Request-local monotonic phase measurements shared across app layers.

    Repeated phase names are summed. Different phases may overlap when nested.
    """

    started_at: float = field(default_factory=time.perf_counter)
    _handler_started_at: float | None = None
    _durations_ms: dict[str, float] = field(default_factory=dict)
    _intervals: list[tuple[float, float]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _finalized: dict[str, float] | None = None

    def mark_handler_started(self) -> None:
        now = time.perf_counter()
        with self._lock:
            if self._handler_started_at is None:
                self._handler_started_at = now

    def observe(self, phase: str, started_at: float, finished_at: float) -> None:
        duration_ms = max(0.0, (finished_at - started_at) * 1000.0)
        with self._lock:
            self._durations_ms[phase] = self._durations_ms.get(phase, 0.0) + duration_ms
            self._intervals.append((started_at, finished_at))

    def finalize(self) -> dict[str, float]:
        finished_at = time.perf_counter()
        with self._lock:
            if self._finalized is not None:
                return dict(self._finalized)
            timings = dict(self._durations_ms)
            handler_started_at = self._handler_started_at
            if handler_started_at is not None:
                timings["queue"] = max(
                    0.0,
                    (handler_started_at - self.started_at) * 1000.0,
                )
                covered = _covered_seconds(
                    self._intervals,
                    lower=handler_started_at,
                    upper=finished_at,
                )
                # Response-model serialization happens after the route returns. The
                # uncovered residual also includes framework overhead before headers.
                timings["serialize"] = max(
                    0.0,
                    ((finished_at - handler_started_at) - covered) * 1000.0,
                )
            self._finalized = timings
            return dict(timings)


_CURRENT_REQUEST_TIMINGS: ContextVar[RequestPhaseTimings | None] = ContextVar(
    "lenslet_request_phase_timings",
    default=None,
)


@contextmanager
def bind_request_phase_timings(timings: RequestPhaseTimings) -> Iterator[None]:
    token = _CURRENT_REQUEST_TIMINGS.set(timings)
    try:
        yield
    finally:
        _CURRENT_REQUEST_TIMINGS.reset(token)


@contextmanager
def request_phase(name: str) -> Iterator[None]:
    timings = _CURRENT_REQUEST_TIMINGS.get()
    if timings is None:
        yield
        return
    started_at = time.perf_counter()
    try:
        yield
    finally:
        timings.observe(name, started_at, time.perf_counter())


def mark_request_handler_started() -> None:
    timings = _CURRENT_REQUEST_TIMINGS.get()
    if timings is not None:
        timings.mark_handler_started()


def _covered_seconds(
    intervals: list[tuple[float, float]],
    *,
    lower: float,
    upper: float,
) -> float:
    bounded = sorted(
        (max(lower, start), min(upper, end))
        for start, end in intervals
        if end > lower and start < upper
    )
    if not bounded:
        return 0.0
    covered = 0.0
    current_start, current_end = bounded[0]
    for start, end in bounded[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        covered += max(0.0, current_end - current_start)
        current_start, current_end = start, end
    return covered + max(0.0, current_end - current_start)
