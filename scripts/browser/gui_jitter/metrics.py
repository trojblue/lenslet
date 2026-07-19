"""Focused painted-frame probe for metric-card geometry stability."""

from __future__ import annotations

from typing import Any

from scripts.browser.gui_jitter.fixtures import METRICS_FIXTURE_ROW_COUNT
from scripts.browser.gui_jitter.grid_dom import open_metrics_panel
from scripts.browser.gui_jitter.metrics_controls import (
    capture_dropdown_first_paint as _capture_dropdown_first_paint,
    collapse_left_panel_with_focus_check as _collapse_left_panel_with_focus_check,
    exercise_operator_dropdowns as _exercise_operator_dropdowns,
)
from scripts.browser.gui_jitter.metrics_controller import (
    configure_facets as _configure_facets,
    install_facet_controller as _install_controlled_facets,
)
from scripts.browser.gui_jitter.metrics_schema import exercise_metric_schema_transitions
from scripts.browser.gui_jitter.metrics_trace import (
    requested_field_ownership_violations as _requested_field_ownership_violations,
    single_field_reset_summary as _single_field_reset_summary,
    summarize_trace as _summarize_trace,
    target_field_trace_summary as _target_field_trace_summary,
    virtual_card_continuity_violations as _virtual_card_continuity_violations,
    virtual_field_reset_summary as _virtual_field_reset_summary,
)
from scripts.browser.gui_jitter.painted_frames import (
    mark_painted_frame_action,
    start_painted_frame_trace,
    stop_painted_frame_trace,
)
from scripts.browser.gui_jitter.shared import ProbeResult, wait_for_grid
from scripts.smoke_harness import SmokeFailure, import_playwright

CATEGORICAL_SELECTORS = {
    "categorical_card": '[data-categorical-card="dataset_from"]',
    "categorical_clear": '[data-categorical-card="dataset_from"] [data-card-action="clear"]',
    "next_control": "[data-attributes-card]",
}
HISTOGRAM_SELECTORS = {
    "histogram_card": '[data-metric-histogram-card="quality_score"]',
    "histogram_clear": '[data-metric-histogram-card="quality_score"] [data-card-action="clear"]',
    "histogram_footer": '[data-metric-histogram-card="quality_score"] [data-histogram-footer]',
    "next_control": "[data-categorical-selector]",
}
FACET_SELECTORS = {
    "categorical_card": "[data-categorical-card]",
    "categorical_selector": "[data-categorical-selector]",
    "categorical_status": "[data-categorical-card] [role='status']",
    "categorical_first_value": "[data-categorical-card] [data-facet-body] button:nth-child(1)",
    "categorical_second_value": "[data-categorical-card] [data-facet-body] button:nth-child(2)",
    "categorical_clear": "[data-categorical-card] [data-card-action='clear']",
    "next_control": "[data-attributes-card]",
}
FACET_REQUIRED_SELECTORS = (
    "categorical_card",
    "categorical_selector",
    "next_control",
)
METRIC_FACET_SELECTORS = {
    "metric_card": "[data-metric-card-host]",
    "metric_selector": "[data-metric-selector]",
    "metric_status": "[data-metric-card-host] [role='status']",
    "metric_clear": "[data-metric-card-host] [data-card-action='clear']",
    "metric_min": "[data-metric-card-host] input[type='number']:nth-of-type(1)",
    "metric_max": "[data-metric-card-host] input[type='number']:nth-of-type(2)",
    "next_control": "[data-categorical-selector]",
}
METRIC_FACET_REQUIRED_SELECTORS = (
    "metric_card",
    "metric_selector",
    "next_control",
)
SELECTION_SELECTORS = {
    "metric_card": "[data-metric-histogram-card]",
    "categorical_selector": "[data-categorical-selector]",
}


class MetricsProbeFailure(SmokeFailure):
    """Metrics failure carrying bounded frame evidence for JSON output."""

    def __init__(self, message: str, evidence: dict[str, Any]) -> None:
        super().__init__(message)
        self.evidence = evidence


def _wait_for_metrics_ready(page: Any, timeout_ms: float) -> None:
    page.wait_for_function(
        """() => Boolean(
          document.querySelector('[data-metric-selector] button[aria-haspopup="listbox"]')
          && document.querySelector('[data-categorical-selector] button[aria-haspopup="listbox"]')
        )""",
        timeout=timeout_ms,
    )
    metric_trigger = page.locator(
        '[data-metric-selector] button[aria-haspopup="listbox"]'
    ).first
    if metric_trigger.inner_text().strip() != "quality_score":
        _select_dropdown_option(page, '[data-metric-selector] button', "Metric", "quality_score")
    categorical_trigger = page.locator(
        '[data-categorical-selector] button[aria-haspopup="listbox"]'
    ).first
    if categorical_trigger.inner_text().strip() != "dataset_from":
        _select_dropdown_option(page, '[data-categorical-selector] button', "Categorical", "dataset_from")
    page.wait_for_function(
        """(rowCount) => {
          const metric = document.querySelector('[data-metric-histogram-card="quality_score"]');
          const categorical = document.querySelector('[data-categorical-card="dataset_from"]');
          return metric instanceof HTMLElement
            && categorical instanceof HTMLElement
            && (metric.textContent || '').includes(`Population: ${rowCount}`)
            && (categorical.textContent || '').includes(`Population: ${rowCount}`)
            && (categorical.textContent || '').includes('2 values');
        }""",
        arg=METRICS_FIXTURE_ROW_COUNT,
        timeout=timeout_ms,
    )


def _footer_structure(page: Any) -> dict[str, Any]:
    result = page.evaluate(
        """() => {
          const footer = document.querySelector('[data-histogram-footer]');
          if (!(footer instanceof HTMLElement)) return null;
          const style = getComputedStyle(footer);
          return {
            clientHeight: footer.clientHeight,
            scrollHeight: footer.scrollHeight,
            whiteSpace: style.whiteSpace,
            text: (footer.textContent || '').replace(/\\s+/g, ' ').trim(),
          };
        }"""
    )
    if not isinstance(result, dict):
        raise SmokeFailure("Histogram footer is missing.")
    return result


def _select_dropdown_option(
    page: Any,
    trigger_selector: str,
    aria_label: str,
    value: str,
    *,
    action_id: str | None = None,
) -> None:
    trigger = page.locator(trigger_selector).first
    trigger.scroll_into_view_if_needed()
    trigger.click()
    panel = page.locator(f'[role="listbox"][aria-label="{aria_label}"]').first
    panel.wait_for(state="visible")
    option = panel.locator("button.dropdown-item", has_text=value).first
    if option.count() != 1:
        raise SmokeFailure(f"Dropdown {aria_label!r} is missing option {value!r}.")
    if action_id:
        mark_painted_frame_action(
            page,
            action_id=action_id,
            expected_path=value,
        )
    option.click()


def _wait_for_categorical_state(
    page: Any,
    field: str,
    state: str,
    timeout_ms: float,
) -> None:
    page.wait_for_function(
        """expected => {
          const selector = document.querySelector('[data-categorical-selector] button');
          const card = document.querySelector('[data-categorical-card]');
          return selector instanceof HTMLButtonElement
            && card instanceof HTMLElement
            && (selector.textContent || '').trim() === expected.field
            && card.getAttribute('data-categorical-card') === expected.field
            && card.getAttribute('data-facet-state') === expected.state;
        }""",
        arg={"field": field, "state": state},
        timeout=timeout_ms,
    )


def _wait_for_categorical_request(page: Any, field: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """field => {
          const selector = document.querySelector('[data-categorical-selector]');
          return selector instanceof HTMLElement
            && selector.getAttribute('data-facet-requested-field') === field;
        }""",
        arg=field,
        timeout=timeout_ms,
    )


def _wait_for_categorical_network_request(page: Any, field: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """field => window.__lensletFacetController?.requests?.some(
          request => request.categoricalFields.includes(field),
        )""",
        arg=field,
        timeout=timeout_ms,
    )


def _wait_for_categorical_network_completion(page: Any, field: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """field => window.__lensletFacetController?.completions?.some(
          request => request.categoricalFields.includes(field),
        )""",
        arg=field,
        timeout=timeout_ms,
    )


def _wait_for_metric_state(page: Any, field: str, state: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """expected => {
          const selector = document.querySelector('[data-metric-selector] button');
          const card = document.querySelector('[data-metric-card-host]');
          return selector instanceof HTMLButtonElement
            && card instanceof HTMLElement
            && (selector.textContent || '').trim() === expected.field
            && card.getAttribute('data-metric-card-host') === expected.field
            && card.getAttribute('data-facet-state') === expected.state;
        }""",
        arg={"field": field, "state": state},
        timeout=timeout_ms,
    )


def _wait_for_metric_request(page: Any, field: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """field => document.querySelector('[data-metric-selector]')
          ?.getAttribute('data-facet-requested-field') === field""",
        arg=field,
        timeout=timeout_ms,
    )


