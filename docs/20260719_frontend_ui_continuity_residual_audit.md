# Frontend UI Continuity Residual Audit

- **Date:** 2026-07-19
- **Audited revision:** `f4b9eae` (`fix: stabilize media and lazy presentation`)
- **Scope:** current `frontend/src/` and browser continuity gates after
  completion of `docs/20260718_frontend_ui_stability_execution_plan.md`
- **Status:** diagnosis only; no product fix is implemented by this audit

## Outcome

The remaining flashes are not primarily an 800-millisecond tuning problem.
They are presentation-identity gaps: a requested target replaces or clears the
currently presented content before the target has a complete settled payload or
decoded pixels. Several previous fixes reserve the outer rectangle or suppress
fallback text, but the values, rows, actions, transforms, or images inside that
rectangle still disappear for one or more painted frames.

One residual was an explicit limitation of the previous plan rather than
implementation drift. S3-T2 required a new uncached facet field to own a
loading shell immediately and prohibited cross-field previous data. That
prevented mislabeled stale data, but it also codified the reported
old-field -> loading-shell -> new-field flash. The revised design contract now
requires retaining the complete old identity, including its label, until the
new identity can be promoted atomically.

The central acceptance gap is:

```text
stable outer geometry != stable presentation

requested B
  -> old A content is cleared, hidden, dimmed, reset, or replaced by fallback
  -> B data or decoded pixels arrive
  -> B presentation appears
```

The required contract is complete A -> complete B. A frame may show one full
identity or the other, never a mixed label/content identity and never an
avoidable blank intermediate.

## Direct evidence

The existing probes pass while recording the reported failures.

- `python -m scripts.browser.gui_jitter.probe --scenario metrics` records
  `dataset_from` -> `Population: — / Loading values for this field…` ->
  `review_group`, with zero rectangle movement and zero violations.
- `python -m scripts.browser.gui_jitter.probe --scenario inspector` records a
  target-pending Quick View with zero real rows and three placeholder rows. Its
  first slow Metadata frame contains only `Metadata / Show PIL info`; the copy
  action and metadata values return later. The selection trace still reports
  zero anchor movement and zero violations.
- The Inspector trace observes `.inspector-preview-card`, not the child `<img>`,
  its decode state, or its pixels. An empty preview card therefore passes.
- The Viewer probe validates readiness only for images that are visible. A
  frame with no visible image is not rejected, so the network-ready ->
  decode-pending blank interval passes.

## Root mechanisms

1. **Requested state is also rendered state.** Selectors, paths, labels, and
   shells switch to target B immediately even when B has no settled data.
2. **Passive effects discover first-frame requirements.** Child panels register
   facet fields, restore persisted UI, reset target drafts, or notify parents
   only after React has committed the incomplete frame.
3. **Visibility is treated as lifecycle.** Tab and rail conditionals unmount
   controllers, destroying drafts, selection, expansion, scroll, and query
   registration.
4. **Strong stale-response guards clear presentation.** Request correctness is
   preserved, but prior content is replaced with blanks or skeletons instead of
   retaining one complete presented identity.
5. **Network readiness is confused with display readiness.** Several media
   surfaces bind a new URL before `HTMLImageElement.decode()` succeeds.
6. **Tests prove rectangles and final state.** Descendant visibility, row/value
   identity, transforms, image readiness, and pixels are mostly outside the
   frame oracle.

## Confirmed findings

Priority reflects frequency and perceptual impact, not implementation size.

### P0 — Direct, frequent continuity failures

