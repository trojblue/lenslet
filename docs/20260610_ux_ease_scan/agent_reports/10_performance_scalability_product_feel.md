# Performance/Scalability Product Feel Scan

## Journeys Inspected

- Cold browse startup for local directories and preindex-backed storage, including the split between CLI/pre-server scanning and in-app indexing status.
- Large tree navigation and folder counts through `FolderTree`, recursive count queries, and backend browse query payloads.
- Normal folder/table browse with backend-owned `/folders/query` windows, infinite loading, filtering, sorting, and text search.
- Metric and categorical panels, including backend facets, incomplete populations, "show all" modes, derived score authoring, and derived metric ranking.
- Remote image sources through HTTP/S3 reads, thumbnail generation, direct original URLs, proxied originals, request budgeting, and client/server caches.
- Grid scrolling and perceived thumbnail load behavior through virtual rows, intersection-triggered thumbnail fetches, adjacent row prefetch, and request caps.
- Fullscreen viewer navigation, delayed loading indicator, original-image prefetch, zoom/pan behavior, and compare prefetch policy.
- Measurement and smoke validation through `window.__lensletBrowseHotpath`, `/health.hotpath`, and `scripts/browser/large_tree/smoke.py`.

## Current Strengths

- Normal browse has already moved to an authoritative backend query path. The UI no longer relies on first-page local filtering for folder/table membership and counts.
- Infinite query keys include path, recursive flag, filters, sort, text query, random seed, derived metric, and limit, which is the right foundation for stale-response control.
- Browser request budgets are explicit and conservative: `folders=2`, `thumb=6`, `file=3`, plus thumbnail queue caps and original-file prefetch caps.
- The grid virtualizes rendered rows and avoids fetching thumbnails while the user is actively scrolling, which protects responsiveness on large result sets.
- Blob caches deduplicate in-flight thumbnail/original requests and cap memory use separately for thumbnails and full files.
- Viewer navigation feels more polished than grid loading: it delays the spinner briefly, avoids showing stale images for the wrong path, and prefetches adjacent originals within bounded offsets.
- Backend media paths reuse HTTP and S3 clients, cancel queued/in-flight thumbnail work on disconnect, and expose useful hot-path counters through health.
- Metrics panels avoid presenting loaded-window filtered counts as truth when population is incomplete, and table facets can come from row-level backend summaries.
- Large-tree smoke coverage already measures first grid, first thumbnail, frame gaps, request-budget peaks, and optional metric sort/filter behavior.

## Ranked Opportunities

### 1. Replace 50k metric-sort hydration with a smaller authoritative page plus rail summaries

- Severity: High.
- User impact: A metric sort currently asks for `BACKEND_BROWSE_METRIC_SORT_LIMIT = 50_000` items. That can make a "sort by score" feel like the app froze because the first response, JSON parse, React state, adaptive layout, metric rail, and selection maps all scale with that inflated window.
- Likely code area: `frontend/src/api/folders.ts`, `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/features/browse/components/MetricScrollbar.tsx`, `src/lenslet/storage/table/storage.py`, `src/lenslet/browse/query.py`.
- Fix concept: Keep browse pages near the normal 1k size for metric sorts. Feed the metric rail from backend facet histograms/quantiles plus a narrow "jump to nearest metric value" or offset seek path, rather than hydrating tens of thousands of item payloads.
- Effort: M/L.
- Performance/code-bloat risk: Medium. The risk is replacing one blunt large payload with too many small endpoints. Keep the contract narrow: sorted page windows plus metric summary/seek only.
- Validation method: Add a large table smoke where metric sort first page payload stays bounded, first grid and first thumbnail stay under the current primary thresholds, max frame gap remains under 700 ms, and request-budget peaks do not increase.

### 2. Add query-transition feedback for slow filter, sort, and search changes

- Severity: High.
- User impact: The grid only shows the centered loading panel when not in similarity mode, not searching, zero items, and `isLoading`. Slow text search or rapid backend filter/sort changes can feel empty or stale without explaining that the backend is computing authoritative results.
- Likely code area: `frontend/src/app/model/loadingState.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/app/components/GridTopStack.tsx`.
- Fix concept: Preserve useful previous results visually but mark them as updating after a short delay, with a compact top/bottom status such as "Filtering 16,320 items..." or "Searching current scope...". Counts should remain clearly stale until the new `request_token` response lands.
- Effort: S/M.
- Performance/code-bloat risk: Low if it reuses existing query state and does not add a global loading system.
- Validation method: Browser test with delayed `/folders/query` for search and categorical filter; assert old grid remains usable but visibly non-authoritative, then count/grid update atomically when the response lands.

