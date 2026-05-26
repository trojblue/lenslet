#!/usr/bin/env python3
"""Incremental browser evidence for the overall cleanup plan.

The script intentionally starts with the Sprint 1 comparison-export path and a
small layout snapshot. Later cleanup sprints should extend this file with their
new browser-facing assertions instead of creating parallel one-off harnesses.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from PIL import Image

from smoke_harness import choose_port, import_playwright, stop_process, wait_for_health


class OverallCleanupBrowserFailure(RuntimeError):
    """Raised when the browser cleanup evidence path fails."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Lenslet overall-cleanup browser evidence.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7070)
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--keep-dataset", action="store_true")
    parser.add_argument("--server-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--browser-timeout-ms", type=float, default=30_000)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/tmp/lenslet-overall-cleanup-browser.json"),
        help="Path for machine-readable cleanup evidence.",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=Path("/tmp/lenslet-overall-cleanup-browser-screenshots"),
        help="Directory for screenshots captured on scenario failure.",
    )
    parser.add_argument(
        "--only-sprint1",
        action="store_true",
        help="Run only interaction-polish preflight and Sprint 1 browser evidence.",
    )
    return parser.parse_args()


def build_fixture_dataset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    colors = (
        (215, 80, 75),
        (74, 150, 92),
        (64, 112, 202),
        (222, 171, 66),
        (126, 91, 180),
        (42, 164, 176),
        (202, 96, 148),
        (86, 86, 96),
    )
    sizes = (
        (1000, 100),
        (100, 100),
        (100, 100),
        (100, 100),
        (400, 100),
        (100, 800),
        (160, 320),
        (1600, 1200),
    )
    for idx, (color, size) in enumerate(zip(colors, sizes)):
        path = root / f"cleanup_fixture_{idx:02d}.png"
        path.write_bytes(_png_payload(size=size, color=color))
    nested = root / "cleanup_nested"
    nested.mkdir(exist_ok=True)
    (nested / "cleanup_fixture_nested.png").write_bytes(
        _png_payload(size=(640, 360), color=(118, 142, 62))
    )


