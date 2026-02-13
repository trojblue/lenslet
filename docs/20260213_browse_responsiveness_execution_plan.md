# Lenslet Browse Responsiveness Execution Plan


## Outcome + Scope Lock


After implementation, running `lenslet <dir> --share` should remain simple, and opening the generated link should allow first useful browsing within 5 seconds on large recursive trees without freezes, browser request-exhaustion errors, or minute-long stalls.

Goals are to make root browsing responsive under large nested datasets, keep scrolling smooth while background loading continues, eliminate request fanout bursts, and avoid sort-order thrash during progressive discovery. The plan adopts a scan-stable fast-load ordering during active indexing and offers an explicit switch back to “Most recent” after indexing completes.

Non-goals are a full platform rewrite, distributed indexing infrastructure, broad visual redesign, and comprehensive Lighthouse optimization. Mobile work is intentionally minimal and limited to blocking issues that impact usability in this workflow.

Approvals are locked as follows. Pre-approved changes are progressive chunked root loading, request throttling/backpressure, a bounded browse cache with a 200 MB upper bound, minimal mobile hardening, and staged retirement of `legacy_recursive=1`. Changes that still require explicit sign-off are permanently changing final default sort semantics after indexing completion and any externally breaking API behavior for non-UI clients.

Deferred and out-of-scope items are large architectural migrations beyond local bounded caching, non-critical CSS polish, and speculative tuning not tied to measured regressions.


## Context


No `PLANS.md` was found in this repository. This file is the execution source-of-truth and follows the `docs/` planning conventions.

Current lagginess is caused by coupled hot paths. Frontend recursive hydration drains pages aggressively, backend recursive pagination repeats expensive traversal work, and thumbnail/file requests compete for the same browser/network resource pool. The observed result is freeze-prone root loading and `ERR_INSUFFICIENT_RESOURCES` under high-cardinality trees.

A key scope-lock decision is to decouple fast initial browse from “Most recent” sorting while indexing is incomplete. This removes reorder churn that conflicts with chunked loading and preserves user trust by only switching sort mode through explicit user action.


## Plan of Work


Scope budget is 4 sprints and 12 atomic tasks, touching only modules needed for this outcome: `frontend/src/app/hooks`, `frontend/src/features/browse`, `frontend/src/api`, `src/lenslet/server_browse.py`, new/updated browse cache helpers under `src/lenslet/`, and targeted tests under `tests/`.

Quality guardrail is minimum robust behavior, not overbuilt architecture and not fragile shortcuts. The quality floor requires deterministic page behavior, cancellation-safe fetches, bounded cache growth, and measurable responsiveness improvements. The maintainability floor requires explicit cache lifecycle ownership, restart-safe behavior, and validation per task. The complexity ceiling forbids introducing new service layers where in-process and local-disk bounded caching is sufficient.

Debloat/removal scope is mandatory. Implementation removes immediate full recursive hydration on first paint, removes duplicate eager thumbnail triggers, removes UI dependence on `legacy_recursive=1`, and removes only clearly obsolete mobile loading paths that block this flow. Net-change measurement is required through removed hot paths, reduced request fanout, and retained or smaller critical bundle/loading overhead.

Sprint Plan:

1. Sprint 1: Viewport-First Loading, Backpressure, and Instrumentation
   Goal: Make root browse interactive quickly and stop request storms before backend work scales up.
   Demo outcome: First thumbnails appear within target window and scroll remains responsive while background loading continues.
   Tasks:
   - T1. Implement progressive root hydration in `useAppDataScope` and `pagedFolder` so page 1 renders first and subsequent pages are scheduled incrementally. (Completed 2026-02-13)
   - T2. Add strict client-side in-flight request budgets for `/folders`, `/thumb`, and preview `/file`, including cancellation on scope changes. (Completed 2026-02-13)
   - T3. Consolidate thumbnail trigger paths so visible-load and prefetch do not duplicate fetch issuance for the same asset. (Completed 2026-02-13)
   - T4. Add instrumentation markers and counters for first-thumbnail latency, in-flight request counts, and hydration progress so acceptance criteria are machine-checkable. (Completed 2026-02-13)

