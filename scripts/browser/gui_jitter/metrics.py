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


class MetricsProbeFailure(SmokeFailure):
    """Metrics failure carrying bounded frame evidence for JSON output."""

    def __init__(self, message: str, evidence: dict[str, Any]) -> None:
        super().__init__(message)
        self.evidence = evidence


def _wait_for_metrics_ready(page: Any, timeout_ms: float) -> None:
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
            narrow = _narrow_app_structure(browser, base_url, browser_timeout_ms)
        finally:
            context.close()
            browser.close()

    violations = [
        f"{phase}: {violation}"
        for phase, summary in (("categorical", categorical), ("histogram", histogram))
        for violation in summary["violations"]
    ]
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
        "narrow_390x844_structure": narrow,
        "violations": violations,
    }
    if violations:
        raise MetricsProbeFailure("; ".join(violations), checks)
    maximum_delta = max(
        *categorical["rectangle_deltas_px"].values(),
        *histogram["rectangle_deltas_px"].values(),
        0.0,
    )
    return ProbeResult(
        scenario="metrics",
        max_delta_px=max_delta_px,
        max_anchor_delta_px=maximum_delta,
        checks=checks,
    )
