#!/usr/bin/env python3
"""Minimal responsive layout geometry evidence for Lenslet.

Sprint 1 seeds the browser-facing harness with two viewport classes and
layout-debug capture. Later responsive tickets should expand assertions here
instead of creating a parallel browser script.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from smoke_harness import (
    choose_port,
    import_playwright,
    launch_lenslet,
    stop_process,
    wait_for_health,
)


class ResponsiveGeometryFailure(RuntimeError):
    """Raised when a responsive geometry invariant fails."""


@dataclass(frozen=True)
class Scenario:
    name: str
    width: int
    height: int
    storage: dict[str, str]
    open_mobile_search: bool = False
    has_touch: bool = False
    select_first: bool = False
    assert_inspector: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Lenslet responsive layout geometry checks.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7070)
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--keep-dataset", action="store_true")
    parser.add_argument("--server-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--browser-timeout-ms", type=float, default=30_000)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/tmp/lenslet-responsive-geometry.json"),
        help="Path for machine-readable responsive geometry evidence.",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=Path("/tmp/lenslet-responsive-geometry-screenshots"),
        help="Directory for screenshots captured on scenario failure.",
    )
    return parser.parse_args()


def build_fixture_dataset(root: Path) -> None:
    payload = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAABgAAAASCAYAAABFGc6JAAAAGklEQVR4nGNkYGBg+M+ABzAx"
        "VAlGtWAIBgAEcwEem4pV9wAAAABJRU5ErkJggg=="
    )
    for folder in ("alpha", "beta"):
        for idx in range(4):
            filename = (
                f"{folder}_source_path_with_unbroken_metadata_identifier_{idx:02d}_abcdef0123456789.png"
                if idx == 0
                else f"{folder}_{idx:02d}.png"
            )
            path = root / folder / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)


def scenario_storage() -> dict[str, str]:
    return {
        "leftOpen": "1",
        "rightOpen": "1",
        "leftW.folders": "760",
        "leftW.metrics": "760",
        "rightW": "900",
    }


def seed_storage_script(storage: dict[str, str]) -> str:
    return f"""{{
      localStorage.clear();
      const values = {json.dumps(storage)};
      for (const [key, value] of Object.entries(values)) {{
        localStorage.setItem(key, value);
      }}
    }}"""


def collect_snapshot(page: Any, name: str) -> dict[str, Any]:
    snapshot = page.evaluate(
        """(name) => {
          const shell = document.querySelector('.app-shell');
          if (!shell) return { name, missingShell: true };
          const shellStyle = getComputedStyle(shell);
          const doc = document.documentElement;
          const rectFor = (selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {
              x: rect.x,
              y: rect.y,
              width: rect.width,
              height: rect.height,
              left: rect.left,
              right: rect.right,
              top: rect.top,
              bottom: rect.bottom,
            };
          };
          const describeElement = (el) => {
            if (!el) return null;
            return {
              tag: el.tagName,
              id: el.id || null,
              className: typeof el.className === 'string' ? el.className : null,
              ariaLabel: el.getAttribute('aria-label'),
              dataToolbarControl: el.getAttribute('data-toolbar-control'),
              inBrowseShell: Boolean(el.closest('[data-browse-shell]')),
              inToolbar: Boolean(el.closest('.toolbar-shell')),
              inLeftSidebar: Boolean(el.closest('.app-left-panel')),
              inRightSidebar: Boolean(el.closest('.app-right-panel')),
              inMobileDrawer: Boolean(el.closest('.mobile-drawer')),
              inGrid: Boolean(el.closest('[role="grid"][aria-label="Gallery"]')),
              inOverlayDialog: Boolean(el.closest('[role="dialog"][aria-modal="true"]')),
            };
          };
          const panel = document.querySelector('.app-right-panel');
          const inspectorChecks = panel
            ? Array.from(panel.querySelectorAll([
                '.inspector-preview-card',
                '.inspector-star-row',
                '.inspector-section-header',
                '.ui-kv-row',
                '.inspector-field',
              ].join(','))).map((el) => {
                const rect = el.getBoundingClientRect();
                return {
                  selector: el.className,
                  left: rect.left,
                  right: rect.right,
                  width: rect.width,
                  overflowsPanel: rect.left < panel.getBoundingClientRect().left - 1 ||
                    rect.right > panel.getBoundingClientRect().right + 1,
                };
              })
            : [];
          const toolbarControls = Array.from(document.querySelectorAll('[data-toolbar-control]'))
            .map((el) => {
              const rect = el.getBoundingClientRect();
              const style = getComputedStyle(el);
              const centerX = rect.left + rect.width / 2;
              const centerY = rect.top + rect.height / 2;
              const hit = rect.width > 0 && rect.height > 0
                ? document.elementFromPoint(centerX, centerY)
                : null;
              const focusTarget = el.matches('button,input,select,textarea,a,[tabindex]')
                ? el
                : el.querySelector('button,input,select,textarea,a,[tabindex]:not([tabindex="-1"])');
              const focusStyle = focusTarget ? getComputedStyle(focusTarget) : null;
              return {
                name: el.getAttribute('data-toolbar-control') || el.getAttribute('aria-label') || '',
                ariaHidden: el.getAttribute('aria-hidden'),
                disabled: Boolean(el.disabled),
                visible: style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0,
                hitTargetOk: Boolean(hit && (el === hit || el.contains(hit) || hit.closest('[data-toolbar-control]') === el)),
                focusDisabled: Boolean(focusTarget && focusTarget.disabled),
                keyboardFocusable: Boolean(
                  focusTarget &&
                  !focusTarget.disabled &&
                  focusTarget.getAttribute('aria-hidden') !== 'true' &&
                  focusTarget.getAttribute('tabindex') !== '-1' &&
                  focusStyle &&
                  focusStyle.display !== 'none' &&
                  focusStyle.visibility !== 'hidden'
                ),
                rect: {
                  x: rect.x,
                  y: rect.y,
                  width: rect.width,
                  height: rect.height,
                  left: rect.left,
                  right: rect.right,
                  top: rect.top,
                  bottom: rect.bottom,
                },
              };
            });
          return {
            name,
            viewport: { width: window.innerWidth, height: window.innerHeight },
            media: {
              coarsePointer: window.matchMedia('(pointer: coarse)').matches,
            },
            layout: {
              mode: shell.getAttribute('data-layout-mode'),
              shortHeight: shell.getAttribute('data-short-height'),
              leftSuppressionReason: shell.getAttribute('data-left-suppression-reason'),
              rightSuppressionReason: shell.getAttribute('data-right-suppression-reason'),
              inspectorSuppressionReason: shell.getAttribute('data-inspector-suppression-reason'),
              overlayMode: shell.getAttribute('data-overlay-mode'),
              mobileSearchOpen: shell.getAttribute('data-mobile-search-open'),
              mobileDrawerOpen: shell.getAttribute('data-mobile-drawer-open'),
              effectiveLeftWidth: shell.getAttribute('data-effective-left-width'),
              effectiveRightWidth: shell.getAttribute('data-effective-right-width'),
            },
            cssVars: {
              gridLeft: shellStyle.getPropertyValue('--grid-left').trim(),
              gridRight: shellStyle.getPropertyValue('--grid-right').trim(),
              overlayLeft: shellStyle.getPropertyValue('--overlay-left').trim(),
              overlayRight: shellStyle.getPropertyValue('--overlay-right').trim(),
              toolbarHeight: shellStyle.getPropertyValue('--toolbar-h').trim(),
              mobileDrawerHeight: shellStyle.getPropertyValue('--mobile-drawer-h').trim(),
            },
            scroll: {
              scrollWidth: doc.scrollWidth,
              clientWidth: doc.clientWidth,
            },
            rects: {
              shell: rectFor('.app-shell'),
              toolbar: rectFor('.toolbar-shell'),
              leftSidebar: rectFor('.app-left-panel'),
              rightSidebar: rectFor('.app-right-panel'),
              gridShell: rectFor('.grid-shell'),
              mobileDrawer: rectFor('.mobile-drawer'),
              overlay: rectFor('[role="dialog"][aria-label="Image viewer"], [role="dialog"][aria-label="Compare images"]'),
              viewer: rectFor('[role="dialog"][aria-label="Image viewer"]'),
              compare: rectFor('[role="dialog"][aria-label="Compare images"]'),
              compareStage: rectFor('.compare-stage'),
              inspectorPreview: rectFor('.inspector-preview-card'),
              inspectorStarRow: rectFor('.inspector-star-row'),
            },
            focus: {
              activeElement: describeElement(document.activeElement),
              browseShellInert: document.querySelector('[data-browse-shell]')?.hasAttribute('inert') ?? false,
              browseShellAriaHidden: document.querySelector('[data-browse-shell]')?.getAttribute('aria-hidden') ?? null,
              toolbarInert: document.querySelector('.toolbar-shell')?.hasAttribute('inert') ?? false,
              toolbarAriaHidden: document.querySelector('.toolbar-shell')?.getAttribute('aria-hidden') ?? null,
            },
            inspector: panel ? {
              clientWidth: panel.clientWidth,
              scrollWidth: panel.scrollWidth,
              rect: rectFor('.app-right-panel'),
              checks: inspectorChecks,
            } : null,
            toolbarControls,
            storage: {
              leftOpen: localStorage.getItem('leftOpen'),
              rightOpen: localStorage.getItem('rightOpen'),
              leftFoldersWidth: localStorage.getItem('leftW.folders'),
              rightWidth: localStorage.getItem('rightW'),
            },
          };
        }""",
        name,
    )
    if not isinstance(snapshot, dict) or snapshot.get("missingShell"):
        raise ResponsiveGeometryFailure(f"App shell was not available for scenario {name!r}.")
    return snapshot


def assert_no_document_overflow(snapshot: dict[str, Any]) -> None:
    scroll = snapshot.get("scroll")
    if not isinstance(scroll, dict):
        raise ResponsiveGeometryFailure(f"Missing scroll evidence for {snapshot.get('name')!r}.")
    scroll_width = float(scroll.get("scrollWidth", 0))
    client_width = float(scroll.get("clientWidth", 0))
    if scroll_width > client_width + 1:
        raise ResponsiveGeometryFailure(
            f"Document overflow in {snapshot.get('name')}: scrollWidth={scroll_width}, clientWidth={client_width}."
        )


def _rect(control: dict[str, Any]) -> dict[str, float]:
    rect = control.get("rect")
    if not isinstance(rect, dict):
        return {}
    return rect


def _visible_toolbar_controls(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    controls = snapshot.get("toolbarControls")
    if not isinstance(controls, list):
        raise ResponsiveGeometryFailure(f"Missing toolbar control evidence for {snapshot.get('name')!r}.")
    return [
        control for control in controls
        if isinstance(control, dict)
        and control.get("visible")
        and control.get("ariaHidden") != "true"
    ]


def assert_no_visible_control_overlap(snapshot: dict[str, Any]) -> None:
    controls = _visible_toolbar_controls(snapshot)
    for index, left in enumerate(controls):
        left_rect = _rect(left)
        for right in controls[index + 1:]:
            right_rect = _rect(right)
            x_overlap = min(float(left_rect.get("right", 0)), float(right_rect.get("right", 0))) - max(
                float(left_rect.get("left", 0)),
                float(right_rect.get("left", 0)),
            )
            y_overlap = min(float(left_rect.get("bottom", 0)), float(right_rect.get("bottom", 0))) - max(
                float(left_rect.get("top", 0)),
                float(right_rect.get("top", 0)),
            )
            if x_overlap > 1 and y_overlap > 1:
                raise ResponsiveGeometryFailure(
                    "Visible toolbar controls overlap in "
                    f"{snapshot.get('name')}: {left.get('name')} with {right.get('name')}."
                )


def _parse_px(raw: Any) -> float:
    if not isinstance(raw, str):
        return 0.0
    try:
        return float(raw.strip().removesuffix("px"))
    except ValueError:
        return 0.0


def assert_mobile_search_reserved(snapshot: dict[str, Any]) -> None:
    css_vars = snapshot.get("cssVars")
    rects = snapshot.get("rects")
    if not isinstance(css_vars, dict) or not isinstance(rects, dict):
        raise ResponsiveGeometryFailure(f"Missing search reserve evidence for {snapshot.get('name')!r}.")
    toolbar_height = _parse_px(css_vars.get("toolbarHeight"))
    if toolbar_height < 96:
        raise ResponsiveGeometryFailure(
            f"Mobile search did not reserve declared toolbar height in {snapshot.get('name')}: {toolbar_height}px."
        )
    controls = {control.get("name"): control for control in _visible_toolbar_controls(snapshot)}
    if not controls.get("search-mobile"):
        raise ResponsiveGeometryFailure(f"Mobile search input is not visible in {snapshot.get('name')}.")
    toolbar_rect = rects.get("toolbar")
    grid_rect = rects.get("gridShell")
    if not isinstance(toolbar_rect, dict) or not isinstance(grid_rect, dict):
        raise ResponsiveGeometryFailure(f"Missing toolbar/grid rects for {snapshot.get('name')!r}.")
    if float(grid_rect.get("top", 0)) + 1 < float(toolbar_rect.get("bottom", 0)):
        raise ResponsiveGeometryFailure(
            f"Grid starts under the mobile search toolbar in {snapshot.get('name')}."
        )


REQUIRED_DRAWER_CONTROLS = {
    "drawer-layout-grid",
    "drawer-layout-masonry",
    "drawer-theme",
    "drawer-sort",
    "drawer-sort-dir",
    "drawer-filters",
    "drawer-refresh",
    "drawer-left-panel",
    "drawer-right-panel",
    "drawer-upload",
}


def assert_mobile_drawer_reachable(snapshot: dict[str, Any]) -> None:
    layout = snapshot.get("layout")
    if not isinstance(layout, dict) or layout.get("mobileDrawerOpen") != "true":
        raise ResponsiveGeometryFailure(f"Mobile drawer is not open in {snapshot.get('name')!r}.")
    viewport = snapshot.get("viewport")
    viewport_width = float(viewport.get("width", 0)) if isinstance(viewport, dict) else 0.0
    required_controls = set(REQUIRED_DRAWER_CONTROLS)
    if viewport_width <= 767:
        required_controls.add("drawer-select")
    controls = {control.get("name"): control for control in _visible_toolbar_controls(snapshot)}
    missing = sorted(name for name in required_controls if name not in controls)
    if missing:
        raise ResponsiveGeometryFailure(
            f"Mobile drawer controls are missing in {snapshot.get('name')}: {', '.join(missing)}."
        )
    blocked = [
        name for name in sorted(required_controls)
        if not controls[name].get("hitTargetOk")
        or (not controls[name].get("focusDisabled") and not controls[name].get("keyboardFocusable"))
    ]
    if blocked:
        raise ResponsiveGeometryFailure(
            f"Mobile drawer controls are not pointer/keyboard reachable in {snapshot.get('name')}: "
            f"{', '.join(blocked)}."
        )


def assert_overlay_isolated(snapshot: dict[str, Any], expected_mode: str) -> None:
    layout = snapshot.get("layout")
    rects = snapshot.get("rects")
    focus = snapshot.get("focus")
    if not isinstance(layout, dict) or layout.get("overlayMode") != expected_mode:
        raise ResponsiveGeometryFailure(
            f"Expected {expected_mode} overlay mode in {snapshot.get('name')}, got {layout!r}."
        )
    if not isinstance(rects, dict) or not isinstance(rects.get("overlay"), dict):
        raise ResponsiveGeometryFailure(f"Missing overlay rect for {snapshot.get('name')}.")
    if not isinstance(focus, dict):
        raise ResponsiveGeometryFailure(f"Missing focus evidence for {snapshot.get('name')}.")
    if focus.get("browseShellInert") is not True or focus.get("browseShellAriaHidden") != "true":
        raise ResponsiveGeometryFailure(f"Browse shell is not inert under overlay in {snapshot.get('name')}.")
    if expected_mode == "compare":
        if focus.get("toolbarInert") is not True or focus.get("toolbarAriaHidden") != "true":
            raise ResponsiveGeometryFailure(f"Compare overlay did not inert the toolbar in {snapshot.get('name')}.")
    if expected_mode == "viewer":
        if focus.get("toolbarInert") is True or focus.get("toolbarAriaHidden") == "true":
            raise ResponsiveGeometryFailure(f"Viewer overlay disabled viewer toolbar chrome in {snapshot.get('name')}.")
    active = focus.get("activeElement")
    if isinstance(active, dict) and active.get("inBrowseShell"):
        raise ResponsiveGeometryFailure(f"Focus reached browse shell under overlay in {snapshot.get('name')}: {active!r}.")

    overlay_rect = rects["overlay"]
    viewport = snapshot.get("viewport", {})
    css_vars = snapshot.get("cssVars", {})
    expected_left = _parse_px(css_vars.get("overlayLeft") if isinstance(css_vars, dict) else None)
    expected_right = _parse_px(css_vars.get("overlayRight") if isinstance(css_vars, dict) else None)
    viewport_width = float(viewport.get("width", 0)) if isinstance(viewport, dict) else 0.0
    if float(overlay_rect.get("left", 0)) > expected_left + 1:
        raise ResponsiveGeometryFailure(f"Overlay left edge is squeezed in {snapshot.get('name')}: {overlay_rect!r}.")
    if float(overlay_rect.get("right", 0)) < viewport_width - expected_right - 1:
            raise ResponsiveGeometryFailure(f"Overlay right edge is squeezed in {snapshot.get('name')}: {overlay_rect!r}.")


def assert_viewer_toolbar_chrome(snapshot: dict[str, Any]) -> None:
    controls = {control.get("name"): control for control in _visible_toolbar_controls(snapshot)}
    back = controls.get("back")
    if not back or not back.get("hitTargetOk") or not back.get("keyboardFocusable"):
        raise ResponsiveGeometryFailure(f"Viewer toolbar back control is not usable in {snapshot.get('name')}.")


def assert_overlay_closed(snapshot: dict[str, Any], expected_name: str) -> None:
    layout = snapshot.get("layout")
    focus = snapshot.get("focus")
    if not isinstance(layout, dict) or layout.get("overlayMode") != "none":
        raise ResponsiveGeometryFailure(f"Overlay did not close in {expected_name}: {layout!r}.")
    if isinstance(focus, dict):
        active = focus.get("activeElement")
        if isinstance(active, dict) and active.get("inOverlayDialog"):
            raise ResponsiveGeometryFailure(f"Focus stayed in closed overlay for {expected_name}: {active!r}.")


def assert_inspector_contained(snapshot: dict[str, Any]) -> None:
    layout = snapshot.get("layout")
    inspector = snapshot.get("inspector")
    if not isinstance(layout, dict):
        raise ResponsiveGeometryFailure(f"Missing layout for {snapshot.get('name')}.")
    if layout.get("effectiveRightWidth") == "0":
        return
    if not isinstance(inspector, dict):
        raise ResponsiveGeometryFailure(f"Missing inspector evidence for {snapshot.get('name')}.")
    scroll_width = float(inspector.get("scrollWidth", 0))
    client_width = float(inspector.get("clientWidth", 0))
    if scroll_width > client_width + 1:
        raise ResponsiveGeometryFailure(
            f"Inspector has horizontal overflow in {snapshot.get('name')}: "
            f"scrollWidth={scroll_width}, clientWidth={client_width}."
        )
    checks = inspector.get("checks")
    if not isinstance(checks, list):
        raise ResponsiveGeometryFailure(f"Missing inspector child checks for {snapshot.get('name')}.")
    overflowing = [check for check in checks if isinstance(check, dict) and check.get("overflowsPanel")]
    if overflowing:
        raise ResponsiveGeometryFailure(
            f"Inspector child escaped panel in {snapshot.get('name')}: {overflowing[:3]!r}."
        )


def wait_for_shell(page: Any, timeout_ms: float) -> None:
    page.locator(".app-shell").wait_for(state="visible", timeout=timeout_ms)
    page.locator("[role='grid']").wait_for(state="visible", timeout=timeout_ms)


def select_first_item(page: Any, timeout_ms: float) -> None:
    first_cell = page.locator('[role="gridcell"][id^="cell-"]').first
    first_cell.click(timeout=timeout_ms)


def open_first_viewer(page: Any, timeout_ms: float) -> None:
    first_cell = page.locator('[role="gridcell"][id^="cell-"]').first
    first_cell.dblclick(timeout=timeout_ms)
    page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(state="visible", timeout=timeout_ms)


def open_compare_from_first_two_items(page: Any, timeout_ms: float) -> None:
    cells = page.locator('[role="gridcell"][id^="cell-"]')
    cells.nth(0).click(timeout=timeout_ms)
    cells.nth(1).click(timeout=timeout_ms, modifiers=["Control"])
    page.locator('[aria-label="Compare selected images"]').click(timeout=timeout_ms)
    page.locator('[role="dialog"][aria-label="Compare images"]').wait_for(state="visible", timeout=timeout_ms)


def run_scenario(page: Any, base_url: str, scenario: Scenario, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": scenario.width, "height": scenario.height})
    page.add_init_script(seed_storage_script(scenario.storage))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    if scenario.open_mobile_search:
        page.locator('[data-toolbar-control="search-toggle"]').click(timeout=timeout_ms)
    if scenario.select_first or scenario.assert_inspector:
        select_first_item(page, timeout_ms)
    page.wait_for_timeout(200)
    snapshot = collect_snapshot(page, scenario.name)
    assert_no_document_overflow(snapshot)
    assert_no_visible_control_overlap(snapshot)
    if scenario.width <= 900:
        assert_mobile_drawer_reachable(snapshot)
    if scenario.open_mobile_search:
        assert_mobile_search_reserved(snapshot)
    if scenario.assert_inspector:
        assert_inspector_contained(snapshot)
    return snapshot


def run_resize_persistence_scenario(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.add_init_script(seed_storage_script(scenario_storage()))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    desktop_before = collect_snapshot(page, "resize-persistence-desktop-before")

    page.set_viewport_size({"width": 320, "height": 700})
    page.wait_for_timeout(300)
    phone = collect_snapshot(page, "resize-persistence-phone")

    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_timeout(300)
    desktop_after = collect_snapshot(page, "resize-persistence-desktop-after")

    for snapshot in (desktop_before, phone, desktop_after):
        assert_no_document_overflow(snapshot)
        assert_no_visible_control_overlap(snapshot)
    assert_mobile_drawer_reachable(phone)

    for snapshot in (desktop_before, phone, desktop_after):
        storage = snapshot.get("storage", {})
        if storage.get("leftOpen") != "1" or storage.get("rightOpen") != "1":
            raise ResponsiveGeometryFailure(
                "Responsive suppression rewrote persisted sidebar preferences during "
                f"{snapshot.get('name')}: storage={storage!r}."
            )
        if storage.get("leftFoldersWidth") != "760" or storage.get("rightWidth") != "900":
            raise ResponsiveGeometryFailure(
                "Responsive suppression rewrote persisted sidebar widths during "
                f"{snapshot.get('name')}: storage={storage!r}."
            )

    if desktop_after.get("layout", {}).get("mode") != "desktop":
        raise ResponsiveGeometryFailure("Desktop layout mode did not restore after resize-up.")
    if desktop_after.get("layout", {}).get("effectiveRightWidth") == "0":
        raise ResponsiveGeometryFailure("Right sidebar did not restore after resize-up.")

    return {
        "name": "resize-persistence",
        "steps": [desktop_before, phone, desktop_after],
    }


def run_viewer_overlay_scenario(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 390, "height": 520})
    page.add_init_script(seed_storage_script(scenario_storage()))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    open_first_viewer(page, timeout_ms)
    page.keyboard.press("Tab")
    page.wait_for_timeout(100)
    open_snapshot = collect_snapshot(page, "viewer-overlay-390x520")
    assert_no_document_overflow(open_snapshot)
    assert_overlay_isolated(open_snapshot, "viewer")

    page.keyboard.press("Escape")
    page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(state="detached", timeout=timeout_ms)
    page.wait_for_timeout(100)
    closed_snapshot = collect_snapshot(page, "viewer-overlay-closed")
    assert_overlay_closed(closed_snapshot, "viewer-overlay-closed")

    page.set_viewport_size({"width": 1024, "height": 760})
    page.wait_for_timeout(200)
    open_first_viewer(page, timeout_ms)
    page.wait_for_timeout(100)
    desktop_snapshot = collect_snapshot(page, "viewer-toolbar-1024x760")
    assert_no_document_overflow(desktop_snapshot)
    assert_overlay_isolated(desktop_snapshot, "viewer")
    assert_viewer_toolbar_chrome(desktop_snapshot)

    page.locator('[data-toolbar-control="back"]').click(timeout=timeout_ms)
    page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(state="detached", timeout=timeout_ms)
    page.wait_for_timeout(100)
    toolbar_closed_snapshot = collect_snapshot(page, "viewer-toolbar-closed")
    assert_overlay_closed(toolbar_closed_snapshot, "viewer-toolbar-closed")

    return {
        "name": "viewer-overlay",
        "steps": [open_snapshot, closed_snapshot, desktop_snapshot, toolbar_closed_snapshot],
    }


def run_compare_overlay_scenario(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.add_init_script(seed_storage_script(scenario_storage()))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    open_compare_from_first_two_items(page, timeout_ms)
    page.set_viewport_size({"width": 390, "height": 520})
    page.wait_for_timeout(300)
    page.keyboard.press("Tab")
    page.wait_for_timeout(100)
    open_snapshot = collect_snapshot(page, "compare-overlay-390x520")
    assert_no_document_overflow(open_snapshot)
    assert_overlay_isolated(open_snapshot, "compare")

    page.keyboard.press("Escape")
    page.locator('[role="dialog"][aria-label="Compare images"]').wait_for(state="detached", timeout=timeout_ms)
    page.wait_for_timeout(100)
    closed_snapshot = collect_snapshot(page, "compare-overlay-closed")
    assert_overlay_closed(closed_snapshot, "compare-overlay-closed")

    return {
        "name": "compare-overlay",
        "steps": [open_snapshot, closed_snapshot],
    }


def write_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    dataset_tmp: Path | None = None
    dataset_dir = args.dataset_dir
    if dataset_dir is None:
        dataset_tmp = Path(tempfile.mkdtemp(prefix="lenslet-responsive-fixture-"))
        dataset_dir = dataset_tmp
        build_fixture_dataset(dataset_dir)

    port = choose_port(args.host, args.port)
    base_url = f"http://{args.host}:{port}"
    process = launch_lenslet(dataset_dir, host=args.host, port=port, cwd=repo_root)
    evidence: dict[str, Any] = {
        "baseUrl": base_url,
        "datasetDir": str(dataset_dir),
        "startedAt": time.time(),
        "scenarios": [],
        "failures": [],
    }

    _, _, sync_playwright = import_playwright()
    try:
        wait_for_health(base_url, args.server_timeout_seconds)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                scenarios = [
                    Scenario("desktop-open-oversized", 1440, 900, scenario_storage()),
                    Scenario("phone-open-oversized", 320, 700, scenario_storage(), has_touch=True),
                    Scenario("phone-toolbar-360", 360, 700, scenario_storage(), has_touch=True),
                    Scenario("phone-toolbar-390", 390, 700, scenario_storage(), has_touch=True),
                    Scenario(
                        "phone-search-open-320",
                        320,
                        700,
                        scenario_storage(),
                        open_mobile_search=True,
                        has_touch=True,
                    ),
                    Scenario(
                        "narrow-search-open-640",
                        640,
                        760,
                        scenario_storage(),
                        open_mobile_search=True,
                        has_touch=True,
                    ),
                    Scenario(
                        "inspector-phone-suppressed-480",
                        480,
                        760,
                        scenario_storage(),
                        select_first=True,
                        assert_inspector=True,
                        has_touch=True,
                    ),
                    Scenario(
                        "inspector-short-narrow-760",
                        760,
                        430,
                        scenario_storage(),
                        select_first=True,
                        assert_inspector=True,
                    ),
                    Scenario(
                        "inspector-short-tablet-1024",
                        1024,
                        480,
                        scenario_storage(),
                        select_first=True,
                        assert_inspector=True,
                    ),
                    Scenario(
                        "inspector-allowed-900",
                        900,
                        760,
                        scenario_storage(),
                        select_first=True,
                        assert_inspector=True,
                    ),
                ]
                for scenario in scenarios:
                    context = browser.new_context(
                        viewport={"width": scenario.width, "height": scenario.height},
                        has_touch=scenario.has_touch,
                        is_mobile=scenario.has_touch,
                    )
                    page = context.new_page()
                    try:
                        evidence["scenarios"].append(
                            run_scenario(page, base_url, scenario, args.browser_timeout_ms)
                        )
                    except Exception as exc:
                        args.screenshot_dir.mkdir(parents=True, exist_ok=True)
                        screenshot = args.screenshot_dir / f"{scenario.name}.png"
                        page.screenshot(path=str(screenshot), full_page=True)
                        evidence["failures"].append({
                            "scenario": scenario.name,
                            "error": str(exc),
                            "screenshot": str(screenshot),
                        })
                        raise
                    finally:
                        context.close()

                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()
                try:
                    evidence["scenarios"].append(
                        run_resize_persistence_scenario(page, base_url, args.browser_timeout_ms)
                    )
                except Exception as exc:
                    args.screenshot_dir.mkdir(parents=True, exist_ok=True)
                    screenshot = args.screenshot_dir / "resize-persistence.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    evidence["failures"].append({
                        "scenario": "resize-persistence",
                        "error": str(exc),
                        "screenshot": str(screenshot),
                    })
                    raise
                finally:
                    context.close()

                overlay_runners = [
                    ("viewer-overlay", run_viewer_overlay_scenario),
                    ("compare-overlay", run_compare_overlay_scenario),
                ]
                for scenario_name, runner in overlay_runners:
                    context = browser.new_context(viewport={"width": 1440, "height": 900})
                    page = context.new_page()
                    try:
                        evidence["scenarios"].append(runner(page, base_url, args.browser_timeout_ms))
                    except Exception as exc:
                        args.screenshot_dir.mkdir(parents=True, exist_ok=True)
                        screenshot = args.screenshot_dir / f"{scenario_name}.png"
                        page.screenshot(path=str(screenshot), full_page=True)
                        evidence["failures"].append({
                            "scenario": scenario_name,
                            "error": str(exc),
                            "screenshot": str(screenshot),
                        })
                        raise
                    finally:
                        context.close()
            finally:
                browser.close()
    except Exception as exc:
        evidence["error"] = str(exc)
        write_evidence(args.output_json, evidence)
        raise SystemExit(1) from exc
    finally:
        stop_process(process)
        if dataset_tmp is not None and not args.keep_dataset:
            shutil.rmtree(dataset_tmp, ignore_errors=True)

    write_evidence(args.output_json, evidence)
    print(f"Wrote responsive geometry evidence to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
