# Browse/Grid Smoothness Codepath Scan

## Scope And Files Inspected

This scan focused on browse/grid/viewer smoothness from the React codepaths, not visual redesign. I treated the browse `Viewer` overlay as the app's fullscreen viewer path; I did not find browser Fullscreen API usage in the browse gallery. No internet search was used.

Primary files inspected:
- `frontend/src/app/AppShell.tsx`
- `frontend/src/app/hooks/useAppDataScope.ts`
- `frontend/src/app/hooks/useAppSelectionViewerCompare.ts`
- `frontend/src/app/hooks/useAppHashRouting.ts`
- `frontend/src/app/hooks/useFolderSessionState.ts`
- `frontend/src/features/browse/components/VirtualGrid.tsx`
- `frontend/src/features/browse/components/VirtualGridRows.tsx`
- `frontend/src/features/browse/components/ThumbCard.tsx`
- `frontend/src/features/browse/components/MetricScrollbar.tsx`
- `frontend/src/features/browse/hooks/useVirtualGrid.ts`
- `frontend/src/features/browse/hooks/useKeyboardNav.ts`
- `frontend/src/features/browse/model/virtualGridSession.ts`
- `frontend/src/features/browse/model/virtualGridPrefetch.ts`
- `frontend/src/features/browse/model/prefetchPolicy.ts`
- `frontend/src/features/browse/model/metricRail.ts`
- `frontend/src/features/media/originalImageResource.ts`
- `frontend/src/shared/hooks/useBlobUrl.ts`
- `frontend/src/lib/blobCache.ts`
- `frontend/src/api/client.ts`
- `frontend/src/api/folders.ts`
- `frontend/src/api/requestBudget.ts`

Validation/probe files sampled:
- `scripts/browser/gui_smoke/scenarios.py`
- `scripts/browser/gui_smoke/acceptance.py`
- `scripts/browser/viewer_probe/flicker_back.py`
- `scripts/browser/viewer_probe/open.py`
- `scripts/browser/viewer_probe/back.py`
- `scripts/browser/large_tree/smoke.py`
- Focused frontend tests under `frontend/src/features/browse/model/__tests__`, `frontend/src/features/browse/components/__tests__`, `frontend/src/app/hooks/__tests__`, and `frontend/src/api/__tests__`.

## Concise Architecture Map

- `AppShell` owns app-level browse state, current folder, selected paths, viewer/compare state, prefetch effects, and wires `VirtualGrid`, `MetricScrollbar`, and `Viewer`.
- `useAppDataScope` owns backend browse data. It uses `useBrowseQuery` over `/folders/query` as an infinite query, with a normal page size of 1000 and a metric-sort page size of 50000.
- `VirtualGrid` owns virtualized grid behavior: layout selection, keyboard navigation, load-more trigger, active/focused cell state, hover preview, visible path reporting, and scroll restoration tokens.
- `useVirtualGrid` wraps `@tanstack/react-virtual` and computes either fixed grid rows or adaptive rows.
- `ThumbCard` uses an `IntersectionObserver`, `useBlobUrl`, `api.getThumb`, `thumbCache`, and request budgets. It delays requests while scrolling unless the card is marked priority.
- `Viewer` uses direct HTTP originals when allowed, otherwise `api.getFile` through `fileCache` and `useBlobUrl`. It intentionally avoids rebinding the previous blob URL to a new path.
- `AppShell` prefetches adjacent viewer and compare full files via fixed offsets, plus thumbs.
- `MetricScrollbar` is entirely client-side over currently loaded `items`: it computes finite metric values, histogram bins, quantiles, current marker, and click-to-jump target.

## Ranked Findings

1. **High: Viewer next/prev can show an empty surface while the next original loads.**
   - **User impact:** Moving next/prev can feel like flicker or a broken viewer on slow originals. The code avoids showing the wrong stale image, which is correct for trust, but the result can be a blank panel until the new image is ready.
   - **Likely root file(s):** `frontend/src/features/viewer/Viewer.tsx:75-86`, `frontend/src/features/viewer/Viewer.tsx:140-177`, `frontend/src/shared/hooks/useBlobUrl.ts:70-104`.
   - **Suggested fix shape:** Keep explicit viewer resource state with `current`, `loading`, and optionally `previousVisual` or `nextThumbVisual`. Do not label the previous image as the current path. A conservative approach is to keep the previous image visually dimmed/aria-hidden behind a spinner until the next image is ready, or show the selected thumbnail for the next path while the original loads.
   - **Effort:** M.
   - **Performance/code-bloat risk:** Low if limited to one previous visual resource; high if this becomes a carousel/cache subsystem.
   - **Validation method:** Extend `python -m scripts.browser.viewer_probe.flicker_back --mode viewer` with delayed `/file` next/prev sampling. Assert no sequence has zero visible image-like pixels for more than a small frame budget, and assert the visible image is not exposed as the wrong current path.

