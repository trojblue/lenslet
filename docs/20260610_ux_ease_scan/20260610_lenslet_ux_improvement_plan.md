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

The 12 agent reports live under `docs/20260610_ux_ease_scan/agent_reports/`. They cover six paired aspects: browse/grid, metrics/filters, backend/table/media, navigation/state, performance/scalability, and accessibility/resilience. The plan review in `docs/20260610_ux_ease_scan/20260610_lenslet_ux_improvement_plan_review.md` recommended revising the original broad roadmap before use. A later reviewer pass in `docs/20260610_ux_ease_scan/20260610_reviewer_feedback.md` approved the direction but found that several contracts needed to be locked before implementation to avoid parallel truths across query identity, media policy, source/path identity, selection state, URL state, and derived metrics. This revision applies both reviews by making backend trust fixes explicit, defining a Phase 1 boundary, adding a contract-lock sprint, splitting the query/metrics sprint, and moving broad accessibility and speculative URL/performance work into backlog.

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

Phase 1 is a contract-lock sprint, four implementation sprints, and validation. Later roadmap candidates are recorded below but are not immediate work. This keeps the work executable and prevents polished UI tasks from outrunning the trust fixes.

The core invariants are:

- Source datasets and source Parquet tables are not mutated by default.
- Normal browse membership, order, totals, facet truth, and derived metric truth are backend-owned.
- Frontend windows, loaded rows, and visible cards never masquerade as full-population truth.
- The canonical analysis query identity excludes offset, limit, request generation, and transport-only fields; window request tokens may include them.
- Sort/filter/search/view-mode transitions preserve selected or top-anchor context when the path still exists.
- Folder scope changes clear or revalidate selection and inspector state.
- Backend owns original-media policy; frontend rendering can choose the display path but must not infer policy from `http` string checks alone.
- Dimension caches are namespaced by table fingerprint, source identity, and row identity so switching source columns cannot reuse wrong dimensions.
- Media surfaces never fail as blank silent space, and aborted/cancelled thumbnail requests during scrolling are not user-visible errors.
- Large-folder/table paths stay bounded by windowed payloads and measured request budgets.
- Explicit URL state owns shareable analysis context and always wins over localStorage. localStorage owns personal workspace preferences; backend owns durable data.

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

### Sprint 0: Contract Lock And Fixture Baseline

Demo outcome: implementers have one shared source of truth for query identity, media policy, source/dimension identity, selection boundaries, and URL ownership before behavior changes begin.

- [x] S0-T1: Write an ownership matrix for the Phase 1 contracts.
  Cover source data, workspace cache, browse query, facets, media originals, URL state, localStorage preferences, selection, inspector/sidecar targets, compare state, and derived metrics. The matrix must say which layer owns each fact and which layers may only display or cache it.

- [x] S0-T2: Define canonical analysis query identity separately from window request tokens.
  `analysisQueryKey` includes folder/scope, `q`, filters, sort intent, random seed when active, derived metric spec intent, and unsupported metric intent. It must not include offset, limit, request generation, or transport-only fields. `windowRequestToken` may include `analysisQueryKey`, offset, limit, and request generation.

- [x] S0-T3: Define backend-owned media policy and redaction contracts.
  Lock the media original policy enum before frontend fallback work. The contract should support local streaming, backend-proxy-required, browser-direct-allowed, browser-direct-preferred-with-proxy-fallback, and unsupported modes, plus source kind, proxy availability, direct-allowed reason, redacted origin, and warnings.

- [x] S0-T4: Create baseline fixtures and tests before feature edits.
  Cover Parquet with missing dimensions, multiple source/path columns, local and HTTP media, direct-browser media failure with backend fallback, large-table metric sorting, URL-vs-localStorage precedence, and folder-scope selection clearing.

### Sprint 1: Backend Trust, Source Immutability, And Media Policy

Demo outcome: a user can launch a table and know Lenslet chose the right source/path contract, source Parquet files are not rewritten by default, media loading has a clear direct/proxy/streaming policy, and failures are visible instead of silent.

- [x] S1-T1: Make source Parquet immutable by default.
  Replace default in-source Parquet dimension caching with workspace-backed dimension caching. The default must never rewrite the source Parquet. Keep source mutation only behind an explicit opt-in such as `--write-source-dimensions` or `--dimension-cache=source`, with separate tests. Key cached dimensions by table fingerprint, source identity, and row identity: include source parquet path, file size, mtime or affordable content hash, schema hash, row count, selected source column, selected path/root/base-dir mode, workspace id, stable row id when available, and otherwise row index plus normalized source/path value.

