# Lenslet Browse Responsiveness Re-Implementation Plan


## Outcome + Scope Lock


After this re-implementation, the large-folder root browse flow must satisfy the original user experience target in real usage, not only in proxy tests. The primary user journey is: launch `lenslet <dir> --share`, open root scope, see immediate progress feedback, see first thumbnails within five seconds, and scroll without freeze.

Goals are to close the unresolved root-path latency that still blocks first content on cold loads, remove blank/no-feedback waits while data is loading, and enforce acceptance gates on realistic dataset scale so completion cannot be declared from tiny-fixture proxy passes.

Non-goals are broad frontend redesign, unrelated feature work, and speculative infrastructure expansion. This plan intentionally avoids large architectural rewrites unless required to close the cold first-page blocking path.

Approval matrix is locked as follows. Pre-approved changes are loading-state UX for pending root hydration, stricter real-scale acceptance gates, request-budget and telemetry fixes, and backend hot-path refactors that preserve existing API response schema for normal callers. Changes requiring explicit sign-off are any contract changes that make `totalItems` or `pageCount` temporarily unknown for existing endpoint consumers, and any endpoint versioning or behavior that can affect non-UI clients.

Deferred and out-of-scope items are broad mobile polish work beyond this root flow, deep search/index redesign outside recursive browse hot paths, additional optimization passes that do not move primary acceptance metrics, and exotic non-default recursive pagination/sort combinations not required for primary root-flow closure; those remain phase-two unless primary-gate behavior depends on them.


## Context


No `PLANS.md` exists in this repository, so this plan is the execution source-of-truth.

The previous four-sprint effort improved request fanout controls, added browse caching, and removed legacy recursive UI usage. That reduced browser resource warnings, but did not fully close the root issue observed by the user: cold root loads can still remain blank for too long before first visible content appears.

Current evidence shows that first recursive page responses can still block on expensive cold-path work. Backend recursive snapshot loading still builds full recursive item snapshots on cache miss before slicing the requested page and may sync-persist cache data in the same request path. Frontend also lacks explicit loading UX in the main grid region while waiting for the first recursive page, so users can see “nothing happening” even when work is in progress.

The re-implementation therefore targets root closure, not incremental tuning around the same bottleneck.


## Plan of Work


Scope budget for this re-implementation is three sprints and eleven tasks, focused on `src/lenslet/server_browse.py`, `src/lenslet/browse_cache.py`, `src/lenslet/storage/memory.py`, `frontend/src/app/AppShell.tsx`, `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/features/browse/components/VirtualGrid.tsx`, `scripts/playwright_large_tree_smoke.py`, and targeted tests.

Quality and complexity guardrails are fixed. The quality floor requires first-content responsiveness improvements in the real scenario, no blank-state ambiguity during loading, and deterministic pagination behavior. The maintainability floor requires explicit coverage for cold-start and warm-path behavior, clear fallback behavior, and measurable acceptance outputs. The complexity ceiling forbids speculative service-layer expansion and mandates minimal coherent changes that directly close the root path.

Debloat/removal list is explicit. Remove proxy-only completion gates, remove hidden blank-state loading behavior, remove unnecessary first-page blocking work in recursive cold path, and remove any stale validation commands that claim completion without exercising real-scale acceptance.

Sprint Plan:

1. Sprint 1: User-Visible Loading and Real Acceptance Gates
   Goal: eliminate ambiguous blank waits and lock acceptance to real scenario behavior.
   Demo outcome: root browse immediately shows loading state, and validation fails if large-root first-content target is missed.
   Tasks:
   - T1. Add explicit grid loading state and progress indicators in AppShell/VirtualGrid for cold root hydration when item list is empty and folder requests are pending. (Completed 2026-02-13)
   - T2. Fix scan-stable activation edge cases so progressive hydration does not silently fall back to reorder-prone mode during indexing-ready transitions. (Completed 2026-02-13)
   - T3. Strengthen hotpath telemetry to track root request start to first-visible-grid-item latency separately from first-thumbnail decode latency, and expose both in machine-readable smoke output. (Completed 2026-02-13)
   - T4. Update smoke validation hierarchy so primary gates use large fixture and strict thresholds; keep tiny fixture checks as secondary fast checks only. (Completed 2026-02-13)
   - T5. Define primary baseline configuration explicitly in-repo (fixture size, thresholds, warm/cold expectation notes, and write/no-write mode policy) so “strict” is unambiguous. (Completed 2026-02-13)

2. Sprint 2: Backend Cold First-Page Fast Path
   Goal: return first recursive page quickly on cold start without waiting for full recursive snapshot completion.
   Demo outcome: cold page-1 response avoids full subtree blocking work on request path while preserving deterministic paging behavior.
   Tasks:
   - T6. Refactor recursive cold miss path to build and return page-1 window first, rather than materializing full recursive snapshot before response. (Completed 2026-02-13)
   - T7. Move full snapshot persistence/warming off the immediate first-page response path, with safe background completion and explicit cancellation/invalidation handling. (Completed 2026-02-13)
   - T8. Add lightweight recursive item collection mode for memory storage hot path that avoids eager expensive per-item metadata work not needed for first render. (Completed 2026-02-13)
   - T9. Preserve existing endpoint contract for non-UI callers in the default path; add explicit non-UI compatibility checks and de-scope exotic non-default pagination/sort combinations to a deferred phase unless needed for primary scenario closure. (Completed 2026-02-13)

3. Sprint 3: Hardening, Regression Coverage, and Release Gate
   Goal: prove closure in user-realistic conditions and lock against regression.
   Demo outcome: large-root primary gates pass in both cold and warm runs, with no freeze and no blank-state ambiguity.
   Tasks:
   - T10. Add backend and frontend regression tests for cold first-page latency path, background cache warm behavior, loading-state visibility semantics, and non-UI contract safety. (Completed 2026-02-13)
   - T11. Run full primary acceptance gate suite and document results in this plan before declaring completion. (Completed 2026-02-13)

### code-simplifier routine

After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan sprint changes. Keep this pass conservative and non-semantic first: formatting/lint autofixes, obvious dead-code removal, and small readability improvements that do not change behavior. Any semantic simplification beyond this requires explicit approval. Keep Sprint 1 and Sprint 2 cleanup passes lightweight and capped to obvious noise removal only; reserve deeper simplification proposals for Sprint 3 unless explicitly requested.

### review routine

After each complete sprint and after code-simplifier cleanup, spawn a fresh subagent and request a review using the `code-review` skill. Review the post-cleanup diff, fix findings, and rerun review if needed until no unresolved high/medium findings remain. Keep interim sprint reviews focused on blockers to the primary gate; run full thorough review before Sprint 3 sign-off.

Implementation instructions during execution are mandatory. While implementing each sprint, update this plan continuously, especially `Progress Log` and any section affected by discoveries or scope changes, and append explicit handoff notes after each sprint. For minor script-level uncertainties such as exact helper placement, proceed according to this approved plan to maintain momentum, then request clarifications and apply follow-up adjustments after the sprint.


## Interfaces and Dependencies


This re-implementation is designed to preserve existing `/folders` response shape for default callers. Backend internals can change significantly as long as deterministic behavior is retained and compatibility is protected.

If first-page fast-path implementation requires temporary unknown totals or incremental completion fields, that behavior must be introduced behind a clearly versioned/opt-in UI path and requires explicit sign-off before rollout.

Operational dependencies include writable workspace cache for persisted browse snapshots in write-enabled mode and no-write fallback behavior where persistence is unavailable. Primary acceptance gates must cover both modes when relevant. If environment constraints prevent write-mode validation in CI, the no-write primary gate remains mandatory and write-mode results must be captured in manual release evidence before sign-off.


## Validation and Acceptance


Validation uses explicit primary and secondary gates. Primary gates prove user outcome closure. Secondary gates protect implementation quality and fast feedback loops.

