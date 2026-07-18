from __future__ import annotations

from typing import Any

from scripts.browser.overall_cleanup.grid import wait_for_visible_grid_cell_ids
from scripts.browser.overall_cleanup.support import OverallCleanupBrowserFailure
from scripts.browser.overall_cleanup.transforms import wait_for_image_ready

def verify_browse_ctrl_wheel_and_slider(page: Any, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 1440, "height": 920})
    grid = page.get_by_role("grid", name="Gallery")
    grid.wait_for(state="visible", timeout=timeout_ms)
    slider = page.get_by_role("slider", name="Thumbnail size").first
    slider.wait_for(state="visible", timeout=timeout_ms)
    before_value = slider.input_value()
    before_anchor = wait_for_visible_grid_cell_ids(page, minimum_count=1, timeout_ms=timeout_ms)[0]
    before_viewport = page.evaluate(
        """() => {
          const rect = document.querySelector('.app-shell')?.getBoundingClientRect()
          return {
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            visualScale: window.visualViewport?.scale ?? 1,
            appWidth: rect?.width ?? 0,
            appHeight: rect?.height ?? 0,
          }
        }"""
    )
    grid_box = grid.bounding_box()
    if grid_box is None:
        raise OverallCleanupBrowserFailure("Gallery has no bounding box for Ctrl+wheel check.")
    page.mouse.move(
        float(grid_box["x"]) + float(grid_box["width"]) / 2,
        float(grid_box["y"]) + float(grid_box["height"]) / 2,
    )
    page.keyboard.down("Control")
    try:
        page.mouse.wheel(0, -120)
    finally:
        page.keyboard.up("Control")
    page.wait_for_function(
        """before => {
          const slider = document.querySelector('input[aria-label="Thumbnail size"]')
          return slider instanceof HTMLInputElement && slider.value !== before
        }""",
        arg=before_value,
        timeout=timeout_ms,
    )
    after_ctrl_wheel_value = slider.input_value()
    if int(after_ctrl_wheel_value) <= int(before_value):
        raise OverallCleanupBrowserFailure(
            f"Browse Ctrl+wheel did not increase thumbnail size: {before_value!r} -> {after_ctrl_wheel_value!r}."
        )
    after_ctrl_anchor = wait_for_visible_grid_cell_ids(page, minimum_count=1, timeout_ms=timeout_ms)[0]
    if after_ctrl_anchor != before_anchor:
        raise OverallCleanupBrowserFailure(
            f"Browse Ctrl+wheel moved the top-visible path: {before_anchor!r} -> {after_ctrl_anchor!r}."
        )
    after_viewport = page.evaluate(
        """() => {
          const rect = document.querySelector('.app-shell')?.getBoundingClientRect()
          return {
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            visualScale: window.visualViewport?.scale ?? 1,
            appWidth: rect?.width ?? 0,
            appHeight: rect?.height ?? 0,
          }
        }"""
    )
    for key in ("innerWidth", "innerHeight", "visualScale", "appWidth", "appHeight"):
        if abs(float(after_viewport[key]) - float(before_viewport[key])) > 1.0:
            raise OverallCleanupBrowserFailure(
                f"Browse Ctrl+wheel changed viewport geometry for {key}: "
                f"{before_viewport!r} -> {after_viewport!r}."
            )

    meta_result = grid.evaluate(
        """element => {
          const event = new WheelEvent('wheel', {
            bubbles: true,
            cancelable: true,
            metaKey: true,
            deltaY: 120,
          })
          element.dispatchEvent(event)
          return { defaultPrevented: event.defaultPrevented }
        }"""
    )
    if not meta_result.get("defaultPrevented"):
        raise OverallCleanupBrowserFailure(f"Browse Meta+wheel was not synchronously prevented: {meta_result!r}.")
    page.wait_for_function(
        """before => {
          const slider = document.querySelector('input[aria-label="Thumbnail size"]')
          return slider instanceof HTMLInputElement && slider.value !== before
        }""",
        arg=after_ctrl_wheel_value,
        timeout=timeout_ms,
    )
    after_meta_wheel_value = slider.input_value()
    if int(after_meta_wheel_value) >= int(after_ctrl_wheel_value):
        raise OverallCleanupBrowserFailure(
            "Browse Meta+wheel did not decrease thumbnail size: "
            f"{after_ctrl_wheel_value!r} -> {after_meta_wheel_value!r}."
        )

    explicit_value = "500"
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
    ordinary_default_prevented = grid.evaluate(
        """element => {
          const event = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: 120 })
          element.dispatchEvent(event)
          return event.defaultPrevented
        }"""
    )
    if ordinary_default_prevented:
        raise OverallCleanupBrowserFailure("Browse ordinary wheel was unexpectedly prevented.")
    grid.evaluate("element => { element.scrollTop = 0 }")
    page.mouse.move(
        float(grid_box["x"]) + float(grid_box["width"]) / 2,
        float(grid_box["y"]) + float(grid_box["height"]) / 2,
    )
    page.mouse.wheel(0, 480)
    page.wait_for_function(
        """() => (document.querySelector('[role="grid"][aria-label="Gallery"]')?.scrollTop ?? 0) > 0""",
        timeout=timeout_ms,
    )
    ordinary_scroll_top = float(grid.evaluate("element => element.scrollTop"))
    return {
        "initial_size": before_value,
        "after_ctrl_wheel_size": after_ctrl_wheel_value,
        "after_meta_wheel_size": after_meta_wheel_value,
        "explicit_slider_size": explicit_value,
        "ordinary_scroll_top": ordinary_scroll_top,
        "top_anchor_before": before_anchor,
        "top_anchor_after_ctrl_wheel": after_ctrl_anchor,
        "viewport_before": before_viewport,
        "viewport_after": after_viewport,
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
