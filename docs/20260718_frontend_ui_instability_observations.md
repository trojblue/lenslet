# Lenslet Frontend UI Instability Observations

Status: observation and diagnosis only. No product behavior was changed in this pass.

## Outcome

Lenslet's remaining jitter is not one animation bug. The repeated pattern is that target changes, request progress, and short-lived diagnostics are allowed to alter normal document flow or replace settled content before the next state is known. The user sees technically valid intermediate React states that are semantically false or too short-lived to be useful.

The most important causal chain is:

```text
user action
  -> new target/query identity has no settled snapshot
  -> each consumer independently renders empty, idle, zero, or fallback UI
  -> conditional rows, labels, controls, and bands enter/leave layout
  -> response settles and the intended UI replaces them one or two frames later
```

The primary design requirement should therefore be **presentation continuity**: keep one target-owned, settled presentation until the replacement is ready; distinguish pending from absent or failed; and keep transient information out of layout flow.

## Scope and Method

This audit covered all source under `frontend/src/`, including metrics and filters, Derived Score, browse/grid, toolbar and top-stack, folders, Inspector, Viewer/Compare, ranking, shared menus, responsive behavior, bootstrap, and theme/settings surfaces.

Three read-only subagent scans independently covered:

1. Metrics, filters, facets, and Derived Score.
2. Browse shell, gallery, toolbar, folders, Inspector, Viewer/Compare, and ranking.
3. Shared controls, popovers, responsive/bootstrap behavior, modals, and CSS.

The main session traced the reported source paths and ran a live Chromium probe against a synthetic 1,585-row table at 390x844, 820x900, and 1440x920. The interaction measurements below were taken at 1440x920. Historical files under `docs/agents_archive/` were excluded as instructed. No current top-level `DESIGN_SYSTEM.md`, `FRONTEND_GUIDELINES.md`, `APP_FLOW.md`, `PRD.md`, `TECH_STACK.md`, or `LESSONS.md` exists; current design context came from the shipping code, the active 2026-06-10 UX plan, the 2026-07-17 continuity plan, and the live app.

## Live Evidence

| Interaction | Settled state before | Intermediate/after state | Measured effect |
| --- | --- | --- | --- |
| Apply categorical filter `dataset_from: gt` | Card 116.72px high; no `Active` row | `Active: gt` plus a new card-level `Clear` button | Card became 178.66px, a **61.94px vertical shift** |
| Drag numeric histogram range | Card 283.81px high; one-line `Drag to filter` footer | Range plus `Cursor` on a second line; `Filtered: 0` also appeared while the new target was pending | Card became 295.38px, an **11.57px shift** |
| Select the next image with Inspector Metadata autoloaded | Loaded Metadata with `Show PIL info / Copy` | At ~39ms: `Show PIL info / Load meta / PNG metadata not loaded yet`; at ~56ms: loaded Metadata returned | A **painted false-idle frame**; the request was fast enough that `Loading…` never painted |
| Focus Derived Score `Missing` | Native select at x=82, y=419.625, 168x32 | Same node, same rectangle, same value after focus | No React remount or layout change; the open-popup flash is most likely the browser/OS native popup boundary and needs a headed filmstrip to confirm |

The live result validates the user's distinction: a fallback can be visually harmful even when it lasts for only one painted frame and even when geometry is reserved.

## Systemic Root Causes

### R1. Conditional diagnostics are in normal flow

`Active`, `Selected`, `Cursor`, error, warning, count, and clear-action rows are frequently mounted only while relevant. The content is secondary, but it moves the primary controls and everything below them. Long labels make several shifts unbounded because the rows wrap.

### R2. Query identity and presented identity are split

React Query correctly creates a new target identity for a filter, search, or sort. Most consumers immediately read that target's empty initial state, while only the grid has a retained presentation grace. Toolbar totals, filter counts, metric rail, comparison eligibility, and metrics completeness therefore disagree during the same request.

### R3. Pending, absent, and failed are conflated