def _png_payload(*, size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def visible_grid_cell_ids(page: Any) -> list[str]:
    raw = page.evaluate(
        """() => {
          const cells = Array.from(document.querySelectorAll('[role="gridcell"][id^="cell-"]'))
            .map((el) => {
              const rect = el.getBoundingClientRect()
              return {
                id: el.id,
                top: rect.top,
                left: rect.left,
                bottom: rect.bottom,
                right: rect.right,
              }
            })
            .filter((entry) => (
              entry.id &&
              entry.bottom > 0 &&
              entry.right > 0 &&
              entry.top < window.innerHeight &&
              entry.left < window.innerWidth
            ))
          cells.sort((a, b) => (a.top - b.top) || (a.left - b.left))
          return cells.map((entry) => entry.id)
        }""",
    )
    if not isinstance(raw, list):
        raise OverallCleanupBrowserFailure("Failed to evaluate visible grid cells.")
    return [cell_id for cell_id in raw if isinstance(cell_id, str) and cell_id.startswith("cell-")]


def wait_for_visible_grid_cell_ids(page: Any, minimum_count: int, timeout_ms: float) -> list[str]:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    latest_ids: list[str] = []
    while time.monotonic() < deadline:
        latest_ids = visible_grid_cell_ids(page)
        if len(latest_ids) >= minimum_count:
            return latest_ids
        page.wait_for_timeout(120)
    raise OverallCleanupBrowserFailure(
        f"Expected at least {minimum_count} visible grid cells; last visible ids={latest_ids!r}."
    )


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


def select_two_visible_images(page: Any, timeout_ms: float) -> list[str]:
    cell_ids = wait_for_visible_grid_cell_ids(page, minimum_count=2, timeout_ms=timeout_ms)
    first_cell_id = cell_ids[0]
    second_cell_id = next((cell_id for cell_id in cell_ids if cell_id != first_cell_id), None)
    if second_cell_id is None:
        raise OverallCleanupBrowserFailure(f"No distinct second grid cell in {cell_ids!r}.")

    page.locator(f"[id='{first_cell_id}']").first.click()
    page.locator(f"[id='{second_cell_id}']").first.click(modifiers=["Control"])
    page.get_by_text("2 files").first.wait_for(state="visible")
    return [first_cell_id, second_cell_id]


def collect_layout_evidence(page: Any, name: str) -> dict[str, Any]:
    return page.evaluate(
        """(name) => {
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
          const rectFor = (selector) => {
            const el = document.querySelector(selector)
            return el ? rectPayload(el.getBoundingClientRect()) : null
          }
          const visibleCells = Array.from(document.querySelectorAll('[role="gridcell"][id^="cell-"]'))
            .map((el) => {
              const rect = el.getBoundingClientRect()
              return { id: el.id, rect: rectPayload(rect) }
            })
            .filter((entry) => (
              entry.rect &&
              entry.rect.bottom > 0 &&
              entry.rect.right > 0 &&
              entry.rect.top < window.innerHeight &&
              entry.rect.left < window.innerWidth
            ))
            .slice(0, 8)
          const visualViewport = window.visualViewport ? {
            width: window.visualViewport.width,
            height: window.visualViewport.height,
            offsetLeft: window.visualViewport.offsetLeft,
            offsetTop: window.visualViewport.offsetTop,
            scale: window.visualViewport.scale,
          } : null
          return {
            name,
            viewport: {
              innerWidth: window.innerWidth,
              innerHeight: window.innerHeight,
              devicePixelRatio: window.devicePixelRatio,
              visualViewport,
            },
            grid: rectFor('[role="grid"][aria-label="Gallery"]'),
            rightPanel: rectFor('.app-right-panel'),
            compareDialog: rectFor('[role="dialog"][aria-label="Compare images"]'),
            selectedCellCount: document.querySelectorAll('[role="gridcell"][aria-selected="true"]').length,
            visibleCells,
            exportButtonCount: Array.from(document.querySelectorAll('button'))
              .filter((button) => (button.textContent || '').includes('Export comparison')).length,
          }
        }""",
        name,
    )


def collect_adaptive_geometry_evidence(page: Any, name: str) -> dict[str, Any]:
    return page.evaluate(
        """(name) => {
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
          const grid = document.querySelector('[role="grid"][aria-label="Gallery"]')
          const gridRect = grid ? rectPayload(grid.getBoundingClientRect()) : null
          const rows = grid ? Array.from(grid.querySelectorAll('[role="row"]')).map((row, rowIndex) => {
            const rowRect = row.getBoundingClientRect()
            const cells = Array.from(row.querySelectorAll('[role="gridcell"][id^="cell-"]')).map((cell) => {
              const rect = cell.getBoundingClientRect()
              return {
                id: cell.id,
                fit: cell.getAttribute('data-adaptive-fit') || null,
                rect: rectPayload(rect),
              }
            })
            return {
              rowIndex,
              rect: rectPayload(rowRect),
              imageHeight: Number(row.getAttribute('data-adaptive-image-height')),
              cells,
            }
          }) : []
          const bodyText = document.body ? document.body.innerText : ''
          const desktopSort = document.querySelector('button[aria-label="Sort and layout"]')
          const mobileJustified = document.querySelector('[data-toolbar-control="drawer-layout-masonry"]')
          const visualViewport = window.visualViewport ? {
            width: window.visualViewport.width,
            height: window.visualViewport.height,
            offsetLeft: window.visualViewport.offsetLeft,
            offsetTop: window.visualViewport.offsetTop,
            scale: window.visualViewport.scale,
          } : null
          return {
            name,
            viewport: {
              innerWidth: window.innerWidth,
              innerHeight: window.innerHeight,
              visualViewport,
            },
            grid: gridRect,
            rows,
            labels: {
              desktopSort: desktopSort ? desktopSort.textContent.trim() : '',
              mobileJustified: mobileJustified ? mobileJustified.textContent.trim() : '',
              bodyIncludesJustifiedRows: bodyText.includes('Justified rows'),
              bodyIncludesLegacyMasonry: bodyText.includes('Masonry'),
            },
          }
        }""",
        name,
    )


def assert_adaptive_geometry(snapshot: dict[str, Any]) -> None:
    name = str(snapshot.get("name", "<unknown>"))
    grid = snapshot.get("grid")
    rows = snapshot.get("rows")
    labels = snapshot.get("labels")
    if not isinstance(grid, dict):
        raise OverallCleanupBrowserFailure(f"Missing adaptive grid bounds for {name}.")
    if not isinstance(rows, list) or len(rows) < 3:
        observed_rows = len(rows) if isinstance(rows, list) else rows
        raise OverallCleanupBrowserFailure(
            f"Expected at least 3 adaptive rows for {name}; got {observed_rows!r}."
        )
    if not isinstance(labels, dict):
        raise OverallCleanupBrowserFailure(f"Missing adaptive label evidence for {name}.")
    mobile_label = str(labels.get("mobileJustified") or "")
    if mobile_label and mobile_label != "Justified rows":
        raise OverallCleanupBrowserFailure(
            f"Unexpected mobile adaptive label in {name}: {mobile_label!r}."
        )
    if labels.get("bodyIncludesLegacyMasonry"):
        raise OverallCleanupBrowserFailure(f"Legacy Masonry label is still visible for {name}.")

    min_image_height = 220 * 0.65
    max_image_height = 220 * 1.35
    tolerance = 1.5
    contained_count = 0
    grid_left = float(grid.get("left", 0))
    grid_right = float(grid.get("right", 0))
    for row in rows:
        if not isinstance(row, dict):
            raise OverallCleanupBrowserFailure(
                f"Malformed adaptive row evidence for {name}: {row!r}."
            )
        image_height = float(row.get("imageHeight", 0))
        row_index = row.get("rowIndex")
        if image_height < min_image_height - tolerance:
            raise OverallCleanupBrowserFailure(
                f"Adaptive row {row_index} is too short in {name}: {image_height:.1f}px."
            )
        if image_height > max_image_height + tolerance:
            raise OverallCleanupBrowserFailure(
                f"Adaptive row {row_index} is too tall in {name}: {image_height:.1f}px."
            )
        cells = row.get("cells")
        if not isinstance(cells, list) or not cells:
            raise OverallCleanupBrowserFailure(f"Adaptive row {row_index} has no cells in {name}.")
        for cell in cells:
            if not isinstance(cell, dict):
                raise OverallCleanupBrowserFailure(
                    f"Malformed adaptive cell evidence for {name}: {cell!r}."
                )
            rect = cell.get("rect")
            if not isinstance(rect, dict):
                raise OverallCleanupBrowserFailure(
                    f"Missing adaptive cell rect for {cell.get('id')} in {name}."
                )
            left = float(rect.get("left", 0))
            right = float(rect.get("right", 0))
            if left < grid_left - tolerance or right > grid_right + tolerance:
                raise OverallCleanupBrowserFailure(
                    f"Adaptive cell {cell.get('id')} overflows grid in {name}: "
                    f"{left:.1f}..{right:.1f} outside {grid_left:.1f}..{grid_right:.1f}."
                )
            if cell.get("fit") == "contain":
                contained_count += 1

    if contained_count < 2:
        raise OverallCleanupBrowserFailure(
            f"Expected contained panorama/tall rows in {name}; observed {contained_count}."
        )


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


def capture_context_screenshots(contexts: list[Any], screenshot_dir: Path, prefix: str) -> list[str]:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for context_index, context in enumerate(contexts):
        for page_index, page in enumerate(context.pages):
            try:
                if page.is_closed():
                    continue
                path = screenshot_dir / f"{prefix}_{context_index}_{page_index}.png"
                page.screenshot(path=str(path), full_page=True)
                paths.append(str(path))
            except Exception:
                continue
    return paths


def screenshot_suffix(paths: list[str]) -> str:
    if not paths:
        return ""
    return f" Screenshots: {', '.join(paths)}"


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


def wait_for_image_ready(page: Any, selector: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """(selector) => {
          const img = document.querySelector(selector)
          if (!(img instanceof HTMLImageElement)) return false
          const opacity = Number(window.getComputedStyle(img).opacity || '0')
          return img.complete && img.naturalWidth > 0 && img.naturalHeight > 0 && opacity > 0.5
        }""",
        arg=selector,
        timeout=timeout_ms,
    )


def collect_transformed_image_center(
    page: Any,
    *,
    container_selector: str,
    image_selector: str,
    name: str,
) -> dict[str, Any]:
    snapshot = page.evaluate(
        """({ containerSelector, imageSelector, name }) => {
          const rectPayload = (rect) => ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          })
          const container = document.querySelector(containerSelector)
          const img = document.querySelector(imageSelector)
          if (!container || !(img instanceof HTMLImageElement)) return null
          const containerRect = container.getBoundingClientRect()
          const transform = window.getComputedStyle(img).transform
          const matrix = new DOMMatrixReadOnly(transform && transform !== 'none' ? transform : undefined)
          const scaleX = matrix.a
          const scaleY = matrix.d
          if (!scaleX || !scaleY || !img.naturalWidth || !img.naturalHeight) return null
          return {
            name,
            container: rectPayload(containerRect),
            naturalWidth: img.naturalWidth,
            naturalHeight: img.naturalHeight,
            transform: {
              scaleX,
              scaleY,
              tx: matrix.e,
              ty: matrix.f,
            },
            normalizedCenter: {
              x: ((containerRect.width / 2) - matrix.e) / (img.naturalWidth * scaleX),
              y: ((containerRect.height / 2) - matrix.f) / (img.naturalHeight * scaleY),
            },
          }
        }""",
        {
            "containerSelector": container_selector,
            "imageSelector": image_selector,
            "name": name,
        },
    )
    if not isinstance(snapshot, dict):
        raise OverallCleanupBrowserFailure(f"Failed to collect transformed image center for {name}.")
    return snapshot


def assert_center_preserved(before: dict[str, Any], after: dict[str, Any], *, tolerance: float = 0.055) -> None:
    before_center = before.get("normalizedCenter")
    after_center = after.get("normalizedCenter")
    if not isinstance(before_center, dict) or not isinstance(after_center, dict):
        raise OverallCleanupBrowserFailure(f"Missing normalized centers: before={before!r}, after={after!r}.")
    container = after.get("container")
    transform = after.get("transform")
    if not isinstance(container, dict) or not isinstance(transform, dict):
        raise OverallCleanupBrowserFailure(f"Missing rendered bounds for resize comparison: after={after!r}.")
    rendered_width = float(after.get("naturalWidth", 0)) * float(transform.get("scaleX", 0))
    rendered_height = float(after.get("naturalHeight", 0)) * float(transform.get("scaleY", 0))
    width = float(container.get("width", 0))
    height = float(container.get("height", 0))
    axis_deltas: dict[str, float] = {}
    if rendered_width > width + 1.5:
        axis_deltas["x"] = abs(float(before_center.get("x", 0)) - float(after_center.get("x", 0)))
    if rendered_height > height + 1.5:
        axis_deltas["y"] = abs(float(before_center.get("y", 0)) - float(after_center.get("y", 0)))
    if not axis_deltas:
        return
    failed = {axis: delta for axis, delta in axis_deltas.items() if delta > tolerance}
    if failed:
        raise OverallCleanupBrowserFailure(
            f"{after.get('name')} center drifted after resize on pannable axes: "
            f"deltas={failed!r}, before={before_center!r}, after={after_center!r}."
        )


def assert_transform_stable(before: dict[str, Any], after: dict[str, Any], name: str) -> None:
    before_transform = before.get("transform")
    after_transform = after.get("transform")
    if not isinstance(before_transform, dict) or not isinstance(after_transform, dict):
        raise OverallCleanupBrowserFailure(f"Missing transform evidence for {name}: before={before!r}, after={after!r}.")
    limits = {"scaleX": 0.01, "scaleY": 0.01, "tx": 1.0, "ty": 1.0}
    drift = {
        key: abs(float(before_transform.get(key, 0)) - float(after_transform.get(key, 0)))
        for key in limits
    }
    failed = {key: value for key, value in drift.items() if value > limits[key]}
    if failed:
        raise OverallCleanupBrowserFailure(
            f"{name} transform changed after late load despite interaction freeze: {failed!r}."
        )


def assert_meaningfully_off_center(snapshot: dict[str, Any], name: str, *, tolerance: float = 0.025) -> None:
    center = snapshot.get("normalizedCenter")
    if not isinstance(center, dict):
        raise OverallCleanupBrowserFailure(f"Missing normalized center for {name}: {snapshot!r}.")
    dx = abs(float(center.get("x", 0.5)) - 0.5)
    dy = abs(float(center.get("y", 0.5)) - 0.5)
    if max(dx, dy) <= tolerance:
        raise OverallCleanupBrowserFailure(
            f"{name} did not become meaningfully off-center before resize: center={center!r}."
        )


def zoom_and_pan_surface(page: Any, selector: str) -> None:
    surface = page.locator(selector).first
    box = surface.bounding_box()
    if not box:
        raise OverallCleanupBrowserFailure(f"Missing bounding box for zoom/pan surface {selector!r}.")
    x = box["x"] + (box["width"] * 0.55)
    y = box["y"] + (box["height"] * 0.52)
    page.mouse.move(x, y)
    for _ in range(3):
        page.mouse.wheel(0, -620)
        page.wait_for_timeout(80)
    page.wait_for_timeout(160)
    page.mouse.down()
    page.mouse.move(x - 132, y - 96, steps=8)
    page.mouse.up()
    page.wait_for_timeout(180)


def assert_surface_wheel_zoomed(before: dict[str, Any], after: dict[str, Any], name: str) -> None:
    before_scale = float((before.get("transform") or {}).get("scaleX", 0))
    after_scale = float((after.get("transform") or {}).get("scaleX", 0))
    if after_scale <= before_scale:
        raise OverallCleanupBrowserFailure(
            f"{name} wheel zoom did not increase image scale: before={before_scale}, after={after_scale}."
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


def is_media_request(url: str) -> bool:
    path = urlparse(url).path
    return path.endswith("/thumb") or path.endswith("/file")


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


def set_range_value(page: Any, selector: str, value: int) -> None:
    page.locator(selector).first.evaluate(
        """(element, value) => {
          if (!(element instanceof HTMLInputElement)) throw new Error('Range target is not an input')
          element.value = String(value)
          element.dispatchEvent(new Event('input', { bubbles: true }))
          element.dispatchEvent(new Event('change', { bubbles: true }))
        }""",
        value,
    )


def delay_nth_file_request(page: Any, request_index: int, delay_ms: int) -> tuple[dict[str, int], Any]:
    state = {"count": 0, "delayed": 0}

    def route_handler(route: Any) -> None:
        state["count"] += 1
        if state["count"] == request_index:
            state["delayed"] += 1
            time.sleep(delay_ms / 1000.0)
        route.continue_()

    page.route("**/file?*", route_handler)
    return state, route_handler


def delay_file_path_requests(page: Any, target_path: str, delay_ms: int) -> tuple[dict[str, int], Any]:
    state = {"count": 0, "delayed": 0}

    def route_handler(route: Any) -> None:
        state["count"] += 1
        request_path = parse_qs(urlparse(route.request.url).query).get("path", [""])[0]
        if request_path == target_path:
            state["delayed"] += 1
            time.sleep(delay_ms / 1000.0)
        route.continue_()

    page.route("**/file?*", route_handler)
    return state, route_handler


def path_from_grid_cell_id(cell_id: str) -> str:
    if not cell_id.startswith("cell-"):
        raise OverallCleanupBrowserFailure(f"Unexpected grid cell id: {cell_id!r}.")
    return parse_qs(f"path={cell_id.removeprefix('cell-')}")["path"][0]


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


def run_preflight_checks(
    browser: Any,
    base_url: str,
    timeout_ms: float,
    screenshot_dir: Path,
) -> dict[str, Any]:
    mobile_context = browser.new_context(
        accept_downloads=True,
        viewport={"width": 390, "height": 844},
        has_touch=True,
        is_mobile=True,
    )
    coarse_context = browser.new_context(
        accept_downloads=True,
        viewport={"width": 900, "height": 700},
        has_touch=True,
    )
    reduced_context = browser.new_context(
        accept_downloads=True,
        viewport={"width": 1024, "height": 700},
    )
    try:
        mobile_page = mobile_context.new_page()
        mobile_page.set_default_timeout(timeout_ms)
        mobile_page.goto(base_url, wait_until="domcontentloaded")
        mobile_nav = verify_mobile_viewer_navigation(mobile_page, timeout_ms)

        coarse_page = coarse_context.new_page()
        coarse_page.set_default_timeout(timeout_ms)
        coarse_page.goto(base_url, wait_until="domcontentloaded")
        coarse_actions = verify_coarse_pointer_actions(coarse_page, timeout_ms)

        reduced_page = reduced_context.new_page()
        reduced_page.set_default_timeout(timeout_ms)
        reduced_page.goto(base_url, wait_until="domcontentloaded")
        reduced_motion = verify_reduced_motion(reduced_page, timeout_ms)
        return {
            "mobile_viewer_navigation": mobile_nav,
            "coarse_pointer_actions": coarse_actions,
            "reduced_motion": reduced_motion,
        }
    except Exception as exc:
        paths = capture_context_screenshots(
            [mobile_context, coarse_context, reduced_context],
            screenshot_dir,
            "interaction_polish_preflight_failure",
        )
        raise OverallCleanupBrowserFailure(f"{exc}{screenshot_suffix(paths)}") from exc
    finally:
        mobile_context.close()
        coarse_context.close()
        reduced_context.close()


def verify_viewer_zoom_load_race(
    browser: Any,
    base_url: str,
    timeout_ms: float,
    screenshot_dir: Path,
) -> dict[str, Any]:
    context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 920})
    page = context.new_page()
    page.set_default_timeout(timeout_ms)
    route_state, route_handler = delay_nth_file_request(page, request_index=1, delay_ms=1000)
    try:
        page.goto(base_url, wait_until="domcontentloaded")
        page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
        first_cell_id = wait_for_visible_grid_cell_ids(page, minimum_count=1, timeout_ms=timeout_ms)[0]
        page.locator(f"[id='{first_cell_id}']").first.evaluate("(element) => element.focus()")
        page.keyboard.press("Enter")
        dialog_selector = '[role="dialog"][aria-label="Image viewer"]'
        image_selector = f"{dialog_selector} img[data-viewer-image='full']"
        page.locator(dialog_selector).first.wait_for(state="visible", timeout=timeout_ms)
        set_range_value(page, 'input[aria-label="Zoom level"]', 200)
        close_button = page.locator(f"{dialog_selector} button[aria-label='Close']").first
        close_button.focus()
        before_path = page.locator(dialog_selector).first.get_attribute("data-current-path")
        page.keyboard.press("d")
        page.keyboard.press("Control+A")
        after_control_keys_path = page.locator(dialog_selector).first.get_attribute("data-current-path")
        if after_control_keys_path != before_path:
            raise OverallCleanupBrowserFailure(
                f"Viewer navigation fired from a focused control: {before_path!r} -> {after_control_keys_path!r}."
            )
        wait_for_image_ready(page, image_selector, timeout_ms)
        page.wait_for_function(
            """() => {
              const input = document.querySelector('input[aria-label="Zoom level"]')
              return input instanceof HTMLInputElement && Number(input.value) >= 195 && Number(input.value) <= 205
            }""",
            timeout=timeout_ms,
        )
        zoom_value = page.locator('input[aria-label="Zoom level"]').first.input_value()
        image_alt = assert_useful_image_alt(page, image_selector, "viewer zoom race", {"viewer"})
        success_screenshots = capture_context_screenshots(
            [context],
            screenshot_dir,
            "viewer_zoom_load_race_success",
        )
        page.keyboard.press("Escape")
        page.locator(dialog_selector).first.wait_for(state="hidden", timeout=timeout_ms)
        return {
            "delayed_file_requests": route_state,
            "invoking_cell_id": first_cell_id,
            "zoom_value": zoom_value,
            "image_alt": image_alt,
            "control_keys_path_stable": before_path == after_control_keys_path,
            "screenshots": success_screenshots,
        }
    except Exception as exc:
        paths = capture_context_screenshots([context], screenshot_dir, "viewer_zoom_load_race_failure")
        raise OverallCleanupBrowserFailure(f"{exc}{screenshot_suffix(paths)}") from exc
    finally:
        page.unroute("**/file?*", route_handler)
        context.close()


