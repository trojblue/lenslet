# Lenslet Ease-Of-Use Improvement Plan


## Outcome + Scope Lock


This plan turns the 2026-06-10 ease-of-use scan into a Phase 1 implementation path for making Lenslet feel trustworthy, smooth, and fast without bloating the product. Phase 1 is intentionally narrower than the full scan: it prioritizes backend truth, media reliability, stable browse context, bounded metric workflows, and shareable core analysis state.

Goals are to make repeated Lenslet use less surprising: table launches explain and enforce the actual source/media contract, source datasets are not mutated implicitly, filters/sorts/facets/derived scores remain backend-truthful, image surfaces do not fail as blank space, browse/viewer transitions preserve context, metric sorting stays bounded, and copied URLs reproduce the important analysis view.

Non-goals for Phase 1 are a visual reskin, a new frontend state manager, a general expression language, a custom virtualizer, a full design-system rewrite, a telemetry dashboard, broad compatibility layers, i18n, screen-reader-first accessibility, blind/disabled-user parity, HTML semantics audits, and full keyboard-only operation for every pointer workflow.

Keyboard shortcuts and keyboard-adjacent interaction quality remain in scope only where they already matter to fast Lenslet use: existing grid/viewer/ranking shortcuts, searchable dropdowns, context-preserving navigation, and clear focus after closing overlays. Broad ARIA/live-region/semantic work from the accessibility reports is useful background but is not immediate implementation scope.

Approved Phase 1 behavior changes are hard cutovers where they reduce misleading behavior: source Parquet files are immutable by default, backend-owned query/facet/derived truth for normal browse, workspace-scoped personal settings, explicit URL ownership for core shareable analysis state, bounded metric sort pages, clear failure states instead of blank media, and explicit source/workspace/dimension launch status. This repo is pre-release alpha, so do not preserve confusing old defaults just for compatibility.

Deferred items are a full SQL-like query engine, complete remote/HF streaming ingestion, durable cloud share aliases, full filtered facet counts for every field if too expensive, broad ranking visual redesign, smart-folder/similarity/ranking deep URL restoration beyond the base query state, and comprehensive accessibility compliance.


## Context


The scan was requested after several concrete product failures: dropdowns were hard to search, metrics/filtering mixed loaded-window and backend truth, source-column and dimension detection were surprising, HTTP media behavior was too implicit, fullscreen navigation and scroll restoration could lose context, metric rail jumps could mislead, and shared URLs did not capture enough view state.

The current architecture is strong enough to improve without a rewrite. Browse query truth flows through `POST /folders/query`, table storage has row-id based query windows, facets are separate from browse windows, React Query owns server data, `VirtualGrid` already has selection/top-anchor restore hooks, media requests are budgeted, and the frontend has useful primitives such as searchable `Dropdown`.

The weak spots are mostly ownership boundaries and feedback surfaces. Large files like `frontend/src/app/AppShell.tsx`, `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/styles.css`, and `src/lenslet/storage/table/storage.py` coordinate many concerns. Phase 1 avoids piling more ad hoc logic into those files where a small backend contract or shared utility would make behavior simpler.

The 12 agent reports live under `docs/20260610_ux_ease_scan/agent_reports/`. They cover six paired aspects: browse/grid, metrics/filters, backend/table/media, navigation/state, performance/scalability, and accessibility/resilience. The plan review in `docs/20260610_ux_ease_scan/20260610_lenslet_ux_improvement_plan_review.md` recommended revising the original broad roadmap before use. This revision applies that feedback by making backend trust fixes explicit, defining a Phase 1 boundary, and moving broad accessibility and speculative URL/performance work into backlog.

The strongest repeated findings retained for Phase 1 are:

- Make truth backend-owned and visibly provenance-aware.
- Fix root backend trust problems, not just UI messaging around them.
- Preserve user context across mode, filter, sort, layout, and media transitions.
- Prefer bounded payloads and explicit summaries over hydrating huge result windows.
- Show loading, empty, partial, and error states where the user is looking.
- Make shareable state canonical, and personal preferences workspace-scoped.


