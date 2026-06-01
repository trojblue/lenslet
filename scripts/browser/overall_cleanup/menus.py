from __future__ import annotations

from typing import Any

from scripts.browser.overall_cleanup.support import OverallCleanupBrowserFailure
from scripts.browser.overall_cleanup.surfaces import (
    assert_surface_inside_visible_bounds,
    collect_surface_bounds,
)

def verify_menu_bounds_and_roles(page: Any, timeout_ms: float) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    page.set_viewport_size({"width": 1024, "height": 480})
    page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)

    sort_trigger = page.get_by_role("button", name="Sort and layout").first
    sort_trigger.wait_for(state="visible", timeout=timeout_ms)
    sort_trigger.click()
    sort_selector = '.dropdown-panel[role="listbox"][aria-label="Sort and layout"]'
    page.locator(sort_selector).first.wait_for(state="visible", timeout=timeout_ms)
    sort_surface = collect_surface_bounds(page, sort_selector, "sort-layout-menu")
    assert_surface_inside_visible_bounds(sort_surface)
    if sort_surface.get("optionCount", 0) <= 0 or sort_surface.get("menuItemCount", 0) != 0:
        raise OverallCleanupBrowserFailure(f"Sort dropdown role mismatch: {sort_surface!r}.")
    evidence.append(sort_surface)
    page.keyboard.press("Escape")
    page.locator(sort_selector).first.wait_for(state="hidden", timeout=timeout_ms)

    filter_trigger = page.locator('button[title="Filters"]').first
    filter_trigger.wait_for(state="visible", timeout=timeout_ms)
    filter_trigger.click()
    filter_selector = '[role="dialog"][aria-label="Filters"]'
    page.locator(filter_selector).first.wait_for(state="visible", timeout=timeout_ms)
    filter_surface = collect_surface_bounds(page, filter_selector, "filter-dialog-menu")
    assert_surface_inside_visible_bounds(filter_surface)
    evidence.append(filter_surface)
    page.keyboard.press("Escape")
    page.locator(filter_selector).first.wait_for(state="hidden", timeout=timeout_ms)

    page.set_viewport_size({"width": 1440, "height": 920})
    page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
    theme_trigger = page.locator('button[aria-haspopup="menu"][aria-label^="Theme settings"]').first
    theme_trigger.wait_for(state="visible", timeout=timeout_ms)
    theme_trigger.click()
    theme_selector = '[role="menu"][aria-label="Theme settings"]'
    page.locator(theme_selector).first.wait_for(state="visible", timeout=timeout_ms)
    theme_surface = collect_surface_bounds(page, theme_selector, "theme-settings-menu")
    assert_surface_inside_visible_bounds(theme_surface)
    if theme_surface.get("menuItemCount", 0) <= 0:
        raise OverallCleanupBrowserFailure(f"Theme menu has no menu items: {theme_surface!r}.")
    evidence.append(theme_surface)
    page.keyboard.press("Escape")
    page.locator(theme_selector).first.wait_for(state="hidden", timeout=timeout_ms)

    page.set_viewport_size({"width": 1024, "height": 480})
    page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
    page.evaluate(
        """() => {
          const cell = document.querySelector('[role="gridcell"][id^="cell-"]')
          if (!cell) throw new Error('No grid cell for context menu evidence')
          cell.dispatchEvent(new MouseEvent('contextmenu', {
            bubbles: true,
            cancelable: true,
            clientX: window.innerWidth - 4,
            clientY: window.innerHeight - 4,
          }))
        }"""
    )
    context_selector = '.dropdown-panel[role="menu"]'
    page.locator(context_selector).first.wait_for(state="visible", timeout=timeout_ms)
    context_surface = collect_surface_bounds(page, context_selector, "grid-context-menu")
    assert_surface_inside_visible_bounds(context_surface)
    if context_surface.get("menuItemCount", 0) <= 0:
        raise OverallCleanupBrowserFailure(f"Context menu has no menu items: {context_surface!r}.")
    evidence.append(context_surface)
    page.keyboard.press("Escape")
    page.locator(context_selector).first.wait_for(state="hidden", timeout=timeout_ms)
    return evidence