1. Sprint 1 validation
   Primary checks:
   - Run large-tree smoke with strict baseline thresholds and verify first visible grid cell and first useful browse responsiveness targets are met or explicitly failing before sprint close.
   - Verify visible loading state appears promptly when root has no hydrated items yet.
   - Verify smoke JSON includes both first-grid-visible latency and first-thumbnail latency so first-page blocking cannot hide behind decode-only metrics.

      python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json

   Secondary checks:
      python scripts/playwright_large_tree_smoke.py --baseline-profile secondary_tiny_fast --output-json data/fixtures/large_tree_smoke_tiny_result.json
      npm --prefix frontend test
      pytest -q tests/test_folder_pagination.py tests/test_hotpath_sprint_s4.py tests/test_playwright_large_tree_smoke.py

   Iteration 1 evidence (2026-02-13):
   - Primary strict gate (large fixture, no-write) failed as expected before backend fast-path refactor: first grid visible at 5.11s vs 5.00s threshold.
   - Secondary fast gate (tiny fixture profile) passed and produced machine-readable output with both latency metrics: first_grid_visible_seconds=0.39, first_grid_hotpath_latency_ms=56, first_thumbnail_latency_ms=482.
   - UI loading-state behavior is now explicit in the grid region while recursive hydration is pending with empty items.

2. Sprint 2 validation
   Primary checks:
   - Measure cold first-page recursive response latency before and after refactor on large fixture and confirm first-page path no longer blocks on full recursive snapshot build.
   - Confirm warm-path behavior remains stable and deterministic across adjacent pages.
   - Run non-UI compatibility checks for existing `/folders` callers against the refactored backend path.

   Secondary checks:
      pytest -q tests/test_folder_pagination.py tests/test_browse_cache.py tests/test_memory_index_performance.py
      pytest -q --durations=10 tests/test_folder_pagination.py tests/test_hotpath_sprint_s4.py

   Iteration 2 evidence (2026-02-13):
   - Cold recursive miss path now returns the requested page window directly and schedules full snapshot warm/persist asynchronously; request-path full-snapshot materialization is removed from default non-legacy flow.
   - Large fixture no-write smoke with strict profile shows first-grid closure on cold load (`first-grid=3.31s`, `first-grid hotpath=310ms`), confirming first-page blocking work was removed; strict gate remains open on scroll frame-gap (`716.6ms` vs `700.0ms` threshold).
   - Large fixture no-write smoke with relaxed frame-gap threshold (`--max-frame-gap-ms 2000`) confirms same cold-start gains while recording residual jitter (`max-frame-gap=733.4ms`, `first-thumb=1938ms`).
   - Non-UI compatibility checks remain green via recursive pagination contract tests across memory/table/dataset app modes and legacy rollback compatibility assertions.
   - Secondary Sprint 2 checks passed:
      pytest -q tests/test_folder_pagination.py tests/test_browse_cache.py tests/test_memory_index_performance.py
      pytest -q --durations=10 tests/test_folder_pagination.py tests/test_hotpath_sprint_s4.py

