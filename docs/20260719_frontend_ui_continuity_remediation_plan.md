# Lenslet Frontend UI Continuity Remediation Plan


## Outcome + Scope Lock


After this plan, compatible asynchronous navigation presents one complete settled identity and then atomically promotes the next. Metric and Categorical fields no longer pass through a loading card, Folders-to-Metrics no longer discovers its query after paint, Inspector values/actions/thumbnail move directly from image A to image B, and Viewer, hover preview, Compare, and ranking never expose an avoidable blank or undecoded frame. The 800-millisecond and 1,000-millisecond tokens delay reserved status copy only; they never clear a valid settled presentation.

This plan implements every confirmed `RC-01` through `RC-30` finding in `docs/20260719_frontend_ui_continuity_residual_audit.md` under the canonical rules in `docs/DESIGN_SYSTEM.md`. It supersedes the conflicting parts of `docs/20260718_frontend_ui_stability_execution_plan.md`, especially the requirement that an uncached field immediately show a loading shell and the test that retires retained browse membership after 800 milliseconds. Previously stable geometry, controls, overall-population histogram semantics, hard-reset boundaries, and non-findings remain closed.

The user approved the confirmed remediation program and Ralph execution. Pre-approved behavior changes are: retain complete prior content while a compatible target is pending; make retained controls inert and busy where acting would be unsafe; reveal reserved neutral status only after the documented delay; preserve drafts, field selection, expansion, scroll, and cached presentation across tabs/panel visibility/responsive suppression; decode media before promotion; atomically bind labels, rows, actions, counts, pixels, opacity, and transforms; show target-owned terminal empty/error/retry only after settlement; resolve initial hashes before first app presentation; and, specifically for `RC-28`, add one optional `anchor_path` field to the existing `POST /folders/query` request when current browse-window primitives cannot restore a valid off-page target.

Further sign-off is required for a new runtime dependency, a new standalone backend endpoint, any public request/response change other than the approved optional `anchor_path`, storage schema changes, a new visible timing value, changed filter/metric semantics, editable retained stale content, an app-wide state or Suspense framework, unbounded media preloading, or behavior code for the audit's unconfirmed/intentional P2 tail.

Out of scope are FolderTree's user-owned expansion geometry and pull-to-refresh motion; live Theme/Sync growth without new failing evidence; the Viewer first-ever 150-millisecond loader timing, cold ThumbCard fade, Similarity/zoom/health content pop, Dropdown second-frame highlight, VirtualFieldList first measurement, and cursor-tail candidates unless a scoped ticket reproduces them as part of its primary path; visual restyling; compatibility layers; filtered-out deep-link/filter-reset policy; and unrelated cleanup. Compare navigation-control identity and mutable busy-label widths may be corrected only while their owning confirmed ticket already touches that surface.


## Context


The implementation baseline is HEAD `72154e7`; source behavior was last changed at `f4b9eae`, and `72154e7` committed the current `AGENTS.md`, `docs/DESIGN_SYSTEM.md`, and residual audit. Existing browser probes pass while recording the failures because they primarily assert outer rectangles and settled end state. The metrics trace accepts `old field -> Loading values -> target field`; the Inspector trace accepts placeholder rows, invisible actions, and an empty preview card; the Viewer probe does not fail a frame with zero visible images.

The rendering work is latency-sensitive, correctness-critical, and at high risk of ornamental state architecture. The core invariants are: a frame is complete presented A or complete presented B; requested and presented identity are separate; terminal empty/error belongs only to the latest target; retained actions cannot mutate A under a requested B; target data and decoded pixels promote atomically; media resources and transforms have bounded, explicit ownership; source/table/workspace/session resets retain nothing incompatible; and browser evidence inspects descendants and pixels, not only boxes.

Three audit agents mapped the current owners across metrics, Inspector, browse/scope, Viewer, Compare, ranking, routing, and the painted-frame gates. No `PLANS.md` exists; this document follows the Plan Writer execution format and is the implementation source of truth. The plan deliberately uses focused domain owners instead of one global presentation store.


## Interfaces and Dependencies


No new package is planned. Reuse TanStack Query, the existing browse presentation owner, query caches, media resource state, thumbnail cache, and browser harnesses.

Metrics may add one focused requested/presented field projection owned by the existing panels. Inspector may add one focused presented snapshot keyed by path that combines the already-requested item detail, sidecar, metadata, and derived Quick View rows; it is not a general store. Browse evolves the existing presented snapshot so its membership, authoritative counts, histogram/domain/quantiles, and required metric-rail readiness promote together. Media surfaces reuse or minimally extend existing decoded-resource primitives with latest-target guards and bounded URL retirement.

Deep image restoration must first reuse the existing folder-query/window and entity-store paths. If that cannot produce a window containing the requested path, the approved optional `anchor_path` extends the existing `BrowseQueryRequest` for `POST /folders/query`; no new endpoint is added. It affects only the initial window, and the response `offset` reports the effective centered/clamped offset. The anchor participates in window/request tokens but not the analysis/facet key. Superseding and fetch-next requests do not re-anchor. Both generic `evaluate_browse_records` and TableStorage `query_scope_from_analysis` must produce identical ordering/window semantics. A valid in-scope target that survives the active analysis is centered; missing, out-of-scope, or filtered-out targets produce the ordinary requested window without synthetic membership, and the frontend settles the hash target as unavailable. The plan does not reset filters to recover an excluded hash target.


## Plan of Work


### Sprint Plan


