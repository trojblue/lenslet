"""Toolbar jitter probe scenario."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.browser.gui_jitter.shared import ProbeResult, state_delta, wait_for_grid
from scripts.smoke_harness import SmokeFailure, import_playwright
from scripts.browser.viewer_probe.page import wait_for_back_button


@dataclass(slots=True)
class ToolbarSnapshots:
    desktop_browse: dict[str, Any]
    desktop_viewer: dict[str, Any]
    desktop_restored: dict[str, Any]
    narrow_closed: dict[str, Any]
    narrow_open: dict[str, Any]
    narrow_restored: dict[str, Any]


def snapshot_toolbar(page: Any) -> dict[str, Any]:
    snapshot = page.evaluate(
        """() => {
          const shell = document.querySelector('.toolbar-shell');
          if (!shell) return null;
          const appShell = document.querySelector('.app-shell');
          const slotNames = ['back', 'refresh', 'nav', 'upload', 'search-desktop', 'search-toggle', 'search-row'];
          const controlNames = ['back', 'refresh', 'upload', 'search-desktop', 'search-toggle', 'search-mobile'];
          const anchors = {};
          for (const slotName of slotNames) {
            const node = document.querySelector(`[data-toolbar-slot="${slotName}"]`);
            if (!node) {
              anchors[slotName] = null;
              continue;
            }
            const rect = node.getBoundingClientRect();
            anchors[slotName] = {
              left: rect.left,
              top: rect.top,
              width: rect.width,
              height: rect.height,
            };
          }
          const controls = {};
          for (const controlName of controlNames) {
            const node = document.querySelector(`[data-toolbar-control="${controlName}"]`);
            if (!(node instanceof HTMLElement)) {
              controls[controlName] = null;
              continue;
            }
            const disabled = 'disabled' in node ? Boolean((node).disabled) : false;
            controls[controlName] = {
              disabled,
              tabIndex: node.tabIndex,
              ariaHidden: node.getAttribute('aria-hidden') === 'true',
            };
          }
          const toolbarVarRaw = getComputedStyle(appShell || document.documentElement).getPropertyValue('--toolbar-h').trim();
          const toolbarVarValue = Number.parseFloat(toolbarVarRaw);
          const shellRect = shell.getBoundingClientRect();
          const searchRow = document.querySelector('[data-toolbar-slot="search-row"]');
          const searchRowPointerEvents = searchRow instanceof HTMLElement
            ? getComputedStyle(searchRow).pointerEvents
            : null;
          return {
            toolbarHeight: shellRect.height,
            toolbarVarPx: Number.isFinite(toolbarVarValue) ? toolbarVarValue : null,
            searchRowPointerEvents,
            anchors,
            controls,
          };
        }"""
    )
    if not isinstance(snapshot, dict):
        raise SmokeFailure("Failed to capture toolbar snapshot.")
    return snapshot


def anchor_delta(lhs: dict[str, Any], rhs: dict[str, Any], slot: str) -> float | None:
    left = lhs.get("anchors", {}).get(slot)
    right = rhs.get("anchors", {}).get(slot)
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    try:
        left_delta = abs(float(left["left"]) - float(right["left"]))
        width_delta = abs(float(left["width"]) - float(right["width"]))
        top_delta = abs(float(left["top"]) - float(right["top"]))
    except (KeyError, TypeError, ValueError):
        return None
    return max(left_delta, width_delta, top_delta)


def assert_hidden_control_state(
    snapshot: dict[str, Any],
    control_name: str,
    context: str,
    violations: list[str],
) -> None:
    control = snapshot.get("controls", {}).get(control_name)
    if not isinstance(control, dict):
        violations.append(f"{context}: missing control state for {control_name}")
        return
    if not bool(control.get("disabled")):
        violations.append(f"{context}: expected {control_name} to be disabled")
    if int(control.get("tabIndex", 0)) != -1:
        violations.append(f"{context}: expected {control_name} tabindex=-1")
    if not bool(control.get("ariaHidden")):
        violations.append(f"{context}: expected {control_name} aria-hidden=true")


def is_viewer_open(page: Any) -> bool:
    raw = page.evaluate(
        """() => {
          const viewer = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
          if (!(viewer instanceof HTMLElement)) return false;
          const rect = viewer.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        }"""
    )
    return bool(raw)


def open_viewer_with_fallback(
    page: Any,
    browser_timeout_ms: float,
    playwright_timeout_error: type[BaseException],
    playwright_error: type[BaseException],
) -> None:
    attempts = [
        lambda: page.locator('[role="gridcell"][id^="cell-"] > div').first.dblclick(),
        lambda: (
            page.locator('[role="gridcell"][id^="cell-"]').first.click(),
            page.keyboard.press("Enter"),
        ),
        lambda: page.evaluate(
            """() => {
              const target = document.querySelector('[role="gridcell"][id^="cell-"] > div');
              if (!(target instanceof HTMLElement)) return false;
              target.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true, detail: 2 }));
              return true;
            }"""
        ),
    ]
    for attempt in attempts:
        if is_viewer_open(page):
            return
        try:
            attempt()
        except playwright_error:
            if is_viewer_open(page):
                return
            continue
        if is_viewer_open(page):
            return
        try:
            wait_for_back_button(page, min(5_000, browser_timeout_ms))
            return
        except playwright_timeout_error:
            if is_viewer_open(page):
                return
            continue
    raise SmokeFailure("Timed out waiting for viewer back button to become interactive.")


def close_viewer(page: Any, browser_timeout_ms: float) -> None:
    back_button = page.locator('[data-toolbar-control="back"]').first
    if back_button.count() > 0 and back_button.is_enabled():
        back_button.click()
    else:
        page.keyboard.press("Escape")
    wait_for_grid(page, browser_timeout_ms)


def wait_for_mobile_search(page: Any, *, disabled: bool, browser_timeout_ms: float) -> None:
    page.wait_for_function(
        """(expectedDisabled) => {
          const input = document.querySelector('[data-toolbar-control="search-mobile"]');
          return input instanceof HTMLInputElement && input.disabled === expectedDisabled;
        }""",
        arg=disabled,
        timeout=browser_timeout_ms,
    )


def exercise_toolbar_probe(
    page: Any,
    *,
    base_url: str,
    browser_timeout_ms: float,
    playwright_timeout_error: type[BaseException],
    playwright_error: type[BaseException],
) -> ToolbarSnapshots:
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)
    desktop_browse = snapshot_toolbar(page)

    open_viewer_with_fallback(page, browser_timeout_ms, playwright_timeout_error, playwright_error)
    desktop_viewer = snapshot_toolbar(page)
    close_viewer(page, browser_timeout_ms)
    desktop_restored = snapshot_toolbar(page)

    page.set_viewport_size({"width": 760, "height": 840})
    page.reload(wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)
    narrow_closed = snapshot_toolbar(page)

    toggle_button = page.locator('[data-toolbar-control="search-toggle"]').first
    toggle_button.click()
    wait_for_mobile_search(page, disabled=False, browser_timeout_ms=browser_timeout_ms)
    narrow_open = snapshot_toolbar(page)

    toggle_button.click()
    wait_for_mobile_search(page, disabled=True, browser_timeout_ms=browser_timeout_ms)
    narrow_restored = snapshot_toolbar(page)

    return ToolbarSnapshots(
        desktop_browse=desktop_browse,
        desktop_viewer=desktop_viewer,
        desktop_restored=desktop_restored,
        narrow_closed=narrow_closed,
        narrow_open=narrow_open,
        narrow_restored=narrow_restored,
    )


def toolbar_slot_deltas(snapshots: ToolbarSnapshots) -> dict[str, float]:
    slot_deltas: dict[str, float] = {}
    for slot_name in ("back", "refresh", "nav", "upload", "search-desktop", "search-toggle"):
        comparisons = [
            delta
            for delta in (
                anchor_delta(snapshots.desktop_browse, snapshots.desktop_viewer, slot_name),
                anchor_delta(snapshots.desktop_browse, snapshots.desktop_restored, slot_name),
                anchor_delta(snapshots.narrow_closed, snapshots.narrow_open, slot_name),
                anchor_delta(snapshots.narrow_closed, snapshots.narrow_restored, slot_name),
            )
            if delta is not None
        ]
        if comparisons:
            slot_deltas[slot_name] = max(comparisons)
    return slot_deltas


def toolbar_size_deltas(snapshots: ToolbarSnapshots) -> dict[str, float]:
    return {
        "desktop_toolbar_height_delta": max(
            state_delta(snapshots.desktop_browse, snapshots.desktop_viewer, "toolbarHeight"),
            state_delta(snapshots.desktop_browse, snapshots.desktop_restored, "toolbarHeight"),
        ),
        "desktop_toolbar_var_delta": max(
            state_delta(snapshots.desktop_browse, snapshots.desktop_viewer, "toolbarVarPx"),
            state_delta(snapshots.desktop_browse, snapshots.desktop_restored, "toolbarVarPx"),
        ),
        "narrow_toolbar_height_delta": max(
            state_delta(snapshots.narrow_closed, snapshots.narrow_open, "toolbarHeight"),
            state_delta(snapshots.narrow_closed, snapshots.narrow_restored, "toolbarHeight"),
        ),
        "narrow_toolbar_var_delta": max(
            state_delta(snapshots.narrow_closed, snapshots.narrow_open, "toolbarVarPx"),
            state_delta(snapshots.narrow_closed, snapshots.narrow_restored, "toolbarVarPx"),
        ),
    }


def toolbar_violations(
    snapshots: ToolbarSnapshots,
    *,
    max_anchor_delta: float,
    max_toolbar_delta: float,
    max_delta_px: float,
) -> list[str]:
    violations: list[str] = []
    if max_anchor_delta > max_delta_px:
        violations.append(f"anchor delta {max_anchor_delta:.3f}px exceeded threshold {max_delta_px:.3f}px")
    if max_toolbar_delta > max_delta_px:
        violations.append(f"toolbar delta {max_toolbar_delta:.3f}px exceeded threshold {max_delta_px:.3f}px")

    assert_hidden_control_state(snapshots.desktop_browse, "back", "desktop browse state", violations)
    assert_hidden_control_state(snapshots.desktop_viewer, "refresh", "desktop viewer state", violations)
    assert_hidden_control_state(snapshots.desktop_viewer, "upload", "desktop viewer state", violations)
    assert_hidden_control_state(snapshots.desktop_viewer, "search-desktop", "desktop viewer state", violations)
    assert_hidden_control_state(snapshots.narrow_closed, "search-mobile", "narrow browse closed state", violations)
    if snapshots.narrow_closed.get("searchRowPointerEvents") != "none":
        violations.append("narrow browse closed state: expected search-row pointer-events=none")
    if snapshots.narrow_open.get("searchRowPointerEvents") == "none":
        violations.append("narrow browse open state: expected search-row pointer-events to be interactive")
    return violations


def toolbar_result(snapshots: ToolbarSnapshots, max_delta_px: float) -> ProbeResult:
    slot_deltas = toolbar_slot_deltas(snapshots)
    toolbar_deltas = toolbar_size_deltas(snapshots)
    max_anchor_delta = max(slot_deltas.values(), default=0.0)
    max_toolbar_delta = max(toolbar_deltas.values(), default=0.0)
    violations = toolbar_violations(
        snapshots,
        max_anchor_delta=max_anchor_delta,
        max_toolbar_delta=max_toolbar_delta,
        max_delta_px=max_delta_px,
    )
    if violations:
        raise SmokeFailure("; ".join(violations))
    return ProbeResult(
        scenario="toolbar",
        max_delta_px=max_delta_px,
        max_anchor_delta_px=max_anchor_delta,
        max_toolbar_delta_px=max_toolbar_delta,
        checks={
            "slot_deltas_px": slot_deltas,
            "toolbar_deltas_px": toolbar_deltas,
            "desktop_browse_snapshot": snapshots.desktop_browse,
            "desktop_viewer_snapshot": snapshots.desktop_viewer,
            "desktop_restored_snapshot": snapshots.desktop_restored,
            "narrow_closed_snapshot": snapshots.narrow_closed,
            "narrow_open_snapshot": snapshots.narrow_open,
            "narrow_restored_snapshot": snapshots.narrow_restored,
            "violations": violations,
        },
    )


def run_toolbar_probe(base_url: str, max_delta_px: float, browser_timeout_ms: float) -> ProbeResult:
    playwright_error, playwright_timeout_error, sync_playwright = import_playwright()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1120, "height": 840})
            page = context.new_page()
            page.set_default_timeout(browser_timeout_ms)
            snapshots = exercise_toolbar_probe(
                page,
                base_url=base_url,
                browser_timeout_ms=browser_timeout_ms,
                playwright_timeout_error=playwright_timeout_error,
                playwright_error=playwright_error,
            )
            context.close()
            browser.close()
    except playwright_timeout_error as exc:
        raise SmokeFailure(f"playwright timeout: {exc}") from exc
    except playwright_error as exc:
        raise SmokeFailure(f"playwright probe failed: {exc}") from exc
    return toolbar_result(snapshots, max_delta_px)
