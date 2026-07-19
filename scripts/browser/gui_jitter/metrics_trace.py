"""Content and ownership analysis for Metrics painted-frame traces."""

from __future__ import annotations

import json
from typing import Any


def requested_field_ownership_violations(surfaces: dict[str, Any]) -> list[str]:
    panel = surfaces.get("metrics_panel")
    panel_data = panel.get("attrs", {}).get("data", {}) if isinstance(panel, dict) else {}
    violations: list[str] = []
    for kind in ("metric", "categorical"):
        field_list = surfaces.get(f"{kind}_virtual_list")
        if not isinstance(field_list, dict) or field_list.get("visible") is not True:
            continue
        list_data = field_list.get("attrs", {}).get("data", {})
        rendered_raw = list_data.get("data-rendered-field-keys", "[]")
        requested_raw = panel_data.get(f"data-requested-{kind}-fields", "[]")
        try:
            rendered = set(json.loads(rendered_raw))
            requested = set(json.loads(requested_raw))
        except (TypeError, ValueError):
            violations.append(f"{kind} field ownership attributes were not valid JSON")
            continue
        if not rendered:
            violations.append(f"visible {kind} virtual list rendered no fields")
            continue
        missing = sorted(rendered - requested)
        if missing:
            violations.append(
                f"rendered {kind} fields lacked first-frame query ownership: {missing!r}"
            )
    return violations


def virtual_card_continuity_violations(
    frames: list[dict[str, Any]],
    *,
    surface_names: tuple[str, ...],
    initially_settled: frozenset[str],
) -> list[str]:
    settled = set(initially_settled)
    violations: list[str] = []
    for frame in frames:
        surfaces = frame.get("surfaces") if isinstance(frame, dict) else None
        if not isinstance(surfaces, dict):
            continue
        for surface_name in surface_names:
            surface = surfaces.get(surface_name)
            if not isinstance(surface, dict) or surface.get("visible") is not True:
                continue
            cards = surface.get("facetCards")
            data = surface.get("attrs", {}).get("data", {})
            try:
                rendered = set(json.loads(data.get("data-rendered-field-keys", "[]")))
            except (TypeError, ValueError):
                violations.append(f"{surface_name} rendered-field keys were not valid JSON")
                continue
            if not isinstance(cards, list):
                violations.append(f"{surface_name} did not record per-card painted state")
                continue
            recorded = {card.get("key") for card in cards if isinstance(card, dict)}
            if recorded != rendered:
                violations.append(
                    f"{surface_name} per-card evidence did not match rendered keys: "
                    f"{sorted(recorded)!r} != {sorted(rendered)!r}"
                )
            for card in cards:
                if not isinstance(card, dict):
                    continue
                key = card.get("key")
                state = card.get("state")
                text = str(card.get("text") or "")
                if not isinstance(key, str):
                    violations.append(f"{surface_name} recorded a card without a key")
                    continue
                if card.get("requested") != key or card.get("presented") != key:
                    violations.append(f"{surface_name} mixed requested/presented card {card!r}")
                if key in settled and (state == "pending" or "Loading values" in text):
                    violations.append(f"settled Show-all field {key!r} regressed to loading")
                if card.get("ariaBusy") == "true" and (
                    card.get("ariaDisabled") != "true" or card.get("inert") is not True
                ):
                    violations.append(f"retained Show-all field {key!r} was not disabled and inert")
                if state in {"ready", "empty", "error"}:
                    settled.add(key)
    return list(dict.fromkeys(violations))


