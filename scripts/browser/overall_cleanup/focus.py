from __future__ import annotations

from typing import Any

from scripts.browser.overall_cleanup.support import OverallCleanupBrowserFailure

def collect_active_element_snapshot(page: Any) -> dict[str, Any] | None:
    return page.evaluate(
        """() => {
          const el = document.activeElement
          return el ? {
            tag: el.tagName,
            role: el.getAttribute('role'),
            label: el.getAttribute('aria-label'),
            id: el.id,
            text: (el.textContent || '').trim().slice(0, 80),
          } : null
        }"""
    )

def assert_focus_inside(page: Any, selector: str, name: str) -> None:
    try:
        page.wait_for_function(
            """(selector) => {
          const container = document.querySelector(selector)
          return Boolean(container && document.activeElement && container.contains(document.activeElement))
        }""",
            arg=selector,
            timeout=1000,
        )
    except Exception as exc:
        active = collect_active_element_snapshot(page)
        raise OverallCleanupBrowserFailure(f"Focus escaped {name}; active element was {active!r}.") from exc

def assert_focus_restored(page: Any, selector: str, name: str) -> None:
    restored = page.evaluate(
        """(selector) => document.activeElement === document.querySelector(selector)""",
        selector,
    )
    if not restored:
        active = collect_active_element_snapshot(page)
        raise OverallCleanupBrowserFailure(f"Focus did not restore to {name}; active element was {active!r}.")

def assert_focused_element_has_visible_outline(page: Any, name: str) -> dict[str, Any]:
    snapshot = page.evaluate(
        """() => {
          const el = document.activeElement
          if (!(el instanceof HTMLElement)) return null
          const style = window.getComputedStyle(el)
          return {
            tag: el.tagName,
            text: (el.textContent || '').trim().slice(0, 80),
            label: el.getAttribute('aria-label'),
            outlineStyle: style.outlineStyle,
            outlineWidth: style.outlineWidth,
            boxShadow: style.boxShadow,
          }
        }"""
    )
    if not isinstance(snapshot, dict):
        raise OverallCleanupBrowserFailure(f"Missing focused element for {name}.")
    outline_style = str(snapshot.get("outlineStyle") or "")
    outline_width = str(snapshot.get("outlineWidth") or "")
    box_shadow = str(snapshot.get("boxShadow") or "")
    if (outline_style == "none" or outline_width in {"", "0px"}) and box_shadow == "none":
        raise OverallCleanupBrowserFailure(f"Focused control has no visible focus style for {name}: {snapshot!r}.")
    return snapshot

def assert_useful_image_alt(page: Any, selector: str, name: str, generic_values: set[str]) -> str:
    alt = page.locator(selector).first.get_attribute("alt")
    if alt is None:
        raise OverallCleanupBrowserFailure(f"{name} image is missing alt text.")
    normalized = alt.strip()
    if not normalized or normalized in generic_values:
        raise OverallCleanupBrowserFailure(f"{name} image still has generic alt text: {alt!r}.")
    return normalized
