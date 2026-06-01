from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.smoke_harness import SmokeFailure
from scripts.browser.waits import wait_for_grid_selection_count, wait_for_ui_settled
from scripts.browser.gui_smoke.inspector import (
    assert_section_precedes,
    ensure_inspector_reorder_handles,
    inspector_section_order,
    set_right_panel_open,
    wait_for_section_precedence,
)

try:
    from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
except ImportError as exc:  # pragma: no cover - runtime dependency guard
    raise SystemExit(
        "playwright is required: run python scripts/setup_dev.py from the repo root"
    ) from exc


@dataclass(frozen=True)
class SmokeResult:
    indexing_banner_seen: bool
    sidebar_resize_delta_px: float
    left_collapsed_width_px: float
    left_hotkey_reopen_width_px: float
    right_resized_width_px: float
    center_width_after_right_resize_px: float
    anchor_before: str
    anchor_restored: str
    anchor_settled: str
    anchor_reentry_exact: bool
    search_visible_matches: list[str]
    inspector_default_order: list[str]
    inspector_reordered_order: list[str]
    inspector_reloaded_order: list[str]
    inspector_compare_over_cap_message: str


@dataclass(frozen=True)
class LeftPanelScenarioResult:
    sidebar_resize_delta_px: float
    left_collapsed_width_px: float
    left_hotkey_reopen_width_px: float


@dataclass(frozen=True)
class RightPanelResizeScenarioResult:
    right_resized_width_px: float
    center_width_after_right_resize_px: float


@dataclass(frozen=True)
class AnchorSearchScenarioResult:
    anchor_before: str
    anchor_restored: str
    anchor_settled: str
    anchor_reentry_exact: bool
    search_visible_matches: list[str]


@dataclass(frozen=True)
class InspectorReorderScenarioResult:
    inspector_default_order: list[str]
    inspector_reordered_order: list[str]
    inspector_reloaded_order: list[str]


def top_visible_grid_path(page: Page) -> str:
    value = page.evaluate(
        """() => {
          const cells = Array.from(document.querySelectorAll('[role="gridcell"][id^="cell-"]'))
            .map((el) => {
              const rect = el.getBoundingClientRect();
              const id = el.id || '';
              const encodedPath = id.startsWith('cell-') ? id.slice(5) : '';
              let path = '';
              try {
                path = encodedPath ? decodeURIComponent(encodedPath) : '';
              } catch {
                path = '';
              }
              return { path, top: rect.top, left: rect.left, bottom: rect.bottom };
            })
            .filter((entry) => entry.path && entry.bottom > 0 && entry.top < window.innerHeight);
          cells.sort((a, b) => (a.top - b.top) || (a.left - b.left));
          return cells.length ? cells[0].path : null;
        }"""
    )
    if not value or not isinstance(value, str):
        raise SmokeFailure("No visible gallery grid path found.")
    return value


def visible_grid_cell_ids(page: Page) -> list[str]:
    raw = page.evaluate(
        """() => {
          const cells = Array.from(document.querySelectorAll('[role="gridcell"][id^="cell-"]'))
            .map((el) => {
              const rect = el.getBoundingClientRect()
              return { id: el.id, top: rect.top, left: rect.left, bottom: rect.bottom, right: rect.right }
            })
            .filter((entry) => entry.id && entry.bottom > 0 && entry.right > 0 && entry.top < window.innerHeight && entry.left < window.innerWidth)
          cells.sort((a, b) => (a.top - b.top) || (a.left - b.left))
          return cells.map((entry) => entry.id)
        }"""
    )
    if not isinstance(raw, list):
        raise SmokeFailure("Failed to evaluate visible grid cells.")
    result: list[str] = []
    for candidate in raw:
        if isinstance(candidate, str) and candidate.startswith("cell-"):
            result.append(candidate)
    return result


