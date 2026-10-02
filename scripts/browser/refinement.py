"""Focused regression gate for the Jaku main-gallery refinements.

Build/mirror the frontend first, then run:
python -m scripts.browser.refinement --output-dir /tmp/lenslet-refinement
Use --base-url for an existing server with the same synthetic fixture dataset.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
from typing import Any

from playwright.sync_api import sync_playwright

from scripts.browser.gui_jitter.fixtures import build_fixture_dataset
from scripts.browser.gui_jitter.inspector import (
    inspector_storage_payload, select_grid_path, wait_for_inspector_hydrated,
)
from scripts.browser.gui_jitter.shared import wait_for_grid
from scripts.browser.gui_jitter.metrics_controller import configure_facets, install_facet_controller
from scripts.browser.gui_jitter.grid_dom import open_metrics_panel
from scripts.smoke_harness import choose_port, running_lenslet_server, wait_for_health


PATH = "/quick_01_meta.png"
NOTES = '[data-inspector-section-id="notes"]'


def prepare(page: Any, base_url: str) -> None:
    payload = json.dumps({**inspector_storage_payload(), "rightOpen": "true"})
    page.add_init_script(f"""(() => {{
      if (sessionStorage.getItem('refinementPrepared')) return;
      sessionStorage.setItem('refinementPrepared', '1');
      for (const [key, value] of Object.entries({payload})) {{
        if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
      }}
    }})()""")
    page.route("**/embeddings", lambda route: route.fulfill(json={
        "embeddings": [{"name": f"fixture-{i}", "dimension": 3, "metric": "cosine", "dtype": "float32"}
                       for i in range(12)], "rejected": [],
    }))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_grid(page, 30_000)


def tab_to(page: Any, target: Any, limit: int = 120) -> None:
    for _ in range(limit):
        page.keyboard.press("Tab")
        if target.evaluate("node => node === document.activeElement"):
            return
    raise AssertionError(f"Keyboard never reached {target}")


def focus_evidence(target: Any) -> dict[str, Any]:
    evidence = target.evaluate("""node => {
      const css = getComputedStyle(node);
      return {visible: node.matches(':focus-visible'), outline: css.outlineStyle,
        width: parseFloat(css.outlineWidth), color: css.outlineColor,
        shadow: css.boxShadow};
    }""")
    assert evidence["visible"] and evidence["outline"] != "none" and evidence["width"] >= 1, evidence
    return evidence


def desktop(page: Any, base_url: str) -> dict[str, Any]:
    prepare(page, base_url)
    search = page.get_by_label("Search filename, tags, notes", exact=True)
    tab_to(page, search)
    result = {"searchFocus": focus_evidence(search)}
    slider = page.get_by_role("slider", name="Thumbnail size")
    tab_to(page, slider)
    result["sliderFocus"] = focus_evidence(slider)
    old_size = slider.input_value()
    page.keyboard.press("ArrowRight")
    assert slider.input_value() != old_size, "Keyboard sizing did not update"
    select_grid_path(page, PATH, 30_000)
    wait_for_inspector_hydrated(page, PATH, 30_000)
    metadata = page.get_by_role("region", name="Image metadata", exact=True)
    tab_to(page, metadata)
    result["metadataFocus"] = focus_evidence(metadata)
    copy = metadata.get_by_role("button", name="Copy value for found_text_chunks[0].text.prompt", exact=True)
    tab_to(page, copy)
    page.keyboard.press("Enter")
    page.wait_for_function("navigator.clipboard.readText().then(text => text === 'beta prompt')")
    result["copiedMetadataValue"] = page.evaluate("navigator.clipboard.readText()")
    result["theme"] = theme_switch(page)
    select_grid_path(page, "/quick_00_meta.png", 30_000)
    page.locator('[id="cell-%2Fquick_01_meta.png"]').click(modifiers=["Control"])
    page.get_by_role("button", name="Side by side view", exact=True).click()
    dialog = page.get_by_role("dialog", name="Compare images")
    divider = dialog.get_by_role("slider", name="Comparison split")
    divider.wait_for()
    pair = dialog.get_attribute("data-compare-presented-pair")
    tab_to(page, divider)
    result["dividerFocus"] = focus_evidence(divider)
    for key, expected in (("Home", "5"), ("ArrowRight", "6"), ("Shift+ArrowRight", "16"), ("End", "95")):
        page.keyboard.press(key)
        assert divider.get_attribute("aria-valuenow") == expected, key
        assert dialog.get_attribute("data-compare-presented-pair") == pair, "Divider navigated images"
    page.keyboard.press("Escape")
    dialog.wait_for(state="hidden")
    result["comparePair"] = pair
    result["modal"] = modal_portal(page)
    search.fill('sample')
    page.set_viewport_size({"width": 390, "height": 960})
    page.get_by_role('button', name='Open search', exact=True).click()
    mobile_search = page.locator('[data-toolbar-control="search-mobile"]')
    assert mobile_search.input_value() == 'sample', 'Search draft lost across mobile breakpoint'
    page.get_by_role('button', name='Close search', exact=True).click()
    page.get_by_role('button', name='Open search', exact=True).click()
    assert mobile_search.input_value() == 'sample', 'Search draft lost on hide/show'
    page.set_viewport_size({"width": 1440, "height": 960})
    assert search.input_value() == 'sample', 'Search draft lost returning to desktop'
    result['responsiveSearch'] = 'sample'
    return result


def theme_switch(page: Any) -> list[dict[str, Any]]:
    results = []
    for theme in ("Charcoal", "Original", "Charcoal"):
        page.get_by_role("button", name="Settings (", exact=False).click()
        choice = page.get_by_role("menuitemradio", name=theme, exact=True)
        # Start the trace before the action, including the first painted frame.
        choice.evaluate("""node => {
          window.__themeFrames = [];
          let left = 12;
          node.click();
          requestAnimationFrame(function sample() {
            const transitions = document.getAnimations().filter(animation =>
              ['color','background-color','border-color','border-top-color','border-right-color',
               'border-bottom-color','border-left-color','box-shadow'].includes(animation.transitionProperty));
            window.__themeFrames.push({theme: document.documentElement.dataset.lensletTheme,
              transitions: transitions.map(animation => ({property: animation.transitionProperty,
                target: animation.effect.target?.className}))});
            if (--left) requestAnimationFrame(sample); else window.__themeDone = true;
          });
        }""")
        page.wait_for_function("window.__themeFrames.length === 12")
        frames = page.evaluate("window.__themeFrames")
        assert all(not frame["transitions"] for frame in frames), frames
        results.append({"requested": theme, "frames": frames})
    # The suppression must not permanently remove normal interaction feedback.
    page.wait_for_function("getComputedStyle(document.querySelector('.btn')).transitionDuration !== '0s'")
    return results


def modal_portal(page: Any) -> dict[str, Any]:
    # Only capability enumeration is synthetic; the real Dropdown and modal own
    # focus, portal mounting, dismissal, and restore behavior.
    select_grid_path(page, PATH, 30_000)
    trigger = page.get_by_role("button", name="Find similar", exact=True).first
    trigger.click()
    modal = page.get_by_role("dialog", name="Find similar", exact=True)
    modal.wait_for()
    embedding = modal.get_by_role("button", name="Embedding", exact=True)
    embedding.click()
    popup_id = embedding.get_attribute("aria-controls")
    popup = page.locator(f'[id="{popup_id}"]')
    popup.wait_for()
    search = popup.get_by_role("searchbox")
    search.focus()
    search.fill("fixture-1")
    page.keyboard.press("ArrowDown")
    assert popup.evaluate("node => node.contains(document.activeElement)"), "Portal focus escaped"
    page.keyboard.press("Escape")
    popup.wait_for(state="hidden")
    assert modal.is_visible(), "First Escape dismissed the parent modal"
    page.keyboard.press("Escape")
    modal.wait_for(state="hidden")
    assert trigger.evaluate("node => node === document.activeElement"), "Modal did not restore trigger focus"
    return {"portal": popup_id, "escapeLayers": 2}


MOBILE_FRAMES = """({selector}) => {
  window.__paneFrames = [];
  window.__paneTracing = true;
  const snapshot = () => {
    const panel = document.querySelector('[data-inspector-panel]');
    const rect = panel?.getBoundingClientRect();
    if (rect?.width && rect?.height && getComputedStyle(panel).visibility !== 'hidden'
        && !panel.closest('[inert]') && rect.right > 0 && rect.left < innerWidth) {
      const section = panel.querySelector('[data-inspector-section-id="notes"]');
      const body = section?.querySelector('.inspector-section-body');
      const img = panel.querySelector('.inspector-preview-image');
      let pixel = null;
      if (img?.complete && img.naturalWidth) {
        const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
        const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0, 1, 1);
        pixel = [...ctx.getImageData(0, 0, 1, 1).data];
      }
      window.__paneFrames.push({draft: section?.querySelector('textarea')?.value,
        open: section?.querySelector('[aria-expanded]')?.getAttribute('aria-expanded'),
        bodyHeight: body?.getBoundingClientRect().height, inert: body?.inert,
        src: img?.currentSrc, pixel, complete: img?.complete, opacity: img && getComputedStyle(img).opacity,
        width: rect.width, left: rect.left, right: rect.right});
    }
    if (window.__paneTracing) requestAnimationFrame(snapshot);
  };
  requestAnimationFrame(snapshot);
  document.querySelector(selector).click();
}"""


def touch_targets(page: Any) -> list[dict[str, Any]]:
    targets = page.locator('[data-toolbar-control]').evaluate_all("""nodes => nodes
      .filter(node => node.tagName === 'BUTTON' && !node.disabled && node.getClientRects().length
        && getComputedStyle(node).visibility !== 'hidden' && node.getAttribute('aria-hidden') !== 'true')
      .map(node => {
        const rect = node.getBoundingClientRect();
        const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
        return {name: node.dataset.toolbarControl, x: rect.x, y: rect.y,
          width: rect.width, height: rect.height, unobscured: node.contains(hit)};
      })""")
    assert targets
    for target in targets:
        assert target['width'] >= 24 and target['height'] >= 24 and target['unobscured'], target
    for index, first in enumerate(targets):
        for second in targets[index + 1:]:
            overlap_x = min(first['x'] + first['width'], second['x'] + second['width']) - max(first['x'], second['x'])
            overlap_y = min(first['y'] + first['height'], second['y'] + second['height']) - max(first['y'], second['y'])
            assert overlap_x <= 1 or overlap_y <= 1, (first, second)
    return targets


def mobile(page: Any, base_url: str, width: int) -> dict[str, Any]:
    prepare(page, base_url)
    page.get_by_role("button", name="Open search", exact=True).click()
    page.get_by_role("textbox", name="Search filename, tags, notes", exact=True).fill("quick_01_meta")
    page.locator('[id="cell-%2Fquick_01_meta.png"]').click()
    # Open the responsive toolbar if its controls live in the narrow drawer.
    browse = page.locator('[data-toolbar-control="drawer-left-panel"]')
    if not browse.is_visible():
        page.get_by_role("button", name="Show mobile toolbar controls", exact=True).click()
    toolbar_targets = touch_targets(page)
    browse.click()
    folders = page.get_by_role("dialog", name="Browse tools", exact=True)
    folders.wait_for()
    assert folders.get_by_role("tree").is_visible(), "Folder tree is not reachable"
    settings = folders.get_by_role("button", name="Settings (", exact=False)
    settings.focus()
    page.keyboard.press("Enter")
    theme_menu = page.locator('.theme-settings-menu-panel')
    theme_menu.wait_for()
    assert theme_menu.evaluate("node => node.contains(document.activeElement)"), 'Settings keyboard focus missing'
    page.keyboard.press("Escape")
    theme_menu.wait_for(state="hidden")
    assert folders.is_visible(), 'Settings Escape closed the sheet too'
    assert settings.evaluate("node => node === document.activeElement"), 'Settings focus not restored'
    page.keyboard.press("Escape")
    folders.wait_for(state="hidden")
    inspector_trigger = page.locator('[data-toolbar-control="drawer-right-panel"]')
    if not inspector_trigger.is_visible():
        page.get_by_role("button", name="Show mobile toolbar controls", exact=True).click()
    inspector_trigger.click()
    dialog = page.get_by_role("dialog", name="Inspector", exact=True)
    dialog.wait_for()
    expected_notes = page.request.get(f"{base_url}/item?path=%2Fquick_01_meta.png").json()["notes"]
    page.wait_for_function("""expected => {
      const panel = document.querySelector('[data-inspector-panel]');
      const image = panel?.querySelector('.inspector-preview-image');
      return panel?.textContent.includes('beta prompt') && image?.complete && image.naturalWidth > 0
        && panel.querySelector('textarea[aria-label="Notes"]')?.value === expected;
    }""", arg=expected_notes)
    notes = page.get_by_role("textbox", name="Notes", exact=True)
    draft = f"Unsaved mobile draft at {width}px"
    pending_saves = []
    page.route("**/item?*", lambda route: pending_saves.append(route)
               if route.request.method in ("PATCH", "PUT") else route.continue_())
    notes.fill(draft)
    page.locator(f'{NOTES} [aria-expanded]').click()
    page.wait_for_function("document.querySelector('[data-inspector-section-id=notes] .inspector-section-body').getBoundingClientRect().height < 1")
    page.get_by_role("button", name="Close Inspector", exact=True).click()
    dialog.wait_for(state="hidden")
    if not inspector_trigger.is_visible():
        page.get_by_role("button", name="Show mobile toolbar controls", exact=True).click()
    page.evaluate(MOBILE_FRAMES, {"selector": '[data-toolbar-control="drawer-right-panel"]'})
    dialog.wait_for()
    page.wait_for_function("window.__paneFrames.length >= 8")
    frames = page.evaluate("() => { window.__paneTracing = false; return window.__paneFrames; }")
    assert frames, "No visible pane frames"
    for frame in frames:
        assert frame["draft"] == draft and frame["open"] == "false", frame
        assert frame["inert"] and frame["bodyHeight"] <= 1, frame
        assert frame["complete"] and frame["pixel"], frame
        assert all(abs(actual - expected) <= 2 for actual, expected in zip(frame["pixel"][:3], [36, 126, 74])), frame
        assert frame["src"] == frames[0]["src"] and frame["pixel"] == frames[0]["pixel"], frame
        assert frame["opacity"] == "1" and frame["left"] >= -1 and frame["right"] <= width + 1, frame
    close = page.get_by_role("button", name="Close Inspector", exact=True)
    targets = close.evaluate("""node => {
      const rect = node.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return {width: rect.width, height: rect.height, unobscured: node.contains(hit)};
    }""")
    assert targets["width"] >= 24 and targets["height"] >= 24 and targets["unobscured"], targets
    saved_notes = page.request.get(f"{base_url}/item?path=%2Fquick_01_meta.png").json()["notes"]
    assert saved_notes == expected_notes and saved_notes != draft, 'Draft was already saved; retention not exercised'
    close.click()
    if not browse.is_visible():
        page.get_by_role("button", name="Show mobile toolbar controls", exact=True).click()
    browse.click()
    folder_actions = folders.get_by_role("button", name="Open actions for Root", exact=True)
    folder_actions.focus()
    page.keyboard.press("Enter")
    menu = page.locator('.context-menu-panel')
    menu.wait_for()
    items = menu.locator('[role="menuitem"]:not([aria-disabled="true"]):not(:disabled)')
    assert items.first.evaluate("node => node === document.activeElement"), 'Folder menu first focus missing'
    page.keyboard.press("Tab")
    menu.wait_for(state="hidden")
    assert folders.evaluate("node => document.activeElement !== document.body && node.contains(document.activeElement)"), 'Folder menu Tab lost focus'
    folder_actions.focus()
    page.keyboard.press("Enter")
    page.keyboard.press("End")
    assert items.last.evaluate("node => node === document.activeElement"), 'Folder menu End missed final action'
    page.keyboard.press("Home")
    assert items.first.evaluate("node => node === document.activeElement"), 'Folder menu Home missed first action'
    page.keyboard.press("Escape")
    menu.wait_for(state="hidden")
    assert folders.is_visible() and folder_actions.evaluate("node => node === document.activeElement"), 'Folder Escape scope/focus failed'
    page.keyboard.press("Enter")
    with page.expect_download() as export:
        page.get_by_role("menuitem", name="Export metadata (JSON)", exact=True).click()
    assert export.value.suggested_filename.startswith("metadata_root_"), "Folder action did not export"
    for save in pending_saves:
        save.abort()
    return {"viewport": width, "revealFrames": frames, "closeTarget": targets, "toolbarTargets": toolbar_targets, "unsavedDraftVerified": True, "keyboardMenus": "first focus, Tab continuation, Home, End, scoped Escape, focus restoration"}


def metrics_retry(page: Any, base_url: str) -> dict[str, Any]:
    prepare(page, base_url)
    install_facet_controller(page)
    field = 'zz_probe_metric_29'
    configure_facets(page, errorFields=[field])
    page.get_by_role('button', name='Derived Score', exact=True).click()
    draft = page.locator('[data-derived-score-name]')
    draft.fill('retain-this-draft')
    open_metrics_panel(page, 30_000)
    selector = page.locator('[data-metric-selector] button[aria-haspopup="listbox"]').first
    selector.click()
    popup = page.get_by_role('listbox', name='Metric', exact=True)
    popup.get_by_role('searchbox').fill(field)
    popup.get_by_role('option', name=field, exact=True).click()
    card = page.locator(f'[data-metric-card-host="{field}"]')
    retry = card.get_by_role('button', name='Retry values', exact=True)
    retry.wait_for(timeout=30_000)
    assert card.get_attribute('data-facet-state') == 'error'
    before_requests = page.evaluate('window.__lensletFacetController.requests.length')
    height = card.bounding_box()['height']
    configure_facets(page, errorFields=[], delays={field: 350})
    retry.evaluate("""node => {
      window.__retryFrames = [];
      window.__retryTracing = true;
      requestAnimationFrame(function sample() {
        const card = document.querySelector('[data-metric-card-host="zz_probe_metric_29"]');
        window.__retryFrames.push({height: card?.getBoundingClientRect().height,
          state: card?.dataset.facetState,
          selected: document.querySelector('[data-metric-selector] button')?.textContent.trim(),
          draft: document.querySelector('[data-derived-score-name]')?.value});
        if (window.__retryTracing) requestAnimationFrame(sample);
      });
      node.click();
    }""")
    page.wait_for_function("document.querySelector('[data-metric-card-host=zz_probe_metric_29]')?.dataset.facetState === 'ready'", timeout=30_000)
    frames = page.evaluate('() => { window.__retryTracing = false; return window.__retryFrames; }')
    after_requests = page.evaluate('window.__lensletFacetController.requests.length')
    assert after_requests > before_requests, 'Retry did not request new facet values'
    assert frames and all(abs(frame['height'] - height) <= 1 for frame in frames), frames
    assert all(frame['selected'] == field and frame['draft'] == 'retain-this-draft' for frame in frames), frames
    population = card.locator('[data-count-role="population"]').inner_text()
    assert population == 'Population: 1585', population
    page.get_by_role('button', name='Derived Score', exact=True).click()
    assert draft.input_value() == 'retain-this-draft'
    return {'field': field, 'requestsBefore': before_requests, 'requestsAfter': after_requests,
            'population': population, 'frames': frames, 'draft': draft.input_value()}


def run(base_url: str, output: Path, only: str | None = None) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            scenarios = [("metrics", 1440, False)] if only == "metrics" else [
                ("desktop", 1440, False), ("mobile320", 320, True), ("mobile390", 390, True)]
            for scenario, viewport, touch in scenarios:
                if only and scenario != only:
                    continue
                context = browser.new_context(viewport={"width": viewport, "height": 960}, has_touch=touch,
                                              permissions=["clipboard-read", "clipboard-write"])
                page = context.new_page()
                page.set_default_timeout(15_000)
                try:
                    if scenario == "metrics":
                        results[scenario] = metrics_retry(page, base_url)
                    else:
                        results[scenario] = desktop(page, base_url) if not touch else mobile(page, base_url, viewport)
                    page.screenshot(path=str(output / f"{scenario}.png"))
                except Exception as error:
                    page.screenshot(path=str(output / f"{scenario}-failure.png"))
                    results[scenario] = {"error": str(error)}
                    raise
                finally:
                    (output / "result.json").write_text(json.dumps(results, indent=2) + "\n")
                    context.close()
        finally:
            browser.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--port", type=int, default=7137)
    parser.add_argument("--scenario", choices=["desktop", "mobile320", "mobile390", "metrics"])
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/lenslet-refinement"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lenslet-refinement-") as directory:
        dataset = Path(directory)
        if args.base_url:
            server_context = nullcontext(None)
        else:
            build_fixture_dataset(dataset)
            source = dataset / "metrics_items.parquet" if args.scenario == "metrics" else dataset
            extra = ["--source-column", "source", "--base-dir", str(dataset)] if args.scenario == "metrics" else []
            server_context = running_lenslet_server(source, host="127.0.0.1", port=choose_port("127.0.0.1", args.port), extra_args=extra)
        with server_context as server:
            base_url = args.base_url or server.base_url
            wait_for_health(base_url, 60)
            if server is not None and server.process.poll() is not None:
                raise RuntimeError(f"Fixture server exited; see {server.log_path}")
            run(base_url, args.output_dir, args.scenario)
        if not args.base_url and not args.scenario:
            with running_lenslet_server(
                dataset / "metrics_items.parquet", host="127.0.0.1", port=choose_port("127.0.0.1", args.port),
                extra_args=["--source-column", "source", "--base-dir", str(dataset)],
            ) as metrics_server:
                wait_for_health(metrics_server.base_url, 60)
                run(metrics_server.base_url, args.output_dir / "metrics", "metrics")
    print("PASS: main-gallery refinement browser regressions")


if __name__ == "__main__":
    main()
