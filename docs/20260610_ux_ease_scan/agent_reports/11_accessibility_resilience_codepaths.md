# Accessibility/Resilience Codepath Scan

## Scope and Files Inspected

This scan focused on codepaths that affect repeated real use: keyboard access, touch ergonomics, modal/menu focus behavior, status and save feedback, form labeling, error handling, and API failure presentation. No implementation files were modified.

Primary frontend primitives and app shell inspected:

- `frontend/src/shared/ui/Dropdown.tsx`
- `frontend/src/shared/hooks/useModalFocusTrap.ts`
- `frontend/src/shared/ui/ThemeSettingsMenu.tsx`
- `frontend/src/shared/ui/SyncIndicator.tsx`
- `frontend/src/shared/ui/Toolbar.tsx`
- `frontend/src/shared/ui/toolbar/ToolbarMobileDrawer.tsx`
- `frontend/src/shared/ui/toolbar/ToolbarFilterMenu.tsx`
- `frontend/src/app/AppShell.tsx`
- `frontend/src/app/components/GridTopStack.tsx`
- `frontend/src/app/components/StatusBar.tsx`
- `frontend/src/app/hooks/useAppActions.ts`
- `frontend/src/app/hooks/useAppDataScope.ts`
- `frontend/src/app/hooks/useAppKeyboardShortcuts.ts`
- `frontend/src/app/hooks/useFolderRefreshActions.ts`
- `frontend/src/app/hooks/useGridPinchResize.ts`
- `frontend/src/app/hooks/useSimilaritySearchWorkflow.ts`
- `frontend/src/app/menu/ContextMenu.tsx`
- `frontend/src/app/menu/AppContextMenuItems.tsx`
- `frontend/src/lib/fetcher.ts`
- `frontend/src/lib/touch.ts`

Feature codepaths inspected:

- Browse/grid/tree: `frontend/src/features/browse/components/VirtualGrid.tsx`, `VirtualGridRows.tsx`, `ThumbCard.tsx`, `frontend/src/features/folders/FolderTree.tsx`, `frontend/src/features/folders/hooks/useFolderTreeKeyboardNav.ts`
- Viewer/compare/similarity: `frontend/src/features/viewer/Viewer.tsx`, `frontend/src/features/viewer/hooks/useZoomPan.ts`, `frontend/src/features/compare/CompareViewer.tsx`, `frontend/src/features/compare/hooks/useCompareZoomPan.ts`, `frontend/src/features/compare/hooks/useDividerDrag.ts`, `frontend/src/features/embeddings/SimilarityModal.tsx`
- Ranking: `frontend/src/features/ranking/RankingApp.tsx`, `frontend/src/features/ranking/hooks/useRankingKeyboard.ts`, `useRankingFullscreen.ts`, `useRankingSession.ts`, `useRankingDrag.ts`, `frontend/src/features/ranking/api.ts`, `frontend/src/features/ranking/model/keyboard.ts`
- Inspector/forms/exports: `frontend/src/features/inspector/Inspector.tsx`, `hooks/useInspectorSidecarWorkflow.ts`, `hooks/useInspectorCompareExport.ts`, `compareExportBoundary.ts`, `sections/BasicsSection.tsx`, `InspectorSection.tsx`, `NotesSection.tsx`, `SelectionActionsSection.tsx`, `SelectionExportSection.tsx`, `CompareMetadataSection.tsx`
- Metrics/filter forms: `frontend/src/features/metrics/MetricsPanel.tsx`, `DerivedScorePanel.tsx`, `components/MetricRangePanel.tsx`, `CategoricalPanel.tsx`, `DerivedScoreCard.tsx`, `AttributesPanel.tsx`
- API/backend error surfaces: `frontend/src/api/base.ts`, `frontend/src/api/client.ts`, `frontend/src/api/items.ts`, `frontend/src/api/folders.ts`, `frontend/src/api/embeddings.ts`, `src/lenslet/web/responses.py`, `src/lenslet/web/export/response.py`, `src/lenslet/web/routes/table_settings.py`, `src/lenslet/web/media.py`

## Concise Primitive/State Map

