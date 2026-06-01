from __future__ import annotations

from typing import Any

from scripts.browser.viewer_probe.config import DEFAULT_DRAGS, EDGE_DRAGS

MIN_RECOVERABLE_IMAGE_PX = 24
TRANSFORM_TRANSLATE_TOLERANCE_PX = 0.5
TRANSFORM_SCALE_TOLERANCE = 0.001
TRANSFORM_BOUNDS_TOLERANCE_PX = 1.5
ZOOM_CONTROL_NAMES = {"wheel", "toolbar", "pinch"}


def transform_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    before_matrix = before.get("matrix")
    after_matrix = after.get("matrix")
    if not isinstance(before_matrix, dict) or not isinstance(after_matrix, dict):
        return before.get("transform") != after.get("transform")
    return (
        _matrix_delta(before_matrix, after_matrix, "e") > TRANSFORM_TRANSLATE_TOLERANCE_PX
        or _matrix_delta(before_matrix, after_matrix, "f") > TRANSFORM_TRANSLATE_TOLERANCE_PX
        or _matrix_delta(before_matrix, after_matrix, "a") > TRANSFORM_SCALE_TOLERANCE
        or _matrix_delta(before_matrix, after_matrix, "d") > TRANSFORM_SCALE_TOLERANCE
    )


def interactions_acceptance_failures(raw_scenarios: Any) -> list[str]:
    if not isinstance(raw_scenarios, dict):
        return ["interactions: missing interaction scenarios"]

    failures: list[str] = []
    failures.extend(
        transform_probe_failures(
            raw_scenarios.get("defaultFitPan"),
            expected_names={name for name, _, _ in DEFAULT_DRAGS},
            context="default-fit drag",
        )
    )
    failures.extend(
        transform_probe_failures(
            raw_scenarios.get("zoomEdgePan"),
            expected_names={name for name, _, _ in EDGE_DRAGS},
            context="edge drag",
            drag_key="additionalDrag",
        )
    )
    failures.extend(zoom_control_failures(raw_scenarios.get("zoomControls")))
    failures.extend(click_acceptance_failures(raw_scenarios.get("clicks")))
    return failures


def click_acceptance_failures(clicks: Any) -> list[str]:
    if not isinstance(clicks, dict):
        return ["interactions: missing click scenarios"]
    failures: list[str] = []
    failures.extend(_click_closed_failures(clicks, ("singleClickImage", "singleClickBackground"), should_close=False))
    failures.extend(_click_closed_failures(clicks, ("doubleClickImage", "doubleClickBackground"), should_close=True))
    failures.extend(_guarded_double_click_failures(clicks, ("doubleClickAfterDrag", "doubleClickToolbarZoom")))
    return failures


def zoom_control_failures(raw_items: Any) -> list[str]:
    by_name, failures = _scenario_map(raw_items, expected_names=ZOOM_CONTROL_NAMES, context="zoom control")
    if by_name is None:
        return failures
    for name in sorted(ZOOM_CONTROL_NAMES & set(by_name)):
        failures.extend(_zoom_control_item_failures(name, by_name[name]))
    return failures


def transform_probe_failures(
    raw_items: Any,
    *,
    expected_names: set[str],
    context: str,
    drag_key: str = "drag",
) -> list[str]:
    by_name, failures = _scenario_map(raw_items, expected_names=expected_names, context=context)
    if by_name is None:
        return failures
    for name in sorted(expected_names & set(by_name)):
        failures.extend(_transform_probe_item_failures(name, by_name[name], context, drag_key))
    return failures


def strict_initial_transform_failures(name: str, state: Any) -> list[str]:
    if transform_outside_bounds(state, "strict"):
        return [f"interactions:{name}: initial ready transform was not strict fitted"]
    return []


def drag_acceptance_failures(name: str, drag: dict[str, Any], context: str) -> list[str]:
    failures = _drag_changed_failures(name, drag, context)
    matrix_pair = _drag_matrix_pair(name, drag)
    if matrix_pair is None:
        return [*failures, f"interactions:{name}: missing transform matrices"]

    before_matrix, after_matrix = matrix_pair
    failures.extend(_drag_direction_failures(name, drag, before_matrix, after_matrix))
    failures.extend(_drag_bounds_failures(name, drag.get("after")))
    return failures