1. **Sprint 1 — Make field and tool transitions complete on their first visible frame.** Demo: cold Categorical/Metric selection is complete A -> complete B, Folders -> Metrics has its query on frame one, and tabs/collapse/responsive return preserve tool state.

   1. **S1-T1 — Turn the metrics trace into a content-continuity oracle.** Coverage: `RC-01`, `RC-02`, and left-tool `RC-03`; root closure is in S1-T2 through S1-T4. Owners: `scripts/browser/gui_jitter/{painted_frames,metrics}.py` and their focused tests. Record selector/card identity, individual values/actions/placeholders, computed descendant visibility, and the earliest post-action frame while preserving geometry assertions. Add failing baselines for uncached field selection, Folders -> Metrics, Metrics -> Derived -> Metrics, panel collapse/reopen, and rapid A-to-B-to-C before product edits.

   2. **S1-T2 — Give Metric and Categorical fields atomic requested/presented ownership.** Closes `RC-01`. Owners: `CategoricalPanel.tsx`, `MetricRangePanel.tsx`, `CategoricalCard.tsx`, histogram/category cards, and `facetPresentation.ts`. Begin with the failing S1-T1 field trace. Retain field label, selector value, card data, filter controls, and actions as one inert presented identity until the latest requested field settles; promote success/empty/error atomically without cross-label stale data. Pass the browse presentation reset identity into this owner so an incompatible source/table/workspace/session boundary clears retention synchronously. Preserve filter-free population histogram shape. Validation: focused panel/model tests, a hard-reset case, and cold/warm/A-to-B-to-C traces show complete A or B only.

   3. **S1-T3 — Make active facet requirements available before the Metrics frame.** Closes `RC-02`. Owners: `MetricsPanel.tsx`, `CategoricalPanel.tsx`, `MetricRangePanel.tsx`, `AppShell.tsx`, and `useAppDataScope` query ownership. Begin with the failing Folders -> Metrics trace. Move durable active-field ownership above remount/effect timing, remove chained child-to-parent discovery, and keep hidden panels from unnecessary polling. Validation: the first visible Metrics frame has the correct cached/requested batches and never publishes an empty intermediate field set.

   4. **S1-T4 — Preserve left-tool state across visibility changes.** Closes the left-tool portion of `RC-03`. Owners: `LeftSidebar.tsx`, `FolderTree.tsx`, `MetricsPanel.tsx`, `DerivedScorePanel`/`DerivedScoreCard.tsx`, and the smallest necessary AppShell state owner. Begin with failing tab/collapse/responsive traces. Preserve FolderTree expansion/scroll, Metrics selection/show-all, Derived drafts, and last-settled presentation while keeping hidden content inert and inaccessible. Disable hidden FolderTree observers/recursive-count work without clearing their state, and close body-portaled tool popups plus hidden focus before paint. Validation: repeated tab, content-collapse, left-panel hide/show, responsive suppression, Show-all-active, portal-open, and hidden-request-counter cycles retain state with no hidden focus target or background polling regression.

2. **Sprint 2 — Make Derived, filters, counts, and the metric rail truthful and atomic.** Demo: no partial/false-empty Derived plot, stale filter input, disappearing count role, retained-rail reshape, or placeholder-to-rail promotion remains.

   1. **S2-T1 — Bind Derived inputs to authoritative field state.** Closes `RC-13`. Owners: `DerivedScoreCard.tsx`, `DerivedMetricMiniHistogram.tsx`, and existing facet presentation/query state. Begin with failing delayed numeric/categorical traces. Distinguish pending, settled empty, error, and ready; incomplete loaded windows cannot become population truth. Preserve freeform categorical entry and unsaved formula/name/weight/missing drafts. Validation: focused Derived tests and delayed success/empty/error traces never paint `No finite values` for pending data.

   2. **S2-T2 — Remove effect-late controlled filter mirrors.** Closes `RC-21`. Owners: `AttributesPanel.tsx`, `MetricHistogramCard.tsx`, and focused input tests. Begin with failing external-update frames. Separate active edit drafts from synchronously projected filter identity for operators/text and histogram Min/Max. External Clear all, Smart Folder activation, and view restore commit visible state in one frame without overwriting an active edit. Validation: external update, typing/debounce, blur, and clear tests plus painted values pass.

   3. **S2-T3 — Keep metric row/header roles invariant.** Closes `RC-22` and `RC-26`. Owners: `MetricHistogramCard.tsx`, `MetricCategoryCard.tsx`, `CategoricalCard.tsx`, and metrics evidence. Begin with failing row-position/count-role frames. Reserve filtered/population and per-row selected-count roles through incomplete states; use target-correct neutral or inert presented values instead of removing prefixes/columns. Validation: individual suffix positions and header roles stay invariant through selection, clear, slow filtering, and settlement with accessible full text.

   4. **S2-T4 — Complete the presented browse/metric-rail bundle.** Closes `RC-09` and `RC-30`. Owners: `useGridPresentation`, `AppShell.tsx`, `MetricScrollbar.tsx`, presentation tests, and the grid/metrics trace. Begin with failing over-800ms and delayed derived-rail cases. Add an explicit table-backed `table-1585` browser fixture profile so this path exercises a paginated dataset larger than 1,000 rows. Invert the stale 800-millisecond unit contract; retain authoritative membership, histogram/domain/quantiles, and require independent rail readiness before metric-sorted grid promotion. Remove loaded-window fallback reshaping. Validation: sub/over-800ms, A-to-B-to-C, terminal outcomes, full-population histogram, and the paginated 1,585-row profile pass.

