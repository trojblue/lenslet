from __future__ import annotations

from typing import Any

from scripts.browser.viewer_probe.config import DEFAULT_DRAGS, EDGE_DRAGS, ViewerProbeFailure
from scripts.browser.viewer_probe.interaction_checks import transform_changed
from scripts.browser.viewer_probe.page import (
    close_viewer,
    open_first_viewer,
    read_viewer_state,
    seed_storage_script,
    wait_for_shell,
    wait_for_viewer_closed,
    wait_for_viewer_ready,
)


def drag_viewer_image(page: Any, dx: int, dy: int) -> dict[str, Any]:
    before = read_viewer_state(page)
    if before.get("missing"):
        return {"before": before, "after": before, "changed": False, "error": "missing viewer image"}
    image_rect = before["imageRect"]
    dialog_rect = before["dialogRect"]
    matrix = before.get("matrix")
    scale = float(matrix.get("a", 1)) if isinstance(matrix, dict) else 1
    if scale > 1:
        start_x = float(dialog_rect["left"]) + float(dialog_rect["width"]) / 2
        start_y = float(dialog_rect["top"]) + float(dialog_rect["height"]) / 2
    else:
        start_x = min(
            max(float(image_rect["left"]) + float(image_rect["width"]) / 2, float(dialog_rect["left"]) + 8),
            float(dialog_rect["right"]) - 8,
        )
        start_y = min(
            max(float(image_rect["top"]) + float(image_rect["height"]) / 2, float(dialog_rect["top"]) + 8),
            float(dialog_rect["bottom"]) - 8,
        )
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x + dx, start_y + dy, steps=10)
    page.mouse.up()
    page.wait_for_timeout(80)
    after = read_viewer_state(page)
    changed = transform_changed(before, after)
    return {
        "dx": dx,
        "dy": dy,
        "start": {"x": start_x, "y": start_y},
        "before": before,
        "after": after,
        "changed": changed,
    }


def zoom_viewer_with_wheel(page: Any) -> dict[str, Any]:
    before = read_viewer_state(page)
    if before.get("missing"):
        return {"before": before, "after": before, "steps": 0}
    rect = before["imageRect"]
    x = float(rect["left"]) + float(rect["width"]) / 2
    y = float(rect["top"]) + float(rect["height"]) / 2
    page.mouse.move(x, y)
    for _ in range(5):
        page.mouse.wheel(0, -420)
        page.wait_for_timeout(40)
    return {"before": before, "after": read_viewer_state(page), "steps": 5}