- [x] S1-T2: Add a backend table/media launch status payload and CLI/UI summary.
  Include source column, path mode, root/base-dir policy, workspace mode, total table rows, gallery rows, skipped-row counters, media source kind, dimension coverage, dimension cache/write policy, original-media policy, proxy availability, redacted origin, and warnings. Redact sensitive local paths and signed URL details for shared clients.

- [x] S1-T3: Define and implement a narrow HTTP original media policy.
  Direct browser URL handoff is allowed only when policy says it is safe and selected. Backend proxy mode must stream rather than fully buffer large originals, preserve safe content headers, handle or pass through ranges where supported, cancel upstream reads on client disconnect, and enforce timeouts/max-byte policies. Direct image failure is tracked per item/session and should have an automatic or one-click proxy fallback when backend fetch can succeed; it must not globally change source policy by itself.

- [x] S1-T4: Make media fetch failures visible in thumbnails, hover preview, viewer, and compare.
  Replace `string | null` media resource results with an explicit state: idle, loading with request id, ready with URL and source, error with retry, or unsupported with reason. Preserve backend media error categories such as local not found, remote not found, permission, timeout, decode, and upstream failure. Do not surface aborted/cancelled thumbnail requests from normal fast scrolling as user-visible errors.

- [x] S1-T5: Add an app-level action feedback channel for user-triggered failures.
  Replace swallowed errors and `alert()` paths for table source switching, refresh, export/download, clipboard, ranking save, and inspector bulk updates with one concise status/error surface. This is interaction resilience, not accessibility compliance.

### Sprint 2: Browse Continuity, Selection Boundaries, And Honest States

Demo outcome: users can scroll, select, search, sort, filter, resize cards, enter viewer, navigate next/prev, change folders, and return without stale inspector targets, context jumps, or blank image swaps.

- [x] S2-T1: Treat folder scope changes as a selection boundary.
  Clear or revalidate `selectedPaths`, inspector target, compare set and compare eligibility, sidecar edit target, hover preview target, context menu target, viewer path unless opened from an explicit viewer hash, similarity/ranking target where path-scoped, pending media prefetches for old scope, metric rail jump target, top-anchor restore token, and stale query/facet/metric request tokens.

- [x] S2-T2: Generalize selection/top-anchor restore for sort, filter, search clear, view mode, thumbnail size, folder re-entry, and viewer close.
  Capture selected path first, top anchor second, and restore only after the new backend window contains the target. Avoid client-side page walking.

- [x] S2-T3: Make viewer next/prev non-blank.
  Use two-layer viewer state: `targetPath` updates immediately, `displayedResource` keeps the last decoded image, and `pendingResource` loads the new target. Metadata, title, URL, and next/prev state must reflect the new target immediately. The old image may remain visible only as clearly transitioning/non-current until the new image decodes; if the new image fails, show an error for the new item rather than silently showing the old image as current.

- [x] S2-T4: Improve thumbnail demand loading during scroll.
  Split visible demand loading from adjacent prefetch. Visible rows should load through budgets even while scrolling; offscreen prefetch stays deferred and bounded.

- [x] S2-T5: Add stable grid states for updating, empty, loading more, unsupported, and failed query.
  Add a bottom sentinel with loaded/filtered counts and retry. Mark old grid results as updating during slow committed backend query transitions without replacing useful content with a full-screen spinner.

### Sprint 3A: Canonical Query Identity, Facets, And Capabilities

Demo outcome: browse, facets, capabilities, and URL round-tripping share one canonical analysis identity, and explicit URL state cannot be overwritten by localStorage.

- [x] S3A-T1: Implement one canonical analysis query identity.
  Use `analysisQueryKey` for `/folders/query`, query-shaped facets, field capabilities, derived metric status, metric summaries, URL round-trips, and cache/provenance checks. Use a separate `windowRequestToken` for offset/limit/generation-bound requests. Phase 1 URL ownership includes folder/hash, `q`, filters, sort, random seed when random is active, derived metric spec when present, and unsupported metric intent.

- [x] S3A-T2: Add query-shaped facets or query-aware facet summaries.
  Facet requests must share canonical query identity with browse queries. Return explicit count provenance: scope population, query-filtered count when backend-computed, and loaded-window count only when labeled as such or omitted.