3. **Sprint 3 — Present the entire Inspector, including its preview, as one identity.** Demo: selecting an unvisited image moves directly from complete Inspector A to complete Inspector B, and reopening restores the same layout on its first frame.

   1. **S3-T1 — Upgrade Inspector evidence from section boxes to content and pixels.** Coverage: Inspector `RC-03`, `RC-04`, `RC-05`, `RC-06`, `RC-10`, `RC-11`, `RC-24`, and `RC-25`; root closure is in S3-T2 through S3-T5. Owners: `scripts/browser/gui_jitter/{inspector,painted_frames}.py`, distinct image fixtures, and focused helper tests. Record requested/presented path, filename, preview `currentSrc`/readiness/opacity/RGB, real/placeholder row IDs and values, metric keys, Notes/Tags, action visibility, copied context, and section state. Rewrite stale sentinels to allow complete retained A while rejecting mixed A/B. Add failing cold/warm/rapid/slow/error/reopen/responsive traces before product edits.

   2. **S3-T2 — Define one focused Inspector bundle and settlement model.** Establishes the ownership model for `RC-04`, `RC-05`, `RC-06`, and `RC-11`; live closure occurs in S3-T4. Owners: `Inspector.tsx`, `useInspectorSingleMetadata`, `useInspectorSidecarWorkflow`, item-detail/sidecar query hooks, and one focused Inspector presentation model/hook. This is model-only: it does not switch the rendered Inspector away from the existing complete A. Start detail, sidecar, metadata, and decoded-preview candidate work in parallel. Autoload-off metadata is settled idle. An individual dependency failure prepares coherent target B with a bounded target-owned error region; it cannot wait forever or fail the whole Inspector. Retained edit actions are inert, hard resets clear, and latest-target success/error alone becomes promotable. Validation: pure race/settlement tests cover A-to-B-to-C, cache hits, each individual failure, autoload off, preview readiness, and scope reset.

   3. **S3-T3 — Integrate a decoded Inspector preview candidate without visible promotion.** Prepares the media root for `RC-06`; live closure occurs in S3-T4. Owners: `InspectorPreviewImage`, `useBlobUrl` or the existing bounded thumbnail resource/cache, the S3 bundle, and preview evidence. Begin with the failing pixel trace from S3-T1. Fetch and decode the latest preview candidate with latest-target and URL-retirement guards, but keep rendering complete Inspector A until the entire B bundle is promotable. A corrupt target prepares a bounded target-specific error/retry state rather than a blank. Validation: resource/model tests prove cold/warm/A-to-B-to-C/corrupt candidates never alter the live A presentation before bundle promotion.

   4. **S3-T4 — Hard-cut fields, rows, actions, feedback, and decoded preview to the bundle.** Closes `RC-04`, `RC-05`, `RC-06`, `RC-11`, and `RC-24`. Owners: `Inspector.tsx`, Metadata/Basics/Notes/QuickView sections, `InspectorPreviewImage`, sidecar draft logic, and the S3 bundle. Begin with failing content and pixel traces. Perform the single live render cut only after S3-T2 and S3-T3: remove mismatch empty strings, settled-row skeleton replacement, keyed blank preview handoff, effect-time clearing, and unkeyed feedback; promote filename/ext, rows, actions, values, and decoded pixels as one identity. Define the dirty-edit race: typing Notes/Tags on A then selecting B commits to A exactly once or preserves an A-keyed draft, never writes B. Validation: no blank field, missing action, placeholder-for-settled-row, mixed filename/value/pixels, stale copy feedback, cross-path edit, or undecoded target appears.

   5. **S3-T5 — Initialize Inspector lifecycle and bound secondary regions before paint.** Closes the Inspector portion of `RC-03`, `RC-10`, and `RC-25`. Owners: `useInspectorUiState`, `useInspectorCompareExport`, `Inspector.tsx`, Basics/SelectionExport/conflict regions, and panel mounting. Begin with failing cold-mount/reopen/narrow traces. Read persisted state synchronously, suppress writes until hydrated, preserve state across close/responsive suppression, clamp filename with accessible full text, and reserve bounded meaningful error/action regions. Validation: first-frame state and twenty reopen cycles are identical, storage is not overwritten, hidden content is inert, and primary section anchors stay stable.

4. **Sprint 4 — Make Viewer and hover preview decode-atomic.** Demo: both surfaces show decoded A or decoded B, never an empty/progressive frame.

   1. **S4-T1 — Replace Viewer URL-ready promotion with decoded promotion.** Closes `RC-07`. Owners: `Viewer.tsx`, existing media-resource state, Viewer tests, and `viewer_probe`. First make a frame with zero visible decoded images or mixed label/pixels/transform fail. Keep prior decoded media, full opacity, label, and transform until latest target decode; atomically retire URLs and preserve error/back/navigation. Do not change the separate first-ever 150-millisecond loader timing. Validation: cold/warm/back/A-to-B-to-C/corrupt/reduced-motion cases reject blank, stale promotion, transform reset, and leaks.

   2. **S4-T2 — Reveal hover preview only with decoded target pixels.** Closes `RC-16`. Owners: `VirtualGrid.tsx`, the smallest existing decoded resource path, grid evidence, and cancellation tests. First fail spinner/blank/progressive first-visible frames. Keep the 350-millisecond hover-intent decision separate from readiness; handle direct/proxy sources, cancellation, latest target, and terminal failure without a new media store. Validation: enter/leave/A-to-B/error/reduced-motion traces show decoded target pixels on the first visible portal frame and no orphan panel/request.