def wait_for_visible_grid_cell_ids(page: Page, minimum_count: int, timeout_ms: float) -> list[str]:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    latest_ids: list[str] = []
    while time.monotonic() < deadline:
        latest_ids = visible_grid_cell_ids(page)
        if len(latest_ids) >= minimum_count:
            return latest_ids
        page.wait_for_timeout(120)
    raise SmokeFailure(
        f"Timed out waiting for {minimum_count} visible gallery grid cells. Last visible ids: {latest_ids!r}"
    )


def wait_for_top_name_prefix(page: Page, prefix: str, timeout_ms: float) -> str:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_name: str | None = None
    while time.monotonic() < deadline:
        try:
            current = top_visible_grid_path(page)
            last_name = current
            if current.startswith(prefix):
                return current
        except SmokeFailure:
            pass
        page.wait_for_timeout(120)
    raise SmokeFailure(
        f"Timed out waiting for top visible filename prefix '{prefix}'. Last observed: {last_name!r}"
    )


def wait_for_stable_top_name(page: Page, prefix: str, timeout_ms: float, stable_reads: int = 3) -> str:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_name: str | None = None
    stable_count = 0
    while time.monotonic() < deadline:
        current = wait_for_top_name_prefix(page, prefix, timeout_ms=1_000)
        if current == last_name:
            stable_count += 1
        else:
            last_name = current
            stable_count = 1
        if stable_count >= stable_reads:
            return current
        page.wait_for_timeout(180)
    raise SmokeFailure(
        f"Timed out waiting for stable top visible filename prefix '{prefix}'. "
        f"Last observed: {last_name!r}"
    )


def left_panel_state(page: Page) -> dict[str, Any]:
    payload = page.evaluate(
        """() => {
          const panel = document.querySelector('.app-left-panel');
          if (!panel) return null;
          const rect = panel.getBoundingClientRect();
          return {
            width: rect.width,
            contentOpen: panel.getAttribute('data-left-content-open') === 'true',
          };
        }"""
    )
    if not isinstance(payload, dict):
        raise SmokeFailure("Left panel is missing from the desktop layout.")
    return payload


def wait_for_left_panel_content_open(page: Page, open_state: bool, timeout_ms: float) -> dict[str, Any]:
    page.wait_for_function(
        """(expectedOpen) => {
          const panel = document.querySelector('.app-left-panel');
          return panel?.getAttribute('data-left-content-open') === String(expectedOpen);
        }""",
        arg=open_state,
        timeout=timeout_ms,
    )
    wait_for_ui_settled(page, timeout_ms)
    return left_panel_state(page)


def wait_for_visible_search_matches(page: Page, token: str, timeout_ms: float) -> list[str]:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    latest_matches: list[str] = []
    while time.monotonic() < deadline:
        raw_matches = page.eval_on_selector_all(
            ".thumb-filename",
            "nodes => nodes.map((n) => (n.textContent || '').trim()).filter(Boolean)",
        )
        latest_matches = [value for value in raw_matches if isinstance(value, str)]
        if latest_matches and all(token in name for name in latest_matches):
            return latest_matches
        page.wait_for_timeout(120)
    raise SmokeFailure(
        f"Timed out waiting for search results matching token '{token}'. "
        f"Last visible names={latest_matches!r}."
    )


def run_indexing_banner_scenario(page: Page) -> bool:
    indexing_banner = page.get_by_text("Indexing in progress").first
    try:
        indexing_banner.wait_for(state="visible", timeout=20_000)
        indexing_banner.wait_for(state="hidden", timeout=180_000)
        return True
    except PlaywrightTimeoutError:
        return False