The Inspector Metadata flash is the clearest example. A new path synchronously projects an `idle` empty view; passive effects start autoload afterward. `idle` is rendered as “not loaded yet,” even though autoload is already the intended behavior. Similar empty-to-full substitutions exist in facets, derived previews, modal content, and first-use lazy boundaries.

### R4. Restoration and responsive truth arrive after paint

Persisted shell settings and media queries are read in effects. The app first paints defaults, then corrects grid size, view mode, panels, or mobile toolbar structure.

### R5. Utility surfaces are recreated from invisibility

Shared dropdown panels conditionally mount, measure, and run an opacity/translation entrance on every open. Theme Settings positions even later in a passive effect. These mechanics turn frequent controls into repeated flashes.

### R6. Native and app-owned controls are mixed

Derived `Missing` and the width/height operators use native selects inside an otherwise custom dark UI. The closed control is styled, but its popup belongs to the browser/OS compositor. Its paint, theme, and animation are not controlled by the app.

### R7. Async content changes control type or card shape

First facet hydration or a change to an uncached facet field batch can replace a Dropdown with an input, an empty message with a full histogram, or a compact fallback with a chart. Virtualized show-all lists then remeasure and translate every following card.

### R8. Resource identity is sometimes weaker than displayed identity

Compare and ranking can update labels or target paths before decoded media is atomically associated with them. That produces old content under new labels or a blank image surface.

## Finding Registry

### Critical and High

#### UI-01 — Categorical and metric-class filters insert redundant `Active` and `Clear` rows

- Trigger: select the first categorical value or metric class; clear the last selection.
- Symptom: the card and every following control move vertically. Long active values wrap and amplify the shift.
- Source: `frontend/src/features/metrics/components/CategoricalCard.tsx:59-64,96-103`; `frontend/src/features/metrics/components/MetricCategoryCard.tsx:56-61,94-101`.
- Observation: active button styling and the grid-level Filters chip already communicate the filter. The extra `Active` row is redundant, as the user noted.
- Stabilization direction: remove the `Active` row; remove the card-level Clear action or keep a persistent same-height action slot if local clearing remains necessary.

#### UI-02 — Histogram range and cursor information creates a second footer line

- Trigger: drag a range while the pointer remains over the histogram.
- Symptom: the footer grows immediately after pointer-up and shrinks on pointer-leave.
- Source: `frontend/src/features/metrics/components/MetricHistogramCard.tsx:180-199`; pointer-up intentionally retains hover in `frontend/src/features/metrics/hooks/useMetricHistogramInteraction.ts:131-140`.
- Stabilization direction: keep one fixed-height textual footer. Put cursor value in an SVG tooltip/overlay or one reserved inline slot; never append a second flow line.

#### UI-03 — Filtered completeness can briefly manufacture `Filtered: 0`

- Trigger: a new filter target before its first page arrives.
- Symptom: count text appears as zero, then changes to the real result; wrapped headers can gain or lose a line.
- Source: `metricsFilteredItemsComplete` uses `items.length >= filteredCount` at `frontend/src/app/AppShell.tsx:645`; missing first-page totals fall back to `items.length` at `frontend/src/app/hooks/useAppDataScope.ts:544-546`; count rows are conditional in `MetricHistogramCard.tsx:143-152`, `CategoricalCard.tsx:51-58`, and `MetricCategoryCard.tsx:48-55`.
- Stabilization direction: completeness must require a settled response owned by the current target, not `0 >= 0`; retain the settled count or use a fixed-width neutral pending value.

#### UI-04 — Browse consumers do not share one atomic presented snapshot

- Trigger: filter, sort, or search creates a new query key.
- Symptom: grid content is retained, but toolbar count changes to `0 items`, rating counts drop to zero, and the metric rail disappears before all return.
- Source: new keys have no placeholder data at `frontend/src/api/folders.ts:293-325`; page, items, and totals fall back independently at `frontend/src/app/hooks/useAppDataScope.ts:430-452,537-549`; consumers include `frontend/src/app/AppShell.tsx:773-776,830-843,1201,1435-1455` and `frontend/src/shared/ui/Toolbar.tsx:292-310,667-674`.
- Stabilization direction: define one `presentedBrowseSnapshot` containing items, totals, counts, facet/rail summaries, and settled identity. Retain it through the grace window and swap it atomically.

