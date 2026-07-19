"""Painted-frame evidence for Derived term presentation ownership."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from scripts.browser.gui_jitter.metrics_controller import configure_facets
from scripts.browser.gui_jitter.metrics_trace import summarize_trace
from scripts.browser.gui_jitter.painted_frames import (
    start_painted_frame_trace,
    stop_painted_frame_trace,
)
from scripts.smoke_harness import SmokeFailure

_SELECTORS = {
    "numeric_term": '[data-derived-numeric-term-slot="0"]',
    "numeric_selector": '[data-derived-numeric-key="0"] button[aria-haspopup="listbox"]',
    "numeric_histogram": '[data-derived-numeric-histogram-slot="0"]',
    "numeric_histogram_content": (
        '[data-derived-numeric-histogram-slot="0"] [data-derived-metric-histogram]'
    ),
    "score_preview": '[data-derived-numeric-histogram-slot="score-preview"]',
    "name": "[data-derived-score-name]",
    "weight": '[data-derived-numeric-weight="0"]',
}


def _select_numeric_metric(page: Any, metric_key: str) -> None:
    trigger = page.locator(_SELECTORS["numeric_selector"]).first
    trigger.scroll_into_view_if_needed()
    trigger.click()
    panel = page.get_by_role("listbox", name="Numeric metric 1")
    panel.wait_for(state="visible")
    option = panel.locator("button.dropdown-item", has_text=metric_key).first
    if option.count() != 1:
        raise SmokeFailure(f"Derived metric selector is missing {metric_key!r}.")
    option.click()


def _wait_for_retained_metric(page: Any, metric_key: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """key => {
          const term = document.querySelector('[data-derived-numeric-term-slot="0"]');
          const slot = document.querySelector('[data-derived-numeric-histogram-slot="0"]');
          const selector = document.querySelector(
            '[data-derived-numeric-key="0"] button[aria-haspopup="listbox"]'
          );
          const presented = term?.getAttribute('data-facet-presented-field');
          return term?.getAttribute('data-facet-requested-field') === key
            && presented !== key
            && term?.hasAttribute('inert')
            && selector?.textContent?.trim() === presented
            && slot?.getAttribute('data-facet-requested-field') === key
            && slot.getAttribute('data-facet-presented-field') === presented
            && slot.getAttribute('aria-busy') === 'true';
        }""",
        arg=metric_key,
        timeout=timeout_ms,
    )


def _wait_for_terminal_metric(
    page: Any,
    metric_key: str,
    terminal_state: str,
    timeout_ms: float,
) -> None:
    try:
        page.wait_for_function(
            """expected => {
              const slot = document.querySelector('[data-derived-numeric-histogram-slot="0"]');
              const term = document.querySelector('[data-derived-numeric-term-slot="0"]');
              const selector = document.querySelector(
                '[data-derived-numeric-key="0"] button[aria-haspopup="listbox"]'
              );
              const histogram = slot?.querySelector('[data-derived-metric-histogram]');
              return term?.getAttribute('data-facet-presented-field') === expected.key
                && !term.hasAttribute('inert')
                && selector?.textContent?.trim() === expected.key
                && slot?.getAttribute('data-facet-presented-field') === expected.key
                && histogram?.getAttribute('data-facet-state') === expected.state;
            }""",
            arg={"key": metric_key, "state": terminal_state},
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError as exc:
        diagnostic = page.evaluate(
            """() => {
              const slot = document.querySelector('[data-derived-numeric-histogram-slot="0"]');
              const term = document.querySelector('[data-derived-numeric-term-slot="0"]');
              const histogram = slot?.querySelector('[data-derived-metric-histogram]');
              const controller = window.__lensletFacetController;
              return {
                requested: term?.getAttribute('data-facet-requested-field'),
                presented: term?.getAttribute('data-facet-presented-field'),
                inert: term?.hasAttribute('inert'),
                slotPresented: slot?.getAttribute('data-facet-presented-field'),
                state: histogram?.getAttribute('data-facet-state'),
                requestedTarget: document.querySelector('[data-browse-shell]')
                  ?.getAttribute('data-browse-requested-target'),
                requests: controller?.requests?.slice(-3),
                completions: controller?.completions?.slice(-3),
              };
            }"""
        )
        raise SmokeFailure(
            f"Derived metric {metric_key!r} did not settle as {terminal_state!r}: {diagnostic!r}"
        ) from exc


def _wait_for_scope_presentation(page: Any, path: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """expectedPath => {
          const shell = document.querySelector('[data-browse-shell]');
          const grid = document.querySelector('[role="grid"][aria-label="Gallery"]');
          const requested = shell?.getAttribute('data-browse-requested-target');
          const presented = shell?.getAttribute('data-browse-presentation-target');
          if (!requested || requested !== presented) return false;
          try {
            const queryKey = JSON.parse(requested);
            return grid?.getAttribute('data-grid-presentation-phase') === 'steady'
              && grid.getAttribute('aria-busy') !== 'true'
              && queryKey?.[1]?.[1] === expectedPath;
          } catch {
            return false;
          }
        }""",
        arg=path,
        timeout=timeout_ms,
    )


def _read_scope_draft_state(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => ({
          sameNode: window.__lensletDerivedScopeNode
            === document.querySelector('[data-derived-score-card]'),
          name: document.querySelector('[data-derived-score-name]')?.value,
          weight: document.querySelector('[data-derived-numeric-weight="0"]')?.value,
          metric: document.querySelector(
            '[data-derived-numeric-key="0"] button[aria-haspopup="listbox"]'
          )?.textContent?.trim(),
        })"""
    )