| ID | Surface and transition | Current owner and cause | Eventual contract |
| --- | --- | --- | --- |
| RC-01 | Uncached Metric/Categorical selection: settled field -> `Loading values…` -> target field | `features/metrics/components/CategoricalPanel.tsx:47-55,86-123` and `MetricRangePanel.tsx:64-69,109-175` commit selection before passive field registration. `model/facetPresentation.ts:11-19` maps an unregistered field to pending. | Retain selector label and card data as one inert settled identity; promote target label and data together. |
| RC-02 | Folders -> Metrics: empty field batch -> pending cards -> settled cards | `app/components/LeftSidebar.tsx:244-330` unmounts panels. `MetricsPanel.tsx:57-64` remounts with empty keys; child panels and parent synchronize requirements through chained passive effects. | Active field requirements and cached presentation exist before the first visible Metrics frame. |
| RC-03 | Tab, panel hide/show, or responsive suppression loses tree state, metric/categorical choice, unsaved Derived draft, and Inspector-local presentation | `LeftSidebar.tsx:244-330` destroys tool controllers; `AppShell.tsx:1427+,1590+` conditionally mounts the left rail and Inspector; Derived editor state is local at `DerivedScoreCard.tsx:72-121`. | Tabs, panel collapse, and responsive visibility change presentation, not lifecycle; preserve draft, selection, expansion, scroll, query registration, and last-settled presentation until explicit reset or hard scope change. |
| RC-04 | Cold Inspector selection: Metadata, Quick View, PIL/Copy actions, Basics metric labels/values, and table rows disappear before the target populates | `useInspectorSingleMetadata.ts:82-100` clears metadata; `Inspector.tsx:304-434,465-503` filters old detail and swaps Quick View rows for reservations; `api/items.ts:399-407` has no target placeholder; `BasicsSection.tsx:180-306` conditionally removes full-detail regions. | Present one complete Inspector identity. Retain old filename, values, actions, rows, and target-bound state together until the target's required bundle is ready. |
| RC-05 | Inspector Notes/Tags: old values -> blank editable fields -> target values | `useInspectorSidecarWorkflow.ts:59-66,89-105,203-205` returns empty strings while its path-tagged draft is repaired in an effect; even cached sidecar data can paint the blank frame. | Never use empty editable values as a transient path guard; project a complete cached target or retain the complete prior Inspector presentation. |
| RC-06 | Inspector thumbnail: image A -> empty preview card -> image B; a failed target can remain blank indefinitely | `Inspector.tsx:78-82,725-739` keys the preview by path and returns `null` until `useBlobUrl`; `shared/hooks/useBlobUrl.ts:102-142` starts at `null`, fetches in an effect, exposes the URL without a decode gate, and ignores fetch errors. | Bind filename/ext and decoded thumbnail to one presented identity; atomically replace decoded A with decoded B, or retire A into a bounded target-specific error/retry state. |
| RC-07 | Viewer navigation: decoded A -> no visible image during B decode -> B fade-in | `Viewer.tsx:100-107,168-178,202-247,310-329` promotes B at blob-URL readiness, removes A, hides B until `onLoad`, then fades it. It never awaits `decode()`. | Keep decoded A fully visible until latest B decodes; atomically promote B and retire A. |
| RC-08 | Folder navigation briefly exposes no metric/categorical schema and may fall back to a raw sort key | `app/hooks/useAppDataScope.ts:340-342,395-397,454-465` returns empty capability keys until a path-change effect. `MetricsPanel.tsx:91-100` renders terminal `No metrics…`; Toolbar options temporarily vanish. | Capability/schema identity commits with the target scope; pending is not an empty schema. |
| RC-27 | Folder/hash/Smart Folder navigation can paint the new scope with the old selection, Inspector, and Compare eligibility | `AppShell.tsx:1197-1202` changes `current` synchronously, but scope cleanup is a passive effect at `1223-1240`; `useAppSelectionViewerCompare.ts:297-316` therefore resets path-owned state after the first target-scope commit. | A scope boundary clears or explicitly preserves all path-owned presentation before the first target-scope frame; explicit image-hash restoration is the documented exception. |

### P1 — Confirmed systemic or adjacent failures

