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
import subprocess  # nosec B404 - Lenslet is launched with a fixed argv and shell=False.
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

if __name__ == "__main__" and not __package__:
    raise SystemExit("Run from the repository root with: python -m scripts.browser.overall_cleanup.browser")

from lenslet.processes import long_running_process, start_process
from scripts.smoke_harness import choose_port, import_playwright, server_base_url, stop_process, wait_for_health

from scripts.browser.overall_cleanup.fixtures import build_fixture_dataset, write_text_atomic
from scripts.browser.overall_cleanup.focus import (
    assert_focus_inside,
    assert_focus_restored,
    assert_focused_element_has_visible_outline,
    assert_useful_image_alt,
    collect_active_element_snapshot,
)
from scripts.browser.overall_cleanup.grid import (
    assert_adaptive_geometry,
    collect_adaptive_geometry_evidence,
    collect_layout_evidence,
    path_from_grid_cell_id,
    select_two_visible_images,
    wait_for_visible_grid_cell_ids,
)
from scripts.browser.overall_cleanup.hover import verify_hover_preview
from scripts.browser.overall_cleanup.media_requests import (
    delay_file_path_requests,
    delay_nth_file_request,
    is_media_request,
)
from scripts.browser.overall_cleanup.menus import verify_menu_bounds_and_roles
from scripts.browser.overall_cleanup.mobile import (
    verify_browse_ctrl_wheel_and_slider,
    verify_coarse_pointer_actions,
    verify_mobile_viewer_navigation,
    verify_reduced_motion,
)
from scripts.browser.overall_cleanup.panels import set_right_panel_open
from scripts.browser.overall_cleanup.screenshots import capture_context_screenshots, screenshot_suffix
from scripts.browser.overall_cleanup.transforms import (
    assert_center_preserved,
    assert_compare_split_changed,
    assert_compare_split_in_range,
    assert_compare_split_stable,
    assert_meaningfully_off_center,
    assert_surface_wheel_zoomed,
    assert_transform_stable,
    collect_compare_divider_split,
    collect_transformed_image_center,
    set_range_value,
    wait_for_image_ready,
    zoom_and_pan_surface,
)
from scripts.browser.overall_cleanup.support import (
    OverallCleanupBrowserFailure,
    _BROWSER_SCENARIO_ERRORS,
    _SCREENSHOT_CAPTURE_ERRORS,
    _SCRIPT_RUN_ERRORS,
)


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
        default=Path(tempfile.gettempdir()) / "lenslet-overall-cleanup-browser.json",
        help="Path for machine-readable cleanup evidence.",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "lenslet-overall-cleanup-browser-screenshots",
        help="Directory for screenshots captured on scenario failure.",
    )
    parser.add_argument(
        "--only-sprint1",
        action="store_true",
        help="Run only interaction-polish preflight and Sprint 1 browser evidence.",
    )
    return parser.parse_args()


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
    divider_lifecycle = verify_compare_divider_lifecycle(page, timeout_ms)
    wait_for_image_ready(page, image_a_selector, timeout_ms)
    wait_for_image_ready(page, image_b_selector, timeout_ms)
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
        "divider_lifecycle": divider_lifecycle,
        "focus_outline": focus_outline,
        "image_alt": {"a": image_alt_a, "b": image_alt_b},
        "focus_restored": True,
    }