def verify_compare_late_load_freeze(
    browser: Any,
    base_url: str,
    timeout_ms: float,
    screenshot_dir: Path,
) -> dict[str, Any]:
    context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 920})
    page = context.new_page()
    page.set_default_timeout(timeout_ms)
    route_handler = None
    route_state: dict[str, int] = {"count": 0, "delayed": 0}
    try:
        page.goto(base_url, wait_until="domcontentloaded")
        page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
        selected_cell_ids = select_two_visible_images(page, timeout_ms)
        delayed_path = path_from_grid_cell_id(selected_cell_ids[1])
        route_state, route_handler = delay_file_path_requests(page, target_path=delayed_path, delay_ms=1800)
        set_right_panel_open(page, open_state=True, timeout_ms=10_000)
        side_by_side = page.get_by_role("button", name="Side by side view").first
        side_by_side.click()
        dialog_selector = '[role="dialog"][aria-label="Compare images"]'
        stage_selector = ".compare-stage"
        image_a_selector = "img[data-compare-image='a']"
        image_b_selector = "img[data-compare-image='b']"
        page.locator(dialog_selector).first.wait_for(state="visible", timeout=timeout_ms)
        wait_for_image_ready(page, image_a_selector, timeout_ms)
        b_ready_before_drag = page.evaluate(
            """(selector) => {
              const img = document.querySelector(selector)
              if (!(img instanceof HTMLImageElement)) return false
              const opacity = Number(window.getComputedStyle(img).opacity || '0')
              return img.complete && img.naturalWidth > 0 && img.naturalHeight > 0 && opacity > 0.5
            }""",
            image_b_selector,
        )
        if b_ready_before_drag:
            raise OverallCleanupBrowserFailure("Compare late-load fixture did not keep side B delayed before interaction.")
        divider = page.locator(".compare-divider-hit").first
        box = divider.bounding_box()
        if not box:
            raise OverallCleanupBrowserFailure("Missing compare divider for late-load freeze check.")
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + 180, box["y"] + box["height"] / 2, steps=6)
        page.mouse.up()
        before_late_load = collect_transformed_image_center(
            page,
            container_selector=stage_selector,
            image_selector=image_a_selector,
            name="compare-a-before-late-load",
        )
        wait_for_image_ready(page, image_b_selector, timeout_ms)
        after_late_load = collect_transformed_image_center(
            page,
            container_selector=stage_selector,
            image_selector=image_a_selector,
            name="compare-a-after-late-load",
        )
        assert_transform_stable(before_late_load, after_late_load, "compare A")
        close_button = page.locator(f"{dialog_selector} button:has-text('Close')").first
        close_button.focus()
        before_path = page.locator(dialog_selector).first.get_attribute("data-compare-a-path")
        page.keyboard.press("a")
        page.keyboard.press("Alt+ArrowLeft")
        after_control_keys_path = page.locator(dialog_selector).first.get_attribute("data-compare-a-path")
        if before_path != after_control_keys_path:
            raise OverallCleanupBrowserFailure(
                f"Compare navigation fired from a focused control/modifier combo: {before_path!r} -> {after_control_keys_path!r}."
            )
        image_alt_a = assert_useful_image_alt(page, image_a_selector, "compare late-load A", {"compare A", "thumb A"})
        image_alt_b = assert_useful_image_alt(page, image_b_selector, "compare late-load B", {"compare B", "thumb B"})
        success_screenshots = capture_context_screenshots(
            [context],
            screenshot_dir,
            "compare_late_load_success",
        )
        page.keyboard.press("Escape")
        page.locator(dialog_selector).first.wait_for(state="hidden", timeout=timeout_ms)
        return {
            "selected_cell_ids": selected_cell_ids,
            "delayed_path": delayed_path,
            "delayed_file_requests": route_state,
            "before_late_load": before_late_load,
            "after_late_load": after_late_load,
            "control_keys_path_stable": before_path == after_control_keys_path,
            "image_alt": {"a": image_alt_a, "b": image_alt_b},
            "screenshots": success_screenshots,
        }
    except Exception as exc:
        paths = capture_context_screenshots([context], screenshot_dir, "compare_late_load_failure")
        raise OverallCleanupBrowserFailure(f"{exc}{screenshot_suffix(paths)}") from exc
    finally:
        if route_handler is not None:
            page.unroute("**/file?*", route_handler)
        context.close()