| ID | Surface and transition | Current owner and cause | Eventual contract |
| --- | --- | --- | --- |
| RC-09 | Retained gallery keeps old items during the 800ms grace, but the metric rail immediately reshapes to a loaded-window histogram | `AppShell.tsx:1563-1585` drops the snapshot histogram override on target-key mismatch; `MetricScrollbar.tsx:39-55,86-115` recomputes from retained window items. Current grid evidence checks rail presence/width, not bins/domain. | The retained browse snapshot owns histogram, domain, and quantiles until atomic target commit. |
| RC-10 | First lazy Inspector mount reorders/collapses/expands sections and can overwrite stored defaults after paint | `useInspectorUiState.ts:116-131,217-293` initializes defaults, restores persisted presentation in effects, and has adjacent persistence effects. `useInspectorCompareExport.ts:73-94` does the same for export settings. | Read all first-visible persisted state in lazy initializers and suppress persistence until hydration is complete. |
| RC-11 | First/no-Quick-View item -> metadata-rich item inserts the entire Quick View section after load | `Inspector.tsx:349-434` reserves only when the previous item had rows; `inspectorWidgets.tsx:30-35` then inserts the section when metadata resolves. | Reserve the possible target-owned region from the first pending frame, or retain the whole prior Inspector identity until target promotion. |
| RC-12 | Compare Metadata autoactivates one frame late; context/reload collapses a settled matrix to one loading line, then expands it | `useInspectorUiState.ts:295-315` autoactivates in an effect. `useInspectorCompareMetadata.ts:44-98` sets loading immediately; `CompareMetadataSection.tsx:305-389` gates away the matrix and changes action labels without a stable status region. | Project compare context synchronously; retain settled matrix during refresh and atomically promote the next matrix. |
| RC-13 | Derived numeric term shows partial/wrong histogram or terminal-looking `No finite values` before authoritative population facets | `DerivedScoreCard.tsx:158-179,395-401,661-687` registers fields passively and falls back to incomplete local items without pending ownership; `DerivedMetricMiniHistogram.tsx:11-24` labels `null` as final empty. | Key mini-histograms to field/query ownership; incomplete population is pending, never empty. |
| RC-14 | Smart Folders first paints `No saved Smart Folders yet.` before views load, then an unbounded button list moves FolderTree down | `useSmartFolders.ts:41-58` initializes `[]` and fetches in an effect; `LeftSidebar.tsx:249-278` treats it as terminal empty and gives the hydrated list no stable bound. | Distinguish pending from settled empty; retain cached views or use a delayed, bounded region with internal overflow. |
| RC-15 | Deep-linked folder/image startup paints Root before the hash target | `AppShell.tsx:288` initializes `/`; `useAppHashRouting.ts:21-44` applies the hash after first paint. | Resolve boot routing before presenting the app target, or retain the boot shell until route identity is known. |
| RC-16 | Hover preview paints a large spinner/blank/progressive surface before decoded target pixels | `VirtualGrid.tsx:335-368,813-849` uses a 350ms hover-intent delay, then reveals the portal before proxy fetch/decode; direct URLs are also not decode-gated. | Hover intent decides whether to request, not whether pending UI must paint; reveal decoded target pixels atomically. |
| RC-17 | Compare target navigation resets zoom/pan on the retained old pair | `CompareViewer.tsx:169-177,383-431,533-610` resets target view while the old presented pair remains; `useCompareZoomPan.ts:257-272` refits it. | Transform belongs to the presented pair; retain it with A and initialize B's transform at promotion. |
| RC-18 | Ranking fullscreen target navigation resets the retained old image transform | `useRankingFullscreen.ts:100-112` resets immediately while `RankingApp.tsx:321-348,612-662` retains old decoded pixels. | Transform and pixels promote as one fullscreen identity. |
| RC-19 | First-open Compare/ranking fullscreen has a blank stage before any decoded presentation | `CompareViewer.tsx:529-533,622-630` and `RankingApp.tsx:318-348,612-663` mount the overlay before an initial decoded resource exists. Existing pixel traces begin after initial presentation. | Keep underlying context or a stable delayed first-load shell until initial decoded content exists. |
| RC-20 | Ranking board changes target labels while bare lazy images independently pop/progressively decode; failed cards have no explicit terminal state | `RankingApp.tsx:111-150,432-453`; `useRankingSession.ts:103-111` preloads network bytes but not decoded pixels. The card image has no `onError`. | Decode visible cards before reveal, bind card label/pixels to one target instance, and keep a stable per-card error state. |
| RC-21 | External filter/smart-view changes paint stale Attributes values and histogram Min/Max for one frame | `AttributesPanel.tsx:56-65,367-386` and `MetricHistogramCard.tsx:75-100,213-255` mirror props into local state in passive effects. | Outside an active edit, derive display values synchronously from the owning filter identity; keep edit drafts separately. |
| RC-22 | Filtered-count columns/prefixes disappear after cold load or after the 800ms grace, then return | Conditional content at `MetricHistogramCard.tsx:148-152`, `MetricCategoryCard.tsx:47-63,84-89`, and `CategoricalCard.tsx:51-67,87-92` removes count roles when incomplete. | Reserve count roles; use a dash or inert presented count rather than removing the column/prefix. |
| RC-23 | Folder count can paint direct/page count before recursive total | `FolderTree.tsx:273-275,306-320` publishes `items.length`, then replaces it with async recursive count. The fixed slot prevents geometry movement but not semantic flicker. | Show only authoritative recursive truth, a retained value, or neutral pending content. |
| RC-24 | Inspector copy feedback can leak to the next path/compare context for one frame | `useInspectorUiState.ts:129-136,181-215,317-324` clears feedback passively and omits one copied field; Metadata/Compare toasts are not fully context-keyed. | Key transient feedback to the complete target identity and project it synchronously. |
| RC-25 | Basics/Export/Conflict/filename content still inserts, removes, or wraps normal-flow regions asynchronously | `BasicsSection.tsx:127-178,223-306`, `SelectionExportSection.tsx:122-148`, and `Inspector.tsx:734-739` conditionally add helper/error/detail regions; filename has no bounded slot. | Reserve bounded status/detail regions and clamp filename with accessible full text. |
| RC-26 | Per-row selected-count prefixes shift value/count text horizontally | `CategoricalCard.tsx:87-92` and `MetricCategoryCard.tsx:84-89` insert `N sel ·` into an auto-width suffix. | Reserve a fixed selected-count subcolumn or communicate selection without changing row text width. |
| RC-28 | Deep image links outside the loaded browse window open a Viewer but cannot establish grid navigation/back context | `useAppSelectionViewerCompare.ts:318-329,401-404` adopts navigation paths only when the target is already in `itemPaths`; there is no path-centered page fetch. Close/back cannot focus or scroll to an absent cell. | A valid image deep link establishes a path-containing browse window and restores a visible selected cell without a top jump. |
| RC-29 | Nested-folder toolbar count commits scope total, then adds root total when a secondary query arrives | `useAppDataScope.ts:395,565-567` temporarily substitutes nested `scopeTotal` for `rootTotal`; `AppShell.tsx:518-534` and `Toolbar.tsx:292,671-677` therefore paint `100 items` -> `100 / 10,000 items`. | Include every visible secondary count dependency in the presented count bundle, or retain the last authoritative root total. |
| RC-30 | New metric-sorted grid can commit before its independent metric-rail facet query | `AppShell.tsx:589-638` computes `targetMetricRailReady` but calls `useGridPresentation` with browse settlement alone; `1571-1588` then paints placeholder -> rail on paginated/derived cases. | Required grid and rail readiness participate in one atomic promotion gate. |