- Modal focus: `useModalFocusTrap` is a good existing primitive with Tab containment, Escape handling, focus restoration, and outside-focus recovery. It is used by compare fullscreen, but not consistently used by similarity search, ranking fullscreen, regular viewer, or popover-style dialogs.
- Menus/popovers: `Dropdown` has search, listbox semantics, arrow/Home/End handling, outside close, and Escape support for its standard trigger. `DropdownMenu`, `ContextMenu`, `ThemeSettingsMenu`, `ToolbarFilterMenu`, and `SyncIndicator` each implement their own partial menu/popover behavior.
- Keyboard navigation: grid and folder tree have substantial keyboard navigation. App-level shortcuts avoid text inputs. Ranking has workflow shortcuts for rank assignment and fullscreen review. Pointer-only surfaces remain in compare divider dragging, section/board drag-sort, sidebar resizing, and some context menu open paths.
- Touch support: browse grid has long-press action handling, pinch resize, and pointer capture; viewer/compare have pinch/pan. Mobile toolbar search and drawer behavior are present. Touch problems are mostly around parity with keyboard/focus and ensuring controls are large, labeled, and recoverable.
- Status/sync: `SyncIndicator`, `StatusBar`, and inspector sidecar state already carry useful read-only, indexing, conflict, queue, and save states. Several action failures bypass these surfaces and go to console-only, `alert()`, or unused hook state.
- API errors: `fetcher.ts` is a solid base because it normalizes status, URL, message, and parsed body. Backend responses are mixed between `{error,message}` JSON and default FastAPI `{"detail": ...}`. UI call sites do not consistently surface the normalized message.
- Forms/labels: metrics and derived-score controls are generally strong. Inspector, similarity modal, attributes filters, copyable metadata, and star rating controls have inconsistent `htmlFor`, `aria-describedby`, button semantics, and live feedback.

## Ranked Findings

### 1. Persistence failures can be invisible in ranking and inspector bulk edits

- Severity: High
- User impact: A user can spend time ranking images or bulk editing metadata and have failures disappear into local state, console logs, or unhandled promises. This is the highest ease-of-use risk because it directly affects trust in repeated work.
- Root files: `frontend/src/features/ranking/hooks/useRankingSession.ts`, `frontend/src/features/ranking/RankingApp.tsx`, `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/inspector/hooks/useInspectorSidecarWorkflow.ts`, `frontend/src/api/items.ts`
- Evidence: ranking save state records `saveStatus` and `saveError`, but the app does not render an accessible save/error indicator. Bulk sidecar paths call `bulkUpdateSidecars(...)` without awaiting/catching in key multi-select flows, while `bulkUpdateSidecars` logs partial failures and only throws when all fail.
- Suggested fix shape: route ranking saves and inspector bulk sidecar updates through one user-visible save/status surface. Show saving, saved, partial failure count, and retry guidance with `role="status"` or `role="alert"` as appropriate. Make bulk edit call sites await and set the same sync/action error state used by the rest of the inspector.
- Effort: M
- Performance/code-bloat risk: Low. This reuses existing sync/status state instead of adding a new framework.
- Validation method: mock ranking session save failure and partial sidecar update failure in tests; add a browser smoke case that performs a rank/bulk-star action and verifies an accessible error/status message appears and clears after recovery.

### 2. Modal and fullscreen overlays do not share one focus policy

- Severity: High
- User impact: Keyboard and screen-reader users can land behind active overlays, lose opener focus, or miss dialog content. This is especially disruptive in similarity search, viewer, and fullscreen ranking where users repeatedly enter/exit overlays.
- Root files: `frontend/src/shared/hooks/useModalFocusTrap.ts`, `frontend/src/features/compare/CompareViewer.tsx`, `frontend/src/features/embeddings/SimilarityModal.tsx`, `frontend/src/features/ranking/RankingApp.tsx`, `frontend/src/features/viewer/Viewer.tsx`, `frontend/src/app/AppShell.tsx`
- Evidence: `useModalFocusTrap` exists and is used by compare fullscreen. Similarity search focuses the query input but does not trap/restore focus. Ranking fullscreen has a dialog but no trap. Regular viewer is declared as a dialog with `aria-modal={false}` while background browse controls remain focusable; `AppShell` only applies `inert` handling for compare.
- Suggested fix shape: make a small overlay policy around the existing `useModalFocusTrap`: modal overlays trap and restore focus, set background inert where appropriate, and define the first focus target. Apply it to similarity modal, ranking fullscreen, compare, and decide whether regular viewer should be modal or intentionally non-modal.
- Effort: M
- Performance/code-bloat risk: Low. The primitive already exists; the work is adoption and consistent options.
- Validation method: Playwright keyboard test for open overlay -> Tab cycle stays inside -> Escape closes -> focus returns to opener. Include viewer and ranking fullscreen.

