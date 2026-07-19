"""Live schema-transition evidence for the Metrics painted-frame probe."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from scripts.browser.gui_jitter.painted_frames import (
    arm_painted_frame_attribute_change,
    arm_painted_frame_click_action,
    start_painted_frame_trace,
    stop_painted_frame_trace,
)

SCHEMA_SELECTORS = {
    "metrics_panel": "[data-metrics-panel]",
    "metric_virtual_list": '[data-virtual-field-list="metric"]',
}


def exercise_metric_schema_transitions(page: Any, timeout_ms: float) -> dict[str, Any]:
    schema_a = _metric_schema(page)
    bottom_initial = _scroll_metric_list_to_bottom(page, timeout_ms)
    page.get_by_role("button", name="Derived Score").click()
    _wait_for_tool(page, "derived", timeout_ms)
    hidden_b_trace = _trace_action(
        page,
        "schema-hidden-b",
        lambda: page.locator("[data-derived-score-apply]").click(),
        lambda: _wait_for_derived_schema(page, len(schema_a) + 1, timeout_ms),
        arm_schema_change=True,
    )
    schema_b = _metric_schema(page)
    transitions = {
        "hidden_b": _schema_transition_summary(hidden_b_trace, schema_b, False),
        "reopen_b": _trace_tool_reopen(page, schema_b, timeout_ms),
    }
    transitions["visible_a_return"] = _trace_schema_action(
        page,
        schema_a,
        True,
        "schema-visible-a-return",
        lambda: page.locator("[data-derived-score-clear]").evaluate("button => button.click()"),
        timeout_ms,
    )
    bottom_before_hidden = _scroll_metric_list_to_bottom(page, timeout_ms)
    page.get_by_role("button", name="Folders").click()
    _wait_for_tool(page, "folders", timeout_ms)
    transitions["hidden_b_again"] = _trace_schema_action(
        page,
        schema_b,
        False,
        "schema-hidden-b-again",
        lambda: page.locator("[data-derived-score-apply]").evaluate("button => button.click()"),
        timeout_ms,
    )
    transitions["hidden_a_return"] = _trace_schema_action(
        page,
        schema_a,
        False,
        "schema-hidden-a-return",
        lambda: page.locator("[data-derived-score-clear]").evaluate("button => button.click()"),
        timeout_ms,
    )
    transitions["reopen_a"] = _trace_tool_reopen(page, schema_a, timeout_ms)
    return {
        "schema_a": schema_a,
        "schema_b": schema_b,
        "bottom_initial": bottom_initial,
        "bottom_before_hidden": bottom_before_hidden,
        "transitions": transitions,
        "violations": [
            f"{name}: {violation}"
            for name, summary in transitions.items()
            for violation in summary["violations"]
        ],
    }


def _trace_schema_action(
    page: Any,
    schema: list[str],
    expected_visible: bool,
    action_id: str,
    action: Callable[[], Any],
    timeout_ms: float,
) -> dict[str, Any]:
    trace = _trace_action(
        page,
        action_id,
        action,
        lambda: _wait_for_schema(page, schema, timeout_ms),
        arm_schema_change=True,
    )
    return _schema_transition_summary(trace, schema, expected_visible)


def _trace_tool_reopen(page: Any, schema: list[str], timeout_ms: float) -> dict[str, Any]:
    trace = _trace_action(
        page,
        "schema-reopen",
        lambda: page.get_by_role("button", name="Metrics and Filters").click(),
        lambda: _wait_for_tool(page, "metrics", timeout_ms),
    )
    return _schema_transition_summary(trace, schema, True)


def _trace_action(
    page: Any,
    action_id: str,
    action: Callable[[], Any],
    wait: Callable[[], Any],
    *,
    arm_schema_change: bool = False,
) -> dict[str, Any]:
    start_painted_frame_trace(
        page,
        page_id="metrics",
        phase=action_id,
        selectors=SCHEMA_SELECTORS,
    )
    if arm_schema_change:
        arm_painted_frame_attribute_change(
            page,
            action_id=action_id,
            expected_path="metrics",
            selector=SCHEMA_SELECTORS["metrics_panel"],
            attribute="data-metric-field-schema",
        )
    else:
        arm_painted_frame_click_action(page, action_id=action_id, expected_path="metrics")
    action()
    wait()
    page.wait_for_timeout(80)
    return stop_painted_frame_trace(page)


def _wait_for_schema(page: Any, schema: list[str], timeout_ms: float) -> None:
    page.wait_for_function(
        "expected => document.querySelector('[data-metrics-panel]')?.getAttribute('data-metric-field-schema') === expected",
        arg=json.dumps(schema, separators=(",", ":")),
        timeout=timeout_ms,
    )


def _wait_for_derived_schema(page: Any, length: int, timeout_ms: float) -> None:
    page.wait_for_function(
        """expectedLength => {
          const raw = document.querySelector('[data-metrics-panel]')?.getAttribute('data-metric-field-schema');
          const schema = raw ? JSON.parse(raw) : [];
          return schema.length === expectedLength && schema.some(key => key.startsWith('@derived/'));
        }""",
        arg=length,
        timeout=timeout_ms,
    )


def _metric_schema(page: Any) -> list[str]:
    raw = page.locator("[data-metrics-panel]").get_attribute("data-metric-field-schema")
    value = json.loads(raw or "[]")
    if not isinstance(value, list) or not all(isinstance(key, str) for key in value):
        raise RuntimeError("Metrics panel did not expose a valid field schema")
    return value


def _wait_for_tool(page: Any, tool: str, timeout_ms: float) -> None:
    page.wait_for_function(
        "tool => document.querySelector(`[data-left-tool-panel=\"${tool}\"]`)?.hidden === false",
        arg=tool,
        timeout=timeout_ms,
    )


def _scroll_metric_list_to_bottom(page: Any, timeout_ms: float) -> dict[str, Any]:
    boundary = _metric_schema(page)[-1]
    page.locator('[data-virtual-field-list="metric"]').evaluate(
        "list => { list.scrollTop = list.scrollHeight; }"
    )
    page.wait_for_function(
        """boundary => {
          const list = document.querySelector('[data-virtual-field-list="metric"]');
          const rendered = JSON.parse(list?.getAttribute('data-rendered-field-keys') || '[]');
          return (list?.scrollTop || 0) > 0 && rendered.includes(boundary);
        }""",
        arg=boundary,
        timeout=timeout_ms,
    )
    return page.evaluate(
        """() => {
          const list = document.querySelector('[data-virtual-field-list="metric"]');
          return {
            scrollTop: list?.scrollTop || 0,
            rendered: JSON.parse(list?.getAttribute('data-rendered-field-keys') || '[]'),
          };
        }"""
    )


def _schema_transition_summary(
    trace: dict[str, Any],
    schema: list[str],
    expected_visible: bool,
) -> dict[str, Any]:
    expected_schema = json.dumps(schema, separators=(",", ":"))
    expected_batch = schema[:24]
    marked: list[dict[str, Any]] = []
    for frame in trace.get("frames", []):
        marker = frame.get("marker") if isinstance(frame, dict) else None
        surfaces = frame.get("surfaces") if isinstance(frame, dict) else None
        if isinstance(marker, dict) and isinstance(surfaces, dict):
            marked.append(frame)
    if not marked:
        return {
            "first_frame": None,
            "frame_count": 0,
            "violations": ["schema action had no post-action painted frame"],
        }
    first = marked[0]["surfaces"]
    field_list = first.get("metric_virtual_list")
    panel = first.get("metrics_panel")
    panel_data = panel.get("attrs", {}).get("data", {}) if isinstance(panel, dict) else {}
    painted_schema = panel_data.get("data-metric-field-schema")
    rendered = _data_json(field_list, "data-rendered-field-keys")
    requested = _data_json(panel, "data-requested-metric-fields")
    scroll_top = field_list.get("scrollTop") if isinstance(field_list, dict) else None
    visible = field_list.get("visible") if isinstance(field_list, dict) else None
    violations: list[str] = []
    if painted_schema != expected_schema:
        violations.append(
            f"earliest post-action frame painted schema {painted_schema!r}, expected {expected_schema!r}"
        )
    if scroll_top != 0:
        violations.append(f"earliest schema frame retained scrollTop={scroll_top!r}")
    if requested != expected_batch:
        violations.append(f"earliest schema frame requested {requested!r}, expected first batch")
    if expected_visible and not rendered:
        violations.append("earliest visible schema frame rendered no fields")
    if rendered and not set(rendered).issubset(requested):
        violations.append(f"earliest schema frame rendered unowned fields: {rendered!r} vs {requested!r}")
    if not expected_visible and rendered:
        violations.append(f"earliest hidden schema frame rendered fields: {rendered!r}")
    if visible is not expected_visible:
        violations.append(f"earliest schema frame visibility was {visible!r}")
    return {
        "first_frame": {
            "scrollTop": scroll_top,
            "rendered": rendered,
            "requested": requested,
            "visible": visible,
        },
        "frame_count": len(marked),
        "violations": violations,
    }


def _data_json(surface: Any, name: str) -> list[str]:
    if not isinstance(surface, dict):
        return []
    raw = surface.get("attrs", {}).get("data", {}).get(name, "[]")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []
