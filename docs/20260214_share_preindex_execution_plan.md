# Lenslet Share Preindex Execution Plan


## Outcome + Scope Lock


After this implementation, the share URL is only printed after a full preindex completes, and the first browser load is immediately browseable with all dimensions ready. The system always preindexes for share, with no bypass and no partial totals. Recursive browse returns the full list in one response, and pagination or background hydration logic is removed from the default path. The `--no-write` mode is eliminated as a behavior branch; all modes write to a temp workspace under `/tmp` with a 200 MB thumbnail cache cap when the target workspace is not writable.

Goals are to make shared galleries instantly usable at the time the URL is issued, eliminate UI refresh churn from page hydration, and reduce branching by converging on a single preindexed path. Non-goals are broad UI redesign, mobile performance work beyond the browse flow, or new distributed indexing services. Contract changes are pre-approved; this plan assumes removing recursive pagination semantics from `/folders?recursive=1` and removing related frontend hydration.

Deferred and out-of-scope items include incremental live-update sorting while indexing, advanced background indexing pipelines, and any new remote persistence service. If those are needed later, they should be handled in a follow-up plan after this preindex-first path is stable.


## Context


No `PLANS.md` exists in this repository, so this plan is the execution source-of-truth. The prior browse-responsiveness plan focused on incremental hydration and pagination but did not satisfy the requirement that shared URLs be fully ready before being issued. The user confirmed that the share URL must only be printed after full indexing (including width/height), and approved contract changes. The user also confirmed that recursive browsing should return the full list in a single response and that `--no-write` should write to a temp workspace with a 200 MB thumbnail cache cap.

This plan replaces any residual “preindex optional” behavior. The design assumption is that index materialization is a prerequisite for serving the gallery, not something that happens while the end user waits at the URL.


## Interfaces and Dependencies


The `/folders` recursive contract will change. For recursive requests, pagination parameters and page metadata are removed or ignored, and the API returns the full item list with stable order. The frontend will no longer request recursive pages beyond the first. Existing consumers relying on pagination must be updated or removed as part of this plan. This change is explicitly approved.

Preindex outputs will be persisted under the workspace root (or `/tmp` workspace when the target is not writable). This introduces a dependency on a local writable cache directory and on `pyarrow` for Parquet output where available; a JSON fallback will be used only when Parquet is unavailable and with clear logging.


## Plan of Work


### Scope Budget and Guardrails


Budget is three sprints and nine tasks. The quality floor is immediate usability after share URL issuance, stable full-list browse response, and verified dimensions for all items. The maintainability floor is a single preindexed path with minimal branching and clear caching policy. The complexity ceiling prohibits adding new long-running services or remote dependencies.

While implementing each sprint, update this plan document continuously (especially Progress Log and any impacted sections). After each sprint is complete, add clear handoff notes. For minor script-level uncertainties (for example, exact helper placement), proceed according to the approved plan to maintain momentum. After the sprint, ask for clarifications and then apply follow-up adjustments.

### Sprint 1: Preindex Pipeline and Share Gating


Goal is to make preindexing mandatory for share and persistent for reuse, with complete width/height available before URL issuance.

Tasks (Sprint 1):
1. T1: Implement a preindex builder for local folder mode that enumerates all images, probes width/height, and writes an index payload (Parquet when available, JSON fallback) under the workspace or temp workspace. Include a dataset signature to detect reuse and invalidation.
2. T2: Wire CLI startup so `--share` blocks until preindex is complete, then prints the share URL. Remove or bypass any “serve before preindex” path. Add terminal indexing progress output that matches the preindex phase.
3. T3: On startup, load preindexed data into `TableStorage` when available, rather than building recursive folder indexes at request time.

### Sprint 2: Full Recursive Response and Frontend Simplification


Goal is to return the full recursive list in a single response and remove pagination/hydration churn in the UI.

Tasks (Sprint 2):
1. T4: Update `/folders?recursive=1` to return the full item list directly with stable ordering, and remove server-side recursive pagination and related cache pathways that are no longer used.
2. T5: Remove frontend recursive pagination hydration (`hydrateFolderPages`) and related periodic updates. Replace with a single recursive fetch that populates the grid, and keep a simple loading state until the data arrives.
3. T6: Remove request-budget entries and telemetry that were specific to recursive page hydration, and adjust any tests that depended on pagination.