def wait_for_retained_categorical_term(
    page: Any,
    field_key: str,
    timeout_ms: float,
) -> None:
    page.wait_for_function(
        """key => {
          const term = document.querySelector('[data-derived-categorical-term-slot="0"]');
          const field = term?.querySelector(
            '[data-derived-categorical-key="0"] button[aria-haspopup="listbox"]'
          );
          const value = term?.querySelector('[data-derived-categorical-value="0"]');
          const presented = term?.getAttribute('data-facet-presented-field');
          return term?.getAttribute('data-facet-requested-field') === key
            && presented !== key
            && term.hasAttribute('inert')
            && term.getAttribute('aria-busy') === 'true'
            && field?.textContent?.trim() === presented
            && value?.getAttribute('data-facet-requested-field') === key
            && value.getAttribute('data-facet-presented-field') === presented;
        }""",
        arg=field_key,
        timeout=timeout_ms,
    )


def categorical_term_identity_violations(
    trace: dict[str, Any],
    field_key: str,
    terminal_state: str,
) -> list[str]:
    violations: list[str] = []
    frames = trace.get("frames", [])
    initial_surfaces = frames[0].get("surfaces", {}) if frames else {}
    initial_value = (initial_surfaces.get("value_input") or {}).get("value")
    initial_weight = (initial_surfaces.get("weight") or {}).get("value")
    for frame in frames:
        surfaces = frame.get("surfaces", {})
        term = surfaces.get("categorical_term") or {}
        term_attrs = term.get("attrs", {})
        term_data = term_attrs.get("data", {})
        requested = term_data.get("data-facet-requested-field")
        presented = term_data.get("data-facet-presented-field")
        field_text = str((surfaces.get("categorical_key") or {}).get("text") or "").strip()
        value = surfaces.get("value_control") or {}
        value_data = value.get("attrs", {}).get("data", {})
        if requested == field_key and presented != field_key:
            if (
                term_attrs.get("ariaBusy") != "true"
                or term_attrs.get("ariaDisabled") != "true"
                or field_text != presented
                or value_data.get("data-facet-presented-field") != presented
                or (surfaces.get("value_input") or {}).get("value") != initial_value
                or (surfaces.get("weight") or {}).get("value") != initial_weight
            ):
                violations.append(
                    f"{field_key} mixed its pending categorical row with the retained field"
                )
        if presented == field_key and value_data.get("data-facet-state") != terminal_state:
            violations.append(
                f"{field_key} presented before terminal categorical state {terminal_state}"
            )
    return sorted(set(violations))