#### UI-06 — Inspector Metadata paints a false idle fallback on every path change

- Trigger: click a new image with metadata autoload enabled.
- Symptom: loaded metadata flashes to `Load meta / PNG metadata not loaded yet`, then returns to loaded content. This is semantic flashing even though the section height and PIL action width are reserved.
- Source: context mismatch returns `EMPTY_SINGLE_METADATA_VIEW` with `metaState: 'idle'` at `frontend/src/features/inspector/hooks/useInspectorSingleMetadata.ts:35-48,65-69,127-136`; reset and autoload occur in passive effects at `:71-78,122-125`; loading begins at `:80-89`; Inspector maps idle to the false fallback at `frontend/src/features/inspector/Inspector.tsx:494-509`. Existing reservations are at `Inspector.tsx:502` and `frontend/src/features/inspector/sections/MetadataSection.tsx:48-64,85-93`.
- Stabilization direction: when autoload is enabled and a target path exists, project a synchronous target-owned pending state. Keep “not loaded yet / Load meta” exclusively for autoload-off idle. A neutral loader may itself be delayed (for example, about one second) so fast metadata requests swap directly without any transient copy.

#### UI-07 — Filter/status/similarity bands change gallery geometry

- Trigger: first/last filter, additional wrapped chips, similarity mode, indexing state, zoom warning, off-view activity, or action feedback.
- Symptom: the gallery moves vertically and its viewport changes; wrapped chips multiply the movement.
- Source: hidden bands render a zero-height reserve at `frontend/src/app/components/GridTopStack.tsx:37-55`; CSS confirms height zero at `frontend/src/styles.css:547-565`; variable content mounts in flow at `GridTopStack.tsx:69-153` and `frontend/src/app/components/StatusBar.tsx:139-246`.
- Stabilization direction: use a fixed one-line horizontally constrained filter rail. Present transient warnings/actions as overlays or toasts. If a band is reserved, reserve its real geometry rather than zero.

#### UI-08 — Derived Score drafts can reset on ordinary browse responses

- Trigger: a filter/browse response reconstructs semantically unchanged metric-key arrays.
- Symptom: Derived controls repaint and unsaved draft edits can be overwritten, which is both instability and data loss.
- Source: reset effect depends on referentially new `sourceMetricKeys` at `frontend/src/features/metrics/components/DerivedScoreCard.tsx:68-78,99-101`; evaluation/key arrays are rebuilt through `frontend/src/app/hooks/useAppDataScope.ts:501-535` and `frontend/src/features/metrics/model/derivedMetric.ts:280-334`.
- Stabilization direction: reset only on a semantic spec/scope/schema token; compare key contents and preserve an active draft across data refresh.

#### UI-09 — Persisted shell settings restore after first paint

- Trigger: returning with saved grid size, view mode, closed panels, metadata autoload, or media settings.
- Symptom: default adaptive/220px/both-panels-open UI paints, then snaps to saved settings.
- Source: defaults at `frontend/src/app/AppShell.tsx:267-289`; restoration in `useEffect` at `frontend/src/app/hooks/usePersistedAppShellSettings.ts:192-231`; `persistedSettingsReady` guards writes, not initial presentation.
- Stabilization direction: synchronously read one restored snapshot before AppShell state initialization.

#### UI-10 — Mobile responsive truth is corrected after paint

- Trigger: first load at mobile/tablet breakpoints.
- Symptom: desktop-oriented toolbar DOM or contradictory reserved mobile space appears before the toolbar swaps.
- Source: `frontend/src/shared/hooks/useMediaQuery.ts:3-15` initializes false and reads `matchMedia` in an effect; Toolbar consumes it at `frontend/src/shared/ui/Toolbar.tsx:156-173` while AppShell already has synchronous viewport geometry.
- Stabilization direction: use a synchronous media-query snapshot, preferably `useSyncExternalStore`, so all responsive owners agree on the first render.

