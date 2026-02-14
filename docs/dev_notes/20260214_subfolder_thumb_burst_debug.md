# 2026-02-14 Subfolder Thumbnail Burst Debug (Headless Browser Run)

## Summary

This documents the root-cause debug session for:

- root view initially smooth
- entering a subfolder causes continuous thumbnail request bursts + high CPU
- returning to root inherits the same behavior
- scrollbar/position indicator looked wrong in subfolders (looked like a tiny dataset even when very large)

This bug was finally fixed only after instrumenting with a headless browser. Prior terminal-only/reasoning-only attempts changed data loading but did not remove the burst loop.

## Why Earlier Attempts Missed

Earlier fixes focused on request/data scope (recursive payload handling, cache retention behavior). That was directionally reasonable, but it did not inspect:

- actual rendered grid viewport height
- rendered cell count
- live request-budget queue growth (`window.__lensletBrowseHotpath.requestBudget`)

Without browser-side DOM + runtime telemetry, we were fixing likely causes instead of the actual trigger.

## Headless Repro Workflow

1. Run Lenslet on a free port (used `7092`, then `7094` after restart):
   - `python -m lenslet.cli /data/yada/data/dit03_hps_csway --port 7092`
2. Wait for `/health` indexing state `ready`.
3. Run Playwright script that performs:
   - open `#/`
   - click `base_spine`
   - click back to root tree item
   - collect `/thumb` request activity and `window.__lensletBrowseHotpath.requestBudget`
   - collect DOM geometry (`grid.clientHeight`, rendered `gridcell` count)

## Findings (Before Fix)

### 1) The burst was real and sustained

During root -> subfolder -> root:

- thumb queue climbed to ~`8209` with inflight pinned at `6`
- queue drained slowly while CPU remained high

### 2) The viewport geometry was broken after navigation

Captured after reproducing:

- `grid clientHeight`: ~`320162`
- rendered `gridcell` count: ~`8365`
- `app-shell scrollHeight`: ~`320257`

Expected was a bounded viewport close to window height (~`900-1000px`), not hundreds of thousands of pixels.

### 3) Root cause was layout track expansion, not only API/query behavior

The second row of `.app-shell` could expand to min-content height after navigation. Once that happened, virtualized rendering effectively over-rendered massively, and thumbnail loading attempted to fill the huge viewport.

## Fix

File changed: `frontend/src/styles.css`

```css
.app-shell {
  grid-template-rows: var(--toolbar-h) minmax(0, 1fr);
}

.grid-shell {
  min-height: 0;
  padding-bottom: var(--mobile-drawer-h);
}
```

Key point:

- `minmax(0, 1fr)` prevents row-2 min-content expansion in CSS Grid.
- `min-height: 0` ensures the inner flex/grid container can shrink instead of forcing parent growth.

## Verification (After Fix)

Same scripted flow (root -> subfolder -> root), on rebuilt frontend assets:

- `grid clientHeight`: ~`905`
- rendered `gridcell` count: `84`
- thumb request queue: `0`
- no sustained burst pattern observed

This matched expected behavior: bounded viewport, bounded visible cells, bounded thumbnail fetches.

## Regression Note

This incident shows why browser-in-the-loop debugging is required for UI perf bugs:

- backend logs + request counts alone were insufficient
- the decisive signal was DOM geometry + live request-budget queue

For similar issues, start with an automated browser probe that captures:

1. viewport dimensions
2. rendered item count
3. request budget (`inflight`, `queued`, `peakInflight`)

before making data-layer changes.