def _identity_violations(
    trace: dict[str, Any],
    metric_key: str,
    terminal_state: str,
) -> list[str]:
    violations: list[str] = []
    for frame in trace.get("frames", []):
        surfaces = frame.get("surfaces", {})
        term = surfaces.get("numeric_term") or {}
        selector = surfaces.get("numeric_selector") or {}
        term_attrs = term.get("attrs", {})
        term_data = term_attrs.get("data", {})
        presented = term_data.get("data-facet-presented-field")
        requested = term_data.get("data-facet-requested-field")
        histogram = surfaces.get("numeric_histogram") or {}
        histogram_data = histogram.get("attrs", {}).get("data", {})
        histogram_state = (
            (surfaces.get("numeric_histogram_content") or {})
            .get("attrs", {})
            .get("data", {})
            .get("data-facet-state")
        )
        selector_text = str(selector.get("text") or "").strip()
        if requested == metric_key and presented != metric_key:
            if (
                term_attrs.get("inert") is not True
                or term_attrs.get("ariaBusy") != "true"
                or term_attrs.get("ariaDisabled") != "true"
                or selector_text != presented
                or histogram_data.get("data-facet-presented-field") != presented
                or histogram_state == "pending"
            ):
                violations.append(
                    f"{metric_key} mixed its pending numeric row with the retained metric"
                )
        if requested == metric_key and presented == metric_key:
            if (
                term_attrs.get("inert") is True
                or term_attrs.get("ariaBusy") is not None
                or selector_text != metric_key
                or histogram_data.get("data-facet-presented-field") != metric_key
                or histogram_state != terminal_state
            ):
                violations.append(
                    f"{metric_key} presented before terminal numeric state {terminal_state}"
                )
    return sorted(set(violations))


def _exercise_numeric_case(
    page: Any,
    *,
    metric_key: str,
    terminal_state: str,
    facet_config: dict[str, Any],
    max_delta_px: float,
    timeout_ms: float,
) -> dict[str, Any]:
    configure_facets(
        page,
        delays=facet_config.get("delays", {}),
        emptyFields=[],
        explicitEmptyFields=facet_config.get("explicitEmptyFields", []),
        errorFields=facet_config.get("errorFields", []),
    )
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase=f"derived_numeric_{terminal_state}",
        selectors=_SELECTORS,
    )
    _select_numeric_metric(page, metric_key)
    _wait_for_retained_metric(page, metric_key, timeout_ms)
    _wait_for_terminal_metric(page, metric_key, terminal_state, timeout_ms)
    page.wait_for_timeout(80)
    trace = stop_painted_frame_trace(page)
    summary = summarize_trace(
        trace,
        anchor_names=("numeric_histogram",),
        required_names=tuple(_SELECTORS),
        max_delta_px=max_delta_px,
    )
    summary["violations"].extend(_identity_violations(trace, metric_key, terminal_state))
    if terminal_state == "error":
        score_state = page.locator(
            '[data-derived-numeric-histogram-slot="score-preview"] '
            '[data-derived-metric-histogram]'
        ).get_attribute("data-facet-state")
        if score_state != "error":
            summary["violations"].append(
                f"source facet error did not terminate the score preview: {score_state!r}"
            )
    name = page.locator("[data-derived-score-name]").input_value()
    weight = page.locator('[data-derived-numeric-weight="0"]').input_value()
    if name != "draft-survives" or weight != "7":
        summary["violations"].append(
            f"{metric_key} facet transition reset the active Derived draft"
        )
    return summary