def virtual_field_reset_summary(
    trace: dict[str, Any],
    *,
    previous_reset_key: str,
    expectations: tuple[tuple[str, str, str], ...],
) -> dict[str, Any]:
    states = {field: [] for _, field, _ in expectations}
    violations: list[str] = []
    for frame in trace.get("frames", []):
        surfaces = frame.get("surfaces") if isinstance(frame, dict) else None
        panel = surfaces.get("metrics_panel") if isinstance(surfaces, dict) else None
        panel_data = panel.get("attrs", {}).get("data", {}) if isinstance(panel, dict) else {}
        reset_key = panel_data.get("data-presentation-reset-key")
        if not reset_key or reset_key == previous_reset_key:
            continue
        for surface_name, field, _ in expectations:
            surface = surfaces.get(surface_name) if isinstance(surfaces, dict) else None
            cards = surface.get("facetCards", []) if isinstance(surface, dict) else []
            card = next(
                (value for value in cards if isinstance(value, dict) and value.get("key") == field),
                None,
            )
            if card is not None:
                states[field].append(card)

    for _, field, terminal_text in expectations:
        field_states = states[field]
        if not field_states:
            violations.append(f"virtual hard reset recorded no frames for {field!r}")
            continue
        first = field_states[0]
        if (
            first.get("state") != "pending"
            or "Loading values" not in str(first.get("text") or "")
            or first.get("requested") != field
            or first.get("presented") != field
            or first.get("ariaBusy") == "true"
            or first.get("inert") is True
        ):
            violations.append(f"virtual hard reset retained or mixed {field!r}: {first!r}")
        if not any(
            state.get("state") in {"ready", "empty", "error"}
            and terminal_text in str(state.get("text") or "")
            for state in field_states
        ):
            violations.append(f"virtual hard reset never painted terminal {field!r}")
    return {
        "states": states,
        "violations": list(dict.fromkeys(violations)),
    }


def _rect_delta(baseline: dict[str, Any], candidate: dict[str, Any]) -> float:
    return max(
        abs(float(baseline[key]) - float(candidate[key]))
        for key in ("top", "left", "width", "height")
    )


