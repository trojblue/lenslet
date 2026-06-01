from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True, slots=True)
class DegradedFeature:
    feature: str
    detail: str
    startup_continues: bool


def report_degraded_feature(
    feature: str,
    exc: BaseException | None = None,
    *,
    detail: str | None = None,
    startup_continues: bool = True,
    impact: str | None = None,
    stream: TextIO | None = None,
) -> DegradedFeature:
    reason = detail if detail is not None else str(exc) if exc is not None else "unavailable"
    report = DegradedFeature(
        feature=feature,
        detail=reason,
        startup_continues=startup_continues,
    )
    outcome = impact or ("startup continues without it" if startup_continues else "startup cannot continue")
    print(f"[lenslet] Warning: {feature} degraded: {reason}; {outcome}.", file=stream or sys.stderr)
    return report
