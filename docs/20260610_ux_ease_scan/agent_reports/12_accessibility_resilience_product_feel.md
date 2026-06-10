# Accessibility/Resilience Product Feel Scan

## Journeys Inspected

- Read-only inspection of browse mode from boot through toolbar, folder tree, virtual grid, viewer, compare viewer, similarity modal, inspector, metrics, derived score, status banners, context menus, theme/settings, sync indicator, mobile drawer, and responsive layout policy.
- Read-only inspection of ranking mode including loading/error states, unassigned tray, rank buckets, drag/drop, keyboard shortcuts, fullscreen viewer, export, and autosave-oriented flow.
- Reviewed active docs and validation hooks: `README.md`, `frontend/docs/ui-stack-rationale.md`, `docs/dev_notes/Theming.md`, `scripts/browser/gui_smoke`, `scripts/browser/overall_cleanup`, and `scripts/browser/responsive_geometry`.
- Did not launch the live app or run smokes because this assignment requires writing only the assigned report file, while the app and browser smokes create logs, fixtures, caches, and temp artifacts.

## Current Strengths

- Browse grid has a real `role="grid"`, active descendant handling, roving gridcell focus, keyboard navigation, and a polite live region for selection count.
- Global `:focus-visible`, reduced-motion handling, coarse-pointer target expansion, and mobile-specific browse controls are already present.
- The searchable `Dropdown` is stronger than most custom selects: it supports search, disabled options, listbox roles, Escape close, highlighted option movement, and trigger focus restore.
- Compare viewer is the best overlay foundation: it uses `aria-modal="true"`, a focus trap, inert background shell, explicit close/navigation, and stable image loading behavior.
- Status and resilience thinking exists: read-only workspace warning, indexing status, derived metric warnings, sync indicator, lazy surface boundaries, sidecar conflict resolution, and stale-resource guards are all good product trust primitives.
- Existing browser tooling already checks focus, menu bounds, mobile hit targets, reduced motion, responsive geometry, and image alt quality, so many improvements can be validated without a new large framework.

## Ranked Opportunities

1. **Standardize custom menus and popovers**
   - Severity: High.
   - User impact: Fast keyboard and screen-reader users get inconsistent behavior across sort dropdowns, filter popovers, theme/settings, context menus, and sync details. This makes Lenslet feel less trustworthy even when the visual styling is polished.
   - Likely code area: `frontend/src/shared/ui/Dropdown.tsx`, `frontend/src/app/menu/ContextMenu.tsx`, `frontend/src/shared/ui/ThemeSettingsMenu.tsx`, `frontend/src/shared/ui/toolbar/ToolbarFilterMenu.tsx`, `frontend/src/shared/ui/SyncIndicator.tsx`.
   - Fix concept: Create one lightweight `AppMenu`/`AppPopover` primitive for focus entry, roving focus, Arrow/Home/End navigation, typeahead where useful, Escape close, outside click, portal positioning, and focus restore. Preserve the existing visual classes. Use the WAI-ARIA menu/listbox/popover keyboard contracts as acceptance criteria, not as a visual redesign.
   - Effort: M.
   - Performance/code-bloat risk: Medium if implemented as a broad rewrite. Keep it as a small local primitive or selectively adopt a headless primitive only for the complex surfaces called out in `frontend/docs/ui-stack-rationale.md`.
   - Validation method: Extend `scripts/browser/overall_cleanup/menus.py` to Tab and Arrow through every menu, assert focus remains inside while open, assert Escape restores focus to the trigger, and add Vitest helper tests for roving focus state.

2. **Make ranking cards and buckets semantically operable**
   - Severity: High.
   - User impact: Ranking is a speed-critical flow, but draggable `article` cards are not explicit buttons/options, do not expose selected/ranked/unassigned state clearly, and do not announce moves. Keyboard shortcuts work, but assistive tech users cannot confidently understand the board.
   - Likely code area: `frontend/src/features/ranking/RankingApp.tsx`, `frontend/src/features/ranking/hooks/useRankingKeyboard.ts`, `frontend/src/features/ranking/hooks/useRankingDrag.ts`, `frontend/src/features/ranking/ranking.css`.
   - Fix concept: Make cards focusable with clear `aria-label` text including filename, current bucket, position, and selected state. Add `aria-selected` or a listbox/grid pattern for the active card. Use dnd-kit accessibility announcements or a local polite live region for "moved X to rank N" and save/completion status. Add explicit keyboard alternatives for any pointer-only drag action.
   - Effort: M/L.
   - Performance/code-bloat risk: Low to medium. The DOM changes are small; the risk is choosing an overbuilt board abstraction.
   - Validation method: Add ranking browser smoke coverage for Tab focus, Arrow selection, `1-9` assignment announcement, fullscreen focus restore, and useful accessible names. Keep existing ranking keyboard unit tests.