2. Sprint 2: Backend Recursive Caching and Deterministic Paging
   Goal: Remove repeated recursive recomputation and support fast repeat browsing on the same dataset.
   Demo outcome: Recursive pages are served from deterministic bounded cache/index windows with measurable latency reduction.
   Tasks:
   - T5. Implement in-memory recursive window cache keyed by scope plus sort mode, with deterministic slicing semantics for page windows. (Completed 2026-02-13)
   - T6. Add optional persisted browse cache for relaunch reuse with explicit location, schema/version marker, permission-safe fallback, and enforced 200 MB cap plus eviction policy. (Completed 2026-02-13)
   - T7. Add invalidation/rebuild rules tied to refresh/index changes and stale generation detection to avoid mixed-window corruption. (Completed 2026-02-13)

3. Sprint 3: Stable Ordering UX and Legacy Recursive Retirement
   Goal: Keep ordering stable during progressive discovery and remove problematic legacy recursive path safely.
   Demo outcome: Users browse in scan-stable mode during indexing and are prompted to switch to “Most recent” only after completion.
   Tasks:
   - T8. Define and implement indexing-complete signal contract from backend to UI, including generation ID so completion state is deterministic across reloads. (Completed 2026-02-13)
   - T9. Implement scan-stable mode plus completion banner behavior with explicit user action to switch to “Most recent,” including persistence of banner dismissal and deterministic reset behavior after mode switch. (Completed 2026-02-13)
   - T10. Inventory `legacy_recursive=1` consumers, remove UI emission, run compatibility validation for explicit non-UI callers, and then hard-restrict/remove server legacy path behind a rollback flag. (Completed 2026-02-13)

4. Sprint 4: Minimal Mobile Hardening and Final Regression Lock
   Goal: Keep mobile workflow usable without broad redesign and lock in regression protection.
   Demo outcome: Mobile root browse no longer hits major blocking behavior for this flow, and perf regressions are catchable.
   Tasks:
   - T11. Apply only highest-impact mobile tweaks for this workflow: targeted render-blocker reduction and minimal legacy mobile asset removal that has direct measured benefit.
   - T12. Add a focused large-tree perf smoke harness and targeted regression tests that assert request-budget compliance, cache-cap compliance, and responsiveness thresholds.

Implementation instructions are mandatory during execution. While implementing each sprint, update this plan continuously, especially `Progress Log` and all affected sections, and append clear handoff notes immediately after each sprint completes. For minor script-level uncertainties such as exact helper placement, proceed per approved scope to maintain momentum, then ask for clarification after the sprint and apply follow-up adjustments.


## Interfaces and Dependencies


The `/folders` recursive API remains paginated and deterministic, but backend internals will move from repeated traversal-heavy page generation to cache/index-backed window serving. The UI dataflow will move from eager full recursive hydration to progressive bounded hydration with explicit completion signaling.

Persisted browse cache dependency is local writable workspace storage. The implementation must define cache path ownership, permissions fallback when write is unavailable, schema/version invalidation on format changes, and strict 200 MB size enforcement.

`legacy_recursive=1` retirement has compatibility dependencies. The plan requires explicit consumer inventory, staged restriction/removal, and rollback gating so non-UI callers are not silently broken.


## Validation and Acceptance


Each sprint has concrete behavior validation and expected outcomes.

1. Sprint 1 validation
   - Validate progressive render path and request budgets with automated assertions and manual large-tree scenario.
   - Expected outcome: first thumbnails visible within 5 seconds on local no-throttle run, no freeze during initial scroll, and no `ERR_INSUFFICIENT_RESOURCES`.
   - Iteration 1 evidence (2026-02-13): `npm --prefix frontend test` passed (38 test files / 180 tests) and `pytest -q tests/test_folder_pagination.py tests/test_hotpath_sprint_s4.py` passed (15 tests).

      npm --prefix frontend test
      pytest -q tests/test_folder_pagination.py tests/test_hotpath_sprint_s4.py

