"""Focused painted-frame probe for metric-card geometry stability."""

from __future__ import annotations

from typing import Any

from scripts.browser.gui_jitter.fixtures import METRICS_FIXTURE_ROW_COUNT
from scripts.browser.gui_jitter.grid_dom import open_metrics_panel
from scripts.browser.gui_jitter.painted_frames import (
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
    "next_control": "[data-attributes-card]",
}
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


def _rect_delta(baseline: dict[str, Any], candidate: dict[str, Any]) -> float:
    return max(
        abs(float(baseline[key]) - float(candidate[key]))
        for key in ("top", "left", "width", "height")
    )


def _summarize_trace(
    trace: dict[str, Any],
    *,
    anchor_names: tuple[str, ...],
    required_names: tuple[str, ...],
    max_delta_px: float,
) -> dict[str, Any]:
    frames = trace.get("frames")
    if not isinstance(frames, list) or not frames:
        return {"violations": ["trace has no painted frames"]}
    baseline_surfaces = frames[0].get("surfaces") if isinstance(frames[0], dict) else None
    if not isinstance(baseline_surfaces, dict):
        return {"violations": ["trace has no baseline surfaces"]}

    violations: list[str] = []
    deltas = {name: 0.0 for name in anchor_names}
    visible_states = {name: set() for name in required_names}
    texts = {name: set() for name in required_names}
    missing = {name: 0 for name in required_names}
    replaced: set[str] = set()
    for frame in frames:
        surfaces = frame.get("surfaces") if isinstance(frame, dict) else None
        if not isinstance(surfaces, dict):
            violations.append("trace contains a malformed frame")
            continue
        for name in required_names:
            surface = surfaces.get(name)
            if not isinstance(surface, dict) or not isinstance(surface.get("rect"), dict):
                missing[name] += 1
                continue
            visible_states[name].add(bool(surface.get("visible")))
            texts[name].add(str(surface.get("text") or ""))
        for name in anchor_names:
            baseline = baseline_surfaces.get(name)
            candidate = surfaces.get(name)
            if not isinstance(baseline, dict) or not isinstance(candidate, dict):
                continue
            if baseline.get("token") != candidate.get("token"):
                replaced.add(name)
            baseline_rect = baseline.get("rect")
            candidate_rect = candidate.get("rect")
            if isinstance(baseline_rect, dict) and isinstance(candidate_rect, dict):
                deltas[name] = max(deltas[name], _rect_delta(baseline_rect, candidate_rect))

    for name, count in missing.items():
        if count:
            violations.append(f"{name} was absent in {count} painted frames")
    if replaced:
        violations.append(f"anchored nodes were replaced: {sorted(replaced)!r}")
    for name, delta in deltas.items():
        if delta > max_delta_px:
            violations.append(
                f"{name} rectangle delta {delta:.3f}px exceeded {max_delta_px:.3f}px"
            )
    return {
        "frame_count": len(frames),
        "rectangle_deltas_px": deltas,
        "visible_states": {name: sorted(states) for name, states in visible_states.items()},
        "visible_text_states": {name: sorted(values) for name, values in texts.items()},
        "violations": violations,
    }


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


