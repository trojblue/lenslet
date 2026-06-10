# Navigation/State Product Feel Scan

## Journeys inspected

- Shared an analysis view with folder scope, metric sort, filters, and derived score parameters, then opened the URL in a fresh session.
- Moved between folders, parent folders, search, similarity mode, metrics, derived score, smart folders, inspector, viewer, and compare.
- Opened a viewer from the grid, navigated next/previous, closed it, used browser back/forward, and checked how the hash changes.
- Selected multiple items, changed compare order preference, opened compare, navigated compare pairs, and observed how compare exits on selection changes.
- Switched mobile-only modes such as search drawer and multi-select in relation to persisted desktop layout state.
- Entered ranking mode, resumed a ranking session, navigated instances, changed ranking layout sizing, opened ranking fullscreen, and returned later.

## Current strengths

- Folder and single-image viewer links are already shareable: folder hashes are plain paths and viewer hashes use explicit `#!` image routes, avoiding extensionless item ambiguity (`frontend/src/app/routing/hash.ts`).
- Sort, filters, and derived metric definitions are URL-owned query params, and they override local restored state when present (`frontend/src/app/routing/viewStateUrl.ts`, `frontend/src/app/AppShell.tsx`).
- Layout preferences that are personal rather than share intent are localStorage-owned: view mode, thumbnail size, panel open state, compare order preference, metadata autoload, HTTP proxy setting, and sidebar widths.
- Viewer back/forward behavior has a real history model: opening viewer writes an image hash, closing can use `history.back()`, and stepping images replaces the hash instead of flooding history (`frontend/src/app/hooks/useAppSelectionViewerCompare.ts`).
- Folder scroll restoration is session-memory-owned rather than persisted, which is appropriate for performance and privacy on large trees (`frontend/src/app/hooks/useFolderSessionState.ts`).
- Similarity mode is visibly labeled with an explicit exit band, and exit restores the previous selection when available (`frontend/src/app/hooks/useSimilaritySearchWorkflow.ts`, `frontend/src/app/components/GridTopStack.tsx`).
- Ranking results and resume progress are backend-owned, with autosave and resume loaded from `/rank/progress` and exports (`frontend/src/features/ranking/hooks/useRankingSession.ts`, `src/lenslet/ranking/routes.py`).

## State ownership map

- URL-owned now: folder scope hash, viewer image hash, sort, filters, derived metric definitions.
- URL-owned should add: text search query, compare pair/open state, compare index or selected paths for share links, active smart-folder id, ranking instance id/index, and optionally similarity query parameters for path-based similarity.
- Local-storage-owned now: browse view mode, thumbnail size, side panel open states, side panel widths, theme, metadata autoload, compare ordering preference, HTTP-original proxy preference, ranking unassigned panel height and thumb size.
- Local-storage-owned should add: dismissed low-risk notices by workspace/bucket, last active left tool, mobile drawer preference if it does not fight responsive defaults, inspector section layout already mostly fits here.
- Backend-owned now: saved smart folders, ranking results/progress, sidecar edits, workspace views.
- Backend-owned should add: durable named analysis views and share aliases if URLs become too large for complex derived metrics or filters.
- Ephemeral now and mostly appropriate: viewer zoom/pan, compare split/zoom/pan, ranking fullscreen zoom/pan, modal draft fields, context menu state, hover/focus, in-flight loading, off-view update summaries.

## Ranked opportunities

1. **High: Make compare links shareable and restorable.** User impact: analysts cannot send "compare these two outputs" or reload into a side-by-side view; compare is only a pushed history sentinel with no URL payload. Likely code area: `useAppSelectionViewerCompare.ts`, `CompareViewer.tsx`, `viewStateUrl.ts`. Fix concept: encode `mode=compare`, ordered `paths`, and optional `compareIndex` in query params; hydrate selection and open compare from URL; keep split/zoom ephemeral. Effort: M. Performance/code-bloat risk: low if capped to explicit paths and no image data. Validation: browser smoke opens a compare URL, asserts both paths and back closes compare without losing folder/filter state.

2. **High: URL-own text search.** User impact: a user sharing a searched/filtered folder currently shares filters/sort/folder but not the search term, so recipients land in a broader or different result set. Likely code area: `AppShell.tsx`, `useAppDataScope.ts`, `viewStateUrl.ts`, `Toolbar.tsx`. Fix concept: add a compact `q` search param with debounced replace semantics; restore it on boot; clear it intentionally on "Reveal off-view" or explicit search clear. Effort: S. Performance/code-bloat risk: low; query key already depends on `normalizedQ`. Validation: URL round-trip test plus Playwright flow for search -> copy URL -> reload.

