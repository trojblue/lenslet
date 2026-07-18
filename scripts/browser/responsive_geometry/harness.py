#!/usr/bin/env python3
"""Responsive layout geometry evidence for Lenslet.

This live-browser harness exercises the resize failure classes from the
responsive-layout plan. It uses temporary fixtures by default, records DOM
layout evidence for each scenario, and saves a screenshot plus failure snapshot
when an assertion trips.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

if __name__ == "__main__" and not __package__:
    raise SystemExit("Run from the repository root with: python -m scripts.browser.responsive_geometry.harness")

from scripts.browser.waits import wait_for_grid_selection_count, wait_for_ui_settled
from scripts.browser.responsive_geometry.catalog import layout_scenario_catalog
from scripts.browser.responsive_geometry.fixtures import (
    build_fixture_dataset,
    scenario_storage,
    seed_storage_script,
)
from scripts.browser.responsive_geometry.types import BrowserScenario, Scenario, ScenarioRunner
from scripts.smoke_harness import (
    choose_port,
    import_playwright,
    read_log_tail,
    running_lenslet_server,
    wait_for_health,
    write_json_evidence,
)
from scripts.browser.viewer_probe.page import wait_for_viewer_path

from scripts.browser.responsive_geometry.errors import (
    ResponsiveGeometryFailure,
    _PLAYWRIGHT_OPERATION_ERRORS,
    _SNAPSHOT_CAPTURE_ERRORS,
)
from scripts.browser.responsive_geometry.evidence import (
    assert_hidden_toolbar_controls_not_interactable,
    assert_inspector_contained,
    assert_metrics_left_760_observed,
    assert_mobile_drawer_reachable,
    assert_mobile_search_reserved,
    assert_no_document_overflow,
    assert_no_visible_control_overlap,
    assert_overlay_closed,
    assert_overlay_contained_to_center,
    assert_overlay_image_stable,
    assert_overlay_isolated,
    assert_side_regions_visible,
    assert_theme_settings_reachable,
    assert_viewer_toolbar_chrome,
    assert_visible_metrics_left_contained,
    collect_snapshot,
    sample_overlay_images,
    scenario_state,
    _assert_close,
    _parse_float,
    _rect_left,
    _rect_right,
    _rect_width,
    _sample_image_visible,
)


LOCAL_SERVER_SCHEME = "http"


@dataclass(frozen=True)
class BrowserScenarioRun:
    browser: Any
    scenarios: list[BrowserScenario]
    evidence: dict[str, Any]
    base_url: str
    timeout_ms: float
    screenshot_dir: Path


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
        default=Path(tempfile.gettempdir()) / "lenslet-responsive-geometry.json",
        help="Path for machine-readable responsive geometry evidence.",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "lenslet-responsive-geometry-screenshots",
        help="Directory for screenshots captured on scenario failure.",
    )
    return parser.parse_args()


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
    deadline = time.monotonic() + (timeout_ms * 0.001)
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


def select_first_items(page: Any, count: int, timeout_ms: float) -> list[str]:
    if count < 1:
        return []
    cell_ids = wait_for_visible_grid_cell_ids(page, count, timeout_ms)[:count]
    page.locator(f"[id='{cell_ids[0]}']").click(timeout=timeout_ms)
    wait_for_grid_selection_count(page, 1, timeout_ms)
    for selected_count, cell_id in enumerate(cell_ids[1:], start=2):
        page.locator(f"[id='{cell_id}']").click(timeout=timeout_ms, modifiers=["Control"])
        wait_for_grid_selection_count(page, selected_count, timeout_ms)
    return [path_from_cell_id(cell_id) for cell_id in cell_ids]


def open_metrics_left_panel(page: Any, timeout_ms: float) -> None:
    page.get_by_role("button", name="Metrics and Filters").first.click(timeout=timeout_ms)
    page.wait_for_function(
        """() => {
          const panel = document.querySelector('.app-left-panel');
          const metricsButton = panel?.querySelector('button[aria-label="Metrics and Filters"]');
          return panel?.getAttribute('data-left-content-open') === 'true'
            && metricsButton?.getAttribute('aria-pressed') === 'true';
        }""",
        timeout=timeout_ms,
    )
    wait_for_ui_settled(page, timeout_ms)


def open_first_viewer(page: Any, timeout_ms: float) -> str:
    first_cell_id = wait_for_visible_grid_cell_ids(page, 1, timeout_ms)[0]
    page.locator(f"[id='{first_cell_id}']").dblclick(timeout=timeout_ms)
    page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(state="visible", timeout=timeout_ms)
    return path_from_cell_id(first_cell_id)


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
        select_first_items(page, 1, timeout_ms)
    wait_for_ui_settled(page, timeout_ms)
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
    wait_for_ui_settled(page, timeout_ms)
    phone = collect_snapshot(page, "resize-persistence-phone")

    page.set_viewport_size({"width": 1440, "height": 900})
    wait_for_ui_settled(page, timeout_ms)
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
        if storage.get("leftSharedWidth") != "760" or storage.get("rightWidth") != "900":
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
    wait_for_ui_settled(page, timeout_ms)
    open_snapshot = collect_snapshot(page, "viewer-overlay-390x520")
    assert_no_document_overflow(open_snapshot)
    assert_hidden_toolbar_controls_not_interactable(open_snapshot)
    assert_overlay_isolated(open_snapshot, "viewer")

    page.keyboard.press("Escape")
    page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(state="detached", timeout=timeout_ms)
    wait_for_ui_settled(page, timeout_ms)
    closed_snapshot = collect_snapshot(page, "viewer-overlay-closed")
    assert_overlay_closed(closed_snapshot, "viewer-overlay-closed")

    page.set_viewport_size({"width": 1024, "height": 760})
    wait_for_ui_settled(page, timeout_ms)
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
    wait_for_ui_settled(page, timeout_ms)
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
    wait_for_ui_settled(page, timeout_ms)
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
    wait_for_ui_settled(page, timeout_ms)
    page.keyboard.press("Tab")
    wait_for_ui_settled(page, timeout_ms)
    open_snapshot = collect_snapshot(page, "compare-overlay-390x520")
    assert_no_document_overflow(open_snapshot)
    assert_hidden_toolbar_controls_not_interactable(open_snapshot)
    assert_overlay_isolated(open_snapshot, "compare")

    page.keyboard.press("Escape")
    page.locator('[role="dialog"][aria-label="Compare images"]').wait_for(state="detached", timeout=timeout_ms)
    wait_for_ui_settled(page, timeout_ms)
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
    except ValueError:
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
    wait_for_ui_settled(page, 2_000)


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
    preview_rect, image_rect, cell_rect, viewport = _require_hover_preview_geometry(snapshot, expected_path)
    _assert_hover_preview_size(snapshot, image_rect, cell_rect, viewport)
    _assert_hover_preview_centered(snapshot, preview_rect, viewport)
    _assert_hover_preview_bounds(snapshot, preview_rect, viewport)
    _assert_hover_preview_media_requests(media_requests, expected_path)


def _require_hover_preview_geometry(
    snapshot: dict[str, Any],
    expected_path: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
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
    return preview_rect, image_rect, cell_rect, viewport


def _assert_hover_preview_size(
    snapshot: dict[str, Any],
    image_rect: dict[str, Any],
    cell_rect: dict[str, Any],
    viewport: dict[str, Any],
) -> None:
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


def _assert_hover_preview_centered(
    snapshot: dict[str, Any],
    preview_rect: dict[str, Any],
    viewport: dict[str, Any],
) -> None:
    viewport_width = _parse_float(viewport.get("width"))
    viewport_height = _parse_float(viewport.get("height"))
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


def _assert_hover_preview_bounds(
    snapshot: dict[str, Any],
    preview_rect: dict[str, Any],
    viewport: dict[str, Any],
) -> None:
    viewport_width = _parse_float(viewport.get("width"))
    viewport_height = _parse_float(viewport.get("height"))
    if _rect_left(preview_rect) < 7 or _rect_right(preview_rect) > viewport_width - 7:
        raise ResponsiveGeometryFailure(
            f"Hover preview escaped horizontal viewport bounds in {snapshot.get('name')}: {preview_rect!r}."
        )
    if _parse_float(preview_rect.get("top")) < 7 or _parse_float(preview_rect.get("bottom")) > viewport_height - 7:
        raise ResponsiveGeometryFailure(
            f"Hover preview escaped vertical viewport bounds in {snapshot.get('name')}: {preview_rect!r}."
        )


def _assert_hover_preview_media_requests(media_requests: list[str], expected_path: str) -> None:
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

    move_pointer_away(page); hotspot.hover(timeout=timeout_ms); wait_for_ui_settled(page, timeout_ms)
    dispatch_grid_scroll(page)
    page.locator(".grid-hover-preview").wait_for(state="detached", timeout=timeout_ms)
    pending_count = page.locator(".grid-hover-preview").count()
    if pending_count: raise ResponsiveGeometryFailure(f"Pending hover preview survived scroll cancellation with {pending_count} preview(s).")

    held: dict[str, Any] = {}
    def hold_hover_file(route: Any, request: Any) -> None:
        if urlparse(request.url).path == "/file" and _request_path_param(request.url) == expected_path and "route" not in held:
            held["route"] = route; return
        route.continue_()
    page.route("**/file?**", hold_hover_file)
    try:
        wait_for_ui_settled(page, timeout_ms); move_pointer_away(page); hotspot.hover(timeout=timeout_ms)
        for _ in range(40):
            if "route" in held: break
            page.wait_for_timeout(50)
        if "route" not in held: raise ResponsiveGeometryFailure(f"Delayed hover /file request did not start for {expected_path!r}.")
        dispatch_grid_scroll(page)
        try:
            held["route"].continue_()
        except _PLAYWRIGHT_OPERATION_ERRORS as exc:
            held["releaseError"] = str(exc)
        page.locator(".grid-hover-preview").wait_for(state="detached", timeout=timeout_ms)
        delayed_count = page.locator(".grid-hover-preview").count()
        if delayed_count: raise ResponsiveGeometryFailure(f"Delayed hover /file response reached the DOM after scroll clear with {delayed_count} preview(s).")
    finally:
        page.unroute("**/file?**", hold_hover_file)

    wait_for_ui_settled(page, timeout_ms)
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
        remove_request_listener(page, record_request)

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


def remove_request_listener(page: Any, callback: Any) -> bool:
    try:
        page.remove_listener("request", callback)
    except _PLAYWRIGHT_OPERATION_ERRORS:
        return False
    return True


def run_metrics_left_760_scenario(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 900, "height": 760})
    page.add_init_script(seed_storage_script(scenario_storage()))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    select_first_items(page, 2, timeout_ms)
    open_metrics_left_panel(page, timeout_ms)
    wait_for_ui_settled(page, timeout_ms)
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
    wait_for_ui_settled(page, timeout_ms)
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
    wait_for_ui_settled(page, timeout_ms)
    snapshot = collect_snapshot(
        page,
        "mobile-drawer-theme-settings-320x700",
        {"width": 320, "height": 700, "drawerThemeMenuOpen": True},
    )
    assert_no_document_overflow(snapshot)
    assert_mobile_drawer_reachable(snapshot)
    assert_theme_settings_reachable(snapshot)
    return snapshot


def layout_scenario_runner(scenario: Scenario) -> ScenarioRunner:
    def runner(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
        return run_scenario(page, base_url, scenario, timeout_ms)

    return runner


def browser_scenario_catalog() -> list[BrowserScenario]:
    return [
        *[
            BrowserScenario(
                name=scenario.name,
                width=scenario.width,
                height=scenario.height,
                runner=layout_scenario_runner(scenario),
                has_touch=scenario.has_touch,
            )
            for scenario in layout_scenario_catalog()
        ],
        BrowserScenario("resize-persistence", 1440, 900, run_resize_persistence_scenario),
        BrowserScenario("metrics-left-760-r10-observation", 900, 760, run_metrics_left_760_scenario),
        BrowserScenario(
            "mobile-drawer-theme-settings",
            320,
            700,
            run_mobile_drawer_theme_scenario,
            has_touch=True,
        ),
        BrowserScenario("viewer-overlay", 1440, 900, run_viewer_overlay_scenario),
        BrowserScenario("compare-overlay", 1440, 900, run_compare_overlay_scenario),
        BrowserScenario("hover-preview", 1440, 900, run_hover_preview_scenario),
    ]


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
    except _SNAPSHOT_CAPTURE_ERRORS as snapshot_error:
        failure["snapshotError"] = str(snapshot_error)
    evidence["failures"].append(failure)


def run_and_record_browser_scenario(
    *,
    run: BrowserScenarioRun,
    scenario: BrowserScenario,
) -> None:
    context = run.browser.new_context(
        viewport={"width": scenario.width, "height": scenario.height},
        has_touch=scenario.has_touch,
        is_mobile=scenario.has_touch,
    )
    page = context.new_page()
    page.set_default_timeout(run.timeout_ms)
    try:
        run.evidence["scenarios"].append(scenario.runner(page, run.base_url, run.timeout_ms))
    except Exception as exc:
        record_failure(
            evidence=run.evidence,
            page=page,
            screenshot_dir=run.screenshot_dir,
            scenario_name=scenario.name,
            error=exc,
        )
        raise
    finally:
        context.close()


def run_browser_scenarios(run: BrowserScenarioRun) -> None:
    for scenario in run.scenarios:
        run_and_record_browser_scenario(
            run=run,
            scenario=scenario,
        )


def finalize_evidence(evidence: dict[str, Any], started_at: float) -> None:
    if "finishedAt" not in evidence:
        evidence["finishedAt"] = time.time()
    evidence["durationSeconds"] = round(float(evidence["finishedAt"]) - started_at, 3)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    dataset_tmp: Path | None = None
    dataset_dir = args.dataset_dir
    if dataset_dir is None:
        dataset_tmp = Path(tempfile.mkdtemp(prefix="lenslet-responsive-fixture-"))
        dataset_dir = dataset_tmp
        try:
            build_fixture_dataset(dataset_dir)
        except Exception:
            if not args.keep_dataset:
                shutil.rmtree(dataset_tmp, ignore_errors=True)
            raise

    port = choose_port(args.host, args.port)
    base_url = f"{LOCAL_SERVER_SCHEME}://{args.host}:{port}"
    started_at = time.time()
    evidence: dict[str, Any] = {
        "evidenceVersion": 2,
        "baseUrl": base_url,
        "datasetDir": str(dataset_dir),
        "serverLog": None,
        "startedAt": started_at,
        "scenarios": [],
        "failures": [],
        "warnings": [],
    }

    try:
        _, _, sync_playwright = import_playwright()
        with running_lenslet_server(
            dataset_dir,
            host=args.host,
            port=port,
            extra_args=["--verbose"],
            cwd=repo_root,
            log_prefix="lenslet-responsive-server-",
        ) as server:
            evidence["baseUrl"] = server.base_url
            evidence["serverLog"] = str(server.log_path)
            initial_health = wait_for_health(server.base_url, args.server_timeout_seconds)
            evidence["initialHealth"] = initial_health

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    run_browser_scenarios(
                        BrowserScenarioRun(
                            browser=browser,
                            scenarios=browser_scenario_catalog(),
                            evidence=evidence,
                            base_url=server.base_url,
                            timeout_ms=args.browser_timeout_ms,
                            screenshot_dir=args.screenshot_dir,
                        )
                    )
                finally:
                    browser.close()
            evidence["finalHealth"] = wait_for_health(server.base_url, args.server_timeout_seconds)
        evidence["status"] = "passed"
    except Exception as exc:
        evidence["error"] = str(exc)
        evidence["status"] = "failed"
        server_log = evidence.get("serverLog")
        evidence["serverLogTail"] = read_log_tail(Path(server_log)) if isinstance(server_log, str) else "<unavailable>"
        finalize_evidence(evidence, started_at)
        write_json_evidence(args.output_json, evidence)
        raise SystemExit(1) from exc
    finally:
        if dataset_tmp is not None and not args.keep_dataset:
            shutil.rmtree(dataset_tmp, ignore_errors=True)

    finalize_evidence(evidence, started_at)
    write_json_evidence(args.output_json, evidence)
    print(f"Wrote responsive geometry evidence to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