3. **Unify overlay focus semantics**
   - Severity: High.
   - User impact: Compare behaves like a real modal, but the normal viewer uses `role="dialog"` with `aria-modal={false}` and no focus trap, while SimilarityModal has modal markup but no shared trap. Popover-like dialogs such as filters and sync details also mix modal and non-modal semantics.
   - Likely code area: `frontend/src/features/viewer/Viewer.tsx`, `frontend/src/features/embeddings/SimilarityModal.tsx`, `frontend/src/features/compare/CompareViewer.tsx`, `frontend/src/shared/hooks/useModalFocusTrap.ts`, `frontend/src/app/AppShell.tsx`.
   - Fix concept: Define when a surface is a modal dialog versus a non-modal popover. Use `useModalFocusTrap` for actual modals, restore focus to the invoking grid cell or button, and avoid `role="dialog"` for simple popovers unless focus is intentionally managed. Keep viewer light visually, but make its focus model as predictable as compare.
   - Effort: M.
   - Performance/code-bloat risk: Low. Reuses existing focus-trap helper.
   - Validation method: Extend browser probes to open viewer, compare, similarity, filters, and sync card; assert initial focus, Tab containment where modal, background inertness where modal, Escape close, and focus restore.

4. **Route async failures into visible, persistent action feedback**
   - Severity: High.
   - User impact: Several fast actions fail silently or only log to console: table source switching catches and drops errors, clipboard failures are swallowed, selection downloads continue with console-only failures, and folder export uses `alert`. Heavy users need to know whether data changed, saved, exported, or failed.
   - Likely code area: `frontend/src/app/AppShell.tsx`, `frontend/src/app/components/GridTopStack.tsx`, `frontend/src/app/components/StatusBar.tsx`, `frontend/src/app/menu/AppContextMenuItems.tsx`, inspector copy/export hooks, `frontend/src/shared/ui/SyncIndicator.tsx`.
   - Fix concept: Wire a small action feedback channel into `GridTopStack` or `StatusBar`: success, warning, error, retry/dismiss where relevant. Replace `alert` with the same banner. Include action names and affected count/path, for example "3 downloads failed" or "Image column switch failed".
   - Effort: M.
   - Performance/code-bloat risk: Low if modeled as one state object and a small banner component.
   - Validation method: Unit-test failure reducers and browser-smoke forced API failures for table source switch/export/download/copy. Assert `role="alert"` for errors and `role="status"` for non-error progress.

5. **Add intentional empty and no-result states in the grid**
   - Severity: Medium/High.
   - User impact: A blank gallery after filtering, search, unsupported source switching, similarity constraints, or loading delays can feel like data loss. Lenslet needs to distinguish "still loading", "no files here", "no matches", and "backend query unavailable".
   - Likely code area: `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/app/components/GridTopStack.tsx`, `frontend/src/app/model/loadingState.ts`, `frontend/src/app/model/filterChips.ts`, `frontend/src/app/hooks/useAppDataScope.ts`.
   - Fix concept: Add one compact grid empty-state component with state-specific copy and a direct action when available: clear filters, exit similarity, open root, refresh, or inspect warning. Keep it utilitarian and non-ornamental.
   - Effort: S/M.
   - Performance/code-bloat risk: Low. Render only when `items.length === 0` and not loading.
   - Validation method: Vitest state matrix for empty-state selection and browser checks for search no-result, active filters no-result, empty folder, and loading overlay.