5. **Sprint 5 — Make scope, routing, Smart Folders, and counts first-frame correct.** Demo: folder/hash/Smart Folder navigation never shows Root, stale selection, false-empty schema, provisional counts, or an off-page restoration gap.

   1. **S5-T1 — Preserve capability identity through scope changes.** Closes `RC-08`. Owners: `useAppDataScope`, `MetricsPanel.tsx`, Toolbar sort options, and capability tests. Begin with a failing delayed `/folder-fields` scope trace. Model pending/ready-empty/ready-populated and never render pending as `No metrics…` or drop the friendly sort label. Validation: active Metrics/Derived folder and Smart Folder switches stay coherent through success/empty/error.

   2. **S5-T2 — Commit scope-boundary selection before target paint.** Closes `RC-27`. Owners: `AppShell.tsx`, `useAppSelectionViewerCompare`, folder/Smart Folder navigation hooks, and grid evidence. Begin with a failing new-scope/old-selection frame. Clear or explicitly preserve selection, Inspector, and Compare eligibility before the first target-scope commit, with valid image-hash restoration as the exception. Validation: folder/hash/Smart Folder A-to-B-to-C and hard resets never mix target scope with old path-owned presentation.

   3. **S5-T3 — Add identical optional anchor semantics to the existing browse query paths.** Closes the backend/window root of `RC-28`. Owners: frontend `lib/types.ts`, `api/folders.ts`, client/query keys; backend `web/models.py`, `web/routes/folders.py`, `browse/query.py`, `web/browse.py`, `storage/table/query_execution.py`; and generic/route/TableStorage tests. Start with parity tests that fail for an off-page valid target near the middle of 1,585 rows. Implement the approved `anchor_path` semantics from Interfaces and Dependencies identically in generic and table engines; fetch-next/superseding requests do not re-anchor. Validation: effective offset, ordering, tokens, valid/missing/out-of-scope/filtered target behavior, and engine parity pass.

   4. **S5-T4 — Resolve initial hashes and restore the anchored frontend window.** Closes `RC-15` and frontend `RC-28`. Owners: `AppShell.tsx`, `useAppHashRouting`, `useAppSelectionViewerCompare`, browse window restore, and grid evidence. Begin with failing fresh-page Root and off-page close/back traces. Derive initial folder/image target before app presentation, send the anchor only on the initial request, and restore a visible selected cell with both Prev and Next available. Do not reset filters for an excluded target. Validation: a target near row 792 of the `table-1585` profile paints no provisional Root and returns to the exact visible cell.

   5. **S5-T5 — Make Smart Folder and folder/root counts authoritative.** Closes `RC-14`, `RC-23`, and `RC-29`. Owners: `useSmartFolders`, `LeftSidebar.tsx`, `FolderTree.tsx`, `useAppDataScope`, Toolbar counts, and toolbar/grid evidence. Begin with false-empty/interim-count frames. Use pending versus settled-empty Smart Folder state in a bounded scroll region; never publish direct/page count as recursive total; retain authoritative root count or include its readiness before promotion. Validation: delayed views/counts, nested `scope / root`, long lists, error, and scope switches paint no false empty/interim total or anchor shift.

6. **Sprint 6 — Finish Compare/ranking identity and ship the full program.** Demo: Compare and ranking first-open/navigation preserve decoded pixels, transforms, labels, controls, and metadata; all continuity scenarios pass together.

   1. **S6-T1 — Bind Compare first-open, navigation, controls, and transform to presented pair.** Closes `RC-17` and the Compare portion of `RC-19`. Owners: `CompareViewer.tsx`, `useCompareZoomPan`, Compare resource presentation, and grid pixel evidence. First make first-open blank and retained-pair transform reset fail. Do not expose content-ready overlay until the first pair decodes; retain pair labels/count/buttons/transform coherently during target decode and initialize target transform only at promotion. Validation: distinct-pixel first-open, boundaries, zoom/pan, A-to-B-to-C, and corrupt target show no blank/mixed/reset frame.

   2. **S6-T2 — Retain Compare Metadata during context and reload.** Closes `RC-12`. Owners: `useInspectorCompareMetadata`, `CompareMetadataSection.tsx`, compare context state, and Inspector evidence. First fail the matrix-to-one-loading-line collapse. Project compare context synchronously, retain the settled matrix during refresh, atomically promote target success/error, and reserve action/status width. Validation: context A-to-B-to-C, Reload, PIL toggle, narrow width, and failure never collapse settled content or mix columns.

   3. **S6-T3 — Bind ranking fullscreen transform and first-open to decoded identity.** Closes `RC-18` and the ranking-fullscreen portion of `RC-19`. Owners: `useRankingFullscreen`, `RankingApp.tsx`, resource/layout state, and grid pixel evidence. First fail blank first-open and retained-image transform reset. Retain prior pixels/label/transform until target decode and initialize target transform at promotion while preserving cache bounds, keyboard navigation, save status, and failure. Validation: first-open/navigation/zoom/A-to-B-to-C/corrupt traces pass.

   4. **S6-T4 — Decode-gate ranking board cards and own failure.** Closes `RC-20`. Owners: ranking board/card rendering, `useRankingSession` preload, bounded decoded resources, and grid evidence. First fail progressive/blank/broken-card frames. Reveal each visible card only after decode with coherent instance labels and explicit terminal error; avoid gallery-wide or unbounded preload. Validation: cold instance, viewport entry, rapid next-instance, and corrupt-card traces pass.

   5. **S6-T5 — Run closure, debloat, and packaged-asset gates.** Evidence for `RC-01` through `RC-30`; this is not a substitute for root tickets. Run every primary scenario independently, full Python/frontend tests/typecheck, GUI acceptance, build/rsync, lint, dependency/hard-cut checks, and final cleanup/review. Update the residual audit with outcomes rather than deleting history and add final sprint handoffs. The plan remains open if any RC mapping lacks passing primary evidence.


### Scope Budget and Guardrails


The budget is six sprints and twenty-five atomic tickets, with at most five tickets per sprint. This exceeds the moderate four-sprint/twelve-task heuristic because thirty confirmed findings cross six existing presentation owners and four independent browser gates; six end-to-end increments are the smallest grouping that closes every confirmed root path without one oversized rewrite. The expected owner areas are existing app/browse routing and presentation hooks, metrics/Derived controls, Inspector hooks/sections, Viewer/hover/media resources, Compare/ranking, focused frontend tests, browser probes, docs, and regenerated packaged assets.

No new dependency, app-wide presentation store, generic Suspense boundary system, screenshot-diff framework, parallel legacy path, unbounded cache, or speculative P2 behavior is permitted. At most one focused presentation owner may be added per existing domain: metrics, Inspector, browse, and media/Compare-ranking. Prefer deleting effect-time registration/restoration/clearing and stale tests as each owner becomes authoritative. Report production additions/deletions and helper count in each sprint handoff; a new helper must replace an existing branch/effect or be removed.

Every `S*-T*` ticket above is substantive code or browser-evidence work and must invoke `better-code` before and during implementation. The code agent states material assumptions and ambiguous interpretations, the one-to-five core invariants, smallest robust approach, files, and evidence before editing. It touches only lines tied to the request, invariants, or verification; adds no speculative feature/configuration; removes only code made unused by the ticket; and attaches a concrete check to every step. These Karpathy-style execution guardrails are mandatory.

