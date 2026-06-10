# Navigation/State Codepath Scan

## Scope and Files Inspected

Aspect: navigation, state persistence, URL/shareability, and mode transitions, codepath-focused.

Primary files inspected:

- `frontend/src/app/AppModeRouter.tsx`
- `frontend/src/app/AppShell.tsx`
- `frontend/src/app/routing/hash.ts`
- `frontend/src/app/routing/viewStateUrl.ts`
- `frontend/src/app/hooks/useAppHashRouting.ts`
- `frontend/src/app/hooks/useAppSelectionViewerCompare.ts`
- `frontend/src/app/hooks/useFolderSessionState.ts`
- `frontend/src/app/hooks/usePersistedAppShellSettings.ts`
- `frontend/src/app/hooks/useAppDataScope.ts`
- `frontend/src/app/hooks/useSimilaritySearchWorkflow.ts`
- `frontend/src/app/hooks/useAppPresenceSync.ts`
- `frontend/src/app/hooks/usePresenceLeaseLifecycle.ts`
- `frontend/src/app/hooks/useAppSyncEvents.ts`
- `frontend/src/api/client.ts`
- `frontend/src/api/folders.ts`
- `frontend/src/shared/ui/Toolbar.tsx`
- `frontend/src/shared/ui/SyncIndicator.tsx`
- `frontend/src/app/components/StatusBar.tsx`
- `frontend/src/features/browse/components/VirtualGrid.tsx`
- `frontend/src/features/browse/model/virtualGridSession.ts`
- `frontend/src/features/ranking/RankingApp.tsx`
- `frontend/src/features/ranking/hooks/useRankingSession.ts`
- `frontend/src/theme/storage.ts`
- `src/lenslet/web/routes/folders.py`
- `src/lenslet/browse/query.py`
- Relevant frontend tests under `frontend/src/app/**/__tests__` and `frontend/src/features/browse/model/__tests__`.

## Architecture Map

- App mode is backend-owned. `AppModeRouter` calls `/health`, maps `health.mode` to `browse` or `ranking`, and renders either `AppShell` or lazy `RankingApp`.
- Browse location is split across URL hash and query string. Plain hashes represent folder scopes, while `#!/path` represents viewer image routes. Search params represent shared `viewState` pieces: sort, filters, and referenced derived metric definitions.
- `AppShell` is the central owner for browse state: `current`, transient `query`, `similarityState`, `viewState`, random seed, view mode, sidebars, selected paths, viewer, compare, warnings, and table source state.
- `useAppDataScope` is the execution bridge from `current + query + viewState + randomSeed` to backend `/folders/query` requests.
- `usePersistedAppShellSettings` writes global localStorage keys for `viewState`, view mode, grid size, sidebars, metadata autoload, compare order, and HTTP proxy behavior. It skips local `viewState` restore only when the current URL already has Lenslet view-state params.
- `useAppSelectionViewerCompare` owns `selectedPaths`, viewer, compare, overlay history entries, and grid restore tokens. Viewer is URL-addressed; compare is not.
- Folder session state is in-memory only. The currently wired part saves and restores top-anchor paths; hydrated snapshot APIs exist but are not wired from `AppShell`.
- Presence/sync state is session-owned and backend-driven. Events use a tab-scoped `client_id` in `sessionStorage` and a global `last_event_id` in `localStorage`. Presence scope follows the current folder with coalesced join/move/leave calls.
- Ranking mode is backend-progress-owned. Current instance resumes from `/rank/progress`; board state persists via `/rank/save`. URL state does not address instance, fullscreen image, or board substate.

## Ranked Findings

### 1. Global shell settings are not workspace-scoped

- Severity: High
- User impact: Launching a different dataset/workspace on the same origin can inherit stale filters, metric sorts, sidebars, grid size, source proxy setting, and compare-order preference. A folder URL with no explicit Lenslet params can become non-deterministic because local `viewState` is restored and then written into the URL.
- Root files: `frontend/src/app/hooks/usePersistedAppShellSettings.ts:21`, `frontend/src/app/hooks/usePersistedAppShellSettings.ts:144`, `frontend/src/app/AppShell.tsx:298`, `frontend/src/app/AppShell.tsx:319`, `frontend/src/theme/storage.ts:42`
- Suggested fix shape: Scope shell settings by the same workspace identity used for themes. Keep one canonical settings object, but key it by `workspace_id` plus mode, with URL params still taking precedence over persisted `viewState`.
- Effort: M
- Performance/code-bloat risk: Low if this is a key-building change plus migration deletion. Medium if compatibility layers are added; avoid those in alpha.
- Validation method: Unit-test storage key isolation for two workspace IDs; browser smoke with workspace A filters, then workspace B clean launch; verify copied clean URL does not gain A's filters.