def run_interaction_polish_sprint1_checks(
    browser: Any,
    base_url: str,
    timeout_ms: float,
    screenshot_dir: Path,
) -> dict[str, Any]:
    return {
        "viewer_zoom_load_race": verify_viewer_zoom_load_race(browser, base_url, timeout_ms, screenshot_dir),
        "compare_late_load_freeze": verify_compare_late_load_freeze(browser, base_url, timeout_ms, screenshot_dir),
    }


def run_sprint1_browser_checks(base_url: str, timeout_ms: float, screenshot_dir: Path) -> dict[str, Any]:
    playwright_import = import_playwright()
    sync_playwright = playwright_import[2]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            return {
                "preflight": run_preflight_checks(browser, base_url, timeout_ms, screenshot_dir),
                "interaction_polish_sprint1": run_interaction_polish_sprint1_checks(
                    browser,
                    base_url,
                    timeout_ms,
                    screenshot_dir,
                ),
            }
        finally:
            browser.close()


def verify_viewer_resize_focus(page: Any, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 1440, "height": 920})
    page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
    first_cell_id = wait_for_visible_grid_cell_ids(page, minimum_count=1, timeout_ms=timeout_ms)[0]
    first_cell_selector = f"[id='{first_cell_id}']"
    page.locator(first_cell_selector).first.evaluate("(element) => element.focus()")
    page.keyboard.press("Enter")
    dialog_selector = '[role="dialog"][aria-label="Image viewer"]'
    image_selector = f"{dialog_selector} img[data-viewer-image='full']"
    page.locator(dialog_selector).first.wait_for(state="visible", timeout=timeout_ms)
    wait_for_image_ready(page, image_selector, timeout_ms)
    image_alt = assert_useful_image_alt(page, image_selector, "viewer", {"viewer"})
    assert_focus_inside(page, dialog_selector, "viewer dialog after open")
    focus_sequence = [collect_active_element_snapshot(page)]
    for _ in range(5):
        page.keyboard.press("Tab")
        assert_focus_inside(page, dialog_selector, "viewer dialog Tab cycle")
        focus_sequence.append(collect_active_element_snapshot(page))
    page.keyboard.press("Shift+Tab")
    assert_focus_inside(page, dialog_selector, "viewer dialog Shift+Tab cycle")
    focus_sequence.append(collect_active_element_snapshot(page))
    if any((entry or {}).get("text") != "Close" for entry in focus_sequence):
        raise OverallCleanupBrowserFailure(
            f"Viewer desktop focus order included a hidden or unexpected control: {focus_sequence!r}."
        )
    focus_outline = assert_focused_element_has_visible_outline(page, "viewer dialog controls")

    before_zoom = collect_transformed_image_center(
        page,
        container_selector=dialog_selector,
        image_selector=image_selector,
        name="viewer-before-wheel",
    )
    zoom_and_pan_surface(page, dialog_selector)
    before_resize = collect_transformed_image_center(
        page,
        container_selector=dialog_selector,
        image_selector=image_selector,
        name="viewer-after-pan-before-resize",
    )
    assert_surface_wheel_zoomed(before_zoom, before_resize, "viewer")
    assert_meaningfully_off_center(before_resize, "viewer")

    resize_evidence: list[dict[str, Any]] = []
    previous = before_resize
    for name, width, height in (
        ("viewer-half-width", 720, 900),
        ("viewer-short-height", 1024, 480),
    ):
        page.set_viewport_size({"width": width, "height": height})
        wait_for_image_ready(page, image_selector, timeout_ms)
        page.wait_for_timeout(260)
        after = collect_transformed_image_center(
            page,
            container_selector=dialog_selector,
            image_selector=image_selector,
            name=name,
        )
        assert_center_preserved(previous, after)
        resize_evidence.append(after)
        previous = after

    page.keyboard.press("Escape")
    page.locator(dialog_selector).first.wait_for(state="hidden", timeout=timeout_ms)
    page.wait_for_timeout(160)
    assert_focus_restored(page, first_cell_selector, "viewer invoking grid cell")
    return {
        "invoking_cell_id": first_cell_id,
        "before_zoom": before_zoom,
        "before_resize": before_resize,
        "after_resizes": resize_evidence,
        "focus_sequence": focus_sequence,
        "focus_outline": focus_outline,
        "image_alt": image_alt,
        "focus_restored": True,
    }