def run_left_panel_scenario(page: Page) -> LeftPanelScenarioResult:
    left_width_before = float(
        page.eval_on_selector(".app-left-panel", "el => el.getBoundingClientRect().width")
    )
    tree_scroll_rect = page.eval_on_selector(
        "[aria-label='Folders']",
        """el => {
          const target = el.parentElement || el;
          const rect = target.getBoundingClientRect();
          return { left: rect.left, right: rect.right, top: rect.top, height: rect.height };
        }""",
    )
    drag_x = float(tree_scroll_rect["right"]) - 2.0
    drag_y = float(tree_scroll_rect["top"]) + min(float(tree_scroll_rect["height"]) * 0.6, 220.0)
    page.mouse.move(drag_x, drag_y)
    page.mouse.down()
    page.mouse.move(drag_x, drag_y + 160, steps=12)
    page.mouse.up()
    wait_for_ui_settled(page, 5_000)

    left_width_after = float(
        page.eval_on_selector(".app-left-panel", "el => el.getBoundingClientRect().width")
    )
    sidebar_resize_delta_px = abs(left_width_after - left_width_before)
    if sidebar_resize_delta_px > 1.5:
        raise SmokeFailure(
            f"Left sidebar width changed during scrollbar-lane drag: {left_width_before:.2f}px -> "
            f"{left_width_after:.2f}px."
        )

    page.get_by_role("button", name="Toggle left panel").click()
    collapsed_state = wait_for_left_panel_content_open(page, False, 5_000)
    left_collapsed_width_px = float(collapsed_state["width"])
    if collapsed_state["contentOpen"]:
        raise SmokeFailure("Toolbar left-panel toggle did not collapse left content.")
    if left_collapsed_width_px < 44.0 or left_collapsed_width_px > 84.0:
        raise SmokeFailure(
            "Left icon rail was not preserved at collapsed width: "
            f"{left_collapsed_width_px:.2f}px."
        )

    page.get_by_role("button", name="Folders").click()
    active_tab_open_state = wait_for_left_panel_content_open(page, True, 5_000)
    if not active_tab_open_state["contentOpen"]:
        raise SmokeFailure("Clicking active Folder tab did not re-open collapsed left content.")

    page.get_by_role("button", name="Folders").click()
    active_tab_collapsed_state = wait_for_left_panel_content_open(page, False, 5_000)
    if active_tab_collapsed_state["contentOpen"]:
        raise SmokeFailure("Clicking active Folder tab did not collapse left content.")

    page.keyboard.press("Control+B")
    hotkey_reopen_state = wait_for_left_panel_content_open(page, True, 5_000)
    left_hotkey_reopen_width_px = float(hotkey_reopen_state["width"])
    if not hotkey_reopen_state["contentOpen"]:
        raise SmokeFailure("Ctrl+B did not re-open left content from the collapsed icon rail state.")
    if left_hotkey_reopen_width_px < 200.0:
        raise SmokeFailure(
            "Left content panel reopened below expected width floor after Ctrl+B: "
            f"{left_hotkey_reopen_width_px:.2f}px."
        )

    return LeftPanelScenarioResult(
        sidebar_resize_delta_px=sidebar_resize_delta_px,
        left_collapsed_width_px=left_collapsed_width_px,
        left_hotkey_reopen_width_px=left_hotkey_reopen_width_px,
    )


def run_right_panel_resize_scenario(page: Page) -> RightPanelResizeScenarioResult:
    right_handle = page.locator(".app-right-panel .sidebar-resize-handle-right").first
    if right_handle.count() == 0:
        raise SmokeFailure("Right sidebar resize handle not found for desktop width check.")
    handle_box = right_handle.bounding_box()
    if handle_box is None:
        raise SmokeFailure("Right sidebar resize handle has no visible bounding box.")

    drag_start_x = float(handle_box["x"]) + max(2.0, float(handle_box["width"]) * 0.5)
    drag_y = float(handle_box["y"]) + min(float(handle_box["height"]) * 0.6, 220.0)
    page.mouse.move(drag_start_x, drag_y)
    page.mouse.down()
    page.mouse.move(8.0, drag_y, steps=20)
    page.mouse.up()
    wait_for_ui_settled(page, 5_000)

    right_resized_width_px = float(
        page.eval_on_selector(".app-right-panel", "el => el.getBoundingClientRect().width")
    )
    center_width_after_right_resize_px = float(
        page.eval_on_selector(".grid-shell", "el => el.getBoundingClientRect().width")
    )
    if right_resized_width_px < 560.0:
        raise SmokeFailure(
            f"Right inspector max width did not reach target at 1440px viewport: {right_resized_width_px:.2f}px."
        )
    if center_width_after_right_resize_px < 520.0:
        raise SmokeFailure(
            "Center pane width dropped below 520px during right inspector max resize: "
            f"{center_width_after_right_resize_px:.2f}px."
        )

    return RightPanelResizeScenarioResult(
        right_resized_width_px=right_resized_width_px,
        center_width_after_right_resize_px=center_width_after_right_resize_px,
    )


