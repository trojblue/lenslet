#!/usr/bin/env python3
"""Responsive layout geometry evidence for Lenslet.

This live-browser harness exercises the resize failure classes from the
responsive-layout plan. It uses temporary fixtures by default, records DOM
layout evidence for each scenario, and saves a screenshot plus failure snapshot
when an assertion trips.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from smoke_harness import (
    choose_port,
    import_playwright,
    stop_process,
    wait_for_health,
)


class ResponsiveGeometryFailure(RuntimeError):
    """Raised when a responsive geometry invariant fails."""


FIXTURE_METRIC_NAMES = (
    "quality_score",
    "aesthetic_score",
    "sharpness",
    "composition_balance",
    "color_harmony",
    "detail_density",
    "noise_penalty",
    "subject_confidence",
    "background_complexity",
    "prompt_alignment",
    "texture_consistency",
    "edge_integrity",
    "lighting_stability",
    "long_metric_name_for_selected_summary_stress",
)


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
    payload = build_png_payload()
    rows: list[dict[str, Any]] = []
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
            logical_path = f"{folder}/{filename}"
            rows.append(
                {
                    "path": logical_path,
                    "metrics": build_fixture_metrics(folder=folder, index=idx),
                }
            )
    write_fixture_parquet(root / "items.parquet", rows)


def build_png_payload() -> bytes:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - project dependency guard
        raise ResponsiveGeometryFailure("Pillow is required for responsive geometry fixtures") from exc
    buffer = BytesIO()
    Image.new("RGB", (1600, 1200), color=(44, 88, 132)).save(buffer, format="PNG")
    return buffer.getvalue()


def build_fixture_metrics(*, folder: str, index: int) -> dict[str, float]:
    prefix = 0.1 if folder == "alpha" else 0.6
    return {
        name: round(prefix + (index * 0.03) + (metric_index * 0.011), 6)
        for metric_index, name in enumerate(FIXTURE_METRIC_NAMES)
    }


def write_fixture_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - project dependency guard
        raise ResponsiveGeometryFailure("pyarrow is required for responsive geometry fixtures") from exc

    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


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


def scenario_state(scenario: Scenario) -> dict[str, Any]:
    return {
        "width": scenario.width,
        "height": scenario.height,
        "storage": dict(scenario.storage),
        "openMobileSearch": scenario.open_mobile_search,
        "hasTouch": scenario.has_touch,
        "selectFirst": scenario.select_first,
        "assertInspector": scenario.assert_inspector,
    }


def collect_snapshot(page: Any, name: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = page.evaluate(
        """({ name, state }) => {
          const shell = document.querySelector('.app-shell');
          if (!shell) return { name, missingShell: true };
          const shellStyle = getComputedStyle(shell);
          const doc = document.documentElement;
          const rectPayload = (rect) => ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          });
          const rectFor = (selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return rectPayload(rect);
          };
          const imageFor = (selector) => {
            const el = document.querySelector(selector);
            if (!(el instanceof HTMLImageElement)) return null;
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return {
              selector,
              src: el.currentSrc || el.src || null,
              currentPath: el.getAttribute("data-current-path"),
              complete: el.complete,
              naturalWidth: el.naturalWidth,
              naturalHeight: el.naturalHeight,
              opacity: Number(style.opacity || "0"),
              display: style.display,
              visibility: style.visibility,
              rect: rectPayload(rect),
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
          const elementText = (el) => el ? (el.textContent || '').replace(/\\s+/g, ' ').trim() : '';
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
          const leftPanel = document.querySelector('.app-left-panel');
          const selectedMetricsHeader = leftPanel
            ? Array.from(leftPanel.querySelectorAll('.ui-section-title'))
              .find((el) => elementText(el) === 'Selected metrics')
            : null;
          const selectedMetricsCard = selectedMetricsHeader?.closest('.ui-card') || null;
          const selectedMetricsChecks = leftPanel && selectedMetricsCard
            ? Array.from(selectedMetricsCard.querySelectorAll('*')).map((el) => {
              const rect = el.getBoundingClientRect();
              const panelRect = leftPanel.getBoundingClientRect();
              return {
                className: typeof el.className === 'string' ? el.className : null,
                text: elementText(el).slice(0, 120),
                rect: rectPayload(rect),
                overflowsPanel: rect.left < panelRect.left - 1 || rect.right > panelRect.right + 1,
              };
            })
            : [];
          const leftPanelContentChecks = leftPanel
            ? Array.from(leftPanel.querySelectorAll('*'))
              .filter((el) => !el.closest('.sidebar-resize-handle'))
              .map((el) => {
                const rect = el.getBoundingClientRect();
                const panelRect = leftPanel.getBoundingClientRect();
                return {
                  className: typeof el.className === 'string' ? el.className : null,
                  text: elementText(el).slice(0, 120),
                  rect: rectPayload(rect),
                  overflowsPanel: rect.left < panelRect.left - 1 || rect.right > panelRect.right + 1,
                };
              })
            : [];
          const activeLeftTool = leftPanel
            ? (
              leftPanel.querySelector('button[aria-label="Metrics and Filters"]')?.getAttribute('aria-pressed') === 'true'
                ? 'metrics'
                : leftPanel.querySelector('button[aria-label="Folders"]')?.getAttribute('aria-pressed') === 'true'
                  ? 'folders'
                  : null
            )
            : null;
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
                rect: rectPayload(rect),
              };
            });
          return {
            name,
            state,
            viewport: { width: window.innerWidth, height: window.innerHeight },
            browser: {
              devicePixelRatio: window.devicePixelRatio,
              visualViewportScale: window.visualViewport?.scale ?? null,
              url: window.location.href,
            },
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
              gridTopStack: rectFor('[data-grid-top-stack]'),
              statusBand: rectFor('[data-grid-top-band="status"]'),
              filtersBand: rectFor('[data-grid-top-band="filters"]'),
              leftSidebar: rectFor('.app-left-panel'),
              rightSidebar: rectFor('.app-right-panel'),
              gridShell: rectFor('.grid-shell'),
              mobileDrawer: rectFor('.mobile-drawer'),
              overlay: rectFor('[role="dialog"][aria-label="Image viewer"], [role="dialog"][aria-label="Compare images"]'),
              overlayStage: rectFor('.compare-stage, [role="dialog"][aria-label="Image viewer"]'),
              viewer: rectFor('[role="dialog"][aria-label="Image viewer"]'),
              compare: rectFor('[role="dialog"][aria-label="Compare images"]'),
              compareStage: rectFor('.compare-stage'),
              themeMenu: rectFor('[role="menu"][aria-label="Theme settings"]'),
              inspectorPreview: rectFor('.inspector-preview-card'),
              inspectorStarRow: rectFor('.inspector-star-row'),
            },
            images: {
              viewer: imageFor('[role="dialog"][aria-label="Image viewer"] img[alt="viewer"]'),
              viewerThumb: imageFor('[role="dialog"][aria-label="Image viewer"] img[alt="thumb"]'),
              compareA: imageFor('[role="dialog"][aria-label="Compare images"] img[alt="compare A"]'),
              compareB: imageFor('[role="dialog"][aria-label="Compare images"] img[alt="compare B"]'),
              compareThumbA: imageFor('[role="dialog"][aria-label="Compare images"] img[alt="thumb A"]'),
              compareThumbB: imageFor('[role="dialog"][aria-label="Compare images"] img[alt="thumb B"]'),
            },
            focus: {
              activeElement: describeElement(document.activeElement),
              browseShellInert: document.querySelector('[data-browse-shell]')?.hasAttribute('inert') ?? false,
              browseShellAriaHidden: document.querySelector('[data-browse-shell]')?.getAttribute('aria-hidden') ?? null,
              toolbarInert: document.querySelector('.toolbar-shell')?.hasAttribute('inert') ?? false,
              toolbarAriaHidden: document.querySelector('.toolbar-shell')?.getAttribute('aria-hidden') ?? null,
            },
            selection: {
              ariaSelectedCount: document.querySelectorAll('[role="gridcell"][aria-selected="true"]').length,
              liveText: elementText(document.querySelector('[aria-live="polite"]')),
            },
            leftPanel: leftPanel ? {
              clientWidth: leftPanel.clientWidth,
              scrollWidth: leftPanel.scrollWidth,
              rect: rectFor('.app-left-panel'),
              contentOpen: leftPanel.getAttribute('data-left-content-open'),
              activeTool: activeLeftTool,
              horizontalOverflow: leftPanel.scrollWidth > leftPanel.clientWidth + 1,
              contentOverflowCount: leftPanelContentChecks.filter((check) => check.overflowsPanel).length,
              contentOverflowExamples: leftPanelContentChecks.filter((check) => check.overflowsPanel).slice(0, 6),
              selectedMetricsCard: selectedMetricsCard ? {
                clientWidth: selectedMetricsCard.clientWidth,
                scrollWidth: selectedMetricsCard.scrollWidth,
                rect: rectPayload(selectedMetricsCard.getBoundingClientRect()),
                text: elementText(selectedMetricsCard).slice(0, 320),
                overflowsPanel: (() => {
                  const rect = selectedMetricsCard.getBoundingClientRect();
                  const panelRect = leftPanel.getBoundingClientRect();
                  return rect.left < panelRect.left - 1 || rect.right > panelRect.right + 1;
                })(),
                childOverflowCount: selectedMetricsChecks.filter((check) => check.overflowsPanel).length,
                checks: selectedMetricsChecks,
              } : null,
            } : null,
            inspector: panel ? {
              clientWidth: panel.clientWidth,
              scrollWidth: panel.scrollWidth,
              rect: rectFor('.app-right-panel'),
              checks: inspectorChecks,
            } : null,
            toolbarControls,
            themeMenu: {
              labels: Array.from(document.querySelectorAll('[role="menu"][aria-label="Theme settings"] [role^="menuitem"]'))
                .map((el) => elementText(el))
                .filter(Boolean),
            },
            storage: {
              leftOpen: localStorage.getItem('leftOpen'),
              rightOpen: localStorage.getItem('rightOpen'),
              leftFoldersWidth: localStorage.getItem('leftW.folders'),
              leftMetricsWidth: localStorage.getItem('leftW.metrics'),
              rightWidth: localStorage.getItem('rightW'),
            },
          };
        }""",
        {"name": name, "state": state or {}},
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


def assert_hidden_toolbar_controls_not_interactable(snapshot: dict[str, Any]) -> None:
    controls = snapshot.get("toolbarControls")
    if not isinstance(controls, list):
        raise ResponsiveGeometryFailure(f"Missing toolbar control evidence for {snapshot.get('name')!r}.")
    offenders = [
        str(control.get("name"))
        for control in controls
        if isinstance(control, dict)
        and not control.get("visible")
        and control.get("ariaHidden") != "true"
        and (control.get("hitTargetOk") or control.get("keyboardFocusable"))
    ]
    if offenders:
        raise ResponsiveGeometryFailure(
            f"Hidden toolbar controls are still reachable in {snapshot.get('name')}: "
            f"{', '.join(sorted(offenders))}."
        )


def _parse_px(raw: Any) -> float:
    if not isinstance(raw, str):
        return 0.0
    try:
        return float(raw.strip().removesuffix("px"))
    except ValueError:
        return 0.0


def _parse_float(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _require_rect(snapshot: dict[str, Any], rect_name: str) -> dict[str, Any]:
    rects = snapshot.get("rects")
    if not isinstance(rects, dict) or not isinstance(rects.get(rect_name), dict):
        raise ResponsiveGeometryFailure(
            f"Missing {rect_name} rect in {snapshot.get('name')!r}: {rects!r}."
        )
    return rects[rect_name]


def _rect_width(rect: dict[str, Any]) -> float:
    return _parse_float(rect.get("width"))


def _rect_left(rect: dict[str, Any]) -> float:
    return _parse_float(rect.get("left"))


def _rect_right(rect: dict[str, Any]) -> float:
    return _parse_float(rect.get("right"))


def _assert_close(
    *,
    actual: float,
    expected: float,
    tolerance: float,
    label: str,
    snapshot_name: Any,
) -> None:
    if abs(actual - expected) > tolerance:
        raise ResponsiveGeometryFailure(
            f"{label} mismatch in {snapshot_name}: actual={actual:.2f}, expected={expected:.2f}."
        )


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
    status_rect = rects.get("statusBand")
    if isinstance(status_rect, dict) and float(status_rect.get("height", 0)) > 1:
        if float(status_rect.get("top", 0)) + 1 < float(toolbar_rect.get("bottom", 0)):
            raise ResponsiveGeometryFailure(
                f"Status band starts under the mobile search toolbar in {snapshot.get('name')}."
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


def assert_theme_settings_reachable(snapshot: dict[str, Any]) -> None:
    rects = snapshot.get("rects")
    theme_menu = snapshot.get("themeMenu")
    if not isinstance(rects, dict) or not isinstance(rects.get("themeMenu"), dict):
        raise ResponsiveGeometryFailure(f"Theme settings menu is not visible in {snapshot.get('name')}.")
    labels = theme_menu.get("labels") if isinstance(theme_menu, dict) else None
    if not isinstance(labels, list):
        raise ResponsiveGeometryFailure(f"Missing theme settings labels in {snapshot.get('name')}.")
    required = ("Autoload image metadata", "Order compare by selection")
    missing = sorted(label for label in required if not any(label in candidate for candidate in labels))
    if missing:
        raise ResponsiveGeometryFailure(
            f"Theme settings drawer controls are missing in {snapshot.get('name')}: {missing!r}."
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


def assert_side_regions_visible(snapshot: dict[str, Any]) -> None:
    layout = snapshot.get("layout")
    if not isinstance(layout, dict):
        raise ResponsiveGeometryFailure(f"Missing layout evidence for {snapshot.get('name')!r}.")
    if _parse_float(layout.get("effectiveLeftWidth")) <= 0:
        raise ResponsiveGeometryFailure(f"Left side region is not visible in {snapshot.get('name')}: {layout!r}.")
    if _parse_float(layout.get("effectiveRightWidth")) <= 0:
        raise ResponsiveGeometryFailure(f"Right side region is not visible in {snapshot.get('name')}: {layout!r}.")
    left = _require_rect(snapshot, "leftSidebar")
    right = _require_rect(snapshot, "rightSidebar")
    if _rect_width(left) <= 1 or _rect_width(right) <= 1:
        raise ResponsiveGeometryFailure(
            f"Side region rects are not visible in {snapshot.get('name')}: left={left!r}, right={right!r}."
        )


def assert_overlay_contained_to_center(
    before: dict[str, Any],
    after: dict[str, Any],
    expected_mode: str,
) -> None:
    assert_side_regions_visible(before)
    assert_side_regions_visible(after)
    assert_overlay_isolated(after, expected_mode)

    before_layout = before.get("layout")
    after_layout = after.get("layout")
    if not isinstance(before_layout, dict) or not isinstance(after_layout, dict):
        raise ResponsiveGeometryFailure(f"Missing layout evidence for overlay containment in {after.get('name')}.")
    if after_layout.get("leftSuppressionReason") == "overlay-active":
        raise ResponsiveGeometryFailure(f"Overlay suppressed the left side region in {after.get('name')}.")
    if after_layout.get("rightSuppressionReason") == "overlay-active":
        raise ResponsiveGeometryFailure(f"Overlay suppressed the right side region in {after.get('name')}.")

    before_left = _require_rect(before, "leftSidebar")
    before_right = _require_rect(before, "rightSidebar")
    after_left = _require_rect(after, "leftSidebar")
    after_right = _require_rect(after, "rightSidebar")
    for label, before_rect, after_rect in (
        ("left side width", before_left, after_left),
        ("right side width", before_right, after_right),
    ):
        _assert_close(
            actual=_rect_width(after_rect),
            expected=_rect_width(before_rect),
            tolerance=1.0,
            label=label,
            snapshot_name=after.get("name"),
        )

    grid = _require_rect(after, "gridShell")
    overlay = _require_rect(after, "overlay")
    _assert_close(
        actual=_rect_left(overlay),
        expected=_rect_left(grid),
        tolerance=1.0,
        label="overlay left edge versus grid shell",
        snapshot_name=after.get("name"),
    )
    _assert_close(
        actual=_rect_right(overlay),
        expected=_rect_right(grid),
        tolerance=1.0,
        label="overlay right edge versus grid shell",
        snapshot_name=after.get("name"),
    )

    viewport = after.get("viewport")
    viewport_width = _parse_float(viewport.get("width")) if isinstance(viewport, dict) else 0.0
    if viewport_width > 0 and _rect_width(overlay) >= viewport_width - 1:
        raise ResponsiveGeometryFailure(
            f"Overlay spans the full viewport despite visible side regions in {after.get('name')}: {overlay!r}."
        )

    if expected_mode == "compare":
        stage = _require_rect(after, "compareStage")
        if _rect_left(stage) < _rect_left(overlay) - 1 or _rect_right(stage) > _rect_right(overlay) + 1:
            raise ResponsiveGeometryFailure(
                f"Compare stage escaped contained overlay in {after.get('name')}: "
                f"stage={stage!r}, overlay={overlay!r}."
            )


def sample_overlay_images(
    page: Any,
    name: str,
    *,
    frames: int = 30,
    interval_ms: int = 35,
) -> dict[str, Any]:
    evidence = page.evaluate(
        """async ({ name, frames, intervalMs }) => {
          const rectPayload = (rect) => ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          });
          const readImage = (selector) => {
            const el = document.querySelector(selector);
            if (!(el instanceof HTMLImageElement)) return null;
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return {
              selector,
              src: el.currentSrc || el.src || null,
              currentPath: el.getAttribute("data-current-path"),
              complete: el.complete,
              naturalWidth: el.naturalWidth,
              naturalHeight: el.naturalHeight,
              opacity: Number(style.opacity || "0"),
              display: style.display,
              visibility: style.visibility,
              rect: rectPayload(rect),
            };
          };
          const sleep = () => new Promise((resolve) => {
            requestAnimationFrame(() => window.setTimeout(resolve, intervalMs));
          });
          const startedAt = performance.now();
          const samples = [];
          for (let frame = 0; frame < frames; frame += 1) {
            await sleep();
            samples.push({
              frame,
              elapsedMs: Math.round(performance.now() - startedAt),
              images: {
                viewer: readImage('[role="dialog"][aria-label="Image viewer"] img[alt="viewer"]'),
                compareA: readImage('[role="dialog"][aria-label="Compare images"] img[alt="compare A"]'),
                compareB: readImage('[role="dialog"][aria-label="Compare images"] img[alt="compare B"]'),
              },
            });
          }
          return { name, frames, intervalMs, samples };
        }""",
        {"name": name, "frames": frames, "intervalMs": interval_ms},
    )
    if not isinstance(evidence, dict):
        raise ResponsiveGeometryFailure(f"Failed to sample overlay images for {name}.")
    return evidence


def _sample_image_visible(image: Any) -> bool:
    if not isinstance(image, dict):
        return False
    rect = image.get("rect")
    return (
        bool(image.get("complete"))
        and _parse_float(image.get("naturalWidth")) > 0
        and _parse_float(image.get("naturalHeight")) > 0
        and _parse_float(image.get("opacity")) > 0.05
        and image.get("display") != "none"
        and image.get("visibility") != "hidden"
        and isinstance(rect, dict)
        and _rect_width(rect) > 1
        and _parse_float(rect.get("height")) > 1
    )


def assert_overlay_image_stable(
    samples: dict[str, Any],
    required_images: tuple[str, ...],
    expected_paths: dict[str, str] | None = None,
) -> None:
    raw_samples = samples.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ResponsiveGeometryFailure(f"Missing image samples for {samples.get('name')!r}.")
    for image_name in required_images:
        seen_visible = False
        last_image: Any = None
        for sample in raw_samples:
            if not isinstance(sample, dict):
                continue
            images = sample.get("images")
            image = images.get(image_name) if isinstance(images, dict) else None
            last_image = image
            visible = _sample_image_visible(image)
            expected_path = expected_paths.get(image_name) if expected_paths else None
            if visible and expected_path is not None and image.get("currentPath") != expected_path:
                raise ResponsiveGeometryFailure(
                    f"{image_name} shows the wrong current path in {samples.get('name')}: "
                    f"expected={expected_path!r}, image={image!r}."
                )
            if visible:
                seen_visible = True
                continue
            if seen_visible:
                raise ResponsiveGeometryFailure(
                    f"{image_name} became invisible after becoming visible in {samples.get('name')}: "
                    f"frame={sample.get('frame')}, image={image!r}."
                )
        if not seen_visible:
            raise ResponsiveGeometryFailure(
                f"{image_name} did not become visibly loaded in {samples.get('name')}: last={last_image!r}."
            )


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


def assert_metrics_left_760_observed(snapshot: dict[str, Any]) -> None:
    state = snapshot.get("state")
    layout = snapshot.get("layout")
    storage = snapshot.get("storage")
    viewport = snapshot.get("viewport")
    selection = snapshot.get("selection")
    if not isinstance(state, dict) or state.get("activeLeftTool") != "metrics":
        raise ResponsiveGeometryFailure(f"Missing active metrics-left state for {snapshot.get('name')}.")
    if int(state.get("selectedCount", 0)) < 2:
        raise ResponsiveGeometryFailure(f"Metrics-left scenario did not keep selected items in {snapshot.get('name')}.")
    if not isinstance(selection, dict) or int(selection.get("ariaSelectedCount", 0)) < 2:
        raise ResponsiveGeometryFailure(f"Metrics-left DOM selection was not preserved in {snapshot.get('name')}.")
    if not isinstance(viewport, dict) or int(viewport.get("width", 0)) != 760:
        raise ResponsiveGeometryFailure(f"Metrics-left R10 observation must run at 760px: {viewport!r}.")
    if not isinstance(storage, dict) or storage.get("leftOpen") != "1" or storage.get("rightOpen") != "1":
        raise ResponsiveGeometryFailure(
            f"Metrics-left R10 observation must preserve both sidebar preferences: {storage!r}."
        )
    if not isinstance(layout, dict) or layout.get("mode") != "narrow":
        raise ResponsiveGeometryFailure(f"Metrics-left R10 observation expected narrow mode: {layout!r}.")

    effective_left_width = _parse_px(f"{layout.get('effectiveLeftWidth', '0')}px") if isinstance(layout, dict) else 0
    left_panel = snapshot.get("leftPanel")
    if effective_left_width <= 0:
        if layout.get("leftSuppressionReason") not in {"insufficient-center-space", "viewport-too-narrow"}:
            raise ResponsiveGeometryFailure(
                f"Metrics-left panel was suppressed for an unexpected reason in {snapshot.get('name')}: "
                f"{layout!r}."
            )
        return

    if not isinstance(left_panel, dict):
        raise ResponsiveGeometryFailure(f"Metrics-left panel is visible but missing evidence in {snapshot.get('name')}.")
    if left_panel.get("activeTool") != "metrics":
        raise ResponsiveGeometryFailure(f"Left panel did not render Metrics tool in {snapshot.get('name')}.")
    if left_panel.get("horizontalOverflow"):
        raise ResponsiveGeometryFailure(f"Metrics-left panel has horizontal overflow in {snapshot.get('name')}.")
    selected_card = left_panel.get("selectedMetricsCard")
    if not isinstance(selected_card, dict):
        raise ResponsiveGeometryFailure(f"Selected metrics summary is missing in {snapshot.get('name')}.")
    if selected_card.get("overflowsPanel") or int(selected_card.get("childOverflowCount", 0)) > 0:
        raise ResponsiveGeometryFailure(
            f"Selected metrics summary escaped the left panel in {snapshot.get('name')}: {selected_card!r}."
        )


def assert_visible_metrics_left_contained(snapshot: dict[str, Any]) -> None:
    selection = snapshot.get("selection")
    if not isinstance(selection, dict) or int(selection.get("ariaSelectedCount", 0)) < 2:
        raise ResponsiveGeometryFailure(f"Visible metrics-left scenario has fewer than 2 selected items in {snapshot.get('name')}.")
    left_panel = snapshot.get("leftPanel")
    if not isinstance(left_panel, dict):
        raise ResponsiveGeometryFailure(f"Visible metrics-left panel is missing in {snapshot.get('name')}.")
    if left_panel.get("activeTool") != "metrics":
        raise ResponsiveGeometryFailure(f"Visible left panel did not render Metrics tool in {snapshot.get('name')}.")
    if int(left_panel.get("contentOverflowCount", 0)) > 0:
        raise ResponsiveGeometryFailure(
            f"Visible metrics-left content escaped the panel in {snapshot.get('name')}: "
            f"{left_panel.get('contentOverflowExamples')!r}."
        )
    selected_card = left_panel.get("selectedMetricsCard")
    if not isinstance(selected_card, dict):
        raise ResponsiveGeometryFailure(f"Visible selected metrics summary is missing in {snapshot.get('name')}.")
    if float(selected_card.get("scrollWidth", 0)) > float(selected_card.get("clientWidth", 0)) + 1:
        raise ResponsiveGeometryFailure(
            f"Selected metrics summary has horizontal overflow in {snapshot.get('name')}: "
            f"scrollWidth={selected_card.get('scrollWidth')}, clientWidth={selected_card.get('clientWidth')}."
        )
    if selected_card.get("overflowsPanel") or int(selected_card.get("childOverflowCount", 0)) > 0:
        raise ResponsiveGeometryFailure(
            f"Selected metrics summary escaped the visible left panel in {snapshot.get('name')}: {selected_card!r}."
        )


def wait_for_shell(page: Any, timeout_ms: float) -> None:
    page.locator(".app-shell").wait_for(state="visible", timeout=timeout_ms)
    page.locator("[role='grid']").wait_for(state="visible", timeout=timeout_ms)


def visible_grid_cell_ids(page: Any) -> list[str]:
    raw = page.evaluate(
        """() => {
          const cells = Array.from(document.querySelectorAll('[role="gridcell"][id^="cell-"]'))
            .map((el) => {
              const rect = el.getBoundingClientRect();
              return { id: el.id, top: rect.top, left: rect.left, bottom: rect.bottom, right: rect.right };
            })
            .filter((entry) => entry.id && entry.bottom > 0 && entry.right > 0 && entry.top < window.innerHeight && entry.left < window.innerWidth);
          cells.sort((a, b) => (a.top - b.top) || (a.left - b.left));
          return cells.map((entry) => entry.id);
        }"""
    )
    if not isinstance(raw, list):
        raise ResponsiveGeometryFailure("Failed to evaluate visible grid cells.")
    return [candidate for candidate in raw if isinstance(candidate, str) and candidate.startswith("cell-")]


def wait_for_visible_grid_cell_ids(page: Any, minimum_count: int, timeout_ms: float) -> list[str]:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    latest_ids: list[str] = []
    while time.monotonic() < deadline:
        latest_ids = visible_grid_cell_ids(page)
        if len(latest_ids) >= minimum_count:
            return latest_ids
        page.wait_for_timeout(120)
    raise ResponsiveGeometryFailure(
        f"Timed out waiting for {minimum_count} visible grid cells. Last visible ids: {latest_ids!r}."
    )


def path_from_cell_id(cell_id: str) -> str:
    if not cell_id.startswith("cell-"):
        raise ResponsiveGeometryFailure(f"Unexpected grid cell id: {cell_id!r}.")
    return unquote(cell_id[5:])


def select_first_item(page: Any, timeout_ms: float) -> None:
    first_cell_id = wait_for_visible_grid_cell_ids(page, 1, timeout_ms)[0]
    page.locator(f"[id='{first_cell_id}']").click(timeout=timeout_ms)


def select_first_items(page: Any, count: int, timeout_ms: float) -> list[str]:
    if count < 1:
        return []
    cell_ids = wait_for_visible_grid_cell_ids(page, count, timeout_ms)[:count]
    page.locator(f"[id='{cell_ids[0]}']").click(timeout=timeout_ms)
    for cell_id in cell_ids[1:]:
        page.locator(f"[id='{cell_id}']").click(timeout=timeout_ms, modifiers=["Control"])
    return [path_from_cell_id(cell_id) for cell_id in cell_ids]


def select_first_two_items(page: Any, timeout_ms: float) -> None:
    select_first_items(page, 2, timeout_ms)


def open_metrics_left_panel(page: Any, timeout_ms: float) -> None:
    page.get_by_role("button", name="Metrics and Filters").first.click(timeout=timeout_ms)
    page.wait_for_timeout(150)


def open_first_viewer(page: Any, timeout_ms: float) -> str:
    first_cell_id = wait_for_visible_grid_cell_ids(page, 1, timeout_ms)[0]
    page.locator(f"[id='{first_cell_id}']").dblclick(timeout=timeout_ms)
    page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(state="visible", timeout=timeout_ms)
    return path_from_cell_id(first_cell_id)


def wait_for_viewer_path(page: Any, expected_path: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """(expectedPath) => {
          return document
            .querySelector('[role="dialog"][aria-label="Image viewer"]')
            ?.getAttribute('data-current-path') === expectedPath;
        }""",
        arg=expected_path,
        timeout=timeout_ms,
    )


def navigate_viewer_next(page: Any, expected_path: str, timeout_ms: float) -> None:
    page.locator('.toolbar-nav button[aria-label="Next image"]').click(timeout=timeout_ms)
    wait_for_viewer_path(page, expected_path, timeout_ms)


def wait_for_compare_paths(page: Any, expected_a_path: str, expected_b_path: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """([expectedAPath, expectedBPath]) => {
          const dialog = document.querySelector('[role="dialog"][aria-label="Compare images"]');
          return dialog?.getAttribute('data-compare-a-path') === expectedAPath
            && dialog?.getAttribute('data-compare-b-path') === expectedBPath;
        }""",
        arg=[expected_a_path, expected_b_path],
        timeout=timeout_ms,
    )


def navigate_compare_next(page: Any, expected_a_path: str, expected_b_path: str, timeout_ms: float) -> None:
    page.locator('[role="dialog"][aria-label="Compare images"] button[title^="Next"]').click(timeout=timeout_ms)
    wait_for_compare_paths(page, expected_a_path, expected_b_path, timeout_ms)


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
    snapshot = collect_snapshot(page, scenario.name, scenario_state(scenario))
    assert_no_document_overflow(snapshot)
    assert_no_visible_control_overlap(snapshot)
    assert_hidden_toolbar_controls_not_interactable(snapshot)
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
        assert_hidden_toolbar_controls_not_interactable(snapshot)
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
    assert_hidden_toolbar_controls_not_interactable(open_snapshot)
    assert_overlay_isolated(open_snapshot, "viewer")

    page.keyboard.press("Escape")
    page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(state="detached", timeout=timeout_ms)
    page.wait_for_timeout(100)
    closed_snapshot = collect_snapshot(page, "viewer-overlay-closed")
    assert_overlay_closed(closed_snapshot, "viewer-overlay-closed")

    page.set_viewport_size({"width": 1024, "height": 760})
    page.wait_for_timeout(200)
    desktop_before = collect_snapshot(page, "viewer-toolbar-before-1024x760")
    assert_no_document_overflow(desktop_before)
    assert_side_regions_visible(desktop_before)
    expected_viewer_paths = [
        path_from_cell_id(cell_id)
        for cell_id in wait_for_visible_grid_cell_ids(page, 2, timeout_ms)[:2]
    ]
    opened_path = open_first_viewer(page, timeout_ms)
    if opened_path != expected_viewer_paths[0]:
        raise ResponsiveGeometryFailure(
            f"Viewer opened unexpected path: {opened_path!r}, expected {expected_viewer_paths[0]!r}."
        )
    wait_for_viewer_path(page, expected_viewer_paths[0], timeout_ms)
    viewer_samples = sample_overlay_images(page, "viewer-toolbar-1024x760-samples")
    desktop_snapshot = collect_snapshot(page, "viewer-toolbar-1024x760")
    assert_no_document_overflow(desktop_snapshot)
    assert_hidden_toolbar_controls_not_interactable(desktop_snapshot)
    assert_overlay_contained_to_center(desktop_before, desktop_snapshot, "viewer")
    assert_overlay_image_stable(
        viewer_samples,
        ("viewer",),
        {"viewer": expected_viewer_paths[0]},
    )
    assert_viewer_toolbar_chrome(desktop_snapshot)

    navigate_viewer_next(page, expected_viewer_paths[1], timeout_ms)
    viewer_next_samples = sample_overlay_images(page, "viewer-toolbar-next-1024x760-samples")
    desktop_next_snapshot = collect_snapshot(page, "viewer-toolbar-next-1024x760")
    assert_no_document_overflow(desktop_next_snapshot)
    assert_hidden_toolbar_controls_not_interactable(desktop_next_snapshot)
    assert_overlay_contained_to_center(desktop_before, desktop_next_snapshot, "viewer")
    assert_overlay_image_stable(
        viewer_next_samples,
        ("viewer",),
        {"viewer": expected_viewer_paths[1]},
    )

    page.locator('[data-toolbar-control="back"]').click(timeout=timeout_ms)
    page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(state="detached", timeout=timeout_ms)
    page.wait_for_timeout(100)
    toolbar_closed_snapshot = collect_snapshot(page, "viewer-toolbar-closed")
    assert_overlay_closed(toolbar_closed_snapshot, "viewer-toolbar-closed")

    return {
        "name": "viewer-overlay",
        "steps": [
            open_snapshot,
            closed_snapshot,
            desktop_before,
            desktop_snapshot,
            desktop_next_snapshot,
            toolbar_closed_snapshot,
        ],
        "imageSamples": [viewer_samples, viewer_next_samples],
    }


def run_compare_overlay_scenario(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.add_init_script(seed_storage_script(scenario_storage()))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    compare_paths = select_first_items(page, 3, timeout_ms)
    page.wait_for_timeout(150)
    desktop_before = collect_snapshot(page, "compare-overlay-before-1440x900")
    assert_no_document_overflow(desktop_before)
    assert_side_regions_visible(desktop_before)
    page.locator('[aria-label="Compare selected images"]').click(timeout=timeout_ms)
    page.locator('[role="dialog"][aria-label="Compare images"]').wait_for(state="visible", timeout=timeout_ms)
    compare_samples = sample_overlay_images(page, "compare-overlay-1440x900-samples")
    desktop_open = collect_snapshot(page, "compare-overlay-1440x900")
    assert_no_document_overflow(desktop_open)
    assert_hidden_toolbar_controls_not_interactable(desktop_open)
    assert_overlay_contained_to_center(desktop_before, desktop_open, "compare")
    assert_overlay_image_stable(
        compare_samples,
        ("compareA", "compareB"),
        {"compareA": compare_paths[0], "compareB": compare_paths[1]},
    )

    navigate_compare_next(page, compare_paths[1], compare_paths[2], timeout_ms)
    compare_next_samples = sample_overlay_images(page, "compare-overlay-next-1440x900-samples")
    desktop_next_open = collect_snapshot(page, "compare-overlay-next-1440x900")
    assert_no_document_overflow(desktop_next_open)
    assert_hidden_toolbar_controls_not_interactable(desktop_next_open)
    assert_overlay_contained_to_center(desktop_before, desktop_next_open, "compare")
    assert_overlay_image_stable(
        compare_next_samples,
        ("compareA", "compareB"),
        {"compareA": compare_paths[1], "compareB": compare_paths[2]},
    )

    page.set_viewport_size({"width": 390, "height": 520})
    page.wait_for_timeout(300)
    page.keyboard.press("Tab")
    page.wait_for_timeout(100)
    open_snapshot = collect_snapshot(page, "compare-overlay-390x520")
    assert_no_document_overflow(open_snapshot)
    assert_hidden_toolbar_controls_not_interactable(open_snapshot)
    assert_overlay_isolated(open_snapshot, "compare")

    page.keyboard.press("Escape")
    page.locator('[role="dialog"][aria-label="Compare images"]').wait_for(state="detached", timeout=timeout_ms)
    page.wait_for_timeout(100)
    closed_snapshot = collect_snapshot(page, "compare-overlay-closed")
    assert_overlay_closed(closed_snapshot, "compare-overlay-closed")

    return {
        "name": "compare-overlay",
        "steps": [desktop_before, desktop_open, desktop_next_open, open_snapshot, closed_snapshot],
        "imageSamples": [compare_samples, compare_next_samples],
    }


def _request_path_param(url: str) -> str | None:
    try:
        values = parse_qs(urlparse(url).query).get("path")
    except Exception:
        return None
    if not values:
        return None
    return values[0]


def _requests_for_media_path(urls: list[str], *, route: str, media_path: str) -> list[str]:
    matches: list[str] = []
    route_path = f"/{route}"
    for url in urls:
        parsed = urlparse(url)
        if parsed.path != route_path:
            continue
        if _request_path_param(url) == media_path:
            matches.append(url)
    return matches


def wait_for_cell_thumb_ready(page: Any, cell_id: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """(cellId) => {
          const cell = document.getElementById(cellId);
          const img = cell?.querySelector('.cell-content img');
          return img instanceof HTMLImageElement && img.complete && img.naturalWidth > 0;
        }""",
        arg=cell_id,
        timeout=timeout_ms,
    )


def move_pointer_away(page: Any) -> None:
    page.mouse.move(2, 2)
    page.wait_for_timeout(80)


def dispatch_grid_scroll(page: Any) -> None:
    page.locator('[role="grid"][aria-label="Gallery"]').evaluate(
        """(el) => {
          el.scrollTop += Math.max(120, Math.floor(el.clientHeight / 3));
          el.dispatchEvent(new Event('scroll', { bubbles: true }));
        }"""
    )


def hover_preview_snapshot(page: Any, name: str, cell_id: str) -> dict[str, Any]:
    snapshot = page.evaluate(
        """({ name, cellId }) => {
          const rectPayload = (rect) => ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          });
          const imagePayload = (el) => {
            if (!(el instanceof HTMLImageElement)) return null;
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return {
              src: el.currentSrc || el.src || null,
              complete: el.complete,
              naturalWidth: el.naturalWidth,
              naturalHeight: el.naturalHeight,
              opacity: Number(style.opacity || "0"),
              display: style.display,
              visibility: style.visibility,
              rect: rectPayload(rect),
            };
          };
          const preview = document.querySelector('.grid-hover-preview');
          const previewImage = preview?.querySelector('img') || null;
          const cell = document.getElementById(cellId);
          const viewport = {
            width: window.innerWidth,
            height: window.innerHeight,
            left: 0,
            top: 0,
            right: window.innerWidth,
            bottom: window.innerHeight,
          };
          return {
            name,
            cellId,
            viewport,
            preview: preview ? {
              path: preview.getAttribute('data-preview-path'),
              rect: rectPayload(preview.getBoundingClientRect()),
            } : null,
            image: imagePayload(previewImage),
            cell: cell ? {
              rect: rectPayload(cell.getBoundingClientRect()),
            } : null,
          };
        }""",
        {"name": name, "cellId": cell_id},
    )
    if not isinstance(snapshot, dict):
        raise ResponsiveGeometryFailure(f"Failed to collect hover preview snapshot for {name}.")
    return snapshot


def assert_hover_preview_large_original(
    snapshot: dict[str, Any],
    *,
    expected_path: str,
    media_requests: list[str],
) -> None:
    preview = snapshot.get("preview")
    image = snapshot.get("image")
    cell = snapshot.get("cell")
    viewport = snapshot.get("viewport")
    if not isinstance(preview, dict) or preview.get("path") != expected_path:
        raise ResponsiveGeometryFailure(
            f"Hover preview path mismatch in {snapshot.get('name')}: "
            f"expected={expected_path!r}, preview={preview!r}."
        )
    if not isinstance(image, dict) or not _sample_image_visible(image):
        raise ResponsiveGeometryFailure(f"Hover preview image is not visibly loaded in {snapshot.get('name')}: {image!r}.")
    if not isinstance(cell, dict) or not isinstance(cell.get("rect"), dict):
        raise ResponsiveGeometryFailure(f"Missing hover source cell rect in {snapshot.get('name')}: {cell!r}.")
    if not isinstance(viewport, dict):
        raise ResponsiveGeometryFailure(f"Missing hover viewport evidence in {snapshot.get('name')}.")

    preview_rect = preview.get("rect")
    image_rect = image.get("rect")
    cell_rect = cell["rect"]
    if not isinstance(preview_rect, dict) or not isinstance(image_rect, dict):
        raise ResponsiveGeometryFailure(f"Missing hover preview rects in {snapshot.get('name')}: {snapshot!r}.")

    viewport_width = _parse_float(viewport.get("width"))
    viewport_height = _parse_float(viewport.get("height"))
    image_width = _rect_width(image_rect)
    image_height = _parse_float(image_rect.get("height"))
    cell_width = _rect_width(cell_rect)
    cell_height = _parse_float(cell_rect.get("height"))
    if image_width <= cell_width * 2 or image_height <= cell_height * 2:
        raise ResponsiveGeometryFailure(
            f"Hover preview image is not materially larger than the source cell in {snapshot.get('name')}: "
            f"image={image_rect!r}, cell={cell_rect!r}."
        )
    if image_width < viewport_width * 0.65 or image_height < viewport_height * 0.65:
        raise ResponsiveGeometryFailure(
            f"Hover preview image is not close to restored viewport-sized bounds in {snapshot.get('name')}: "
            f"image={image_rect!r}, viewport={viewport!r}."
        )

    expected_left = (viewport_width - _rect_width(preview_rect)) / 2
    expected_top = (viewport_height - _parse_float(preview_rect.get("height"))) / 2
    _assert_close(
        actual=_rect_left(preview_rect),
        expected=expected_left,
        tolerance=2.0,
        label="hover preview centered left edge",
        snapshot_name=snapshot.get("name"),
    )
    _assert_close(
        actual=_parse_float(preview_rect.get("top")),
        expected=expected_top,
        tolerance=2.0,
        label="hover preview centered top edge",
        snapshot_name=snapshot.get("name"),
    )
    if _rect_left(preview_rect) < 7 or _rect_right(preview_rect) > viewport_width - 7:
        raise ResponsiveGeometryFailure(
            f"Hover preview escaped horizontal viewport bounds in {snapshot.get('name')}: {preview_rect!r}."
        )
    if _parse_float(preview_rect.get("top")) < 7 or _parse_float(preview_rect.get("bottom")) > viewport_height - 7:
        raise ResponsiveGeometryFailure(
            f"Hover preview escaped vertical viewport bounds in {snapshot.get('name')}: {preview_rect!r}."
        )

    file_requests = _requests_for_media_path(media_requests, route="file", media_path=expected_path)
    thumb_requests = _requests_for_media_path(media_requests, route="thumb", media_path=expected_path)
    if not file_requests:
        raise ResponsiveGeometryFailure(
            f"Hover preview did not request the original file for {expected_path!r}: {media_requests!r}."
        )
    if thumb_requests:
        raise ResponsiveGeometryFailure(
            f"Hover preview requested thumbnail content for {expected_path!r}: {thumb_requests!r}."
        )


def run_hover_preview_scenario(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.add_init_script(seed_storage_script(scenario_storage()))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    cell_id = wait_for_visible_grid_cell_ids(page, 2, timeout_ms)[-1]
    expected_path = path_from_cell_id(cell_id)
    wait_for_cell_thumb_ready(page, cell_id, timeout_ms)
    hotspot = page.locator(f"[id='{cell_id}'] .grid-item-preview-hotspot")

    move_pointer_away(page); hotspot.hover(timeout=timeout_ms); page.wait_for_timeout(100)
    dispatch_grid_scroll(page); page.wait_for_timeout(500)
    pending_count = page.locator(".grid-hover-preview").count()
    if pending_count: raise ResponsiveGeometryFailure(f"Pending hover preview survived scroll cancellation with {pending_count} preview(s).")

    held: dict[str, Any] = {}
    def hold_hover_file(route: Any, request: Any) -> None:
        if urlparse(request.url).path == "/file" and _request_path_param(request.url) == expected_path and "route" not in held:
            held["route"] = route; return
        route.continue_()
    page.route("**/file?**", hold_hover_file)
    try:
        page.wait_for_timeout(250); move_pointer_away(page); hotspot.hover(timeout=timeout_ms)
        for _ in range(40):
            if "route" in held: break
            page.wait_for_timeout(50)
        if "route" not in held: raise ResponsiveGeometryFailure(f"Delayed hover /file request did not start for {expected_path!r}.")
        dispatch_grid_scroll(page); page.wait_for_timeout(120)
        try:
            held["route"].continue_()
        except Exception as exc:
            held["releaseError"] = str(exc)
        page.wait_for_timeout(450)
        delayed_count = page.locator(".grid-hover-preview").count()
        if delayed_count: raise ResponsiveGeometryFailure(f"Delayed hover /file response reached the DOM after scroll clear with {delayed_count} preview(s).")
    finally:
        page.unroute("**/file?**", hold_hover_file)

    page.wait_for_timeout(250)
    media_requests: list[str] = []

    def record_request(request: Any) -> None:
        media_requests.append(request.url)

    page.on("request", record_request)
    try:
        move_pointer_away(page)
        hotspot.hover(timeout=timeout_ms)
        page.locator(".grid-hover-preview img").first.wait_for(state="visible", timeout=timeout_ms)
        snapshot = hover_preview_snapshot(page, "hover-preview-original-file-1440x900", cell_id)
        assert_hover_preview_large_original(
            snapshot,
            expected_path=expected_path,
            media_requests=media_requests,
        )

        dispatch_grid_scroll(page)
        page.locator(".grid-hover-preview").wait_for(state="detached", timeout=timeout_ms)
        cleared_count = page.locator(".grid-hover-preview").count()
        if cleared_count:
            raise ResponsiveGeometryFailure(
                f"Active hover preview survived scroll cancellation with {cleared_count} preview(s)."
            )
    finally:
        try:
            page.remove_listener("request", record_request)
        except Exception:
            pass

    return {
        "name": "hover-preview",
        "expectedPath": expected_path,
        "mediaRequests": media_requests,
        "snapshot": snapshot,
        "pendingScrollCancelPreviewCount": pending_count,
        "delayedFileStalePreviewCount": delayed_count,
        "delayedFileReleaseError": held.get("releaseError"),
        "activeScrollCancelPreviewCount": cleared_count,
    }


def run_metrics_left_760_scenario(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 900, "height": 760})
    page.add_init_script(seed_storage_script(scenario_storage()))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    select_first_two_items(page, timeout_ms)
    open_metrics_left_panel(page, timeout_ms)
    page.wait_for_timeout(250)
    before_state = {
        "activeLeftTool": "metrics",
        "selectedCount": 2,
        "bothSidebarPreferencesOpen": True,
        "purpose": "R10 selected-metrics observation before 760px resize",
    }
    before = collect_snapshot(page, "metrics-left-selected-before-900x760", before_state)
    assert_no_document_overflow(before)
    assert_no_visible_control_overlap(before)
    assert_hidden_toolbar_controls_not_interactable(before)
    assert_visible_metrics_left_contained(before)

    page.set_viewport_size({"width": 760, "height": 700})
    page.wait_for_timeout(300)
    after_state = {
        "activeLeftTool": "metrics",
        "selectedCount": 2,
        "bothSidebarPreferencesOpen": True,
        "purpose": "R10 metrics-left/both-sidebars-preferred-open selected-items observation",
    }
    after = collect_snapshot(page, "metrics-left-selected-760x700", after_state)
    assert_no_document_overflow(after)
    assert_no_visible_control_overlap(after)
    assert_hidden_toolbar_controls_not_interactable(after)
    assert_mobile_drawer_reachable(after)
    assert_metrics_left_760_observed(after)

    return {
        "name": "metrics-left-760-r10-observation",
        "steps": [before, after],
    }


def run_mobile_drawer_theme_scenario(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 320, "height": 700})
    page.add_init_script(seed_storage_script(scenario_storage()))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    page.locator('[data-toolbar-control="drawer-theme"] button').click(timeout=timeout_ms)
    page.locator('[role="menu"][aria-label="Theme settings"]').wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_timeout(100)
    snapshot = collect_snapshot(
        page,
        "mobile-drawer-theme-settings-320x700",
        {"width": 320, "height": 700, "drawerThemeMenuOpen": True},
    )
    assert_no_document_overflow(snapshot)
    assert_mobile_drawer_reachable(snapshot)
    assert_theme_settings_reachable(snapshot)
    return snapshot


def write_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def launch_lenslet_with_log(
    source_path: Path,
    *,
    host: str,
    port: int,
    cwd: Path,
    log_path: Path,
) -> subprocess.Popen[Any]:
    command = [
        sys.executable,
        "-m",
        "lenslet.cli",
        str(source_path),
        "--host",
        host,
        "--port",
        str(port),
        "--verbose",
    ]
    log_handle = log_path.open("w", encoding="utf-8")
    try:
        return subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
    finally:
        log_handle.close()


def read_log_tail(path: Path, line_count: int = 40) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return "<unavailable>"
    return "\n".join(lines[-line_count:])


def record_failure(
    *,
    evidence: dict[str, Any],
    page: Any,
    screenshot_dir: Path,
    scenario_name: str,
    error: Exception,
) -> None:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot = screenshot_dir / f"{scenario_name}.png"
    page.screenshot(path=str(screenshot), full_page=True)
    failure: dict[str, Any] = {
        "scenario": scenario_name,
        "error": str(error),
        "screenshot": str(screenshot),
    }
    try:
        failure["snapshot"] = collect_snapshot(
            page,
            f"{scenario_name}-failure",
            {"failedScenario": scenario_name},
        )
    except Exception as snapshot_error:
        failure["snapshotError"] = str(snapshot_error)
    evidence["failures"].append(failure)


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
    log_file = tempfile.NamedTemporaryFile(
        prefix="lenslet-responsive-server-",
        suffix=".log",
        delete=False,
    )
    server_log = Path(log_file.name)
    log_file.close()
    process = launch_lenslet_with_log(
        dataset_dir,
        host=args.host,
        port=port,
        cwd=repo_root,
        log_path=server_log,
    )
    started_at = time.time()
    evidence: dict[str, Any] = {
        "evidenceVersion": 2,
        "baseUrl": base_url,
        "datasetDir": str(dataset_dir),
        "serverLog": str(server_log),
        "startedAt": started_at,
        "scenarios": [],
        "failures": [],
        "warnings": [],
    }

    _, _, sync_playwright = import_playwright()
    try:
        initial_health = wait_for_health(base_url, args.server_timeout_seconds)
        evidence["initialHealth"] = initial_health
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
                        "narrow-search-open-760",
                        760,
                        760,
                        scenario_storage(),
                        open_mobile_search=True,
                    ),
                    Scenario(
                        "narrow-search-open-900",
                        900,
                        760,
                        scenario_storage(),
                        open_mobile_search=True,
                    ),
                    Scenario(
                        "short-search-open-760",
                        760,
                        430,
                        scenario_storage(),
                        open_mobile_search=True,
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
                    page.set_default_timeout(args.browser_timeout_ms)
                    try:
                        evidence["scenarios"].append(
                            run_scenario(page, base_url, scenario, args.browser_timeout_ms)
                        )
                    except Exception as exc:
                        record_failure(
                            evidence=evidence,
                            page=page,
                            screenshot_dir=args.screenshot_dir,
                            scenario_name=scenario.name,
                            error=exc,
                        )
                        raise
                    finally:
                        context.close()

                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()
                page.set_default_timeout(args.browser_timeout_ms)
                try:
                    evidence["scenarios"].append(
                        run_resize_persistence_scenario(page, base_url, args.browser_timeout_ms)
                    )
                except Exception as exc:
                    record_failure(
                        evidence=evidence,
                        page=page,
                        screenshot_dir=args.screenshot_dir,
                        scenario_name="resize-persistence",
                        error=exc,
                    )
                    raise
                finally:
                    context.close()

                context = browser.new_context(viewport={"width": 900, "height": 760})
                page = context.new_page()
                page.set_default_timeout(args.browser_timeout_ms)
                try:
                    evidence["scenarios"].append(
                        run_metrics_left_760_scenario(page, base_url, args.browser_timeout_ms)
                    )
                except Exception as exc:
                    record_failure(
                        evidence=evidence,
                        page=page,
                        screenshot_dir=args.screenshot_dir,
                        scenario_name="metrics-left-760-r10-observation",
                        error=exc,
                    )
                    raise
                finally:
                    context.close()

                context = browser.new_context(
                    viewport={"width": 320, "height": 700},
                    has_touch=True,
                    is_mobile=True,
                )
                page = context.new_page()
                page.set_default_timeout(args.browser_timeout_ms)
                try:
                    evidence["scenarios"].append(
                        run_mobile_drawer_theme_scenario(page, base_url, args.browser_timeout_ms)
                    )
                except Exception as exc:
                    record_failure(
                        evidence=evidence,
                        page=page,
                        screenshot_dir=args.screenshot_dir,
                        scenario_name="mobile-drawer-theme-settings",
                        error=exc,
                    )
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
                    page.set_default_timeout(args.browser_timeout_ms)
                    try:
                        evidence["scenarios"].append(runner(page, base_url, args.browser_timeout_ms))
                    except Exception as exc:
                        record_failure(
                            evidence=evidence,
                            page=page,
                            screenshot_dir=args.screenshot_dir,
                            scenario_name=scenario_name,
                            error=exc,
                        )
                        raise
                    finally:
                        context.close()

                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()
                page.set_default_timeout(args.browser_timeout_ms)
                try:
                    evidence["scenarios"].append(
                        run_hover_preview_scenario(page, base_url, args.browser_timeout_ms)
                    )
                except Exception as exc:
                    record_failure(
                        evidence=evidence,
                        page=page,
                        screenshot_dir=args.screenshot_dir,
                        scenario_name="hover-preview",
                        error=exc,
                    )
                    raise
                finally:
                    context.close()
            finally:
                browser.close()
        evidence["finalHealth"] = wait_for_health(base_url, args.server_timeout_seconds)
        evidence["status"] = "passed"
    except Exception as exc:
        evidence["error"] = str(exc)
        evidence["status"] = "failed"
        evidence["serverLogTail"] = read_log_tail(server_log)
        evidence["finishedAt"] = time.time()
        evidence["durationSeconds"] = round(float(evidence["finishedAt"]) - started_at, 3)
        write_evidence(args.output_json, evidence)
        raise SystemExit(1) from exc
    finally:
        if "finishedAt" not in evidence:
            evidence["finishedAt"] = time.time()
            evidence["durationSeconds"] = round(float(evidence["finishedAt"]) - started_at, 3)
        stop_process(process)
        if dataset_tmp is not None and not args.keep_dataset:
            shutil.rmtree(dataset_tmp, ignore_errors=True)

    write_evidence(args.output_json, evidence)
    print(f"Wrote responsive geometry evidence to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
