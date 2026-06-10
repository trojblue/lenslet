# Browse/Grid Product Feel Scan

## Journeys Inspected

- Gallery browse to selection to fullscreen viewer, then previous/next and exit back to the grid.
- Wheel and native scrollbar scrolling through the virtualized grid, including lazy thumbnail loading and load-more triggering.
- Metric rail activation under metric sort, hover/scrub behavior, and jump-to-metric selection restore.
- Sort changes across built-in, random, and metric sorts; filter changes through rating/filter chips and metrics panel; text search entry and clearing.
- Slow media behavior for thumbnails, hover previews, full-original viewer fetches, request budgeting, and prefetch cache reuse.
- Mobile and tablet paths: mobile drawer controls, search row, touch select/open, long-press actions, pinch grid resizing, phone viewer nav, and tablet/narrow toolbar behavior.

## Current Strengths

- The grid has the right foundation for professional continuity: virtualized rows, stable cell dimensions, top-anchor tracking, selected-path restore tokens, and per-folder top-anchor memory in `useFolderSessionState`.
- The viewer journey respects current gallery order. `useAppSelectionViewerCompare` freezes viewer nav paths on open, updates selection during next/previous, and restores focus to the navigated image on close.
- Media fetches are bounded. Thumbnail and full-file requests go through caches and request budgets, with adjacent thumbnail prefetch and viewer-neighbor prefetch already present.
- Selection has useful primitives: `aria-selected`, roving focus, selection-order badges, touch long-press actions, and mobile select mode.
- Layout already reserves key UI space. The metric rail slot remains mounted, top-stack bands reserve structure, and toolbar slots stay present when hidden, reducing some jitter.
- Viewer zoom/pan internals are strong: cursor-anchored wheel zoom, pinch zoom, drag suppression, resize center preservation, and toolbar zoom requests are implemented without a new interaction layer.

## Ranked Opportunities

### 1. Preserve context through sort, filter, layout, and size changes

- **Severity:** P1 High
- **User impact:** Users can lose their place when changing sort/filter/view mode or thumbnail size. The app already preserves context across folder re-entry and viewer close, so jumps here feel inconsistent and less professional.
- **File/code area:** `frontend/src/app/AppShell.tsx` around `handleSortChange`, `updateFilters`, `handleFiltersChange`, `handleClearFilters`, `setViewMode`, `setGridItemSize`; `frontend/src/features/browse/components/VirtualGrid.tsx` restore props and the keyed inner grid at line 667.
- **Fix concept:** Treat context preservation as a first-class browse invariant. Before changing sort/filter/layout/size, capture the selected path if present, otherwise the top anchor. After the new item window is available, bump the existing restore token and restore that path if it still exists. For layout/size changes, prefer top-anchor restore. For sort/filter/search changes, prefer selected-path restore, then top-anchor if still present. Remove or narrow the `key={`${viewMode}-${effectiveColumns}`}` remount if it is not required for virtualizer correctness.
- **Effort:** M
- **Performance/code-bloat risk:** Low if it reuses the existing restore-token path. Avoid a second scroll manager.
- **Validation method:** Add focused tests around `resolveVirtualGridRestoreDecision` for layout/filter/sort transitions, then a Playwright scenario that scrolls deep, changes view mode and thumbnail size, and asserts the same path remains visible without a top jump. Extend `scripts/browser/gui_jitter/grid.py` to record top visible path before/after sort/filter changes.

### 2. Keep slow thumbnails informative instead of blank

- **Severity:** P1 High
- **User impact:** During slow thumbnail fetches or errors, cards are empty surfaces with no state. Users cannot tell whether media is loading, missing, or failed.
- **File/code area:** `frontend/src/features/browse/components/ThumbCard.tsx`; `frontend/src/shared/hooks/useBlobUrl.ts`; CSS around thumbnail/card styles in `frontend/src/styles.css`.
- **Fix concept:** Add a lightweight in-card loading state and an error state using existing card dimensions: muted skeleton/placeholder until a URL is ready, fade to image on load, and a compact failed-thumbnail mark if fetch rejects. `useBlobUrl` currently catches and ignores errors, so expose a local status or wrap thumbnail fetching in `ThumbCard` with a tiny status state.
- **Effort:** S
- **Performance/code-bloat risk:** Low. Use CSS and existing request path; do not add a skeleton dependency.
- **Validation method:** Unit-test status transitions with mocked `api.getThumb`; Playwright route-delay `/thumb` and verify cards retain size, show loading affordance, then fade in without layout shift.