def run_anchor_and_search_scenario(
    page: Page,
    timeout_ms: float,
    strict_reentry_anchor: bool,
) -> AnchorSearchScenarioResult:
    page.locator("[role='treeitem']", has_text="alpha").first.click()
    wait_for_top_name_prefix(page, "/alpha/", timeout_ms=15_000)
    gallery = page.get_by_role("grid", name="Gallery")
    gallery.hover()
    page.mouse.wheel(0, 900)
    anchor_before = wait_for_stable_top_name(page, "/alpha/", timeout_ms=15_000, stable_reads=12)

    page.locator("[role='treeitem']", has_text="beta").first.click()
    wait_for_top_name_prefix(page, "/beta/", timeout_ms=15_000)
    page.locator("[role='treeitem']", has_text="alpha").first.click()
    anchor_restored = wait_for_top_name_prefix(page, "/alpha/", timeout_ms=15_000)
    anchor_settled = wait_for_stable_top_name(page, "/alpha/", timeout_ms=15_000, stable_reads=4)
    anchor_reentry_exact = anchor_settled == anchor_before
    if strict_reentry_anchor and not anchor_reentry_exact:
        raise SmokeFailure(
            "Folder re-entry top-anchor mismatch: "
            f"before={anchor_before}, restored={anchor_restored}, settled={anchor_settled}."
        )

    search_box = page.get_by_label("Search filename, tags, notes").first
    token = Path(anchor_before).name.rsplit(".", 1)[0]
    search_box.fill(token)
    search_visible_matches = wait_for_visible_search_matches(page, token, timeout_ms=15_000)

    search_box.fill("")
    wait_for_visible_grid_cell_ids(page, minimum_count=2, timeout_ms=timeout_ms)
    return AnchorSearchScenarioResult(
        anchor_before=anchor_before,
        anchor_restored=anchor_restored,
        anchor_settled=anchor_settled,
        anchor_reentry_exact=anchor_reentry_exact,
        search_visible_matches=search_visible_matches,
    )


def select_first_visible_grid_cell(page: Page, timeout_ms: float) -> str:
    cell_ids = wait_for_visible_grid_cell_ids(page, minimum_count=1, timeout_ms=timeout_ms)
    first_cell_id = cell_ids[0]
    page.locator(f"[id='{first_cell_id}']").first.click()
    return first_cell_id


def prepare_reorder_scenario(page: Page, timeout_ms: float) -> None:
    # Work around current production-bundle instability when selecting while inspector is mounted.
    set_right_panel_open(page, open_state=False, timeout_ms=10_000)
    select_first_visible_grid_cell(page, timeout_ms=timeout_ms)
    set_right_panel_open(page, open_state=True, timeout_ms=10_000)
    ensure_inspector_reorder_handles(page, timeout_ms=10_000)