- [x] S3A-T3: Split field capabilities.
  Replace broad metric heuristics with backend-provided capability metadata: display metrics, sortable/filterable metrics, numeric formula inputs, categorical inputs, labels, raw keys, type/source, and availability.

- [x] S3A-T4: Tighten URL/localStorage precedence.
  Explicit URL state always wins over localStorage for `q`, filters, sort, random seed, derived metric spec, and unsupported metric intent. localStorage may fill only absent personal preferences such as pane state or display preferences. Tests must prove copied URLs reproduce the analysis view in a fresh browser profile and in a profile with conflicting saved preferences.

### Sprint 3B: Backend Derived Metrics And Bounded Metric Navigation

Demo outcome: derived score workflows are clear, searchable, backend-truthful, and bounded on large tables; the metric rail no longer implies full-population authority from a loaded subset.

- [x] S3B-T1: Move normal-browse derived metric display/status to backend response truth.
  Return derived metric key, display name, applied/unavailable/invalid status, score scope, valid/invalid counts, missing inputs, unavailable categoricals, z-normalization mean/std when applicable, and item score values from backend query evaluation. Keep frontend derived evaluation for drafts and similarity mode only.

- [x] S3B-T2: Define derived metric score scope.
  Normal browse derived scores use the query-filtered population before offset/limit, only rows with valid inputs for normalization/statistics, and report valid, invalid, and missing counts. If a future score intentionally uses folder-wide normalization, it must be labeled as folder scope instead of silently appearing query-shaped.

- [x] S3B-T3: Replace the 50k metric-sort hydration path.
  Keep item pages near normal page size. Feed the metric rail from backend metric summaries and add a narrow seek/window-by-metric-value contract if click-to-jump remains.

- [x] S3B-T4: Polish derived score authoring without adding an expression engine.
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


## Interfaces and Dependencies


Phase 1 changes a few internal contracts. Keep these small and explicit; do not add a general query language, a new frontend state manager, or broad compatibility wrappers.

Canonical query identity has two names. `analysisQueryKey` is the semantic identity for browse analysis: folder/scope, `q`, filters, sort intent, random seed when active, derived metric spec intent, and unsupported metric intent. It excludes offset, limit, request generation, and transport-only fields. `windowRequestToken` is a request/window identity: `analysisQueryKey` plus offset, limit, and generation. Facets, field capabilities, derived metric status, metric summaries, URL round-trips, and provenance checks use `analysisQueryKey`; paginated item fetches use `windowRequestToken`.

Backend original-media policy owns direct/proxy behavior. The enum should cover local file streaming, backend proxy required, browser direct allowed, browser direct preferred with proxy fallback, and unsupported. The payload should include source kind, proxy availability, direct-allowed status or reason, redacted origin, and warnings. Frontend media rendering may choose direct/proxy display from this contract, but must not independently decide policy from source strings.

Frontend media resource state should distinguish idle, loading, ready, error, and unsupported states. Ready state includes URL and whether it came from direct, blob, or proxy. Error state includes a typed media error and retry path. Aborted thumbnail requests caused by fast scrolling are normal cancellation, not a visible item error.

Derived metric status is backend-owned for normal browse. The response must include key, display name, applied/unavailable/invalid status, score scope, valid and invalid counts, missing numeric inputs, unavailable categorical inputs, z-normalization mean/std when applicable, and item score values for the returned page. Normal browse score scope is query-filtered population before offset/limit unless explicitly labeled otherwise.


## Validation and Acceptance


Primary acceptance must be scenario-driven, not only unit tests. Each Phase 1 sprint should include focused unit/model tests plus at least one browser or real-fixture validation that matches how users operate Lenslet.

Primary Phase 1 gates:

- Contract lock: ownership matrix exists, `analysisQueryKey` and `windowRequestToken` tests prove offset/limit separation, media policy enum/redaction contract is covered, and baseline fixtures cover missing dimensions, multiple source/path columns, local/HTTP media, direct-browser failure, large metric sort, URL precedence, and folder-scope selection clearing.
- Source immutability: launch a Parquet with missing dimensions and assert the source file hash/mtime is unchanged while browse, metadata, thumbnails, and dimension filters can use workspace/cache-backed dimensions. Switching source columns must namespace or invalidate cached dimensions so dimensions from one column cannot apply to another.
- Launch/status truth: CLI and UI show selected source column, path mode, workspace mode, row totals, skipped counts, dimension policy, media source kind, original-media policy, proxy availability, and redacted origin without leaking sensitive paths or signed URLs to shared clients.
- Media policy: fake large HTTP original proves proxy mode streams rather than buffering all bytes, preserves safe content headers, handles disconnect cancellation, enforces timeout/max-byte policy, and keeps local `FileResponse` fast path unchanged. Browser test proves direct image display can fail and recover through backend fallback without globally changing source policy.
- Selection boundary: select an item in folder A, open folder B, and assert selected paths, inspector path, compare set/eligibility, sidecar edit target, hover target, context menu target, old viewer path, path-scoped ranking/similarity target, media prefetches, metric rail jump target, restore token, and stale request tokens are cleared or revalidated.
- Browse continuity: deep scroll context survives sort/filter/view-size changes when the target path remains in the new backend window; viewer next/prev has no all-background blank interval under delayed file responses and never exposes an old image as the current item after metadata has moved to the new target.
- Metrics truth: query-shaped facets and derived metric status match backend query truth over unloaded rows; z-normalized derived scores use the query-filtered population before offset/limit and report score scope, valid counts, invalid counts, missing inputs, and z mean/std; formula import with missing fields fails closed.
- Metric bounds: metric sort first payload remains near normal page size, and metric rail data comes from backend summaries or is visibly unavailable/incomplete.
- URL core state: `q`, filters, sort, random seed, derived score spec, and unsupported metric intent round-trip in a fresh browser profile and in a profile with conflicting saved preferences. Explicit URL state always wins over localStorage.

Commands expected during Phase 1 validation:

    python -m scripts.browser.gui_smoke.acceptance
    python -m scripts.browser.large_tree.smoke --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json
    cd frontend && npm test -- --run
    cd frontend && npm run build
    rsync -a --delete frontend/dist/ src/lenslet/frontend/
    python scripts/lint_repo.py

Add focused tests near affected code. Examples include table launch/dimension cache pytest, media streaming tests, browse query/facet backend tests, frontend URL round-trip tests, media resource-state tests, `useAppSelectionViewerCompare` scope-boundary tests, and Playwright delayed media/filter/sort scenarios.


## Risks and Recovery


The main risk is adding polish while preserving misleading ownership. Recovery is to block any frontend-only truth fallback for normal browse and require backend contracts for membership, order, totals, facets, derived values, and source/media status.

The second risk is letting Sprint 0 become documentation without enforcement. Recovery is to require baseline fixtures and at least one failing-or-pending test per contract before Sprint 1 starts, then close those tests during the relevant implementation sprint.

The third risk is treating status as a substitute for root fixes. Recovery is to require source immutability, media streaming/fallback policy, and stale selection clearing as code behavior, not just UI disclosure.

The fourth risk is overbuilding shared primitives. Recovery is to defer broad accessibility/menu/dialog primitive work until Phase 1 passes, and keep any immediate interaction fixes tied to current user workflows.

The fifth risk is performance regression from nicer UI. Recovery is to measure payload bytes, first grid, first thumbnail, frame gaps, query p95, request queue peaks, and RSS where relevant before accepting changes.

The sixth risk is URL bloat or parallel query identities. Recovery is to implement `analysisQueryKey` first, keep `windowRequestToken` separate, URL-own only reproducible Phase 1 analysis state, avoid vectors/transforms/large selections, and keep durable named/saved views backend-owned.

The seventh risk is source/media diagnostics leaking sensitive local paths or signed URLs. Recovery is to redact diagnostics based on trusted-local context and keep share clients on safe summaries.

