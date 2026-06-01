from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from scripts.browser.overall_cleanup.grid import wait_for_visible_grid_cell_ids
from scripts.browser.overall_cleanup.support import OverallCleanupBrowserFailure
from scripts.browser.overall_cleanup.surfaces import (
    assert_surface_inside_visible_bounds,
    collect_surface_bounds,
)

def verify_hover_preview(page: Any, timeout_ms: float, media_requests: list[str]) -> dict[str, Any]:
    page.set_viewport_size({"width": 390, "height": 700})
    page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
    wait_for_visible_grid_cell_ids(page, minimum_count=2, timeout_ms=timeout_ms)
    page.evaluate(
        """() => {
          const grid = document.querySelector('[role="grid"][aria-label="Gallery"]')
          if (grid) grid.scrollTop = 0
        }"""
    )
    page.wait_for_timeout(180)

    hotspots = page.locator(".grid-item-preview-hotspot")
    if hotspots.count() < 2:
        raise OverallCleanupBrowserFailure("Expected at least two hover-preview hotspots.")

    hotspots.nth(0).hover()
    page.wait_for_timeout(80)
    page.evaluate(
        """() => {
          const grid = document.querySelector('[role="grid"][aria-label="Gallery"]')
          if (grid) grid.scrollTop = Math.min(grid.scrollTop + 240, grid.scrollHeight)
        }"""
    )
    page.wait_for_timeout(520)
    scroll_stale_count = page.locator(".grid-hover-preview").count()
    if scroll_stale_count != 0:
        raise OverallCleanupBrowserFailure(
            f"Hover preview survived scroll cancellation with {scroll_stale_count} preview(s) visible."
        )
    page.evaluate(
        """() => {
          const grid = document.querySelector('[role="grid"][aria-label="Gallery"]')
          if (grid) grid.scrollTop = 0
        }"""
    )
    page.wait_for_timeout(180)

    request_start = len(media_requests)
    hotspots.nth(0).hover()
    page.wait_for_timeout(80)
    hotspots.nth(1).hover()
    page.wait_for_timeout(80)
    page.mouse.move(4, 4)
    page.wait_for_timeout(520)
    stale_count = page.locator(".grid-hover-preview").count()
    if stale_count != 0:
        raise OverallCleanupBrowserFailure(f"Rapid hover leave left {stale_count} stale preview(s) visible.")

    hotspots.nth(1).hover()
    preview_selector = ".grid-hover-preview"
    page.locator(preview_selector).first.wait_for(state="visible", timeout=timeout_ms)
    preview_surface = collect_surface_bounds(page, preview_selector, "hover-preview")
    assert_surface_inside_visible_bounds(preview_surface)
    preview_path = page.locator(preview_selector).first.get_attribute("data-preview-path")
    page.mouse.move(4, 4)
    page.locator(preview_selector).first.wait_for(state="hidden", timeout=timeout_ms)

    hover_requests = media_requests[request_start:]
    thumb_requests = [url for url in hover_requests if urlparse(url).path.endswith("/thumb")]
    file_requests = [url for url in hover_requests if urlparse(url).path.endswith("/file")]
    if not file_requests:
        raise OverallCleanupBrowserFailure(f"Hover preview did not request /file: {hover_requests!r}.")

    return {
        "preview_path": preview_path,
        "surface": preview_surface,
        "thumb_request_count": len(thumb_requests),
        "file_request_count": len(file_requests),
        "scroll_cancel_preview_count": scroll_stale_count,
        "request_count": len(hover_requests),
    }