3. **High: Stop using browser back as an internal close command when the overlay URL is stale.** User impact: close actions can unexpectedly leave the app or jump to an unrelated browser entry if state was opened by URL, restored after reload, or changed through `pushState` sentinels. Likely code area: `useAppSelectionViewerCompare.ts`. Fix concept: centralize overlay history ownership with explicit route state comparison; close should replace to the underlying route when the current URL already represents the current overlay, and use back only when the previous entry is known to be the parent Lenslet route. Effort: M. Performance/code-bloat risk: medium if over-abstracted; keep a small route-state helper. Validation: unit tests for open-by-click, open-by-URL, open-compare-from-viewer, reload-in-viewer, close, browser back/forward.

4. **High: Give ranking instance navigation stable URLs.** User impact: ranking resume works, but a reviewer cannot share "instance 37" or use browser back/forward between instances; refresh always follows backend resume, not necessarily the current analysis target. Likely code area: `RankingApp.tsx`, `useRankingSession.ts`, `src/lenslet/ranking/routes.py`. Fix concept: support `?instance=<id-or-index>` and replace/push it on Prev/Next; keep completed rankings backend-owned. Effort: M. Performance/code-bloat risk: low. Validation: frontend tests for URL parsing/clamping and a ranking smoke reloads `?instance=...`.

5. **Medium-high: Preserve selected paths in shareable analysis URLs when selection matters.** User impact: inspector and metadata compare depend on selection, but a shared view loses the current selected item(s), so recipients see filters but not the subject of the analysis. Likely code area: `useAppSelectionViewerCompare.ts`, `AppShell.tsx`, `viewStateUrl.ts`, `Inspector.tsx`. Fix concept: add optional `selected=` path list for explicit share actions or compare/inspector states; avoid continuously writing large multi-select lists during normal clicking. Effort: M. Performance/code-bloat risk: medium due URL length and selection churn; cap length and prefer explicit "copy link to selection". Validation: reload with selected paths shows inspector target and multi-selection count.

6. **Medium-high: Make active smart folders addressable.** User impact: saved views are durable, but active view identity is memory-only and clears on equivalent manual edits; sharing or returning later loses "I am in Smart Folder X" context. Likely code area: `useSmartFolders.ts`, `LeftSidebar.tsx`, `viewStateUrl.ts`, `/views` routes. Fix concept: encode `view=<id>` in URL when activated, load the saved view by id, and mark "modified" instead of immediately dropping active identity when state diverges. Effort: M. Performance/code-bloat risk: low. Validation: activate saved view -> URL has id -> reload -> same folder/view active; edit filter -> active pill becomes modified.

7. **Medium: Separate "shared view state" from "personal remembered defaults" more visibly.** User impact: because AppShell writes every view state to both URL and localStorage, users may not know whether a reload used the link or their last local preferences. Likely code area: `usePersistedAppShellSettings.ts`, `viewStateUrl.ts`, `GridTopStack.tsx`. Fix concept: when URL params are present, show a subtle "Shared view" chip with a clear action to "make default" or "clear shared params"; keep local restoration silent only when no shared params exist. Effort: S/M. Performance/code-bloat risk: low. Validation: reload with query params skips local view restore and shows the chip; clearing returns to local default.

8. **Medium: Persist dismissals for recurring low-risk notices by workspace.** User impact: browser zoom, table source warnings, and read-only warnings can reappear after reload even after the user has acknowledged them, increasing visual noise. Likely code area: `useBrowserZoomWarning.ts`, `AppShell.tsx`, `StatusBar.tsx`, theme/workspace storage helpers. Fix concept: localStorage-own dismissals with scoped keys: zoom bucket, table source warning key, read-only workspace id. Keep indexing errors and off-view updates ephemeral. Effort: S. Performance/code-bloat risk: low. Validation: dismiss, reload, warning stays hidden until bucket/key changes.

9. **Medium: Remember the active left tool independently from panel open state.** User impact: users who live in metrics or derived score return to the app in folders because `leftTool` is only in memory, even though widths and panel open state persist. Likely code area: `AppShell.tsx`, `usePersistedAppShellSettings.ts`, `useSidebars.ts`. Fix concept: localStorage-own `leftTool`, restored after boot and compatible with responsive suppression. Effort: S. Performance/code-bloat risk: low. Validation: choose Derived Score, reload, left panel reopens to Derived Score without changing shared URL.