def _exercise_formula_transition(
    page: Any,
    max_delta_px: float,
    timeout_ms: float,
) -> dict[str, Any]:
    configure_facets(page, delays={}, emptyFields=[], explicitEmptyFields=[], errorFields=[])
    _select_numeric_metric(page, "quality_score")
    _wait_for_terminal_metric(page, "quality_score", "ready", timeout_ms)

    target = "zz_probe_metric_26"
    configure_facets(
        page,
        delays={target: 450},
        emptyFields=[],
        explicitEmptyFields=[],
        errorFields=[],
    )
    page.locator("[data-derived-formula-code]").fill(
        f"draft_formula = 0 + 7*{target}"
    )
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase="derived_formula_numeric_transition",
        selectors=_SELECTORS,
    )
    page.locator("[data-derived-formula-apply]").evaluate("button => button.click()")
    _wait_for_retained_metric(page, target, timeout_ms)
    _wait_for_terminal_metric(page, target, "ready", timeout_ms)
    page.wait_for_timeout(80)
    trace = stop_painted_frame_trace(page)
    summary = summarize_trace(
        trace,
        anchor_names=("numeric_term", "numeric_histogram"),
        required_names=tuple(_SELECTORS),
        max_delta_px=max_delta_px,
    )
    summary["violations"].extend(_identity_violations(trace, target, "ready"))
    name = page.locator("[data-derived-score-name]").input_value()
    weight = page.locator('[data-derived-numeric-weight="0"]').input_value()
    if name != "draft_formula" or weight != "7":
        summary["violations"].append(
            f"formula application produced unexpected draft values: {name!r}, {weight!r}"
        )
    request_count = int(page.evaluate(
        """() => {
          window.__lensletDerivedScopeNode = document.querySelector('[data-derived-score-card]');
          return window.__lensletFacetController.requests.length;
        }"""
    ))
    page.evaluate("() => { window.location.hash = '#/metrics'; }")
    _wait_for_scope_presentation(page, "/metrics", timeout_ms)
    page.wait_for_function(
        """expected => window.__lensletFacetController.requests.slice(expected.count)
          .some(request => request.metricFields.includes(expected.key))""",
        arg={"count": request_count, "key": target},
        timeout=timeout_ms,
    )
    _wait_for_terminal_metric(page, target, "ready", timeout_ms)
    scope_state = _read_scope_draft_state(page)
    if scope_state != {
        "sameNode": True,
        "name": "draft_formula",
        "weight": "7",
        "metric": target,
    }:
        summary["violations"].append(
            f"compatible folder navigation reset the Derived draft: {scope_state!r}"
        )
    page.evaluate("() => { window.location.hash = '#/'; }")
    _wait_for_scope_presentation(page, "/", timeout_ms)
    _wait_for_terminal_metric(page, target, "ready", timeout_ms)
    return_scope_state = _read_scope_draft_state(page)
    if return_scope_state != {
        "sameNode": True,
        "name": "draft_formula",
        "weight": "7",
        "metric": target,
    }:
        summary["violations"].append(
            f"return folder navigation reset the Derived draft: {return_scope_state!r}"
        )
    summary["scope_draft"] = {
        "forward": scope_state,
        "return": return_scope_state,
    }
    page.evaluate("() => { delete window.__lensletDerivedScopeNode; }")
    return summary


def exercise_derived_numeric_presentations(
    page: Any,
    max_delta_px: float,
    timeout_ms: float,
) -> dict[str, Any]:
    cases = {
        terminal_state: _exercise_numeric_case(
            page,
            metric_key=metric_key,
            terminal_state=terminal_state,
            facet_config=facet_config,
            max_delta_px=max_delta_px,
            timeout_ms=timeout_ms,
        )
        for metric_key, facet_config, terminal_state in (
            ("zz_probe_metric_29", {"delays": {"zz_probe_metric_29": 450}}, "ready"),
            (
                "zz_probe_metric_28",
                {
                    "delays": {"zz_probe_metric_28": 180},
                    "explicitEmptyFields": ["zz_probe_metric_28"],
                },
                "empty",
            ),
            (
                "zz_probe_metric_27",
                {"delays": {"zz_probe_metric_27": 80}, "errorFields": ["zz_probe_metric_27"]},
                "error",
            ),
        )
    }
    formula = _exercise_formula_transition(page, max_delta_px, timeout_ms)
    return {
        "violations": [
            violation
            for summary in (*cases.values(), formula)
            for violation in summary["violations"]
        ],
        "cases": cases,
        "formula_apply": formula,
        "rectangle_deltas_px": formula.get("rectangle_deltas_px", {}),
    }