def verify_desktop_layout_label(page: Any, timeout_ms: float) -> dict[str, Any]:
    trigger = page.get_by_role("button", name="Sort and layout").first
    trigger.wait_for(state="visible", timeout=timeout_ms)
    if trigger.is_disabled():
        switch_button = page.locator('button:has-text("Switch to Most recent")').first
        if switch_button.count() > 0:
            switch_button.click()
            page.wait_for_function(
                """() => {
                  const button = document.querySelector('button[aria-label="Sort and layout"]')
                  return button instanceof HTMLButtonElement ? !button.disabled : false
                }""",
                timeout=timeout_ms,
            )
    if trigger.is_disabled():
        raise OverallCleanupBrowserFailure(
            "Sort and layout trigger stayed disabled after scan-stable unlock."
        )
    trigger.click()
    panel = page.locator('.dropdown-panel[aria-label="Sort and layout"]').first
    panel.wait_for(state="visible", timeout=timeout_ms)
    labels = [label.strip() for label in panel.locator("button.dropdown-item").all_inner_texts()]
    if "Justified rows" not in labels:
        raise OverallCleanupBrowserFailure(
            f"Desktop layout menu is missing Justified rows label: {labels!r}."
        )
    if "Masonry" in labels:
        raise OverallCleanupBrowserFailure(
            f"Desktop layout menu still exposes legacy Masonry label: {labels!r}."
        )

    panel.get_by_role("option", name="Grid").click()
    trigger.click()
    panel = page.locator('.dropdown-panel[aria-label="Sort and layout"]').first
    panel.wait_for(state="visible", timeout=timeout_ms)
    panel.get_by_role("option", name="Justified rows").click()
    page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
    return {"labels": labels, "switchToGridAndBack": True}