def run_inspector_reorder_scenario(page: Page, timeout_ms: float) -> InspectorReorderScenarioResult:
    prepare_reorder_scenario(page, timeout_ms=timeout_ms)

    inspector_default_order = inspector_section_order(page)
    assert_section_precedes(inspector_default_order, "metadata", "basics", "default order assertion")

    reorder_basics = page.get_by_role("button", name="Reorder Basics").first
    reorder_metadata = page.get_by_role("button", name="Reorder Metadata").first
    basics_box = reorder_basics.bounding_box()
    metadata_box = reorder_metadata.bounding_box()
    if basics_box is None or metadata_box is None:
        raise SmokeFailure("Inspector reorder handles are not visible for section-order validation.")

    basics_center_x = float(basics_box["x"]) + (float(basics_box["width"]) * 0.5)
    basics_center_y = float(basics_box["y"]) + (float(basics_box["height"]) * 0.5)
    metadata_center_x = float(metadata_box["x"]) + (float(metadata_box["width"]) * 0.5)
    metadata_center_y = float(metadata_box["y"]) + (float(metadata_box["height"]) * 0.5)

    page.mouse.move(basics_center_x, basics_center_y)
    page.mouse.down()
    page.mouse.move(metadata_center_x, metadata_center_y, steps=18)
    page.mouse.up()

    inspector_reordered_order = wait_for_section_precedence(
        page,
        first="basics",
        second="metadata",
        timeout_ms=10_000,
        context="post-drag order assertion",
    )

    page.reload(wait_until="domcontentloaded")
    page.get_by_role("grid", name="Gallery").wait_for(state="visible")
    prepare_reorder_scenario(page, timeout_ms=timeout_ms)

    inspector_reloaded_order = wait_for_section_precedence(
        page,
        first="basics",
        second="metadata",
        timeout_ms=10_000,
        context="reload persistence assertion",
    )
    return InspectorReorderScenarioResult(
        inspector_default_order=inspector_default_order,
        inspector_reordered_order=inspector_reordered_order,
        inspector_reloaded_order=inspector_reloaded_order,
    )


def run_compare_export_scenario(page: Page, timeout_ms: float) -> None:
    set_right_panel_open(page, open_state=False, timeout_ms=10_000)
    visible_cell_ids = wait_for_visible_grid_cell_ids(page, minimum_count=2, timeout_ms=timeout_ms)
    first_cell_id = visible_cell_ids[0]
    page.locator(f"[id='{first_cell_id}']").first.click()

    visible_cell_ids = wait_for_visible_grid_cell_ids(page, minimum_count=2, timeout_ms=timeout_ms)
    second_cell_id = next((cell_id for cell_id in visible_cell_ids if cell_id != first_cell_id), None)
    if second_cell_id is None:
        raise SmokeFailure(
            f"Failed to resolve a distinct second grid cell for multi-select. Visible ids: {visible_cell_ids!r}"
        )

    page.locator(f"[id='{second_cell_id}']").first.click(modifiers=["Control"])
    set_right_panel_open(page, open_state=True, timeout_ms=10_000)

    page.get_by_text("2 files").first.wait_for(state="visible")
    side_by_side = page.get_by_role("button", name="Side by side view").first
    if side_by_side.is_disabled():
        raise SmokeFailure("Side by side action is disabled for exactly two selections.")
    side_by_side.click()
    compare_dialog = page.get_by_role("dialog", name="Compare images")
    compare_dialog.wait_for(state="visible")
    compare_dialog.get_by_role("button", name="Close").click()
    compare_dialog.wait_for(state="hidden")

    export_entries = page.get_by_role("button", name="Export comparison")
    enabled_export_idx: int | None = None
    for idx in range(export_entries.count()):
        if export_entries.nth(idx).is_enabled():
            enabled_export_idx = idx
            break
    if enabled_export_idx is None:
        raise SmokeFailure("No enabled inspector Export comparison entry action found.")

    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/export-comparison")
    ) as export_response_info:
        export_entries.nth(enabled_export_idx).click()
    if export_response_info.value.status != 200:
        raise SmokeFailure(
            f"Comparison export request returned unexpected status: {export_response_info.value.status}."
        )


