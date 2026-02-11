# Foundational Refactor and Performance Plan for Longest Core Files


## Purpose / Big Picture


No `PLANS.md` (or equivalent canonical planning file) exists in this repository, so this document is the canonical execution plan for this change set. After implementation, users should see unchanged Lenslet behavior and API contracts, but with materially better maintainability and targeted runtime speedups in hot paths. The redesign assumes modular boundaries and performance budgets were first-day assumptions, not retrofit constraints.

This plan now explicitly allows bold internal refactors and algorithmic optimizations. The guardrail is strict behavioral parity at public interfaces: same endpoints, same payload contracts, same user-visible semantics, same workspace data model, and no broad product-scope changes.


## Progress


- [x] 2026-02-11 03:55:02Z Confirmed target scope and measured file-length hotspots for `src/lenslet/server.py`, `src/lenslet/storage/table.py`, `frontend/src/app/AppShell.tsx`, `frontend/src/features/inspector/Inspector.tsx`, and `frontend/src/features/metrics/MetricsPanel.tsx`.
- [x] 2026-02-11 03:55:02Z Mapped structural hotspots (route density, hook density, large methods/components) and existing automated test coverage in `tests/` and `frontend/src/**/__tests__/`.
- [x] 2026-02-11 04:01:34Z Captured user directive to permit larger, performance-oriented refactors while preserving behavior and contracts.
- [x] 2026-02-11 04:01:34Z Completed mandatory subagent review using the required prompt and integrated findings (architecture gate, compatibility matrix, validation expansion, ticket splits, artifact sync).
- [x] 2026-02-11 04:01:34Z Finalized this plan as implementation handoff under `docs/`.
- [x] 2026-02-11 04:12:31Z Completed S0 `T0` baseline snapshot capture: backend parity matrix (`63 passed`), import-contract probe (`import-contract-ok`), and hotpath timing baseline (`19 passed`, slowest case `0.10s`) recorded in `docs/dev_notes/20260211_s0_t0_baseline_snapshot.md`.
- [x] 2026-02-11 04:21:23Z Completed S0 `T1` seam-map capture: added per-file extraction map in `docs/dev_notes/20260211_s0_t1_seam_map.md` plus `S0/T1 seam anchors` comments in `src/lenslet/server.py`, `src/lenslet/storage/table.py`, `frontend/src/app/AppShell.tsx`, `frontend/src/features/inspector/Inspector.tsx`, and `frontend/src/features/metrics/MetricsPanel.tsx`; validation: backend slice (`11 passed`), import probe (`import-contract-ok`), frontend slice (`19 passed`).
- [x] 2026-02-11 04:22:50Z Completed S0 `T2a` architecture decision gate: added module-structure artifact `docs/dev_notes/20260211_s0_t2a_server_module_structure_gate.md`, explicitly locked module-only extraction (`server.py` + sibling helpers), and recorded the no-package-conversion constraint before S1 edits; validation: architecture-link check and module import probe (`server-module-import-ok`).
- [x] 2026-02-11 04:25:18Z Completed S0 `T2b` import-compatibility contract checks: added `tests/test_import_contract.py` to lock public/de-facto symbol exposure (`create_app*`, `HotpathTelemetry`, `_file_response`, `_thumb_response_async`, `og`, `TableStorage`, parquet loaders) plus the monkeypatch-sensitive `lenslet.server.og.subtree_image_count` path; validation: `pytest -q tests/test_import_contract.py` (`2 passed`) and import probe (`import-contract-ok`).
- [x] 2026-02-11 04:27:13Z Completed S1 `T3` runtime extraction: added `src/lenslet/server_runtime.py` with `build_app_runtime` and `AppRuntime`, rewired `create_app`, `create_app_from_datasets`, and `create_app_from_storage` through shared runtime construction while preserving `lenslet.server` facade symbols and health payload semantics; validation: `pytest -q tests/test_hotpath_sprint_s3.py tests/test_presence_lifecycle.py tests/test_refresh.py tests/test_import_contract.py` (`21 passed`), `pytest -q tests/test_hotpath_sprint_s4.py tests/test_collaboration_sync.py` (`14 passed`), and import probe (`import-contract-ok`).


## Surprises & Discoveries


`src/lenslet/server.py` currently mixes app factory composition, route registration, media/export helpers, presence logic, embeddings wiring, OG handling, and cache/runtime configuration in one 2314-line module. The module has 26 route decorators and many private helpers, so coupling is operationally high.

`src/lenslet/storage/table.py` currently acts as parser, path resolver, index builder, remote probe client, media dimension reader, metadata mutator, and search service. `_build_indexes` is 219 lines and dominates initialization complexity.

