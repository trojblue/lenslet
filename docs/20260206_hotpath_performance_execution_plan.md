# Folder, OG, and File Hot Path Performance Plan (Items 1,2,3,4,5,9)


## Purpose / Big Picture


This plan defines the implementation sequence to remove major user-visible latency from Lenslet’s browse startup and media loading paths while preserving core behavior. After implementation, users should see faster initial folder render, less stalled thumbnail/file loading, lower backend memory pressure, and fewer unnecessary network requests during scrolling and navigation.

The plan scope is explicitly items 1, 2, 3, 4, 5, and 9 from the prior inspection round, interpreted from the user’s “459” shorthand as items 4, 5, and 9. The remaining identified hotspots are intentionally moved to a deferred “Potential Future Changes” backlog.

No `PLANS.md` file is present in this repository. This document is the canonical execution plan for this change set.


## Progress


- [x] 2026-02-06 11:37:07Z Re-read the incident report and re-audited backend/frontend hot paths with file-level evidence.
- [x] 2026-02-06 11:37:07Z Scoped the implementation to items 1,2,3,4,5,9 and defined deferred backlog boundaries.
- [x] 2026-02-06 11:37:07Z Drafted sprint and atomic ticket breakdown with validations.
- [x] 2026-02-06 11:47:53Z Ran pseudo-subagent review pass and wrote output to `docs/20260206_hotpath_performance_execution_plan_review.txt`.
- [x] 2026-02-06 11:47:53Z Incorporated review feedback: measurable gates, API contract hardening, compatibility/abuse safeguards, task splits, observability, and packaging checks.
- [ ] Execute Sprint S1 (recursive folder payload contract + incremental loading foundations).
- [ ] Execute Sprint S2 (OG shell path + `/file` delivery/prefetch policy).
- [ ] Execute Sprint S3 (render purity, S3 reuse, cancellation, observability).
- [ ] Execute Sprint S4 (regression tests, packaging verification, docs).


## Surprises & Discoveries


The main browse query still requests recursive folder payloads by default in the app shell. Evidence: `frontend/src/app/AppShell.tsx:307` and recursive backend traversal at `src/lenslet/server.py:197`.

The index HTML route executes subtree counting work during render when OG preview is enabled, which can block shell delivery on large trees. Evidence: `src/lenslet/server.py:500` through `src/lenslet/server.py:506` and traversal function `src/lenslet/og.py:50`.

The `/file` route materializes whole files into memory and the UI speculatively prefetches full files in multiple places, amplifying I/O and memory pressure. Evidence: `src/lenslet/server.py:468`, `frontend/src/app/AppShell.tsx:1231`, and `frontend/src/features/browse/components/VirtualGrid.tsx:469`.

Thumbnail prefetch side effects currently run during render in `VirtualGrid`, which can repeat request scheduling across rerenders. Evidence: `frontend/src/features/browse/components/VirtualGrid.tsx:433`.

Thumbnail scheduler cancellation exists but is not wired on client disconnect, so queued work can continue after request abandonment. Evidence: `src/lenslet/thumbs.py:39` and disconnect path in `src/lenslet/server.py:458`.

S3 presign calls create a boto3 client repeatedly per call path, which adds avoidable overhead under bursty thumb/file traffic. Evidence: `src/lenslet/storage/table.py:1050` and `src/lenslet/storage/dataset.py:87`.

Route stacks are duplicated across three app factory paths in `src/lenslet/server.py`, so interface changes must be applied consistently in all three to avoid mode-specific behavior drift.


## Decision Log


2026-02-06, author: assistant. The implementation set is fixed to items 1,2,3,4,5,9, with “459” interpreted as 4+5+9 to preserve momentum and align with the prior recommendation.

2026-02-06, author: assistant. Recursive folder behavior remains supported, but recursive delivery is paged and contract-defined, including defaults, clamping, and explicit compatibility behavior for existing clients.

2026-02-06, author: assistant. OG metadata injection must not perform per-request recursive tree counting on the critical HTML shell path.

2026-02-06, author: assistant. `/file` is split into local streaming behavior and non-local fallback behavior with explicit validation for range/head semantics where applicable.

2026-02-06, author: assistant. Frontend render functions must remain side-effect free; request scheduling work is moved to effects.

2026-02-06, author: assistant. S3 client/session reuse is required in storage backends to remove repeated client construction overhead.