The eighth risk is fixing viewer blanking by showing stale media as if it were current. Recovery is to enforce two-layer viewer state in tests: metadata moves to the target immediately, old decoded media is visually marked transitional, and failed target media shows a target-specific error.

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
- [x] 2026-06-10: First markdown verification confirmed the revised plan, review file, and all 12 agent reports are present under `docs/20260610_ux_ease_scan/`.
- [x] 2026-06-10: Integrated supplemental reviewer feedback from `docs/20260610_ux_ease_scan/20260610_reviewer_feedback.md`: added Sprint 0, split Sprint 3 into 3A/3B, tightened source dimension cache keys, backend media policy, streaming acceptance, selection boundaries, viewer state, derived score scope, and URL/localStorage precedence.
- [x] 2026-06-10: Final consistency check after integration confirmed no stale `S3-T*` task IDs, no old derived-score full-scope wording, and all review/report artifacts present under `docs/20260610_ux_ease_scan/`.
- [x] 2026-06-10: Sprint 0 completed. Added the Phase 1 ownership matrix, backend/frontend analysis query and window token helpers, original media policy/redaction contract, and baseline pending tests for source immutability, direct/proxy fallback, bounded metric sort, URL precedence, and folder-scope selection clearing.
- [x] 2026-06-10: Sprint 0 validation passed: focused pytest reported 28 passed and 3 expected xfails; focused Vitest reported 27 passed and 2 todo; targeted Ruff and `python scripts/lint_repo.py` passed. Cleanup gate applied Tier 1 local simplifications; review gate found one malformed-URL redaction issue, which was fixed and covered by test.
- [x] 2026-06-10: Sprint 1 partial, S1-T1 completed. Default table dimension caching now writes to a workspace cache, not source Parquet; source Parquet writes require explicit `--write-source-dimensions`/`--dimension-cache source`; `--no-write` falls back to temp workspace caching. Cache identity includes Parquet fingerprint, schema hash, row count, source/path/root/base-dir choices, workspace id, row index, normalized source, and logical path. Focused pytest, targeted Ruff, and `python scripts/lint_repo.py` passed. A broader `tests/storage/table` run still has three current formula-metric classification failures outside this S1-T1 slice.
- [x] 2026-06-10: Sprint 1 partial, S1-T2 and S1-T3 completed. Table health now exposes launch status with redacted base-dir/origin summaries, CLI table launches print source/media/dimension summaries, browse item payloads carry backend-owned original-media policy, HTTP/S3 proxy responses stream through `/file` with safe headers/range forwarding/max-byte enforcement, and viewer/compare/hover preview direct HTTP failures fall back per item/session to the backend proxy. Focused pytest, focused Vitest, frontend build, Playwright GUI acceptance, targeted Ruff, and `python scripts/lint_repo.py` passed. A broader `tests/web/routes/test_table_source_settings.py` run still exposes a null-only `q2` metric-key classification failure outside this slice.
- [x] 2026-06-10: Sprint 1 completed, S1-T4 and S1-T5 landed. Media loading now uses explicit resource/error states for thumbnails, hover preview, viewer, and compare; direct HTTP display still falls back per item while backend/proxy/decode failures surface typed error states and retry where reachable. Remote-not-found media failures now keep a distinct backend detail for frontend category mapping. User-triggered failures for table source switching, refresh, metadata export/download, clipboard, comparison export, inspector rating/bulk updates, and ranking save now surface through concise app or mode-local error banners instead of silent catches or `alert()`. Cleanup gate applied Tier 1 simplifications; review gate found stale action errors, unreachable hover retry, and compare divider z-index issues, all fixed and revalidated. Focused frontend/backend tests, frontend build with regenerated `src/lenslet/frontend/`, Playwright GUI acceptance, targeted Ruff, and `python scripts/lint_repo.py` passed. Full `npx tsc --noEmit` still fails on pre-existing derived-metric/metric-scrollbar type errors outside Sprint 1.
- [x] 2026-06-10: Sprint 2 completed, S2-T1 through S2-T5 landed. Folder scope changes now clear path-scoped selection/viewer/compare/context/similarity state while preserving explicit viewer hashes; sort/filter/search/layout changes request selection-first/top-anchor fallback restoration without page walking; viewer navigation keeps prior decoded media only as a dim transitional resource until the new target decodes and hides it on target error/unsupported; visible thumbnail demand is separated from adjacent prefetch; and the grid now distinguishes loading, updating, empty, failed, unsupported, and loading-more states with a bottom loaded/filtered sentinel and retry. Cleanup gate applied a Tier 1 dedupe in virtual-grid prefetch helpers. Review gate found pending-search false-empty and stale-error viewer media issues; both were fixed and rechecked. Focused Vitest, frontend build with regenerated `src/lenslet/frontend/`, Playwright GUI acceptance, and `python scripts/lint_repo.py` passed.
- [x] 2026-06-10: Sprint 3A completed, S3A-T1 through S3A-T4 landed. Browse query, facets, field capability metadata, URL state, and cache patching now share canonical analysis identity; facets accept query-shaped POST bodies, ignore offset/limit for population summaries, return count provenance, and use table row metadata without materializing image payloads. URL state now owns `q`, filters, sort, active random seed, derived metric spec, and unsupported metric intent; localStorage no longer restores analysis state and remains for personal display preferences. Cleanup gate applied a Tier 1 persistence cleanup. Review gate found unsupported-intent identity drift between URL, browse, and facets; fixes were applied and confirmed. Focused backend/frontend tests, frontend build with regenerated `src/lenslet/frontend/`, Playwright GUI acceptance, and `python scripts/lint_repo.py` passed.
- [x] 2026-06-10: Sprint 3B completed, S3B-T1 through S3B-T4 landed. Normal browse derived metrics now come from backend query evaluation, including item scores, applied/unavailable/invalid status, query-filtered score scope, valid/invalid counts, missing inputs, and z-normalization stats. Derived metric sorts and filters evaluate over the query-filtered population before offset/limit, while first pages stay bounded at the normal browse page size. Metric rail data now uses backend facet histograms for large/incomplete derived populations and disables jump semantics when only a summary is available; plain metric sorts no longer auto-trigger query-shaped facets just to draw the rail. Formula import fails closed for unavailable inputs, the card shows a score-preview histogram, and the action reads as sort-by-score. Review gate found an over-broad metric-sort facet fetch and a smoke test that could pass without observing the UI-triggered rank request; both were fixed and revalidated. Focused backend/frontend tests, frontend build with regenerated `src/lenslet/frontend/`, Playwright GUI acceptance, targeted Ruff, and `python scripts/lint_repo.py` passed. Full `npx tsc --noEmit` still fails only on the known out-of-scope `frontend/src/app/routing/__tests__/viewStateUrl.test.ts:123` arity issue.


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