Update this plan continuously during implementation, especially the Progress Log, scope/risk changes, primary evidence, and impacted task text. After each sprint, add a handoff containing files, commands/evidence, cleanup/review results, residual risks, and the next sprint. For minor script-level uncertainty such as exact helper placement, follow the approved plan to maintain momentum, log the choice, then request clarification after the sprint and apply any follow-up adjustment.

Delegate bounded codepath discovery early when it reduces context load. If a subagent remains active after ten minutes, request a brief progress update and why more time is needed; before forty minutes, wait instead of substituting manual/self-review. Only use a documented manual fallback after forty minutes without a usable response or explicit user approval. Cleanup and review agents are blocking once launched and may not be interrupted, repurposed, or terminated to reclaim the main loop.


### Gate routine


0. **Plan gate (fast).** Before each ticket, restate its goal, observable acceptance, material assumptions/ambiguities, and exact files. Stop and ask if an ambiguity changes behavior. Invoke `better-code` for every substantive ticket and restate the core invariants, smallest robust approach, and evidence.

1. **Implement gate (correctness-first).** Implement the smallest coherent slice that satisfies the ticket. Avoid speculative features, one-off abstractions, unrelated cleanup, or broad refactors. Run the focused reproduction/test before moving on.

2. **Cleanup gate.** After the sprint's implementation and primary evidence pass, run the blocking `code-simplifier` routine below.

3. **Review gate.** After cleanup, run the blocking review routine on the post-cleanup ship diff, resolve findings, rerun affected evidence, and only then write the sprint handoff or commit.


### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use `code-simplifier` on the current sprint changes. Start with formatting/lint fixes, obvious dead code, non-semantic readability edits, and comments/docs that state current truth. Keep the pass conservative and do not expand into semantic refactors without approval. Do not interrupt or repurpose the agent. If it is still running after ten minutes, request a brief progress update, then keep waiting. Manual cleanup is allowed only after forty minutes without a usable response or explicit user approval. If the subagent is unavailable or fails to launch, stop and ask the user for an alternative cleanup/review path.


### review routine


After cleanup, spawn a fresh best-available subagent with medium reasoning effort and instruct it to use `code-review` on the post-cleanup ship diff. The review must be constructively adversarial about correctness, mixed/stale identity, query ownership, edit safety, decode/resource lifetime, transforms, accessibility, scope creep, weak evidence, and removable complexity. Do not interrupt, repurpose, self-review, or proceed while it runs. If it is still running after ten minutes, request a brief progress update and keep waiting; before forty minutes, do not substitute manual review or guessed fixes. Resolve red flags, rerun affected evidence, and repeat review until clean. Manual fallback requires forty minutes without usable output or explicit user approval. If the review agent is unavailable, fails, or leaves an unresolved concern, stop and ask the user.


## Validation and Acceptance


### Primary acceptance


Primary browser evidence is authoritative. Each scenario starts from packaged assets, uses visibly distinct data/media, samples the earliest post-action frame, and records complete requested/presented identity. Final-DOM assertions, unit tests, geometry alone, and a screenshot after settlement cannot replace a failing painted-frame path.

1. **Sprint 1:** cold uncached Metric/Categorical switches, Folders/Derived tab cycles, collapse/reopen, responsive suppression, warm revisit, rapid A-to-B-to-C, and terminal empty/error show only complete A or complete B. No `Loading values…`, missing action/value, lost draft, or hidden focus target appears; supported outer anchors move at most one pixel.

       python -m scripts.browser.gui_jitter.probe --scenario metrics --output-json /tmp/lenslet-continuity-s1-metrics.json

2. **Sprint 2:** add and use the explicit table-backed `table-1585` fixture profile so evidence exercises pagination beyond the default small grid. Its delayed paginated/derived cases keep authoritative Derived values, controlled filters, count roles, full-population histogram, and metric rail atomic through fast/slow/empty/error transitions.

       python -m scripts.browser.gui_jitter.probe --scenario metrics --fixture-profile table-1585 --output-json /tmp/lenslet-continuity-s2-metrics.json
       python -m scripts.browser.gui_jitter.probe --scenario grid --fixture-profile table-1585 --output-json /tmp/lenslet-continuity-s2-grid.json

3. **Sprint 3:** twenty cold/warm Inspector selections plus A-to-B-to-C, slow metadata/detail/sidecar/preview decode, individual failures, autoload off, panel reopen, responsive suppression, narrow width, edit races, and copied feedback retain one coherent field/action/pixel identity. No placeholder replaces settled rows, no field/button/metric label disappears, and no empty or mismatched preview frame paints.

       python -m scripts.browser.gui_jitter.probe --scenario inspector --output-json /tmp/lenslet-continuity-s3-inspector.json

4. **Sprint 4:** distinct-color Viewer navigation and hover preview cases include cold/warm, rapid supersession, direct/proxy, corrupt target, back, and reduced motion. Every successful transition frame visibly contains decoded A or decoded B with matching label and transform; zero-visible-image and progressive target frames fail.

       python -m scripts.browser.viewer_probe.flicker_back --output-json /tmp/lenslet-continuity-s4-viewer.json
       python -m scripts.browser.gui_jitter.probe --scenario grid --output-json /tmp/lenslet-continuity-s4-grid.json

5. **Sprint 5:** the table-backed `table-1585` fixture covers a target near row 792, fresh folder/image hashes, off-page image restoration, folder/Smart Folder switches, delayed capabilities/views/direct-recursive-root counts, active Metrics, optimistic annotation during compatible retention, terminal outcomes, and hard resets. The first app frame is target-correct and no frame mixes scope, selection, schema, count, histogram, or rail identities.

       python -m scripts.browser.gui_jitter.probe --scenario toolbar --fixture-profile table-1585 --output-json /tmp/lenslet-continuity-s5-toolbar.json
       python -m scripts.browser.gui_jitter.probe --scenario grid --fixture-profile table-1585 --output-json /tmp/lenslet-continuity-s5-grid.json

