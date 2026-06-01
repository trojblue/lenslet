from __future__ import annotations

from typing import Any

from scripts.browser.overall_cleanup.grid import wait_for_visible_grid_cell_ids
from scripts.browser.overall_cleanup.support import OverallCleanupBrowserFailure
from scripts.browser.overall_cleanup.transforms import wait_for_image_ready

def verify_browse_ctrl_wheel_and_slider(page: Any, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 1024, "height": 640})
    page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
    slider = page.get_by_role("slider", name="Thumbnail size").first
    slider.wait_for(state="visible", timeout=timeout_ms)
    before_value = slider.input_value()
    page.evaluate(
        """() => {
          const grid = document.querySelector('[role="grid"][aria-label="Gallery"]')
          if (!grid) throw new Error('Missing gallery grid for Ctrl+wheel check')
          grid.dispatchEvent(new WheelEvent('wheel', {
            bubbles: true,
            cancelable: true,
            ctrlKey: true,
            deltaY: -480,
          }))
        }"""
    )
    page.wait_for_timeout(160)
    after_ctrl_wheel_value = slider.input_value()
    if after_ctrl_wheel_value != before_value:
        raise OverallCleanupBrowserFailure(
            f"Browse Ctrl+wheel mutated thumbnail size: {before_value!r} -> {after_ctrl_wheel_value!r}."
        )

    explicit_value = "280" if before_value != "280" else "220"
    slider.evaluate(
        """(element, value) => {
          element.value = value
          element.dispatchEvent(new Event('input', { bubbles: true }))
          element.dispatchEvent(new Event('change', { bubbles: true }))
        }""",
        explicit_value,
    )
    page.wait_for_function(
        """({ selector, value }) => {
          const slider = document.querySelector(selector)
          return slider instanceof HTMLInputElement && slider.value === value
        }""",
        arg={"selector": 'input[aria-label="Thumbnail size"]', "value": explicit_value},
        timeout=timeout_ms,
    )
    return {
        "initial_size": before_value,
        "after_ctrl_wheel_size": after_ctrl_wheel_value,
        "explicit_slider_size": explicit_value,
    }

def verify_mobile_viewer_navigation(page: Any, timeout_ms: float) -> dict[str, Any]:
    page.goto(page.url or "about:blank")
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
    first_cell_id = wait_for_visible_grid_cell_ids(page, minimum_count=2, timeout_ms=timeout_ms)[0]
    first_cell_selector = f"[id='{first_cell_id}']"
    page.locator(first_cell_selector).first.evaluate("(element) => element.focus()")
    page.keyboard.press("Enter")
    dialog_selector = '[role="dialog"][aria-label="Image viewer"]'
    image_selector = f"{dialog_selector} img[data-viewer-image='full']"
    page.locator(dialog_selector).first.wait_for(state="visible", timeout=timeout_ms)
    wait_for_image_ready(page, image_selector, timeout_ms)
    nav_display = page.locator(".viewer-mobile-nav").first.evaluate(
        "(element) => window.getComputedStyle(element).display"
    )
    if nav_display == "none":
        raise OverallCleanupBrowserFailure("Mobile viewer navigation is not visible at 390x844.")
    before_path = page.locator(dialog_selector).first.get_attribute("data-current-path")
    next_button = page.get_by_role("button", name="Next image").first
    if next_button.is_disabled():
        raise OverallCleanupBrowserFailure("Mobile viewer Next button is unexpectedly disabled.")
    next_button.click()
    page.wait_for_function(
        """({ selector, beforePath }) => {
          const dialog = document.querySelector(selector)
          return dialog && dialog.getAttribute('data-current-path') !== beforePath
        }""",
        arg={"selector": dialog_selector, "beforePath": before_path},
        timeout=timeout_ms,
    )
    after_path = page.locator(dialog_selector).first.get_attribute("data-current-path")
    page.keyboard.press("Escape")
    page.locator(dialog_selector).first.wait_for(state="hidden", timeout=timeout_ms)
    return {"display": nav_display, "before_path": before_path, "after_path": after_path}

def verify_coarse_pointer_actions(page: Any, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 900, "height": 700})
    page.goto(page.url or "about:blank")
    page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
    snapshot = page.evaluate(
        """() => {
          const read = (selector) => {
            const element = document.querySelector(selector)
            if (!(element instanceof HTMLElement)) return null
            const rect = element.getBoundingClientRect()
            const style = window.getComputedStyle(element)
            return {
              selector,
              opacity: style.opacity,
              width: rect.width,
              height: rect.height,
              visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
            }
          }
          return {
            coarse: window.matchMedia('(pointer: coarse)').matches,
            gridAction: read('.grid-item-action-btn'),
            folderAction: read('.tree-row-action-btn'),
          }
        }"""
    )
    if not isinstance(snapshot, dict) or not snapshot.get("coarse"):
        raise OverallCleanupBrowserFailure(f"Coarse pointer emulation did not activate: {snapshot!r}.")
    for key in ("gridAction", "folderAction"):
        entry = snapshot.get(key)
        if not isinstance(entry, dict) or not entry.get("visible") or float(entry.get("opacity", 0)) < 0.95:
            raise OverallCleanupBrowserFailure(f"{key} is not visible under coarse pointer: {snapshot!r}.")
    return snapshot

def verify_reduced_motion(page: Any, timeout_ms: float) -> dict[str, Any]:
    page.emulate_media(reduced_motion="reduce")
    page.goto(page.url or "about:blank")
    page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
    snapshot = page.evaluate(
        """() => {
          const target = document.querySelector('.btn, .grid-item-action-btn') || document.body
          const style = window.getComputedStyle(target)
          const animated = Array.from(document.querySelectorAll('*')).filter((element) => {
            const computed = window.getComputedStyle(element)
            return computed.animationName !== 'none' || computed.transitionDuration !== '0s'
          }).slice(0, 5).map((element) => ({
            tag: element.tagName,
            className: element instanceof HTMLElement ? element.className : '',
            animationName: window.getComputedStyle(element).animationName,
            transitionDuration: window.getComputedStyle(element).transitionDuration,
          }))
          return {
            reduced: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
            probeTransitionDuration: style.transitionDuration,
            probeAnimationName: style.animationName,
            animated,
          }
        }"""
    )
    if not isinstance(snapshot, dict) or not snapshot.get("reduced"):
        raise OverallCleanupBrowserFailure(f"Reduced-motion emulation did not activate: {snapshot!r}.")
    if snapshot.get("animated"):
        raise OverallCleanupBrowserFailure(f"Reduced-motion CSS left active animation/transition styles: {snapshot!r}.")
    return snapshot