def summarize_trace(
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


def target_field_trace_summary(
    trace: dict[str, Any],
    *,
    action_id: str,
    anchor_names: tuple[str, ...],
    card_attribute: str,
    card_surface: str,
    previous_field: str,
    field: str,
    field_label: str,
    required_names: tuple[str, ...],
    selector_surface: str,
    terminal_state: str,
    forbidden_texts: tuple[str, ...],
    expected_text: str,
    max_delta_px: float,
) -> dict[str, Any]:
    summary = summarize_trace(
        trace,
        anchor_names=anchor_names,
        required_names=required_names,
        max_delta_px=max_delta_px,
    )
    target_card_texts: list[str] = []
    post_action_frames = 0
    first_post_action_frame: dict[str, Any] | None = None
    for frame in trace.get("frames", []):
        marker = frame.get("marker") if isinstance(frame, dict) else None
        if not isinstance(marker, dict) or marker.get("actionId") != action_id:
            continue
        post_action_frames += 1
        surfaces = frame.get("surfaces") if isinstance(frame, dict) else None
        if not isinstance(surfaces, dict):
            continue
        selector = surfaces.get(selector_surface)
        card = surfaces.get(card_surface)
        selector_text = str(selector.get("text") or "") if isinstance(selector, dict) else ""
        card_text = str(card.get("text") or "") if isinstance(card, dict) else ""
        selector_field = selector_text.strip()
        card_data = card.get("attrs", {}).get("data", {}) if isinstance(card, dict) else {}
        card_field = card_data.get(card_attribute) if isinstance(card_data, dict) else None
        card_state = card_data.get("data-facet-state") if isinstance(card_data, dict) else None
        frame_state = {
            "selector": selector_field,
            "card": card_field,
            "state": card_state,
            "text": card_text,
        }
        if first_post_action_frame is None:
            first_post_action_frame = frame_state
        complete_previous = (
            selector_field == previous_field
            and card_field == previous_field
            and card_state != "pending"
            and "Loading values" not in card_text
        )
        complete_target = (
            selector_field == field
            and card_field == field
            and card_state == terminal_state
            and expected_text in card_text
            and "Loading values" not in card_text
        )
        if not complete_previous and not complete_target:
            summary["violations"].append(
                f"{field} painted an incomplete or mixed field frame: {frame_state!r}"
            )
        if selector_text.strip() == field:
            target_card_texts.append(card_text)
    if post_action_frames == 0:
        summary["violations"].append(f"{field_label} has no earliest post-action painted frame")
    if not target_card_texts:
        summary["violations"].append(f"{field_label} never owned a painted frame")
    if any(text in card_text for text in forbidden_texts for card_text in target_card_texts):
        summary["violations"].append(f"{field_label} painted data from the previous field")
    if not any(expected_text in text for text in target_card_texts):
        summary["violations"].append(f"{field_label} never painted {expected_text!r}")
    summary["post_action_frame_count"] = post_action_frames
    summary["first_post_action_frame"] = first_post_action_frame
    summary["target_card_texts"] = sorted(set(target_card_texts))
    summary["violations"] = list(dict.fromkeys(summary["violations"]))
    return summary


def single_field_reset_summary(
    trace: dict[str, Any],
    *,
    previous_reset_key: str,
) -> dict[str, Any]:
    frames: list[dict[str, Any]] = []
    for frame in trace.get("frames", []):
        surfaces = frame.get("surfaces") if isinstance(frame, dict) else None
        panel = surfaces.get("metrics_panel") if isinstance(surfaces, dict) else None
        panel_data = panel.get("attrs", {}).get("data", {}) if isinstance(panel, dict) else {}
        reset_key = panel_data.get("data-presentation-reset-key")
        if reset_key and reset_key != previous_reset_key:
            frames.append(frame)

    violations: list[str] = []
    states: list[dict[str, Any]] = []
    for frame in frames:
        surfaces = frame["surfaces"]
        metric_selector = surfaces.get("metric_selector", {})
        metric_card = surfaces.get("metric_card", {})
        categorical_selector = surfaces.get("categorical_selector", {})
        categorical_card = surfaces.get("categorical_card", {})
        metric_data = metric_card.get("attrs", {}).get("data", {})
        categorical_data = categorical_card.get("attrs", {}).get("data", {})
        state = {
            "metricSelector": str(metric_selector.get("text") or "").strip(),
            "metricField": metric_data.get("data-metric-card-host"),
            "metricState": metric_data.get("data-facet-state"),
            "metricText": str(metric_card.get("text") or ""),
            "categoricalSelector": str(categorical_selector.get("text") or "").strip(),
            "categoricalField": categorical_data.get("data-categorical-card"),
            "categoricalState": categorical_data.get("data-facet-state"),
            "categoricalText": str(categorical_card.get("text") or ""),
        }
        states.append(state)
        if state["metricSelector"] != "quality_score" or state["metricField"] != "quality_score":
            violations.append(f"hard reset mixed metric identity: {state!r}")
        if state["categoricalSelector"] != "review_group" or state["categoricalField"] != "review_group":
            violations.append(f"hard reset mixed categorical identity: {state!r}")
        metric_pending = (
            state["metricState"] == "pending"
            and "Loading values for this metric" in state["metricText"]
            and "0.000" not in state["metricText"]
            and "1.000" not in state["metricText"]
        )
        metric_target = (
            state["metricState"] == "ready"
            and "10.00" in state["metricText"]
            and "20.00" in state["metricText"]
        )
        if not metric_pending and not metric_target:
            violations.append(f"hard reset retained or mixed the metric snapshot: {state!r}")
        categorical_pending = (
            state["categoricalState"] == "pending"
            and "Loading values for this field" in state["categoricalText"]
            and "review-0" not in state["categoricalText"]
        )
        categorical_target = (
            state["categoricalState"] == "empty"
            and "No values found for this field" in state["categoricalText"]
        )
        if not categorical_pending and not categorical_target:
            violations.append(f"hard reset retained or mixed the categorical snapshot: {state!r}")

    if not states:
        violations.append("hard reset produced no target-owned painted frame")
    elif states[0]["metricState"] != "pending" or states[0]["categoricalState"] != "pending":
        violations.append(f"hard reset first target-owned frame was not neutral: {states[0]!r}")
    if not any(state["metricState"] == "ready" for state in states):
        violations.append("hard reset never painted the terminal metric target")
    if not any(state["categoricalState"] == "empty" for state in states):
        violations.append("hard reset never painted the terminal categorical target")
    return {
        "frame_count": len(frames),
        "first_frame": states[0] if states else None,
        "terminal_frame": states[-1] if states else None,
        "states": states,
        "violations": list(dict.fromkeys(violations)),
    }