def run_adaptive_geometry_checks(page: Any, timeout_ms: float) -> list[dict[str, Any]]:
    viewport_sizes = (
        ("adaptive-320x700", 320, 700),
        ("adaptive-390x700", 390, 700),
        ("adaptive-760x430", 760, 430),
        ("adaptive-1024x480", 1024, 480),
        ("adaptive-half-desktop", 720, 900),
    )
    evidence: list[dict[str, Any]] = []
    for name, width, height in viewport_sizes:
        page.set_viewport_size({"width": width, "height": height})
        page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
        wait_for_visible_grid_cell_ids(page, minimum_count=2, timeout_ms=timeout_ms)
        page.evaluate(
            """() => {
              const grid = document.querySelector('[role="grid"][aria-label="Gallery"]')
              if (grid) grid.scrollTop = 0
            }"""
        )
        page.wait_for_timeout(220)
        snapshot = collect_adaptive_geometry_evidence(page, name)
        assert_adaptive_geometry(snapshot)
        evidence.append(snapshot)
    page.set_viewport_size({"width": 1440, "height": 920})
    page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_timeout(180)
    return evidence


def verify_compare_resize_focus(page: Any, timeout_ms: float) -> dict[str, Any]:
    side_by_side = page.get_by_role("button", name="Side by side view").first
    if side_by_side.is_disabled():
        raise OverallCleanupBrowserFailure("Side by side action is disabled for compare behavior checks.")
    side_by_side.focus()
    side_by_side.click()
    dialog_selector = '[role="dialog"][aria-label="Compare images"]'
    stage_selector = ".compare-stage"
    image_a_selector = "img[data-compare-image='a']"
    image_b_selector = "img[data-compare-image='b']"
    dialog = page.locator(dialog_selector).first
    dialog.wait_for(state="visible", timeout=timeout_ms)
    wait_for_image_ready(page, image_a_selector, timeout_ms)
    wait_for_image_ready(page, image_b_selector, timeout_ms)
    image_alt_a = assert_useful_image_alt(page, image_a_selector, "compare A", {"compare A", "thumb A"})
    image_alt_b = assert_useful_image_alt(page, image_b_selector, "compare B", {"compare B", "thumb B"})
    assert_focus_inside(page, dialog_selector, "compare dialog after open")
    for _ in range(7):
        page.keyboard.press("Tab")
        assert_focus_inside(page, dialog_selector, "compare dialog Tab cycle")
    page.keyboard.press("Shift+Tab")
    assert_focus_inside(page, dialog_selector, "compare dialog Shift+Tab cycle")
    focus_outline = assert_focused_element_has_visible_outline(page, "compare dialog controls")

    layout = collect_layout_evidence(page, "compare-dialog-open")
    before_zoom_a = collect_transformed_image_center(
        page,
        container_selector=stage_selector,
        image_selector=image_a_selector,
        name="compare-a-before-wheel",
    )
    before_zoom_b = collect_transformed_image_center(
        page,
        container_selector=stage_selector,
        image_selector=image_b_selector,
        name="compare-b-before-wheel",
    )
    zoom_and_pan_surface(page, stage_selector)
    before_resize_a = collect_transformed_image_center(
        page,
        container_selector=stage_selector,
        image_selector=image_a_selector,
        name="compare-a-after-pan-before-resize",
    )
    before_resize_b = collect_transformed_image_center(
        page,
        container_selector=stage_selector,
        image_selector=image_b_selector,
        name="compare-b-after-pan-before-resize",
    )
    assert_surface_wheel_zoomed(before_zoom_a, before_resize_a, "compare A")
    assert_surface_wheel_zoomed(before_zoom_b, before_resize_b, "compare B")
    assert_meaningfully_off_center(before_resize_a, "compare A")

    resize_evidence: list[dict[str, Any]] = []
    previous_a = before_resize_a
    previous_b = before_resize_b
    for name, width, height in (
        ("compare-half-width", 720, 900),
        ("compare-short-height", 1024, 480),
    ):
        page.set_viewport_size({"width": width, "height": height})
        wait_for_image_ready(page, image_a_selector, timeout_ms)
        wait_for_image_ready(page, image_b_selector, timeout_ms)
        page.wait_for_timeout(260)
        after_a = collect_transformed_image_center(
            page,
            container_selector=stage_selector,
            image_selector=image_a_selector,
            name=f"{name}-a",
        )
        after_b = collect_transformed_image_center(
            page,
            container_selector=stage_selector,
            image_selector=image_b_selector,
            name=f"{name}-b",
        )
        assert_center_preserved(previous_a, after_a)
        assert_center_preserved(previous_b, after_b)
        resize_evidence.append({"name": name, "a": after_a, "b": after_b})
        previous_a = after_a
        previous_b = after_b

    page.keyboard.press("Escape")
    dialog.wait_for(state="hidden", timeout=timeout_ms)
    page.wait_for_timeout(160)
    restored = page.evaluate(
        """() => (
          document.activeElement instanceof HTMLElement
          && document.activeElement.getAttribute('role') === 'gridcell'
          && document.activeElement.id.startsWith('cell-')
        )"""
    )
    if not restored:
        raise OverallCleanupBrowserFailure("Focus did not restore to a selected compare grid cell.")
    return {
        "layout": layout,
        "before_zoom": {"a": before_zoom_a, "b": before_zoom_b},
        "before_resize": {"a": before_resize_a, "b": before_resize_b},
        "after_resizes": resize_evidence,
        "focus_outline": focus_outline,
        "image_alt": {"a": image_alt_a, "b": image_alt_b},
        "focus_restored": True,
    }