def _install_facet_controller(page: Any) -> None:
    page.evaluate(
        """() => {
          if (window.__lensletFacetController) return;
          const originalFetch = window.fetch.bind(window);
          const controller = {
            delays: {},
            emptyFields: [],
            explicitEmptyFields: [],
            errorFields: [],
            categoryFields: [],
            requests: [],
          };
          window.__lensletFacetController = controller;
          window.fetch = async (...args) => {
            const input = args[0];
            const init = args[1] || {};
            const rawUrl = input instanceof Request ? input.url : String(input);
            if (new URL(rawUrl, location.href).pathname !== '/folders/facets') {
              return originalFetch(...args);
            }
            let payload = {};
            try {
              const rawBody = input instanceof Request ? await input.clone().text() : init.body;
              payload = rawBody ? JSON.parse(String(rawBody)) : {};
            } catch {}
            const facetFields = payload.facet_fields || {};
            const metricFields = facetFields.metric_keys || [];
            const categoricalFields = facetFields.categorical_keys || [];
            const fields = [...metricFields, ...categoricalFields];
            const delayMs = fields.reduce(
              (maximum, field) => Math.max(maximum, Number(controller.delays[field] || 0)),
              0,
            );
            controller.requests.push({
              at: performance.now(),
              metricFields,
              categoricalFields,
              delayMs,
            });
            const response = await originalFetch(...args);
            if (delayMs > 0) await new Promise(resolve => setTimeout(resolve, delayMs));
            if (fields.some(field => controller.errorFields.includes(field))) {
              return new Response(JSON.stringify({ detail: 'forced facet probe failure' }), {
                status: 503,
                headers: { 'Content-Type': 'application/json' },
              });
            }
            const emptyFields = fields.filter(field => controller.emptyFields.includes(field));
            const explicitEmptyFields = fields.filter(
              field => controller.explicitEmptyFields.includes(field),
            );
            const categoryFields = metricFields.filter(field => controller.categoryFields.includes(field));
            if (!emptyFields.length && !explicitEmptyFields.length && !categoryFields.length) return response;
            const body = await response.json();
            for (const field of emptyFields) {
              if (metricFields.includes(field)) {
                body.metrics = body.metrics || {};
                delete body.metrics[field];
              }
              if (categoricalFields.includes(field)) {
                body.categoricals = body.categoricals || {};
                delete body.categoricals[field];
              }
            }
            for (const field of explicitEmptyFields) {
              if (metricFields.includes(field)) {
                body.metrics = body.metrics || {};
                body.metrics[field] = { histogram: null, categories: [] };
              }
              if (categoricalFields.includes(field)) {
                body.categoricals = body.categoricals || {};
                body.categoricals[field] = { values: [] };
              }
            }
            for (const field of categoryFields) {
              body.metrics = body.metrics || {};
              body.metrics[field] = body.metrics[field] || { histogram: null, categories: [] };
              body.metrics[field].categories = [
                { code: 0, label: 'low', population_count: 793 },
                { code: 1, label: 'high', population_count: 792 },
              ];
            }
            const headers = new Headers(response.headers);
            headers.delete('content-length');
            headers.delete('content-encoding');
            headers.set('content-type', 'application/json');
            return new Response(JSON.stringify(body), {
              status: response.status,
              statusText: response.statusText,
              headers,
            });
          };
        }"""
    )


def _configure_facets(page: Any, **updates: Any) -> None:
    page.evaluate(
        """updates => {
          const controller = window.__lensletFacetController;
          if (!controller) throw new Error('facet controller is not installed');
          Object.assign(controller, updates);
        }""",
        updates,
    )


def _select_dropdown_option(page: Any, trigger_selector: str, aria_label: str, value: str) -> None:
    trigger = page.locator(trigger_selector).first
    trigger.scroll_into_view_if_needed()
    trigger.click()
    panel = page.locator(f'[role="listbox"][aria-label="{aria_label}"]').first
    panel.wait_for(state="visible")
    option = panel.locator("button.dropdown-item", has_text=value).first
    if option.count() != 1:
        raise SmokeFailure(f"Dropdown {aria_label!r} is missing option {value!r}.")
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