## Plan of Work


While implementing each sprint, update this plan document continuously, especially Progress Log and Artifacts and Handoff. After each sprint, add handoff notes with changed files, validation evidence, and remaining risks. For minor script-level uncertainties, such as exact test placement, proceed according to this plan and record the choice afterward.

For every non-trivial code ticket, the implementing agent must use the `better-code` skill before and during implementation. State assumptions and acceptance criteria first, choose the smallest robust path, touch only files tied to the request and validation, avoid speculative abstractions, and attach evidence to each change.

### Phase 1 Scope Budget and Guardrails

Phase 1 is three implementation sprints plus validation. Later roadmap candidates are recorded below but are not immediate work. This keeps the work executable and prevents polished UI tasks from outrunning the trust fixes.

The core invariants are:

- Source datasets and source Parquet tables are not mutated by default.
- Normal browse membership, order, totals, facet truth, and derived metric truth are backend-owned.
- Frontend windows, loaded rows, and visible cards never masquerade as full-population truth.
- Sort/filter/search/view-mode transitions preserve selected or top-anchor context when the path still exists.
- Folder scope changes clear or revalidate selection and inspector state.
- Media surfaces never fail as blank silent space.
- Large-folder/table paths stay bounded by windowed payloads and measured request budgets.
- URL state owns shareable analysis context; localStorage owns personal workspace preferences; backend owns durable data.

Debloat targets are loaded-window metric truth, 50k first-page metric sort hydration, recursive no-limit UI paths, console-only or `alert()` action errors, global unscoped shell settings, source/row/dimension decisions that exist only in terminal logs, and frontend-only heuristics for backend-owned facts.

### Gate Routine for Every Ticket

0. Plan gate: restate the ticket goal, acceptance criteria, assumptions, expected files, and the invariant being protected. If a behavior ambiguity would change the implementation, ask before coding. For substantive code, use `better-code` to identify the smallest robust approach and verification evidence.

1. Implement gate: implement one coherent slice. Avoid broad refactors, speculative features, duplicated state stores, compatibility shims, and unrelated cleanup.

2. Cleanup gate: run the `code-simplifier routine` after each sprint.

3. Review gate: run the `review routine` after cleanup and before declaring the sprint complete.

### code-simplifier routine

After each complete sprint, spawn a subagent using the `code-simplifier` skill to scan only current sprint changes. The pass should remove obvious dead code introduced by the sprint, simplify local duplication, fix formatting/lint issues, and keep comments aligned with behavior. It must not expand into semantic refactors unless explicitly approved.

### review routine

After cleanup, spawn a fresh subagent using the `code-review` skill with `reasoning_effort` set to `medium`. The review should be constructively adversarial: look for correctness gaps, hidden local truth, unbounded payloads, stale state, media policy regressions, performance regressions, and unnecessary complexity. Fix real findings, rerun focused validation, and record unresolved risks in this document.

### Sprint 1: Backend Trust, Source Immutability, And Media Policy

Demo outcome: a user can launch a table and know Lenslet chose the right source/path contract, source Parquet files are not rewritten by default, media loading has a clear direct/proxy/streaming policy, and failures are visible instead of silent.

- S1-T1: Make source Parquet immutable by default.
  Move discovered dimension persistence out of source Parquet writes and into a workspace/cache-backed store keyed by table signature and stable row identity. Keep any in-place Parquet dimension write as an explicit opt-in flag with separate tests.

- S1-T2: Add a backend table/media launch status payload and CLI/UI summary.
  Include source column, path mode, root/base-dir policy, workspace mode, total table rows, gallery rows, skipped-row counters, media source kind, dimension coverage, cache/write policy, and warnings. Redact sensitive local paths for shared clients.

- S1-T3: Define and implement a narrow HTTP original media policy.
  Direct browser URL handoff is allowed only when safe and selected. Backend proxy mode should stream rather than fully buffer large originals. Direct image failure should have an automatic or one-click proxy fallback when backend fetch can succeed.

