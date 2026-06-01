from __future__ import annotations

from typing import Any

from scripts.browser.overall_cleanup.support import OverallCleanupBrowserFailure

def wait_for_image_ready(page: Any, selector: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """(selector) => {
          const img = document.querySelector(selector)
          if (!(img instanceof HTMLImageElement)) return false
          const opacity = Number(window.getComputedStyle(img).opacity || '0')
          return img.complete && img.naturalWidth > 0 && img.naturalHeight > 0 && opacity > 0.5
        }""",
        arg=selector,
        timeout=timeout_ms,
    )

def collect_transformed_image_center(
    page: Any,
    *,
    container_selector: str,
    image_selector: str,
    name: str,
) -> dict[str, Any]:
    snapshot = page.evaluate(
        """({ containerSelector, imageSelector, name }) => {
          const rectPayload = (rect) => ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          })
          const container = document.querySelector(containerSelector)
          const img = document.querySelector(imageSelector)
          if (!container || !(img instanceof HTMLImageElement)) return null
          const containerRect = container.getBoundingClientRect()
          const transform = window.getComputedStyle(img).transform
          const matrix = new DOMMatrixReadOnly(transform && transform !== 'none' ? transform : undefined)
          const scaleX = matrix.a
          const scaleY = matrix.d
          if (!scaleX || !scaleY || !img.naturalWidth || !img.naturalHeight) return null
          return {
            name,
            container: rectPayload(containerRect),
            naturalWidth: img.naturalWidth,
            naturalHeight: img.naturalHeight,
            transform: {
              scaleX,
              scaleY,
              tx: matrix.e,
              ty: matrix.f,
            },
            normalizedCenter: {
              x: ((containerRect.width / 2) - matrix.e) / (img.naturalWidth * scaleX),
              y: ((containerRect.height / 2) - matrix.f) / (img.naturalHeight * scaleY),
            },
          }
        }""",
        {
            "containerSelector": container_selector,
            "imageSelector": image_selector,
            "name": name,
        },
    )
    if not isinstance(snapshot, dict):
        raise OverallCleanupBrowserFailure(f"Failed to collect transformed image center for {name}.")
    return snapshot

def assert_center_preserved(before: dict[str, Any], after: dict[str, Any], *, tolerance: float = 0.055) -> None:
    before_center = before.get("normalizedCenter")
    after_center = after.get("normalizedCenter")
    if not isinstance(before_center, dict) or not isinstance(after_center, dict):
        raise OverallCleanupBrowserFailure(f"Missing normalized centers: before={before!r}, after={after!r}.")
    container = after.get("container")
    transform = after.get("transform")
    if not isinstance(container, dict) or not isinstance(transform, dict):
        raise OverallCleanupBrowserFailure(f"Missing rendered bounds for resize comparison: after={after!r}.")
    rendered_width = float(after.get("naturalWidth", 0)) * float(transform.get("scaleX", 0))
    rendered_height = float(after.get("naturalHeight", 0)) * float(transform.get("scaleY", 0))
    width = float(container.get("width", 0))
    height = float(container.get("height", 0))
    axis_deltas: dict[str, float] = {}
    if rendered_width > width + 1.5:
        axis_deltas["x"] = abs(float(before_center.get("x", 0)) - float(after_center.get("x", 0)))
    if rendered_height > height + 1.5:
        axis_deltas["y"] = abs(float(before_center.get("y", 0)) - float(after_center.get("y", 0)))
    if not axis_deltas:
        return
    failed = {axis: delta for axis, delta in axis_deltas.items() if delta > tolerance}
    if failed:
        raise OverallCleanupBrowserFailure(
            f"{after.get('name')} center drifted after resize on pannable axes: "
            f"deltas={failed!r}, before={before_center!r}, after={after_center!r}."
        )

def assert_transform_stable(before: dict[str, Any], after: dict[str, Any], name: str) -> None:
    before_transform = before.get("transform")
    after_transform = after.get("transform")
    if not isinstance(before_transform, dict) or not isinstance(after_transform, dict):
        raise OverallCleanupBrowserFailure(f"Missing transform evidence for {name}: before={before!r}, after={after!r}.")
    limits = {"scaleX": 0.01, "scaleY": 0.01, "tx": 1.0, "ty": 1.0}
    drift = {
        key: abs(float(before_transform.get(key, 0)) - float(after_transform.get(key, 0)))
        for key in limits
    }
    failed = {key: value for key, value in drift.items() if value > limits[key]}
    if failed:
        raise OverallCleanupBrowserFailure(
            f"{name} transform changed after late load despite interaction freeze: {failed!r}."
        )

