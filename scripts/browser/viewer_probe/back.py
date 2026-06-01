from __future__ import annotations

from typing import Any

from scripts.browser.viewer_probe.config import BACK_CLICK_POINTS, BACK_SAMPLE_X_FRACS, BACK_SAMPLE_Y_FRACS, BACK_SWEEP_VIEWPORTS
from scripts.browser.viewer_probe.page import (
    is_viewer_open,
    open_first_viewer,
    seed_storage_script,
    wait_for_back_button,
    wait_for_shell,
    wait_for_viewer_closed,
)


def sample_back_button(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """({ xFracs, yFracs }) => {
          const rectPayload = (rect) => ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          });
          const stylePayload = (el) => {
            if (!(el instanceof HTMLElement)) return null;
            const style = getComputedStyle(el);
            return {
              pointerEvents: style.pointerEvents,
              zIndex: style.zIndex,
              position: style.position,
              opacity: Number(style.opacity || '0'),
              visibility: style.visibility,
              display: style.display,
            };
          };
          const describe = (el) => {
            if (!(el instanceof HTMLElement)) return null;
            return {
              tag: el.tagName,
              id: el.id || null,
              className: typeof el.className === 'string' ? el.className : null,
              ariaLabel: el.getAttribute('aria-label'),
              dataToolbarControl: el.getAttribute('data-toolbar-control'),
              dataToolbarSlot: el.getAttribute('data-toolbar-slot'),
              role: el.getAttribute('role'),
              text: (el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 80),
              rect: rectPayload(el.getBoundingClientRect()),
              style: stylePayload(el),
            };
          };
          const nearest = (el, selector) => (
            el instanceof HTMLElement ? describe(el.closest(selector)) : null
          );
          const back = document.querySelector('[data-toolbar-control="back"]');
          if (!(back instanceof HTMLElement)) {
            return { missing: true, roleButtonCountByName: 0, points: [] };
          }
          const backRect = back.getBoundingClientRect();
          const backStyle = getComputedStyle(back);
          const points = [];
          for (const yFrac of yFracs) {
            for (const xFrac of xFracs) {
              const x = backRect.left + backRect.width * xFrac;
              const y = backRect.top + backRect.height * yFrac;
              const hit = document.elementFromPoint(x, y);
              points.push({
                xFrac,
                yFrac,
                x,
                y,
                hit: describe(hit),
                resolvesToBack: Boolean(hit && (hit === back || back.contains(hit))),
                nearest: {
                  toolbarControl: nearest(hit, '[data-toolbar-control]'),
                  toolbarSlot: nearest(hit, '[data-toolbar-slot]'),
                  toolbarShell: nearest(hit, '.toolbar-shell'),
                  toolbarLeft: nearest(hit, '.toolbar-left'),
                  toolbarCenter: nearest(hit, '.toolbar-center'),
                  toolbarRight: nearest(hit, '.toolbar-right'),
                  viewerOrDialog: nearest(hit, '[role="dialog"], .z-viewer'),
                },
                backRect: rectPayload(backRect),
                backStyle: {
                  pointerEvents: backStyle.pointerEvents,
                  zIndex: backStyle.zIndex,
                  position: backStyle.position,
                  opacity: Number(backStyle.opacity || '0'),
                  visibility: backStyle.visibility,
                  display: backStyle.display,
                },
              });
            }
          }
          return {
            missing: false,
            rect: rectPayload(backRect),
            ariaLabel: back.getAttribute('aria-label'),
            title: back.getAttribute('title'),
            disabled: Boolean(back.disabled),
            ariaHidden: back.getAttribute('aria-hidden'),
            tabIndex: back.tabIndex,
            display: backStyle.display,
            visibility: backStyle.visibility,
            pointerEvents: backStyle.pointerEvents,
            roleButtonCountByName: Array.from(document.querySelectorAll('button'))
              .filter((el) => el.getAttribute('aria-label') === 'Back to grid').length,
            points,
          };
        }""",
        {"xFracs": list(BACK_SAMPLE_X_FRACS), "yFracs": list(BACK_SAMPLE_Y_FRACS)},
    )