2026-02-06, author: assistant. Delivery is gated by measurable performance targets and baseline-vs-post comparisons, not solely by functional correctness.

2026-02-06, author: assistant. Non-selected findings (search indexing, folder tree virtualization, durability write batching) move to deferred backlog and are excluded from this implementation.


## Outcomes & Retrospective


No code has been changed yet in this turn, so this section records intended outcomes by milestone. Sprint 1 should make recursive browsing payload delivery incremental and contract-safe. Sprint 2 should remove OG-related shell stalls and reduce memory/network spikes from full-file transfers. Sprint 3 should eliminate render-time request side effects and tighten backend efficiency for remote and canceled thumbnail paths. Sprint 4 should make regressions unlikely through tests, packaging checks, and docs.

The key lesson from this inspection is that latency is produced by interaction between multiple “small defaults” across backend and frontend, not by a single hotspot.


## Context and Orientation


The backend API entrypoint is `src/lenslet/server.py`, with recursive folder assembly in `_collect_recursive_items` and `_build_folder_index`. OG helpers are in `src/lenslet/og.py`. Thumbnail queue behavior is in `src/lenslet/thumbs.py`. Storage behavior for local/table/dataset modes is in `src/lenslet/storage/memory.py`, `src/lenslet/storage/table.py`, and `src/lenslet/storage/dataset.py`.

The frontend browse entrypoint is `frontend/src/app/AppShell.tsx`. Folder query hooks are in `frontend/src/api/folders.ts` and `frontend/src/api/client.ts`. Virtualized grid behavior is in `frontend/src/features/browse/components/VirtualGrid.tsx`. Shared blob caching is in `frontend/src/lib/blobCache.ts`.

In this plan, “recursive payload” means item materialization across folder descendants for one browse scope. “Critical shell path” means delivery of `/` or `/index.html` prior to user interaction. “Speculative prefetch” means network fetches initiated before explicit user open action.


## Plan of Work


The work starts by hardening the recursive `/folders` contract so first render can be fast and predictable without one-shot full-subtree payloads, while preserving compatibility for existing callers. Next it removes OG count traversal from the HTML shell route and reduces heavy full-file path pressure by switching to streaming for local files and tightening prefetch behavior. Then it addresses correctness and efficiency details that still leak work, including render-time side effects, repeated S3 client creation, cancellation, and observability. The final sprint hardens the change set with regression tests, packaging verification, and documentation.

### Sprint Plan


1. Sprint S1: Recursive Folder Contract and Incremental Loading.
Goal: preserve recursive browsing while avoiding one-shot full-subtree payload stalls, and define strict API behavior.
Demo outcome: opening `/` returns quickly with first-page recursive items, pages are stable and bounded, and legacy callers remain functional under compatibility mode.
Linked tasks: T1, T2, T3, T4, T5, T6, T7, T8.

2. Sprint S2: OG Shell Path and `/file` Hot Path Reduction.
Goal: remove recursive count work from HTML render and reduce full-file memory/network pressure.
Demo outcome: `/index.html` render does not invoke subtree traversal; local `/file` uses streaming response; non-local fallback behavior remains correct; unnecessary full-file prefetches are removed.
Linked tasks: T9, T10, T11, T12, T13, T14.

3. Sprint S3: Render Purity, Backend Efficiency, and Telemetry.
Goal: remove render-time side effects, reuse S3 clients, stop thumbnail work on disconnect, and add runtime metrics.
Demo outcome: no thumb prefetch scheduling inside render body; S3 presign path reuses clients; disconnected thumb requests cancel queued/in-flight work; counters are visible for key operations.
Linked tasks: T15, T16, T17, T18, T19.

4. Sprint S4: Regression Hardening, Packaging Verification, and Docs.
Goal: lock behavior with tests, verify served frontend bundle packaging, and publish rollout/deferred backlog notes.
Demo outcome: passing targeted backend/frontend tests and updated docs with explicit deferred backlog and rollout checks.
Linked tasks: T20, T21, T22.

### Potential Future Changes


The following findings are intentionally deferred out of this implementation scope.

1. Build a real indexed search path to replace O(N) in-memory scans (`src/lenslet/storage/memory.py:387`, `src/lenslet/storage/table.py:953`, `src/lenslet/storage/dataset.py:528`).

2. Virtualize or flatten very large folder trees in UI (`frontend/src/features/folders/FolderTree.tsx:205`).

3. Make label persistence durability configurable or batched to reduce per-edit fsync latency (`src/lenslet/workspace.py:169`).