### 3. Make fullscreen next/previous feel continuous on slow originals

- **Severity:** P1 High
- **User impact:** On next/previous, `Viewer` resets readiness, clears `imageResource`, hides the image at opacity 0, and shows only a delayed spinner. With slow originals this feels like a blank-screen swap, even though neighbor prefetch exists.
- **File/code area:** `frontend/src/features/viewer/Viewer.tsx` around path reset, `imageResource`, `showDelayedLoader`, and `markImageReady`; `frontend/src/api/client.ts` full-file prefetch.
- **Fix concept:** Keep the last ready image visible under a subtle dim/loading overlay until the next image decodes, then crossfade. Show the next image filename or index in the existing viewer chrome only if needed for orientation. Reset zoom when the next image is ready, not while the surface is blank.
- **Effort:** M
- **Performance/code-bloat risk:** Medium if old object URLs are held too long. Use the current scheduled URL revoke pattern and cap the retained previous resource to one image.
- **Validation method:** Extend `scripts/browser/viewer_probe/flicker_back.py` with delayed file route on next/previous, sample frames, and assert no all-background frame between two ready images.

### 4. Add explicit empty states for zero results, unsupported query, and loading-more

- **Severity:** P1 High
- **User impact:** Empty search/filter results and unsupported derived-metric browse states can leave the grid feeling blank. Loading more is only exposed by `aria-busy`, so long paginated folders can look stalled at the bottom.
- **File/code area:** `frontend/src/app/model/loadingState.ts`; `frontend/src/app/AppShell.tsx` around `showGridLoading`, `browseQueryUnavailableReason`, `filteredCount`, `searching`; `frontend/src/features/browse/components/VirtualGrid.tsx` loading overlay.
- **Fix concept:** Split grid state into `initial-loading`, `empty-folder`, `empty-search`, `empty-filter`, `unsupported-view`, and `loading-more`. Render a compact grid-center state for zero items and a footer row for loading more. Include clear-search/clear-filters actions where already available, but keep copy terse.
- **Effort:** M
- **Performance/code-bloat risk:** Low. This is presentational state derived from existing booleans.
- **Validation method:** Add model tests for state resolution, then Playwright cases for empty search, empty filter, unsupported derived metric, and bottom pagination showing a footer.

### 5. Strengthen selection clarity, especially on touch

- **Severity:** P2 Medium
- **User impact:** On touch, the first tap selects and the second tap opens. That is sensible, but the selected state needs to be unmistakable because the old bottom selection bar is removed and a single selected image can look only subtly ringed.
- **File/code area:** `frontend/src/features/browse/components/ThumbCard.tsx`; `frontend/src/features/browse/components/VirtualGridRows.tsx`; `frontend/src/lib/mobileSelection.ts`; mobile drawer selected count in `frontend/src/shared/ui/Toolbar.tsx`.
- **Fix concept:** Make selected cards visually unmistakable without helper text: stronger ring contrast, a small check/order badge for single selection as well as multi-selection, and a brief press/selection feedback state on touch. Keep the existing two-tap model.
- **Effort:** S
- **Performance/code-bloat risk:** Low. CSS and existing selection props are enough.
- **Validation method:** Playwright mobile/coarse-pointer screenshot at 390px and 900px after first tap; assert selected cell is visible, `aria-selected=true`, and action button remains reachable.

### 6. Improve metric rail as a professional navigation control