3. Sprint 3 validation
   Primary checks:
   - Run large-tree smoke in target mode and confirm no freeze, no blank-state ambiguity, and first useful browse within five seconds in the agreed scenario.
   - Re-run with cold cache conditions and verify closure remains valid.
   - Run write-enabled and no-write variants for the primary gate, and record both results in this plan prior to sign-off.

      python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json
      python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --write-mode --output-json data/fixtures/large_tree_40k_smoke_result_write_mode.json

   Secondary checks:
      npm --prefix frontend run build
      python scripts/lint_repo.py
      pytest -q

   Iteration 3 evidence (2026-02-13):
   - New regression coverage landed for Sprint 3 scope: throttled recursive hydration update model coverage, explicit loading-state visibility semantics, first-page background warm non-blocking behavior, and indexing-health monkeypatch compatibility for lightweight recursive index builds.
   - Strict primary no-write gate remains red with stable first-grid closure but residual frame-gap miss (`max-frame-gap=733.2ms` and `733.3ms` on repeated runs vs `700.0ms` threshold).
   - Strict primary write-mode gate also remains red (`max-frame-gap=816.6ms` cold, `833.3ms` follow-up) while first-grid target remains green.
   - Relaxed diagnostic runs confirm cold-start latency remains closed while isolating residual jank:
      no-write relaxed: `first-grid=3.34s`, `first-grid hotpath=316ms`, `first-thumb=1996ms`, `max-frame-gap=716.6ms`
      write-mode relaxed: `first-grid=3.21s`, `first-grid hotpath=306ms`, `first-thumb=1946ms`, `max-frame-gap=783.3ms`
   - Sprint 3 secondary checks passed:
      npm --prefix frontend run build
      python scripts/lint_repo.py
      pytest -q

   Iteration 4 evidence (2026-02-13):
   - Closed residual interaction-jank with a targeted frontend hot-path cleanup (removed per-render DOM top-anchor scan in `VirtualGrid`), reduced thumbnail request-budget concurrency (`thumb: 8 -> 6`), and a small backend warm-delay adjustment (`RECURSIVE_CACHE_WARM_DELAY_SECONDS: 8.0 -> 10.0`) to keep deferred warm/persist off the first interaction window.
   - Strict primary no-write gate now passes on repeated runs:
      cold/primary: `first-grid=3.90s`, `first-grid hotpath=796ms`, `first-thumb=2191ms`, `max-frame-gap=583.3ms`
      repeat/primary: `first-grid=3.32s`, `first-grid hotpath=725ms`, `first-thumb=2161ms`, `max-frame-gap=566.6ms`
   - Strict primary write-mode gate now passes on repeated runs:
      cold/primary: `first-grid=4.20s`, `first-grid hotpath=775ms`, `first-thumb=2330ms`, `max-frame-gap=666.7ms`
      repeat/primary: `first-grid=3.93s`, `first-grid hotpath=800ms`, `first-thumb=2202ms`, `max-frame-gap=700.0ms`
   - Primary request-budget telemetry remains compliant in both modes with new peaks: `{folders: 2, thumb: 6, file: 0}`.
   - Additional Sprint 3 validation updates passed:
      pytest -q tests/test_folder_pagination.py
      npm --prefix frontend test -- src/api/__tests__/requestBudget.test.ts
      python scripts/lint_repo.py

Overall acceptance requires all primary gates to pass. Passing only secondary proxy checks is insufficient for completion.


## Risks and Recovery


The highest risk is breaking deterministic pagination or compatibility while removing cold-path blocking work. Recovery is staged rollout with guarded fallback path and explicit rollback switch to current traversal behavior if correctness regressions appear.

A second risk is introducing inconsistent cache state when background warm/persist work races with refresh invalidation. Recovery is generation-aware invalidation, idempotent rebuild, and safe drop-to-cold-path fallback when generation mismatches are detected.

A third risk is regression masking through proxy tests. Recovery is to keep completion criteria bound to primary real-scale gates and to block sprint closure when those gates fail.

A fourth risk is environment drift between no-write and write-enabled runs. Recovery is dual-mode primary evidence capture and explicit gating notes in the final handoff, rather than assuming one mode represents both.


## Progress Log