#### UI-11 — Derived `Missing` is a native popup surface

- Trigger: open Derived Score `Missing`; the same family applies to width/height operators and native date inputs.
- Symptom: the reported flash does not involve a React remount or geometry change; it most likely occurs at the browser/OS popup boundary against the dark custom UI.
- Source: native select at `frontend/src/features/metrics/components/DerivedScoreCard.tsx:317-331`; width/height selects at `frontend/src/features/metrics/components/AttributesPanel.tsx:264-278,301-315`; dates at `AttributesPanel.tsx:239-252`; closed-control CSS only at `frontend/src/styles.css:640-668`; no document `color-scheme` contract in `frontend/src/theme.css`.
- Confidence: high-confidence source inference plus live proof that focusing the control preserves the exact React node and rectangle. The native popup itself was not captured in headless Chromium.
- Stabilization direction: hard-cut the three selects to the app-owned Dropdown. `color-scheme: dark` can improve remaining native widgets but cannot fully control native popup compositing.

#### UI-12 — Shared utility popups animate from opacity zero on every open

- Trigger: open Dropdown, DropdownMenu, toolbar Filters, ContextMenu, or the SyncIndicator status card.
- Symptom: repeated fade/4px slide; search result count changes can also resize and reposition the open panel.
- Source: panels mount conditionally at `frontend/src/shared/ui/Dropdown.tsx:326-372,519-523`; `.dropdown-panel` always runs `slideDown` from opacity zero at `frontend/src/styles.css:1363-1366,1495-1508`. SyncIndicator separately conditionally mounts a card with the same animation at `frontend/src/shared/ui/SyncIndicator.tsx:119-157` and `frontend/src/styles.css:869-883`.
- Stabilization direction: remove opacity entrance animation from frequently used utility surfaces; keep a stable measured shell and update only its contents. Reserve the checkmark column and lock above/below placement for one open lifetime.

### Medium

#### UI-13 — Uncached facet batches replace settled cards and sometimes control types

- Trigger: active metric/categorical fields change to an uncached facet batch, or the first facet payload hydrates.
- Symptom: full cards switch through local/empty paths; a Derived categorical value control can change from input to Dropdown and lose focus.
- Source: a new field-batch query initially has no merged payload at `frontend/src/api/folders.ts:360-394` and `frontend/src/app/AppShell.tsx:619-623`; consumers branch at `frontend/src/features/metrics/components/MetricRangePanel.tsx:60-82,102-134`, `CategoricalPanel.tsx:46-60`, `DerivedScorePanel.tsx:58-66`, and `DerivedScoreCard.tsx:424-456`.
- Stabilization direction: retain per-field settled facets while refreshing; keep one fixed control type with disabled/loading state.

#### UI-14 — Empty/loading cards and ready cards do not share a shell

- Trigger: first facet hydration or a newly visible show-all field.
- Symptom: a one-line “No values” card becomes a full plot/list.
- Source: `MetricHistogramCard.tsx:125-134` versus `:138-252`; `CategoricalCard.tsx:29-35` versus `:48-104`; `MetricCategoryCard.tsx:36-42` versus `:45-103`.
- Stabilization direction: keep one stable card frame with equal loading, empty, and ready plot/list regions.

#### UI-15 — Selection inserts multiple metrics blocks

- Trigger: select/deselect one or more images.
- Symptom: a whole Selected Metrics card appears at the top; headers and individual categorical rows gain extra text lines.
- Source: `frontend/src/features/metrics/MetricsPanel.tsx:68-81,115-138`; `MetricHistogramCard.tsx:147-151`; `CategoricalCard.tsx:55,87-91`; `MetricCategoryCard.tsx:52,85-89`.
- Stabilization direction: consolidate selection into reserved header cells and chart overlays; avoid per-row flow insertion.

#### UI-16 — Show-all virtualization amplifies variable card height