6. **Sprint 6:** visibly distinct Compare/ranking resources cover Compare Metadata refresh/context changes, first-open, navigation boundaries, zoom/pan, rapid supersession, corrupt resources, board viewport entry, and instance change. Pixels, metadata columns, labels, counts, buttons, transforms, and error states remain coherent; no blank/progressive stage paints.

       python -m scripts.browser.gui_jitter.probe --scenario grid --output-json /tmp/lenslet-continuity-s6-grid.json
       python -m scripts.browser.gui_jitter.probe --scenario inspector --output-json /tmp/lenslet-continuity-s6-inspector.json

7. **Overall:** run all four `gui_jitter` scenarios, the Viewer probe, and default GUI acceptance independently. All `RC-01` through `RC-30` mappings must have direct primary evidence in the plan handoff. Do not hide a failing reported path behind a passing aggregate count.

       python -m scripts.browser.gui_jitter.probe --scenario toolbar --output-json /tmp/lenslet-continuity-final-toolbar.json
       python -m scripts.browser.gui_jitter.probe --scenario grid --output-json /tmp/lenslet-continuity-final-grid.json
       python -m scripts.browser.gui_jitter.probe --scenario inspector --output-json /tmp/lenslet-continuity-final-inspector.json
       python -m scripts.browser.gui_jitter.probe --scenario metrics --output-json /tmp/lenslet-continuity-final-metrics.json
       python -m scripts.browser.gui_jitter.probe --scenario metrics --fixture-profile table-1585 --output-json /tmp/lenslet-continuity-final-table-metrics.json
       python -m scripts.browser.gui_jitter.probe --scenario grid --fixture-profile table-1585 --output-json /tmp/lenslet-continuity-final-table-grid.json
       python -m scripts.browser.viewer_probe.flicker_back --output-json /tmp/lenslet-continuity-final-viewer.json
       python -m scripts.browser.gui_smoke.acceptance


### Secondary acceptance


1. Run focused owner tests during each ticket, then the full frontend suite and typecheck before each sprint handoff.

       npm --prefix frontend test -- --run
       cd frontend
       npx tsc --noEmit
       cd ..

2. Run painted-frame and browser-helper tests whenever evidence code changes.

       python -m pytest -q tests/scripts/test_painted_frames.py tests/browser/test_browser_probe_helpers.py tests/browser/test_browser_harness_helpers.py

3. For the Sprint 5 anchor work, require generic evaluator, HTTP route, and TableStorage parity tests before browser acceptance.

       python -m pytest -q tests/browse/test_query_evaluator.py tests/web/routes/test_browse_query.py tests/storage/table/test_table_browse_query_storage.py

4. Build and mirror packaged assets before primary browser evidence, then run repository hygiene.

       npm --prefix frontend run build
       rsync -a --delete frontend/dist/ src/lenslet/frontend/
       python scripts/lint_repo.py
       git diff --check

5. Confirm scope and debloat after every sprint. No dependency or parallel framework may appear; obsolete effect-time owners and stale expectations must be deleted rather than left dormant.

       git diff --stat
       git diff -- frontend/package.json frontend/package-lock.json pyproject.toml
       rg -n "GRID_PRESENTATION_GRACE_MS|METADATA_LOADING_COPY_DELAY_MS|VIEWER_LOADER_DELAY_MS" frontend/src

6. Run the full Python suite as a final closure gate after all focused and browser evidence passes.

       pytest


## Risks and Recovery


The primary correctness risk is allowing a retained control to mutate presented A after the user requests B. Recovery is one explicit presented identity per domain, inert/`aria-busy` unsafe controls, latest-target guards, and target-keyed feedback. Read-only navigation and cancellation remain available where safe.

Inspector aggregation can create a request waterfall or make a fast field wait on an unrelated source. Start existing target requests in parallel, define the minimum bundle explicitly, use query cache hits, and show only delayed reserved status. Do not serialize requests or duplicate the cache. A definitive target failure must retire retained data into a coherent error/retry state rather than strand A indefinitely.

Keeping tab/panel state can accidentally preserve hidden focus targets or background polling. Recovery is durable owner state with visibility-aware rendering/query enablement; keeping a subtree mounted is acceptable only if it is inert, inaccessible while hidden, and does not continue unnecessary work.

Decoded media retention can leak object URLs, retain transforms under the wrong target, or promote superseded resources. Each owner needs request identity, successful decode, connected/current checks, bounded cache/URL retirement, target-specific error, and tests for A-to-B-to-C plus corrupt B. Do not add a second unbounded preload system.

The deep-link window may expose a missing query capability. Reuse current browse-query/window primitives first. If the pre-approved minimal path anchor is needed, keep it internal to the existing request/response contract with focused backend/frontend tests. Stop before inventing a new endpoint or storage scan.

Browser harness growth can become a second UI framework. Extend the four focused scenarios and their existing helpers; add only data fields needed to reject a known bad frame. Split a file only at current repository guardrails and do not build a generic screenshot DSL.

Rollback is sprint-local through the conventional commit produced only after primary, cleanup, and review gates. Each ticket hard-cuts to its new authoritative owner and deletes the obsolete path and stale expectations in the same ticket; it does not ship parallel fallback ownership. If evidence fails, keep the sprint open and repair the hard cut, or revert the sprint commit as a unit after recording the failed evidence. Ralph retries are idempotent: read the Progress Log and latest handoff, rerun the failing focused gate, and continue the same sprint without skipping forward.


## Progress Log