def click_back_point(page: Any, sample: dict[str, Any], label: str, x_frac: float, y_frac: float) -> dict[str, Any]:
    rect = sample.get("rect")
    if not isinstance(rect, dict):
        return {"label": label, "closed": False, "error": "missing back rect"}
    x = float(rect["left"]) + float(rect["width"]) * x_frac
    y = float(rect["top"]) + float(rect["height"]) * y_frac
    page.mouse.click(x, y)
    closed = wait_for_viewer_closed(page, 1_500)
    return {"label": label, "x": x, "y": y, "closed": closed}


def run_back_probe(context: Any, base_url: str, *, timeout_ms: float) -> list[dict[str, Any]]:
    page = context.new_page()
    page.set_default_timeout(timeout_ms)
    page.add_init_script(seed_storage_script())
    results: list[dict[str, Any]] = []
    for viewport in BACK_SWEEP_VIEWPORTS:
        page.set_viewport_size({"width": viewport.width, "height": viewport.height})
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_shell(page, timeout_ms)
        opened_path, _ = open_first_viewer(page, timeout_ms)
        wait_for_back_button(page, timeout_ms)
        sample = sample_back_button(page)
        click_results: list[dict[str, Any]] = []
        for index, (label, x_frac, y_frac) in enumerate(BACK_CLICK_POINTS):
            if not is_viewer_open(page):
                open_first_viewer(page, timeout_ms)
                wait_for_back_button(page, timeout_ms)
            current_sample = sample_back_button(page)
            click_result = click_back_point(page, current_sample, label, x_frac, y_frac)
            click_results.append(click_result)
            if not click_result.get("closed"):
                page.keyboard.press("Escape")
                wait_for_viewer_closed(page, timeout_ms)
            if index != len(BACK_CLICK_POINTS) - 1:
                wait_for_shell(page, timeout_ms)
        failed_points = [
            point
            for point in sample.get("points", [])
            if isinstance(point, dict) and not point.get("resolvesToBack")
        ]
        results.append(
            {
                "name": viewport.name,
                "width": viewport.width,
                "height": viewport.height,
                "openedPath": opened_path,
                "sample": sample,
                "clicks": click_results,
                "failedPointCount": len(failed_points),
                "failedPoints": failed_points,
            }
        )
    page.close()
    return results

def back_acceptance_failures(raw_scenarios: Any) -> list[str]:
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        return ["back: missing Back hit-target scenarios"]

    failures: list[str] = []
    for scenario in raw_scenarios:
        if not isinstance(scenario, dict):
            failures.append("back: malformed Back scenario")
            continue
        name = str(scenario.get("name") or "<unnamed>")
        sample = scenario.get("sample")
        if not isinstance(sample, dict) or sample.get("missing"):
            failures.append(f"back:{name}: missing Back sample")
            continue
        points = sample.get("points")
        expected_point_count = len(BACK_SAMPLE_X_FRACS) * len(BACK_SAMPLE_Y_FRACS)
        if not isinstance(points, list) or len(points) != expected_point_count:
            failures.append(f"back:{name}: expected {expected_point_count} sampled points")
        else:
            failed_points = [point for point in points if not point.get("resolvesToBack")]
            if failed_points:
                failures.append(
                    f"back:{name}: {len(failed_points)} sampled points do not resolve to Back"
                )

        clicks = scenario.get("clicks")
        expected_click_labels = {label for label, _, _ in BACK_CLICK_POINTS}
        if not isinstance(clicks, list):
            failures.append(f"back:{name}: missing click results")
            continue
        click_labels = {click.get("label") for click in clicks if isinstance(click, dict)}
        missing_clicks = sorted(expected_click_labels - click_labels)
        if missing_clicks:
            failures.append(f"back:{name}: missing click labels {missing_clicks}")
        for click in clicks:
            if not isinstance(click, dict):
                failures.append(f"back:{name}: malformed click result")
            elif not click.get("closed"):
                failures.append(f"back:{name}: click {click.get('label')!r} did not close viewer")
    return failures