### 3. Give thumbnail cards real placeholder, queued, and error states

- Severity: High.
- User impact: `ThumbCard` renders blank surface cards until a blob URL arrives, and `useBlobUrl` silently ignores fetch errors. On remote images or slow thumbnail generation, users see empty cards with no distinction between queued, loading, broken, or not yet intersected.
- Likely code area: `frontend/src/features/browse/components/ThumbCard.tsx`, `frontend/src/shared/hooks/useBlobUrl.ts`, `frontend/src/api/client.ts`.
- Fix concept: Return lightweight status from the blob hook, then show stable per-card placeholders using known dimensions/name, a delayed loading affordance only after a threshold, and a small failed-thumbnail state with retry-on-open behavior.
- Effort: S/M.
- Performance/code-bloat risk: Low. Avoid animated skeletons on every visible card; use CSS-only static placeholders or delayed minimal indicators.
- Validation method: Route selected `/thumb` requests through a Playwright delay/failure handler and verify cards do not collapse, do not spin immediately, and expose a recoverable error state without increasing request concurrency.

### 4. Show visible load-more progress at the grid boundary

- Severity: Medium.
- User impact: Infinite paging triggers automatically near the end, but `isLoadingMore` is only exposed as `aria-busy`. Users scrolling large filtered results get no clear indication that the next authoritative page is in flight.
- Likely code area: `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/app/AppShell.tsx`, `frontend/src/app/hooks/useAppDataScope.ts`.
- Fix concept: Add a non-intrusive bottom sentinel or status strip: loaded count, filtered total, and "Loading more..." while the next page is fetching. Keep it outside virtual row measurement or with stable height to avoid scroll jumps.
- Effort: S.
- Performance/code-bloat risk: Low.
- Validation method: Use a small backend page fixture, scroll near the end, delay the next page, and assert the sentinel appears without layout jump or duplicate requests.

### 5. Distinguish "facets loading" from "no metric values"

- Severity: Medium/High.
- User impact: When Metrics opens on a large incomplete population and facets are still loading, metric/categorical cards can fall back to empty maps and say "No values found" even though authoritative distributions are just pending.
- Likely code area: `frontend/src/app/AppShell.tsx`, `frontend/src/app/components/LeftSidebar.tsx`, `frontend/src/features/metrics/MetricsPanel.tsx`, `MetricRangePanel.tsx`, `CategoricalPanel.tsx`.
- Fix concept: Thread `facetsLoading` and `facetsError` into the metrics panels. Show a compact loading placeholder for distributions while retaining metric/categorical selectors from browse keys. Only show "No values found" after facets or complete local population prove it.
- Effort: S.
- Performance/code-bloat risk: Low.
- Validation method: Mock delayed `/folders/facets` with known metric keys; assert the panel says distributions are loading, not empty, then renders the authoritative facet values.

### 6. Virtualize or progressively reveal large folder sibling lists

- Severity: Medium/High.
- User impact: Folder data is lazily fetched by expansion, but rendering is recursive and not virtualized. A root with thousands of sibling folders can still mount thousands of `TreeNode` components and count badges, making navigation feel heavy before images load.
- Likely code area: `frontend/src/features/folders/FolderTree.tsx`, `frontend/src/features/folders/hooks/useFolderTreeKeyboardNav.ts`, `frontend/src/api/folders.ts`.
- Fix concept: Flatten expanded visible nodes into a virtualized tree when node count crosses a threshold. Keep recursive counts lazy and show count placeholders, not immediate count fan-out.
- Effort: M.
- Performance/code-bloat risk: Medium. Tree virtualization can complicate keyboard navigation; preserve the existing tree semantics and test focus movement.
- Validation method: Fixture with 10k folders at root; measure time to first usable tree interaction, React commit duration, and frame gaps while expanding/collapsing.

### 7. Communicate expensive backend ranking and derived-score operations

