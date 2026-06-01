from __future__ import annotations

try:
    from playwright.sync_api import Error as PlaywrightError
except ImportError:  # pragma: no cover - handled by import_playwright at runtime
    PlaywrightError = RuntimeError


class ResponsiveGeometryFailure(RuntimeError):
    """Raised when a responsive geometry invariant fails."""


_PLAYWRIGHT_OPERATION_ERRORS = (PlaywrightError, RuntimeError, ValueError)
_SNAPSHOT_CAPTURE_ERRORS = (PlaywrightError, RuntimeError, TypeError, ValueError)
