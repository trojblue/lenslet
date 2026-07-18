"""DOM helpers for the grid jitter probe."""

from __future__ import annotations

import re
from typing import Any

from scripts.smoke_harness import SmokeFailure

COUNT_LABEL_RE = re.compile(r"^\s*(\d[\d,]*)\s*(?:/\s*(\d[\d,]*)\s*)?items\s*$")


def read_toolbar_counts(page: Any) -> dict[str, Any]:
    label = page.locator(".toolbar-count").first.text_content()
    if not isinstance(label, str):
        raise SmokeFailure("Toolbar count label is missing.")
    match = COUNT_LABEL_RE.match(label.strip())
    if match is None:
        raise SmokeFailure(f"Unexpected toolbar count label: {label!r}")
    current = int(match.group(1).replace(",", ""))
    total_raw = match.group(2)
    total = current if total_raw is None else int(total_raw.replace(",", ""))
    return {
        "label": label.strip(),
        "current": current,
        "total": total,
    }


def visible_grid_paths(page: Any, limit: int = 12) -> list[str]:
    raw = page.evaluate(
        """(maxItems) => {
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
              return { path, top: rect.top, left: rect.left, bottom: rect.bottom, right: rect.right };
            })
            .filter((entry) => entry.path && entry.bottom > 0 && entry.right > 0 && entry.top < window.innerHeight && entry.left < window.innerWidth);
          cells.sort((a, b) => (a.top - b.top) || (a.left - b.left));
          return cells.slice(0, maxItems).map((entry) => entry.path);
        }""",
        limit,
    )
    if not isinstance(raw, list):
        raise SmokeFailure("Failed to capture visible grid paths.")
    return [candidate for candidate in raw if isinstance(candidate, str) and candidate]


def open_metrics_panel(page: Any, timeout_ms: float) -> None:
    button = page.locator('button[aria-label="Metrics and Filters"]').first
    if button.count() == 0:
        raise SmokeFailure("Metrics panel trigger is missing.")
    if button.get_attribute("aria-pressed") != "true":
        button.click()
    page.wait_for_function(
        """() => {
          const button = document.querySelector('button[aria-label="Metrics and Filters"]');
          return button instanceof HTMLButtonElement && button.getAttribute('aria-pressed') === 'true';
        }""",
        timeout=timeout_ms,
    )


def read_metric_panel_keys(page: Any) -> list[str]:
    trigger = page.locator('.app-left-panel [data-metric-selector] button[aria-haspopup="listbox"]').first
    if trigger.count() == 0:
        return []
    trigger.click()
    panel = page.locator('[role="listbox"][aria-label="Metric"]').first
    panel.wait_for(state="visible", timeout=5_000)
    raw = panel.locator("button.dropdown-item").evaluate_all(
        "nodes => nodes.map((node) => (node.textContent || '').trim()).filter(Boolean)"
    )
    page.keyboard.press("Escape")
    if not isinstance(raw, list):
        raise SmokeFailure("Failed to read metric panel options.")
    return [candidate for candidate in raw if isinstance(candidate, str)]


def snapshot_grid(page: Any) -> dict[str, Any]:
    snapshot = page.evaluate(
        """() => {
          const topStack = document.querySelector('[data-grid-top-stack]');
          const topStackRect = topStack instanceof HTMLElement ? topStack.getBoundingClientRect() : null;
          const bandNames = ['status', 'similarity', 'filters'];
          const bandHeights = {};
          const bandHidden = {};
          for (const bandName of bandNames) {
            const band = document.querySelector(`[data-grid-top-band="${bandName}"]`);
            if (!(band instanceof HTMLElement)) {
              bandHeights[bandName] = null;
              bandHidden[bandName] = null;
              continue;
            }
            const rect = band.getBoundingClientRect();
            bandHeights[bandName] = rect.height;
            bandHidden[bandName] = band.getAttribute('aria-hidden') === 'true';
          }

          const bodyMain = document.querySelector('[data-grid-body-main]');
          const bodyRect = bodyMain instanceof HTMLElement ? bodyMain.getBoundingClientRect() : null;
          const rail = document.querySelector('[data-metric-rail-slot]');
          const railRect = rail instanceof HTMLElement ? rail.getBoundingClientRect() : null;
          const railActive = rail instanceof HTMLElement
            ? rail.getAttribute('data-metric-rail-active') === 'true'
            : null;

          const scrollRoot = document.querySelector('[role="grid"][aria-label="Gallery"]');
          const scrollRootClasses = scrollRoot instanceof HTMLElement ? Array.from(scrollRoot.classList) : [];
          const usesHiddenScrollbar = scrollRootClasses.includes('scrollbar-hidden');

          const sortTrigger = document.querySelector('button[aria-label="Sort and layout"]');
          const sortDirection = document.querySelector('button[aria-label="Toggle sort direction"]');

          const firstCell = document.querySelector('[role="gridcell"][id^="cell-"]');
          const firstCellRect = firstCell instanceof HTMLElement ? firstCell.getBoundingClientRect() : null;

          return {
            topStackHeight: topStackRect ? topStackRect.height : null,
            topStackTop: topStackRect ? topStackRect.top : null,
            bandHeights,
            bandHidden,
            gridBodyWidth: bodyRect ? bodyRect.width : null,
            gridBodyLeft: bodyRect ? bodyRect.left : null,
            metricRailWidth: railRect ? railRect.width : null,
            metricRailActive: railActive,
            firstCellLeft: firstCellRect ? firstCellRect.left : null,
            firstCellWidth: firstCellRect ? firstCellRect.width : null,
            scrollRootClasses,
            scrollRootUsesHiddenScrollbar: usesHiddenScrollbar,
            sortLabel: sortTrigger instanceof HTMLButtonElement
              ? (sortTrigger.textContent || '').trim()
              : null,
            sortDirection: sortDirection instanceof HTMLButtonElement
              ? sortDirection.title
              : null,
          };
        }"""
    )
    if not isinstance(snapshot, dict):
        raise SmokeFailure("Failed to capture grid snapshot.")
    return snapshot