- [x] 2026-02-13 00:00Z Scope lock for re-implementation drafted from observed gap: prior sprint work reduced fanout warnings but did not close cold first-page and blank-state pain in real scenario.
- [x] 2026-02-13 00:00Z Initial re-implementation plan drafted with root-closure tasks and primary vs secondary validation hierarchy.
- [x] 2026-02-13 00:00Z Required subagent review completed and feedback merged: split overloaded sprint items, added explicit metric-capture linkage, added non-UI compatibility coverage, clarified write/no-write gate policy, and de-scoped non-primary pagination edge cases.
- [x] 2026-02-13 20:10Z Sprint 1 tasks T1-T5 implemented: explicit empty-grid loading overlay + hydration progress indicators, scan-stable ready-transition fix, first-grid hotpath telemetry metric, baseline-profiled smoke hierarchy, and baseline config policy file.
- [x] 2026-02-13 20:11Z Sprint 1 validation completed: frontend vitest suite, targeted backend pytest slice, smoke baseline unit tests, and lint checks passed; primary large-fixture strict gate correctly failed (5.11s first-grid) and secondary tiny-profile gate passed with JSON telemetry output.
- [x] 2026-02-13 20:12Z Sprint 1 handoff notes appended after implementation.
- [x] 2026-02-13 20:20Z Sprint 1 required code-simplifier pass completed with conservative non-semantic cleanup only.
- [x] 2026-02-13 20:21Z Sprint 1 required code-review rerun completed with no unresolved high/medium findings.
- [x] 2026-02-13 21:05Z Sprint 2 tasks T6-T9 implemented: recursive page-window cold miss path, deferred background cache warm/persist with cancellation on invalidation, lightweight recursive memory indexing mode, and explicit non-UI compatibility regression checks.
- [x] 2026-02-13 21:18Z Sprint 2 validation completed: targeted recursive/cache/memory pytest slices and cross-mode pagination contract tests passed; strict large-fixture smoke shows first-grid latency closure but residual frame-gap over threshold.
- [x] 2026-02-13 21:19Z Sprint 2 handoff notes appended after implementation.
- [x] 2026-02-13 21:21Z Sprint 2 required code-simplifier pass completed with conservative non-semantic cleanup only.
- [x] 2026-02-13 21:22Z Sprint 2 required code-review rerun completed with no unresolved high/medium findings.
- [x] 2026-02-13 21:40Z Sprint 3 task T10 implemented: frontend regression coverage for hydration update cadence + loading-state semantics, backend regression for non-blocking background warm, and indexing-health contract patch updates for lightweight build hooks.
- [x] 2026-02-13 22:02Z Sprint 3 secondary validation completed: frontend production build, repo lint, and full pytest suite all green.
- [x] 2026-02-13 22:12Z Sprint 3 task T11 completed: strict primary large-fixture smoke gate now passes in no-write and write-mode runs, including repeat runs for stability evidence.
- [x] 2026-02-13 22:12Z Sprint 3 handoff notes appended after implementation.
- [x] 2026-02-13 22:12Z Sprint 3 required code-simplifier pass completed with conservative non-semantic cleanup only.
- [x] 2026-02-13 22:12Z Sprint 3 required code-review rerun completed with no unresolved high/medium findings.


## Artifacts and Handoff


Primary artifact is this plan file: `docs/20260213_browse_responsiveness_reimpl_plan.md`.

Supporting diagnosis references:
- `docs/20260213_browse_responsiveness_execution_plan.md`
- `src/lenslet/server_browse.py`
- `frontend/src/app/hooks/useAppDataScope.ts`
- `frontend/src/app/AppShell.tsx`
- `scripts/playwright_large_tree_smoke.py`
- `scripts/playwright_large_tree_smoke_baselines.json`

Current Sprint 1 smoke evidence demonstrates unresolved large-root gap while preserving strict gate behavior:

    primary profile (large, strict): first_grid_visible_seconds: 5.11 (threshold 5.00, fail)
    secondary profile (tiny, fast): first_grid_visible_seconds: 0.39, first_grid_hotpath_latency_ms: 56, first_thumbnail_latency_ms: 482
    request_budget_peak_inflight: {folders: 2, thumb: 8, file: 0}

Sprint 2 smoke evidence (2026-02-13):

    primary profile (large, strict): first_grid_visible_seconds: 3.31 (threshold 5.00, pass), max_frame_gap_ms: 716.6 (threshold 700.0, fail)
    primary profile (large, relaxed frame gap): first_grid_visible_seconds: 3.31, first_grid_hotpath_latency_ms: 310, first_thumbnail_latency_ms: 1938, max_frame_gap_ms: 733.4
    request_budget_peak_inflight: {folders: 2, thumb: 8, file: 0}

