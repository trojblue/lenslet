from __future__ import annotations

import subprocess  # nosec B404 - used only for subprocess exception types.

try:
    from playwright.sync_api import Error as PlaywrightError
except ImportError:  # pragma: no cover - handled by import_playwright at runtime
    PlaywrightError = RuntimeError


class OverallCleanupBrowserFailure(RuntimeError):
    """Raised when the browser cleanup evidence path fails."""


_SCREENSHOT_CAPTURE_ERRORS = (OSError, PlaywrightError, ValueError)
_BROWSER_SCENARIO_ERRORS = (
    AssertionError,
    OSError,
    PlaywrightError,
    RuntimeError,
    TypeError,
    ValueError,
)
_SCRIPT_RUN_ERRORS = (
    OSError,
    PlaywrightError,
    RuntimeError,
    subprocess.SubprocessError,
    TimeoutError,
    TypeError,
    ValueError,
)