def _target_facet_trace_summary(
    trace: dict[str, Any],
    *,
    previous_field: str,
    field: str,
    terminal_state: str,
    forbidden_texts: tuple[str, ...],
    expected_text: str,
    max_delta_px: float,
) -> dict[str, Any]:
    return _target_field_trace_summary(
        trace,
        action_id=f"select-{field}",
        anchor_names=("categorical_card", "next_control"),
        card_attribute="data-categorical-card",
        card_surface="categorical_card",
        previous_field=previous_field,
        field=field,
        field_label=field,
        required_names=FACET_REQUIRED_SELECTORS,
        selector_surface="categorical_selector",
        terminal_state=terminal_state,
        forbidden_texts=forbidden_texts,
        expected_text=expected_text,
        max_delta_px=max_delta_px,
    )


def _target_metric_trace_summary(
    trace: dict[str, Any],
    *,
    previous_field: str,
    field: str,
    max_delta_px: float,
) -> dict[str, Any]:
    return _target_field_trace_summary(
        trace,
        action_id=f"select-metric-{field}",
        anchor_names=("metric_card", "next_control"),
        card_attribute="data-metric-card-host",
        card_surface="metric_card",
        previous_field=previous_field,
        field=field,
        field_label=f"metric {field}",
        required_names=METRIC_FACET_REQUIRED_SELECTORS,
        selector_surface="metric_selector",
        terminal_state="ready",
        forbidden_texts=("0.000", "1.000"),
        expected_text="20.00",
        max_delta_px=max_delta_px,
    )


def _exercise_categorical(page: Any, max_delta_px: float, timeout_ms: float) -> dict[str, Any]:
    card = page.locator(CATEGORICAL_SELECTORS["categorical_card"])
    card.scroll_into_view_if_needed()
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="categorical_selection",
        selectors=CATEGORICAL_SELECTORS,
    )
    card.locator('button[title="gt"]').click()
    page.wait_for_function(
        """() => document.querySelector('[data-categorical-card="dataset_from"] button[title="gt"]')?.getAttribute('aria-pressed') === 'true'""",
        timeout=timeout_ms,
    )
    page.wait_for_timeout(120)
    trace = stop_painted_frame_trace(page)
    summary = _summarize_trace(
        trace,
        anchor_names=("categorical_card", "next_control"),
        required_names=tuple(CATEGORICAL_SELECTORS),
        max_delta_px=max_delta_px,
    )
    card_texts = summary["visible_text_states"].get("categorical_card", [])
    if any("Active:" in text for text in card_texts):
        summary["violations"].append("categorical card painted redundant Active copy")
    clear = card.locator('[data-card-action="clear"]')
    if clear.count() != 1 or clear.is_hidden():
        summary["violations"].append("categorical Clear did not occupy its active fixed slot")
    clear.click()
    page.wait_for_function(
        """() => document.querySelector('[data-categorical-card="dataset_from"] button[title="gt"]')?.getAttribute('aria-pressed') === 'false'""",
        timeout=timeout_ms,
    )
    return summary


def _exercise_metric_field_transition(
    page: Any,
    max_delta_px: float,
    timeout_ms: float,
) -> dict[str, Any]:
    _install_controlled_facets(page)
    _configure_facets(
        page,
        delays={"contrast_score": 350},
        metricRanges={"contrast_score": [10, 20]},
    )
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="metric_contrast_score",
        selectors=METRIC_FACET_SELECTORS,
    )
    _select_dropdown_option(
        page,
        "[data-metric-selector] button[aria-haspopup='listbox']",
        "Metric",
        "contrast_score",
        action_id="select-metric-contrast_score",
    )
    _wait_for_metric_request(page, "contrast_score", timeout_ms)
    _wait_for_metric_state(page, "contrast_score", "ready", timeout_ms)
    page.wait_for_timeout(80)
    trace = stop_painted_frame_trace(page)
    _configure_facets(page, delays={}, metricRanges={})
    summary = _target_metric_trace_summary(
        trace,
        previous_field="quality_score",
        field="contrast_score",
        max_delta_px=max_delta_px,
    )
    _select_dropdown_option(
        page,
        "[data-metric-selector] button[aria-haspopup='listbox']",
        "Metric",
        "quality_score",
    )
    _wait_for_metric_state(page, "quality_score", "ready", timeout_ms)
    return summary


def _exercise_histogram(page: Any, max_delta_px: float, timeout_ms: float) -> dict[str, Any]:
    card = page.locator(HISTOGRAM_SELECTORS["histogram_card"])
    card.scroll_into_view_if_needed()
    chart = card.locator("svg").first
    box = chart.bounding_box()
    if not isinstance(box, dict):
        raise SmokeFailure("Metric histogram chart has no bounding box.")
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="histogram_drag",
        selectors=HISTOGRAM_SELECTORS,
    )
    y = float(box["y"]) + (float(box["height"]) / 2)
    start_x = float(box["x"]) + (float(box["width"]) * 0.25)
    end_x = float(box["x"]) + (float(box["width"]) * 0.75)
    page.mouse.move(start_x, y)
    page.mouse.down()
    page.mouse.move(end_x, y, steps=8)
    page.mouse.up()
    page.wait_for_function(
        """() => document.querySelector('[data-metric-histogram-card="quality_score"] [data-card-action="clear"]')?.getAttribute('aria-hidden') === 'false'""",
        timeout=timeout_ms,
    )
    page.wait_for_timeout(80)
    page.mouse.move(1_000, 80)
    page.wait_for_timeout(80)
    clear = card.locator('[data-card-action="clear"]')
    clear.click()
    page.wait_for_function(
        """() => document.querySelector('[data-metric-histogram-card="quality_score"] [data-card-action="clear"]')?.getAttribute('aria-hidden') === 'true'""",
        timeout=timeout_ms,
    )
    page.wait_for_timeout(80)
    trace = stop_painted_frame_trace(page)
    summary = _summarize_trace(
        trace,
        anchor_names=("histogram_card", "next_control"),
        required_names=tuple(HISTOGRAM_SELECTORS),
        max_delta_px=max_delta_px,
    )
    footer = _footer_structure(page)
    summary["footer_structure"] = footer
    if footer.get("whiteSpace") != "nowrap":
        summary["violations"].append("histogram footer is not no-wrap")
    if float(footer.get("scrollHeight") or 0) > float(footer.get("clientHeight") or 0) + 1:
        summary["violations"].append("histogram footer overflowed onto another line")
    footer_states = summary["visible_text_states"].get("histogram_footer", [])
    summary["footer_states"] = footer_states
    if any(text.count("Cursor:") > 1 for text in footer_states):
        summary["violations"].append("histogram footer painted a second cursor row")
    return summary


def _exercise_facet_transitions(page: Any, max_delta_px: float, timeout_ms: float) -> dict[str, Any]:
    _install_controlled_facets(page)
    phases: dict[str, Any] = {}
    cases = (
        ("review_group", {"delays": {"review_group": 350}}, "ready", "Population: 1585", ("synthetic",)),
        ("empty_group", {"delays": {"empty_group": 250}, "emptyFields": ["empty_group"]}, "empty", "No values found", ("review-",)),
        ("error_group", {"delays": {"error_group": 80}, "errorFields": ["error_group"]}, "error", "Could not load values", ("placeholder",)),
    )
    previous_field = "dataset_from"
    for field, config, terminal_state, expected_text, forbidden_texts in cases:
        _configure_facets(
            page,
            delays=config.get("delays", {}),
            emptyFields=config.get("emptyFields", []),
            errorFields=config.get("errorFields", []),
        )
        start_painted_frame_trace(
            page,
            page_id="metrics",
            phase=f"facet_{field}",
            selectors=FACET_SELECTORS,
        )
        _select_dropdown_option(
            page,
            "[data-categorical-selector] button[aria-haspopup='listbox']",
            "Categorical",
            field,
            action_id=f"select-{field}",
        )
        _wait_for_categorical_request(page, field, timeout_ms)
        _wait_for_categorical_state(page, field, terminal_state, timeout_ms)
        page.wait_for_timeout(80)
        trace = stop_painted_frame_trace(page)
        phases[field] = _target_facet_trace_summary(
            trace,
            previous_field=previous_field,
            field=field,
            terminal_state=terminal_state,
            forbidden_texts=forbidden_texts,
            expected_text=expected_text,
            max_delta_px=max_delta_px,
        )
        previous_field = field
    _configure_facets(
        page,
        delays={"late_group": 450, "derived_group": 100},
        emptyFields=[],
        errorFields=[],
    )
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="facet_rapid_abc",
        selectors=FACET_SELECTORS,
    )
    _select_dropdown_option(
        page,
        "[data-categorical-selector] button[aria-haspopup='listbox']",
        "Categorical",
        "late_group",
    )
    _wait_for_categorical_request(page, "late_group", timeout_ms)
    _wait_for_categorical_network_request(page, "late_group", timeout_ms)
    _select_dropdown_option(
        page,
        "[data-categorical-selector] button[aria-haspopup='listbox']",
        "Categorical",
        "derived_group",
        action_id="select-derived_group",
    )
    _wait_for_categorical_request(page, "derived_group", timeout_ms)
    _wait_for_categorical_state(page, "derived_group", "ready", timeout_ms)
    _wait_for_categorical_network_completion(page, "late_group", timeout_ms)
    _wait_for_categorical_state(page, "derived_group", "ready", timeout_ms)
    network_supersession = page.evaluate(
        """() => {
          const controller = window.__lensletFacetController;
          const lastFor = (entries, field) => entries
            .filter(entry => entry.categoricalFields.includes(field)).at(-1) || null;
          const lateRequest = lastFor(controller.requests, 'late_group');
          const lateCompletion = lastFor(controller.completions, 'late_group');
          const targetCompletion = lastFor(controller.completions, 'derived_group');
          return {
            lateRequestAt: lateRequest?.at ?? null,
            lateCompletionAt: lateCompletion?.at ?? null,
            targetCompletionAt: targetCompletion?.at ?? null,
            lateCompletedAfterTarget: Boolean(
              lateCompletion && targetCompletion && lateCompletion.at > targetCompletion.at
            ),
          };
        }"""
    )
    rapid_summary = _target_facet_trace_summary(
        stop_painted_frame_trace(page),
        previous_field="error_group",
        field="derived_group",
        terminal_state="ready",
        forbidden_texts=("Could not load", "late-"),
        expected_text=f"Population: {METRICS_FIXTURE_ROW_COUNT}",
        max_delta_px=max_delta_px,
    )
    rapid_summary["network_supersession"] = network_supersession
    if not network_supersession.get("lateCompletedAfterTarget"):
        rapid_summary["violations"].append(
            f"pending B did not complete after terminal C: {network_supersession!r}"
        )
    phases["rapid_abc"] = rapid_summary
    _configure_facets(page, delays={}, emptyFields=[], errorFields=[])
    return phases