2. **High: Deep image hash/viewer restore only works once the image path is in the loaded browse window.**
   - **User impact:** A direct deep link to `#!/some/deep/image.jpg` can open the viewer, but closing may not restore the grid to that item if it is beyond loaded pages. This undermines "Back to grid" trust on large folders.
   - **Likely root file(s):** `frontend/src/app/hooks/useAppSelectionViewerCompare.ts:190-201`, `frontend/src/app/hooks/useAppSelectionViewerCompare.ts:218-229`, `frontend/src/features/browse/components/VirtualGrid.tsx:537-573`, `frontend/src/app/hooks/useAppDataScope.ts:371-379`.
   - **Suggested fix shape:** Add a backend browse "window around path" or "resolve path index in current query" capability, then hydrate a page around the viewer path before restore. Keep the hard cutover: no client-side scan through every page.
   - **Effort:** L.
   - **Performance/code-bloat risk:** Medium. The right solution is a narrow backend window query, not a client loop that fetches pages until the item appears.
   - **Validation method:** Add a browser smoke fixture with more than one browse page, open a hash for an item past page 1, close viewer, and assert the grid cell is visible, focused, selected, and the scroll position is stable.

3. **High: Metric scrollbar looks authoritative but is built from currently loaded client items.**
   - **User impact:** For metric-sorted scopes larger than the hydrated set, the rail can imply it represents the whole distribution and jump space when it only sees loaded rows.
   - **Likely root file(s):** `frontend/src/app/AppShell.tsx:1227-1234`, `frontend/src/features/browse/components/MetricScrollbar.tsx:34-45`, `frontend/src/features/browse/components/MetricScrollbar.tsx:75-110`, `frontend/src/app/hooks/useAppDataScope.ts:194-205`.
   - **Suggested fix shape:** Make the rail backend-owned: return full-scope metric rail summaries from facets/query metadata and add a backend jump/window-by-metric endpoint. Until then, gate the rail behind "population complete" or visibly mark it as loaded-subset only.
   - **Effort:** L.
   - **Performance/code-bloat risk:** Medium. Avoid a fancy interactive custom scrollbar that requires loading all rows into React.
   - **Validation method:** Fixture with `filtered_total > BACKEND_BROWSE_METRIC_SORT_LIMIT` and metric values outside the first hydrated window. Confirm rail labels/jumps do not misrepresent unloaded values.

4. **High: Metric sort hydrates up to 50000 items into React and then recomputes rail data client-side.**
   - **User impact:** Sorting by metric can feel dramatically slower than normal browse, especially with thumbnails, derived metrics, inspector data, and the rail all depending on the large `items` array.
   - **Likely root file(s):** `frontend/src/api/folders.ts:20-21`, `frontend/src/app/hooks/useAppDataScope.ts:194-205`, `frontend/src/app/hooks/useAppDataScope.ts:335-363`, `frontend/src/features/browse/model/metricRail.ts:16-32`, `frontend/src/features/browse/model/metricRail.ts:55-73`.
   - **Suggested fix shape:** Keep normal browse page size bounded and move metric rail/jump data to backend summaries. If a short-term guard is needed, cap metric-hydrate lower and disable rail jump when incomplete.
   - **Effort:** M to L.
   - **Performance/code-bloat risk:** High if solved by raising limits or memoizing everything. Lower risk if the data contract changes so React receives less data.
   - **Validation method:** Run `python -m scripts.browser.large_tree.smoke --dataset-dir data/fixtures/large_tree_40k` with a metric sort scenario and assert max frame gap, first visible grid, request budgets, and memory do not regress.

5. **Medium: Thumbnail requests are blocked while scrolling, so fast scrolls can reveal empty cards.**
   - **User impact:** The grid can feel hollow during fast scroll or slow disk/network loads: visible cards may show only the surface background until scrolling stops and fetches complete.
   - **Likely root file(s):** `frontend/src/features/browse/components/ThumbCard.tsx:69-78`, `frontend/src/features/browse/components/VirtualGrid.tsx:230-247`, `frontend/src/features/browse/components/VirtualGrid.tsx:589-594`.
   - **Suggested fix shape:** Keep the request budget but let actually visible rows request thumbnails during scrolling through a small rAF/idle-throttled queue. Continue to defer offscreen prefetch. Distinguish "visible demand load" from "nice-to-have adjacent prefetch."
   - **Effort:** M.
   - **Performance/code-bloat risk:** Medium. Raising thumb concurrency globally would be the brittle fix; a demand-vs-prefetch split is cleaner.
   - **Validation method:** Playwright fast-scroll probe with delayed `/thumb`. Measure visible blank card duration and request-budget peak/queue counts before and after.