Review artifacts:

- `docs/20260610_ux_ease_scan/20260610_lenslet_ux_improvement_plan_review.md`
- `docs/20260610_ux_ease_scan/20260610_reviewer_feedback.md`

Plan artifact:

- `docs/20260610_ux_ease_scan/20260610_lenslet_ux_improvement_plan.md`
- `docs/20260610_ux_ease_scan/phase1_contracts.md`

Sprint 0 implementation artifacts:

- Query identity: `src/lenslet/browse/query.py`, `frontend/src/api/folders.ts`
- Media policy: `src/lenslet/media_policy.py`
- Baseline contract tests: `tests/phase1/test_sprint0_baseline_contracts.py`
- Focused query/media tests: `tests/browse/test_query_evaluator.py`, `tests/web/routes/test_browse_query.py`, `tests/web/media/test_media_policy_contract.py`, `frontend/src/api/__tests__/folders.test.ts`
- Pending frontend contract markers: `frontend/src/app/routing/__tests__/viewStateUrl.test.ts`, `frontend/src/app/hooks/__tests__/useAppSelectionViewerCompare.test.ts`

Sprint 0 handoff: contract lock is complete. The next sprint is Sprint 1, starting with source Parquet immutability by default and workspace-backed dimension caching. Keep the Sprint 0 expected xfails/todos in place until the relevant implementation sprint closes them.

Sprint 1 partial handoff: S1-T1 is complete. Implementation artifacts include workspace dimension cache helpers, CLI dimension-cache policy flags, table-launch cache identity/load/write wiring, and focused source immutability tests. Remaining Sprint 1 tasks are S1-T2 through S1-T5. Validation note: `python scripts/lint_repo.py` and the S1-T1 focused suites pass. `pytest -q tests/storage/table` currently fails in formula-metric tests outside this slice (`pending_gpt_q4_value_view` and string `q10` classification).

Sprint 1 partial handoff: S1-T2 and S1-T3 are complete. Implementation artifacts include `TableLaunchStatus` and health payload mapping, CLI launch summaries, frontend launch-status propagation into settings, policy-gated original-media payloads, remote original streaming through `/file`, and per-session direct-image fallback in viewer, compare, and hover preview. Remaining Sprint 1 tasks are S1-T4 media error states and S1-T5 app-level action feedback. Validation note: focused backend/frontend checks, `npm run build`, Playwright GUI acceptance, and `python scripts/lint_repo.py` pass; a broader table-source route test still has an out-of-scope null-only `q2` metric-key expectation failure.