6. **Use semantic buttons for copyable inspector and metadata values**
   - Severity: Medium.
   - User impact: Some high-value inspector actions are clickable spans or JSON keys with cursor/hover styling only. Mouse users can discover them, but keyboard and screen-reader users miss copy affordances and copied feedback.
   - Likely code area: `frontend/src/features/inspector/sections/BasicsSection.tsx`, `frontend/src/features/inspector/sections/JsonRenderCode.tsx`, `frontend/src/features/inspector/sections/MetadataSection.tsx`, `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`, `frontend/src/features/inspector/sections/QuickViewSection.tsx`.
   - Fix concept: Convert clickable labels/JSON keys to visually quiet `button` elements with `aria-label="Copy ..."` and a shared copied-status live region. Keep dense typography and avoid adding extra icons everywhere.
   - Effort: S/M.
   - Performance/code-bloat risk: Low.
   - Validation method: Render tests for accessible names plus browser Tab checks in inspector sections. Assert copied feedback is announced and visible without changing layout height.

7. **Expose gallery cell names, state, and selection order**
   - Severity: Medium.
   - User impact: The grid has good structural roles, but individual cells do not expose a complete accessible name or selection order. Fast keyboard users need to hear filename, dimensions, selected state, and position without entering the image.
   - Likely code area: `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/features/browse/components/VirtualGridRows.tsx`, `frontend/src/features/browse/components/ThumbCard.tsx`.
   - Fix concept: Add `aria-label` or `aria-labelledby`/`aria-describedby` on gridcells using filename, dimensions, selected/unselected, and selection order when present. Consider `aria-rowcount`, `aria-colcount`, and `aria-posinset` only if they can stay correct under virtualization.
   - Effort: S.
   - Performance/code-bloat risk: Low, but avoid expensive per-render string work for large grids.
   - Validation method: Browser accessibility snapshot for several grid states and existing `assert_useful_image_alt` extended to gridcell names.

8. **Make sliders and drag handles keyboard-complete**
   - Severity: Medium.
   - User impact: Thumbnail size and viewer zoom are native sliders, but sidebars, compare divider, metric rail, and ranking unassigned height rely heavily on pointer drag. Users on keyboard, trackpad, stylus, or touch need predictable alternatives.
   - Likely code area: `frontend/src/app/layout/useSidebars.ts`, `frontend/src/app/components/LeftSidebar.tsx`, `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/compare/CompareViewer.tsx`, `frontend/src/features/browse/components/MetricScrollbar.tsx`, `frontend/src/features/ranking/hooks/useUnrankedPanelSizing.ts`.
   - Fix concept: Make resize/divider handles focusable with `role="separator"` and `aria-orientation`, support Arrow/Page/Home/End where useful, expose current value via `aria-valuenow` where it behaves like a splitter, and keep pointer hitboxes large on coarse pointers.
   - Effort: M.
   - Performance/code-bloat risk: Low.
   - Validation method: Browser keyboard tests for left/right sidebar resize, compare split movement, ranking unassigned height, and metric rail focusability.

9. **Clarify status banner severity and announcement behavior**
   - Severity: Medium.
   - User impact: Read-only, indexing, source warnings, derived score warnings, zoom warnings, and off-view updates are visually similar. Some should interrupt (`role="alert"`), some should politely update (`role="status"`), and some should be passive.
   - Likely code area: `frontend/src/app/components/StatusBar.tsx`, `frontend/src/app/components/GridTopStack.tsx`, `frontend/src/shared/ui/SyncIndicator.tsx`, `frontend/src/styles.css`.
   - Fix concept: Add a `StatusBanner` primitive with severity, role, dismiss, optional action, and compact visual variants. Use it everywhere instead of ad hoc `ui-banner` blocks. Reserve danger styling for data-loss or failed actions.
   - Effort: S/M.
   - Performance/code-bloat risk: Low.
   - Validation method: Component tests for role/label/dismiss behavior and browser smoke for read-only, indexing, derived warning, zoom warning, and off-view update.

10. **Centralize shortcut metadata without adding a heavy help layer**
   - Severity: Medium.
   - User impact: Lenslet has powerful shortcuts, but they are scattered across titles, README text, and hook code. Heavy users benefit from consistent labels; assistive tech benefits from `aria-keyshortcuts`.
   - Likely code area: `frontend/src/app/hooks/useAppKeyboardShortcuts.ts`, `frontend/src/features/browse/hooks/useKeyboardNav.ts`, `frontend/src/features/viewer/Viewer.tsx`, `frontend/src/features/compare/CompareViewer.tsx`, `frontend/src/features/ranking/model/keyboard.ts`, toolbar and inspector buttons.
   - Fix concept: Add a small shortcut registry that feeds `title`, `aria-keyshortcuts`, and tests. Do not add a visible tutorial panel. Keep visible text work-focused and surface shortcuts only in tooltips/button metadata.
   - Effort: S/M.
   - Performance/code-bloat risk: Low.
   - Validation method: Unit tests that shortcut labels match handlers, plus browser checks that critical controls expose `aria-keyshortcuts`.