`frontend/src/app/AppShell.tsx` has high orchestration density (many state/effect/callback hooks), which increases stale closure risk and diff complexity for every feature adjustment.

Subagent review surfaced a critical architectural ambiguity: the first draft mixed a module facade (`src/lenslet/server.py`) with a package path proposal (`src/lenslet/server/*`). Python import precedence makes that risky. This plan resolves it by choosing a module-only layout with sibling helper modules (for example `server_runtime.py`, `server_routes_*.py`), preserving `lenslet.server` import stability.

Subagent review also found gaps in the first validation matrix. Additional existing suites are now required for parity: `tests/test_hotpath_sprint_s2.py`, `tests/test_metadata_endpoint.py`, and `tests/test_embeddings_cache.py`.

Initial baseline run for S0 `T0` completed quickly (`63 backend tests` in `3.49s` pytest time) with the current slowest hotpath test at `0.10s`, giving a concrete pre-refactor latency reference for S1+ comparisons.

Seam mapping confirmed that all three frontend target files interleave domain logic and UI rendering in the same component body; extraction should start from pure helpers and async workflows first to avoid stale-closure regressions during hook/component splits.

While closing S0 `T2a`, the architecture risk proved broader than import precedence alone: creating a `src/lenslet/server/` package would also destabilize de facto monkeypatch surfaces (`lenslet.server.og`) used in tests. Keeping sibling helper modules preserves both import path and patch target continuity.

For S0 `T2b`, the import contract needed one additional assertion beyond raw symbol presence: retaining `lenslet.server.og.subtree_image_count` as a concrete monkeypatch target to avoid hidden breakage in existing hotpath tests.

For S1 `T3`, extracting runtime wiring into a sibling module was safest when done with callable hooks (`build_thumb_cache`, prune-loop installer, hotpath factory) to avoid circular imports while still centralizing lock/sync/presence/queue setup.


## Decision Log


1. 2026-02-11, user plus assistant. Internal refactors may be large and bold if behavior remains stable and performance materially improves in targeted hot paths.
2. 2026-02-11, assistant. `src/lenslet/server.py` remains a module (not converted into a package). Internal decomposition uses sibling modules to avoid import collisions and maintain compatibility.
3. 2026-02-11, assistant. Public and de facto-private compatibility contracts are explicit and tested, including `create_app*`, `HotpathTelemetry`, `_file_response`, `_thumb_response_async`, `lenslet.server.og`, and table loader symbols.
4. 2026-02-11, assistant. Backend API-contract freeze gate is required before frontend refactor sprints begin.
5. 2026-02-11, assistant. Oversized tickets are split into atomic domain tickets (routes by domain, AppShell domains, validation execution vs regression-fix execution).
6. 2026-02-11, assistant. Line-count reduction is secondary. Primary success criteria are readability, separable responsibilities, and measurable speed improvements with stable behavior.
7. 2026-02-11, assistant. Frontend artifact sync to `src/lenslet/frontend/` is mandatory in closeout when UI files are changed.
8. 2026-02-11, assistant. S0 `T0` performance baseline comparisons use the recorded hotpath `pytest --durations=10` snapshot in `docs/dev_notes/20260211_s0_t0_baseline_snapshot.md` as the before-reference unless a ticket defines a narrower benchmark harness.
9. 2026-02-11, assistant. S0 `T1` will use dual seam artifacts (a detailed `docs/dev_notes` map and lightweight in-file `S0/T1 seam anchors`) so later extraction tickets can move quickly without re-discovering boundaries.
10. 2026-02-11, assistant. S0 `T2a` is considered complete only with an explicit architecture artifact under `docs/dev_notes/` and an explicit prohibition on creating a `src/lenslet/server/` package during S1 extraction.
11. 2026-02-11, assistant. S0 `T2b` compatibility locking is implemented as a dedicated pytest module (`tests/test_import_contract.py`) so it runs naturally in the existing test workflow and enforces both symbol presence and `lenslet.server.og.subtree_image_count` monkeypatch continuity.
12. 2026-02-11, assistant. S1 `T3` runtime extraction uses `server_runtime.build_app_runtime` plus a thin `_initialize_runtime` facade wrapper in `server.py` so app factories share one runtime path without changing `lenslet.server` exports or monkeypatch touchpoints.


## Outcomes & Retrospective


At this planning milestone, the deliverable is a fully self-contained execution document that a new engineer can run without guessing architecture choices. Compared with the initial draft, this revision resolves the server module-structure ambiguity, expands validation to cover hidden compatibility surfaces, and introduces explicit performance verification in addition to parity checks.

The implementation gap remains execution itself. Success of this plan will be judged by whether each sprint can ship independently with passing tests and measurable non-regression or improvement evidence.