Sprint 1 handoff: Sprint 1 is complete. Implementation artifacts for S1-T4/S1-T5 include `frontend/src/lib/mediaResourceState.ts`, `frontend/src/shared/hooks/useBlobUrl.ts`, media error surfaces in `ThumbCard`, `VirtualGrid`, `Viewer`, and `CompareViewer`, app-level feedback in `GridTopStack`/`AppShell`, user-action reporting in context menu and inspector flows, ranking save-error display, and remote-not-found category preservation in `src/lenslet/web/media.py`. `src/lenslet/frontend/` was regenerated from `frontend/dist/`. Validation note: focused media/action feedback Vitest suites, `tests/web/media/test_media_error_contract.py`, targeted Ruff, frontend build, Playwright GUI acceptance, and `python scripts/lint_repo.py` pass. Full frontend typecheck still has known out-of-scope derived metric failures in `frontend/src/api/folders.ts`, `MetricScrollbar.tsx`, and `derivedMetric.test.ts`.

Sprint 2 handoff: Sprint 2 is complete. Implementation artifacts include folder-scope boundary handling in `frontend/src/app/AppShell.tsx` and `frontend/src/app/hooks/useAppSelectionViewerCompare.ts`, restore/status helpers in `frontend/src/app/model/loadingState.ts` and `frontend/src/app/utils/appShellHelpers.ts`, visible-demand thumbnail loading in `frontend/src/features/browse/model/virtualGridPrefetch.ts`, stable grid state/sentinel rendering in `frontend/src/features/browse/components/VirtualGrid.tsx`, and two-layer viewer presentation in `frontend/src/features/viewer/Viewer.tsx`. `src/lenslet/frontend/` was regenerated from `frontend/dist/`. Validation note: focused Sprint 2 Vitest suites, frontend build, Playwright GUI acceptance, and `python scripts/lint_repo.py` pass. The GUI smoke still emits the existing non-strict folder re-entry exact-anchor warning.

Sprint 3A handoff: Sprint 3A is complete. Implementation artifacts include backend analysis identity and unsupported-intent threading in `src/lenslet/browse/query.py` and `src/lenslet/web/routes/folders.py`, query-shaped facet/capability response construction in `src/lenslet/web/browse.py`, `src/lenslet/web/models.py`, and `src/lenslet/storage/table/facets.py`, frontend query/facet keying in `frontend/src/api/folders.ts` and `frontend/src/api/client.ts`, URL/localStorage ownership in `frontend/src/app/routing/viewStateUrl.ts`, `frontend/src/app/AppShell.tsx`, and `frontend/src/app/hooks/usePersistedAppShellSettings.ts`, and canonical query cache patching in `frontend/src/app/model/appShellStateSync.ts`. `src/lenslet/frontend/` was regenerated from `frontend/dist/`. Validation note: focused backend query/parquet tests, focused Vitest suites, frontend build, Playwright GUI acceptance, and `python scripts/lint_repo.py` pass. The GUI smoke still emits the existing non-strict folder re-entry exact-anchor warning.

Sprint 3B handoff: Sprint 3B is complete. Implementation artifacts include backend derived metric application/status in `src/lenslet/browse/query.py`, response payload mapping in `src/lenslet/web/browse.py` and `src/lenslet/web/models.py`, table query/facet metric-key propagation in `src/lenslet/storage/table/storage.py` and `src/lenslet/storage/table/facets.py`, backend-derived evaluation in `frontend/src/features/metrics/model/derivedMetric.ts`, bounded browse/facet query usage in `frontend/src/api/folders.ts` and `frontend/src/app/hooks/useAppDataScope.ts`, derived-only backend-summary metric rail rendering in `frontend/src/app/AppShell.tsx` and `frontend/src/features/browse/components/MetricScrollbar.tsx`, formula/import/preview polish in `frontend/src/features/metrics/model/derivedMetricDraft.ts` and `frontend/src/features/metrics/components/DerivedScoreCard.tsx`, and GUI smoke coverage in `scripts/browser/gui_smoke/scenarios.py`. `src/lenslet/frontend/` was regenerated from `frontend/dist/`. Validation note: focused backend query/table tests, focused Vitest suites, frontend build, Playwright GUI acceptance, targeted Ruff, and `python scripts/lint_repo.py` pass. Review gate findings were fixed: plain metric sorts no longer trigger automatic facet-summary scans, and the derived smoke now waits for the app's own UI-triggered `/folders/query` before checking bounded payload, top item, view state, and rail summary. Full `npx tsc --noEmit` still fails only on the known out-of-scope `frontend/src/app/routing/__tests__/viewStateUrl.test.ts:123` arity issue.