6. **Medium: Priority thumbnail loading may target an overscan row instead of the first actually visible row.**
   - **User impact:** First visible thumbnails can be delayed while offscreen overscan cards are marked priority.
   - **Likely root file(s):** `frontend/src/features/browse/components/VirtualGridRows.tsx:167-178`, `frontend/src/features/browse/components/VirtualGridRows.tsx:261-275`, `frontend/src/features/browse/hooks/useVirtualGrid.ts:76-83`.
   - **Suggested fix shape:** Compute priority from row start/end against the grid scrollTop/clientHeight, or pass the actual top visible row from `VirtualGrid` using the existing top-visible-row logic. Keep it local; no new global scheduler is needed.
   - **Effort:** S.
   - **Performance/code-bloat risk:** Low.
   - **Validation method:** Unit-test priority row selection with overscan rows before the viewport, plus browser evidence that the first viewport row requests before overscan rows.

7. **Medium: Load-more is invisible and failure/slow states are not trustworthy.**
   - **User impact:** At the end of a loaded window, users get no stable "loading more", "retry", or "end" affordance. If the next page is slow or fails, the gallery can look like the true end.
   - **Likely root file(s):** `frontend/src/features/browse/components/VirtualGrid.tsx:325-336`, `frontend/src/app/hooks/useAppDataScope.ts:371-379`, `frontend/src/features/browse/components/VirtualGrid.tsx:653-728`.
   - **Suggested fix shape:** Add a virtualized bottom sentinel/footer row that does not shift layout: loading more, failed/retry, or end. Keep auto-load-more, but make state visible and keyboard/screen-reader reachable.
   - **Effort:** S to M.
   - **Performance/code-bloat risk:** Low if it is just one virtual footer item; avoid a separate pagination panel.
   - **Validation method:** Mock `fetchNextPage` delay and failure in a component test, then run a browser scroll-to-end smoke that asserts footer state and retry behavior.

8. **Medium: Keyboard navigation scrolls the target row to the top, causing jumps.**
   - **User impact:** Arrowing one row below the viewport can jump the selected row to the top instead of the nearest visible position, which feels less stable than native list navigation.
   - **Likely root file(s):** `frontend/src/features/browse/components/VirtualGrid.tsx:198-218`, `frontend/src/features/browse/components/VirtualGrid.tsx:519-530`.
   - **Suggested fix shape:** Use nearest-edge scrolling: if row top is above viewport, scroll to rowTop; if row bottom is below viewport, scroll to `rowBottom - clientHeight`. Keep smooth animation optional or remove it for reduced motion.
   - **Effort:** S.
   - **Performance/code-bloat risk:** Low.
   - **Validation method:** Unit-test scroll target math and browser-test repeated ArrowDown/ArrowUp with max scroll delta bounded to roughly one row unless jumping across larger gaps.

9. **Medium: Grid keyboard navigation still does O(n) path lookup per keypress despite having path indexes.**
   - **User impact:** In hydrated metric views, held-arrow navigation can stutter because `findIndex`/`find` scans the item list repeatedly.
   - **Likely root file(s):** `frontend/src/features/browse/hooks/useKeyboardNav.ts:4-18`, `frontend/src/features/browse/components/VirtualGrid.tsx:500-535`.
   - **Suggested fix shape:** Change key navigation helpers to accept `pathToIndex` or current index, and use direct index access for `nextItem`. This is a small hard cutover, not a new state model.
   - **Effort:** S.
   - **Performance/code-bloat risk:** Low.
   - **Validation method:** Focused unit tests for navigation parity plus a microbenchmark or browser keyboard-repeat sample over 50000 items.

10. **Medium: Direct HTTP originals skip adjacent viewer prefetch.**
   - **User impact:** Remote HTTP/S table sources in direct mode can flicker on next/prev even though local/proxied originals get adjacent full-file prefetch.
   - **Likely root file(s):** `frontend/src/app/AppShell.tsx:132-143`, `frontend/src/app/AppShell.tsx:891-898`, `frontend/src/features/media/originalImageResource.ts:12-21`.
   - **Suggested fix shape:** For direct HTTP originals, use browser-native image prewarming (`new Image().src = url` or `<link rel="prefetch">`) under the same adjacent offsets and a small cap. Keep proxy/fileCache behavior unchanged.
   - **Effort:** S to M.
   - **Performance/code-bloat risk:** Medium. Respect CORS/cache behavior and do not prefetch a large remote range.
   - **Validation method:** Browser probe with delayed remote/direct image URLs and `proxyHttpOriginals=false`; assert the next image is warm after dwell on current.

