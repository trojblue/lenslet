from __future__ import annotations

from typing import Any

from scripts.browser.overall_cleanup.support import OverallCleanupBrowserFailure

def collect_surface_bounds(page: Any, selector: str, name: str) -> dict[str, Any]:
    snapshot = page.evaluate(
        """({ selector, name }) => {
          const rectPayload = (rect) => rect ? ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          }) : null
          const el = document.querySelector(selector)
          const visualViewport = window.visualViewport ? {
            width: window.visualViewport.width,
            height: window.visualViewport.height,
            offsetLeft: window.visualViewport.offsetLeft,
            offsetTop: window.visualViewport.offsetTop,
            scale: window.visualViewport.scale,
          } : null
          const left = visualViewport ? visualViewport.offsetLeft : 0
          const top = visualViewport ? visualViewport.offsetTop : 0
          const width = visualViewport ? visualViewport.width : window.innerWidth
          const height = visualViewport ? visualViewport.height : window.innerHeight
          return {
            name,
            selector,
            rect: el ? rectPayload(el.getBoundingClientRect()) : null,
            role: el ? el.getAttribute('role') : null,
            optionCount: el ? el.querySelectorAll('[role="option"]').length : 0,
            menuItemCount: el ? el.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]').length : 0,
            bounds: {
              left,
              top,
              width,
              height,
              right: left + width,
              bottom: top + height,
              visualViewport,
            },
          }
        }""",
        {"selector": selector, "name": name},
    )
    if not isinstance(snapshot, dict):
        raise OverallCleanupBrowserFailure(f"Failed to collect surface bounds for {name}.")
    return snapshot

def assert_surface_inside_visible_bounds(snapshot: dict[str, Any]) -> None:
    name = str(snapshot.get("name", "<unknown>"))
    rect = snapshot.get("rect")
    bounds = snapshot.get("bounds")
    if not isinstance(rect, dict) or not isinstance(bounds, dict):
        raise OverallCleanupBrowserFailure(f"Missing surface bounds for {name}: {snapshot!r}.")
    tolerance = 1.5
    left = float(rect.get("left", 0))
    right = float(rect.get("right", 0))
    top = float(rect.get("top", 0))
    bottom = float(rect.get("bottom", 0))
    bounds_left = float(bounds.get("left", 0))
    bounds_right = float(bounds.get("right", 0))
    bounds_top = float(bounds.get("top", 0))
    bounds_bottom = float(bounds.get("bottom", 0))
    if left < bounds_left - tolerance or right > bounds_right + tolerance:
        raise OverallCleanupBrowserFailure(
            f"{name} overflows visible viewport horizontally: "
            f"{left:.1f}..{right:.1f} outside {bounds_left:.1f}..{bounds_right:.1f}."
        )
    if top < bounds_top - tolerance or bottom > bounds_bottom + tolerance:
        raise OverallCleanupBrowserFailure(
            f"{name} overflows visible viewport vertically: "
            f"{top:.1f}..{bottom:.1f} outside {bounds_top:.1f}..{bounds_bottom:.1f}."
        )
