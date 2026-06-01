"""Inspector jitter probe scenario."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from scripts.browser.gui_jitter.shared import (
    MILLISECONDS_PER_SECOND,
    ProbeResult,
    require_dict_snapshot,
    set_local_storage,
    wait_for_grid,
)
from scripts.smoke_harness import SmokeFailure, import_playwright

QUICK_ZERO_PATH = "/quick_00_meta.png"
QUICK_ONE_PATH = "/quick_01_meta.png"
PLAIN_PATH = "/quick_02_plain.png"
QUICK_THREE_PATH = "/quick_03_meta.png"

METADATA_DELAY_MS = {
    "quick_00_meta.png": 320,
    "quick_01_meta.png": 45,
    "quick_02_plain.png": 180,
    "quick_03_meta.png": 260,
}
DEFAULT_METADATA_DELAY_MS = 100


@dataclass(slots=True)
class InspectorSnapshots:
    quick_one_loaded: dict[str, Any]
    pending_quick: dict[str, Any]
    quick_three_loaded: dict[str, Any]
    pending_plain: dict[str, Any]
    plain_resolved: dict[str, Any]


def snapshot_quick_view_section(page: Any) -> dict[str, Any]:
    snapshot = page.evaluate(
        """() => {
          const section = document.querySelector('[data-inspector-section-id="quickView"]');
          if (!(section instanceof HTMLElement)) {
            return {
              present: false,
              top: null,
              height: null,
              rowCount: 0,
              placeholderRowCount: 0,
              loading: false,
              promptValue: null,
            };
          }

          const rect = section.getBoundingClientRect();
          const rows = Array.from(section.querySelectorAll('.ui-kv-row'));
          const visibleRows = rows.filter((row) => row.getAttribute('aria-hidden') !== 'true');
          const placeholderRows = rows.filter((row) => row.getAttribute('aria-hidden') === 'true');
          let promptValue = null;

          for (const row of visibleRows) {
            const label = row.querySelector('.ui-kv-label');
            const value = row.querySelector('.ui-kv-value');
            if (!(label instanceof HTMLElement) || !(value instanceof HTMLElement)) continue;
            if ((label.textContent || '').trim() !== 'Prompt') continue;
            promptValue = (value.textContent || '').trim();
            break;
          }

          return {
            present: true,
            top: rect.top,
            height: rect.height,
            rowCount: visibleRows.length,
            placeholderRowCount: placeholderRows.length,
            loading: (section.textContent || '').includes('Loading metadata…'),
            promptValue,
          };
        }"""
    )
    return require_dict_snapshot(snapshot, "Failed to capture Quick View snapshot.")


def quick_view_delta(lhs: dict[str, Any], rhs: dict[str, Any]) -> float:
    if not bool(lhs.get("present")) or not bool(rhs.get("present")):
        return 0.0
    try:
        top_delta = abs(float(lhs.get("top")) - float(rhs.get("top")))
        height_delta = abs(float(lhs.get("height")) - float(rhs.get("height")))
    except (TypeError, ValueError):
        return 0.0
    return max(top_delta, height_delta)


def select_grid_path(page: Any, path: str, browser_timeout_ms: float) -> None:
    selector = f'[id="cell-{quote(path, safe="")}"]'
    cell = page.locator(selector).first
    if cell.count() == 0:
        raise SmokeFailure(f"Grid cell for {path} not found.")
    cell.click()
    page.wait_for_function(
        """(targetPath) => {
          const panel = document.querySelector('.app-right-panel');
          if (!(panel instanceof HTMLElement)) return false;
          const filename = targetPath.split('/').filter(Boolean).pop() || targetPath;
          return (panel.textContent || '').includes(filename);
        }""",
        arg=path,
        timeout=browser_timeout_ms,
    )


def metadata_delay(route: Any) -> None:
    request_url = route.request.url
    delay_ms = DEFAULT_METADATA_DELAY_MS
    for name, configured_delay_ms in METADATA_DELAY_MS.items():
        if name in request_url:
            delay_ms = configured_delay_ms
            break
    time.sleep(delay_ms / MILLISECONDS_PER_SECOND)
    route.continue_()


def inspector_storage_payload() -> dict[str, str | None]:
    return {
        "autoloadImageMetadata": "true",
        "sortSpec": json.dumps({"kind": "builtin", "key": "name", "dir": "asc"}),
        "sortKey": "name",
        "sortDir": "asc",
        "selectedMetric": None,
        "filterAst": json.dumps({"and": []}),
        "starFilters": json.dumps([]),
        "lenslet.inspector.sections": json.dumps(
            {
                "quickView": True,
                "overview": True,
                "compare": True,
                "metadata": True,
                "basics": True,
                "notes": True,
            }
        ),
    }


def wait_for_prompt(page: Any, prompt_text: str, browser_timeout_ms: float, error_message: str) -> None:
    try:
        page.wait_for_function(
            """(expectedPrompt) => {
              const section = document.querySelector('[data-inspector-section-id="quickView"]');
              if (!(section instanceof HTMLElement)) return false;
              if ((section.textContent || '').includes('Loading metadata…')) return false;
              const promptRow = Array.from(section.querySelectorAll('.ui-kv-row')).find((row) => {
                const label = row.querySelector('.ui-kv-label');
                return label instanceof HTMLElement && (label.textContent || '').trim() === 'Prompt';
              });
              if (!(promptRow instanceof HTMLElement)) return false;
              const value = promptRow.querySelector('.ui-kv-value');
              const prompt = value instanceof HTMLElement ? (value.textContent || '').trim() : '';
              return prompt.includes(expectedPrompt);
            }""",
            arg=prompt_text,
            timeout=browser_timeout_ms,
        )
    except TimeoutError as exc:
        raise SmokeFailure(error_message) from exc


def wait_for_latest_prompt(page: Any, browser_timeout_ms: float) -> None:
    try:
        page.wait_for_function(
            """() => {
              const section = document.querySelector('[data-inspector-section-id="quickView"]');
              if (!(section instanceof HTMLElement)) return false;
              const promptRow = Array.from(section.querySelectorAll('.ui-kv-row')).find((row) => {
                const label = row.querySelector('.ui-kv-label');
                return label instanceof HTMLElement && (label.textContent || '').trim() === 'Prompt';
              });
              if (!(promptRow instanceof HTMLElement)) return false;
              const value = promptRow.querySelector('.ui-kv-value');
              const promptText = value instanceof HTMLElement ? (value.textContent || '').trim() : '';
              return promptText.includes('beta prompt')
                && !promptText.includes('alpha prompt')
                && !(section.textContent || '').includes('Loading metadata…');
            }""",
            timeout=browser_timeout_ms,
        )
    except TimeoutError as exc:
        raise SmokeFailure(
            "Timed out waiting for quick-view to settle on latest selection without stale hydration."
        ) from exc


def wait_for_quick_view_absent(page: Any, browser_timeout_ms: float) -> None:
    try:
        page.wait_for_function(
            """() => !document.querySelector('[data-inspector-section-id="quickView"]')""",
            timeout=browser_timeout_ms,
        )
    except TimeoutError as exc:
        raise SmokeFailure("Timed out waiting for Quick View reservation to clear for plain metadata.") from exc


def exercise_inspector_probe(page: Any, browser_timeout_ms: float) -> InspectorSnapshots:
    page.goto(page.url, wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)
    set_local_storage(page, inspector_storage_payload())
    page.reload(wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)

    select_grid_path(page, QUICK_ZERO_PATH, browser_timeout_ms)
    page.wait_for_timeout(20)
    select_grid_path(page, QUICK_ONE_PATH, browser_timeout_ms)
    wait_for_latest_prompt(page, browser_timeout_ms)
    quick_one_loaded = snapshot_quick_view_section(page)
    page.wait_for_timeout(120)

    select_grid_path(page, QUICK_THREE_PATH, browser_timeout_ms)
    pending_quick = snapshot_quick_view_section(page)
    wait_for_prompt(
        page,
        "gamma prompt",
        browser_timeout_ms,
        "Timed out waiting for quick-view quick->quick hydration.",
    )
    quick_three_loaded = snapshot_quick_view_section(page)
    page.wait_for_timeout(120)

    select_grid_path(page, PLAIN_PATH, browser_timeout_ms)
    pending_plain = snapshot_quick_view_section(page)
    wait_for_quick_view_absent(page, browser_timeout_ms)
    plain_resolved = snapshot_quick_view_section(page)

    return InspectorSnapshots(
        quick_one_loaded=quick_one_loaded,
        pending_quick=pending_quick,
        quick_three_loaded=quick_three_loaded,
        pending_plain=pending_plain,
        plain_resolved=plain_resolved,
    )


def inspector_violations(
    snapshots: InspectorSnapshots,
    *,
    max_delta_px: float,
    max_inspector_delta: float,
) -> list[str]:
    violations: list[str] = []
    if max_inspector_delta > max_delta_px:
        violations.append(
            f"inspector delta {max_inspector_delta:.3f}px exceeded threshold {max_delta_px:.3f}px"
        )
    if not bool(snapshots.pending_quick.get("present")):
        violations.append("quick->quick pending: expected Quick View section to remain mounted")
    if not bool(snapshots.pending_plain.get("present")):
        violations.append("quick->plain pending: expected Quick View section to remain mounted")
    if bool(snapshots.plain_resolved.get("present")):
        violations.append("quick->plain resolved: expected Quick View section to unmount after metadata settles")
    prompt_value = str(snapshots.quick_one_loaded.get("promptValue") or "")
    if "beta prompt" not in prompt_value or "alpha prompt" in prompt_value:
        violations.append("stale protection: expected quick-view prompt to match latest selection")
    return violations


def inspector_result(snapshots: InspectorSnapshots, max_delta_px: float) -> ProbeResult:
    quick_view_deltas = {
        "quick_to_quick_pending_delta": quick_view_delta(snapshots.quick_one_loaded, snapshots.pending_quick),
        "quick_to_quick_loaded_delta": quick_view_delta(snapshots.quick_one_loaded, snapshots.quick_three_loaded),
        "quick_to_plain_pending_delta": quick_view_delta(snapshots.quick_three_loaded, snapshots.pending_plain),
    }
    max_inspector_delta = max(quick_view_deltas.values(), default=0.0)
    violations = inspector_violations(
        snapshots,
        max_delta_px=max_delta_px,
        max_inspector_delta=max_inspector_delta,
    )
    if violations:
        raise SmokeFailure("; ".join(violations))
    return ProbeResult(
        scenario="inspector",
        max_delta_px=max_delta_px,
        max_inspector_delta_px=max_inspector_delta,
        checks={
            "quick_view_deltas_px": quick_view_deltas,
            "quick_one_loaded_snapshot": snapshots.quick_one_loaded,
            "pending_quick_snapshot": snapshots.pending_quick,
            "quick_three_loaded_snapshot": snapshots.quick_three_loaded,
            "pending_plain_snapshot": snapshots.pending_plain,
            "plain_resolved_snapshot": snapshots.plain_resolved,
            "violations": violations,
        },
    )


def run_inspector_probe(base_url: str, max_delta_px: float, browser_timeout_ms: float) -> ProbeResult:
    playwright_error, playwright_timeout_error, sync_playwright = import_playwright()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            context.route("**/metadata**", metadata_delay)
            page = context.new_page()
            page.set_default_timeout(browser_timeout_ms)
            page.goto(base_url, wait_until="domcontentloaded")
            snapshots = exercise_inspector_probe(page, browser_timeout_ms)
            context.close()
            browser.close()
    except playwright_timeout_error as exc:
        raise SmokeFailure(f"playwright timeout: {exc}") from exc
    except playwright_error as exc:
        raise SmokeFailure(f"playwright probe failed: {exc}") from exc
    return inspector_result(snapshots, max_delta_px)
