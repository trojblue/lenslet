"""Grid jitter probe scenario."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from scripts.browser.gui_jitter.grid_dom import (
    open_metrics_panel,
    read_metric_panel_keys,
    read_toolbar_counts,
    snapshot_grid,
    visible_grid_paths,
)
from scripts.browser.gui_jitter.shared import (
    ProbeResult,
    set_local_storage,
    state_delta,
    state_delta_nested,
    wait_for_grid,
)
from scripts.smoke_harness import SmokeFailure, import_playwright

SORT_PANEL_SELECTOR = '.dropdown-panel[role="listbox"][aria-label="Sort and layout"]'
BUILTIN_SORT_OPTIONS = {"Grid", "Justified rows", "Date added", "Filename", "Random"}


@dataclass(frozen=True, slots=True)
class GridProbeConfig:
    base_url: str
    max_delta_px: float
    browser_timeout_ms: float
    expected_metric_key: str | None = None
    forbidden_metric_keys: tuple[str, ...] = ()
    metric_filter_min: float | None = None
    metric_filter_max: float | None = None

    @property
    def uses_metric_filter(self) -> bool:
        return self.metric_filter_min is not None or self.metric_filter_max is not None


@dataclass(slots=True)
class GridProbeSnapshots:
    warmup_filters_active: dict[str, Any]
    builtin_initial: dict[str, Any]
    filters_active: dict[str, Any]
    filters_cleared: dict[str, Any]
    metric_mode: dict[str, Any]
    builtin_restored: dict[str, Any]
    metric_sort_label: str
    metric_sort_labels: list[str] = field(default_factory=list)
    metric_panel_keys: list[str] = field(default_factory=list)
    metric_desc_visible_paths: list[str] = field(default_factory=list)
    metric_asc_visible_paths: list[str] = field(default_factory=list)
    baseline_counts: dict[str, Any] | None = None
    filtered_counts: dict[str, Any] | None = None
    continuity: dict[str, Any] = field(default_factory=dict)


def ensure_sort_trigger(page: Any, browser_timeout_ms: float) -> Any:
    del browser_timeout_ms
    trigger = page.locator('button[aria-label="Sort and layout"]').first
    if trigger.count() == 0:
        raise SmokeFailure("Sort dropdown trigger is missing.")
    if trigger.is_disabled():
        raise SmokeFailure("Sort dropdown trigger is disabled.")
    return trigger


def open_sort_panel(page: Any, browser_timeout_ms: float) -> tuple[Any, Any]:
    trigger = ensure_sort_trigger(page, browser_timeout_ms)
    trigger.click()
    page.wait_for_selector(SORT_PANEL_SELECTOR, timeout=browser_timeout_ms)
    return trigger, page.locator(SORT_PANEL_SELECTOR).first


def list_metric_sort_labels(page: Any, browser_timeout_ms: float) -> list[str]:
    trigger, panel = open_sort_panel(page, browser_timeout_ms)
    option_labels = [label.strip() for label in panel.locator("button.dropdown-item").all_inner_texts()]
    metric_labels = [label for label in option_labels if label and label not in BUILTIN_SORT_OPTIONS]
    trigger.click()
    return metric_labels


def set_json_storage(page: Any, payload: dict[str, Any]) -> None:
    serialized: dict[str, str | None] = {}
    for key, value in payload.items():
        if value is None:
            serialized[key] = None
        elif isinstance(value, str):
            serialized[key] = value
        else:
            serialized[key] = json.dumps(value)
    set_local_storage(page, serialized)


def reload_with_state(page: Any, payload: dict[str, Any], browser_timeout_ms: float) -> None:
    set_json_storage(page, payload)
    page.reload(wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)


def wait_for_sort_state(page: Any, label: str, direction: str, browser_timeout_ms: float) -> None:
    page.wait_for_function(
        """(expected) => {
          const trigger = document.querySelector('button[aria-label="Sort and layout"]');
          const direction = document.querySelector('button[aria-label="Toggle sort direction"]');
          return trigger instanceof HTMLButtonElement
            && direction instanceof HTMLButtonElement
            && (trigger.textContent || '').trim() === expected.label
            && direction.title === expected.directionTitle;
        }""",
        arg={
            "label": label,
            "directionTitle": f"Sort {'descending' if direction == 'desc' else 'ascending'}",
        },
        timeout=browser_timeout_ms,
    )


def wait_for_count_change(page: Any, previous_label: str, browser_timeout_ms: float) -> None:
    page.wait_for_function(
        """(baselineLabel) => {
          const node = document.querySelector('.toolbar-count');
          if (!(node instanceof HTMLElement)) return false;
          const label = (node.textContent || '').trim();
          return label.includes('/') || label !== baselineLabel;
        }""",
        arg=previous_label,
        timeout=browser_timeout_ms,
    )


def wait_for_metric_rail(page: Any, *, active: bool, browser_timeout_ms: float) -> None:
    page.wait_for_function(
        """(expectedActive) => {
          const rail = document.querySelector('[data-metric-rail-slot]');
          if (!(rail instanceof HTMLElement)) return false;
          const isActive = rail.getAttribute('data-metric-rail-active') === 'true';
          return isActive === expectedActive;
        }""",
        arg=active,
        timeout=browser_timeout_ms,
    )


def select_sort_option(page: Any, label: str, browser_timeout_ms: float) -> None:
    _, panel = open_sort_panel(page, browser_timeout_ms)
    option = panel.locator("button.dropdown-item", has_text=label).first
    if option.count() == 0:
        available = panel.locator("button.dropdown-item").all_inner_texts()
        raise SmokeFailure(f"Sort option '{label}' not found. Available options: {available}")
    option.click()


def wait_for_filters_band(page: Any, *, hidden: bool, browser_timeout_ms: float) -> None:
    page.wait_for_function(
        """(expectedHidden) => {
          const band = document.querySelector('[data-grid-top-band="filters"]');
          if (!(band instanceof HTMLElement)) return false;
          const isHidden = band.getAttribute('aria-hidden') === 'true';
          return isHidden === expectedHidden;
        }""",
        arg=hidden,
        timeout=browser_timeout_ms,
    )


def enable_unrated_filter(
    page: Any,
    *,
    browser_timeout_ms: float,
    playwright_error: type[BaseException],
) -> None:
    filters_button = page.locator('button[title="Filters"]').first
    filters_button.click()
    page.wait_for_selector('[role="dialog"][aria-label="Filters"]', timeout=browser_timeout_ms)
    page.locator('[role="dialog"][aria-label="Filters"] button:has-text("Unrated")').first.click()
    try:
        filters_button.click()
    except playwright_error as exc:
        raise SmokeFailure("Failed to close filters dialog after enabling Unrated filter.") from exc
    wait_for_filters_band(page, hidden=False, browser_timeout_ms=browser_timeout_ms)


def clear_filter_chips(page: Any, browser_timeout_ms: float) -> None:
    clear_button = page.locator('[data-grid-top-band="filters"] button:has-text("Clear all")').first
    if clear_button.count() > 0:
        clear_button.click()
    wait_for_filters_band(page, hidden=True, browser_timeout_ms=browser_timeout_ms)


def base_grid_payload() -> dict[str, Any]:
    return {
        "sortSpec": {"kind": "builtin", "key": "added", "dir": "desc"},
        "sortKey": "added",
        "sortDir": "desc",
        "selectedMetric": None,
        "filterAst": {"and": []},
        "starFilters": [],
    }


def verify_metric_options(config: GridProbeConfig, sort_labels: list[str], panel_keys: list[str]) -> str:
    if not sort_labels:
        raise SmokeFailure("No metric sort options found in the sort menu.")
    expected = config.expected_metric_key
    if expected and expected not in sort_labels:
        raise SmokeFailure(
            f"Expected metric sort option '{expected}' not found. Available metric options: {sort_labels}"
        )
    forbidden_sort = [key for key in config.forbidden_metric_keys if key in sort_labels]
    if forbidden_sort:
        raise SmokeFailure(f"Forbidden metric sort options found: {forbidden_sort}")
    if expected and expected not in panel_keys:
        raise SmokeFailure(
            f"Expected metric filter option '{expected}' not found. Available metric filters: {panel_keys}"
        )
    forbidden_panel = [key for key in config.forbidden_metric_keys if key in panel_keys]
    if forbidden_panel:
        raise SmokeFailure(f"Forbidden metric filter options found: {forbidden_panel}")
    return expected or sort_labels[0]


def apply_metric_filter_if_requested(
    page: Any,
    config: GridProbeConfig,
    *,
    metric_key: str,
    base_payload: dict[str, Any],
    baseline_counts: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not config.uses_metric_filter:
        return None
    reload_with_state(
        page,
        {
            **base_payload,
            "selectedMetric": metric_key,
            "filterAst": {
                "and": [
                    {
                        "metricRange": {
                            "key": metric_key,
                            "min": config.metric_filter_min if config.metric_filter_min is not None else -1e308,
                            "max": config.metric_filter_max if config.metric_filter_max is not None else 1e308,
                        }
                    }
                ]
            },
        },
        config.browser_timeout_ms,
    )
    if baseline_counts is not None:
        wait_for_count_change(page, baseline_counts["label"], config.browser_timeout_ms)
    return read_toolbar_counts(page)


def install_browse_query_controller(page: Any) -> None:
    page.evaluate(
        """() => {
          if (window.__lensletBrowseQueryController) return;
          const originalFetch = window.fetch.bind(window);
          const controller = {
            nextDelayMs: 0,
            textDelays: {},
            pathDelays: {},
            errorText: null,
            requests: [],
          };
          window.__lensletBrowseQueryController = controller;
          window.fetch = async (...args) => {
            const input = args[0];
            const init = args[1] || {};
            const rawUrl = input instanceof Request ? input.url : String(input);
            const pathname = new URL(rawUrl, location.href).pathname;
            if (pathname !== '/folders/query') return originalFetch(...args);
            let payload = {};
            try {
              const rawBody = input instanceof Request ? await input.clone().text() : init.body;
              payload = rawBody ? JSON.parse(String(rawBody)) : {};
            } catch {}
            const textQuery = payload.text_query || '';
            const scopePath = payload.path || '/';
            const delayMs = controller.nextDelayMs
              || controller.textDelays[textQuery]
              || controller.pathDelays[scopePath]
              || 0;
            controller.nextDelayMs = 0;
            controller.requests.push({
              at: performance.now(),
              textQuery,
              scopePath,
              sort: payload.sort || null,
              filters: payload.filters || null,
              delayMs,
            });
            const response = await originalFetch(...args);
            if (delayMs > 0) {
              await new Promise(resolve => setTimeout(resolve, delayMs));
            }
            if (controller.errorText === textQuery) {
              return new Response(JSON.stringify({ detail: 'forced browse probe failure' }), {
                status: 503,
                headers: { 'Content-Type': 'application/json' },
              });
            }
            return response;
          };
        }"""
    )


def configure_browse_queries(page: Any, **updates: Any) -> None:
    page.evaluate(
        """updates => {
          const controller = window.__lensletBrowseQueryController;
          if (!controller) throw new Error('browse query controller is not installed');
          Object.assign(controller, updates);
        }""",
        updates,
    )


def browse_query_request_count(page: Any) -> int:
    return int(page.evaluate("() => window.__lensletBrowseQueryController?.requests.length || 0"))


def wait_for_browse_query(page: Any, previous_count: int, timeout_ms: float) -> None:
    page.wait_for_function(
        """previous => (
          (window.__lensletBrowseQueryController?.requests.length || 0) > previous
        )""",
        arg=previous_count,
        timeout=timeout_ms,
    )


def start_browse_frame_trace(page: Any) -> None:
    page.evaluate(
        """() => {
          const frames = [];
          let active = true;
          const sample = now => {
            const grid = document.querySelector('[role="grid"][aria-label="Gallery"]');
            const shell = document.querySelector('[data-browse-shell]');
            const countLabel = document.querySelector('.toolbar-count');
            const rail = document.querySelector('[data-metric-rail-slot]');
            let ratingCounts = {};
            try {
              ratingCounts = JSON.parse(shell?.getAttribute('data-browse-rating-counts') || '{}');
            } catch {}
            const filterDialog = document.querySelector('[role="dialog"][aria-label="Filters"]');
            for (const button of filterDialog?.querySelectorAll('button.dropdown-item') || []) {
              const spans = button.querySelectorAll('span');
              if (spans.length < 2) continue;
              const label = (spans[0].textContent || '').trim();
              const count = Number.parseInt((spans[spans.length - 1].textContent || '').trim(), 10);
              if (!Number.isFinite(count)) continue;
              if (label === 'Unrated') ratingCounts['0'] = count;
              else if (label.includes('★')) ratingCounts[String((label.match(/★/g) || []).length)] = count;
            }
            const filteredLabels = [];
            for (const card of document.querySelectorAll(
              '[data-metric-histogram-card], [data-categorical-card], [data-metric-category-card]'
            )) {
              for (const span of card.querySelectorAll('span')) {
                const text = (span.textContent || '').trim();
                if (/^Filtered:\\s*[\\d,]+$/.test(text)) filteredLabels.push(text);
              }
            }
            const paths = Array.from(grid?.querySelectorAll('[role="gridcell"][id^="cell-"]') || [])
              .map(cell => {
                try { return decodeURIComponent(cell.id.slice(5)); } catch { return ''; }
              })
              .filter(Boolean);
            frames.push({
              now,
              phase: grid?.getAttribute('data-grid-presentation-phase') || null,
              gridState: document.querySelector('[data-grid-state]')?.getAttribute('data-grid-state') || null,
              interactionDisabled: grid?.getAttribute('data-grid-interaction-disabled') === 'true',
              cellCount: paths.length,
              paths,
              countLabel: (countLabel?.textContent || '').trim() || null,
              railActive: rail?.getAttribute('data-metric-rail-active') === 'true',
              railInteractionDisabled:
                rail?.getAttribute('data-metric-rail-interaction-disabled') === 'true',
              ratingCounts,
              filteredLabels,
              presentedTarget: shell?.getAttribute('data-browse-presentation-target') || null,
              requestedTarget: shell?.getAttribute('data-browse-requested-target') || null,
              epoch: Number(shell?.getAttribute('data-browse-presentation-epoch') || 0),
            });
            if (active) requestAnimationFrame(sample);
          };
          window.__lensletBrowseFrameTrace = { frames, stop: () => { active = false; } };
          requestAnimationFrame(sample);
        }"""
    )


def stop_browse_frame_trace(page: Any) -> list[dict[str, Any]]:
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    frames = page.evaluate(
        """() => {
          const trace = window.__lensletBrowseFrameTrace;
          trace?.stop();
          const frames = trace?.frames || [];
          delete window.__lensletBrowseFrameTrace;
          return frames;
        }"""
    )
    if not isinstance(frames, list):
        raise SmokeFailure("Failed to capture browse presentation frames.")
    return [frame for frame in frames if isinstance(frame, dict)]


def wait_for_steady_count(page: Any, current: int, timeout_ms: float) -> None:
    page.wait_for_function(
        """expected => {
          const grid = document.querySelector('[role="grid"][aria-label="Gallery"]');
          const label = (document.querySelector('.toolbar-count')?.textContent || '').trim();
          const parsed = Number.parseInt(label.replaceAll(',', ''), 10);
          return grid?.getAttribute('data-grid-presentation-phase') === 'steady'
            && grid.getAttribute('aria-busy') !== 'true'
            && parsed === expected;
        }""",
        arg=current,
        timeout=timeout_ms,
    )


def wait_for_steady_presentation(page: Any, timeout_ms: float) -> None:
    page.wait_for_function(
        """() => {
          const grid = document.querySelector('[role="grid"][aria-label="Gallery"]');
          return grid?.getAttribute('data-grid-presentation-phase') === 'steady'
            && grid.getAttribute('aria-busy') !== 'true';
        }""",
        timeout=timeout_ms,
    )


def read_filter_rating_counts(page: Any) -> dict[str, int]:
    result = page.evaluate(
        """() => {
          const counts = {};
          const dialog = document.querySelector('[role="dialog"][aria-label="Filters"]');
          for (const button of dialog?.querySelectorAll('button.dropdown-item') || []) {
            const spans = button.querySelectorAll('span');
            if (spans.length < 2) continue;
            const label = (spans[0].textContent || '').trim();
            const count = Number.parseInt((spans[spans.length - 1].textContent || '').trim(), 10);
            if (!Number.isFinite(count)) continue;
            if (label === 'Unrated') counts['0'] = count;
            else if (label.includes('★')) counts[String((label.match(/★/g) || []).length)] = count;
          }
          return counts;
        }"""
    )
    return {str(key): int(value) for key, value in result.items()}


def exercise_atomic_browse_continuity(
    page: Any,
    config: GridProbeConfig,
    metric_sort_label: str,
) -> dict[str, Any]:
    timeout_ms = config.browser_timeout_ms
    install_browse_query_controller(page)
    baseline_counts = read_toolbar_counts(page)

    first_cell = page.locator('[role="gridcell"][id^="cell-"]').first
    selected_path = visible_grid_paths(page, limit=1)[0]
    first_cell.click()
    five_star = page.locator('.app-right-panel button[aria-label="5 stars"]').first
    five_star.wait_for(state="visible", timeout=timeout_ms)

    slow_sort_request_count = browse_query_request_count(page)
    configure_browse_queries(page, nextDelayMs=1_100)
    start_browse_frame_trace(page)
    select_sort_option(page, metric_sort_label, timeout_ms)
    wait_for_browse_query(page, slow_sort_request_count, timeout_ms)
    page.wait_for_function(
        """() => document.querySelector('[role="grid"][aria-label="Gallery"]')
          ?.getAttribute('data-grid-presentation-phase') === 'grace'""",
        timeout=timeout_ms,
    )
    five_star.click()
    page.wait_for_function(
        """() => document.querySelector('.app-right-panel button[aria-label="5 stars"]')
          ?.getAttribute('aria-pressed') === 'true'""",
        timeout=timeout_ms,
    )
    wait_for_sort_state(page, metric_sort_label, "asc", timeout_ms)
    wait_for_steady_presentation(page, timeout_ms)
    wait_for_metric_rail(page, active=True, browser_timeout_ms=timeout_ms)
    slow_sort_frames = stop_browse_frame_trace(page)

    fast_sort_request_count = browse_query_request_count(page)
    configure_browse_queries(page, nextDelayMs=350)
    start_browse_frame_trace(page)
    page.locator('button[aria-label="Toggle sort direction"]').first.click()
    wait_for_browse_query(page, fast_sort_request_count, timeout_ms)
    wait_for_sort_state(page, metric_sort_label, "desc", timeout_ms)
    wait_for_steady_presentation(page, timeout_ms)
    fast_sort_frames = stop_browse_frame_trace(page)

    filters_button = page.locator('button[title="Filters"]').first
    filters_button.click()
    filter_dialog = page.locator('[role="dialog"][aria-label="Filters"]').first
    filter_dialog.wait_for(state="visible", timeout=timeout_ms)
    rating_counts_before = read_filter_rating_counts(page)
    filter_request_count = browse_query_request_count(page)
    configure_browse_queries(page, nextDelayMs=450)
    start_browse_frame_trace(page)
    filter_dialog.locator('button.dropdown-item', has_text="Unrated").first.click()
    wait_for_browse_query(page, filter_request_count, timeout_ms)
    wait_for_steady_count(page, baseline_counts["current"] - 1, timeout_ms)
    filter_frames = stop_browse_frame_trace(page)
    filtered_counts = read_toolbar_counts(page)
    rating_counts_after = read_filter_rating_counts(page)

    slow_filter_request_count = browse_query_request_count(page)
    configure_browse_queries(page, nextDelayMs=1_100)
    start_browse_frame_trace(page)
    filter_dialog.locator('button.dropdown-item').nth(1).click()
    wait_for_browse_query(page, slow_filter_request_count, timeout_ms)
    wait_for_steady_count(page, baseline_counts["current"] - 1, timeout_ms)
    slow_filter_frames = stop_browse_frame_trace(page)

    clear_request_count = browse_query_request_count(page)
    filter_dialog.locator('button.dropdown-item').nth(1).click()
    wait_for_browse_query(page, clear_request_count, timeout_ms)
    wait_for_steady_count(page, baseline_counts["current"] - 1, timeout_ms)
    clear_request_count = browse_query_request_count(page)
    filter_dialog.locator('button.dropdown-item', has_text="Unrated").first.click()
    wait_for_browse_query(page, clear_request_count, timeout_ms)
    wait_for_steady_count(page, baseline_counts["current"], timeout_ms)
    filters_button.click()

    select_sort_option(page, "Date added", timeout_ms)
    wait_for_sort_state(page, "Date added", "desc", timeout_ms)
    search = page.get_by_label("Search filename, tags, notes").first
    configure_browse_queries(
        page,
        textDelays={"sample_00": 900, "quick_0": 650, "sample_010": 100},
    )
    rapid_request_count = browse_query_request_count(page)
    start_browse_frame_trace(page)
    for expected_count, term in enumerate(("sample_00", "quick_0", "sample_010"), start=1):
        search.fill(term)
        wait_for_browse_query(page, rapid_request_count + expected_count - 1, timeout_ms)
    page.wait_for_function(
        """() => {
          const grid = document.querySelector('[role="grid"][aria-label="Gallery"]');
          const paths = Array.from(grid?.querySelectorAll('[role="gridcell"][id^="cell-"]') || [])
            .map(cell => decodeURIComponent(cell.id.slice(5)));
          return grid?.getAttribute('data-grid-presentation-phase') === 'steady'
            && paths.length > 0
            && paths.every(path => path.includes('sample_010'));
        }""",
        timeout=timeout_ms,
    )
    page.wait_for_timeout(1_000)
    rapid_frames = stop_browse_frame_trace(page)
    configure_browse_queries(page, textDelays={})
    search.fill("")
    wait_for_steady_count(page, baseline_counts["current"], timeout_ms)

    start_browse_frame_trace(page)
    search.fill("no-terminal-match")
    page.wait_for_function(
        """() => document.querySelector('[data-grid-state]')
          ?.getAttribute('data-grid-state') === 'empty'""",
        timeout=timeout_ms,
    )
    empty_frames = stop_browse_frame_trace(page)
    search.fill("")
    wait_for_steady_count(page, baseline_counts["current"], timeout_ms)

    configure_browse_queries(page, errorText="forced-error")
    start_browse_frame_trace(page)
    search.fill("forced-error")
    page.wait_for_function(
        """() => document.querySelector('[data-grid-state]')
          ?.getAttribute('data-grid-state') === 'failed'""",
        timeout=timeout_ms,
    )
    error_frames = stop_browse_frame_trace(page)
    configure_browse_queries(page, errorText=None)
    search.fill("")
    wait_for_steady_count(page, baseline_counts["current"], timeout_ms)

    configure_browse_queries(page, pathDelays={"/scope_a": 450})
    start_browse_frame_trace(page)
    page.evaluate("() => { window.location.hash = '#/scope_a'; }")
    wait_for_steady_count(page, 2, timeout_ms)
    scope_reset_frames = stop_browse_frame_trace(page)
    page.evaluate("() => { window.location.hash = '#/'; }")
    wait_for_steady_count(page, baseline_counts["current"], timeout_ms)
    configure_browse_queries(page, pathDelays={})

    settings_button = page.get_by_label("Settings").first
    settings_button.click()
    source_trigger = page.get_by_label("Image column").first
    source_trigger.wait_for(state="visible", timeout=timeout_ms)
    current_source = source_trigger.get_attribute("title")
    next_source = "source_alt" if current_source != "source_alt" else "source"
    source_request_count = browse_query_request_count(page)
    configure_browse_queries(page, pathDelays={"/": 450})
    start_browse_frame_trace(page)
    page.wait_for_timeout(50)
    source_trigger.click()
    source_panel = page.locator(
        '.dropdown-panel[role="listbox"][aria-label="Image column"]'
    ).first
    source_panel.wait_for(state="visible", timeout=timeout_ms)
    source_panel.locator("button.dropdown-item", has_text=next_source).first.click()
    wait_for_browse_query(page, source_request_count, timeout_ms)
    active_source = page.evaluate(
        """async () => {
          const response = await fetch('/table/source-columns');
          return (await response.json()).current;
        }"""
    )
    if active_source != next_source:
        raise SmokeFailure(
            f"Source reset selected {next_source!r}, but backend reported {active_source!r}."
        )
    wait_for_steady_count(page, baseline_counts["current"], timeout_ms)
    source_reset_frames = stop_browse_frame_trace(page)
    configure_browse_queries(page, pathDelays={})

    return {
        "baseline_counts": baseline_counts,
        "selected_path": selected_path,
        "rating_counts_before_filter": rating_counts_before,
        "rating_counts_after_filter": rating_counts_after,
        "filtered_counts": filtered_counts,
        "fast_filter_frames": filter_frames,
        "slow_filter_frames": slow_filter_frames,
        "fast_sort_frames": fast_sort_frames,
        "slow_sort_frames": slow_sort_frames,
        "rapid_frames": rapid_frames,
        "empty_frames": empty_frames,
        "error_frames": error_frames,
        "scope_reset_frames": scope_reset_frames,
        "source_reset_frames": source_reset_frames,
    }


def exercise_grid_probe(
    page: Any,
    config: GridProbeConfig,
    playwright_error: type[BaseException],
) -> GridProbeSnapshots:
    page.goto(config.base_url, wait_until="domcontentloaded")
    wait_for_grid(page, config.browser_timeout_ms)
    payload = base_grid_payload()
    reload_with_state(page, payload, config.browser_timeout_ms)
    baseline_counts = read_toolbar_counts(page)

    enable_unrated_filter(page, browser_timeout_ms=config.browser_timeout_ms, playwright_error=playwright_error)
    warmup_filters_active = snapshot_grid(page)
    clear_filter_chips(page, config.browser_timeout_ms)
    builtin_initial = snapshot_grid(page)

    enable_unrated_filter(page, browser_timeout_ms=config.browser_timeout_ms, playwright_error=playwright_error)
    filters_active = snapshot_grid(page)
    clear_filter_chips(page, config.browser_timeout_ms)
    filters_cleared = snapshot_grid(page)

    sort_labels = list_metric_sort_labels(page, config.browser_timeout_ms)
    open_metrics_panel(page, config.browser_timeout_ms)
    panel_keys = read_metric_panel_keys(page)
    metric_sort_label = verify_metric_options(config, sort_labels, panel_keys)

    select_sort_option(page, metric_sort_label, config.browser_timeout_ms)
    wait_for_metric_rail(page, active=True, browser_timeout_ms=config.browser_timeout_ms)
    wait_for_sort_state(page, metric_sort_label, "desc", config.browser_timeout_ms)
    metric_mode = snapshot_grid(page)
    metric_desc_visible_paths = visible_grid_paths(page)

    page.locator('button[aria-label="Toggle sort direction"]').first.click()
    wait_for_sort_state(page, metric_sort_label, "asc", config.browser_timeout_ms)
    page.wait_for_timeout(150)
    metric_asc_visible_paths = visible_grid_paths(page)

    select_sort_option(page, "Date added", config.browser_timeout_ms)
    wait_for_sort_state(page, "Date added", "asc", config.browser_timeout_ms)
    wait_for_metric_rail(page, active=False, browser_timeout_ms=config.browser_timeout_ms)
    builtin_restored = snapshot_grid(page)

    continuity_sort_label = next(
        (label for label in sort_labels if label != metric_sort_label),
        metric_sort_label,
    )
    continuity = exercise_atomic_browse_continuity(page, config, continuity_sort_label)
    filtered_counts = apply_metric_filter_if_requested(
        page,
        config,
        metric_key=config.expected_metric_key or metric_sort_label,
        base_payload=payload,
        baseline_counts=baseline_counts,
    )
    return GridProbeSnapshots(
        warmup_filters_active=warmup_filters_active,
        builtin_initial=builtin_initial,
        filters_active=filters_active,
        filters_cleared=filters_cleared,
        metric_mode=metric_mode,
        builtin_restored=builtin_restored,
        metric_sort_label=metric_sort_label,
        metric_sort_labels=sort_labels,
        metric_panel_keys=panel_keys,
        metric_desc_visible_paths=metric_desc_visible_paths,
        metric_asc_visible_paths=metric_asc_visible_paths,
        baseline_counts=baseline_counts,
        filtered_counts=filtered_counts,
        continuity=continuity,
    )


def grid_top_stack_deltas(snapshots: GridProbeSnapshots) -> dict[str, float]:
    deltas = {
        "baseline_to_filters_top_stack_delta": state_delta(
            snapshots.builtin_initial,
            snapshots.filters_active,
            "topStackHeight",
        ),
        "baseline_to_restored_top_stack_delta": state_delta(
            snapshots.builtin_initial,
            snapshots.filters_cleared,
            "topStackHeight",
        ),
    }
    for band_name in ("status", "similarity", "filters"):
        deltas[f"baseline_to_filters_{band_name}_band_delta"] = state_delta_nested(
            snapshots.builtin_initial,
            snapshots.filters_active,
            "bandHeights",
            band_name,
        )
        deltas[f"baseline_to_restored_{band_name}_band_delta"] = state_delta_nested(
            snapshots.builtin_initial,
            snapshots.filters_cleared,
            "bandHeights",
            band_name,
        )
    return deltas


def grid_width_deltas(snapshots: GridProbeSnapshots) -> dict[str, float]:
    return {
        "metric_to_restored_body_width_delta": state_delta(
            snapshots.metric_mode,
            snapshots.builtin_restored,
            "gridBodyWidth",
        ),
        "metric_to_restored_first_cell_left_delta": state_delta(
            snapshots.metric_mode,
            snapshots.builtin_restored,
            "firstCellLeft",
        ),
        "metric_to_restored_first_cell_width_delta": state_delta(
            snapshots.metric_mode,
            snapshots.builtin_restored,
            "firstCellWidth",
        ),
        "metric_to_restored_rail_width_delta": state_delta(
            snapshots.metric_mode,
            snapshots.builtin_restored,
            "metricRailWidth",
        ),
    }


def snapshot_mount_violations(snapshots: dict[str, dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    for name, snapshot in snapshots.items():
        if bool(snapshot.get("scrollRootUsesHiddenScrollbar")):
            violations.append(f"{name}: expected scroll root to avoid scrollbar-hidden mode")
        if snapshot.get("metricRailWidth") is None:
            violations.append(f"{name}: missing metric rail slot width measurement")
        for band_name in ("status", "similarity", "filters"):
            band_value = snapshot.get("bandHeights", {}).get(band_name)
            if band_value is None:
                violations.append(f"{name}: missing mounted top-stack band '{band_name}'")
    return violations


def grid_state_violations(snapshots: GridProbeSnapshots) -> list[str]:
    violations: list[str] = []
    if snapshots.metric_mode.get("metricRailActive") is not True:
        violations.append("metric_mode: metric rail did not activate after requesting metric sort")
    if snapshots.metric_mode.get("sortLabel") != snapshots.metric_sort_label:
        violations.append(f"metric_mode: expected active metric sort {snapshots.metric_sort_label}")
    if snapshots.builtin_restored.get("sortLabel") != "Date added":
        violations.append("builtin_restored: expected active sort to return to Date added")
    if (
        snapshots.metric_desc_visible_paths
        and snapshots.metric_asc_visible_paths
        and snapshots.metric_desc_visible_paths == snapshots.metric_asc_visible_paths
    ):
        violations.append("metric sort direction toggle did not reorder visible items")
    if snapshots.baseline_counts is not None and snapshots.filtered_counts is not None:
        if snapshots.filtered_counts["current"] >= snapshots.baseline_counts["current"]:
            violations.append(
                "metric range filter did not reduce the visible item count "
                f"({snapshots.filtered_counts['label']} vs {snapshots.baseline_counts['label']})"
            )
        if snapshots.filtered_counts["current"] >= snapshots.filtered_counts["total"]:
            violations.append(
                "metric range filter did not produce a filtered count label "
                f"({snapshots.filtered_counts['label']})"
            )
    return violations


def _phase_frames(frames: list[dict[str, Any]], phase: str) -> list[dict[str, Any]]:
    return [frame for frame in frames if frame.get("phase") == phase]


def _false_zero_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        frame
        for frame in frames
        if frame.get("countLabel") in {"0 items", "0 / 0 items"}
        or "Filtered: 0" in frame.get("filteredLabels", [])
    ]


def _transition_identity_violations(
    name: str,
    frames: list[dict[str, Any]],
) -> list[str]:
    violations: list[str] = []
    grace_indexes = [index for index, frame in enumerate(frames) if frame.get("phase") == "grace"]
    if not grace_indexes:
        return violations
    last_transition_index = max(
        index
        for index, frame in enumerate(frames)
        if frame.get("phase") in {"grace", "loading"}
    )
    prior = next(
        (frame for frame in reversed(frames[: grace_indexes[0]]) if frame.get("phase") == "steady"),
        None,
    )
    terminal = next(
        (
            frame
            for frame in frames[last_transition_index + 1 :]
            if frame.get("phase") == "steady"
        ),
        None,
    )
    if prior is None:
        return [f"{name}: missing pre-transition steady identity frame"]
    grace = [frames[index] for index in grace_indexes]
    if any(frame.get("paths") != prior.get("paths") for frame in grace):
        violations.append(f"{name}: grace changed retained visible membership")
    if any(frame.get("presentedTarget") != prior.get("presentedTarget") for frame in grace):
        violations.append(f"{name}: grace changed the presented target identity")
    if any(frame.get("epoch") != prior.get("epoch") for frame in grace):
        violations.append(f"{name}: grace advanced the presentation epoch")
    if any(frame.get("requestedTarget") == frame.get("presentedTarget") for frame in grace):
        violations.append(f"{name}: grace did not distinguish requested and presented targets")
    if any(frame.get("railActive") and not frame.get("railInteractionDisabled") for frame in grace):
        violations.append(f"{name}: active metric rail remained interactive during grace")
    if terminal is None or terminal.get("presentedTarget") != terminal.get("requestedTarget"):
        violations.append(f"{name}: terminal steady identity did not match the requested target")
    elif (
        terminal.get("presentedTarget") != prior.get("presentedTarget")
        and int(terminal.get("epoch") or 0) <= int(prior.get("epoch") or 0)
    ):
        violations.append(f"{name}: terminal target did not advance the presentation epoch")
    return violations


def _reset_transition_violations(
    name: str,
    frames: list[dict[str, Any]],
) -> list[str]:
    violations: list[str] = []
    if _phase_frames(frames, "grace"):
        violations.append(f"{name}: retained incompatible prior membership")
    loading = _phase_frames(frames, "loading")
    if not loading:
        violations.append(f"{name}: never painted target-owned loading")
    elif any(
        frame.get("cellCount")
        or frame.get("countLabel")
        or frame.get("presentedTarget")
        for frame in loading
    ):
        violations.append(f"{name}: loading mixed prior membership, counts, or identity")
    last_loading_index = max(
        (index for index, frame in enumerate(frames) if frame.get("phase") == "loading"),
        default=-1,
    )
    terminal = next(
        (
            frame
            for frame in frames[last_loading_index + 1 :]
            if frame.get("phase") == "steady"
        ),
        None,
    )
    if terminal is None or terminal.get("presentedTarget") != terminal.get("requestedTarget"):
        violations.append(f"{name}: terminal steady identity did not match the requested target")
    return violations


def browse_continuity_violations(evidence: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    baseline = evidence["baseline_counts"]
    filtered = evidence["filtered_counts"]
    selected_path = evidence["selected_path"]
    transitions = {
        name: evidence[f"{name}_frames"]
        for name in ("fast_filter", "slow_filter", "fast_sort", "slow_sort")
    }

    for name, frames in transitions.items():
        grace = _phase_frames(frames, "grace")
        steady = _phase_frames(frames, "steady")
        if not grace or not steady:
            violations.append(f"{name}: missing grace or terminal steady frames")
        if any(not frame.get("interactionDisabled") for frame in grace):
            violations.append(f"{name}: retained membership remained interactive")
        expected_label = filtered["label"] if name == "slow_filter" else baseline["label"]
        if any(frame.get("countLabel") != expected_label for frame in grace):
            violations.append(f"{name}: grace mixed target toolbar counts with prior membership")
        violations.extend(_transition_identity_violations(name, frames))

    for name in ("fast_filter", "fast_sort"):
        if _phase_frames(transitions[name], "loading"):
            violations.append(f"{name}: sub-grace response painted loading")
    for name in ("slow_filter", "slow_sort"):
        loading = _phase_frames(transitions[name], "loading")
        if not loading:
            violations.append(f"{name}: over-grace response never painted loading")
        elif any(frame.get("cellCount") or frame.get("countLabel") for frame in loading):
            violations.append(f"{name}: loading mixed retained cells or counts into the target")

    slow_sort_grace = _phase_frames(transitions["slow_sort"], "grace")
    if not any(frame.get("ratingCounts", {}).get("5") == 1 for frame in slow_sort_grace):
        violations.append("slow_sort: optimistic rating did not update the retained aggregate")
    if not any(selected_path in frame.get("paths", []) for frame in slow_sort_grace):
        violations.append("slow_sort: rated retained membership disappeared during grace")
    if evidence["rating_counts_before_filter"].get("5") != 1:
        violations.append("rating aggregate did not preserve the optimistic five-star update")
    if evidence["rating_counts_after_filter"].get("5") != 0:
        violations.append("settled unrated filter retained an excluded five-star aggregate")
    fast_filter_steady = _phase_frames(transitions["fast_filter"], "steady")
    if fast_filter_steady and selected_path in fast_filter_steady[-1].get("paths", []):
        violations.append("settled unrated filter retained the rated item")

    rapid_frames = evidence["rapid_frames"]
    final_rapid_indexes = [
        index
        for index, frame in enumerate(rapid_frames)
        if frame.get("phase") == "steady"
        and frame.get("paths")
        and all("sample_010" in path for path in frame["paths"])
    ]
    if not final_rapid_indexes:
        violations.append("rapid A-to-B-to-C transition never settled on C")
    else:
        for frame in rapid_frames[final_rapid_indexes[0]:]:
            if frame.get("phase") != "steady" or not frame.get("paths"):
                continue
            if any("sample_010" not in path for path in frame["paths"]):
                violations.append("rapid A-to-B-to-C transition presented stale A or B after C")
                break

    error_final = evidence["error_frames"][-1]
    violations.extend(_transition_identity_violations("terminal error", evidence["error_frames"]))
    if error_final.get("gridState") != "failed" or error_final.get("cellCount") != 0:
        violations.append("terminal error did not retire membership into the failed target")
    if error_final.get("countLabel") is not None:
        violations.append("terminal error manufactured a toolbar count")
    if error_final.get("presentedTarget") != error_final.get("requestedTarget"):
        violations.append("terminal error identity did not match the requested target")

    empty_final = evidence["empty_frames"][-1]
    violations.extend(_transition_identity_violations("terminal empty", evidence["empty_frames"]))
    if empty_final.get("gridState") != "empty" or empty_final.get("cellCount") != 0:
        violations.append("terminal empty query did not retire membership atomically")
    if not str(empty_final.get("countLabel")).startswith("0"):
        violations.append("terminal empty query did not expose a truthful settled zero")
    if empty_final.get("presentedTarget") != empty_final.get("requestedTarget"):
        violations.append("terminal empty identity did not match the requested target")

    scope_frames = evidence["scope_reset_frames"]
    violations.extend(_reset_transition_violations("scope reset", scope_frames))
    scope_final = scope_frames[-1]
    if scope_final.get("gridState") != "ready" or not str(scope_final.get("countLabel")).startswith("2"):
        violations.append("scope reset did not settle on the target scope membership and total")

    source_frames = evidence["source_reset_frames"]
    violations.extend(_reset_transition_violations("source reset", source_frames))
    source_final = source_frames[-1]
    if source_final.get("gridState") != "ready" or source_final.get("countLabel") != baseline["label"]:
        violations.append("source reset did not settle on the new source generation")

    violations.extend(_transition_identity_violations("rapid", rapid_frames))

    for name, frames in {
        **transitions,
        "rapid": rapid_frames,
        "error": evidence["error_frames"],
        "source_reset": source_frames,
    }.items():
        if _false_zero_frames(frames):
            violations.append(f"{name}: pending/error frames manufactured zero state")
    return violations


def browse_continuity_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    transition_names = (
        "fast_filter",
        "slow_filter",
        "fast_sort",
        "slow_sort",
        "rapid",
        "empty",
        "error",
        "scope_reset",
        "source_reset",
    )
    summaries: dict[str, Any] = {}
    for name in transition_names:
        frames = evidence[f"{name}_frames"]
        summaries[name] = {
            "frame_count": len(frames),
            "phases": {
                phase: len(_phase_frames(frames, phase))
                for phase in ("steady", "grace", "loading")
            },
            "final": frames[-1] if frames else None,
        }
    return {
        "baseline_counts": evidence["baseline_counts"],
        "filtered_counts": evidence["filtered_counts"],
        "selected_path": evidence["selected_path"],
        "rating_counts_before_filter": evidence["rating_counts_before_filter"],
        "rating_counts_after_filter": evidence["rating_counts_after_filter"],
        "transitions": summaries,
    }


def grid_result(snapshots: GridProbeSnapshots, config: GridProbeConfig) -> ProbeResult:
    top_deltas = grid_top_stack_deltas(snapshots)
    width_deltas = grid_width_deltas(snapshots)
    max_top_stack_delta = max(top_deltas.values(), default=0.0)
    max_grid_width_delta = max(width_deltas.values(), default=0.0)
    named_snapshots = {
        "warmup_filters_active": snapshots.warmup_filters_active,
        "builtin_initial": snapshots.builtin_initial,
        "filters_active": snapshots.filters_active,
        "filters_cleared": snapshots.filters_cleared,
        "metric_mode": snapshots.metric_mode,
        "builtin_restored": snapshots.builtin_restored,
    }
    violations = snapshot_mount_violations(named_snapshots)
    violations.extend(grid_state_violations(snapshots))
    violations.extend(browse_continuity_violations(snapshots.continuity))
    if max_grid_width_delta > config.max_delta_px:
        violations.append(
            f"grid-width delta {max_grid_width_delta:.3f}px exceeded threshold {config.max_delta_px:.3f}px"
        )
    if violations:
        raise SmokeFailure("; ".join(violations))
    return ProbeResult(
        scenario="grid",
        max_delta_px=config.max_delta_px,
        max_top_stack_delta_px=max_top_stack_delta,
        max_grid_width_delta_px=max_grid_width_delta,
        checks={
            "top_stack_deltas_px": top_deltas,
            "grid_width_deltas_px": width_deltas,
            "builtin_initial_snapshot": snapshots.builtin_initial,
            "filters_active_snapshot": snapshots.filters_active,
            "filters_cleared_snapshot": snapshots.filters_cleared,
            "metric_mode_snapshot": snapshots.metric_mode,
            "builtin_restored_snapshot": snapshots.builtin_restored,
            "metric_sort_label": snapshots.metric_sort_label,
            "metric_sort_labels": snapshots.metric_sort_labels,
            "metric_panel_keys": snapshots.metric_panel_keys,
            "metric_desc_visible_paths": snapshots.metric_desc_visible_paths,
            "metric_asc_visible_paths": snapshots.metric_asc_visible_paths,
            "baseline_counts": snapshots.baseline_counts,
            "filtered_counts": snapshots.filtered_counts,
            "browse_continuity": browse_continuity_summary(snapshots.continuity),
            "deferred_top_stack_delta_px": max_top_stack_delta,
            "violations": violations,
        },
    )


def run_grid_probe(config: GridProbeConfig) -> ProbeResult:
    playwright_error, playwright_timeout_error, sync_playwright = import_playwright()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 840})
            page = context.new_page()
            page.set_default_timeout(config.browser_timeout_ms)
            snapshots = exercise_grid_probe(page, config, playwright_error)
            context.close()
            browser.close()
    except playwright_timeout_error as exc:
        raise SmokeFailure(f"grid playwright timeout: {exc}") from exc
    except playwright_error as exc:
        raise SmokeFailure(f"grid playwright probe failed: {exc}") from exc
    return grid_result(snapshots, config)