- Trigger: active/clear/selection/facet content changes inside a visible virtual card.
- Symptom: the virtualizer remeasures the card, translates all following cards, and may change the requested visible facet batch.
- Source: estimates at `frontend/src/features/metrics/components/MetricRangePanel.tsx:174-181` and `CategoricalPanel.tsx:129-136`; dynamic measuring and absolute translation at `frontend/src/features/metrics/components/VirtualFieldList.tsx:20-26,69-86`.
- Stabilization direction: invariant show-all card frames or explicit scroll-anchor compensation. Removing conditional rows eliminates most remeasurement.

#### UI-17 — Derived previews and diagnostic regions change height asynchronously

- Trigger: choose a term, wait for facets, produce a valid score, or apply invalid formula code.
- Symptom: mini histogram appears; “No finite values” changes to a taller chart; score preview and diagnostics insert whole regions; long status/formula text wraps.
- Source: `frontend/src/features/metrics/components/DerivedScoreCard.tsx:359-366,494-512,580-584`; mismatched mini-histogram shapes at `DerivedMetricMiniHistogram.tsx:13-21,28-58`.
- Stabilization direction: fixed preview and diagnostic slots with capped lines plus disclosure/tooltip for overflow.

#### UI-18 — Compare media can lag behind new labels

- Trigger: navigate Compare to the next pair.
- Symptom: prior images can remain under new path labels for a frame; thumbnails remain dimmed during load.
- Source: readiness resets in a passive effect at `frontend/src/features/compare/CompareViewer.tsx:76-90`; old blob URLs persist through `CompareViewer.tsx:111-138` and `frontend/src/shared/hooks/useBlobUrl.ts:102-134,161-225`; rendering at `CompareViewer.tsx:329-411`.
- Stabilization direction: bind decoded resources to their pair identity and swap resource plus labels atomically. If old media is retained, retain old labels and mark the pair as transitioning.

#### UI-19 — Similarity modal is centered around variable async content

- Trigger: open with changing selection/mode, embeddings arrive, or validation/request errors appear.
- Symptom: path/vector editor changes height and the vertically centered dialog moves at both edges.
- Source: post-open state reset at `frontend/src/features/embeddings/SimilarityModal.tsx:46-59`; centered shell and conditional regions at `:164-177,188-212,237-275,303-321`.
- Stabilization direction: prepare mode as part of the open action; use fixed header/footer, bounded scroll body, and reserved query/status regions.

#### UI-20 — Scrollbar appearance changes persistent pane width

- Trigger: Inspector, FolderTree, ranking panes, or lists cross their overflow threshold on classic/non-overlay scrollbar platforms.
- Symptom: on those platforms, content width can lose the styled scrollbar width (10px in WebKit), rewrapping text and moving actions. Overlay-scrollbar platforms may not consume layout width.
- Source: scrollbar styling without `scrollbar-gutter` at `frontend/src/styles.css:112-124`; persistent Inspector and FolderTree containers at `frontend/src/features/inspector/Inspector.tsx:716-723` and `frontend/src/features/folders/FolderTree.tsx:184-207`; ranking scroll regions at `frontend/src/features/ranking/ranking.css:384-465`.
- Stabilization direction: `scrollbar-gutter: stable` on persistent scroll containers.

#### UI-21 — Folder counts and children arrive without reserved positions

- Trigger: expand an uncached folder or wait for recursive count resolution.
- Symptom: the count badge appears later and shrinks/moves the filename/action area; children appear as an unreserved block.
- Source: `frontend/src/features/folders/FolderTree.tsx:267-274,305-326,357-361,379-394`.
- Stabilization direction: reserve the count column and show one stable child-loading row for expanded pending folders.

#### UI-22 — Toolbar and sync labels have unstable width

- Trigger: pending/result totals, local typing start/end, or copy feedback.
- Symptom: nearby toolbar controls shift horizontally; sync card dividers move.
- Source: item count at `frontend/src/shared/ui/Toolbar.tsx:292-310,667-674`; typing and copy text at `frontend/src/shared/ui/SyncIndicator.tsx:99-149`.
- Stabilization direction: fixed tabular text slots/right alignment, or move ephemeral secondary text into a floating status card.

#### UI-23 — Theme Settings and browser zoom guidance arrive after paint