- S1-T4: Make media fetch failures visible in thumbnails, hover preview, viewer, and compare.
  Extend the frontend media resource hook to return `loading`, `url`, `error`, and retry state. Preserve backend media error categories such as local not found, remote not found, permission, timeout, decode, and upstream failure.

- S1-T5: Add an app-level action feedback channel for user-triggered failures.
  Replace swallowed errors and `alert()` paths for table source switching, refresh, export/download, clipboard, ranking save, and inspector bulk updates with one concise status/error surface. This is interaction resilience, not accessibility compliance.

### Sprint 2: Browse Continuity, Selection Boundaries, And Honest States

Demo outcome: users can scroll, select, search, sort, filter, resize cards, enter viewer, navigate next/prev, change folders, and return without stale inspector targets, context jumps, or blank image swaps.

- S2-T1: Treat folder scope changes as a selection boundary.
  Clear or revalidate `selectedPaths`, inspector target, compare eligibility, and sidecar edit target when opening a new folder unless the transition is from a viewer hash that explicitly selects a path.

- S2-T2: Generalize selection/top-anchor restore for sort, filter, search clear, view mode, thumbnail size, folder re-entry, and viewer close.
  Capture selected path first, top anchor second, and restore only after the new backend window contains the target. Avoid client-side page walking.

- S2-T3: Make viewer next/prev non-blank.
  Keep the previous ready image visually retained and clearly non-current until the next image decodes, then crossfade or swap without exposing the stale image as the current resource.

- S2-T4: Improve thumbnail demand loading during scroll.
  Split visible demand loading from adjacent prefetch. Visible rows should load through budgets even while scrolling; offscreen prefetch stays deferred and bounded.

- S2-T5: Add stable grid states for updating, empty, loading more, unsupported, and failed query.
  Add a bottom sentinel with loaded/filtered counts and retry. Mark old grid results as updating during slow committed backend query transitions without replacing useful content with a full-screen spinner.

### Sprint 3: Canonical Query Identity, Metrics Truth, And Bounded Ranking

Demo outcome: metrics and derived score workflows are clear, searchable, backend-truthful, URL-shareable for the core view, and bounded on large tables; the metric rail no longer implies full-population authority from a loaded subset.

- S3-T1: Define one canonical browse query identity.
  Use the same normalized identity for `/folders/query`, query-shaped facets, derived metric status, metric summaries, URL round-trips, and request tokens. Phase 1 URL ownership includes folder/hash, `q`, filters, sort, random seed when random is active, derived metric spec when present, and unsupported metric intent.

- S3-T2: Add query-shaped facets or query-aware facet summaries.
  Facet requests must share canonical query identity with browse queries. Return explicit count provenance: scope population, query-filtered count when backend-computed, and loaded-window count only when labeled as such or omitted.

- S3-T3: Move normal-browse derived metric display/status to backend response truth.
  Return derived metric key, display name, applied/unavailable status, valid/invalid counts, missing inputs, and item score values from backend query evaluation. Keep frontend derived evaluation for drafts and similarity mode only.

- S3-T4: Split field capabilities.
  Replace broad metric heuristics with backend-provided capability metadata: display metrics, sortable/filterable metrics, numeric formula inputs, categorical inputs, labels, raw keys, type/source, and availability.

- S3-T5: Replace the 50k metric-sort hydration path.
  Keep item pages near normal page size. Feed the metric rail from backend metric summaries and add a narrow seek/window-by-metric-value contract if click-to-jump remains.

- S3-T6: Polish derived score authoring without adding an expression engine.
  Fail closed on formula import when referenced terms are missing, add clearer diagnostics, output-score preview histogram from existing evaluation, direct "sort by this score" action, and searchable categorical value lists for high-cardinality cards.

### Phase 1 Validation Sprint

Demo outcome: Phase 1 changes are proven on real Lenslet workflows, not just small unit fixtures.