- Severity: Medium.
- User impact: Backend derived metrics now provide correct global sort/filter semantics, but table query execution builds records across the scope before slicing. For large tables, "Rank by score" may be correct but feel unexplained.
- Likely code area: `frontend/src/features/metrics/components/DerivedScoreCard.tsx`, `frontend/src/app/hooks/useAppDataScope.ts`, `src/lenslet/storage/table/storage.py`, `src/lenslet/browse/query.py`.
- Fix concept: Treat rank/filter actions as explicit expensive operations: show "Ranking across N items" when they trigger backend query work, and expose completion via updated counts. Longer term, add backend timing counters for query evaluation stages.
- Effort: S for UI feedback, M for backend stage timings.
- Performance/code-bloat risk: Low for feedback, medium if adding detailed instrumentation. Keep timings coarse.
- Validation method: Delay or instrument derived metric query; assert the UI differentiates draft-local preview from backend-applied global rank and does not double-submit.

### 8. Add slow remote original fallback and error recovery in the viewer

- Severity: Medium.
- User impact: Direct HTTP originals reduce backend load, but failed direct image loads have no `onError` fallback or visible recovery. A remote CORS/auth/network issue can look like an endless viewer load.
- Likely code area: `frontend/src/features/viewer/Viewer.tsx`, `frontend/src/features/media/originalImageResource.ts`, `frontend/src/api/client.ts`.
- Fix concept: On direct image error, show a small inline failure state and offer automatic or one-click proxied retry when `proxyHttpOriginals` is available. Keep direct loading as the default to avoid extra backend load.
- Effort: S/M.
- Performance/code-bloat risk: Low if fallback only fires after failure.
- Validation method: Playwright block/fail direct original URL while `/file` succeeds; assert the viewer recovers and request-budget file concurrency remains bounded.

### 9. Keep server-side abandoned query work from piling up during rapid view changes

- Severity: Medium.
- User impact: The browser bridges abort signals and limits folder requests, but heavy synchronous backend table scans may continue after the client has moved on. Rapid filter/sort/search changes can leave the server doing useful-but-stale work.
- Likely code area: `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/api/folders.ts`, `src/lenslet/web/routes/folders.py`, `src/lenslet/storage/table/storage.py`.
- Fix concept: Coalesce high-cost query triggers on the frontend where practical, and add coarse backend cancellation checkpoints for long table query loops if the route becomes async. Do not delay simple navigation or committed filter clicks unnecessarily.
- Effort: M.
- Performance/code-bloat risk: Medium. Cancellation can overcomplicate sync FastAPI routes; start with measured frontend coalescing and server timing evidence.
- Validation method: Fire rapid sort/filter changes against a large table, then inspect `/health.hotpath` or added query timing counters to prove stale work and p95 query latency do not grow.

### 10. Progressive startup needs to cover pre-server preindex work, not just in-app indexing

- Severity: Medium.
- User impact: Local preindex scanning/building happens before the web app is usable, while the in-app status bar only reports indexing after the app loads. On large local directories, the user's first experience may be waiting at the terminal or a not-yet-ready URL.
- Likely code area: `src/lenslet/storage/local/preindex.py`, `src/lenslet/web/app/local.py`, `src/lenslet/cli/browse.py`, `frontend/src/app/components/StatusBar.tsx`.
- Fix concept: Short term, improve CLI progress wording and ETA-style phases for scan, preindex, and warmup. Medium term, serve a minimal shell earlier with a read-only startup/indexing state if architecture allows.
- Effort: S for CLI progress copy, L for early web shell.
- Performance/code-bloat risk: Low for copy, high for early shell if it forks startup architecture. Do the copy first.
- Validation method: Cold run against the 40k fixture and a larger local tree; record time to URL printed, time to `/health`, and time to first grid.

### 11. Make request-budget pressure visible only when it affects the user