### 2. Search text is transient, unshareable, and can desync from the visible input

- Severity: High
- User impact: Copied URLs drop the active search. Programmatic clears such as off-view reveal call `setQuery('')`, but `Toolbar` search inputs are uncontrolled, so the input can still display the old text. Opening another folder while search is active silently applies the old query to the new folder.
- Root files: `frontend/src/app/AppShell.tsx:236`, `frontend/src/shared/ui/Toolbar.tsx:560`, `frontend/src/shared/ui/Toolbar.tsx:581`, `frontend/src/app/hooks/useAppDataScope.ts:181`, `frontend/src/app/hooks/useSimilaritySearchWorkflow.ts:45`, `frontend/src/app/AppShell.tsx:910`
- Suggested fix shape: Make search a canonical field next to shared view state, preferably `q` in the URL for plain text search. Pass `query` as a controlled toolbar value. Decide explicitly whether folder opens preserve or clear `q`, then make that transition deterministic.
- Effort: M
- Performance/code-bloat risk: Low. Avoid introducing a router/store; this can reuse the existing URL state helper.
- Validation method: Browser test for typing search, copying/reloading URL, off-view reveal clearing input, and folder transition behavior.

### 3. Compare mode is not URL-addressable and uses history without serializing state

- Severity: High
- User impact: A user in compare mode who copies the URL shares only the underlying folder/filter/viewer-free state. Reloading loses compare, selected pair, compare order, and compare index. Back closes compare because a history entry was pushed, but the URL is identical, making the state invisible and hard to reason about.
- Root files: `frontend/src/app/hooks/useAppSelectionViewerCompare.ts:231`, `frontend/src/app/hooks/useAppSelectionViewerCompare.ts:247`, `frontend/src/app/AppShell.tsx:1304`
- Suggested fix shape: Add a compact URL overlay state for compare, for example `compare=a,b&compare_index=0` or a hashbang route variant. Keep `selectedPaths` as the source for compare contents after parsing; do not create a separate compare store.
- Effort: M
- Performance/code-bloat risk: Low. Risk is mostly URL length when many selected paths are included; encode only the active pair/index unless multi-selection share is explicitly needed.
- Validation method: Playwright flow: select two images, open compare, reload, back/forward, and copied URL in a new tab. Assert same pair and index.

### 4. Folder navigation leaves selection and inspector path from the previous scope

- Severity: High
- User impact: Opening a folder changes the grid but does not clear `selectedPaths`. The grid no longer highlights the previous item, while the inspector still receives `selectedPaths[0]` and can show/edit an item outside the current scope. Compare eligibility also derives from stale selection until item resolution drops it.
- Root files: `frontend/src/app/AppShell.tsx:910`, `frontend/src/app/AppShell.tsx:1193`, `frontend/src/app/AppShell.tsx:1251`, `frontend/src/app/hooks/useAppSelectionViewerCompare.ts:132`
- Suggested fix shape: Treat folder scope changes as a canonical selection boundary. `openFolder` and hash-applied folder changes should clear selection unless the transition came from a viewer hash that explicitly selects an image. Keep this centralized in `useAppSelectionViewerCompare` or the hash-routing handoff.
- Effort: S
- Performance/code-bloat risk: Low.
- Validation method: Component/browser test: select item in `/a`, open `/b`, assert inspector path is null and no stale sidecar query/edit surface remains.

### 5. Random sort URLs are not reproducible

- Severity: Medium-High
- User impact: A URL can say `sort=builtin:random:desc`, but it does not carry the `randomSeed`. Reloads, local restore, and shares reshuffle results, so a recipient does not see the same order or selected context.
- Root files: `frontend/src/app/routing/viewStateUrl.ts:111`, `frontend/src/app/AppShell.tsx:254`, `frontend/src/app/AppShell.tsx:838`, `frontend/src/api/folders.ts:82`, `src/lenslet/browse/query.py:527`
- Suggested fix shape: Include `seed` only when sort is random. Keep reshuffle as an explicit command that updates the seed in both state and URL. If random is intended to be ephemeral, do not write it to shared URL state.
- Effort: S
- Performance/code-bloat risk: Low.
- Validation method: Unit-test URL round trip with random seed; backend request key includes same seed; reload preserves item order on fixture data.

### 6. Filter/sort changes replace history, so Back cannot undo browsing refinements