### 3. Menu/popover primitives are split and keyboard behavior is inconsistent

- Severity: High
- User impact: Repeated controls such as context menus, theme settings, toolbar filters, sync details, and custom dropdown triggers behave differently. Some cannot be opened or navigated predictably from keyboard alone.
- Root files: `frontend/src/shared/ui/Dropdown.tsx`, `frontend/src/app/menu/ContextMenu.tsx`, `frontend/src/shared/ui/ThemeSettingsMenu.tsx`, `frontend/src/shared/ui/toolbar/ToolbarFilterMenu.tsx`, `frontend/src/shared/ui/SyncIndicator.tsx`
- Evidence: standard `Dropdown` has good listbox navigation and searchable controls. But the custom `trigger` path renders a clickable `div`, `DropdownMenu` wraps triggers in a `div`, `ContextMenu` has menu roles without initial focus/roving navigation/focus return, and theme/filter/sync panels each implement their own partial outside/Escape behavior.
- Suggested fix shape: introduce a small shared popover/menu helper, not a full design system. It should provide trigger refs, semantic trigger buttons, outside/Escape close, focus return, optional initial focus, and roving arrow/Home/End handling for menu items. Keep `Dropdown` listbox behavior separate where it is already strong.
- Effort: M
- Performance/code-bloat risk: Medium if overbuilt; low if kept as a hook plus two lightweight components.
- Validation method: keyboard-only acceptance flow for theme menu, toolbar filter, grid context menu, and sync popover. Verify trigger `aria-expanded`, first focus target, arrow navigation, Escape close, and focus return.

### 4. Browse, refresh, and table-source errors are often swallowed

- Severity: Medium-High
- User impact: When a browse request, folder refresh, table source switch, or recursive export fails, users may see stale data with no visible recovery path. Console-only handling is not usable in normal gallery work.
- Root files: `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/app/hooks/useFolderRefreshActions.ts`, `frontend/src/features/folders/FolderTree.tsx`, `frontend/src/app/menu/AppContextMenuItems.tsx`, `frontend/src/api/client.ts`
- Evidence: browse data exposes `isError`, but the app shell does not render a grid-level error/retry state. Table source switch catches and ignores failures. Folder refresh logs errors in multiple places. Folder export uses `alert()` while download selection failures are console-only.
- Suggested fix shape: add one app-level action error channel rendered by `GridTopStack` or `StatusBar` with retry where possible. Use it for browse load failure, refresh failure, table source switch failure, and export/download failures. Replace `alert()` with the same accessible surface.
- Effort: M
- Performance/code-bloat risk: Low. Centralizing reduces scattered bespoke handling.
- Validation method: mock failed `/items`, `/folders/refresh`, `/table/source-column`, and folder export responses; verify visible `role="alert"` message and retry action where applicable.

### 5. Status, warning, conflict, and export messages are not consistently live