def verify_compare_divider_lifecycle(page: Any, timeout_ms: float) -> dict[str, Any]:
    stage = page.locator(".compare-stage").first
    divider = page.locator(".compare-divider-hit").first
    stage.wait_for(state="visible", timeout=timeout_ms)
    divider.wait_for(state="visible", timeout=timeout_ms)

    initial = collect_compare_divider_split(page, "compare-divider-initial")
    assert_compare_split_in_range(initial, "initial")
    stage_box = stage.bounding_box()
    divider_box = divider.bounding_box()
    if not stage_box or not divider_box:
        raise OverallCleanupBrowserFailure("Missing compare divider bounds for drag lifecycle check.")
    drag_y = divider_box["y"] + (divider_box["height"] / 2)
    page.mouse.move(divider_box["x"] + (divider_box["width"] / 2), drag_y)
    page.mouse.down()
    page.mouse.move(stage_box["x"] + (stage_box["width"] * 0.82), drag_y, steps=8)
    page.mouse.up()
    page.wait_for_timeout(120)
    after_drag = collect_compare_divider_split(page, "compare-divider-after-drag")
    assert_compare_split_in_range(after_drag, "after drag")
    assert_compare_split_changed(initial, after_drag, "after drag")

    page.set_viewport_size({"width": 1024, "height": 480})
    page.wait_for_timeout(220)
    after_resize = collect_compare_divider_split(page, "compare-divider-after-resize")
    assert_compare_split_in_range(after_resize, "after resize")

    page.evaluate(
        """() => {
          const stage = document.querySelector('.compare-stage')
          const divider = document.querySelector('.compare-divider-hit')
          if (!(stage instanceof HTMLElement) || !(divider instanceof HTMLElement)) {
            throw new Error('Missing compare divider for lost capture check')
          }
          const stageRect = stage.getBoundingClientRect()
          const dividerRect = divider.getBoundingClientRect()
          const pointerId = 901
          const clientY = dividerRect.top + dividerRect.height / 2
          divider.dispatchEvent(new PointerEvent('pointerdown', {
            bubbles: true,
            cancelable: true,
            pointerId,
            pointerType: 'mouse',
            button: 0,
            buttons: 1,
            clientX: dividerRect.left + dividerRect.width / 2,
            clientY,
          }))
          divider.dispatchEvent(new PointerEvent('lostpointercapture', {
            bubbles: false,
            cancelable: false,
            pointerId,
            pointerType: 'mouse',
            clientX: dividerRect.left + dividerRect.width / 2,
            clientY,
          }))
          window.dispatchEvent(new PointerEvent('pointermove', {
            bubbles: true,
            cancelable: true,
            pointerId,
            pointerType: 'mouse',
            buttons: 1,
            clientX: stageRect.left + stageRect.width * 0.1,
            clientY,
          }))
        }"""
    )
    page.wait_for_timeout(120)
    after_lost_capture = collect_compare_divider_split(page, "compare-divider-after-lost-capture")
    assert_compare_split_in_range(after_lost_capture, "after lost capture")
    assert_compare_split_stable(after_resize, after_lost_capture, "after lost capture")

    page.set_viewport_size({"width": 1440, "height": 920})
    page.wait_for_timeout(220)
    after_restore = collect_compare_divider_split(page, "compare-divider-after-viewport-restore")
    assert_compare_split_in_range(after_restore, "after viewport restore")
    return {
        "initial": initial,
        "after_drag": after_drag,
        "after_resize": after_resize,
        "after_lost_capture": after_lost_capture,
        "after_viewport_restore": after_restore,
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
            except _BROWSER_SCENARIO_ERRORS as exc:
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = screenshot_dir / "overall_cleanup_failure.png"
                try:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                except _SCREENSHOT_CAPTURE_ERRORS:
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
    ]


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    write_text_atomic(path, json.dumps(summary, indent=2) + "\n")


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
        try:
            build_fixture_dataset(dataset_dir)
        except Exception:
            if cleanup_dir:
                shutil.rmtree(dataset_dir, ignore_errors=True)
            raise

    port = choose_port(args.host, args.port)
    base_url = server_base_url(args.host, port)
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
        server_proc = start_process(
            command,
            timeout_policy=long_running_process("Lenslet browser evidence server is stopped in cleanup."),
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
    except _SCRIPT_RUN_ERRORS as exc:
        tail = ""
        try:
            tail = "\n".join(log_path.read_text(encoding="utf-8").splitlines()[-40:])
        except (OSError, UnicodeDecodeError):
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