- Severity: Medium
- User impact: Users can see the URL update as filters/sorts change, but browser Back will skip those refinements because `replaceSharedViewStateInCurrentUrl` always calls `replaceState`. This makes folder/viewer history and view-state history feel inconsistent.
- Root files: `frontend/src/app/routing/viewStateUrl.ts:70`, `frontend/src/app/AppShell.tsx:319`
- Suggested fix shape: Keep replacement for high-frequency edits such as sliders/text fields, but push a history entry for committed changes such as sort selection, star toggle, clear filters, and saved-view activation. A small commit API around existing `setViewState` is enough.
- Effort: M
- Performance/code-bloat risk: Medium if every drag/input pushes history. Use explicit commit boundaries.
- Validation method: Playwright back/forward test for sort dropdown and filter chip removal, plus slider/text filter tests to ensure no history spam.

### 7. Shared metric/derived view state can be silently rewritten to default

- Severity: Medium
- User impact: A shared URL with a metric sort or derived metric filter can be normalized away after capability data loads if the metric is unavailable in the current scope/source. The address bar then loses the user's requested state, making the failure hard to diagnose or reshare.
- Root files: `frontend/src/app/AppShell.tsx:636`, `frontend/src/app/AppShell.tsx:645`, `frontend/src/app/routing/viewStateUrl.ts:70`, `frontend/src/app/routing/viewStateUrl.ts:95`
- Suggested fix shape: Preserve unsupported shared intent until the user changes it. Surface a warning and disable execution, but avoid mutating the URL on load. Only canonicalize on explicit user edits.
- Effort: M
- Performance/code-bloat risk: Low. The risk is extra conditional state; keep it as metadata on the existing `viewState`, not a new store.
- Validation method: Unit-test unavailable metric sort from URL remains in search params; browser test shows warning and does not issue unsupported browse query.

### 8. Off-view "Reveal" destroys the current view without a reversible transition

- Severity: Medium
- User impact: The reveal action clears text search and all filters, and exits similarity mode if active. That reveals edits but also discards a carefully constructed view, with no undo and no pushed URL history entry.
- Root files: `frontend/src/app/components/StatusBar.tsx:219`, `frontend/src/app/hooks/useSimilaritySearchWorkflow.ts:45`, `frontend/src/app/AppShell.tsx:1165`
- Suggested fix shape: Make reveal deterministic and reversible. Prefer selecting/navigating to touched items when possible; otherwise push a history entry or show a temporary "return to previous view" action backed by the prior canonical `viewState + q + similarity` snapshot.
- Effort: M
- Performance/code-bloat risk: Medium if snapshots become a second state store. Store only one prior snapshot for undo.
- Validation method: Browser flow with filter hiding an updated item; click Reveal, then Back or Return, and assert original filters/search are restored.

### 9. Similarity mode is local-only and cannot be restored from URL

- Severity: Medium
- User impact: Similarity result context, embedding choice, query path/vector, top K, and min score disappear on reload or share. This is especially confusing because the similarity banner looks like a mode, not a temporary modal result.
- Root files: `frontend/src/app/hooks/useSimilaritySearchWorkflow.ts:53`, `frontend/src/app/hooks/useAppDataScope.ts:180`, `frontend/src/app/components/GridTopStack.tsx:87`, `frontend/src/features/embeddings/SimilarityModal.tsx:103`
- Suggested fix shape: Add shareability only for safe, compact path-query similarity, for example `similar=embedding:path:topk:minscore`. Avoid putting vector payloads in URLs by default. Re-run the search from URL state rather than persisting result rows.
- Effort: M
- Performance/code-bloat risk: Medium because URL restore can trigger embedding search. Gate it behind validated params and existing request cancellation.
- Validation method: Unit parse/build tests and browser reload test for path-based similarity. Explicit negative test that vector payloads are not serialized automatically.

### 10. Folder session snapshot APIs are present but not wired

- Severity: Medium
- User impact: The code suggests folder session hydration can restore snapshots, but `AppShell` only uses top-anchor APIs. Users still see fresh loading/jumps when returning to large folders after scope changes or refreshes, while unused API surface increases maintenance cost.
- Root files: `frontend/src/app/hooks/useFolderSessionState.ts:146`, `frontend/src/app/AppShell.tsx:289`, `frontend/src/features/browse/components/VirtualGrid.tsx:537`
- Suggested fix shape: Either wire the snapshot cache into `useAppDataScope`/React Query placeholder data, or remove the unused snapshot part and keep top-anchor session state focused. Prefer one canonical cache owner; React Query should remain the data cache.
- Effort: S to remove, M to wire correctly
- Performance/code-bloat risk: Medium if snapshots duplicate large query payloads. The current `10_000` item cap helps but still risks memory churn.
- Validation method: Large-tree smoke for folder A scroll, folder B open, return to A; measure first paint and restored anchor. Unit-test that unused APIs are gone or used by data scope.