def transform_outside_bounds(state: Any, bounds_name: str) -> bool:
    matrix, transform_bounds = _transform_state_parts(state)
    if matrix is None or transform_bounds is None:
        return True
    min_key, max_key = _bound_keys(bounds_name)
    return any(
        _axis_outside_bounds(matrix, transform_bounds, axis=axis, matrix_key=matrix_key, min_key=min_key, max_key=max_key)
        for axis, matrix_key in (("x", "e"), ("y", "f"))
    )


def image_still_recoverable(state: Any) -> bool:
    image_rect, dialog_rect = _rect_pair(state)
    if image_rect is None or dialog_rect is None:
        return False
    visible_width = _axis_overlap(image_rect, dialog_rect, low_key="left", high_key="right")
    visible_height = _axis_overlap(image_rect, dialog_rect, low_key="top", high_key="bottom")
    return visible_width >= MIN_RECOVERABLE_IMAGE_PX and visible_height >= MIN_RECOVERABLE_IMAGE_PX


def _matrix_delta(before_matrix: dict[str, Any], after_matrix: dict[str, Any], key: str) -> float:
    return abs(float(before_matrix.get(key, 0)) - float(after_matrix.get(key, 0)))


def _scenario_map(raw_items: Any, *, expected_names: set[str], context: str) -> tuple[dict[str, dict[str, Any]] | None, list[str]]:
    if not isinstance(raw_items, list) or not raw_items:
        return None, [f"interactions: missing {context} scenarios"]
    by_name = {item.get("name"): item for item in raw_items if isinstance(item, dict)}
    missing = sorted(expected_names - set(by_name))
    failures = [f"interactions: missing {context} scenarios {missing}"] if missing else []
    return by_name, failures


def _click_closed_failures(clicks: dict[str, Any], names: tuple[str, ...], *, should_close: bool) -> list[str]:
    failures: list[str] = []
    for name in names:
        result = clicks.get(name)
        if result is None:
            failures.append(f"interactions:{name}: missing click result")
        elif bool(result.get("closed")) != should_close:
            action = "did not close" if should_close else "closed"
            failures.append(f"interactions:{name}: {'double' if should_close else 'single'} click {action} viewer")
    return failures


def _guarded_double_click_failures(clicks: dict[str, Any], names: tuple[str, ...]) -> list[str]:
    failures: list[str] = []
    for name in names:
        result = clicks.get(name)
        if result is None:
            failures.append(f"interactions:{name}: missing guarded double-click result")
        elif result.get("closed"):
            failures.append(f"interactions:{name}: guarded double click closed viewer")
    return failures


def _zoom_control_item_failures(name: str, item: dict[str, Any]) -> list[str]:
    failures = _zoom_setup_failures(name, item.get("prePan"))
    zoom = item.get("zoom")
    if not isinstance(zoom, dict):
        return [*failures, f"interactions:{name}: missing zoom control result"]
    before = zoom.get("before")
    after = zoom.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        return [*failures, f"interactions:{name}: missing zoom control before/after state"]
    failures.extend(_zoom_transform_failures(name, before, after))
    return failures


def _zoom_setup_failures(name: str, pre_pan: Any) -> list[str]:
    if isinstance(pre_pan, dict) and pre_pan.get("changed"):
        return []
    return [f"interactions:{name}: setup pan did not move before zoom control"]