2. Sprint 2 validation
   - Validate deterministic recursive page windows before/after cache and measure repeat-page latency improvement.
   - Validate persisted cache restart behavior and hard 200 MB cap with enforced eviction.
   - Expected outcome: repeated recursive paging avoids prior cumulative stall behavior and cache never exceeds budget.
   - Iteration 2 evidence (2026-02-13): recursive cache regression slice passed across pagination, refresh invalidation, and cap enforcement checks.

      pytest -q tests/test_folder_pagination.py tests/test_memory_index_performance.py
      pytest -q --durations=10 tests/test_folder_pagination.py tests/test_hotpath_sprint_s4.py
      pytest -q tests/test_refresh.py tests/test_browse_cache.py

3. Sprint 3 validation
   - Validate indexing-complete signal and banner lifecycle across reloads.
   - Validate scan-stable mode does not reorder already loaded windows mid-indexing.
   - Validate `legacy_recursive=1` is absent from UI path and server restriction/removal behavior is covered.
   - Iteration 4 evidence (2026-02-13): generation-aware health + scan-stable mode contract tests passed in frontend vitest slice and backend pagination/refresh/indexing contract checks passed.

      npm --prefix frontend test -- src/app/model/__tests__/indexingBrowseMode.test.ts src/app/components/__tests__/StatusBar.test.tsx src/api/__tests__/folders.test.ts src/app/hooks/__tests__/healthIndexing.test.ts
      pytest -q tests/test_folder_pagination.py tests/test_refresh.py tests/test_hotpath_sprint_s4.py tests/test_indexing_health_contract.py

4. Sprint 4 validation
   - Validate minimal mobile hardening outcomes against the root browse flow only.
   - Validate perf smoke harness and regression checks for request-budget and cache-cap constraints.
   - Expected outcome: mobile flow is usable and major regressions are caught before release.

      npm --prefix frontend run build
      pytest -q

Overall acceptance is achieved when all sprint validations pass, first useful browse on large recursive roots is consistently within 5 seconds, scroll remains responsive during background hydration, and prior freeze/error symptoms are no longer reproducible in the target scenario.


## Risks and Recovery


The highest risk is cache invalidation errors that can create missing or duplicated page windows. Recovery is feature-gated fallback to the current traversal path, targeted cache clear, and generation-aware rebuild.

Another risk is compatibility breakage from `legacy_recursive=1` retirement. Recovery is staged rollout with explicit consumer validation and a short-lived rollback flag.

A third risk is over-throttling that slows perceived scrolling. Recovery is bounded tuning via config constants and rollback of only throttle values, not the progressive architecture.

Idempotent retry strategy is required for cache/index refresh. Rebuild operations must be restart-safe, repeat-safe, and schema-version aware so failed attempts can be retried without corrupting prior cache state.


## Progress Log