- Severity: Medium
- User impact: Screen-reader users may not hear read-only mode, indexing completion/failure, off-view updates, save conflicts, export errors, or copy confirmations. Sighted keyboard users also get inconsistent status placement.
- Root files: `frontend/src/app/components/StatusBar.tsx`, `frontend/src/app/components/GridTopStack.tsx`, `frontend/src/features/inspector/sections/NotesSection.tsx`, `frontend/src/features/inspector/sections/SelectionExportSection.tsx`, `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`, `frontend/src/shared/ui/SyncIndicator.tsx`
- Evidence: many warnings/errors are visible `div`s without `role="status"`, `role="alert"`, or `aria-live`. Copy and conflict messages are local and not consistently announced.
- Suggested fix shape: add a tiny `StatusMessage`/`StatusBanner` primitive that maps severity to `status` or `alert`, supports dismissal, and accepts `aria-describedby` IDs from disabled controls. Use it where the app already renders messages; do not redesign the status bar.
- Effort: S-M
- Performance/code-bloat risk: Low.
- Validation method: automated DOM assertions for live-region roles plus manual screen-reader smoke for save conflict, indexing warning, export failure, and copy success/failure.

### 6. Grid and tree action menus need keyboard-native open paths

- Severity: Medium
- User impact: Grid and folder users can navigate items with the keyboard, but opening per-item actions still depends on pointer context menus or small action buttons. This slows high-volume work and blocks some assistive workflows.
- Root files: `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/features/browse/components/VirtualGridRows.tsx`, `frontend/src/features/folders/FolderTree.tsx`, `frontend/src/app/hooks/useAppActions.ts`, `frontend/src/app/menu/ContextMenu.tsx`
- Evidence: grid and tree navigation handle arrows/Home/End/Enter well. Action menus are opened from pointer coordinates or explicit small buttons. There is no focused-item `ContextMenu` key, Shift+F10, or equivalent keyboard command that opens the existing menu from the active item rect.
- Suggested fix shape: add one `openActionsForElement` helper that takes the focused cell/treeitem element and payload, computes a safe anchor position, opens the existing `ContextMenu`, focuses the first enabled item, and restores focus on close.
- Effort: S-M
- Performance/code-bloat risk: Low. No extra per-item state is needed if it uses the active item and existing context menu state.
- Validation method: Playwright: focus grid cell/tree item -> press ContextMenu key or Shift+F10 -> menu opens -> arrow/Enter activates item -> focus returns.

### 7. Virtual grid mixes two focus models under virtualization

- Severity: Medium
- User impact: Focus can become fragile when virtualized rows unmount or when assistive tech expects `aria-activedescendant` to refer to an existing active element. Users may experience lost focus or confusing announcements while navigating large galleries.
- Root files: `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/features/browse/components/VirtualGridRows.tsx`
- Evidence: the grid container uses `aria-activedescendant`, while row cells also receive DOM focus through `focusCell(...)` and per-cell `tabIndex`. This combines active-descendant and roving-DOM-focus patterns.
- Suggested fix shape: choose one model. For this app, roving DOM focus is likely simpler because cells already have IDs and focus calls; remove `aria-activedescendant` if DOM focus remains authoritative. If active-descendant is preferred, keep focus on the grid and stop focusing cells directly.
- Effort: M
- Performance/code-bloat risk: Low if the fix does not add extra rendered nodes or per-cell observers.
- Validation method: keyboard navigation across virtualized boundaries in a large-tree fixture; assert `document.activeElement` and active item remain coherent after scrolling/unmounting.

### 8. Pointer-only controls need keyboard equivalents before they become core workflows

- Severity: Medium
- User impact: Compare divider adjustment, ranking drag-sort, inspector section sorting, and sidebar resizing are difficult or impossible without a pointer. These are not catastrophic for basic browsing, but they matter for repeated compare/ranking/inspection sessions.
- Root files: `frontend/src/features/compare/CompareViewer.tsx`, `frontend/src/features/compare/hooks/useDividerDrag.ts`, `frontend/src/features/ranking/hooks/useRankingDrag.ts`, `frontend/src/features/ranking/RankingApp.tsx`, `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/inspector/sections/InspectorSection.tsx`, `frontend/src/features/folders/FolderTree.tsx`
- Evidence: compare divider uses a `div` drag handle without separator semantics or keyboard step controls. Ranking drag uses `PointerSensor` only. Inspector section reorder uses drag handles and pointer sensors. Sidebar resize handles are pointer-oriented.
- Suggested fix shape: add `role="separator"` with `aria-orientation`, `aria-valuenow`, and Arrow/Home/End stepping for splitters. Add `KeyboardSensor` and `sortableKeyboardCoordinates` where `@dnd-kit` already supports keyboard sorting. Keep custom ranking hotkeys for rank assignment separate from drag-sort semantics.
- Effort: M-L
- Performance/code-bloat risk: Medium. DnD keyboard support should be added narrowly and validated to avoid destabilizing ranking.
- Validation method: keyboard-only compare divider adjustment; keyboard reorder of one ranking card and one inspector section; screen-reader role checks for splitters.

