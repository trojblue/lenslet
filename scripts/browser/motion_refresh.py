"""Painted-frame checks for shared Inspector disclosure motion.

Run after building and mirroring the frontend:
python -m scripts.browser.motion_refresh --output-dir /tmp/lenslet-motion
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from scripts.browser.gui_jitter.fixtures import build_fixture_dataset
from scripts.browser.gui_jitter.inspector import (
    inspector_storage_payload,
    select_grid_path,
    wait_for_inspector_hydrated,
)
from scripts.browser.gui_jitter.shared import wait_for_grid
from scripts.smoke_harness import choose_port, running_lenslet_server, wait_for_health


TRACE_DISCLOSURE = """async ({id, reverse}) => {
  const section = document.querySelector(`[data-inspector-section-id="${id}"]`);
  const button = section.querySelector('[aria-expanded]');
  const body = section.querySelector('.inspector-section-body');
  const descendants = [...body.querySelectorAll('*')];
  const editor = body.querySelector('textarea');
  const value = editor?.value;
  const scroll = editor?.scrollTop;
  const text = body.textContent;
  const fullHeight = body.getBoundingClientRect().height;
  const frames = [];
  const start = performance.now();
  let reversed = false;
  button.click();
  await new Promise(resolve => {
    const frame = () => {
      const elapsed = performance.now() - start;
      if (reverse && !reversed && elapsed >= 50) {
        button.click();
        reversed = true;
      }
      const images = [...document.querySelectorAll('.inspector-preview-image')].map(img => {
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = 1;
        const ctx = canvas.getContext('2d');
        if (img.complete && img.naturalWidth) ctx.drawImage(img, 0, 0, 1, 1);
        return {src: img.currentSrc, complete: img.complete, width: img.naturalWidth,
          opacity: getComputedStyle(img).opacity, transform: getComputedStyle(img).transform,
          pixel: [...ctx.getImageData(0, 0, 1, 1).data]};
      });
      frames.push({elapsed, height: body.getBoundingClientRect().height,
        opacity: getComputedStyle(body).opacity, open: button.getAttribute('aria-expanded'),
        inert: body.inert, textStable: body.textContent === text,
        descendantsRetained: descendants.every(node => body.contains(node)),
        value: editor?.value, images});
      if (elapsed < 320) requestAnimationFrame(frame); else resolve();
    };
    requestAnimationFrame(frame);
  });
  if (!reverse) {
    editor?.focus();
    if (editor && document.activeElement === editor) throw new Error('Closed editor is focusable');
    button.click();
    await new Promise(resolve => setTimeout(resolve, 240));
  }
  return {fullHeight, frames, value, scroll,
    sameEditor: !editor || body.querySelector('textarea') === editor,
    finalValue: editor?.value, finalScroll: editor?.scrollTop,
    finalHeight: body.getBoundingClientRect().height,
    controlsLinked: button.getAttribute('aria-controls') === body.id};
}"""


def assert_disclosure(trace: dict[str, Any], *, reduced: bool, reverse: bool, media: bool = True) -> None:
    frames = trace["frames"]
    full = trace["fullHeight"]
    assert full > 20, "Fixture section must have meaningful content"
    assert trace["controlsLinked"] and trace["sameEditor"]
    assert trace.get("value") == trace.get("finalValue"), "Draft changed across disclosure"
    assert trace.get("scroll") == trace.get("finalScroll"), "Editor scroll was lost"
    assert abs(trace["finalHeight"] - full) <= 1
    assert frames[0]["open"] == "false" and frames[0]["inert"], "First frame is stale"
    assert all(frame["opacity"] == "1" for frame in frames), "Content faded during disclosure"
    assert all(frame["descendantsRetained"] and frame["textStable"] for frame in frames)
    if media:
        assert frames[0]["images"], "Decoded Inspector preview must be present"
    assert all(image["complete"] and image["width"] > 0 for image in frames[0]["images"])
    assert all(frame["images"] == frames[0]["images"] for frame in frames), "Media identity changed"
    if reduced:
        assert frames[0]["height"] <= 1, "Reduced motion must settle in the first frame"
    elif not reverse:
        intermediate = [frame for frame in frames if 1 < frame["height"] < full - 1]
        assert len(intermediate) >= 3, "Disclosure snapped instead of animating intrinsic height"
        assert all(b["height"] <= a["height"] + 1 for a, b in zip(frames, frames[1:]))
    if reverse:
        assert frames[-1]["open"] == "true" and not frames[-1]["inert"]
    else:
        assert frames[-1]["height"] <= 1 and frames[-1]["inert"]


def exercise_disclosures(browser: Any, base_url: str, reduced: bool, output: Path) -> dict[str, Any]:
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        reduced_motion="reduce" if reduced else "no-preference",
    )
    try:
        page = context.new_page()
        page.goto(base_url, wait_until="domcontentloaded")
        page.evaluate("""entries => {
          for (const [key, value] of Object.entries(entries)) {
            if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
          }
        }""", inspector_storage_payload())
        page.reload(wait_until="domcontentloaded")
        wait_for_grid(page, 30_000)
        # A cold, unvisited media target must be settled before cosmetic disclosure.
        select_grid_path(page, "/quick_01_meta.png", 30_000)
        wait_for_inspector_hydrated(page, "/quick_01_meta.png", 30_000)
        notes = page.get_by_role("textbox", name="Notes", exact=True)
        notes.fill("Motion draft\n" * 40)
        notes.evaluate("e => { e.scrollTop = 100; e.setSelectionRange(3, 8); }")
        result = {}
        for section in ("quickView", "metadata", "notes"):
            for reverse in (False, True):
                trace = page.evaluate(TRACE_DISCLOSURE, {"id": section, "reverse": reverse})
                result[f"{section}-{'reverse' if reverse else 'cycle'}"] = trace
                (output / f"{reduced}-{section}-{reverse}.json").write_text(json.dumps(trace, indent=2))
                assert_disclosure(trace, reduced=reduced, reverse=reverse)
        page.screenshot(path=str(output / f"inspector-{'reduced' if reduced else 'motion'}.png"))
        # Persist a collapsed section and verify the very first visible Inspector frame.
        page.locator('[data-inspector-section-id="notes"] [aria-expanded]').click()
        page.wait_for_timeout(240)
        page.add_init_script("""requestAnimationFrame(function frame() {
          const section = document.querySelector('[data-inspector-section-id="notes"]');
          if (!section || !section.getClientRects().length) return requestAnimationFrame(frame);
          const body = section.querySelector('.inspector-section-body');
          window.__firstDisclosureFrame = {height: body.getBoundingClientRect().height,
            inert: body.inert, editorMounted: !!body.querySelector('textarea')};
        });""")
        page.reload(wait_until="domcontentloaded")
        wait_for_grid(page, 30_000)
        select_grid_path(page, "/quick_00_meta.png", 30_000)
        page.wait_for_function("!!window.__firstDisclosureFrame")
        cold = page.evaluate("window.__firstDisclosureFrame")
        assert cold["height"] <= 1 and cold["inert"] and cold["editorMounted"]
        result["reload"] = cold
        second_cell = f'[id="cell-{quote("/quick_01_meta.png", safe="")}"]'
        page.locator(second_cell).click(modifiers=["Control"])
        page.locator('[data-inspector-section-id="compareMetadata"] table').wait_for()
        for reverse in (False, True):
            trace = page.evaluate(TRACE_DISCLOSURE, {"id": "compareMetadata", "reverse": reverse})
            result[f"compare-{reverse}"] = trace
            assert_disclosure(trace, reduced=reduced, reverse=reverse, media=False)
        return result
    finally:
        context.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/lenslet-motion"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lenslet-motion-") as directory:
        results = {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for mode, reduced in (("normal", False), ("reduced", True)):
                    dataset = Path(directory) / mode
                    dataset.mkdir()
                    build_fixture_dataset(dataset)
                    with running_lenslet_server(
                        dataset, host="127.0.0.1", port=choose_port("127.0.0.1", 7093),
                    ) as server:
                        wait_for_health(server.base_url, 60)
                        results[mode] = exercise_disclosures(browser, server.base_url, reduced, args.output_dir)
            finally:
                browser.close()
    (args.output_dir / "disclosures.json").write_text(json.dumps(results, indent=2) + "\n")
    print("PASS: disclosure frames, reversal, retained editors/media, focus, and reduced motion")


if __name__ == "__main__":
    main()