- [x] 2026-02-13 00:00Z Scope lock confirmed with user: chunking approved, 200 MB cache cap approved, staged legacy recursive retirement approved, minimal mobile hardening approved, responsiveness targets defined.
- [x] 2026-02-13 00:00Z Initial plan drafted with 4-sprint scope and explicit guardrails.
- [x] 2026-02-13 00:00Z Required subagent review completed; plan updated to split oversized cache work, add instrumentation, define completion-signal contract, and add explicit compatibility retirement steps.
- [x] 2026-02-13 18:29Z Sprint 1 tasks T1-T4 implemented: incremental recursive hydration pacing, endpoint request budgets/cancellation, adjacent-row-only thumb prefetch, and machine-checkable browse hotpath telemetry.
- [x] 2026-02-13 18:30Z Sprint 1 validation completed: frontend vitest suite and targeted backend pytest hotpath/pagination checks passed.
- [x] 2026-02-13 18:31Z Sprint 1 handoff notes appended after implementation.
- [x] 2026-02-13 18:40Z Sprint 2 tasks T5-T7 implemented: recursive window cache now serves deterministic slices from in-memory snapshots with persisted relaunch reuse, workspace-owned browse cache location, and 200 MB eviction guardrails.
- [x] 2026-02-13 18:40Z Sprint 2 validation completed: targeted recursive pagination, refresh invalidation, and hotpath regression checks passed.
- [x] 2026-02-13 18:41Z Sprint 2 handoff notes appended after implementation.
- [x] 2026-02-13 18:50Z Sprint 3 tasks T8-T10 implemented: indexing health payload now includes deterministic generation IDs, scan-stable ordering stays active until explicit switch, and UI legacy recursive requests were removed.
- [x] 2026-02-13 18:50Z Sprint 3 validation completed: frontend indexing/legacy query tests and backend recursive compatibility checks passed.
- [x] 2026-02-13 18:50Z Sprint 3 handoff notes appended after implementation.
- [ ] 2026-02-13 00:00Z Sprint 4 handoff notes appended after implementation.


## Artifacts and Handoff


Primary execution artifact is `docs/20260213_browse_responsiveness_execution_plan.md`.

Diagnosis references are `docs/20260213_pagespeed_insights_mobile.md`, `tests/test_folder_pagination.py`, and `tests/test_hotpath_sprint_s4.py`.

Investigation baseline snippet for large synthetic recursive tree:

    warmup page1=6.479s total_pages=250
    drain_all_pages pages=250 total_time=70.817s avg_per_page=0.283s max_page=0.366s

Handoff guidance for implementation is to execute sprints in order, keep edits constrained to listed modules, and update this plan continuously as implementation evidence is collected.

Revision note (2026-02-13): Updated after required subagent review to reduce scope-creep risk, split oversized backend tasks, add explicit measurement tasks, and harden compatibility/removal sequencing for `legacy_recursive=1`.

Sprint 1 handoff notes (2026-02-13):
- Progressive hydration now updates incrementally with inter-page pacing and emits progress snapshots from `hydrateFolderPages`.
- Request backpressure now routes `/folders`, `/thumb`, and `/file` through endpoint budgets with explicit queueing and abort-on-scope-change wiring.
- Thumbnail prefetch was narrowed to rows adjacent to the viewport so visible cards and prefetchers no longer compete for the same thumbnail paths.
- Machine-checkable telemetry is now exposed via `window.__lensletBrowseHotpath` and performance markers for hydration start/complete and first-thumbnail latency.

Sprint 2 handoff notes (2026-02-13):
- Recursive `/folders` responses now route through `RecursiveBrowseCache` snapshots keyed by scope, sort mode, and storage generation token, so adjacent page requests avoid repeated subtree recomputation.
- Persisted browse cache entries now live in workspace-owned `browse-cache` directories with schema-version validation and permission-safe fallback to memory-only mode.
- Persisted cache eviction now enforces the 200 MB cap by pruning oldest cache artifacts after writes.
- Refresh now invalidates recursive browse cache state and storage generation tokens so ancestor scopes rebuild deterministically after subtree changes.

Sprint 3 handoff notes (2026-02-13):
- `/health` indexing payloads now include a generation token derived from storage cache signature + browse generation so UI completion state is deterministic across reloads and refreshes.
- Scan-stable ordering now pins loaded windows while generation indexing is active and shows an explicit completion banner that requires a user click to switch back to “Most recent.”
- Scan-stable dismissal now persists by generation in local storage and resets deterministically when a new generation starts indexing.
- UI folder fetch paths no longer emit `legacy_recursive=1`; metadata export now drains recursive pages through paginated requests.
- Server legacy recursive mode is now retired by default with a clear 400 response and a temporary rollback gate via `LENSLET_ENABLE_LEGACY_RECURSIVE_ROLLBACK=1` for explicit non-UI callers.