def collect_compare_divider_split(page: Any, name: str) -> dict[str, Any]:
    snapshot = page.evaluate(
        """(name) => {
          const stage = document.querySelector('.compare-stage')
          const divider = document.querySelector('.compare-divider-hit')
          if (!(stage instanceof HTMLElement) || !(divider instanceof HTMLElement)) return null
          const stageRect = stage.getBoundingClientRect()
          const dividerRect = divider.getBoundingClientRect()
          const inlinePct = Number.parseFloat(divider.style.left || '')
          const renderedPct = stageRect.width > 0
            ? (((dividerRect.left + dividerRect.width / 2) - stageRect.left) / stageRect.width) * 100
            : NaN
          return {
            name,
            inlinePct,
            renderedPct,
            stage: {
              left: stageRect.left,
              top: stageRect.top,
              width: stageRect.width,
              height: stageRect.height,
            },
            divider: {
              left: dividerRect.left,
              top: dividerRect.top,
              width: dividerRect.width,
              height: dividerRect.height,
            },
          }
        }""",
        name,
    )
    if not isinstance(snapshot, dict):
        raise OverallCleanupBrowserFailure(f"Failed to collect compare divider split for {name}.")
    return snapshot

def assert_compare_split_in_range(snapshot: dict[str, Any], name: str) -> None:
    for key in ("inlinePct", "renderedPct"):
        value = float(snapshot.get(key, float("nan")))
        if not 4.5 <= value <= 95.5:
            raise OverallCleanupBrowserFailure(
                f"Compare divider split escaped clamp range for {name}: {key}={value:.2f}, snapshot={snapshot!r}."
            )

def assert_compare_split_changed(before: dict[str, Any], after: dict[str, Any], name: str) -> None:
    delta = abs(float(before.get("inlinePct", 0)) - float(after.get("inlinePct", 0)))
    if delta < 8:
        raise OverallCleanupBrowserFailure(
            f"Compare divider did not move meaningfully for {name}: delta={delta:.2f}, before={before!r}, after={after!r}."
        )

def assert_compare_split_stable(before: dict[str, Any], after: dict[str, Any], name: str) -> None:
    delta = abs(float(before.get("inlinePct", 0)) - float(after.get("inlinePct", 0)))
    if delta > 0.75:
        raise OverallCleanupBrowserFailure(
            f"Compare divider split changed after cleanup for {name}: delta={delta:.2f}, before={before!r}, after={after!r}."
        )

def assert_meaningfully_off_center(snapshot: dict[str, Any], name: str, *, tolerance: float = 0.025) -> None:
    center = snapshot.get("normalizedCenter")
    if not isinstance(center, dict):
        raise OverallCleanupBrowserFailure(f"Missing normalized center for {name}: {snapshot!r}.")
    dx = abs(float(center.get("x", 0.5)) - 0.5)
    dy = abs(float(center.get("y", 0.5)) - 0.5)
    if max(dx, dy) <= tolerance:
        raise OverallCleanupBrowserFailure(
            f"{name} did not become meaningfully off-center before resize: center={center!r}."
        )

def zoom_and_pan_surface(page: Any, selector: str) -> None:
    surface = page.locator(selector).first
    box = surface.bounding_box()
    if not box:
        raise OverallCleanupBrowserFailure(f"Missing bounding box for zoom/pan surface {selector!r}.")
    x = box["x"] + (box["width"] * 0.55)
    y = box["y"] + (box["height"] * 0.52)
    page.mouse.move(x, y)
    for _ in range(3):
        page.mouse.wheel(0, -620)
        page.wait_for_timeout(80)
    page.wait_for_timeout(160)
    page.mouse.down()
    page.mouse.move(x - 132, y - 96, steps=8)
    page.mouse.up()
    page.wait_for_timeout(180)

def assert_surface_wheel_zoomed(before: dict[str, Any], after: dict[str, Any], name: str) -> None:
    before_scale = float((before.get("transform") or {}).get("scaleX", 0))
    after_scale = float((after.get("transform") or {}).get("scaleX", 0))
    if after_scale <= before_scale:
        raise OverallCleanupBrowserFailure(
            f"{name} wheel zoom did not increase image scale: before={before_scale}, after={after_scale}."
        )

def set_range_value(page: Any, selector: str, value: int) -> None:
    page.locator(selector).first.evaluate(
        """(element, value) => {
          if (!(element instanceof HTMLInputElement)) throw new Error('Range target is not an input')
          element.value = String(value)
          element.dispatchEvent(new Event('input', { bubbles: true }))
          element.dispatchEvent(new Event('change', { bubbles: true }))
        }""",
        value,
    )