### 9. Form labels, copy affordances, and star controls are inconsistent

- Severity: Medium
- User impact: Users relying on labels, forms mode, or keyboard activation can miss what fields do, and clickable metadata values are not discoverable as controls.
- Root files: `frontend/src/features/embeddings/SimilarityModal.tsx`, `frontend/src/features/metrics/components/AttributesPanel.tsx`, `frontend/src/features/inspector/sections/BasicsSection.tsx`, `frontend/src/features/inspector/sections/SelectionActionsSection.tsx`, `frontend/src/features/inspector/sections/SelectionExportSection.tsx`
- Evidence: several labels visually precede inputs without `htmlFor`/`id` or `aria-describedby`. Metadata path/source/filename values are clickable `span`s rather than buttons. Star controls are placed in a radiogroup while using `aria-pressed` buttons, which mixes rating-radio and toggle-button semantics.
- Suggested fix shape: add a small `Field` helper for `id`, `htmlFor`, helper text, and error IDs. Replace clickable spans with buttons styled as metadata chips. Pick one star-rating model: radio buttons with `aria-checked` and arrow keys, or a plain toggle/button group without `radiogroup`.
- Effort: M
- Performance/code-bloat risk: Low.
- Validation method: Testing Library accessibility queries by label for similarity and attributes controls; keyboard activation test for metadata copy and star rating.

### 10. Clipboard and copy feedback is not resilient

- Severity: Low-Medium
- User impact: Copy actions are common in metadata, sync details, and compare export workflows. When copy succeeds or fails silently, users repeat actions or assume data was copied.
- Root files: `frontend/src/shared/ui/SyncIndicator.tsx`, `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`, `frontend/src/features/inspector/hooks/useInspectorCompareExport.ts`
- Evidence: some clipboard failures are swallowed, some set local error state, and some copy success messages are not live regions. The behavior differs by panel.
- Suggested fix shape: add a tiny `useClipboardAction` helper returning `copy`, `status`, and `error`. Render a shared live status message near copy controls. Avoid toast infrastructure; this can stay local and lightweight.
- Effort: S
- Performance/code-bloat risk: Low.
- Validation method: mock `navigator.clipboard.writeText` success/failure and assert visible/live result messages.

### 11. API error envelopes are robust on the client but inconsistent at the server edge

- Severity: Low-Medium
- User impact: UI code can parse messages today, but inconsistent backend shapes make it harder to present specific recovery guidance for user-triggered actions.
- Root files: `frontend/src/lib/fetcher.ts`, `src/lenslet/web/responses.py`, `src/lenslet/web/export/response.py`, `src/lenslet/web/routes/table_settings.py`, `src/lenslet/web/media.py`
- Evidence: `fetcher.ts` handles `error`, `message`, and `detail`. Some backend paths return `{error,message}`, while others raise `HTTPException` with default FastAPI `detail`. Export response code duplicates a local error-envelope helper.
- Suggested fix shape: keep `fetcher.ts`, but normalize user-action endpoints to `{error,message}` via the existing `error_response` helper. Start with table source switching, export, refresh, and metadata mutation failures. Do not convert every media thumbnail/file 404 unless the UI needs structured recovery there.
- Effort: S-M
- Performance/code-bloat risk: Low if scoped to user-action endpoints.
- Validation method: API tests for failure bodies on table switch/export/update paths; UI tests assert `FetchError.message` is surfaced.

### 12. Loading and disabled states are visible but not always semantically connected to controls