- V1-T1: Run the reported large Parquet workflow and record source/status, dimension immutability, backend-filter truth, metric sort payload bounds, and media failure behavior.
- V1-T2: Run browse/grid browser acceptance for filter, search, sort, viewer next/prev, folder scope change, and empty/error states.
- V1-T3: Run metrics/derived query identity tests and a large table metric sort scenario.
- V1-T4: Build, package, lint, and record evidence.

### Approved Backlog Candidates, Not Immediate

These came from the scan but should not start until Phase 1 passes.

- Workspace-scope all personal shell settings, active left tool, and recurring notice dismissals if not completed inside S3 URL work.
- Compare URLs, selected-path share links, smart-folder URL identity, safe path-based similarity URLs, and ranking instance URLs.
- Native folder-path listing, large folder-tree virtualization, backend thumbnail byte-budget LRU, frontend queue drop policies, and row-native query fast paths selected from measurement.
- Lightweight menu/popover primitive if menu inconsistency becomes a near-term quality blocker.
- Overlay focus policy cleanup where it directly affects current viewer/compare/similarity/ranking workflows.
- Grid/tree ContextMenu key, Shift+F10, focus-model cleanup, keyboard splitters, drag-sort keyboard support, ARIA labels, live-region completeness, screen-reader support, and i18n. These are explicitly deferred accessibility/compliance items, not Phase 1 requirements.
- Ranking semantic accessibility and broad ranking visual/token pass.


## Validation and Acceptance


Primary acceptance must be scenario-driven, not only unit tests. Each Phase 1 sprint should include focused unit/model tests plus at least one browser or real-fixture validation that matches how users operate Lenslet.

Primary Phase 1 gates:

- Source immutability: launch a Parquet with missing dimensions and assert the source file hash/mtime is unchanged while browse, metadata, thumbnails, and dimension filters can use workspace/cache-backed dimensions.
- Launch/status truth: CLI and UI show selected source column, path mode, workspace mode, row totals, skipped counts, dimension policy, and media source kind without leaking sensitive paths to shared clients.
- Media policy: fake large HTTP original proves proxy mode streams rather than buffering all bytes; browser test proves direct image display can fail and recover through backend fallback.
- Selection boundary: select an item in folder A, open folder B, and assert inspector path, selected paths, compare eligibility, and sidecar edit target are cleared.
- Browse continuity: deep scroll context survives sort/filter/view-size changes when the target path remains in the new backend window; viewer next/prev has no all-background blank interval under delayed file responses.
- Metrics truth: query-shaped facets and derived metric status match backend query truth over unloaded rows; z-normalized derived scores display backend full-scope values; formula import with missing fields fails closed.
- Metric bounds: metric sort first payload remains near normal page size, and metric rail data comes from backend summaries or is visibly unavailable/incomplete.
- URL core state: `q`, filters, sort, random seed, derived score spec, and unsupported metric intent round-trip without localStorage overriding explicit URL state.

Commands expected during Phase 1 validation:

    python -m scripts.browser.gui_smoke.acceptance
    python -m scripts.browser.large_tree.smoke --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json
    cd frontend && npm test -- --run
    cd frontend && npm run build
    rsync -a --delete frontend/dist/ src/lenslet/frontend/
    python scripts/lint_repo.py

Add focused tests near affected code. Examples include table launch/dimension cache pytest, media streaming tests, browse query/facet backend tests, frontend URL round-trip tests, `useAppSelectionViewerCompare` scope-boundary tests, and Playwright delayed media/filter/sort scenarios.


## Risks and Recovery


The main risk is adding polish while preserving misleading ownership. Recovery is to block any frontend-only truth fallback for normal browse and require backend contracts for membership, order, totals, facets, derived values, and source/media status.

The second risk is treating status as a substitute for root fixes. Recovery is to require source immutability, media streaming/fallback policy, and stale selection clearing as code behavior, not just UI disclosure.