def trigger_comparison_export(page: Any) -> dict[str, Any]:
    export_entries = page.get_by_role("button", name="Export comparison")
    enabled_export_idx: int | None = None
    for idx in range(export_entries.count()):
        if export_entries.nth(idx).is_enabled():
            enabled_export_idx = idx
            break
    if enabled_export_idx is None:
        raise OverallCleanupBrowserFailure("No enabled Export comparison button found.")

    button = export_entries.nth(enabled_export_idx)
    button.scroll_into_view_if_needed()
    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/export-comparison")
    ) as export_response_info, page.expect_download() as export_download_info:
        button.click()

    response = export_response_info.value
    download = export_download_info.value
    body = response.body()
    if response.status != 200:
        raise OverallCleanupBrowserFailure(
            f"Comparison export returned status {response.status}: {body[:200]!r}."
        )
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/png"):
        raise OverallCleanupBrowserFailure(f"Unexpected comparison export content type: {content_type!r}.")
    content_length_header = response.headers.get("content-length")
    declared_length = int(content_length_header) if content_length_header and content_length_header.isdigit() else None
    if declared_length is not None and declared_length <= 0:
        raise OverallCleanupBrowserFailure("Comparison export returned an empty content-length header.")
    download_path = download.path()
    if download_path is None:
        raise OverallCleanupBrowserFailure("Comparison export did not produce an inspectable browser download.")
    downloaded = Path(download_path).read_bytes()
    if not downloaded:
        raise OverallCleanupBrowserFailure("Comparison export produced an empty browser download.")
    with Image.open(BytesIO(downloaded)) as exported:
        exported.load()
        if exported.format != "PNG":
            raise OverallCleanupBrowserFailure(f"Downloaded export is not a PNG: {exported.format!r}.")
        export_width, export_height = exported.size
    if export_width <= 0 or export_height <= 0:
        raise OverallCleanupBrowserFailure(f"Downloaded export has invalid dimensions: {export_width}x{export_height}.")
    return {
        "status": response.status,
        "content_type": content_type,
        "content_disposition": response.headers.get("content-disposition", ""),
        "suggested_filename": download.suggested_filename,
        "content_length": declared_length if declared_length is not None else len(downloaded),
        "observed_body_length": len(body),
        "downloaded_content_length": len(downloaded),
        "downloaded_png_width": export_width,
        "downloaded_png_height": export_height,
    }