11. **Medium: Thumbnail and hover fetch failures are silent blank surfaces.**
   - **User impact:** A missing/corrupt/slow image looks like an empty card or non-responsive preview, not a trustworthy load failure.
   - **Likely root file(s):** `frontend/src/shared/hooks/useBlobUrl.ts:70-104`, `frontend/src/features/browse/components/ThumbCard.tsx:80-131`, `frontend/src/api/client.ts:633-641`.
   - **Suggested fix shape:** Give `useBlobUrl` a minimal status return or add a local error state in `ThumbCard` and hover preview. Render a stable icon/label after failure and a retry-on-interaction path. Do not add a global error framework.
   - **Effort:** S to M.
   - **Performance/code-bloat risk:** Low.
   - **Validation method:** Mock 404/500 `/thumb` and `/file` hover responses in component tests and browser smoke. Assert no layout shift and visible failure state.

12. **Low to Medium: Hover preview full-file fetches are intentionally uncached, which can repeat work.**
   - **User impact:** Re-hovering the same item can refetch the original unless it is already in `fileCache` from viewer/compare. This can compete with viewer loads on slow sources.
   - **Likely root file(s):** `frontend/src/features/browse/components/VirtualGrid.tsx:285-312`, `frontend/src/api/client.ts:633-641`, `frontend/src/lib/blobCache.ts:36-68`.
   - **Suggested fix shape:** Add a tiny separate hover-preview LRU or store successful hover blobs in a small cache that is not shared with abortable viewer loads. Prefer using the already-cached thumbnail as the immediate preview while the original warms.
   - **Effort:** M.
   - **Performance/code-bloat risk:** Medium. A second cache can become complexity unless it has strict byte/item limits and clear ownership.
   - **Validation method:** Hover same item repeatedly with request logging and verify one full-file request within cache TTL/limit; ensure aborting hover does not abort viewer loads.

13. **Low to Medium: Top-anchor persistence is row-based, not actual DOM-visible-cell based.**
   - **User impact:** Folder re-entry can restore near the right place but miss the exact top-left visible image after adaptive layout shifts, top-stack changes, or overscan differences.
   - **Likely root file(s):** `frontend/src/features/browse/components/VirtualGrid.tsx:608-629`, `frontend/src/features/browse/model/virtualGridSession.ts:93-135`, `scripts/browser/gui_smoke/acceptance.py:146-149`.
   - **Suggested fix shape:** Reuse the existing `getTopAnchorPathForVisibleCells` helper with throttled DOM measurement after scroll idle or before folder switch. Keep the current row-based path as fallback.
   - **Effort:** M.
   - **Performance/code-bloat risk:** Medium if measuring every scroll event. Low if measured only after scroll idle and before navigation.
   - **Validation method:** Strengthen the existing folder re-entry smoke so `anchor_reentry_exact` is a hard pass for stable fixtures, then test adaptive rows and top-stack height changes.

## 3 Quick Wins

1. Fix keyboard navigation to use nearest-edge scrolling and `pathToIndex` instead of O(n) scans.
2. Compute `ThumbCard` priority from the first actually visible row, not `virtualRows[0]`.
3. Add stable thumbnail failure/long-loading states so blank cards do not look like missing content.

## 3 Medium Projects

1. Redesign viewer image resource state for no-blank next/prev transitions while preserving truthful current-path semantics.
2. Move metric rail distribution and jump semantics to backend-owned full-scope data instead of hydrating 50000 rows into React.
3. Add path-centered browse windows for deep links and viewer close restoration in large folders.

## Things Not To Do

- Do not replace `@tanstack/react-virtual` with a custom virtualizer for these issues.
- Do not raise thumbnail/file request budgets globally to hide scheduling problems.
- Do not prefetch all originals in a folder or all metric-sorted rows for smoothness.
- Do not show a stale previous original as if it were the current viewer path.
- Do not make the metric rail look like a real scrollbar if it only represents loaded rows.
- Do not add a global image state library for local resource lifecycle problems.
- Do not animate scroll restoration after closing viewer; restoration should be exact and quiet.
- Do not reintroduce client-owned browse truth for filtering/sorting/counts.

## Top 5 Recommendations

1. Make viewer next/prev transitions non-blank with explicit previous/current/loading resource state.
2. Replace client-hydrated metric rail truth with backend rail summaries and path-centered jump windows.
3. Add backend support for restoring/deep-linking to a path outside the loaded browse window.
4. Split thumbnail demand loading from prefetch so visible rows load during scroll without flooding requests.
5. Fix small trust details: nearest keyboard scroll, O(1) key navigation lookup, true priority row selection, and visible load-more/error states.