## Concrete Steps


All commands run from `/home/ubuntu/dev/lenslet`.

    cd /home/ubuntu/dev/lenslet

Create and use a feature branch before edits.

    git checkout -b fix/hotpath-performance-round2

Capture baseline metrics before implementation and keep artifacts under `docs/`.

    python -m pytest tests/test_refresh.py -q
    python -m pytest tests/test_memory_index_performance.py -q
    python -m pytest tests/test_remote_worker_scaling.py -q
    /usr/bin/time -v curl -s -o /dev/null "http://127.0.0.1:7070/folders?path=/&recursive=1&page=1&page_size=200"
    /usr/bin/time -v curl -s -o /dev/null "http://127.0.0.1:7070/index.html"

Run targeted checks after each sprint and full checks at end.

    pytest tests/test_refresh.py -q
    pytest tests/test_memory_index_performance.py -q
    pytest tests/test_remote_worker_scaling.py -q
    pytest -q
    cd frontend && npm run test && npm run build
    cp -r dist/* ../src/lenslet/frontend/

### Task/Ticket Details


1. T1: Define strict recursive pagination contract for `/folders`.
Goal: define deterministic sort order, defaults (`page=1`, `page_size=200`), hard max clamp (`page_size<=500`), and invalid parameter behavior (`400` with explicit message).
Affected files/areas: `src/lenslet/server.py`, `src/lenslet/server_models.py`, `frontend/src/lib/types.ts` if schema fields change.
Validation: API tests cover defaulting, clamping, invalid params, and deterministic ordering across repeated calls.

2. T2: Implement bounded recursive item windowing.
Goal: support page-window retrieval without returning full recursive payload for each request.
Affected files/areas: recursive collection logic in `src/lenslet/server.py`.
Validation: tests assert page size bounds and no duplicate items across adjacent pages.

3. T3: Add recursive pagination abuse guards.
Goal: protect server from oversized recursive page requests and pathological parameters.
Affected files/areas: request parsing/validation in `src/lenslet/server.py`.
Validation: tests verify oversized `page_size` is clamped/rejected as defined and negative/zero values are rejected.

4. T4: Add backward compatibility strategy for existing recursive callers.
Goal: provide compatibility mode for legacy full-recursive behavior during rollout (for example via feature flag or explicit legacy query parameter).
Affected files/areas: `src/lenslet/server.py`, docs in `README.md` or `DEVELOPMENT.md`.
Validation: compatibility tests verify legacy path still returns prior shape while new paged path works.

5. T5: Add dedicated API contract tests for `/folders` pagination semantics.
Goal: make contract behavior durable for defaults, ordering, pagination metadata, and compatibility mode.
Affected files/areas: new tests under `tests/` (for example `tests/test_folder_pagination.py`).
Validation: targeted pytest module passes and fails deterministically on contract regressions.

6. T6: Extend frontend folder API client for paging.
Goal: expose `page` and `page_size` in `api.getFolder` and query key composition.
Affected files/areas: `frontend/src/api/client.ts`, `frontend/src/api/folders.ts`, `frontend/src/shared/api/folders.ts`.
Validation: frontend unit test verifies generated URL and cache-key separation by page parameters.

7. T7: Implement AppShell paged fetch lifecycle.
Goal: split fetch orchestration from UI merge so first page renders quickly and additional pages can load incrementally.
Affected files/areas: `frontend/src/app/AppShell.tsx`.
Validation: tests verify first page render without waiting for later pages and correct reset behavior on folder change.

8. T8: Implement AppShell paged merge/dedupe logic.
Goal: merge pages with no duplicates/gaps and stable order under refresh/refetch.
Affected files/areas: `frontend/src/app/AppShell.tsx`, potential helper module under `frontend/src/features/browse/model/`.
Validation: unit tests assert no duplicates and no missing items across multi-page merges.

9. T9: Remove recursive subtree counting from HTML shell render.
Goal: ensure `render_index` does not call `og.subtree_image_count`.
Affected files/areas: `src/lenslet/server.py` in `_register_index_routes`.
Validation: backend test monkeypatches `og.subtree_image_count` to fail if called during `/index.html`; route returns 200 with expected tags.

10. T10: Keep OG metadata lightweight with fallback count behavior.
Goal: preserve OG tags while relying on cheap count sources (or omitting expensive scope counts) on shell route.
Affected files/areas: `src/lenslet/server.py`, optional update to `src/lenslet/cli.py` help/defaults if behavior flagging changes.
Validation: tests verify OG tags still render and no recursive traversal occurs.

11. T11: Implement local-file streaming path for `/file`.
Goal: use `FileResponse` or equivalent file-backed streaming for local sources.
Affected files/areas: `src/lenslet/server.py`, storage path exposure in `src/lenslet/storage/memory.py` and `src/lenslet/storage/table.py` as needed.
Validation: tests verify local file responses stream correctly and return expected MIME type.

12. T12: Define and validate non-local `/file` fallback behavior.
Goal: keep remote/S3/HTTP behavior correct when local streaming is unavailable.
Affected files/areas: `src/lenslet/server.py`, `src/lenslet/storage/table.py`, `src/lenslet/storage/dataset.py`.
Validation: tests verify remote paths still return valid payloads and error handling remains stable.

13. T13: Remove non-essential full-file prefetch on folder load.
Goal: stop automatic first-five full-file prefetch burst on folder change.
Affected files/areas: `frontend/src/app/AppShell.tsx`.
Validation: tests verify folder navigation with viewer closed does not trigger folder-level full-file prefetch.

14. T14: Restrict full-file prefetch to explicit viewer/compare contexts.
Goal: retain useful neighbor prefetch but keep strict bounds.
Affected files/areas: `frontend/src/app/AppShell.tsx`, `frontend/src/api/client.ts`.
Validation: instrumentation tests assert bounded prefetch count per viewer/compare navigation step.

15. T15: Move thumbnail prefetch scheduling out of render body.
Goal: remove render-phase side effects from `VirtualGrid`.
Affected files/areas: `frontend/src/features/browse/components/VirtualGrid.tsx`.
Validation: component tests assert prefetch calls occur only in effects.

16. T16: Add frontend cache retention/eviction policy for paged recursive data.
Goal: prevent unbounded client memory growth during long-scroll paged browsing.
Affected files/areas: `frontend/src/api/folders.ts`, query options in `frontend/src/app/AppShell.tsx`.
Validation: tests verify old pages are evicted or bounded according to policy.

17. T17: Reuse boto3 client/session per storage instance.
Goal: avoid repeated `boto3.client("s3")` construction in table/dataset paths.
Affected files/areas: `src/lenslet/storage/table.py`, `src/lenslet/storage/dataset.py`.
Validation: tests monkeypatch client creation and assert one client/session initialization per storage instance.

18. T18: Cancel thumbnail work on disconnect for both queued and in-flight states.
Goal: wire request disconnect handling to scheduler cancellation and cleanup.
Affected files/areas: `src/lenslet/server.py`, optional scheduler guards in `src/lenslet/thumbs.py`.
Validation: async tests separately cover queued-cancel and in-flight-cancel paths with assertions on scheduler state cleanup.

19. T19: Add observability counters/timers for hot-path behavior.
Goal: expose metrics for recursive traversal calls, `/file` response mode, full-file prefetch counts, thumb cancellations, and S3 client creations.
Affected files/areas: `src/lenslet/server.py` and related helpers, docs notes.
Validation: tests or scripted checks confirm counters increment under controlled scenarios.

20. T20: Add backend regression suites for folder pagination, OG shell, `/file`, and cancellation.
Goal: lock backend behavior changes across memory/table/dataset modes where applicable.
Affected files/areas: `tests/` modules (new + existing).
Validation: targeted backend suites pass and fail deterministically when behavior is intentionally regressed.

21. T21: Add frontend regression suites for paging merge, prefetch policy, and render purity.
Goal: ensure UI behavior remains correct and bounded under paged recursive loading.
Affected files/areas: frontend tests under `frontend/src/app` and `frontend/src/features/browse`.
Validation: `cd frontend && npm run test` passes with new suites.

22. T22: Update docs and verify packaged frontend assets are served.
Goal: document changed interfaces/flags, rollout/compatibility behavior, deferred backlog, and ensure build artifacts are copied to `src/lenslet/frontend/`.
Affected files/areas: `README.md`, `DEVELOPMENT.md`, this plan file, and packaged assets.
Validation: `cd frontend && npm run build && cp -r dist/* ../src/lenslet/frontend/` followed by backend smoke test for `/index.html` asset loading.


## Validation and Acceptance


Performance gates are mandatory and must be measured baseline-vs-post on the same machine/profile.

1. `/folders` gate.
`GET /folders?path=/&recursive=1&page=1&page_size=200` p95 response time improves by at least 30% from baseline, and does not regress more than 10% on small datasets.

2. `/index.html` gate with OG preview enabled.
p95 response time improves by at least 30% from baseline, and tests prove `og.subtree_image_count` is not called in HTML render path.

3. `/file` memory gate.
For large local files, peak RSS delta during transfer is bounded and reduced versus baseline (target: at least 40% reduction relative to prior full-byte path).

4. Prefetch gate.
When viewer is closed, folder-switch full-file speculative prefetch count is zero. In viewer/compare modes, full-file prefetch count stays within defined bounds per navigation action.

Sprint S1 acceptance requires stable paged recursive contract behavior: deterministic order, no duplicates/gaps across pages, valid defaults/clamps, and compatibility mode behavior documented and tested.

Sprint S2 acceptance requires no recursive count work in HTML shell route and validated split behavior for local streaming vs non-local fallback in `/file`.

Sprint S3 acceptance requires no prefetch side effects in render, S3 client/session reuse in both table and dataset storages, and verified queued/in-flight cancellation behavior.

Sprint S4 acceptance requires passing targeted backend/frontend suites, successful frontend packaging copy into `src/lenslet/frontend/`, and docs updated to match actual interfaces and deferred scope.

Overall acceptance scenario is a high-fanout dataset browse session where root/scope shell appears quickly, recursive items load incrementally, OG-enabled shell render does not stall, full-file memory usage remains bounded during browsing, and disconnected thumbnail requests do not continue consuming workers.


## Idempotence and Recovery


Folder paging is request-idempotent by (`path`, `recursive`, `page`, `page_size`, compatibility selector), so retries are safe.

If pagination rollout introduces client regressions, compatibility mode allows temporary fallback to legacy recursive behavior while keeping new code deployable. Rollback requires route-level behavior switch and does not require data migration.

OG shell-path changes are read-only behavior changes; rollback is route logic only.

`/file` local streaming and non-local fallback changes are stateless; rollback restores prior response construction behavior.

S3 reuse and cancellation changes are runtime improvements. If issues appear, rollback is isolated to request handling/storage helper logic.


## Artifacts and Notes


Proposed recursive paging request shape example.

    GET /folders?path=/&recursive=1&page=1&page_size=200

Proposed `/folders` contract constraints example.

    default page=1
    default page_size=200
    max page_size=500
    page<1 => 400
    page_size<1 => 400
    page_size>500 => clamp to 500

Pseudo-check for OG shell path regression.

    monkeypatch og.subtree_image_count to raise AssertionError
    request GET /index.html
    assert status_code == 200

Pseudo-check for queued and in-flight cancellation.

    queued test: submit then disconnect before worker start, assert inflight entry removed
    in-flight test: disconnect during work, assert future cancelled/cleanup path invoked

Review artifact path.

    docs/20260206_hotpath_performance_execution_plan_review.txt

Revision note: Updated on 2026-02-06 after pseudo-subagent review to add measurable performance gates, strict pagination contract details, compatibility/abuse safeguards, observability, split oversized tickets, packaging verification, and explicit schema/client dependency handling.


## Interfaces and Dependencies


The backend `/folders` interface adds bounded recursive pagination semantics (`page`, `page_size`) with explicit defaults, clamping, invalid-input behavior, and deterministic ordering guarantees. Compatibility behavior for legacy recursive callers must be explicitly documented and tested.

Pagination metadata fields in backend models and frontend types must remain backward-compatible where possible and be updated consistently in `src/lenslet/server_models.py` and `frontend/src/lib/types.ts`.

Frontend folder data layer (`frontend/src/api/folders.ts`) must include page parameters in query keys to avoid cache collisions and stale page mixing.

The backend `/file` handler in `src/lenslet/server.py` must prefer local file-backed streaming responses and retain non-local fallback behavior.

Storage backends in `src/lenslet/storage/table.py` and `src/lenslet/storage/dataset.py` maintain reusable S3 client/session objects per storage instance for presign operations.

Thumbnail handling remains on `ThumbnailScheduler` in `src/lenslet/thumbs.py`, with explicit disconnect cancellation wiring from `src/lenslet/server.py`.

No new third-party dependencies are required for scoped changes. Existing dependencies in use are FastAPI/Starlette response primitives, React Query for incremental frontend data loading, and boto3 for S3-presign support.