def run_browser_checks(base_url: str, timeout_ms: float, screenshot_dir: Path) -> dict[str, Any]:
    playwright_import = import_playwright()
    sync_playwright = playwright_import[2]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            preflight = run_preflight_checks(browser, base_url, timeout_ms, screenshot_dir)
            interaction_polish_sprint1 = run_interaction_polish_sprint1_checks(
                browser,
                base_url,
                timeout_ms,
                screenshot_dir,
            )
            context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 920})
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            media_requests: list[str] = []
            page.on(
                "request",
                lambda request: media_requests.append(request.url) if is_media_request(request.url) else None,
            )
            try:
                page.goto(base_url, wait_until="domcontentloaded")
                page.get_by_role("grid", name="Gallery").wait_for(state="visible")
                layout_label = verify_desktop_layout_label(page, timeout_ms)
                adaptive_geometry = run_adaptive_geometry_checks(page, timeout_ms)
                menu_bounds = verify_menu_bounds_and_roles(page, timeout_ms)
                hover_preview = verify_hover_preview(page, timeout_ms, media_requests)
                ctrl_wheel = verify_browse_ctrl_wheel_and_slider(page, timeout_ms)
                viewer_resize_focus = verify_viewer_resize_focus(page, timeout_ms)
                page.set_viewport_size({"width": 1440, "height": 920})
                page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
                before_selection = collect_layout_evidence(page, "browse-ready")
                selected_cell_ids = select_two_visible_images(page, timeout_ms)
                set_right_panel_open(page, open_state=True, timeout_ms=10_000)
                after_selection = collect_layout_evidence(page, "two-selected")
                compare_resize_focus = verify_compare_resize_focus(page, timeout_ms)
                compare_dialog = compare_resize_focus["layout"]
                page.set_viewport_size({"width": 1440, "height": 920})
                page.get_by_role("grid", name="Gallery").wait_for(state="visible", timeout=timeout_ms)
                if page.locator('[role="gridcell"][aria-selected="true"]').count() < 2:
                    selected_cell_ids = select_two_visible_images(page, timeout_ms)
                set_right_panel_open(page, open_state=True, timeout_ms=10_000)
                export_result = trigger_comparison_export(page)
                after_export = collect_layout_evidence(page, "export-complete")
                return {
                    "selected_cell_ids": selected_cell_ids,
                    "layout": [before_selection, after_selection, compare_dialog, after_export],
                    "layout_label": layout_label,
                    "adaptive_geometry": adaptive_geometry,
                    "menu_bounds": menu_bounds,
                    "hover_preview": hover_preview,
                    "ctrl_wheel": ctrl_wheel,
                    "preflight": preflight,
                    "interaction_polish_sprint1": interaction_polish_sprint1,
                    "viewer_resize_focus": viewer_resize_focus,
                    "compare_resize_focus": compare_resize_focus,
                    "comparison_export": export_result,
                }
            except Exception as exc:
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = screenshot_dir / "overall_cleanup_failure.png"
                try:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                except Exception:
                    screenshot_path = Path("")
                suffix = f" Screenshot: {screenshot_path}" if str(screenshot_path) else ""
                raise OverallCleanupBrowserFailure(f"{exc}{suffix}") from exc
            finally:
                context.close()
        finally:
            browser.close()


def server_command(dataset_dir: Path, host: str, port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "lenslet.cli",
        str(dataset_dir),
        "--host",
        host,
        "--port",
        str(port),
        "--verbose",
        "--no-skip-indexing",
    ]


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    cleanup_dir = False
    if args.dataset_dir is not None:
        dataset_dir = args.dataset_dir.resolve()
        if not dataset_dir.exists():
            raise SystemExit(f"Dataset directory does not exist: {dataset_dir}")
    else:
        dataset_dir = Path(tempfile.mkdtemp(prefix="lenslet-overall-cleanup-")).resolve()
        cleanup_dir = not args.keep_dataset
        build_fixture_dataset(dataset_dir)

    port = choose_port(args.host, args.port)
    base_url = f"http://{args.host}:{port}"
    log_file = tempfile.NamedTemporaryFile(
        prefix="lenslet-overall-cleanup-server-",
        suffix=".log",
        delete=False,
    )
    log_path = Path(log_file.name)
    log_file.close()

    command = server_command(dataset_dir, args.host, port)
    server_log = log_path.open("w", encoding="utf-8")
    try:
        server_proc = subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    finally:
        server_log.close()

    summary: dict[str, Any]
    try:
        initial_health = wait_for_health(base_url, args.server_timeout_seconds)
        if server_proc.poll() is not None:
            raise OverallCleanupBrowserFailure(
                f"Lenslet exited unexpectedly with code {server_proc.returncode}."
            )
        if args.only_sprint1:
            checks = run_sprint1_browser_checks(base_url, args.browser_timeout_ms, args.screenshot_dir)
        else:
            checks = run_browser_checks(base_url, args.browser_timeout_ms, args.screenshot_dir)
        final_health = wait_for_health(base_url, args.server_timeout_seconds)
        summary = {
            "base_url": base_url,
            "dataset_dir": str(dataset_dir),
            "server_log": str(log_path),
            "initial_health": initial_health,
            "final_health": final_health,
            "checks": checks,
            "status": "passed",
        }
        print(json.dumps(summary, indent=2))
        write_summary(args.output_json, summary)
        return 0
    except Exception as exc:
        tail = ""
        try:
            tail = "\n".join(log_path.read_text(encoding="utf-8").splitlines()[-40:])
        except Exception:
            tail = "<unavailable>"
        summary = {
            "base_url": base_url,
            "dataset_dir": str(dataset_dir),
            "server_log": str(log_path),
            "error": str(exc),
            "server_log_tail": tail,
            "status": "failed",
        }
        write_summary(args.output_json, summary)
        print(f"[overall-cleanup-browser] FAILED: {exc}", file=sys.stderr)
        print(f"[overall-cleanup-browser] Server log tail ({log_path}):\n{tail}", file=sys.stderr)
        return 1
    finally:
        stop_process(server_proc)
        if cleanup_dir:
            shutil.rmtree(dataset_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