- Severity: Medium.
- User impact: Lenslet already measures request-budget inflight/queued state, but users only see blank thumbnails or delayed pages. A subtle "thumbnails queued" state after a threshold would explain slow remote browsing without encouraging higher concurrency.
- Likely code area: `frontend/src/api/requestBudget.ts`, `frontend/src/lib/browseHotpath.ts`, `ThumbCard.tsx`, `VirtualGrid.tsx`.
- Fix concept: Subscribe to request-budget snapshots in UI only for delayed states. Show aggregate pressure in a small non-blocking status, not per-request noise.
- Effort: M.
- Performance/code-bloat risk: Low/medium. Avoid a chatty global observable that rerenders the whole app on every request transition.
- Validation method: Throttle `/thumb` and scroll a remote table; assert the indicator appears after the delay and React render counts stay bounded.

### 12. Add performance budgets for Metrics "show all" and high-cardinality categorical views

- Severity: Medium.
- User impact: Metrics "show all" renders every metric or categorical card, and categorical cards render every value inside a scroll area. Facets keep backend work sane, but the panel can still become frontend-heavy with many columns or high-cardinality values.
- Likely code area: `frontend/src/features/metrics/MetricRangePanel.tsx`, `CategoricalPanel.tsx`, `CategoricalCard.tsx`, `MetricHistogramCard.tsx`, `DerivedScoreCard.tsx`.
- Fix concept: Use progressive disclosure: cap initial cards/values, searchable selection first, and "show more values" inside high-cardinality cards. Avoid rendering dozens of SVG histograms or thousands of categorical buttons at once.
- Effort: M.
- Performance/code-bloat risk: Medium. Keep the model simple and avoid a second virtual-list abstraction unless measurement proves it is needed.
- Validation method: Synthetic facets with 100 metrics and 10k categorical values; measure open latency, React commit time, and frame gaps before and after.

## Measurement Suggestions

- Keep `python -m scripts.browser.large_tree.smoke --dataset-dir data/fixtures/large_tree_40k` as the primary regression gate for first grid, first thumbnail, frame gaps, and request-budget peaks.
- Add a large table profile that exercises metric sort, derived rank, categorical filter, and text search over a scoped table with at least 50k rows.
- Capture payload bytes and server duration for `/folders/query` and `/folders/facets`, especially metric sort and derived rank. User feel depends on time to first authoritative count, not only time to first thumbnail.
- Add a remote-source smoke with delayed `/thumb` and `/file`, direct original failure, and proxied retry. Measure first visible placeholder, first real thumbnail, and viewer recovery.
- Use React Profiler or a lightweight browser probe for Metrics "show all", folder tree expansion, and adaptive layout after multiple page loads.
- Record cold and warm startup separately: time to URL printed, time to `/health`, first grid, first thumbnail, and final indexing ready.

## 3 Quick Wins

1. Thread `facetsLoading` into Metrics and show "Loading distributions..." instead of "No values found" while backend facets are pending.
2. Add a visible bottom load-more sentinel with loaded/filtered counts for infinite browse pages.
3. Teach `useBlobUrl` and `ThumbCard` to expose delayed loading and error states with stable placeholders.

## 3 Medium Projects

1. Remove the 50k metric-sort hydration path by splitting sorted browse pages from metric rail summary/seek behavior.
2. Virtualize large folder trees and keep recursive counts lazy with placeholders.
3. Add query-stage timing and slow-operation UX for backend browse queries, derived ranking, and large facet builds.

## Things Not To Do

- Do not raise page sizes or the 50k metric-sort limit to hide pagination issues.
- Do not reintroduce frontend-local authoritative filtering/sorting for normal folder/table browse.
- Do not show loaded-window facet counts as if they are global filtered counts.
- Do not add unbounded thumbnail/original prefetch or increase request budgets as the first fix for blank-feeling remote views.
- Do not replace useful previous grid content with a full-screen spinner for every filter or search transition.
- Do not render every metric, categorical field, value, folder, or histogram just because the backend can provide the data.
- Do not add a broad state library or telemetry dashboard for these issues; most fixes can reuse existing query state and hot-path metrics.
- Do not probe remote images from the frontend to compensate for backend metadata gaps.

## Top 5 Recommendations

1. Decouple metric-sort browsing from the 50k hydrated payload.
2. Add honest query-transition feedback for slow filter, sort, and search operations.
3. Fix Metrics pending-facet states so loading is not presented as empty data.
4. Add stable thumbnail placeholders plus delayed loading/error states for remote and slow media.
5. Virtualize large folder trees and validate with the existing large-tree smoke plus a high-sibling-count folder fixture.