def _wait_for_selection_count(page: Any, count: int, timeout_ms: float) -> None:
    page.wait_for_function(
        """expected => (
          document.querySelectorAll('[role="gridcell"][aria-selected="true"]').length === expected
        )""",
        arg=count,
        timeout=timeout_ms,
    )


def _exercise_selection_and_virtualization(
    page: Any,
    max_delta_px: float,
    timeout_ms: float,
) -> dict[str, Any]:
    _select_dropdown_option(
        page,
        "[data-categorical-selector] button[aria-haspopup='listbox']",
        "Categorical",
        "review_group",
    )
    _wait_for_categorical_state(page, "review_group", "ready", timeout_ms)
    _select_dropdown_option(
        page,
        "[data-metric-selector] button[aria-haspopup='listbox']",
        "Metric",
        "quality_score",
    )
    metric_card = page.locator('[data-metric-histogram-card="quality_score"]').first
    metric_card.scroll_into_view_if_needed()
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="metric_selection",
        selectors=SELECTION_SELECTORS,
    )
    cells = page.locator('[role="gridcell"][id^="cell-"]')
    cells.nth(0).click()
    _wait_for_selection_count(page, 1, timeout_ms)
    cells.nth(1).click(modifiers=["Control"])
    _wait_for_selection_count(page, 2, timeout_ms)
    page.wait_for_function(
        """() => (document.querySelector('[data-metric-histogram-card]')?.textContent || '').includes('Selected: 2')""",
        timeout=timeout_ms,
    )
    page.wait_for_timeout(80)
    selection_trace = stop_painted_frame_trace(page)
    selection = _summarize_trace(
        selection_trace,
        anchor_names=tuple(SELECTION_SELECTORS),
        required_names=tuple(SELECTION_SELECTORS),
        max_delta_px=max_delta_px,
    )
    if page.get_by_text("Selected metrics", exact=True).count() != 0:
        selection["violations"].append("selection inserted the removed Selected metrics card")
    selection["selected_overlay_count"] = metric_card.locator('rect[fill="#f59e0b"]').count()
    if selection["selected_overlay_count"] == 0:
        selection["violations"].append("multi-selection did not stay in the histogram SVG overlay")

    _configure_facets(
        page,
        delays={"dataset_from": 450},
        emptyFields=["dataset_from"],
        categoryFields=[],
    )
    categorical_request_count = page.evaluate(
        """() => (window.__lensletFacetController?.requests || [])
          .filter(request => request.categoricalFields.includes('dataset_from')).length"""
    )
    categorical_completion_count = page.evaluate(
        """() => (window.__lensletFacetController?.completions || [])
          .filter(request => request.categoricalFields.includes('dataset_from')).length"""
    )
    categorical_virtual_selectors = {
        "metrics_panel": "[data-metrics-panel]",
        "categorical_virtual_list": '[data-virtual-field-list="categorical"]',
    }
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="categorical_virtual_hydration",
        selectors=categorical_virtual_selectors,
    )
    mark_painted_frame_action(page, action_id="show-all-categoricals", expected_path="metrics")
    page.locator("[data-categorical-show-all]").click()
    page.wait_for_function(
        """previous => (window.__lensletFacetController?.requests || [])
          .filter(request => request.categoricalFields.includes('dataset_from')).length > previous""",
        arg=categorical_request_count,
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """() => {
          const card = document.querySelector('[data-categorical-card="dataset_from"]');
          const owner = card?.closest('[data-facet-presented-field]');
          return card?.getAttribute('data-facet-state') === 'ready'
            && (card.textContent || '').includes('2 values')
            && owner?.getAttribute('aria-busy') === 'true'
            && owner?.getAttribute('aria-disabled') === 'true'
            && owner?.hasAttribute('inert');
        }""",
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """previous => (window.__lensletFacetController?.completions || [])
          .filter(request => request.categoricalFields.includes('dataset_from')).length > previous""",
        arg=categorical_completion_count,
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """() => {
          const card = document.querySelector('[data-categorical-card="dataset_from"]');
          return card?.getAttribute('data-facet-state') === 'empty'
            && (card.textContent || '').includes('No values found for this field');
        }""",
        timeout=timeout_ms,
    )
    page.locator("[data-categorical-show-all]").click()
    page.locator('[data-virtual-field-list="categorical"]').wait_for(state="hidden", timeout=timeout_ms)
    page.locator("[data-categorical-show-all]").click()
    page.locator('[data-virtual-field-list="categorical"]').wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_timeout(80)
    categorical_virtual_trace = stop_painted_frame_trace(page)
    categorical_visible_frames = [
        frame
        for frame in categorical_virtual_trace.get("frames", [])
        if isinstance(frame, dict)
        and isinstance(frame.get("surfaces"), dict)
        and isinstance(frame["surfaces"].get("categorical_virtual_list"), dict)
        and frame["surfaces"]["categorical_virtual_list"].get("visible") is True
    ]
    categorical_virtual = _summarize_trace(
        {"frames": categorical_visible_frames},
        anchor_names=("categorical_virtual_list",),
        required_names=tuple(categorical_virtual_selectors),
        max_delta_px=max_delta_px,
    )
    for frame in categorical_virtual_trace.get("frames", []):
        surfaces = frame.get("surfaces") if isinstance(frame, dict) else None
        if isinstance(surfaces, dict):
            categorical_virtual["violations"].extend(
                _requested_field_ownership_violations(surfaces)
            )
    categorical_virtual["violations"].extend(_virtual_card_continuity_violations(
        categorical_virtual_trace.get("frames", []),
        surface_names=("categorical_virtual_list",),
        initially_settled=frozenset({"dataset_from", "review_group"}),
    ))
    categorical_virtual["violations"] = list(dict.fromkeys(categorical_virtual["violations"]))

    _configure_facets(
        page,
        delays={"contrast_score": 450, "dataset_from": 450},
        emptyFields=[],
        errorFields=[],
        categoryFields=["contrast_score"],
    )
    virtual_selectors = {
        "metrics_panel": "[data-metrics-panel]",
        "metric_virtual_list": '[data-virtual-field-list="metric"]',
        "contrast_card": '[data-metric-card-host="contrast_score"]',
        "categorical_virtual_list": '[data-virtual-field-list="categorical"]',
        "dataset_card": '[data-categorical-card="dataset_from"]',
    }
    contrast_request_count = page.evaluate(
        """() => (window.__lensletFacetController?.requests || [])
          .filter(request => request.metricFields.includes('contrast_score')).length"""
    )
    contrast_completion_count = page.evaluate(
        """() => (window.__lensletFacetController?.completions || [])
          .filter(request => request.metricFields.includes('contrast_score')).length"""
    )
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="metric_virtual_hydration",
        selectors=virtual_selectors,
    )
    mark_painted_frame_action(
        page,
        action_id="show-all-metrics",
        expected_path="metrics",
    )
    page.locator("[data-metric-show-all]").click()
    contrast = page.locator('[data-metric-card-host="contrast_score"]').first
    contrast.wait_for(state="attached", timeout=timeout_ms)
    page.evaluate(
        """() => {
          window.__lensletMetricCardHost = document.querySelector('[data-metric-card-host="contrast_score"]');
        }"""
    )
    page.wait_for_function(
        """previous => (window.__lensletFacetController?.requests || [])
          .filter(request => request.metricFields.includes('contrast_score')).length > previous""",
        arg=contrast_request_count,
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """() => {
          const card = document.querySelector('[data-metric-card-host="contrast_score"]');
          return card?.getAttribute('data-facet-state') === 'ready'
            && !(card.textContent || '').includes('Loading values');
        }""",
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """previous => (window.__lensletFacetController?.completions || [])
          .filter(request => request.metricFields.includes('contrast_score')).length > previous""",
        arg=contrast_completion_count,
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """() => document.querySelector('[data-metric-card-host="contrast_score"]')?.getAttribute('data-facet-state') === 'ready'
          && document.querySelector('[data-metric-card-host="contrast_score"] [data-metric-category-card="contrast_score"]')""",
        timeout=timeout_ms,
    )
    stable_host_retained = page.evaluate(
        """() => window.__lensletMetricCardHost
          === document.querySelector('[data-metric-card-host="contrast_score"]')"""
    )
    geometry = page.evaluate(
        """async () => {
          const list = document.querySelector('[data-virtual-field-list="metric"]');
          if (!(list instanceof HTMLElement)) return null;
          const heights = () => Array.from(list.querySelectorAll('[data-virtual-field-card="metric"]'))
            .map(card => card.getBoundingClientRect().height);
          const before = heights();
          list.scrollTop = list.scrollHeight;
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          return { before, after: heights(), scrollTop: list.scrollTop, scrollHeight: list.scrollHeight };
        }"""
    )
    boundary_field = "zz_probe_metric_29"
    page.wait_for_function(
        """field => {
          const list = document.querySelector('[data-virtual-field-list="metric"]');
          const panel = document.querySelector('[data-metrics-panel]');
          if (!(list instanceof HTMLElement) || !(panel instanceof HTMLElement)) return false;
          const rendered = JSON.parse(list.dataset.renderedFieldKeys || '[]');
          const requested = JSON.parse(panel.dataset.requestedMetricFields || '[]');
          return list.scrollTop > 0 && rendered.includes(field) && requested.includes(field);
        }""",
        arg=boundary_field,
        timeout=timeout_ms,
    )
    bottom_before_toggle = page.evaluate(
        """() => {
          const list = document.querySelector('[data-virtual-field-list="metric"]');
          const panel = document.querySelector('[data-metrics-panel]');
          return {
            scrollTop: list?.scrollTop || 0,
            rendered: JSON.parse(list?.getAttribute('data-rendered-field-keys') || '[]'),
            requested: JSON.parse(panel?.getAttribute('data-requested-metric-fields') || '[]'),
          };
        }"""
    )
    mark_painted_frame_action(page, action_id="show-one-metrics", expected_path="metrics")
    page.locator("[data-metric-show-all]").click()
    page.locator('[data-virtual-field-list="metric"]').wait_for(state="hidden", timeout=timeout_ms)
    mark_painted_frame_action(page, action_id="show-all-metrics-reopen", expected_path="metrics")
    page.locator("[data-metric-show-all]").click()
    page.locator('[data-virtual-field-list="metric"]').wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_function(
        """field => {
          const list = document.querySelector('[data-virtual-field-list="metric"]');
          const panel = document.querySelector('[data-metrics-panel]');
          const rendered = JSON.parse(list?.getAttribute('data-rendered-field-keys') || '[]');
          const requested = JSON.parse(panel?.getAttribute('data-requested-metric-fields') || '[]');
          return (list?.scrollTop || 0) > 0 && rendered.includes(field) && requested.includes(field);
        }""",
        arg=boundary_field,
        timeout=timeout_ms,
    )
    bottom_after_toggle = page.evaluate(
        """() => {
          const list = document.querySelector('[data-virtual-field-list="metric"]');
          const panel = document.querySelector('[data-metrics-panel]');
          return {
            scrollTop: list?.scrollTop || 0,
            rendered: JSON.parse(list?.getAttribute('data-rendered-field-keys') || '[]'),
            requested: JSON.parse(panel?.getAttribute('data-requested-metric-fields') || '[]'),
          };
        }"""
    )
    virtual_reset_key = page.locator("[data-metrics-panel]").get_attribute(
        "data-presentation-reset-key"
    )
    if not virtual_reset_key:
        raise SmokeFailure("Metrics Show-all trace did not expose its reset identity.")

    settings_button = page.get_by_label("Settings").first
    settings_button.click()
    source_trigger = page.get_by_label("Image column").first
    source_trigger.wait_for(state="visible", timeout=timeout_ms)
    current_source = page.evaluate(
        """async () => {
          const response = await fetch('/table/source-columns');
          return (await response.json()).current;
        }"""
    )
    next_source = "source_alt" if current_source != "source_alt" else "source"
    mark_painted_frame_action(page, action_id="metric-source-reset", expected_path="metrics")
    source_trigger.click()
    source_panel = page.locator(
        '.dropdown-panel[role="listbox"][aria-label="Image column"]'
    ).first
    source_panel.wait_for(state="visible", timeout=timeout_ms)
    source_panel.get_by_role("option", name=next_source, exact=True).click()
    page.wait_for_function(
        """async source => {
          const response = await fetch('/table/source-columns');
          return (await response.json()).current === source;
        }""",
        arg=next_source,
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """previous => document.querySelector('[data-metrics-panel]')
          ?.getAttribute('data-presentation-reset-key') !== previous""",
        arg=virtual_reset_key,
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """() => document.querySelector('[data-metric-card-host="contrast_score"]')
          ?.getAttribute('data-facet-state') === 'pending'
          && document.querySelector('[data-categorical-card="dataset_from"]')
          ?.getAttribute('data-facet-state') === 'pending'""",
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """() => document.querySelector('[data-metric-card-host="contrast_score"]')
          ?.getAttribute('data-facet-state') === 'ready'
          && document.querySelector('[data-metric-category-card="contrast_score"]')
          && document.querySelector('[data-categorical-card="dataset_from"]')
          ?.getAttribute('data-facet-state') === 'ready'
          && (document.querySelector('[data-categorical-card="dataset_from"]')?.textContent || '')
            .includes('2 values')""",
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """() => {
          const list = document.querySelector('[data-virtual-field-list="metric"]');
          const panel = document.querySelector('[data-metrics-panel]');
          const rendered = JSON.parse(list?.getAttribute('data-rendered-field-keys') || '[]');
          const requested = JSON.parse(panel?.getAttribute('data-requested-metric-fields') || '[]');
          return (list?.scrollTop || 0) === 0
            && rendered.length > 0
            && rendered.includes('contrast_score')
            && rendered.every(field => requested.includes(field));
        }""",
        timeout=timeout_ms,
    )
    hard_reset = page.evaluate(
        """() => {
          const list = document.querySelector('[data-virtual-field-list="metric"]');
          const panel = document.querySelector('[data-metrics-panel]');
          return {
            scrollTop: list?.scrollTop || 0,
            rendered: JSON.parse(list?.getAttribute('data-rendered-field-keys') || '[]'),
            requested: JSON.parse(panel?.getAttribute('data-requested-metric-fields') || '[]'),
          };
        }"""
    )
    page.wait_for_timeout(80)
    virtual_trace = stop_painted_frame_trace(page)
    schema_transitions = exercise_metric_schema_transitions(page, timeout_ms)

    page.locator("[data-metric-show-all]").click()
    page.locator("[data-categorical-show-all]").click()
    _wait_for_metric_state(page, "quality_score", "ready", timeout_ms)
    _wait_for_categorical_state(page, "review_group", "ready", timeout_ms)
    previous_reset_key = page.locator("[data-metrics-panel]").get_attribute(
        "data-presentation-reset-key"
    )
    if not previous_reset_key:
        raise SmokeFailure("Metrics panel did not expose its presentation reset identity.")
    _configure_facets(
        page,
        delays={"quality_score": 450, "review_group": 450},
        emptyFields=["review_group"],
        categoryFields=[],
        metricRanges={"quality_score": [10, 20]},
    )
    reset_selectors = {
        "metrics_panel": "[data-metrics-panel]",
        "metric_selector": "[data-metric-selector]",
        "metric_card": "[data-metric-card-host]",
        "categorical_selector": "[data-categorical-selector]",
        "categorical_card": "[data-categorical-card]",
    }
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="metric_single_field_hard_reset",
        selectors=reset_selectors,
    )
    settings_button.click()
    source_trigger = page.get_by_label("Image column").first
    source_trigger.wait_for(state="visible", timeout=timeout_ms)
    current_source = page.evaluate(
        """async () => {
          const response = await fetch('/table/source-columns');
          return (await response.json()).current;
        }"""
    )
    next_source = "source_alt" if current_source != "source_alt" else "source"
    source_trigger.click()
    source_panel.wait_for(state="visible", timeout=timeout_ms)
    mark_painted_frame_action(page, action_id="metric-single-source-reset", expected_path="metrics")
    source_panel.get_by_role("option", name=next_source, exact=True).click()
    page.wait_for_function(
        """async source => {
          const response = await fetch('/table/source-columns');
          return (await response.json()).current === source;
        }""",
        arg=next_source,
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """previous => document.querySelector('[data-metrics-panel]')
          ?.getAttribute('data-presentation-reset-key') !== previous""",
        arg=previous_reset_key,
        timeout=timeout_ms,
    )
    _wait_for_metric_state(page, "quality_score", "pending", timeout_ms)
    _wait_for_categorical_state(page, "review_group", "pending", timeout_ms)
    _wait_for_metric_state(page, "quality_score", "ready", timeout_ms)
    _wait_for_categorical_state(page, "review_group", "empty", timeout_ms)
    page.wait_for_function(
        """() => {
          const text = document.querySelector('[data-metric-card-host="quality_score"]')?.textContent || '';
          return text.includes('10.00') && text.includes('20.00');
        }""",
        timeout=timeout_ms,
    )
    page.wait_for_timeout(80)
    single_reset_trace = stop_painted_frame_trace(page)
    single_reset = _single_field_reset_summary(
        single_reset_trace,
        previous_reset_key=previous_reset_key,
    )
    hydration_frames = [
        frame
        for frame in virtual_trace.get("frames", [])
        if isinstance(frame, dict)
        and isinstance(frame.get("marker"), dict)
        and frame["marker"].get("actionId") == "show-all-metrics"
        and isinstance(frame.get("surfaces"), dict)
        and isinstance(frame["surfaces"].get("metric_virtual_list"), dict)
        and isinstance(frame["surfaces"].get("contrast_card"), dict)
    ]
    virtual = _summarize_trace(
        {"frames": hydration_frames},
        anchor_names=("metric_virtual_list", "contrast_card"),
        required_names=tuple(virtual_selectors),
        max_delta_px=max_delta_px,
    )
    contrast_texts = virtual.get("visible_text_states", {}).get("contrast_card", [])
    if any("Loading values" in text for text in contrast_texts):
        virtual["violations"].append(
            "Show-all replaced the previously settled contrast_score card with loading content"
        )
    virtual["violations"].extend(_virtual_card_continuity_violations(
        hydration_frames,
        surface_names=("metric_virtual_list", "categorical_virtual_list"),
        initially_settled=frozenset({
            "contrast_score",
            "quality_score",
            "dataset_from",
            "review_group",
        }),
    ))
    virtual_reset = _virtual_field_reset_summary(
        virtual_trace,
        previous_reset_key=virtual_reset_key,
        expectations=(
            ("metric_virtual_list", "contrast_score", "2 classes"),
            ("categorical_virtual_list", "dataset_from", "2 values"),
        ),
    )
    virtual["virtual_hard_reset"] = virtual_reset
    virtual["violations"].extend(virtual_reset["violations"])
    virtual["show_all_trace_frame_count"] = len(virtual_trace.get("frames", []))
    owned_frames = 0
    for frame in virtual_trace.get("frames", []):
        surfaces = frame.get("surfaces") if isinstance(frame, dict) else None
        if not isinstance(surfaces, dict):
            continue
        field_list = surfaces.get("metric_virtual_list")
        if isinstance(field_list, dict) and field_list.get("visible") is True:
            owned_frames += 1
            virtual["violations"].extend(_requested_field_ownership_violations(surfaces))
    virtual["show_all_owned_frame_count"] = owned_frames
    if owned_frames == 0:
        virtual["violations"].append("Show-all had no visible owned virtual-list frame")
    virtual["stable_host_retained"] = stable_host_retained
    if not virtual["stable_host_retained"]:
        virtual["violations"].append(
            "metric histogram-to-category hydration replaced its stable outer host"
        )
    virtual["geometry"] = geometry
    virtual["bottom_before_toggle"] = bottom_before_toggle
    virtual["bottom_after_toggle"] = bottom_after_toggle
    virtual["schema_transitions"] = schema_transitions
    virtual["violations"].extend(schema_transitions["violations"])
    virtual["hard_reset"] = hard_reset
    virtual["single_field_hard_reset"] = single_reset
    virtual["violations"].extend(single_reset["violations"])
    heights = [] if not isinstance(geometry, dict) else [
        *geometry.get("before", []),
        *geometry.get("after", []),
    ]
    if not heights or any(abs(float(height) - 384.0) > max_delta_px for height in heights):
        virtual["violations"].append(f"virtual metric cards lost their 384px frame: {heights!r}")
    if bottom_before_toggle != bottom_after_toggle:
        virtual["violations"].append(
            "Show-one/Show-all remount did not retain the virtual range and facet ownership"
        )
    if boundary_field not in bottom_after_toggle.get("rendered", []):
        virtual["violations"].append(
            f"virtual scroll never exercised the post-batch boundary {boundary_field!r}"
        )
    if hard_reset.get("scrollTop") != 0 or boundary_field in hard_reset.get("rendered", []):
        virtual["violations"].append("hard reset did not re-seed the first virtual facet batch")
    virtual["violations"] = list(dict.fromkeys(virtual["violations"]))
    _configure_facets(
        page,
        delays={},
        emptyFields=[],
        categoryFields=[],
        metricRanges={},
    )
    return {
        "selection": selection,
        "categorical_virtualization": categorical_virtual,
        "virtualization": virtual,
    }