- Trigger: open Settings; load at non-100% browser zoom; async source/status content changes.
- Symptom: Settings appears a frame late and can retain stale placement; zoom adds a late top band.
- Source: Settings readiness/measurement in passive effect and RAF at `frontend/src/shared/ui/ThemeSettingsMenu.tsx:276-279,322-365`; late zoom measurement at `frontend/src/app/hooks/useBrowserZoomWarning.ts:28-46`.
- Stabilization direction: layout-timed/cached placement with size observation; initialize zoom synchronously or use non-layout-changing guidance.

#### UI-24 — Ranking still has media and layout discontinuities

- Trigger: fullscreen navigation, viewport/tray restoration, or save failure.
- Symptom: uncached fullscreen image can blank; a restored tray height can snap after paint when it no longer fits the current workspace/viewport; save error can add a wrapped header row.
- Source: bare fullscreen image swap at `frontend/src/features/ranking/hooks/useRankingFullscreen.ts:100-113` and `frontend/src/features/ranking/RankingApp.tsx:550-589`; preload does not await decode at `frontend/src/features/ranking/hooks/useRankingSession.ts:103-111`; tray clamp at `frontend/src/features/ranking/hooks/useUnrankedPanelSizing.ts:69-106`; save error at `RankingApp.tsx:409-470` with responsive wrapping in `frontend/src/features/ranking/ranking.css:772-800`.
- Stabilization direction: decoded target resource ownership, pre-paint tray clamp, and a reserved/overlay save-status position.

### Lower priority but real

#### UI-05 — A latent Compare auto-close path depends on transient query state

- Trigger: an external or programmatic query-state change while Compare is open. Normal pointer-driven filter/sort actions are unavailable because the browse shell and toolbar are inert under Compare (`frontend/src/app/AppShell.tsx:560-582`).
- Symptom: if such a transition is supported, the selection pool can become empty for the pending target and close Compare even if its paths will be valid after the response. This is a code-path risk, not a reproduced normal user flow.
- Source: `frontend/src/app/AppShell.tsx:468-479`; `frontend/src/app/hooks/useAppSelectionViewerCompare.ts:147-163,312-315`; `frontend/src/app/components/LeftSidebar.tsx:192-200`.
- Direction: first reproduce through a supported route; if reachable, reconcile selection and Compare only against the settled presented snapshot or a definitive target result.

#### UI-25 — Context menus can resize without reclamping

- Trigger: labels change to `Refreshing…` or `Exporting…` while open.
- Symptom: intrinsic width changes but viewport position does not update.
- Source: `frontend/src/app/menu/AppContextMenuItems.tsx:156-200,237-270,315-326`; position dependencies at `frontend/src/app/menu/ContextMenu.tsx:22-50`.
- Direction: fixed menu width or ResizeObserver-driven reclamp; use a stable busy icon/column.

#### UI-26 — Cold thumbnails still pop in independently

- Trigger: first load or fast scroll into uncached thumbnails.
- Symptom: background-only cards receive images individually with a 160ms fade.
- Source: `frontend/src/features/browse/components/ThumbCard.tsx:42-48,72-81,83-104,128-143`; scroll-idle behavior at `frontend/src/features/browse/components/VirtualGrid.tsx:270-287`.
- Direction: stable neutral skeleton and decode-before-reveal for a visible cohort. The decoded URL cache solves remount flashes, not cold-load pop-in.

#### UI-27 — Cold boot and lazy first-use fallbacks are shown immediately

- Trigger: every cold app boot/health check, plus first Inspector/Compare/ranking chunk load.
- Symptom: `Loading Lenslet...` always replaces the app during cold boot, and short `Loading ...` surfaces replace lazy surfaces even when their work is fast.
- Source: boot state starts loading and health begins in a passive effect at `frontend/src/app/AppModeRouter.tsx:9-37`; lazy boundaries are at `frontend/src/app/AppShell.tsx:136-137,1459-1498,1530-1550`; ranking loader sequence is at `AppModeRouter.tsx:36-45` and `frontend/src/features/ranking/RankingApp.tsx:347-357`.
- Direction: use one stable boot shell with an approved delayed loader, idle-prefetch chunks, and keep one persistent skeleton across module and data loading.