## Context and Orientation


Target backend files are `src/lenslet/server.py` and `src/lenslet/storage/table.py`. Target frontend files are `frontend/src/app/AppShell.tsx`, `frontend/src/features/inspector/Inspector.tsx`, and `frontend/src/features/metrics/MetricsPanel.tsx`.

Current backend constraints include route behavior, presence lifecycle semantics, and hotpath counters/timers. Existing tests already lock meaningful behavior in `tests/test_presence_lifecycle.py`, `tests/test_hotpath_sprint_s2.py`, `tests/test_hotpath_sprint_s3.py`, `tests/test_hotpath_sprint_s4.py`, `tests/test_refresh.py`, `tests/test_folder_pagination.py`, `tests/test_collaboration_sync.py`, `tests/test_compare_export_endpoint.py`, `tests/test_metadata_endpoint.py`, `tests/test_embeddings_search.py`, `tests/test_embeddings_cache.py`, `tests/test_table_security.py`, `tests/test_remote_worker_scaling.py`, and `tests/test_parquet_ingestion.py`.

Current frontend constraints include app utility and behavior tests in `frontend/src/app/__tests__/appShellHelpers.test.ts`, `frontend/src/app/__tests__/presenceActivity.test.ts`, `frontend/src/app/__tests__/presenceUi.test.ts`, `frontend/src/features/inspector/__tests__/exportComparison.test.tsx`, `frontend/src/features/browse/model/__tests__/filters.test.ts`, `frontend/src/features/browse/model/__tests__/pagedFolder.test.ts`, `frontend/src/features/browse/model/__tests__/prefetchPolicy.test.ts`, `frontend/src/api/__tests__/client.events.test.ts`, and `frontend/src/api/__tests__/client.presence.test.ts`.

Compatibility touchpoints outside direct imports also matter. Some tests monkeypatch `lenslet.server.og.subtree_image_count`, so `lenslet.server` must continue exposing an `og` module attribute.

In this plan, "behavioral parity" means unchanged external semantics for API responses and UI interactions. "Performance optimization" means reducing latency, CPU, memory churn, or redundant work in hot paths without changing result correctness.


## Plan of Work


The sequence starts with explicit baselines and architectural gates, then extracts backend modules first because frontend flows depend on stable runtime semantics. Once backend contracts are frozen, frontend decomposition proceeds by domain state ownership and pure-model extraction, with targeted optimization inside each domain. The final sprint runs an expanded validation matrix, performs packaging checks, and verifies bundled frontend artifact synchronization.

Every sprint must produce a demoable and testable increment. Every ticket is atomic and committable, with validation tied to that ticket.

- While implementing each sprint, update the plan document continuously (Progress, Decision Log, Surprises & Discoveries, and relevant sections). After each sprint is complete, add clear handover notes.
- For minor script-level uncertainties (for example, exact file placement), proceed according to the approved plan to maintain momentum. After the sprint, ask for clarifications and then apply follow-up adjustments.

### Sprint Plan


1. S0: Baseline, architecture gate, and compatibility matrix.
   Goal: lock current behavior, establish performance baseline snapshots, and finalize non-ambiguous server/layout decisions before code movement.
   Demo outcome: baseline tests pass; architecture decision note is committed; import-contract check script passes.
   Linked tasks: T0, T1, T2a, T2b, T2c.
2. S1: Backend modular extraction of `server.py` using module-only helper layout.
   Goal: split runtime wiring and route registration into domain modules while preserving `lenslet.server` import surface.
   Demo outcome: app boots and serves in directory, dataset, and table modes with unchanged endpoint behavior.
   Linked tasks: T3, T4a, T4b, T4c, T4d, T5.
3. S2: Backend hotpath optimization and parity lock.
   Goal: optimize recursive folders, thumbnail/file fast paths, and unnecessary work in route handlers while keeping outputs stable.
   Demo outcome: benchmark snapshots show same correctness with improved hotpath timings or lower work for representative cases.
   Linked tasks: T6, T7, T8.
4. S3: TableStorage decomposition and ingestion/runtime optimization.
   Goal: split schema/path/index/probe/media responsibilities and optimize expensive loops/conversions where safe.
   Demo outcome: table-backed browsing and search semantics are unchanged; initialization and hotpath metrics improve on sampled datasets.
   Linked tasks: T9, T10, T11, T12.
5. S4: AppShell decomposition and interaction-path optimization.
   Goal: separate state domains into hooks/selectors/components and reduce avoidable rerenders/effect churn.
   Demo outcome: browse/viewer/compare/selection/presence/upload workflows remain stable and smoother under heavy item sets.
   Linked tasks: T13a, T13b, T13c, T13d, T14, T15.