- **Severity:** P2 Medium
- **User impact:** The metric rail is powerful but narrow and under-instrumented. It also appears authoritative even though it is built from currently loaded `items`; on large metric-sorted scopes this can mislead users about the full distribution. Scrubbing repeatedly scans items for closest value and triggers selection/restore on every pointer move, which can feel jumpy.
- **File/code area:** `frontend/src/features/browse/components/MetricScrollbar.tsx`; `frontend/src/features/browse/model/metricRail.ts`; `frontend/src/app/AppShell.tsx` `hasMetricScrollbar`, `metricsItemPopulationComplete`, and `handleMetricRailJump`.
- **Fix concept:** Keep the visual rail slim but widen the hit target. Until rail data is full-scope, gate or label the rail when `items.length < filteredCount`. Throttle scrubbing to one restore per animation frame. Add keyboard semantics (`role="slider"`, `aria-valuenow`, Home/End/PageUp/PageDown) and keep the value bubble visible while scrubbing. Optionally precompute sorted numeric path/value pairs for `closestMetricPathForValue` during active rail use.
- **Effort:** M
- **Performance/code-bloat risk:** Medium because naive scrubbing is O(n) per move today. A small memoized value index avoids heavy code and improves large-folder behavior.
- **Validation method:** Unit-test keyboard/value mapping and nearest-path lookup; Playwright drag the rail in a metric-sorted 10k fixture and assert frame-budget friendly selection changes and visible value feedback.

### 7. Show pending result updates without clearing the user's mental model

- **Severity:** P2 Medium
- **User impact:** Sort/filter/search changes can make the grid reorder or blank before the user gets feedback that results are updating. This is most noticeable with backend text search and metric filters.
- **File/code area:** `frontend/src/app/hooks/useAppDataScope.ts` browse load lifecycle; `frontend/src/app/AppShell.tsx` `searching`, `isLoading`, `isLoadingMoreFolderItems`; `frontend/src/app/components/GridTopStack.tsx`.
- **Fix concept:** Surface a small non-blocking "updating results" state in the top stack or grid overlay while a new browse request is pending and old items are still visible. Keep old results until the new first page arrives when React Query supports it, but visually mark them as updating.
- **Effort:** M
- **Performance/code-bloat risk:** Low if derived from current query flags. Avoid adding a separate async state machine.
- **Validation method:** Playwright route-delay `/browse/query`, change sort/filter/search, and assert old cells remain visible with a pending state until replacement.

### 8. Preserve selection and scroll context when entering and clearing search

- **Severity:** P2 Medium
- **User impact:** `searching` immediately clears selection and closes the viewer. Clearing the search does not explicitly restore the pre-search selection/top anchor, so exploratory search can feel destructive.
- **File/code area:** `frontend/src/app/AppShell.tsx` effect at lines 869-874; `useAppSelectionViewerCompare.clearViewerForSearch`; `useFolderSessionState` anchor helpers.
- **Fix concept:** Capture a pre-search context snapshot: selected path(s), viewer path if any, and top anchor. During search, suppress incompatible viewer/selection if needed, but restore the snapshot when the query is cleared and the paths still exist. If the selected item is filtered out, fall back to the old top anchor.
- **Effort:** M
- **Performance/code-bloat risk:** Low. Store a small ref; reuse existing restore token.
- **Validation method:** Playwright: select a mid-grid item, search for another item, clear search, assert the original selected/top path is visible and focused if still present.

### 9. Make viewer navigation affordances consistent across phone and tablet touch

- **Severity:** P2 Medium
- **User impact:** Phone gets bottom `Prev`/`Next`; tablet/narrow touch relies on toolbar nav. On touch tablets, top-right controls are less ergonomic for repeated image review.
- **File/code area:** `frontend/src/features/viewer/Viewer.tsx` mobile nav; `frontend/src/styles.css` `.viewer-mobile-nav` media rule; `frontend/src/shared/ui/Toolbar.tsx` `showToolbarNav`.
- **Fix concept:** Gate bottom viewer nav by coarse pointer or narrow/tablet layout rather than only `max-width: 480px`, while keeping it hidden on desktop mouse. Use icon buttons or compact labels and respect safe-area insets.
- **Effort:** S
- **Performance/code-bloat risk:** Low. This is CSS/media-query and existing `canPrev/canNext` props.
- **Validation method:** Extend `scripts/browser/overall_cleanup/mobile.py` with 768x1024 and 900x700 coarse-pointer contexts; assert bottom nav is visible or toolbar nav remains reachable with 44px targets.

### 10. Reduce grid row remount/fade flicker during layout changes

