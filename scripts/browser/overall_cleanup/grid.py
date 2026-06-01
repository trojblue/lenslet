from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs

from scripts.browser.overall_cleanup.support import OverallCleanupBrowserFailure

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
          const mobileJustified = document.querySelector('[data-toolbar-control="drawer-layout-adaptive"]')
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

def path_from_grid_cell_id(cell_id: str) -> str:
    if not cell_id.startswith("cell-"):
        raise OverallCleanupBrowserFailure(f"Unexpected grid cell id: {cell_id!r}.")
    return parse_qs(f"path={cell_id.removeprefix('cell-')}")["path"][0]