def _target_facet_trace_summary(
    trace: dict[str, Any],
    *,
    field: str,
    forbidden_texts: tuple[str, ...],
    expected_text: str,
    max_delta_px: float,
) -> dict[str, Any]:
    summary = _summarize_trace(
        trace,
        anchor_names=("categorical_card", "next_control"),
        required_names=tuple(FACET_SELECTORS),
        max_delta_px=max_delta_px,
    )
    target_card_texts: list[str] = []
    for frame in trace.get("frames", []):
        surfaces = frame.get("surfaces") if isinstance(frame, dict) else None
        if not isinstance(surfaces, dict):
            continue
        selector = surfaces.get("categorical_selector")
        card = surfaces.get("categorical_card")
        selector_text = str(selector.get("text") or "") if isinstance(selector, dict) else ""
        card_text = str(card.get("text") or "") if isinstance(card, dict) else ""
        if selector_text.strip() == field:
            target_card_texts.append(card_text)
    if not target_card_texts:
        summary["violations"].append(f"{field} never owned a painted frame")
    if any(text in card_text for text in forbidden_texts for card_text in target_card_texts):
        summary["violations"].append(f"{field} painted data from the previous field")
    if not any(expected_text in text for text in target_card_texts):
        summary["violations"].append(f"{field} never painted {expected_text!r}")
    summary["target_card_texts"] = sorted(set(target_card_texts))
    return summary


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
    _install_facet_controller(page)
    phases: dict[str, Any] = {}
    cases = (
        ("review_group", {"delays": {"review_group": 350}}, "ready", "Population: 1585", ("synthetic",)),
        ("empty_group", {"delays": {"empty_group": 250}, "emptyFields": ["empty_group"]}, "empty", "No values found", ("review-",)),
        ("error_group", {"delays": {"error_group": 80}, "errorFields": ["error_group"]}, "error", "Could not load values", ("placeholder",)),
    )
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
        )
        _wait_for_categorical_state(page, field, "pending", timeout_ms)
        _wait_for_categorical_state(page, field, terminal_state, timeout_ms)
        page.wait_for_timeout(80)
        trace = stop_painted_frame_trace(page)
        phases[field] = _target_facet_trace_summary(
            trace,
            field=field,
            forbidden_texts=forbidden_texts,
            expected_text=expected_text,
            max_delta_px=max_delta_px,
        )
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
        delays={"contrast_score": 450},
        emptyFields=[],
        errorFields=[],
        categoryFields=["contrast_score"],
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
        """() => document.querySelector('[data-metric-card-host="contrast_score"]')?.getAttribute('data-facet-state') === 'pending'""",
        timeout=timeout_ms,
    )
    virtual_selectors = {
        "virtual_list": '[data-virtual-field-list="metric"]',
        "contrast_card": '[data-metric-card-host="contrast_score"]',
    }
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="metric_virtual_hydration",
        selectors=virtual_selectors,
    )
    page.wait_for_function(
        """() => document.querySelector('[data-metric-card-host="contrast_score"]')?.getAttribute('data-facet-state') === 'ready'
          && document.querySelector('[data-metric-card-host="contrast_score"] [data-metric-category-card="contrast_score"]')""",
        timeout=timeout_ms,
    )
    page.wait_for_timeout(80)
    virtual_trace = stop_painted_frame_trace(page)
    virtual = _summarize_trace(
        virtual_trace,
        anchor_names=tuple(virtual_selectors),
        required_names=tuple(virtual_selectors),
        max_delta_px=max_delta_px,
    )
    virtual["stable_host_retained"] = page.evaluate(
        """() => window.__lensletMetricCardHost
          === document.querySelector('[data-metric-card-host="contrast_score"]')"""
    )
    if not virtual["stable_host_retained"]:
        virtual["violations"].append(
            "metric histogram-to-category hydration replaced its stable outer host"
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
    virtual["geometry"] = geometry
    heights = [] if not isinstance(geometry, dict) else [
        *geometry.get("before", []),
        *geometry.get("after", []),
    ]
    if not heights or any(abs(float(height) - 384.0) > max_delta_px for height in heights):
        virtual["violations"].append(f"virtual metric cards lost their 384px frame: {heights!r}")
    _configure_facets(page, delays={}, categoryFields=[])
    return {"selection": selection, "virtualization": virtual}


def _capture_dropdown_first_paint(page: Any, trigger: Any, aria_label: str) -> dict[str, Any]:
    page.evaluate(
        """label => {
          const samples = [];
          const capture = (panel, phase) => {
            if (!(panel instanceof HTMLElement) || panel.getAttribute('aria-label') !== label) return;
            const style = getComputedStyle(panel);
            samples.push({
              phase,
              opacity: Number(style.opacity),
              transform: style.transform,
              animationName: style.animationName,
              visibility: style.visibility,
            });
          };
          const observer = new MutationObserver(records => {
            for (const record of records) {
              for (const node of record.addedNodes) {
                if (!(node instanceof HTMLElement)) continue;
                const panel = node.matches('.dropdown-panel') ? node : node.querySelector('.dropdown-panel');
                if (!(panel instanceof HTMLElement) || panel.getAttribute('aria-label') !== label) continue;
                capture(panel, 'mount');
                requestAnimationFrame(() => {
                  capture(panel, 'raf-1');
                  requestAnimationFrame(() => capture(panel, 'raf-2'));
                });
              }
            }
          });
          observer.observe(document.body, { childList: true, subtree: true });
          window.__lensletDropdownPaint = { samples, observer };
        }""",
        aria_label,
    )
    trigger.scroll_into_view_if_needed()
    trigger.click()
    page.locator(f'[role="listbox"][aria-label="{aria_label}"]').wait_for(state="visible")
    page.wait_for_timeout(60)
    samples = page.evaluate(
        """() => {
          const trace = window.__lensletDropdownPaint;
          trace?.observer?.disconnect();
          return trace?.samples || [];
        }"""
    )
    page.keyboard.press("Escape")
    visible = [sample for sample in samples if sample.get("visibility") != "hidden"]
    violations: list[str] = []
    if not visible:
        violations.append(f"{aria_label} had no visible first-paint sample")
    for sample in visible:
        if abs(float(sample.get("opacity", 0)) - 1.0) > 0.001:
            violations.append(f"{aria_label} painted with opacity {sample.get('opacity')!r}")
        if sample.get("transform") not in {"none", "matrix(1, 0, 0, 1, 0, 0)"}:
            violations.append(f"{aria_label} painted with transform {sample.get('transform')!r}")
        if sample.get("animationName") not in {"none", ""}:
            violations.append(f"{aria_label} retained animation {sample.get('animationName')!r}")
    return {"samples": samples, "violations": violations}


def _exercise_operator_dropdowns(page: Any, timeout_ms: float) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for dimension in ("width", "height"):
        label = f"{dimension.title()} operator"
        trigger = page.locator(
            f'[data-dimension-operator="{dimension}"] button[aria-haspopup="listbox"]'
        ).first
        checks[dimension] = _capture_dropdown_first_paint(page, trigger, label)
        trigger.focus()
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Home")
        page.keyboard.press("Enter")
        page.wait_for_function(
            """expected => (document.querySelector(expected.selector)?.textContent || '').trim() === '<'""",
            arg={"selector": f'[data-dimension-operator="{dimension}"] button'},
            timeout=timeout_ms,
        )
    native_select_count = page.locator(
        "[data-derived-score-card] select, [data-attributes-card] select"
    ).count()
    checks["native_select_count"] = native_select_count
    checks["violations"] = [
        violation
        for dimension in ("width", "height")
        for violation in checks[dimension]["violations"]
    ]
    if native_select_count:
        checks["violations"].append(f"found {native_select_count} native operator/missing selects")
    return checks


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
        f"facet {field}: {violation}"
        for field, summary in facet_transitions.items()
        for violation in summary["violations"]
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
        "histogram_drag": histogram,
        "facet_transitions": facet_transitions,
        "selection_and_virtualization": selection_virtualization,
        "operator_dropdowns": operator_dropdowns,
        "derived": derived,
        "narrow_390x844_structure": narrow,
        "violations": violations,
    }
    if violations:
        raise MetricsProbeFailure("; ".join(violations), checks)
    maximum_delta = max(
        *categorical["rectangle_deltas_px"].values(),
        *histogram["rectangle_deltas_px"].values(),
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