### P2 — Confirmed but lower-frequency, intentional, or evidence-gated

- Viewer still uses a 150ms spinner delay (`Viewer.tsx:14,202-220,290-297`),
  and its existing probe codifies that old value. This conflicts with the newer
  silent-fast-transition direction, but fixing the decode gap in RC-07 matters
  more than changing the timer.
- Cold FolderTree expansion inserts a 40px `Loading folders…` row immediately
  (`FolderTree.tsx:266-297,385-392`). Expansion geometry is user-owned and may
  be intentional; only the eager sub-threshold fallback needs evaluation.
- Cold grid ThumbCards decode-gate identity but fade from opacity zero over
  160ms (`ThumbCard.tsx:138-150`). This can create cohort shimmer and should be
  measured with reduced-motion enabled before changing it.
- Theme Settings may grow/reclamp when source/session data arrives while open,
  and SyncIndicator grows with live activity. These are low-frequency live
  state changes; keep them evidence-gated.
- Similarity first-open capability details, browser-zoom warnings, and health
  status can populate after paint (`SimilarityModal.tsx:23,52-56,177-200`,
  `useBrowserZoomWarning.ts:26-49`, and `useAppHealthPolling.ts`). Their outer
  rails are stable, so treat these as P2 content-pop until painted evidence
  shows meaningful fatigue.
- Dropdown opens before its passive effect selects the highlighted option
  (`shared/ui/Dropdown.tsx:221-238`), producing a subtle second-frame highlight
  change that current opacity/transform checks do not observe.
- Several action-owned buttons change to shorter busy copy without a reserved
  inline footprint: Compare Export, Similarity `Find similar`, and Compare
  Metadata `Reload`. These are lower priority than navigation continuity, but
  mutable action copy should reserve its maximum supported width.
- Compare retains a presented pair/count while Prev/Next disabled state follows
  the requested target (`CompareViewer.tsx:169-196,490-505`). This can mix
  visible navigation semantics at boundaries; keep it evidence-gated unless the
  controls are moved onto presented identity as part of RC-17.
- `VirtualFieldList` may briefly expose an empty measured viewport on first
  `Show all`; narrow Compare/Export headers may wrap as action labels change;
  histogram Cursor may survive one field-domain frame. These are plausible
  code paths but require an earliest-frame browser reproduction before a
  ticket.

## Timing assessment

Changing the 800ms or 1,000ms values will not fix the reported four residuals.

| Timing owner | What it currently controls | What it does not control |
| --- | --- | --- |
| Browse 800ms grace | How long settled browse membership is retained before target loading | Facet field registration, tab remount, Inspector data, or thumbnail decode |
| Metadata 1,000ms | When `Loading metadata…` copy becomes visible | Immediate clearing of metadata values, rows, and action visibility |
| Viewer 150ms | Spinner visibility | The blank interval created when a URL is promoted before decode |
| Hover 350ms | Hover intent before opening preview | Decode readiness or fallback-copy suppression |
| ThumbCard 160ms | Opacity fade after decode | Query or target identity |