The third risk is overbuilding shared primitives. Recovery is to defer broad accessibility/menu/dialog primitive work until Phase 1 passes, and keep any immediate interaction fixes tied to current user workflows.

The fourth risk is performance regression from nicer UI. Recovery is to measure payload bytes, first grid, first thumbnail, frame gaps, query p95, request queue peaks, and RSS where relevant before accepting changes.

The fifth risk is URL bloat or parallel query identities. Recovery is to implement one canonical browse query identity first, URL-own only reproducible Phase 1 analysis state, avoid vectors/transforms/large selections, and keep durable named/saved views backend-owned.

The sixth risk is source/media diagnostics leaking sensitive local paths or signed URLs. Recovery is to redact diagnostics based on trusted-local context and keep share clients on safe summaries.

Rollback is sprint-local. Most changes are additive contracts or hard cutovers in alpha; if a sprint misses primary acceptance, revert that sprint's behavior path and keep the plan open rather than shipping proxy-only improvements.


## Progress Log


- [x] 2026-06-10: Re-read repository guidance, Lenslet skill, better-code guidance, and recent backend browse query plan.
- [x] 2026-06-10: Re-checked architecture files across `frontend/src/app`, browse/grid, metrics, media, table storage, routes, and settings.
- [x] 2026-06-10: Created `docs/20260610_ux_ease_scan/agent_reports/`.
- [x] 2026-06-10: Launched 12 `gpt-5.5` `xhigh` agents across six paired aspects.
- [x] 2026-06-10: All 12 agent reports completed under `docs/20260610_ux_ease_scan/agent_reports/`.
- [x] 2026-06-10: Read the full report set and consolidated repeated findings into the initial plan.
- [x] 2026-06-10: External plan review completed in `docs/20260610_ux_ease_scan/20260610_lenslet_ux_improvement_plan_review.md`; recommendation was revise before use.
- [x] 2026-06-10: Revised plan to add a Phase 1 boundary, make source immutability/media policy/selection boundaries/canonical query identity explicit, and defer broad accessibility/compliance work based on user clarification.
- [x] 2026-06-10: Final markdown verification confirmed the revised plan, review file, and all 12 agent reports are present under `docs/20260610_ux_ease_scan/`.


## Artifacts and Handoff


Agent report artifacts:

- `docs/20260610_ux_ease_scan/agent_reports/01_browse_grid_codepaths.md`
- `docs/20260610_ux_ease_scan/agent_reports/02_browse_grid_product_feel.md`
- `docs/20260610_ux_ease_scan/agent_reports/03_metrics_filters_codepaths.md`
- `docs/20260610_ux_ease_scan/agent_reports/04_metrics_filters_product_feel.md`
- `docs/20260610_ux_ease_scan/agent_reports/05_backend_table_media_codepaths.md`
- `docs/20260610_ux_ease_scan/agent_reports/06_backend_table_media_product_feel.md`
- `docs/20260610_ux_ease_scan/agent_reports/07_navigation_state_codepaths.md`
- `docs/20260610_ux_ease_scan/agent_reports/08_navigation_state_product_feel.md`
- `docs/20260610_ux_ease_scan/agent_reports/09_performance_scalability_codepaths.md`
- `docs/20260610_ux_ease_scan/agent_reports/10_performance_scalability_product_feel.md`
- `docs/20260610_ux_ease_scan/agent_reports/11_accessibility_resilience_codepaths.md`
- `docs/20260610_ux_ease_scan/agent_reports/12_accessibility_resilience_product_feel.md`

Review artifact:

- `docs/20260610_ux_ease_scan/20260610_lenslet_ux_improvement_plan_review.md`

Plan artifact:

- `docs/20260610_ux_ease_scan/20260610_lenslet_ux_improvement_plan.md`

Recommended first implementation sprint is Sprint 1. It closes the largest trust gaps with source immutability, visible launch/media status, a clear HTTP-original policy, and user-visible failures. Do not start by restyling the interface or doing broad accessibility compliance work. Start by making existing behavior truthful, explicit, and measurable.