10. **Medium: Make similarity mode restorable for path queries.** User impact: similarity is a real analysis mode but cannot be shared or restored; exiting also restores a prior selection from a ref that disappears on reload. Likely code area: `SimilarityModal.tsx`, `useSimilaritySearchWorkflow.ts`, `useAppDataScope.ts`, `viewStateUrl.ts`. Fix concept: support URL params for `similarity_embedding`, `similarity_path`, `top_k`, and `min_score`; do not URL-own vector payloads by default. Effort: M/L. Performance/code-bloat risk: medium because restoring triggers embedding search; require explicit URL params and clear loading state. Validation: link reload runs the same path-based similarity and shows the similarity band.

11. **Medium-low: Make mode exits less surprising when selection changes.** User impact: compare closes automatically when selection drops below two items, which is correct but can feel abrupt if the user mis-clicks or filters the compared item out. Likely code area: `useAppSelectionViewerCompare.ts`, `GridTopStack.tsx`, `SelectionActionsSection.tsx`. Fix concept: when compare auto-closes, show a short, dismissible status reason and a one-click restore if previous compare paths are still available. Effort: S/M. Performance/code-bloat risk: low if previous paths are held in a small ref. Validation: remove one compared selection and assert status plus restore behavior.

12. **Medium-low: Use browser history for folder navigation more predictably.** User impact: folder clicks update `window.location.hash`, which creates history entries, but sort/filter changes use `replaceState`, so back sometimes means "previous folder" but never "previous filter." That is mostly right, but the product should make it intentional. Likely code area: `openFolder`, `viewStateUrl.ts`, `useAppHashRouting.ts`. Fix concept: keep live slider/filter edits as replace, but push history on explicit saved-view activation and folder changes; add tests documenting back/forward expectations. Effort: S. Performance/code-bloat risk: low. Validation: browser smoke folder A -> folder B -> filter -> back returns A with current or restored documented filter behavior.

13. **Low: Add an explicit "copy current view link" command.** User impact: users can copy the address bar, but the product does not communicate that the link contains the analysis state, and future explicit-share behavior can avoid URL-churn-heavy selection persistence. Likely code area: `Toolbar.tsx`, `GridTopStack.tsx`, `viewStateUrl.ts`. Fix concept: button copies the canonical current URL, optionally including selection/compare/similarity only at click time. Effort: S. Performance/code-bloat risk: low. Validation: click command writes expected URL in e2e clipboard stub.

## 3 quick wins

1. URL-own `q` for text search and add a small round-trip test.
2. Persist active `leftTool` locally so Metrics/Derived Score users return to their last working panel.
3. Persist dismissals for browser zoom bucket and table source warning key in workspace-scoped localStorage.

## 3 medium projects

1. Shareable compare URLs with selected paths, compare index, hydration, and back/forward tests.
2. Ranking URL routes for instance index/id plus history-aware Prev/Next.
3. Smart Folder URL identity with "modified from saved view" product state.

## Things not to do

- Do not put viewer zoom/pan, compare split/zoom/pan, or ranking fullscreen transform into the URL; those are noisy, personal, and fragile across screen sizes.
- Do not continuously write every multi-selection change into the address bar for large selections; use explicit share links or capped URL state.
- Do not make localStorage the authority for shareable analysis state; local preferences should never override explicit URL params.
- Do not add a second routing system or global state manager just for this; the current hash/query/local/backend ownership can be extended with small helpers.
- Do not backend-persist transient UI modes such as open modals, context menus, mobile search row, hover preview, or in-flight request state.
- Do not make browser back step through every slider drag or filter keystroke; use replace for live edits and push only for deliberate navigational commits.

## Top 5 recommendations

1. Make compare URLs first-class: `mode=compare`, ordered paths, optional index, and tested back/forward behavior.
2. Add `q` to shared view URL state so search/filter/sort links reproduce the same analysis view.
3. Replace ad hoc overlay history sentinels with a small route-state helper that knows when to back versus replace.
4. Add ranking instance URLs so ranking review targets are shareable and browser navigation is predictable.
5. Persist recurring low-risk notice dismissals and active left tool locally to reduce reload noise without polluting shared URLs.