- Severity: Low-Medium
- User impact: Users can see loading/disabled states, but assistive tech may not know why a command is disabled or whether background loading is complete.
- Root files: `frontend/src/shared/ui/Toolbar.tsx`, `frontend/src/shared/ui/toolbar/ToolbarFilterMenu.tsx`, `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/app/menu/AppContextMenuItems.tsx`, `frontend/src/features/ranking/RankingApp.tsx`, `frontend/src/features/inspector/sections/SelectionActionsSection.tsx`
- Evidence: toolbar and context menu labels often include disabled reasons, and the grid has `aria-busy`, but disabled reasons are not consistently connected with `aria-describedby`. Loading overlays and saving indicators are not uniformly exposed as status regions.
- Suggested fix shape: use `aria-describedby` for disabled controls that already render a reason, and standardize loading/saving text with `role="status"` where the state changes asynchronously. Keep the copy concise.
- Effort: S
- Performance/code-bloat risk: Low.
- Validation method: DOM assertions for disabled buttons with described-by helper text; keyboard/screen-reader smoke on loading grid, refresh, and disabled selection export.

## Quick Wins

1. Add live-region semantics to existing messages.
   - Apply `role="alert"` for failures/conflicts and `role="status"` for progress/success in `StatusBar`, `GridTopStack`, selection export errors, notes conflicts, compare metadata copy state, and sync/copy feedback.

2. Make focused grid/tree actions keyboard-openable.
   - Add ContextMenu key and Shift+F10 handling for the active grid cell/tree item, using the existing `openGridActions`/`openFolderActions` state and the focused element's bounding rect.

3. Surface existing save/error state.
   - Render ranking `saveStatus`/`saveError`, await inspector bulk sidecar mutations, and replace refresh/export console-only handling with the existing app status area.

## Medium Projects

1. Lightweight popover/menu primitive.
   - Build a small shared helper for trigger refs, initial focus, roving menu item navigation, Escape/outside close, and focus return. Adopt it in `ContextMenu`, `DropdownMenu`, `ThemeSettingsMenu`, `ToolbarFilterMenu`, and `SyncIndicator` without replacing the strong `Dropdown` listbox behavior.

2. Unified overlay focus policy.
   - Apply `useModalFocusTrap` consistently to modal overlays, define inert/background behavior, and test viewer, compare, similarity search, and ranking fullscreen as one keyboard workflow family.

3. Keyboard parity for manipulation controls.
   - Add keyboard splitters, dnd-kit keyboard sensors where already appropriate, and a cleaned-up virtual grid focus model. Validate against large virtualized data and ranking/compare workflows.

## Things Not To Do

- Do not introduce a heavy design system or external component library just to fix ARIA and focus behavior. The repo already has useful primitives; the gap is consistency.
- Do not add ARIA roles without matching behavior. A `menu`, `dialog`, `radiogroup`, or `separator` role must have the expected keyboard and focus semantics.
- Do not keep both virtual-grid focus models. Pick roving DOM focus or `aria-activedescendant`; carrying both will keep producing edge cases.
- Do not replace console-only failures with `alert()`. Use one accessible in-app error/status surface with retry where possible.
- Do not add per-call bespoke banners everywhere. Centralize small primitives and state channels so repeated workflows feel predictable.
- Do not add expensive per-item listeners or extra DOM to virtualized grid rows. Accessibility fixes must preserve large-tree performance.
- Do not make every media 404 a user-facing app error. Prioritize user-triggered actions and persistent state changes; thumbnail/file misses need graceful visual fallback, not noisy alerts.

## Top 5 Recommendations

1. Surface save and action failures consistently, starting with ranking saves, inspector bulk edits, browse/load refresh, and table source switching.
2. Adopt one overlay focus policy using the existing `useModalFocusTrap`, then apply it to similarity search, ranking fullscreen, viewer, and compare.
3. Consolidate menu/popover behavior into a lightweight primitive with semantic triggers, roving navigation, Escape/outside close, and focus return.
4. Add keyboard equivalents for focused item action menus, compare splitters, and existing drag-sort workflows before these interactions become deeper product dependencies.
5. Normalize form labels, copy controls, disabled reasons, live status messages, and user-action API error envelopes so repeated work is understandable and recoverable.