- [x] 2026-07-19 UTC — Three read-only audit agents completed metrics/Inspector and browse/media/shell scans; findings were deduplicated into `RC-01` through `RC-30` with explicit non-findings.
- [x] 2026-07-19 UTC — `docs/DESIGN_SYSTEM.md` and `AGENTS.md` were updated to lock complete requested/presented identity, timing, lifecycle, decode, and descendant/pixel evidence rules.
- [x] 2026-07-19 UTC — Scope locked to all confirmed findings; intentional/unreproduced P2 candidates remain deferred and no user clarification is required.
- [x] 2026-07-19 UTC — Required constructively adversarial plan review completed; Inspector ordering, anchor semantics, RC mapping, representative fixtures, backend gates, and hard-cut recovery corrections were incorporated, and the follow-up verdict was clean.
- [x] 2026-07-19 UTC — Ralph plan workspace bootstrapped at `docs/ralph/20260719_frontend_ui_continuity_remediation/`; tmux session `ralph_20260719_lenslet_frontend_ui_continuity_remediation` passed session, pane, and progress-file startup checks.
- [x] 2026-07-19 UTC — S1-T1 complete: the former passing baseline recorded `dataset_from -> Loading values… -> review_group`; the strengthened descendant/action/value oracle failed that intermediate for Metric/Categorical success, empty, and error before product edits (`/tmp/lenslet-continuity-s1-t1-failing.json`).
- [x] 2026-07-19 UTC — S1-T2 complete: Metric and Categorical selectors/cards now retain one inert terminal field snapshot and promote the latest success/empty/error atomically; filter-free population histogram semantics remain authoritative.
- [x] 2026-07-19 UTC — S1-T3 complete: AppShell owns durable field requirements, derives initial metric/categorical keys synchronously, and receives direct selection/virtualization updates without the child-to-parent effect chain.
- [x] 2026-07-19 UTC — S1-T4 implementation and primary evidence complete: all left tools remain mounted but hidden/inert, inactive tools do not add facet requests, and tab/collapse/responsive cycles preserve node identity, field choice, Show-one state, and Derived drafts. The initial expanded metrics gate passed with zero anchor movement (`/tmp/lenslet-continuity-s1-metrics.json`); the review-remediated closure artifact is recorded below.
- [x] 2026-07-19 UTC — Sprint 1 review remediation complete: successive fresh reviews found and drove closure of missing facet hard-reset identity, hidden FolderTree work, responsive portal/focus lifetime, weak late-B/Show-all evidence, passive first-frame virtual ownership, zero-sized hidden-range loss, a responsive-hidden facet observer, per-field Show-all loading regressions, evidence that sampled only one virtual card, hidden Metrics/Derived row-scan work, and a schema oracle that skipped stale precursor frames. Metric/Categorical retain terminal snapshots independently while first-ever fields remain neutral; inactive mounted tools preserve owner state without polling, rendering virtual cards, or scanning item rows. The packaged primary probe crosses a 24-field batch boundary, checks every painted Metric and Categorical Show-all card, retains settled content and the exact bottom range through Show one/reopen, re-seeds virtual ownership at hard reset, and covers live visible/hidden A -> B -> A schema commits. Its marker begins on the actual schema-attribute commit, so the first marked frame must own the top batch; hidden frames render no cards and the first reopen frame renders only owned cards. The latest artifact passes with zero violations and `0.0 px` anchor movement (`/tmp/lenslet-continuity-s1-schema-live-metrics-11.json`), and the final fresh review reported no actionable findings.
- [x] Sprint 1 complete — Field/tool continuity and its primary evidence pass; handoff added.
- [x] 2026-07-19 UTC — `S2-T1` complete: only terminal facets or a complete local population become Derived truth; numeric and categorical rows retain one complete inert presentation through delayed success/empty/error; active draft demand is registered before paint; formula/name/weight/selection and the exact editor node survive compatible folder navigation in both directions while workspace/table-source changes remain hard resets.
- [x] 2026-07-19 UTC — `S2-T2`/`S2-T3` complete: attribute operators/text and histogram bounds synchronously project external filter identity outside actual edit drafts; focus without editing cannot resurrect an external clear; Population/Filtered/Selected and fixed-width row-count roles remain present with accessible full text across incomplete/unfiltered/unselected states.
- [x] 2026-07-19 UTC — `S2-T4` complete: metric-sorted browse promotion waits for an independent authoritative rail summary; the committed snapshot owns histogram/domain/quantiles; compatible A remains complete beyond 800 ms; repeated retries receive fresh grace; final pagination cannot reshape an already-promoted rail. The explicit `table-1585` profile exercises all 1,585 rows.
- [x] 2026-07-19 UTC — Sprint 2 cleanup/review closure complete: conservative cleanup removed a duplicate assertion and extracted one focused Derived evidence helper; successive fresh reviews drove closure of debounce canonicalization, invalid-preview settlement, retry/error inertness, demand/editor reset alignment, focus-only filter races, backend-rail reshaping, retry expiry, categorical whole-row promotion, stale packaged assets, per-frame numeric ownership, and bidirectional scope-draft evidence. The final fresh review reported no actionable findings. Full capability first-frame presentation remains scoped to `S5-T1` and no Sprint 5 behavior ships in this slice.
- [x] Sprint 2 complete — Derived/filter/count/metric-rail continuity and evidence pass; handoff added.
- [ ] Sprint 3 complete — Inspector fields/actions/preview/persistence continuity and evidence pass; handoff added.
- [ ] Sprint 4 complete — Viewer/hover decoded-media continuity and evidence pass; handoff added.
- [ ] Sprint 5 complete — Scope/routing/Smart Folder/count continuity and evidence pass; handoff added.
- [ ] Sprint 6 complete — Compare/ranking continuity and final closure gates pass; handoff added.


## Artifacts and Handoff


Canonical inputs are `AGENTS.md`, `docs/DESIGN_SYSTEM.md`, `docs/20260719_frontend_ui_continuity_residual_audit.md`, and this plan. The completed 2026-07-18 plan is historical implementation context where it does not conflict with the current contract.

The planned Ralph workspace is `docs/ralph/20260719_frontend_ui_continuity_remediation/` in plan mode, using shared assets under `docs/ralph/shared/`. Ralph must point to this exact plan path, execute one sprint slice per iteration, preserve append-only `progress.txt`, and update this plan continuously.

