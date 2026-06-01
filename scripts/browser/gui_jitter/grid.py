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


def ensure_sort_trigger(page: Any, browser_timeout_ms: float) -> Any:
    trigger = page.locator('button[aria-label="Sort and layout"]').first
    if trigger.count() == 0:
        raise SmokeFailure("Sort dropdown trigger is missing.")
    if not trigger.is_disabled():
        return trigger
    switch_button = page.locator('button:has-text("Switch to Most recent")').first
    if switch_button.count() > 0:
        switch_button.click()
        page.wait_for_function(
            """() => {
              const button = document.querySelector('button[aria-label="Sort and layout"]');
              return button instanceof HTMLButtonElement ? !button.disabled : false;
            }""",
            timeout=browser_timeout_ms,
        )
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


def wait_for_sort_state(page: Any, kind: str, key: str, direction: str, browser_timeout_ms: float) -> None:
    page.wait_for_function(
        """(expected) => {
          try {
            const rawSortSpec = window.localStorage.getItem('sortSpec');
            if (!rawSortSpec) return false;
            const sortSpec = JSON.parse(rawSortSpec);
            return sortSpec?.kind === expected.kind
              && sortSpec?.key === expected.key
              && sortSpec?.dir === expected.dir;
          } catch {
            return false;
          }
        }""",
        arg={"kind": kind, "key": key, "dir": direction},
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
    wait_for_sort_state(page, "metric", metric_sort_label, "desc", config.browser_timeout_ms)
    metric_mode = snapshot_grid(page)
    metric_desc_visible_paths = visible_grid_paths(page)

    page.locator('button[aria-label="Toggle sort direction"]').first.click()
    wait_for_sort_state(page, "metric", metric_sort_label, "asc", config.browser_timeout_ms)
    page.wait_for_timeout(150)
    metric_asc_visible_paths = visible_grid_paths(page)

    select_sort_option(page, "Date added", config.browser_timeout_ms)
    wait_for_sort_state(page, "builtin", "added", "asc", config.browser_timeout_ms)
    wait_for_metric_rail(page, active=False, browser_timeout_ms=config.browser_timeout_ms)
    builtin_restored = snapshot_grid(page)

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
    if snapshots.metric_mode.get("persistedSortKind") != "metric":
        violations.append("metric_mode: expected persisted sort kind to be metric")
    if snapshots.metric_mode.get("persistedSortKey") != snapshots.metric_sort_label:
        violations.append(f"metric_mode: expected persisted metric sort key {snapshots.metric_sort_label}")
    if snapshots.builtin_restored.get("persistedSortKind") != "builtin":
        violations.append("builtin_restored: expected persisted sort kind to return to builtin")
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
    if max_top_stack_delta > config.max_delta_px:
        violations.append(
            f"top-stack delta {max_top_stack_delta:.3f}px exceeded threshold {config.max_delta_px:.3f}px"
        )
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