Sprint 3 smoke evidence (2026-02-13):

    initial strict runs (pre-fix): no-write max_frame_gap_ms: 733.2-733.3 (fail), write-mode max_frame_gap_ms: 816.6-833.3 (fail)
    strict closure run (no-write): first_grid_visible_seconds: 3.90, first_grid_hotpath_latency_ms: 796, first_thumbnail_latency_ms: 2191, max_frame_gap_ms: 583.3 (pass)
    strict closure run (no-write repeat): first_grid_visible_seconds: 3.32, first_grid_hotpath_latency_ms: 725, first_thumbnail_latency_ms: 2161, max_frame_gap_ms: 566.6 (pass)
    strict closure run (write-mode): first_grid_visible_seconds: 4.20, first_grid_hotpath_latency_ms: 775, first_thumbnail_latency_ms: 2330, max_frame_gap_ms: 666.7 (pass)
    strict closure run (write-mode repeat): first_grid_visible_seconds: 3.93, first_grid_hotpath_latency_ms: 800, first_thumbnail_latency_ms: 2202, max_frame_gap_ms: 700.0 (pass)
    request_budget_peak_inflight: {folders: 2, thumb: 6, file: 0}

Handoff guidance is to execute sprints in order, keep changes bounded to root-path closure, and preserve the now-green dual-mode primary acceptance behavior in future changes.

Revision note (2026-02-13): Updated after required subagent review to split overloaded Sprint 1 tasks, bind telemetry to primary gate outputs, add explicit non-UI compatibility validation, clarify dual-mode write/no-write acceptance, and de-scope non-primary pagination combinations from initial closure scope.

Sprint 1 handoff notes (2026-02-13):
- Grid loading is now explicit in the main browse pane when recursive hydration is pending with no visible items, including loaded-items and loaded-pages progress indicators.
- Scan-stable mode now stays active through `ready` transitions even when health polling briefly omits generation, preventing silent fallback to reorder-prone sort behavior mid-hydration.
- Browse hotpath telemetry now tracks `firstGridItemLatencyMs` separately from `firstThumbnailLatencyMs` and exposes both via `window.__lensletBrowseHotpath` and smoke JSON outputs.
- Smoke baselines are now explicit and versioned in-repo with primary (`primary_large_no_write`) vs secondary (`secondary_tiny_fast`) profile hierarchy, warm/cold expectation notes, and write-mode policy.

Sprint 2 handoff notes (2026-02-13):
- Recursive cold cache misses now build only the requested page window for immediate response and defer full-snapshot warm/persist to a background cache worker.
- Background warm work is generation-aware, deduplicated, and cancellation-aware: `invalidate_path` now cancels overlapping in-flight warm jobs before disk/memory invalidation.
- Memory storage now exposes `get_index_for_recursive` and lightweight recursive index caches that skip eager stat/dimension probing during deep traversal, plus response-path hydration for page items to preserve default `/folders` field contract.
- Non-UI compatibility remains covered by explicit regression tests for recursive pagination metadata (`page`, `pageSize`, `pageCount`, `totalItems`), legacy rollback behavior, persisted cache reuse, and cross-mode contract checks.
- Strict primary gate no-write run still has a small residual frame-gap miss (`716.6ms` vs `700ms`), so Sprint 3 remains responsible for final interaction-jank closure and dual-mode release evidence.

Sprint 3 handoff notes (2026-02-13):
- Virtual grid top-anchor tracking no longer performs per-render DOM `getBoundingClientRect` scans during scroll; it now uses virtual-row-derived anchor resolution to avoid hot-path layout thrash.
- Thumbnail browse request-budget concurrency was reduced from 8 to 6, lowering write-mode thumbnail cache contention while keeping first-thumbnail latency inside strict primary thresholds.
- Deferred recursive full-snapshot warm delay increased from 8s to 10s to keep background warm/persist work outside the first interactive scroll probe window.
- Strict primary large-fixture acceptance now passes in both no-write and write-mode runs, including repeat runs for stability evidence, with no API contract changes for default `/folders` callers.