Timers should delay status copy only. They are not a presentation-retention
mechanism.

## Verification gaps to close with any future fix

1. `scripts/browser/gui_jitter/painted_frames.py` records only the selected
   node's rectangle, aggregate text, value, visibility, and limited ARIA state.
   It does not inspect descendant computed visibility, row identity, individual
   actions/values, image readiness, transform, or pixels.
2. The metrics probe explicitly waits for and accepts a pending field shell.
   It must fail if `Loading values…` paints between settled A and settled B for
   a compatible switch.
3. `useGridPresentation.test.ts:107-128` explicitly expects the 800ms threshold
   to retire retained membership into an empty loading snapshot. Under the
   revised contract, the threshold may reveal reserved status but may not clear
   a valid settled presentation; this expectation must be inverted.
4. The Inspector trace selects outer section/card nodes. It must record real
   row IDs and values, placeholder count, action computed visibility, filename,
   preview `currentSrc/complete/naturalWidth/opacity`, and distinct pixels.
5. Inspector stale-text sentinels currently treat any prior content after a
   click as failure. The oracle must distinguish requested identity from the
   deliberately retained complete presented identity, and reject only mixed
   labels/content or superseded promotion.
6. Viewer evidence must reject a frame with zero visible decoded images; Compare
   and ranking evidence must include first-open and transform continuity.
7. `gui_smoke` remains an end-state gate. It cannot replace painted-frame
   coverage for cold A-to-unvisited-B, warm revisit, rapid A-to-B-to-C, tab
   return, fast/slow success, and terminal empty/error.

## Engineering references

- React documents that an Effect-triggered parent notification runs after the
  child has already updated the screen and causes another render pass:
  <https://react.dev/learn/you-might-not-need-an-effect#notifying-parent-components-about-state-changes>.
- TanStack Query documents `placeholderData`/`keepPreviousData` specifically to
  avoid jumping between success and pending when a query key changes:
  <https://tanstack.com/query/latest/docs/framework/react/guides/paginated-queries>.
  Lenslet must retain the matching label/identity with previous data rather
  than showing old data under the new label.
- React's `useDeferredValue` can retain stale content, but its data-loading
  example assumes a Suspense-enabled source. Lenslet's current facet and
  Inspector hooks do not suspend, so it is not a drop-in fix:
  <https://react.dev/reference/react/useDeferredValue>.
- Prefetching on hover/focus or likely navigation can reduce cold frequency but
  does not replace a correct miss path:
  <https://tanstack.com/query/latest/docs/framework/react/guides/prefetching>.
- The HTML Standard defines `decode()` so decoded data can be made available
  before insertion/paint, avoiding decode-stage dropped frames:
  <https://html.spec.whatwg.org/multipage/embedded-content.html#dom-img-decode-dev>.

## Explicit non-findings and boundaries

- Single-image Metadata does not leak an old payload under a new target; its
  request/context guards are correct. The problem is that correctness is
  achieved by clearing presentation.
- Quick-to-quick and quick-to-plain Quick View geometry is reserved and covered;
  RC-11 is specifically first/no-prior-rows -> quick.
- Metric card outer geometry, header selected slots, Clear actions, histogram
  cursor footer, Metadata action width, PIL slot, and Derived `Missing` Dropdown
  are already stable.
- Shared Dropdown/DropdownMenu, ToolbarFilterMenu, ContextMenu, Theme Settings,
  persisted main-shell settings, viewport/media-query initialization, toolbar
  slots, FolderTree action/count slots, fixed top rail, and persistent
  scrollbar gutters have the intended first-frame geometry. Do not reopen them
  without new painted evidence.
- Source, table, workspace, and session changes are hard-reset boundaries.
- Folder expansion, pull-to-refresh movement, and explicit user disclosure
  motion are user-owned interactions, not automatically continuity defects.
- First-ever app content has no prior settled snapshot and may use a delayed
  neutral stable shell. Empty/error presentation is valid only after the active
  target terminally settles.

## Design-system consequence

`docs/DESIGN_SYSTEM.md` now makes requested and presented identity a general
rule, states that timers delay copy rather than clear content, preserves tool
state across visibility changes, binds transforms to media identity, and makes
descendant content plus decoded pixels part of painted-frame acceptance.