def _derived_value_state(page: Any) -> str | None:
    value = page.locator('[data-derived-categorical-value="0"]').get_attribute("data-facet-state")
    return value if isinstance(value, str) else None


def _exercise_derived(
    page: Any,
    max_delta_px: float,
    timeout_ms: float,
) -> dict[str, Any]:
    page.get_by_role("button", name="Derived Score").click()
    card = page.locator("[data-derived-score-card]").first
    card.wait_for(state="visible", timeout=timeout_ms)
    name = card.locator("[data-derived-score-name]")
    weight = card.locator('[data-derived-numeric-weight="0"]')
    formula = card.locator("[data-derived-formula-code]")
    name.fill("draft-survives")
    weight.fill("7")
    formula.fill("draft_formula = 0 + 7*quality_score")

    missing_trigger = card.locator(
        '[data-derived-numeric-missing="0"] button[aria-haspopup="listbox"]'
    ).first
    missing_paint = _capture_dropdown_first_paint(page, missing_trigger, "Numeric missing 1")
    missing_trigger.focus()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("End")
    page.keyboard.press("Enter")
    page.wait_for_function(
        """() => (document.querySelector('[data-derived-numeric-missing="0"] button')?.textContent || '').includes('Missing = 0')""",
        timeout=timeout_ms,
    )

    continuity_selectors = {
        "card": "[data-derived-score-card]",
        "name": "[data-derived-score-name]",
        "weight": '[data-derived-numeric-weight="0"]',
        "formula": "[data-derived-formula-code]",
        "missing": '[data-derived-numeric-missing="0"]',
    }
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="derived_equal_schema_response",
        selectors=continuity_selectors,
    )
    direction = page.locator('button[aria-label="Toggle sort direction"]').first
    with page.expect_response(lambda response: "/folders/query" in response.url, timeout=timeout_ms):
        direction.click()
    page.wait_for_timeout(120)
    continuity_trace = stop_painted_frame_trace(page)
    continuity = _summarize_trace(
        continuity_trace,
        anchor_names=("card",),
        required_names=tuple(continuity_selectors),
        max_delta_px=max_delta_px,
    )
    retained = {
        "name": name.input_value(),
        "weight": weight.input_value(),
        "formula": formula.input_value(),
        "missing": missing_trigger.inner_text().strip(),
    }
    continuity["retained_values"] = retained
    expected = {
        "name": "draft-survives",
        "weight": "7",
        "formula": "draft_formula = 0 + 7*quality_score",
        "missing": "Missing = 0",
    }
    if retained != expected:
        continuity["violations"].append(
            f"equal-schema response reset unsaved Derived values: {retained!r}"
        )

    _configure_facets(page, delays={"derived_group": 450}, emptyFields=[], errorFields=[])
    card.get_by_role("button", name="Add").nth(1).click()
    value_control = card.locator('[data-derived-categorical-value="0"]')
    value_input = value_control.get_by_role("combobox", name="Categorical value 1")
    value_input.wait_for(state="visible", timeout=timeout_ms)
    value_selectors = {
        "value_control": '[data-derived-categorical-value="0"]',
        "value_input": '[data-derived-categorical-value="0"] [role="combobox"]',
    }
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="derived_categorical_value",
        selectors=value_selectors,
    )
    _select_dropdown_option(
        page,
        '[data-derived-categorical-key="0"] button[aria-haspopup="listbox"]',
        "Categorical field 1",
        "derived_group",
    )
    page.wait_for_function(
        """() => document.querySelector('[data-derived-categorical-value="0"]')?.getAttribute('data-facet-state') === 'pending'""",
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """() => document.querySelector('[data-derived-categorical-value="0"]')?.getAttribute('data-facet-state') === 'ready'""",
        timeout=timeout_ms,
    )
    page.wait_for_timeout(80)
    value_trace = stop_painted_frame_trace(page)
    value_control_summary = _summarize_trace(
        value_trace,
        anchor_names=tuple(value_selectors),
        required_names=tuple(value_selectors),
        max_delta_px=max_delta_px,
    )
    value_control_summary["terminal_state"] = _derived_value_state(page)
    value_input.click()
    page.keyboard.press("ArrowDown")
    active_option = page.evaluate(
        """() => {
          const input = document.querySelector('[data-derived-categorical-value="0"] [role="combobox"]');
          const activeId = input?.getAttribute('aria-activedescendant') || '';
          const option = activeId ? document.getElementById(activeId) : null;
          return { activeId, role: option?.getAttribute('role') || null };
        }"""
    )
    value_control_summary["active_descendant"] = active_option
    if not active_option.get("activeId") or active_option.get("role") != "option":
        value_control_summary["violations"].append(
            f"editable categorical value lost active-descendant semantics: {active_option!r}"
        )
    page.keyboard.press("Escape")
    value_input.click()
    value_panel = page.get_by_role("listbox", name="Categorical value 1")
    value_panel.wait_for(state="visible", timeout=timeout_ms)
    value_panel.get_by_role("option", name="derived-0", exact=True).click()
    value_panel.wait_for(state="hidden", timeout=timeout_ms)
    value_control_summary["pointer_selection"] = {
        "value": value_input.input_value(),
        "panel_visible": value_panel.is_visible(),
    }
    if value_input.input_value() != "derived-0" or value_panel.is_visible():
        value_control_summary["violations"].append(
            "pointer-selecting a known editable value reopened its panel"
        )
    _configure_facets(
        page,
        delays={"explicit_empty_group": 180},
        emptyFields=[],
        explicitEmptyFields=["explicit_empty_group"],
        errorFields=[],
    )
    _select_dropdown_option(
        page,
        '[data-derived-categorical-key="0"] button[aria-haspopup="listbox"]',
        "Categorical field 1",
        "explicit_empty_group",
    )
    page.wait_for_function(
        """() => document.querySelector('[data-derived-categorical-value="0"]')?.getAttribute('data-facet-state') === 'pending'""",
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """() => document.querySelector('[data-derived-categorical-value="0"]')?.getAttribute('data-facet-state') === 'empty'""",
        timeout=timeout_ms,
    )
    _configure_facets(
        page,
        delays={"error_group": 80},
        emptyFields=[],
        explicitEmptyFields=[],
        errorFields=["error_group"],
    )
    _select_dropdown_option(
        page,
        '[data-derived-categorical-key="0"] button[aria-haspopup="listbox"]',
        "Categorical field 1",
        "error_group",
    )
    page.wait_for_function(
        """() => document.querySelector('[data-derived-categorical-value="0"]')?.getAttribute('data-facet-state') === 'error'""",
        timeout=timeout_ms,
    )
    value_control_summary["partial_local_states"] = {
        "explicit_empty": "empty",
        "terminal_error": _derived_value_state(page),
    }
    _configure_facets(
        page,
        delays={},
        emptyFields=[],
        explicitEmptyFields=[],
        errorFields=[],
    )
    _select_dropdown_option(
        page,
        '[data-derived-categorical-key="0"] button[aria-haspopup="listbox"]',
        "Categorical field 1",
        "derived_group",
    )
    page.wait_for_function(
        """() => document.querySelector('[data-derived-categorical-value="0"]')?.getAttribute('data-facet-state') === 'ready'""",
        timeout=timeout_ms,
    )
    value_input.fill("freeform-value")
    page.keyboard.press("Enter")
    if value_input.input_value() != "freeform-value":
        value_control_summary["violations"].append("freeform categorical value was not retained")

    layout_selectors = {
        "card": "[data-derived-score-card]",
        "formula_preview": "[data-derived-formula-preview]",
        "score_status": "[data-derived-score-status]",
        "score_preview": "[data-derived-score-preview-histogram]",
        "diagnostics": "[data-derived-formula-diagnostics]",
    }
    formula.scroll_into_view_if_needed()
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="derived_long_content",
        selectors=layout_selectors,
    )
    long_name = "long_score_" + ("abcdefghij" * 20)
    name.evaluate(
        """(input, value) => {
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
          setter?.call(input, value);
          input.dispatchEvent(new Event('input', { bubbles: true }));
        }""",
        long_name,
    )
    missing_terms = " + ".join(f"1*missing_metric_{index:02d}" for index in range(20))
    formula.fill(f"broken_score = 0 + {missing_terms}")
    card.locator("[data-derived-formula-apply]").click()
    page.wait_for_function(
        """() => (document.querySelector('[data-derived-formula-diagnostics]')?.textContent || '').includes('missing_metric_19')""",
        timeout=timeout_ms,
    )
    page.wait_for_timeout(80)
    layout_trace = stop_painted_frame_trace(page)
    layout = _summarize_trace(
        layout_trace,
        anchor_names=tuple(layout_selectors),
        required_names=tuple(layout_selectors),
        max_delta_px=max_delta_px,
    )
    bounded = page.evaluate(
        """() => {
          const selectors = ['[data-derived-formula-preview]', '[data-derived-score-status]', '[data-derived-formula-diagnostics]'];
          return selectors.map(selector => {
            const element = document.querySelector(selector);
            const style = element instanceof HTMLElement ? getComputedStyle(element) : null;
            return {
              selector,
              clientHeight: element?.clientHeight || 0,
              scrollHeight: element?.scrollHeight || 0,
              overflowY: style?.overflowY || null,
              text: (element?.textContent || '').trim(),
            };
          });
        }"""
    )
    layout["bounded_regions"] = bounded
    if any(region.get("overflowY") not in {"auto", "scroll"} for region in bounded):
        layout["violations"].append(f"Derived bounded regions lost internal scrolling: {bounded!r}")
    if "missing_metric_19" not in bounded[-1].get("text", ""):
        layout["violations"].append("long diagnostics lost accessible full text")

    card.locator("[data-derived-formula-use-current]").click()
    card.locator("[data-derived-score-apply]").click()
    page.wait_for_function(
        """expected => document.querySelector('[data-derived-score-name]')?.value === expected""",
        arg=long_name,
        timeout=timeout_ms,
    )
    page.locator("[data-derived-score-name]").fill("unsaved-after-apply")
    page.locator("[data-derived-score-clear]").click()
    page.wait_for_function(
        """() => document.querySelector('[data-derived-score-name]')?.value === 'new_score'""",
        timeout=timeout_ms,
    )
    semantic_reset = {
        "name_after_clear": page.locator("[data-derived-score-name]").input_value(),
        "formula_after_clear": page.locator("[data-derived-formula-code]").input_value(),
        "violations": [],
    }
    if semantic_reset["name_after_clear"] != "new_score":
        semantic_reset["violations"].append("semantic clear did not rehydrate the Derived draft")

    return {
        "equal_schema_response": continuity,
        "categorical_value_control": value_control_summary,
        "long_content": layout,
        "semantic_reset": semantic_reset,
        "missing_dropdown_paint": missing_paint,
    }