### 11. Read-only and source warning dismissals are session-only

- Severity: Low-Medium
- User impact: Dismissed read-only and table-source warnings return after reload. The status band has reserved layout, but repeated banners still add visual churn, especially in read-only shared launches.
- Root files: `frontend/src/app/AppShell.tsx:272`, `frontend/src/app/AppShell.tsx:575`, `frontend/src/app/components/StatusBar.tsx:72`, `frontend/src/app/components/StatusBar.tsx:143`
- Suggested fix shape: Persist dismissals by stable warning key and workspace ID. Keep read-only warnings visible on first launch per workspace, but remember dismissal for that exact read-only state.
- Effort: S
- Performance/code-bloat risk: Low.
- Validation method: Browser reload after dismiss in read-only mode; verify warning stays dismissed for same workspace and reappears for a changed warning key.

### 12. Ranking mode has backend progress but no URL substate

- Severity: Low-Medium
- User impact: Refresh resumes the backend's current instance, but copied URLs cannot point to a specific ranking instance or fullscreen image. Navigation in ranking mode also does not participate in browser Back/Forward.
- Root files: `frontend/src/app/AppModeRouter.tsx:40`, `frontend/src/features/ranking/hooks/useRankingSession.ts:78`, `frontend/src/features/ranking/hooks/useRankingSession.ts:216`, `frontend/src/features/ranking/RankingApp.tsx:545`
- Suggested fix shape: Add optional URL params for `rank_instance` and fullscreen image ID, while keeping backend progress as the default when params are absent. Do not encode the whole board in the URL; board state already has a persistence API.
- Effort: M
- Performance/code-bloat risk: Low.
- Validation method: Ranking browser test for direct `?rank_instance=N`, reload, fullscreen image param, and fallback to `/rank/progress`.

### 13. Sync recent-touch UI copies labels, not navigable paths

- Severity: Low
- User impact: The sync popover lists recently touched files, but clicking copies only the display label. Users cannot jump to or share the touched item from that state, even though off-view updates are a navigation problem.
- Root files: `frontend/src/shared/ui/SyncIndicator.tsx:60`, `frontend/src/shared/ui/SyncIndicator.tsx:132`, `frontend/src/app/presenceActivity.ts:91`
- Suggested fix shape: Provide a "go to item" callback that updates canonical folder/viewer/selection state, or copy a viewer URL built from the existing hash helper. Prefer navigation over another local-only copied string.
- Effort: S
- Performance/code-bloat risk: Low.
- Validation method: UI test for clicking a recent touch navigates/selects item or copies `#!/path` URL.

## Quick Wins

1. Clear selection on folder transitions unless applying an explicit viewer hash. This removes stale inspector/selection context with a small, centralized change.
2. Make the toolbar search input controlled by `query`, even before deciding URL semantics. This fixes visible stale search after programmatic clears.
3. Add `randomSeed` to shared URL state when random sort is active, or stop serializing random sort as shareable state.

## Medium Projects

1. Workspace-scope all shell, sidebar, inspector, and ranking localStorage settings using the existing `workspace_id` pattern from theme storage.
2. Build a single URL state module for `folder/viewer/search/viewState/compare` with explicit push-vs-replace commit boundaries.
3. Add restoreable mode URLs for compare and safe path-based similarity, keeping backend/React Query as the data owner.

## Things Not To Do

- Do not add Redux, Zustand, or a full routing framework just to encode the current state model. The existing state can be made canonical with smaller URL helpers.
- Do not create duplicate stores for `selectedPaths`, compare pairs, or view filters. Parse URL state into the existing owners.
- Do not serialize large or sensitive vector similarity payloads into URLs by default.
- Do not preserve every hover, popover, drawer, or transient copied-state flag. Keep URL state to navigable/reproducible workflow state.
- Do not add backward compatibility layers for old localStorage keys beyond hard deletion or one-shot cleanup; this is pre-release alpha.
- Do not push history for every slider tick, text keystroke, or drag move. Use committed transitions.

## Top 5 Recommendations

1. Workspace-scope persisted shell settings so launches and copied URLs are deterministic across datasets.
2. Promote text search into canonical URL/input state and make toolbar search controlled.
3. Clear or explicitly restore selection at folder boundaries to prevent stale inspector context.
4. Make compare mode URL-addressable with compact pair/index state.
5. Fix random sort shareability by serializing a seed or treating random as explicitly non-shareable.
