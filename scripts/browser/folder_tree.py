"""Check virtual folder navigation and painted-frame retention against a live large fixture.

Generate/launch the existing scripts.browser.large_tree fixture, rebuild/mirror the
frontend, then run with --base-url http://127.0.0.1:<port> --output-json /tmp/tree.json.
This gate covers offscreen keyboard targets, bounded DOM, and hidden-tab return;
unit tests cannot detect virtualizer render loops or prepaint scroll loss.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


RETURN_TO_FOLDERS = """async () => {
  const button = document.querySelector('button[aria-label="Folders"]');
  const frames = [];
  button.click();
  for (let index = 0; index < 12; index++) {
    await new Promise(requestAnimationFrame);
    const tree = document.querySelector('[role="tree"]');
    const scroller = tree.closest('.folder-tree-scroll');
    const bounds = scroller.getBoundingClientRect();
    const rows = [...tree.querySelectorAll('[role="treeitem"]')];
    frames.push({
      scrollTop: scroller.scrollTop,
      mounted: rows.length,
      visibleRows: rows.filter(row => {
        const rect = row.getBoundingClientRect();
        return rect.bottom > bounds.top && rect.top < bounds.bottom;
      }).map(row => ({path: row.dataset.folderPath, text: row.textContent, expanded: row.getAttribute('aria-expanded'), actions: row.querySelectorAll('button').length})),
    });
  }
  return frames;
}"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output-json', type=Path, required=True)
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 960})
        errors: list[str] = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.base_url)
        page.wait_for_selector('[role="gridcell"]')
        root = page.locator('[data-folder-path="/"]')
        root.wait_for()
        root.focus()
        page.keyboard.press('End')
        page.wait_for_function("""() => {
          const active = document.activeElement;
          return active.getAttribute('role') === 'treeitem'
            && Number(active.getAttribute('aria-setsize')) > 100
            && active.getAttribute('aria-posinset') === active.getAttribute('aria-setsize');
        }""")
        page.wait_for_function('''() => {
          const row = document.activeElement.getBoundingClientRect();
          const viewport = document.querySelector('.folder-tree-scroll').getBoundingClientRect();
          return row.top >= viewport.top - 1 && row.bottom <= viewport.bottom + 1;
        }''')
        end_path = page.evaluate('document.activeElement.dataset.folderPath')
        scroller = page.locator('.folder-tree-scroll')
        scroll_before = scroller.evaluate('(element) => element.scrollTop')
        assert scroll_before > 0, 'End must reach an offscreen logical row'
        mounted = page.locator('[role="treeitem"]').count()
        assert mounted < 100, f'Expected virtual window, mounted {mounted} folder rows'

        before_rows = scroller.evaluate('''scroller => {
          const bounds = scroller.getBoundingClientRect();
          return [...scroller.querySelectorAll('[role="treeitem"]')].filter(row => {
            const rect = row.getBoundingClientRect();
            return rect.bottom > bounds.top && rect.top < bounds.bottom;
          }).map(row => ({path: row.dataset.folderPath, text: row.textContent, expanded: row.getAttribute('aria-expanded'), actions: row.querySelectorAll('button').length}));
        }''')
        page.get_by_role('button', name='Metrics and Filters', exact=True).click()
        frames = page.evaluate(RETURN_TO_FOLDERS)
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps({'return_frames': frames}, indent=2) + '\n')
        assert frames[0]['visibleRows'], 'First return frame must contain settled folder rows'
        assert all(abs(frame['scrollTop'] - scroll_before) <= 1 for frame in frames), frames
        assert all(frame['visibleRows'] == before_rows for frame in frames), frames
        page.locator(f'[data-folder-path="{end_path}"]').focus()
        page.keyboard.press('Home')
        page.wait_for_function("document.activeElement.dataset.folderPath === '/'")
        page.keyboard.press('ArrowDown')
        page.wait_for_function("document.activeElement.dataset.folderPath !== '/'")
        first_path = page.evaluate('document.activeElement.dataset.folderPath')
        page.keyboard.press('ArrowRight')
        page.keyboard.press('Enter')
        page.wait_for_function("""path => document.querySelector('[role="treeitem"][aria-selected="true"]')
          ?.dataset.folderPath === path""", arg=first_path)
        page.locator('[data-folder-path="/"]').focus()
        page.keyboard.press('Enter')
        page.get_by_role('button', name='Collapse Root', exact=True).click()
        assert page.locator('[role="treeitem"]').count() == 1
        page.get_by_role('button', name='Expand Root', exact=True).click()
        page.wait_for_function('document.querySelectorAll("[role=treeitem]").length > 1')
        root.focus()
        page.keyboard.press('ArrowDown')
        page.keyboard.press('ArrowDown')
        cold_path = page.evaluate('document.activeElement.dataset.folderPath')
        page.evaluate("""path => {
          const originalFetch = window.fetch;
          window.fetch = async (...args) => {
            const response = await originalFetch(...args);
            const url = new URL(typeof args[0] === 'string' ? args[0] : args[0].url, location.href);
            if (url.pathname === '/folders' && url.searchParams.get('path') === path) {
              window.__lensletTreeDelayedFetches = (window.__lensletTreeDelayedFetches ?? 0) + 1;
              await new Promise(resolve => setTimeout(resolve, 450));
              window.__lensletTreeCompletedHidden = !!document.querySelector('[role="tree"]')?.closest('[hidden]');
            }
            return response;
          };
        }""", cold_path)
        page.keyboard.press('ArrowRight')
        page.get_by_role('button', name='Metrics and Filters', exact=True).click()
        page.wait_for_timeout(650)
        assert page.evaluate('window.__lensletTreeDelayedFetches > 0 && window.__lensletTreeCompletedHidden'), 'Expected cold folder fetch to complete while hidden'
        hidden_completion_frames = page.evaluate(RETURN_TO_FOLDERS)
        assert all(frame['visibleRows'] for frame in hidden_completion_frames), hidden_completion_frames
        assert not errors, errors
        result = {'end_path': end_path, 'first_path': first_path, 'mounted_rows': mounted,
                  'return_frames': frames, 'hidden_completion_frames': hidden_completion_frames, 'page_errors': errors}
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2) + '\n')
        print(f'Folder tree passed: {mounted} mounted rows; logical End={end_path}; return frames stable')
        browser.close()


if __name__ == '__main__':
    main()