- **Severity:** P2 Medium
- **User impact:** View mode and column-count changes can rebuild the inner row tree, resetting thumbnail `loaded` state and causing visible fade/flicker even when images are cached.
- **File/code area:** `frontend/src/features/browse/components/VirtualGrid.tsx` inner `key`; `ThumbCard` URL/loaded state; `useVirtualGrid` measure effect.
- **Fix concept:** Avoid remounting rows solely to refresh virtualizer geometry. Prefer `rowVirtualizer.measure()` and anchor restore after geometry changes. If a remount is truly needed, preserve loaded thumbnail state by relying on cached image completion or moving the fade guard up one level.
- **Effort:** M
- **Performance/code-bloat risk:** Medium. Virtualizer correctness matters; validate before removing the key.
- **Validation method:** Playwright capture frames while toggling grid/justified rows and dragging the size slider; assert no mass blanking of visible thumbnails and no wrong row heights.

### 11. Add media failure affordances for hover preview and viewer original

- **Severity:** P2 Medium
- **User impact:** Failed hover previews and original loads silently vanish or stay pending. Users need to know whether the image is missing, remote media failed, or the app is still loading.
- **File/code area:** `HoverPreviewRequestController` use in `VirtualGrid.tsx`; `api.getHoverPreview`; `Viewer.tsx`; `useBlobUrl`.
- **Fix concept:** Add tiny failure states: hover preview can show a compact unavailable panel after delay; viewer can show a centered failure state with filename and a retry button that reuses `api.getFile`. Keep errors local and non-modal.
- **Effort:** M
- **Performance/code-bloat risk:** Low. Do not log noisy errors or add retry loops.
- **Validation method:** Playwright route-abort `/file` and `/thumb`, assert visible failure state and retry works after unblocking route.

### 12. Tune motion and transitions for reduced-motion and high-scroll paths

- **Severity:** P3 Low
- **User impact:** The app uses short fades and scroll animations. They improve polish but can feel busy during rapid keyboard nav, metric rail scrubbing, or reduced-motion settings.
- **File/code area:** `VirtualGrid.tsx` `scrollRowIntoView`; `ThumbCard` opacity transition; `styles.css` transitions and `prefers-reduced-motion`.
- **Fix concept:** Respect `prefers-reduced-motion` for thumbnail fades and programmatic scroll animation. During high-frequency nav/scrub, snap or use a shorter no-ease scroll to avoid compounded motion.
- **Effort:** S
- **Performance/code-bloat risk:** Low. CSS media query and a small helper are enough.
- **Validation method:** Existing `scripts/browser/overall_cleanup/mobile.py` reduced-motion check can be extended to grid card transitions and keyboard nav scroll.

## 3 Quick Wins

1. Add in-card thumbnail loading and failed states in `ThumbCard`, using existing dimensions and CSS only.
2. Strengthen selected-card feedback on touch and single selection with a small badge/check and stronger ring.
3. Expand bottom viewer nav to coarse-pointer tablet/narrow contexts, or otherwise ensure visible 44px next/previous controls outside phone-only width.

## 3 Medium Projects

1. Generalize the existing selection/top-anchor restore system so sort, filter, layout, and size changes preserve user context.
2. Implement viewer next/previous continuity by retaining the previous ready image until the next original decodes.
3. Upgrade metric rail interaction with a wider hit target, keyboard semantics, animation-frame-throttled scrubbing, and precomputed nearest-value lookup.

## Things Not To Do

- Do not add a new global store, router, or interaction manager. The existing app-shell state and restore-token model are enough.
- Do not replace native scrolling with a custom scrollbar. Keep the native scrollbar and metric rail as complementary controls.
- Do not increase full-original prefetch breadth to hide viewer latency. The current request budget and 40 MB prefetch cap protect real workloads.
- Do not add tutorial popovers or verbose helper copy for selection. Improve visible state and controls instead.
- Do not animate every state transition. Professional polish here is mostly stable context and restrained feedback, not more motion.
- Do not build separate mobile and desktop grid components. Reuse the same virtual grid and responsive control shell.
- Do not hide blank/error media states behind console logs. Show small local states where the user is looking.

## Top 5 Recommendations

1. Reuse the existing top-anchor/selection restore system for sort, filter, layout, and thumbnail-size changes.
2. Keep the previous ready viewer image visible while the next original loads, then crossfade once decoded.
3. Add compact thumbnail and original-media loading/error states so slow or broken media never looks like an empty app.
4. Make selection state stronger on touch, especially for the first tap in the two-tap open model.
5. Make the metric rail a real navigation control: wider hit target, keyboard semantics, throttled scrubbing, and stable value feedback.