def _zoom_transform_failures(name: str, before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not transform_changed(before, after):
        failures.append(f"interactions:{name}: zoom control did not change transform")
    if transform_outside_bounds(after, "slack"):
        failures.append(f"interactions:{name}: zoom control exceeded computed slack bounds")
    if not image_still_recoverable(after):
        failures.append(f"interactions:{name}: zoom control moved image outside recoverable bounds")
    return failures


def _transform_probe_item_failures(name: str, item: dict[str, Any], context: str, drag_key: str) -> list[str]:
    drag = item.get(drag_key)
    if not isinstance(drag, dict):
        return [f"interactions:{name}: missing {drag_key} result"]
    failures: list[str] = []
    if context == "default-fit drag":
        failures.extend(strict_initial_transform_failures(name, drag.get("before")))
    if context == "edge drag" and not item.get("reachedStrictEdge"):
        failures.append(f"interactions:{name}: did not reach the old strict edge before additional drag")
    failures.extend(drag_acceptance_failures(name, drag, context))
    return failures


def _drag_changed_failures(name: str, drag: dict[str, Any], context: str) -> list[str]:
    if drag.get("changed"):
        return []
    return [f"interactions:{name}: {context} did not move"]


def _drag_matrix_pair(name: str, drag: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    _ = name
    before = drag.get("before")
    after = drag.get("after")
    before_matrix = before.get("matrix") if isinstance(before, dict) else None
    after_matrix = after.get("matrix") if isinstance(after, dict) else None
    if not isinstance(before_matrix, dict) or not isinstance(after_matrix, dict):
        return None
    return before_matrix, after_matrix


def _drag_direction_failures(
    name: str,
    drag: dict[str, Any],
    before_matrix: dict[str, Any],
    after_matrix: dict[str, Any],
) -> list[str]:
    dx = float(drag.get("dx") or 0)
    dy = float(drag.get("dy") or 0)
    delta_x = float(after_matrix.get("e") or 0) - float(before_matrix.get("e") or 0)
    delta_y = float(after_matrix.get("f") or 0) - float(before_matrix.get("f") or 0)
    if abs(dx) >= abs(dy):
        return _axis_drag_failure(name, axis="x", requested=dx, observed=delta_x)
    return _axis_drag_failure(name, axis="y", requested=dy, observed=delta_y)


def _axis_drag_failure(name: str, *, axis: str, requested: float, observed: float) -> list[str]:
    moved_opposite = (requested < 0 and observed >= 0) or (requested > 0 and observed <= 0)
    if abs(observed) <= TRANSFORM_TRANSLATE_TOLERANCE_PX or moved_opposite:
        return [f"interactions:{name}: {axis} movement {observed:.2f} does not follow drag {requested:.2f}"]
    return []


def _drag_bounds_failures(name: str, after: Any) -> list[str]:
    failures: list[str] = []
    if not image_still_recoverable(after):
        failures.append(f"interactions:{name}: image moved outside recoverable viewer bounds")
    if transform_outside_bounds(after, "slack"):
        failures.append(f"interactions:{name}: image transform exceeded computed slack bounds")
    return failures


def _transform_state_parts(state: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(state, dict):
        return None, None
    matrix = state.get("matrix")
    transform_bounds = state.get("transformBounds")
    if not isinstance(matrix, dict) or not isinstance(transform_bounds, dict):
        return None, None
    return matrix, transform_bounds


def _bound_keys(bounds_name: str) -> tuple[str, str]:
    return {
        "strict": ("strictMin", "strictMax"),
        "slack": ("slackMin", "slackMax"),
    }[bounds_name]


def _axis_outside_bounds(
    matrix: dict[str, Any],
    transform_bounds: dict[str, Any],
    *,
    axis: str,
    matrix_key: str,
    min_key: str,
    max_key: str,
) -> bool:
    bounds = transform_bounds.get(axis)
    value = matrix.get(matrix_key)
    if not isinstance(bounds, dict) or not isinstance(value, (int, float)):
        return True
    return (
        float(value) < float(bounds.get(min_key, 0)) - TRANSFORM_BOUNDS_TOLERANCE_PX
        or float(value) > float(bounds.get(max_key, 0)) + TRANSFORM_BOUNDS_TOLERANCE_PX
    )


def _rect_pair(state: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(state, dict):
        return None, None
    image_rect = state.get("imageRect")
    dialog_rect = state.get("dialogRect")
    if not isinstance(image_rect, dict) or not isinstance(dialog_rect, dict):
        return None, None
    return image_rect, dialog_rect


def _axis_overlap(image_rect: dict[str, Any], dialog_rect: dict[str, Any], *, low_key: str, high_key: str) -> float:
    low = max(float(image_rect.get(low_key) or 0), float(dialog_rect.get(low_key) or 0))
    high = min(float(image_rect.get(high_key) or 0), float(dialog_rect.get(high_key) or 0))
    return high - low