6. S5: Inspector decomposition and metadata/compare-path optimization.
   Goal: isolate section logic, pure metadata/compare utilities, and async workflows; optimize heavy compare rendering paths.
   Demo outcome: inspector parity remains intact, and compare metadata interactions feel faster on large metadata payloads.
   Linked tasks: T16, T17, T18, T19.
7. S6: Metrics panel decomposition and histogram-path optimization.
   Goal: isolate metrics UI from math and interaction logic; cache expensive calculations to reduce repeated work.
   Demo outcome: metric range filtering behavior is unchanged and histogram interactions remain responsive on large metric sets.
   Linked tasks: T20, T21, T22, T23.
8. S7: Consolidation, packaging, and acceptance closeout.
   Goal: run full fixed validation matrix, split regression fixes by domain, sync frontend artifacts, and publish module-map docs.
   Demo outcome: all validation passes; packaged app serves latest frontend bundle; module ownership is documented.
   Linked tasks: T24a, T24b, T25, T26.


## Concrete Steps


All commands below run from the repository root unless noted.

    Working directory: /home/ubuntu/dev/lenslet

    rg -n "def create_app|def create_app_from_|def _register_|class HotpathTelemetry" src/lenslet/server.py
    rg -n "^    def " src/lenslet/storage/table.py
    rg -n "export default function AppShell|useState\(|useEffect\(|useMemo\(|useCallback\(" frontend/src/app/AppShell.tsx
    rg -n "export default function Inspector|function InspectorSection|handleComparisonExport" frontend/src/features/inspector/Inspector.tsx
    rg -n "export default function MetricsPanel|function MetricHistogramCard|computeHistogramFromValues" frontend/src/features/metrics/MetricsPanel.tsx

Baseline parity and compatibility run:

    Working directory: /home/ubuntu/dev/lenslet

    pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py

    python - <<'PY'
    import lenslet.server as server
    import lenslet.storage.table as table
    assert hasattr(server, 'create_app')
    assert hasattr(server, 'create_app_from_datasets')
    assert hasattr(server, 'create_app_from_table')
    assert hasattr(server, 'create_app_from_storage')
    assert hasattr(server, 'HotpathTelemetry')
    assert hasattr(server, '_file_response')
    assert hasattr(server, '_thumb_response_async')
    assert hasattr(server, 'og')
    assert hasattr(table, 'TableStorage')
    assert hasattr(table, 'load_parquet_table')
    assert hasattr(table, 'load_parquet_schema')
    print('import-contract-ok')
    PY

Frontend parity run:

    Working directory: /home/ubuntu/dev/lenslet/frontend

    npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts

    npx tsc --noEmit