### Sprint 3: Remove No-Write Mode and Enforce Temp Cache Cap


Goal is to unify cache behavior so “no write” always uses a temp workspace with bounded thumbnail caching.

Tasks (Sprint 3):
1. T7: Replace `--no-write` behavior with a temp workspace path under `/tmp/lenslet/<dataset-hash>/`, and set `Workspace.can_write` true for that temp workspace so normal cache paths operate.
2. T8: Implement a 200 MB disk cap for the thumbnail cache (LRU or oldest-first eviction) and apply it to temp workspaces. Keep browse cache cap as-is.
3. T9: Update docs and CLI banner text to reflect that “no-write” uses temp cache, and remove warnings that imply caches are disabled.

### Gate Routine (per task/ticket)


0) Plan gate (fast). Before implementing a task, restate the goal, acceptance criteria, and files to touch.

1) Implement gate (correctness-first). Implement the smallest coherent slice that satisfies the task and run its minimal validation command(s).

2) Cleanup gate (reduce noise before review). After each complete sprint, run the `code-simplifier` routine.

3) Review gate (review the ship diff). After each complete sprint, run the `review` routine.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan current sprint changes. Start with non-semantic cleanup first: formatting or lint autofixes, obvious dead code removal, small readability edits that do not change behavior, and doc/comments that reflect what is already true. Keep this pass conservative; do not expand into semantic refactors unless explicitly approved.

### review routine


After each complete sprint and after the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Review the post-cleanup diff, apply fixes, then rerun review when needed to confirm resolution.


## Validation and Acceptance


Primary gates must match the real user path: share URL is only issued after full preindex, and the first browser load is immediately browseable with all thumbnails and dimensions ready.

Primary checks:
1. `lenslet <dir> --share` prints indexing progress first, then prints share URL only after the preindex completes; the browser shows thumbnails immediately on load, without blank refresh churn or missing dimensions.
2. `GET /folders?path=/&recursive=1` returns the full item list in a single response and does not require any follow-up paging calls for the initial grid.

Secondary checks:
1. `pytest -q` with any updated tests for preindex persistence and full recursive response.
2. `python scripts/lint_repo.py`.
3. `python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json` updated to reflect full recursive response expectations.


## Risks and Recovery


The main risk is large JSON payload size when returning the full recursive list. Recovery is to keep the response compressed (FastAPI gzip) and to prefer preindexed table storage so items are served quickly from memory. If full-list response is too large for certain clients, reintroduce pagination behind an explicit opt-in flag in a follow-up plan rather than regressing the default path.

A second risk is slow preindexing for very large datasets. Recovery is to provide clear CLI progress output and to cache the preindex result keyed by dataset signature so repeat runs are fast.

A third risk is cache eviction policy complexity. Recovery is to implement a simple deterministic eviction strategy (oldest-first by file mtime) and keep it isolated to thumbnail cache paths only.


## Progress Log


- [x] 2026-02-14 00:00Z Plan drafted with explicit preindex-first share requirement, full recursive list response, and temp workspace cache policy based on user confirmation.
- [x] 2026-02-14 00:30Z Sprint 1 T1-T3: added local preindex builder with signature + Parquet/JSON outputs, gated share startup on preindex completion, and loaded preindex data into table storage when present.
- [x] 2026-02-14 00:40Z Sprint 1 validation: `python scripts/lint_repo.py` and `pytest -q` (warnings only).


## Artifacts and Handoff


Planned artifacts include a persisted preindex payload (Parquet or JSON) under the workspace or `/tmp` workspace path and updated CLI banners that reflect preindex and temp cache behavior. Handoff notes should include the dataset signature logic, the preindex output location, and any updated validation scripts.

Current implementation notes:
- Preindex outputs live under `<dataset>/.lenslet/preindex/` (or `/tmp/lenslet/<dataset-signature>/preindex/` when the dataset workspace is not writable).
- Payload files: `items.parquet` when `pyarrow` is available, otherwise `items.json`; metadata stored in `meta.json` with signature/version/row count.
- Signature is SHA-256 over the dataset root path plus sorted `(relative_path, size, mtime_ns)` tuples.

Plan revision note: this plan supersedes the previous browse-responsiveness approach by making preindex mandatory before share URLs, removing recursive pagination, and unifying “no-write” into temp workspace caching.
