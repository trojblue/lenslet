from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CacheFailure:
    cache_name: str
    operation: str
    target: str | None
    reason: str


class BestEffortCacheMixin:
    _cache_name: str
    _last_failure: CacheFailure | None

    @property
    def last_failure(self) -> CacheFailure | None:
        return self._last_failure

    def _record_failure(
        self,
        operation: str,
        *,
        target: Path | str | None = None,
        detail: str | None = None,
        exc: BaseException | None = None,
    ) -> None:
        if detail is not None:
            reason = detail
        elif exc is not None and str(exc):
            reason = f"{type(exc).__name__}: {exc}"
        elif exc is not None:
            reason = type(exc).__name__
        else:
            reason = "unknown error"
        target_text = str(target) if target is not None else None
        self._last_failure = CacheFailure(
            cache_name=self._cache_name,
            operation=operation,
            target=target_text,
            reason=reason,
        )
        if target_text is None:
            logger.warning("%s cache %s failed: %s", self._cache_name, operation, reason)
            return
        logger.warning(
            "%s cache %s failed for %s: %s",
            self._cache_name,
            operation,
            target_text,
            reason,
        )