Packaging sanity and shipped-asset sync:

    Working directory: /home/ubuntu/dev/lenslet/frontend

    npm run build
    cp -r dist/* ../src/lenslet/frontend/

    Working directory: /home/ubuntu/dev/lenslet

    python -m build

### Task/Ticket Details


1. T0: Capture behavioral and performance baseline snapshots.
   Goal: record baseline correctness and hotpath numbers before major refactor begins.
   Affected files and areas: test outputs and sprint notes.
   Validation: baseline command set passes and baseline timing snapshot for representative flows is saved.
   Status: completed at `2026-02-11T04:12:31Z`; artifact `docs/dev_notes/20260211_s0_t0_baseline_snapshot.md`.

2. T1: Produce per-file extraction seam map.
   Goal: define responsibility boundaries and extraction order by domain.
   Affected files and areas: `docs/dev_notes/` note plus anchors in target files.
   Validation: each target file has a committed seam map with ticket references.
   Status: completed at `2026-02-11T04:21:23Z`; artifact `docs/dev_notes/20260211_s0_t1_seam_map.md` plus in-file seam comments in all five target long files.

3. T2a: Resolve server module structure decision gate.
   Goal: lock module-only extraction shape (`server.py` + sibling helper modules), avoiding package conversion ambiguity.
   Affected files and areas: this plan and architecture note.
   Validation: documented decision approved before S1 code edits begin.
   Status: completed at `2026-02-11T04:22:50Z`; artifact `docs/dev_notes/20260211_s0_t2a_server_module_structure_gate.md`; approval recorded in Decision Log item `10`.

4. T2b: Add explicit import-compatibility contract checks.
   Goal: codify compatibility for public and currently relied-on private symbols.
   Affected files and areas: small compatibility test/script under `tests/` or CI helper script.
   Validation: check script passes pre- and post-refactor.
   Status: completed at `2026-02-11T04:25:18Z`; artifact `tests/test_import_contract.py`; validation `pytest -q tests/test_import_contract.py` (`2 passed`) and import probe (`import-contract-ok`).

5. T2c: Add API freeze checkpoint before frontend refactors.
   Goal: guarantee backend route contracts are stable before S4 starts.
   Affected files and areas: sprint handoff note and decision log updates.
   Validation: checkpoint recorded and signed off after S3.

6. T3: Extract app runtime wiring into sibling runtime module.
   Goal: move shared setup for workspace, sync state, presence, queue, and telemetry to a dedicated runtime constructor.
   Affected files and areas: `src/lenslet/server.py`, new `src/lenslet/server_runtime.py`.
   Validation: `/health` payload semantics remain unchanged in existing tests.
   Status: completed at `2026-02-11T04:27:13Z`; artifacts `src/lenslet/server_runtime.py` and runtime-facade updates in `src/lenslet/server.py`; validation `pytest -q tests/test_hotpath_sprint_s3.py tests/test_presence_lifecycle.py tests/test_refresh.py tests/test_import_contract.py` (`21 passed`), `pytest -q tests/test_hotpath_sprint_s4.py tests/test_collaboration_sync.py` (`14 passed`), plus import probe (`import-contract-ok`).

7. T4a: Extract common route registration domain.
   Goal: isolate folders/item/thumb/file/search route registration.
   Affected files and areas: `src/lenslet/server.py`, new `src/lenslet/server_routes_common.py`.
   Validation: route-focused tests pass with no response-shape changes.

8. T4b: Extract presence route registration domain.
   Goal: isolate presence endpoints, diagnostics, and lifecycle helpers.
   Affected files and areas: `src/lenslet/server.py`, new `src/lenslet/server_routes_presence.py`.
   Validation: `tests/test_presence_lifecycle.py` and related sync tests pass unchanged.

9. T4c: Extract embeddings and views route registration domains.
   Goal: isolate embeddings and views routes from common route bundle.
   Affected files and areas: `src/lenslet/server.py`, new `src/lenslet/server_routes_embeddings.py`, new `src/lenslet/server_routes_views.py`.
   Validation: embeddings and views tests pass; no route regressions.

10. T4d: Extract index/OG/media route helpers and wiring.
    Goal: isolate index/meta/OG route responsibilities and media helper dependencies.
    Affected files and areas: `src/lenslet/server.py`, new `src/lenslet/server_routes_index.py`, new `src/lenslet/server_routes_og.py`, new `src/lenslet/server_media.py`.
    Validation: `tests/test_hotpath_sprint_s2.py`, `tests/test_hotpath_sprint_s3.py`, `tests/test_hotpath_sprint_s4.py`, and `tests/test_compare_export_endpoint.py` pass.

11. T5: Keep `server.py` as stable facade module.
    Goal: reduce `server.py` to composition and stable exports while preserving import/monkeypatch touchpoints.
    Affected files and areas: `src/lenslet/server.py`.
    Validation: compatibility script and import-heavy tests pass.

12. T6: Optimize recursive folder and traversal hotpaths.
    Goal: remove redundant work in recursive item collection/paging paths without changing ordering and pagination semantics.
    Affected files and areas: extracted folder route/domain modules.
    Validation: `tests/test_folder_pagination.py` and hotpath tests pass; timing snapshot shows lower traversal overhead.

13. T7: Optimize thumb/file response work.
    Goal: reduce avoidable byte reads and blocking work on file/thumb paths while preserving headers and behavior.
    Affected files and areas: `src/lenslet/server_media.py` and related route glue.
    Validation: hotpath tests and metadata tests pass; endpoint semantics unchanged.

14. T8: Optimize presence and sync-path incidental overhead.
    Goal: reduce unnecessary churn in presence publish/prune paths while preserving lifecycle semantics.
    Affected files and areas: presence route/runtime modules.
    Validation: `tests/test_presence_lifecycle.py` and `tests/test_collaboration_sync.py` pass with no behavior diffs.

15. T9: Extract table schema/path resolution modules.
    Goal: move column detection/coercion and path/source derivation out of monolithic class body.
    Affected files and areas: `src/lenslet/storage/table.py`, new `src/lenslet/storage/table_schema.py`, new `src/lenslet/storage/table_paths.py`.
    Validation: `tests/test_parquet_ingestion.py` and `tests/test_table_security.py` pass unchanged.

16. T10: Extract and optimize table index build pipeline.
    Goal: split row scan and index assembly into explicit phases, then remove obvious repeated work in loops.
    Affected files and areas: `src/lenslet/storage/table.py`, new `src/lenslet/storage/table_index.py`.
    Validation: browse/search parity tests pass; index build baseline metrics improve on sampled datasets.

17. T11: Extract remote probing and fast-dimension readers.
    Goal: isolate remote header fetch/parsing and format-specific dimension readers for focused optimization.
    Affected files and areas: `src/lenslet/storage/table.py`, new `src/lenslet/storage/table_probe.py`, new `src/lenslet/storage/table_media.py`.
    Validation: `tests/test_remote_worker_scaling.py` and hotpath tests pass.

18. T12: Keep `TableStorage` as facade while enabling delegated collaborators.
    Goal: preserve constructor and method contracts while reducing internal complexity and coupling.
    Affected files and areas: `src/lenslet/storage/table.py`.
    Validation: embedding and search tests that instantiate `TableStorage` pass without call-site changes.

19. T13a: Extract AppShell data-scope domain hook.
    Goal: isolate folder/search/similarity data loading and derived lists.
    Affected files and areas: `frontend/src/app/AppShell.tsx`, new hook under `frontend/src/app/hooks/`.
    Validation: browse/search/similarity behavior remains unchanged in tests and manual smoke.

20. T13b: Extract AppShell selection/viewer/compare domain hook.
    Goal: isolate selection, viewer state, compare state, and navigation semantics.
    Affected files and areas: `frontend/src/app/AppShell.tsx`, new hook under `frontend/src/app/hooks/`.
    Validation: viewer and compare flows behave identically.

21. T13c: Extract AppShell presence/sync domain hook.
    Goal: isolate event subscriptions, connection status, and activity derivation.
    Affected files and areas: `frontend/src/app/AppShell.tsx`, new hook under `frontend/src/app/hooks/`.
    Validation: presence indicators and reconnect behaviors stay stable.

22. T13d: Extract AppShell mutation/actions domain hook.
    Goal: isolate upload/move/context actions and error handling.
    Affected files and areas: `frontend/src/app/AppShell.tsx`, new hook under `frontend/src/app/hooks/`.
    Validation: action UX and errors match current behavior.

23. T14: Extract AppShell selectors and pure helper models.
    Goal: move list transforms and derived state into pure tested functions.
    Affected files and areas: `frontend/src/app/model/`, `frontend/src/app/utils/`.
    Validation: added unit tests for extracted selectors pass.

24. T15: Reduce AppShell rerender/effect churn.
    Goal: optimize memo boundaries, event listener lifecycles, and expensive derivations.
    Affected files and areas: `frontend/src/app/AppShell.tsx` and new hooks/helpers.
    Validation: interaction semantics remain identical; profiling snapshots show reduced render work.

25. T16: Extract Inspector pure metadata and compare model utilities.
    Goal: isolate metadata normalization/rendering/flattening and compare diff generation.
    Affected files and areas: `frontend/src/features/inspector/model/`, `frontend/src/features/inspector/Inspector.tsx`.
    Validation: inspector export comparison tests and new model tests pass.

26. T17: Split Inspector sections into typed components.
    Goal: separate overview/compare/basics/metadata/notes section responsibilities.
    Affected files and areas: `frontend/src/features/inspector/sections/`, `frontend/src/features/inspector/Inspector.tsx`.
    Validation: visual/interaction parity in manual and automated checks.

27. T18: Extract Inspector async workflows into hooks.
    Goal: isolate metadata fetch, compare export submit, typing state, and conflict logic.
    Affected files and areas: `frontend/src/features/inspector/hooks/`, `frontend/src/features/inspector/Inspector.tsx`.
    Validation: async loading/error/success semantics unchanged.

28. T19: Optimize heavy Inspector render paths.
    Goal: reduce expensive compare/metadata rendering churn without changing what is shown.
    Affected files and areas: inspector sections and model utilities.
    Validation: parity tests pass; sampled interaction latency improves on large metadata payloads.

29. T20: Split MetricsPanel into cards/components.
    Goal: separate attributes, range panel, and histogram card UI components.
    Affected files and areas: `frontend/src/features/metrics/components/`, `frontend/src/features/metrics/MetricsPanel.tsx`.
    Validation: metrics filtering behavior unchanged.

30. T21: Extract histogram math utilities into pure module.
    Goal: isolate binning/range/formatting helpers and edge-case behavior.
    Affected files and areas: `frontend/src/features/metrics/model/histogram.ts` and related files.
    Validation: dedicated utility tests pass on edge values.

31. T22: Extract histogram interaction state machine hook.
    Goal: isolate drag/hover/commit transitions in a testable hook.
    Affected files and areas: `frontend/src/features/metrics/hooks/`, metrics components.
    Validation: histogram drag and clear behavior remains identical.

32. T23: Optimize metrics computation reuse.
    Goal: avoid repeated recomputation across filters/selections where result can be safely reused.
    Affected files and areas: metrics model and hooks/components.
    Validation: same filter outcomes, fewer expensive recalculations in profiling.

33. T24a: Execute fixed validation matrix only.
    Goal: run all required backend/frontend/type/build checks without mixing fixes.
    Affected files and areas: none (execution-only ticket).
    Validation: all checks pass, or failures are captured with failing domain tags.

34. T24b: Fix regressions by explicit domain ownership.
    Goal: resolve failures in scoped follow-up commits by backend/table/frontend ownership lanes.
    Affected files and areas: only files implicated by failing checks.
    Validation: previously failing checks pass; no new failures introduced.

35. T25: Regenerate shipped frontend assets and verify Python-served shell.
    Goal: ensure packaged app serves updated frontend after UI refactor.
    Affected files and areas: `src/lenslet/frontend/` generated assets.
    Validation: build copy succeeds and app serves expected `index.html` content via FastAPI static mount.

36. T26: Update docs with new module map and operational notes.
    Goal: document new boundaries and maintenance guidance for future contributors.
    Affected files and areas: `DEVELOPMENT.md`, `README.md`, and this plan progress section as needed.
    Validation: docs reflect final module layout and verification workflow.


## Validation and Acceptance


Sprint acceptance remains behavior-first, but now includes performance evidence where optimization tickets are claimed complete.

1. S0 acceptance requires passing baseline matrix, documented architecture decision gate, and import-contract script success.
2. S1 acceptance requires unchanged backend route behavior with compatibility checks passing.
3. S2 acceptance requires hotpath endpoint parity and measurable improvement in at least one tracked backend hotpath metric without regressions elsewhere.
4. S3 acceptance requires table-backed parity plus measured reduction in index/probe overhead on representative input.
5. S4 acceptance requires AppShell workflow parity and reduced avoidable rerender/effect churn.
6. S5 acceptance requires Inspector parity and faster heavy metadata/compare interactions on representative payloads.
7. S6 acceptance requires Metrics behavior parity and reduced expensive recomputation in histogram/filter interactions.
8. S7 acceptance requires full matrix pass, artifact sync completion, packaging sanity, and updated docs.

Overall acceptance criteria are:

1. Public APIs, CLI flags, and user-visible semantics are unchanged.
2. Existing tests pass without semantic weakening.
3. Compatibility script for private/de facto surfaces passes.
4. Performance claims are backed by before/after snapshots captured during the sprint.
5. Target long files are materially reduced and responsibilities are cleanly separated.

Required validation matrix:

    Working directory: /home/ubuntu/dev/lenslet

    pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py

    python - <<'PY'
    import lenslet.server as server
    import lenslet.storage.table as table
    assert hasattr(server, 'create_app')
    assert hasattr(server, 'create_app_from_datasets')
    assert hasattr(server, 'create_app_from_table')
    assert hasattr(server, 'create_app_from_storage')
    assert hasattr(server, 'HotpathTelemetry')
    assert hasattr(server, '_file_response')
    assert hasattr(server, '_thumb_response_async')
    assert hasattr(server, 'og')
    assert hasattr(table, 'TableStorage')
    assert hasattr(table, 'load_parquet_table')
    assert hasattr(table, 'load_parquet_schema')
    print('import-contract-ok')
    PY

    Working directory: /home/ubuntu/dev/lenslet/frontend

    npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts

    npx tsc --noEmit
    npm run build
    cp -r dist/* ../src/lenslet/frontend/

    Working directory: /home/ubuntu/dev/lenslet

    python -m build

Performance evidence expectations per optimization sprint:

1. Capture before/after measurement for target operations using the same dataset and command path.
2. Keep correctness checks in the same run so performance does not regress semantics.
3. Record measured deltas in sprint notes under `docs/` for reproducibility.


## Idempotence and Recovery


This plan is idempotent at ticket granularity. Re-running extraction commits should not mutate data formats or route contracts. Optimization tickets must retain exact output semantics, so rollback is straightforward to the previous behavior-safe commit.

Recovery is domain-scoped.

1. If backend extraction regresses behavior, revert affected backend extraction ticket commits and re-run backend matrix before continuing.
2. If frontend extraction regresses behavior, revert only affected frontend domain ticket commits and re-run frontend matrix.
3. If an optimization improves speed but changes semantics, drop that optimization and keep structural refactor only.

No storage migration is introduced in this plan, so rollback does not require data repair.


## Artifacts and Notes


Subagent review artifact for this plan is stored at `docs/20260211_foundational_long_file_refactor_plan_review.txt`.

S0 `T2a` architecture-gate artifact is stored at `docs/dev_notes/20260211_s0_t2a_server_module_structure_gate.md`.

Proposed backend target module shape (module-only; no `server/` package conversion):

    src/lenslet/server.py                              # public facade + stable exports
    src/lenslet/server_runtime.py                      # shared runtime wiring
    src/lenslet/server_routes_common.py                # folders/item/thumb/file/search
    src/lenslet/server_routes_presence.py              # presence routes and diagnostics
    src/lenslet/server_routes_embeddings.py            # embeddings routes
    src/lenslet/server_routes_views.py                 # views routes
    src/lenslet/server_routes_index.py                 # index/meta routes
    src/lenslet/server_routes_og.py                    # OG routes
    src/lenslet/server_media.py                        # media/export helper stack

Proposed table-storage internal split while preserving `TableStorage` facade:

    src/lenslet/storage/table.py                       # public class facade and imports
    src/lenslet/storage/table_schema.py                # column detection and coercion
    src/lenslet/storage/table_paths.py                 # source/path derivation and safety
    src/lenslet/storage/table_index.py                 # index build pipeline
    src/lenslet/storage/table_probe.py                 # remote headers/dimensions
    src/lenslet/storage/table_media.py                 # local fast-dimension readers/thumbnail helpers

Proposed frontend target module shape:

    frontend/src/app/AppShell.tsx
    frontend/src/app/hooks/useAppDataScope.ts
    frontend/src/app/hooks/useAppSelection.ts
    frontend/src/app/hooks/useAppPresenceSync.ts
    frontend/src/app/hooks/useAppActions.ts
    frontend/src/app/model/*.ts
    frontend/src/features/inspector/Inspector.tsx
    frontend/src/features/inspector/sections/*.tsx
    frontend/src/features/inspector/model/*.ts
    frontend/src/features/inspector/hooks/*.ts
    frontend/src/features/metrics/MetricsPanel.tsx
    frontend/src/features/metrics/components/*.tsx
    frontend/src/features/metrics/model/histogram.ts
    frontend/src/features/metrics/hooks/*.ts

Target line-budget outcomes after completion are guidance only:

    src/lenslet/server.py <= 350 lines
    src/lenslet/storage/table.py <= 500 lines
    frontend/src/app/AppShell.tsx <= 850 lines
    frontend/src/features/inspector/Inspector.tsx <= 700 lines
    frontend/src/features/metrics/MetricsPanel.tsx <= 550 lines


## Interfaces and Dependencies


Public interfaces that must remain stable include:

    from lenslet.server import create_app, create_app_from_datasets, create_app_from_table, create_app_from_storage
    from lenslet.storage.table import TableStorage, load_parquet_table, load_parquet_schema

De facto compatibility surfaces that are currently exercised and must remain stable during this refactor include:

    lenslet.server.HotpathTelemetry
    lenslet.server._file_response
    lenslet.server._thumb_response_async
    lenslet.server.og

Backend internal interface targets are:

    build_runtime(...) -> AppRuntime
    register_common_routes(app: FastAPI, runtime: AppRuntime, to_item: Callable[..., Item]) -> None
    register_presence_routes(app: FastAPI, runtime: AppRuntime) -> None
    register_embedding_routes(app: FastAPI, runtime: AppRuntime) -> None

Table-storage internal interface targets are:

    resolve_source_column(columns: list[str], data: dict[str, list[Any]], source_column: str | None) -> str
    build_indexes(...) -> BuildIndexesResult
    probe_remote_dimensions(tasks: list[ProbeTask], workers: int) -> list[ProbeResult]
    read_dimensions_from_bytes(data: bytes, ext: str | None) -> tuple[int, int] | None

Frontend interface targets are:

    useAppDataScope(...) -> { data, items, metricKeys, refetch, loadingState, errors }
    useAppSelection(...) -> { selectedPaths, setSelectedPaths, openViewer, closeViewer, compareState }
    useInspectorCompareExport(...) -> { exportState, onExport, onReverseExport }
    computeHistogramFromValues(values: number[], bins: number, base?: Histogram): Histogram | null

Dependencies remain unchanged unless an optimization ticket explicitly justifies a new dependency with measurable benefit and equivalent correctness guarantees. Default path is no new runtime dependencies.

Ownership lanes for implementation are:

1. Backend lane owns S1, S2, and backend portions of S7.
2. Data/table lane owns S3 and table portions of S7.
3. Frontend lane owns S4, S5, S6, and frontend artifact sync in S7.

Revision note (2026-02-11): Updated after user direction to allow bolder performance refactors and after mandatory subagent review; resolved server module-structure ambiguity, expanded compatibility matrix and validation coverage, split oversized tickets, added API freeze gate, and added frontend shipped-asset synchronization requirements.