def _wait_for_left_tool(page: Any, tool: str, timeout_ms: float) -> None:
    labels = {
        "folders": "Folders",
        "metrics": "Metrics and Filters",
        "derived": "Derived Score",
    }
    page.wait_for_function(
        """expected => {
          const button = document.querySelector(`button[aria-label="${expected.label}"]`);
          const panel = document.querySelector(`[data-left-tool-panel="${expected.tool}"]`);
          return button?.getAttribute('aria-pressed') === 'true'
            && panel instanceof HTMLElement
            && !panel.hidden
            && !panel.closest('[hidden]');
        }""",
        arg={"tool": tool, "label": labels[tool]},
        timeout=timeout_ms,
    )


def _derived_draft_values(page: Any) -> dict[str, str]:
    return {
        "name": page.locator("[data-derived-score-name]").input_value(),
        "formula": page.locator("[data-derived-formula-code]").input_value(),
        "missing": page.locator('[data-derived-numeric-missing="0"] button').inner_text().strip(),
    }


def _exercise_left_tool_continuity(
    page: Any,
    max_delta_px: float,
    timeout_ms: float,
) -> dict[str, Any]:
    violations: list[str] = []
    draft_before = _derived_draft_values(page)
    page.evaluate(
        """() => {
          window.__lensletLeftToolNodes = Object.fromEntries(
            ['folders', 'metrics', 'derived'].map(tool => [
              tool,
              document.querySelector(`[data-left-tool-panel="${tool}"]`),
            ]),
          );
        }"""
    )

    page.get_by_role("button", name="Metrics and Filters").click()
    _wait_for_left_tool(page, "metrics", timeout_ms)
    show_all_button = page.locator("[data-metric-show-all]").first
    if show_all_button.inner_text().strip() == "Show all":
        show_all_button.click()
    page.locator('[data-virtual-field-list="metric"]').wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_function(
        """() => {
          const cards = Array.from(document.querySelectorAll(
            '[data-virtual-field-list="metric"] [data-metric-card-host]',
          ));
          return cards.length > 0
            && cards.every(card => card.getAttribute('data-facet-state') !== 'pending');
        }""",
        timeout=timeout_ms,
    )
    metrics_before = page.evaluate(
        """() => {
          const panel = document.querySelector('[data-metrics-panel]');
          const rect = panel?.getBoundingClientRect();
          return {
            categorical: document.querySelector('[data-categorical-selector]')?.getAttribute('data-facet-presented-field'),
            metricCards: Array.from(document.querySelectorAll('[data-metric-card-host]'))
              .map(card => card.getAttribute('data-metric-card-host')).filter(Boolean).sort(),
            showAll: (document.querySelector('[data-metric-show-all]')?.textContent || '').trim(),
            requestedMetrics: panel?.getAttribute('data-requested-metric-fields'),
            requestedCategoricals: panel?.getAttribute('data-requested-categorical-fields'),
            rect: rect ? { top: rect.top, left: rect.left, width: rect.width, height: rect.height } : null,
          };
        }"""
    )

    page.get_by_role("button", name="Derived Score").click()
    _wait_for_left_tool(page, "derived", timeout_ms)
    if _derived_draft_values(page) != draft_before:
        violations.append("Metrics -> Derived reset the unsaved Derived draft")
    page.get_by_role("button", name="Metrics and Filters").click()
    _wait_for_left_tool(page, "metrics", timeout_ms)

    page.get_by_role("button", name="Folders").click()
    _wait_for_left_tool(page, "folders", timeout_ms)
    hidden_facet_count_before = page.evaluate(
        "() => window.__lensletFacetController?.requests?.length || 0"
    )
    page.wait_for_timeout(120)
    hidden_facet_count_after = page.evaluate(
        "() => window.__lensletFacetController?.requests?.length || 0"
    )
    if hidden_facet_count_after != hidden_facet_count_before:
        violations.append(
            "hidden Metrics tool started a facet request while Folders was active"
        )
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="folders_to_metrics",
        selectors={
            "metrics_panel": "[data-metrics-panel]",
            "metric_card": "[data-metric-card-host]",
            "categorical_card": "[data-categorical-card]",
            "metric_virtual_list": '[data-virtual-field-list="metric"]',
            "categorical_virtual_list": '[data-virtual-field-list="categorical"]',
            "metric_selector": "[data-metric-selector]",
            "categorical_selector": "[data-categorical-selector]",
        },
    )
    mark_painted_frame_action(
        page,
        action_id="folders-to-metrics",
        expected_path="metrics",
    )
    page.get_by_role("button", name="Metrics and Filters").click()
    _wait_for_left_tool(page, "metrics", timeout_ms)
    page.wait_for_timeout(100)
    trace = stop_painted_frame_trace(page)
    visible_frames: list[dict[str, Any]] = []
    for frame in trace.get("frames", []):
        marker = frame.get("marker") if isinstance(frame, dict) else None
        surfaces = frame.get("surfaces") if isinstance(frame, dict) else None
        panel = surfaces.get("metrics_panel") if isinstance(surfaces, dict) else None
        if (
            isinstance(marker, dict)
            and marker.get("actionId") == "folders-to-metrics"
            and isinstance(panel, dict)
            and panel.get("visible") is True
        ):
            visible_frames.append(frame)
    first_visible = visible_frames[0] if visible_frames else None
    if first_visible is None:
        violations.append("Folders -> Metrics had no earliest visible Metrics frame")
    for frame in visible_frames:
        surfaces = frame["surfaces"]
        text = " ".join(str(surface.get("text") or "") for surface in surfaces.values() if isinstance(surface, dict))
        panel_data = surfaces["metrics_panel"].get("attrs", {}).get("data", {})
        if "Loading values" in text:
            violations.append("Folders -> Metrics painted a loading field body")
        if panel_data.get("data-requested-metric-fields") in {None, "[]"}:
            violations.append("Folders -> Metrics painted without metric query ownership")
        if panel_data.get("data-requested-categorical-fields") in {None, "[]"}:
            violations.append("Folders -> Metrics painted without categorical query ownership")
        violations.extend(_requested_field_ownership_violations(surfaces))
    request_count_after = page.evaluate(
        "() => window.__lensletFacetController?.requests?.length || 0"
    )
    hidden_folder_count_before = page.evaluate(
        "() => window.__lensletFacetController?.folderRequests?.length || 0"
    )
    page.wait_for_timeout(120)
    hidden_folder_count_after = page.evaluate(
        "() => window.__lensletFacetController?.folderRequests?.length || 0"
    )
    if hidden_folder_count_after != hidden_folder_count_before:
        violations.append("hidden FolderTree started a folder request while Metrics was active")

    collapsed_focus = _collapse_left_panel_with_focus_check(page, timeout_ms)
    violations.extend(collapsed_focus["violations"])
    collapsed_counts_before = page.evaluate(
        """() => ({
          facets: window.__lensletFacetController?.requests?.length || 0,
          folders: window.__lensletFacetController?.folderRequests?.length || 0,
        })"""
    )
    page.wait_for_timeout(120)
    collapsed_counts_after = page.evaluate(
        """() => ({
          facets: window.__lensletFacetController?.requests?.length || 0,
          folders: window.__lensletFacetController?.folderRequests?.length || 0,
        })"""
    )
    if collapsed_counts_after != collapsed_counts_before:
        violations.append(
            f"collapsed left tools started background requests: "
            f"{collapsed_counts_before!r} -> {collapsed_counts_after!r}"
        )
    page.get_by_role("button", name="Metrics and Filters").click()
    _wait_for_left_tool(page, "metrics", timeout_ms)

    categorical_trigger = page.locator(
        '[data-categorical-selector] button[aria-haspopup="listbox"]'
    ).first
    categorical_trigger.click()
    page.locator('[role="listbox"][aria-label="Categorical"]').wait_for(
        state="visible",
        timeout=timeout_ms,
    )
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function(
        "() => document.querySelector('.app-left-panel')?.hidden === true",
        timeout=timeout_ms,
    )
    page.wait_for_function(
        "() => document.querySelector('[data-metrics-facet-observer-enabled]')"
        "?.getAttribute('data-metrics-facet-observer-enabled') === 'false'",
        timeout=timeout_ms,
    )
    responsive_facet_observer_disabled = page.locator(
        "[data-metrics-facet-observer-enabled]"
    ).get_attribute("data-metrics-facet-observer-enabled") == "false"
    page.wait_for_function(
        "() => !document.querySelector('[role=\"listbox\"][aria-label=\"Categorical\"]')",
        timeout=timeout_ms,
    )
    dropdown_portal_closed = page.evaluate(
        """() => {
          const active = document.activeElement;
          const sidebar = document.querySelector('.app-left-panel');
          return {
            panelPresent: Boolean(document.querySelector('[role="listbox"][aria-label="Categorical"]')),
            activeInPortal: Boolean(active?.closest?.('[role="listbox"], .theme-settings-menu-panel')),
            activeInHiddenSidebar: Boolean(sidebar && active && sidebar.contains(active)),
          };
        }"""
    )
    if any(dropdown_portal_closed.values()):
        violations.append(
            f"responsive suppression retained a categorical portal/focus target: "
            f"{dropdown_portal_closed!r}"
        )
    page.set_viewport_size({"width": 1_440, "height": 920})
    _wait_for_left_tool(page, "metrics", timeout_ms)

    settings_trigger = page.locator(".theme-settings-menu-trigger-sidebar").first
    settings_trigger.click()
    page.locator(".theme-settings-menu-panel").wait_for(state="visible", timeout=timeout_ms)
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function(
        "() => document.querySelector('.app-left-panel')?.hidden === true",
        timeout=timeout_ms,
    )
    page.wait_for_function(
        "() => !document.querySelector('.theme-settings-menu-panel')",
        timeout=timeout_ms,
    )
    settings_portal_closed = page.evaluate(
        """() => {
          const active = document.activeElement;
          const sidebar = document.querySelector('.app-left-panel');
          return {
            panelPresent: Boolean(document.querySelector('.theme-settings-menu-panel')),
            activeInPortal: Boolean(active?.closest?.('[role="listbox"], .theme-settings-menu-panel')),
            activeInHiddenSidebar: Boolean(sidebar && active && sidebar.contains(active)),
          };
        }"""
    )
    if any(settings_portal_closed.values()):
        violations.append(
            f"responsive suppression retained a settings portal/focus target: "
            f"{settings_portal_closed!r}"
        )
    responsive_counts_before = page.evaluate(
        """() => ({
          facets: window.__lensletFacetController?.requests?.length || 0,
          folders: window.__lensletFacetController?.folderRequests?.length || 0,
        })"""
    )
    page.wait_for_timeout(120)
    responsive_counts_after = page.evaluate(
        """() => ({
          facets: window.__lensletFacetController?.requests?.length || 0,
          folders: window.__lensletFacetController?.folderRequests?.length || 0,
        })"""
    )
    if responsive_counts_after != responsive_counts_before:
        violations.append(
            f"responsive suppression started background requests: "
            f"{responsive_counts_before!r} -> {responsive_counts_after!r}"
        )
    page.set_viewport_size({"width": 1_440, "height": 920})
    _wait_for_left_tool(page, "metrics", timeout_ms)
    page.wait_for_function(
        "() => document.querySelector('[data-metrics-facet-observer-enabled]')"
        "?.getAttribute('data-metrics-facet-observer-enabled') === 'true'",
        timeout=timeout_ms,
    )

    node_identity = page.evaluate(
        """() => ({
          folders: window.__lensletLeftToolNodes?.folders
            === document.querySelector('[data-left-tool-panel="folders"]'),
          metrics: window.__lensletLeftToolNodes?.metrics
            === document.querySelector('[data-left-tool-panel="metrics"]'),
          derived: window.__lensletLeftToolNodes?.derived
            === document.querySelector('[data-left-tool-panel="derived"]'),
          hiddenPanelsInert: Array.from(document.querySelectorAll('[data-left-tool-panel][hidden]'))
            .every(panel => panel.hasAttribute('inert') && panel.getClientRects().length === 0),
        })"""
    )
    if not all(node_identity.values()):
        violations.append(f"left-tool lifecycle or inertness changed across visibility: {node_identity!r}")

    metrics_after = page.evaluate(
        """() => ({
          categorical: document.querySelector('[data-categorical-selector]')?.getAttribute('data-facet-presented-field'),
          metricCards: Array.from(document.querySelectorAll('[data-metric-card-host]'))
            .map(card => card.getAttribute('data-metric-card-host')).filter(Boolean).sort(),
          showAll: (document.querySelector('[data-metric-show-all]')?.textContent || '').trim(),
        })"""
    )
    if metrics_after.get("metricCards") != metrics_before.get("metricCards"):
        violations.append(f"metric Show-all cards changed across visibility: {metrics_before!r} -> {metrics_after!r}")
    if metrics_after.get("categorical") != metrics_before.get("categorical"):
        violations.append(f"categorical selection changed across visibility: {metrics_before!r} -> {metrics_after!r}")
    if metrics_after.get("showAll") != metrics_before.get("showAll") or metrics_after.get("showAll") != "Show one":
        violations.append(f"metric Show-all state changed across visibility: {metrics_before!r} -> {metrics_after!r}")

    show_all_button.click()
    _wait_for_metric_state(page, "quality_score", "ready", timeout_ms)
    selected_metric_after = page.locator(
        "[data-metric-selector]"
    ).get_attribute("data-facet-presented-field")
    if selected_metric_after != "quality_score":
        violations.append(
            f"metric selection changed behind Show-all across visibility: {selected_metric_after!r}"
        )

    page.get_by_role("button", name="Derived Score").click()
    _wait_for_left_tool(page, "derived", timeout_ms)
    draft_after = _derived_draft_values(page)
    if draft_after != draft_before:
        violations.append(f"Derived draft changed across visibility: {draft_before!r} -> {draft_after!r}")

    first_visible_state = None
    if isinstance(first_visible, dict):
        surfaces = first_visible.get("surfaces", {})
        first_visible_state = {
            name: {
                "text": surface.get("text"),
                "attrs": surface.get("attrs"),
            }
            for name, surface in surfaces.items()
            if isinstance(surface, dict)
        }
    return {
        "draft_before": draft_before,
        "draft_after": draft_after,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "node_identity": node_identity,
        "hidden_facet_counts": [hidden_facet_count_before, hidden_facet_count_after],
        "request_count_after": request_count_after,
        "hidden_folder_counts": [hidden_folder_count_before, hidden_folder_count_after],
        "collapsed_request_counts": [collapsed_counts_before, collapsed_counts_after],
        "collapsed_focus": collapsed_focus,
        "responsive_request_counts": [responsive_counts_before, responsive_counts_after],
        "responsive_facet_observer_disabled": responsive_facet_observer_disabled,
        "dropdown_portal_closed": dropdown_portal_closed,
        "settings_portal_closed": settings_portal_closed,
        "selected_metric_after_show_all": selected_metric_after,
        "first_visible_metrics_frame": first_visible_state,
        "visible_frame_count": len(visible_frames),
        "max_delta_px": max_delta_px,
        "violations": list(dict.fromkeys(violations)),
    }