Primary evidence is written to `/tmp/lenslet-continuity-*.json`; sprint handoffs record exact commands, outcomes, changed owners, cleanup/review decisions, and residual risks. Shipped frontend assets under `src/lenslet/frontend/` are regenerated only after source tests/typecheck pass and are mirrored with `rsync -a --delete`.

### Sprint 1 handoff — 2026-07-19 UTC

Completed `S1-T1` through `S1-T4` in one sprint slice. AppShell now owns Metric/Categorical selection, Show-all, visible batches, reset identity, and schema revisions before paint. Metric and Categorical field cards retain independent terminal requested/presented snapshots and promote success/empty/error atomically. Left tools stay mounted across tab, collapse, and responsive suppression, while inactive FolderTree/Metrics/Derived work, facet polling, virtual cards, body-portaled popups, and hidden focus are suppressed without clearing expansion, scroll, drafts, selections, or settled presentations.

Changed owners are `frontend/src/app/{AppShell.tsx,components/LeftSidebar.tsx}`, `frontend/src/features/{folders,metrics}/`, `frontend/src/shared/ui/{Dropdown,ThemeSettingsMenu}.tsx`, `scripts/browser/gui_jitter/`, their focused frontend/Python tests, and regenerated `src/lenslet/frontend/` assets. No dependency manifests changed. Probe growth was kept below the hard guardrail by extracting controller, control, schema, and trace helpers; cleanup removed obsolete child-to-parent discovery and parallel facet-demand ownership rather than retaining compatibility paths.

Primary evidence: `python -m scripts.browser.gui_jitter.probe --scenario metrics --output-json /tmp/lenslet-continuity-s1-schema-live-metrics-11.json` passed with no violations and `0.0 px` maximum anchor movement. It covers cold/warm/success/empty/error/rapid field transitions, every rendered Show-all card, more than 24 metrics, exact bottom-range retention, hard resets, visible and hidden A -> B -> A schema commits, earliest target-schema and reopen frames, tab/collapse/responsive cycles, portal/focus closure, and stable hidden request counters.

Secondary gates passed: 665 frontend tests, TypeScript, 70 painted-frame/browser-helper tests, `python scripts/lint_repo.py`, `git diff --check`, packaged-asset dry-run parity, unchanged dependency manifests, and `python -m scripts.browser.gui_smoke.acceptance`. Acceptance retained its known non-failing folder re-entry anchor warning; overall status was `passed`. The final constructively adversarial review reported no actionable findings after the hidden CPU and schema-marker remediations.

No Sprint 1 blocker remains. The residual risk is confined to later planned domains; the full Python suite remains the plan-level final closure gate after all six sprints. The next operator begins Sprint 2 with `S2-T1`, using the table-backed `table-1585` fixture and preserving the completed Sprint 1 ownership model.

### Sprint 2 handoff — 2026-07-19 UTC

Completed `S2-T1` through `S2-T4` in one sprint slice. Derived numeric and categorical term rows now own complete requested/presented bundles with explicit pending/ready/empty/error state, inert retained controls, stable row identity, and authoritative population facets. The editor and its facet-demand owner share one workspace/table-source hard-reset identity, preserve unsaved drafts across compatible folder generations, and query only fields supported by the settled target schema. Controlled text/operator/range filters distinguish real edit drafts from synchronous external identity. Count roles remain structurally invariant. Metric-sorted browse snapshots now promote membership and an authoritative rail histogram/domain/quantile bundle together, preserve backend shape through final pagination, and give every same-target retry a fresh grace interval.

Changed owners are `frontend/src/app/{AppShell.tsx,components/LeftSidebar.tsx,hooks/useGridPresentation.ts}`, `frontend/src/features/{browse,metrics}/`, the focused frontend tests, `scripts/browser/gui_jitter/{grid,metrics,metrics_controls,metrics_derived,painted_frames,probe}.py`, browser-helper tests, and regenerated `src/lenslet/frontend/` assets. Production frontend source changed by 975 additions and 412 deletions. One new focused helper module, `metrics_derived.py`, replaced the extracted Derived transition branch from the near-guardrail metrics probe; no dependency manifests changed and no compatibility owner was retained.

Primary evidence passed from current packaged assets with zero violations and `0.0 px` maximum anchor movement: `python -m scripts.browser.gui_jitter.probe --scenario metrics --fixture-profile table-1585 --output-json /tmp/lenslet-continuity-s2-metrics.json` and `python -m scripts.browser.gui_jitter.probe --scenario grid --fixture-profile table-1585 --output-json /tmp/lenslet-continuity-s2-grid.json`. The metrics artifact covers numeric/categorical success, empty, error, every retained/terminal painted frame, controlled filter Clear/Smart Folder/focus-only paths, invariant count roles, and exact editor/draft identity across `/` -> `/metrics` -> `/`. The grid artifact covers sub/over-800 ms promotion, rapid targets, terminal empty/error, real inert retry interaction, two consecutive slow retries, all 1,585 paginated rows, and unchanged authoritative rail bins/quantiles after the final page.

Secondary gates passed: 677 frontend tests, TypeScript, 72 painted-frame/browser-helper tests, `python scripts/lint_repo.py`, `git diff --check`, packaged-asset dry-run parity, and an empty dependency-manifest diff. `python -m scripts.browser.gui_smoke.acceptance` passed with its known non-failing folder re-entry anchor warning. Conservative cleanup and repeated constructively adversarial reviews completed; the final reviewer reported no actionable findings.

No Sprint 2 blocker remains. Full capability identity during delayed `/folder-fields` scope transitions remains deliberately deferred to `S5-T1`; Inspector, decoded-media, scope/routing, and Compare/ranking risks remain in their planned later sprints. The next operator begins Sprint 3 at `S3-T1` and does not reopen Sprint 2 ownership without new failing evidence.