def run_metadata_compare_cap_scenario(page: Page, timeout_ms: float) -> str:
    set_right_panel_open(page, open_state=False, timeout_ms=10_000)
    over_cap_cell_ids = wait_for_visible_grid_cell_ids(page, minimum_count=7, timeout_ms=timeout_ms)
    page.locator(f"[id='{over_cap_cell_ids[0]}']").first.click()
    wait_for_grid_selection_count(page, 1, 5_000)
    page.keyboard.down("Control")
    try:
        for selected_count, cell_id in enumerate(over_cap_cell_ids[1:7], start=2):
            page.locator(f"[id='{cell_id}']").first.click()
            wait_for_grid_selection_count(page, selected_count, 5_000)
    finally:
        page.keyboard.up("Control")

    selected_cell_count = page.evaluate(
        """() => document.querySelectorAll('[role="gridcell"][aria-selected="true"]').length"""
    )
    if not isinstance(selected_cell_count, int) or selected_cell_count < 7:
        raise SmokeFailure(
            "Failed to assemble seven selected grid cells for metadata compare over-cap validation: "
            f"selected={selected_cell_count!r}, candidate_ids={over_cap_cell_ids[:7]!r}."
        )

    set_right_panel_open(page, open_state=True, timeout_ms=10_000)
    page.get_by_text("7 files").first.wait_for(state="visible")
    compare_metadata_button = page.get_by_role("button", name="Compare metadata").first
    if compare_metadata_button.is_disabled():
        raise SmokeFailure("Compare metadata action is disabled for seven selections.")
    compare_metadata_button.click()

    compare_over_cap_notice = page.get_by_text(re.compile(r"\+\s*1\s+not shown\.?")).first
    compare_over_cap_notice.wait_for(state="visible")
    inspector_compare_over_cap_message = " ".join(compare_over_cap_notice.inner_text().split())
    if not re.fullmatch(r"\+\s*1\s+not shown\.?", inspector_compare_over_cap_message):
        raise SmokeFailure(
            "Unexpected metadata compare over-cap message text: "
            f"{inspector_compare_over_cap_message!r}."
        )
    return inspector_compare_over_cap_message


def run_browser_checks(base_url: str, timeout_ms: float, strict_reentry_anchor: bool) -> SmokeResult:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 980})
        try:
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            page.goto(base_url, wait_until="domcontentloaded")
            page.get_by_role("grid", name="Gallery").wait_for(state="visible")

            indexing_banner_seen = run_indexing_banner_scenario(page)
            left_panel = run_left_panel_scenario(page)
            right_panel = run_right_panel_resize_scenario(page)
            anchor_search = run_anchor_and_search_scenario(page, timeout_ms, strict_reentry_anchor)
            inspector_reorder = run_inspector_reorder_scenario(page, timeout_ms)
            run_compare_export_scenario(page, timeout_ms)
            inspector_compare_over_cap_message = run_metadata_compare_cap_scenario(page, timeout_ms)

            return SmokeResult(
                indexing_banner_seen=indexing_banner_seen,
                sidebar_resize_delta_px=left_panel.sidebar_resize_delta_px,
                left_collapsed_width_px=left_panel.left_collapsed_width_px,
                left_hotkey_reopen_width_px=left_panel.left_hotkey_reopen_width_px,
                right_resized_width_px=right_panel.right_resized_width_px,
                center_width_after_right_resize_px=right_panel.center_width_after_right_resize_px,
                anchor_before=anchor_search.anchor_before,
                anchor_restored=anchor_search.anchor_restored,
                anchor_settled=anchor_search.anchor_settled,
                anchor_reentry_exact=anchor_search.anchor_reentry_exact,
                search_visible_matches=anchor_search.search_visible_matches,
                inspector_default_order=inspector_reorder.inspector_default_order,
                inspector_reordered_order=inspector_reorder.inspector_reordered_order,
                inspector_reloaded_order=inspector_reorder.inspector_reloaded_order,
                inspector_compare_over_cap_message=inspector_compare_over_cap_message,
            )
        finally:
            context.close()
            browser.close()
