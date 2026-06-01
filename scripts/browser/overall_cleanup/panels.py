from __future__ import annotations

import time
from typing import Any

from scripts.browser.overall_cleanup.support import OverallCleanupBrowserFailure

def set_right_panel_open(page: Any, open_state: bool, timeout_ms: float) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        is_open = page.locator(".app-right-panel").count() > 0
        if is_open == open_state:
            return
        toggle_button = page.locator("button[aria-label='Toggle right panel']").first
        if toggle_button.count() == 0:
            page.wait_for_timeout(120)
            continue
        toggle_button.click()
        page.wait_for_timeout(180)
    raise OverallCleanupBrowserFailure(
        f"Timed out setting right panel open state to {open_state}; "
        f"current panel count={page.locator('.app-right-panel').count()}."
    )