def _narrow_app_structure(browser: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_grid(page, timeout_ms)
        result = page.evaluate(
            """() => ({
              documentOverflowPx: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
              mobileDrawerPresent: Boolean(document.querySelector('.mobile-drawer')),
              mobileDrawerToggleName: document.querySelector('button[aria-label$="mobile toolbar controls"]')?.getAttribute('aria-label') || null,
            })"""
        )
        if not isinstance(result, dict):
            raise SmokeFailure("Failed to capture narrow metrics structure.")
        return result
    finally:
        context.close()


def run_metrics_probe(base_url: str, max_delta_px: float, browser_timeout_ms: float) -> ProbeResult:
    _, _, sync_playwright = import_playwright()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1_440, "height": 920})
        try:
            page = context.new_page()
            page.set_default_timeout(browser_timeout_ms)
            page.goto(base_url, wait_until="domcontentloaded")
            wait_for_grid(page, browser_timeout_ms)
            open_metrics_panel(page, browser_timeout_ms)
            _wait_for_metrics_ready(page, browser_timeout_ms)
            metric_field_transition = _exercise_metric_field_transition(
                page,
                max_delta_px,
                browser_timeout_ms,
            )
            categorical = _exercise_categorical(page, max_delta_px, browser_timeout_ms)
            histogram = _exercise_histogram(page, max_delta_px, browser_timeout_ms)
            facet_transitions = _exercise_facet_transitions(page, max_delta_px, browser_timeout_ms)
            selection_virtualization = _exercise_selection_and_virtualization(
                page,
                max_delta_px,
                browser_timeout_ms,
            )
            operator_dropdowns = _exercise_operator_dropdowns(page, browser_timeout_ms)
            derived = _exercise_derived(page, max_delta_px, browser_timeout_ms)
            left_tool_continuity = _exercise_left_tool_continuity(
                page,
                max_delta_px,
                browser_timeout_ms,
            )
            narrow = _narrow_app_structure(browser, base_url, browser_timeout_ms)
        finally:
            context.close()
            browser.close()

    violations = [
        f"{phase}: {violation}"
        for phase, summary in (("categorical", categorical), ("histogram", histogram))
        for violation in summary["violations"]
    ]
    violations.extend(
        f"metric field: {violation}"
        for violation in metric_field_transition["violations"]
    )
    violations.extend(
        f"facet {field}: {violation}"
        for field, summary in facet_transitions.items()
        for violation in summary["violations"]
    )
    violations.extend(
        f"left tool: {violation}"
        for violation in left_tool_continuity["violations"]
    )
    violations.extend(
        f"{phase}: {violation}"
        for phase, summary in selection_virtualization.items()
        for violation in summary["violations"]
    )
    violations.extend(f"operators: {violation}" for violation in operator_dropdowns["violations"])
    violations.extend(
        f"derived {phase}: {violation}"
        for phase, summary in derived.items()
        for violation in summary["violations"]
    )
    if float(narrow.get("documentOverflowPx") or 0) > max_delta_px:
        violations.append("narrow: document overflow exceeded the structural threshold")
    if not narrow.get("mobileDrawerPresent"):
        violations.append("narrow: mobile drawer structure was absent")
    if narrow.get("mobileDrawerToggleName") not in {
        "Hide mobile toolbar controls",
        "Show mobile toolbar controls",
    }:
        violations.append("narrow: mobile drawer trigger lost its accessible name")
    checks = {
        "fixture": {"rows": METRICS_FIXTURE_ROW_COUNT, "categorical_values": 2},
        "categorical_selection": categorical,
        "metric_field_transition": metric_field_transition,
        "histogram_drag": histogram,
        "facet_transitions": facet_transitions,
        "selection_and_virtualization": selection_virtualization,
        "operator_dropdowns": operator_dropdowns,
        "derived": derived,
        "left_tool_continuity": left_tool_continuity,
        "narrow_390x844_structure": narrow,
        "violations": violations,
    }
    if violations:
        raise MetricsProbeFailure("; ".join(violations), checks)
    maximum_delta = max(
        *categorical["rectangle_deltas_px"].values(),
        *histogram["rectangle_deltas_px"].values(),
        *metric_field_transition["rectangle_deltas_px"].values(),
        *(
            delta
            for summary in facet_transitions.values()
            for delta in summary["rectangle_deltas_px"].values()
        ),
        *(
            delta
            for summary in selection_virtualization.values()
            for delta in summary["rectangle_deltas_px"].values()
        ),
        *(
            delta
            for summary in derived.values()
            for delta in summary.get("rectangle_deltas_px", {}).values()
        ),
        0.0,
    )
    return ProbeResult(
        scenario="metrics",
        max_delta_px=max_delta_px,
        max_anchor_delta_px=maximum_delta,
        checks=checks,
    )