def zoom_viewer_with_toolbar(page: Any, percent: int = 240) -> dict[str, Any]:
    before = read_viewer_state(page)
    page.locator('input[aria-label="Zoom level"]').evaluate(
        """(el, value) => {
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
          if (setter) setter.call(el, String(value));
          else el.value = String(value);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        percent,
    )
    page.wait_for_timeout(120)
    return {"before": before, "after": read_viewer_state(page), "percent": percent}


def zoom_viewer_with_pinch(page: Any) -> dict[str, Any]:
    before = read_viewer_state(page)
    page.evaluate(
        """() => {
          const dialog = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
          const image = dialog?.querySelector('img[data-viewer-image="full"]');
          if (!(dialog instanceof HTMLElement) || !(image instanceof HTMLImageElement)) return;
          const rect = image.getBoundingClientRect();
          const cx = rect.left + rect.width / 2;
          const cy = rect.top + rect.height / 2;
          const fire = (type, pointerId, x, y, buttons) => {
            image.dispatchEvent(new PointerEvent(type, {
              pointerId,
              pointerType: 'touch',
              isPrimary: pointerId === 41,
              clientX: x,
              clientY: y,
              button: 0,
              buttons,
              bubbles: true,
              cancelable: true,
            }));
          };
          fire('pointerdown', 41, cx - 45, cy, 1);
          fire('pointerdown', 42, cx + 45, cy, 1);
          fire('pointermove', 41, cx - 100, cy, 1);
          fire('pointermove', 42, cx + 100, cy, 1);
          fire('pointerup', 41, cx - 100, cy, 0);
          fire('pointerup', 42, cx + 100, cy, 0);
        }"""
    )
    page.wait_for_timeout(120)
    return {"before": before, "after": read_viewer_state(page)}


def run_zoom_control_probe(page: Any, base_url: str, timeout_ms: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name, zoom_fn in (
        ("wheel", zoom_viewer_with_wheel),
        ("toolbar", zoom_viewer_with_toolbar),
        ("pinch", zoom_viewer_with_pinch),
    ):
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_shell(page, timeout_ms)
        opened_path, _ = open_first_viewer(page, timeout_ms)
        wait_for_viewer_ready(page, opened_path, timeout_ms)
        pre_pan = drag_viewer_image(page, -90, 0)
        zoom = zoom_fn(page)
        results.append({
            "name": name,
            "openedPath": opened_path,
            "prePan": pre_pan,
            "zoom": zoom,
        })
        close_viewer(page, timeout_ms)
    return results


def active_drag_axis(dx: int, dy: int) -> str:
    return "x" if abs(dx) >= abs(dy) else "y"


def active_drag_value(state: dict[str, Any], axis: str) -> float | None:
    matrix = state.get("matrix")
    if not isinstance(matrix, dict):
        return None
    key = "e" if axis == "x" else "f"
    value = matrix.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def reached_strict_edge(state: dict[str, Any], dx: int, dy: int) -> bool:
    axis = active_drag_axis(dx, dy)
    value = active_drag_value(state, axis)
    transform_bounds = state.get("transformBounds")
    bounds = transform_bounds.get(axis) if isinstance(transform_bounds, dict) else None
    if value is None or not isinstance(bounds, dict):
        return False
    if (dx if axis == "x" else dy) < 0:
        return value <= float(bounds.get("strictMin", 0)) + 1
    return value >= float(bounds.get("strictMax", 0)) - 1


def drag_to_strict_edge(page: Any, dx: int, dy: int) -> list[dict[str, Any]]:
    step_dx = 24 if dx > 0 else -24 if dx < 0 else 0
    step_dy = 24 if dy > 0 else -24 if dy < 0 else 0
    drags: list[dict[str, Any]] = []
    for _ in range(80):
        if reached_strict_edge(read_viewer_state(page), dx, dy):
            break
        drags.append(drag_viewer_image(page, step_dx, step_dy))
    return drags


def run_default_pan_probe(page: Any, base_url: str, timeout_ms: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name, dx, dy in DEFAULT_DRAGS:
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_shell(page, timeout_ms)
        opened_path, _ = open_first_viewer(page, timeout_ms)
        wait_for_viewer_ready(page, opened_path, timeout_ms)
        drag = drag_viewer_image(page, dx, dy)
        results.append({"name": name, "openedPath": opened_path, "drag": drag})
        close_viewer(page, timeout_ms)
    return results


def run_zoom_edge_probe(page: Any, base_url: str, timeout_ms: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name, dx, dy in EDGE_DRAGS:
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_shell(page, timeout_ms)
        opened_path, _ = open_first_viewer(page, timeout_ms)
        wait_for_viewer_ready(page, opened_path, timeout_ms)
        zoom = zoom_viewer_with_wheel(page)
        approach_drags = drag_to_strict_edge(page, dx, dy)
        before_additional = read_viewer_state(page)
        reached_strict = reached_strict_edge(before_additional, dx, dy)
        additional = drag_viewer_image(page, dx, dy)
        results.append(
            {
                "name": name,
                "openedPath": opened_path,
                "zoom": zoom,
                "approachDrags": approach_drags,
                "beforeAdditional": before_additional,
                "reachedStrictEdge": reached_strict,
                "additionalDrag": additional,
                "changedBeyondOldClamp": bool(additional.get("changed")),
            }
        )
        close_viewer(page, timeout_ms)
    return results


def choose_background_point(page: Any) -> dict[str, float]:
    point = page.evaluate(
        """() => {
          const dialog = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
          const image = dialog?.querySelector('img[data-viewer-image="full"]');
          if (!(dialog instanceof HTMLElement)) return null;
          const d = dialog.getBoundingClientRect();
          const candidates = [
            { x: d.left + 18, y: d.top + 18 },
            { x: d.right - 18, y: d.top + 18 },
            { x: d.left + 18, y: d.bottom - 18 },
            { x: d.right - 18, y: d.bottom - 18 },
            { x: d.left + d.width / 2, y: d.bottom - 22 },
          ];
          const inImage = (candidate) => {
            if (!(image instanceof HTMLImageElement)) return false;
            const r = image.getBoundingClientRect();
            return candidate.x >= r.left && candidate.x <= r.right &&
              candidate.y >= r.top && candidate.y <= r.bottom;
          };
          return candidates.find((candidate) => !inImage(candidate)) || candidates[0];
        }"""
    )
    if not isinstance(point, dict):
        raise ViewerProbeFailure("Could not choose a viewer background point.")
    return {"x": float(point["x"]), "y": float(point["y"])}


def choose_image_point(page: Any) -> dict[str, float]:
    point = page.evaluate(
        """() => {
          const image = document.querySelector('[role="dialog"][aria-label="Image viewer"] img[data-viewer-image="full"]');
          if (!(image instanceof HTMLImageElement)) return null;
          const rect = image.getBoundingClientRect();
          return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        }"""
    )
    if not isinstance(point, dict):
        raise ViewerProbeFailure("Could not choose a viewer image point.")
    return {"x": float(point["x"]), "y": float(point["y"])}


def choose_zoom_slider_point(page: Any) -> dict[str, float]:
    point = page.evaluate(
        """() => {
          const slider = document.querySelector('input[aria-label="Zoom level"]');
          if (!(slider instanceof HTMLElement)) return null;
          const rect = slider.getBoundingClientRect();
          return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        }"""
    )
    if not isinstance(point, dict):
        raise ViewerProbeFailure("Could not choose the viewer zoom slider point.")
    return {"x": float(point["x"]), "y": float(point["y"])}


def run_click_probe(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, point_fn, click_count in (
        ("singleClickImage", choose_image_point, 1),
        ("singleClickBackground", choose_background_point, 1),
        ("doubleClickImage", choose_image_point, 2),
        ("doubleClickBackground", choose_background_point, 2),
    ):
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_shell(page, timeout_ms)
        opened_path, _ = open_first_viewer(page, timeout_ms)
        wait_for_viewer_ready(page, opened_path, timeout_ms)
        point = point_fn(page)
        if click_count == 1:
            page.mouse.click(point["x"], point["y"])
        else:
            page.mouse.dblclick(point["x"], point["y"])
        closed = wait_for_viewer_closed(page, 900)
        results[name] = {
            "openedPath": opened_path,
            "point": point,
            "closed": closed,
        }
        if not closed:
            close_viewer(page, timeout_ms)

    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    opened_path, _ = open_first_viewer(page, timeout_ms)
    wait_for_viewer_ready(page, opened_path, timeout_ms)
    drag = drag_viewer_image(page, 90, 0)
    point = choose_image_point(page)
    page.mouse.dblclick(point["x"], point["y"])
    closed = wait_for_viewer_closed(page, 900)
    results["doubleClickAfterDrag"] = {
        "openedPath": opened_path,
        "point": point,
        "drag": drag,
        "closed": closed,
    }
    if not closed:
        close_viewer(page, timeout_ms)

    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    opened_path, _ = open_first_viewer(page, timeout_ms)
    wait_for_viewer_ready(page, opened_path, timeout_ms)
    point = choose_zoom_slider_point(page)
    page.mouse.dblclick(point["x"], point["y"])
    closed = wait_for_viewer_closed(page, 900)
    results["doubleClickToolbarZoom"] = {
        "openedPath": opened_path,
        "point": point,
        "closed": closed,
    }
    if not closed:
        close_viewer(page, timeout_ms)
    return results


def run_interactions_probe(context: Any, base_url: str, *, timeout_ms: float) -> dict[str, Any]:
    page = context.new_page()
    page.set_default_timeout(timeout_ms)
    page.add_init_script(seed_storage_script())
    page.set_viewport_size({"width": 1200, "height": 820})
    result = {
        "defaultFitPan": run_default_pan_probe(page, base_url, timeout_ms),
        "zoomEdgePan": run_zoom_edge_probe(page, base_url, timeout_ms),
        "zoomControls": run_zoom_control_probe(page, base_url, timeout_ms),
        "clicks": run_click_probe(page, base_url, timeout_ms),
    }
    page.close()
    return result