#### UI-28 — Debounced search clears selection at a delayed moment

- Trigger: type into search.
- Symptom: selection badges and Inspector disappear after the 250ms debounce rather than at the explicit input action or settled response.
- Source: debounce at `frontend/src/app/hooks/useAppDataScope.ts:327-333`; clearing at `frontend/src/app/AppShell.tsx:1047-1052`.
- Direction: choose one coherent policy: clear immediately on explicit search, or retain until the settled target proves the selection out of view.

## Stable Patterns to Preserve

- Histogram population, filtered, selected, range, cursor, and selection markers are drawn inside one fixed SVG. The chart overlays themselves do not cause geometry shifts (`MetricHistogramCard.tsx:153-179`).
- Grid loading/empty/error presentation is absolute, and the bottom status row has a minimum height (`frontend/src/features/browse/components/VirtualGrid.tsx:852-878`).
- The metric rail slot keeps fixed width even when inactive (`frontend/src/styles.css:567-590`).
- Inspector Metadata already reserves body height and PIL action geometry; only its state semantics are wrong.
- Recent Quick View and Basics reservations protect Inspector geometry across hydration.
- Viewer already delays its loader and retains decoded media through target transitions; this is the reference pattern for metadata, Compare, ranking, and cold media.
- Toolbar refresh/back/upload/filter-count slots explicitly reserve width. The same pattern should govern totals and sync text.
- Reduced-motion CSS exists and should remain honored (`frontend/src/styles.css:1994-1999`).

## Validation Gaps

1. Metrics tests mostly assert strings. There is no frame-level bounding-box contract for filter apply, histogram drag, categorical selection, facet hydration, or selection overlays.
2. The current Inspector continuity gate does not reject the semantically false `PNG metadata not loaded yet` frame. Add this exact forbidden state when autoload is enabled.
3. Native popup flashing needs a headed Chromium/Edge filmstrip because headless screenshots cannot capture the OS popup reliably.
4. No test captures the first painted frame with persisted settings or mobile media queries.
5. Shared dropdown tests cover behavior and classes, not painted opacity, placement stability, or open-panel height changes.
6. GridTopStack tests assert reserve nodes but not their zero geometry.
7. Compare and ranking need decoded-resource/label identity traces similar to Viewer continuity.

The smallest useful future browser gate is not a generic visual-testing framework. Extend the existing painted-frame sampler with a focused `ui_stability` scenario that records named rectangles, text-state transitions, node identity, and decoded media identity for the interactions above. A one-frame false fallback, replaced stable node, or greater-than-one-pixel unintended anchor movement should fail.

DESIGN AUDIT RESULTS:

Overall Assessment: Lenslet has several strong local continuity patterns, but no application-wide presentation contract. Short-lived request and diagnostic states are still allowed to change geometry or briefly assert false outcomes, which makes otherwise fast interactions feel unstable.

PHASE 1 — Critical (remove false states and query-transition geometry)

- Metrics filter cards: redundant Active/Clear flow rows -> filter state communicated by pressed controls and the existing filter rail -> removes the largest measured card shift.
- Histogram footer: two-line range/cursor state -> one reserved information slot or chart overlay -> pointer movement no longer resizes the card.
- Browse query presentation: independent empty target fallbacks -> one atomic settled presentation snapshot -> totals, grid, rail, filters, and selection agree during transitions; validate the latent Compare path separately.
- Inspector Metadata: autoload target projects idle/not-loaded -> synchronous pending with delayed neutral loading -> fast loads swap directly and absent messaging becomes truthful.
- Grid top stack: zero reserve plus wrapped in-flow bands -> fixed one-line filter rail and overlay feedback -> gallery geometry remains stable.
- Derived Score: referential key-array reset -> semantic reset token -> ordinary filter responses cannot repaint or erase drafts.
- Bootstrap/responsive state: effect-restored truth -> synchronous initial snapshots -> no returning-user or mobile first-frame snap.