11. **Align ranking visual language with browse mode**
   - Severity: Medium.
   - User impact: Ranking looks more glassy and ornamental than browse mode, with larger radii, heavy blur, and many raw rgba values. It feels like a separate product even though it shares Lenslet's trust and speed promise.
   - Likely code area: `frontend/src/features/ranking/ranking.css`, `frontend/src/theme.css`, shared button/token styles.
   - Fix concept: Reuse Lenslet tokens for borders, panels, buttons, focus rings, and text hierarchy. Reduce decorative blur/radii where they do not improve task speed. Keep the ranking board visually distinct through layout and rank dots, not through a separate aesthetic system.
   - Effort: M.
   - Performance/code-bloat risk: Low to medium. Removing blur/shadow can improve paint cost; the risk is churn if done as a reskin instead of token alignment.
   - Validation method: Screenshot comparison at desktop/tablet/mobile, reduced-motion check, and CSS scan for one-off rgba/radius values in ranking.

12. **Add a lightweight accessibility release gate**
   - Severity: Medium.
   - User impact: The repo has focused helpers, but no single acceptance path that says "keyboard/touch/assistive-tech product feel is still intact" across browse and ranking. Regressions can slip in while features move quickly.
   - Likely code area: `scripts/browser/overall_cleanup`, `scripts/browser/responsive_geometry`, `scripts/browser/gui_smoke`, `tests/browser`.
   - Fix concept: Add an optional accessibility scenario pack to existing browser smokes: tab order, focus restore, menu keyboarding, modal trap, grid accessible names, touch action visibility, reduced motion, and ranking card semantics. Keep it scenario-driven and under the same lean smoke philosophy.
   - Effort: M.
   - Performance/code-bloat risk: Low if it reuses existing fixtures and helpers.
   - Validation method: Run as `python -m scripts.browser.gui_smoke.acceptance` extension or a separate `overall_cleanup` command; include a JSON evidence summary.

## 3 Quick Wins

- Add gridcell accessible names and selection-order descriptions in `VirtualGridRows`/`ThumbCard`.
- Give `ContextMenu`, `ToolbarFilterMenu`, and `ThemeSettingsMenu` first-focus, Arrow navigation, Escape focus restore, and tests before changing visuals.
- Replace `alert`/console-only failures in export/source switch/copy paths with the existing `GridTopStack` action-error band, using proper `role="alert"`.

## 3 Medium Projects

- Build a small `AppMenu`/`AppPopover`/`AppDialog` behavior layer that preserves current styling while centralizing focus, Escape, outside click, and ARIA contracts.
- Do a ranking accessibility pass: semantic cards/buckets, live announcements, focus restore, keyboard alternatives for drag/resize, and browser evidence.
- Create a unified status/action feedback system for read-only, sync, indexing, source switching, exports, similarity, and inspector conflict/copy actions.

## Things Not To Do

- Do not add a full UI kit or large design-system rewrite to solve a handful of interaction contracts.
- Do not add ornamental empty states, animated tours, or marketing-style help. Lenslet should stay dense, calm, and task-first.
- Do not rely on color or hover alone for state. Every state that matters should also have text, structure, or ARIA state.
- Do not add more global shortcuts until focus ownership and `aria-keyshortcuts` metadata are consistent.
- Do not use blocking `alert()` for recoverable workflow errors.
- Do not make ranking prettier by increasing blur, shadows, or decorative card treatment; improve trust through consistency, semantics, and state feedback.
- Do not broaden smoke tests into brittle pixel-perfect assertions. Keep them scenario-driven around focus, roles, hit targets, and clear state.

## Top 5 Recommendations

1. Standardize menus/popovers with shared keyboard, focus restore, and ARIA behavior.
2. Make ranking cards and buckets semantically operable and announce rank moves.
3. Unify modal and popover focus semantics across viewer, compare, similarity, filters, sync, and settings.
4. Route async failures and successes into visible, non-blocking action feedback.
5. Add intentional empty/no-result/loading states so blank grids never look like broken data.