Review: These issues are highest priority because they are frequent, measured, and either move primary controls or present false semantics. They should be resolved before adding motion polish.

PHASE 2 — Refinement (stabilize controls and async card shells)

- Native selects: UA-owned popup surfaces -> app-owned Dropdown controls -> consistent dark rendering and opening behavior.
- Shared utility menus: remount from opacity zero -> stable measured popover shell without entrance fade -> frequent menus feel immediate.
- Metrics/Derived async content: empty/full and input/Dropdown swaps -> invariant card and control shells -> facet refresh does not change structure or focus.
- Similarity, Theme Settings, and zoom guidance: post-paint positioning/content -> prepared state, bounded bodies, and layout-timed positioning -> dialogs and menus stay anchored.
- Scroll containers and folders: threshold-dependent scrollbar/count geometry -> stable gutters and reserved count/loading columns -> content width stops changing after hydration.

Review: Phase 2 establishes reusable stable primitives after Phase 1 defines correct ownership. Doing it first would polish components while the underlying presented state still changes beneath them.

PHASE 3 — Polish (decoded media and low-frequency feedback)

- Compare/ranking/cold thumbnails: resource swaps without unified decoded identity -> target-bound decoded presentation -> media never blanks or appears under new labels.
- Toolbar/sync/context/ranking status: changing intrinsic text -> fixed status slots or overlays -> secondary feedback no longer moves controls.
- Lazy surfaces: immediate first-use fallback -> idle-prefetched chunk and delayed persistent skeleton -> fast module loads do not flash.
- Debounced search selection: delayed unrelated clearing -> one explicit settled policy -> selection changes feel causally connected.

Review: These are real but lower-frequency or more localized. They should reuse the presentation and feedback contracts established in the first two phases.

DESIGN_SYSTEM (.md) UPDATES REQUIRED:

- There is no current canonical design-system document. Create one before implementation rather than reviving an archived guide.
- Define a presentation-continuity rule: pending never renders as absent/empty/error, and fast pending states may remain visually silent for an approved delay.
- Define a geometry rule: transient information may replace reserved content or overlay it, but may not add normal-flow rows beside primary controls.
- Define a utility-popover motion rule: frequent menus do not animate from opacity zero; modal motion remains allowed and must honor reduced motion.
- Define stable slot contracts for filter rail height, toolbar count/status width, metrics card header/footer, preview/diagnostic regions, and persistent scrollbar gutters.
- Define a decoded-media identity rule tying displayed pixels, labels, and target path/pair together.
- Exact delays, heights, and widths require approval and live tuning before becoming tokens.

IMPLEMENTATION NOTES FOR BUILD AGENT:

- `CategoricalCard` / `MetricCategoryCard`: conditional Active row and Clear block -> remove redundant row; use existing filter chips and active button styling; retain only a fixed action slot if product review keeps local Clear.
- `MetricHistogramCard`: conditional second Cursor span -> one invariant footer slot or absolutely positioned SVG cursor label.
- `useAppDataScope` / `AppShell`: per-consumer pending fallbacks -> a canonical settled `presentedBrowseSnapshot` swapped atomically after target success/empty/failure.
- `useInspectorSingleMetadata`: context mismatch returns idle -> context mismatch with autoload returns target-owned pending; delayed loader; idle copy only when autoload is off.
- `GridTopStack`: hidden reserve height 0 and wrapped in-flow transient bands -> fixed filter rail plus non-layout-changing status/action feedback.
- `DerivedScoreCard`: reset dependency on fresh array identity -> reset dependency on semantic spec/schema identity.
- `usePersistedAppShellSettings` / `useMediaQuery`: effect-time initialization -> synchronous initial snapshot before first paint.
- Derived/Attributes native selects -> shared Dropdown with fixed trigger geometry.
- `.dropdown-panel`: unconditional `slideDown` opacity animation -> no opacity entrance for utility menus; keep modal/intentional disclosure motion separate.
- Persistent overflow panes -> `scrollbar-gutter: stable` where supported.
- Do not implement any item above until the user approves scope and the missing design-system contracts are written.
