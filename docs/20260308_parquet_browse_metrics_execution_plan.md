# Parquet Browse and Metric Sort Recovery Plan


## Outcome + Scope Lock


This plan closes the remaining user-facing failures on the standalone parquet path. After implementation, a user should be able to launch:

    lenslet /local/yada/dev/aeslib/ongoing/11_retrain_old_scores_on_siglip2/outputs/vqr1_concat.parquet --share

and then browse the parquet root, enter large child folders, view images, sort by `quality_score`, and filter by `quality_score` without synthetic parquet index columns leaking into the UI.

Goals are narrow. The work should make the current parquet browse path function correctly at the user-reported scale, keep the local path boundary conservative, and remove obvious metric-schema noise. Non-goals are a broad browse protocol redesign, a generic pagination system for every storage backend, or a global weakening of filesystem safety limits.

Pre-approved behavior changes are limited to adding explicit metric-key metadata to the folder payload, filtering internal parquet index columns out of metric exposure, and replacing the current large-table recursive failure path with a table-aware browse path that preserves existing security boundaries. The repo is on a hard-cutover posture, so normal browse mode should move to the explicit folder contract rather than carrying a compatibility fallback for older folder payloads. Anything broader, especially a cross-backend recursive contract rewrite or a global increase to recursive traversal limits for filesystem storage, should be treated as deferred unless explicitly re-approved.

Deferred and out-of-scope items include query-language expansion, new histogram interaction features, table pagination UX, any redesign of large-folder session hydration or re-entry caching, any rewrite of search or similarity metric discovery unless it becomes strictly necessary, and any performance work not needed to make this parquet load, sort, and filter correctly.


## Context


The repo already contains one relevant fix on `main`: commit `b410d4d` introduced safe standalone parquet root detection plus clearer boundary logging for local-path cutoffs. That closed the earlier `0`-results failure caused by using the parquet’s parent directory as an overly strict local-file boundary.

The remaining issue is not parquet ingestion. On the current codebase, the user parquet does expose `quality_score` as a metric on item payloads. Direct inspection of `/folders?path=/pixai-aes-1.2-train-val-images` returns item metrics containing both `quality_score` and the synthetic pandas column `__index_level_0__`.

The mismatch is between inspector rendering and metric discovery for sort/filter. The inspector renders the selected item’s `metrics` directly. The sort and filter affordances do not use an explicit metric schema; they infer metric keys from the currently loaded gallery items. That inference path depends on a recursive folder fetch.

Large table scopes currently fail on that recursive path. The server enforces a hard recursive item limit of `10_000`. The user’s table-backed folder `/pixai-aes-1.2-train-val-images` contains `19,456` items, so recursive `/folders` requests return `413`. That leaves the frontend without a reliable metric catalog for sort/filter discovery even though individual item metrics are valid.

There is also a separate hygiene bug: table metric extraction currently treats synthetic parquet/pandas index columns such as `__index_level_0__` as user metrics. That pollutes any metric-key list and should be removed at the source.

The current worktree is not fully clean. There is an unrelated local modification in `pyproject.toml` that should stay out of future browse/metric commits unless intentionally included.


## Interfaces and Dependencies


This plan expects one small contract change: `FolderIndex` should expose a stable `metricKeys` list on all folder payloads so the frontend does not have to guess metric availability from whichever items happen to be loaded. Normal browse mode should then use that contract as its single source of truth. Search and similarity mode are explicitly excluded from this contract change unless implementation proves they must be updated to close the primary user path.

The likely change surface is small and concrete: backend browse/model code under `src/lenslet/server_models.py`, `src/lenslet/server_browse.py`, and table metric extraction in `src/lenslet/storage/table_index.py`; frontend consumption in `frontend/src/lib/types.ts`, `frontend/src/api/folders.ts`, `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/app/model/appShellSelectors.ts`, and `frontend/src/app/AppShell.tsx`; plus regenerated packaged assets under `src/lenslet/frontend/` after the frontend build.


## Plan of Work


The implementation should stay focused on the user’s real failure path: large standalone parquet browse plus metric sort/filter. Do not solve this by layering more frontend guesswork on top of incomplete backend signals. Fix the browse path, expose explicit metric keys, and remove internal metric noise.

Scope budget: three demoable sprints, seven atomic tasks, and the minimum module touch set needed to change the backend contract, repair the large-table browse path, and wire the frontend to the explicit metric list. Keep filesystem recursive behavior unchanged outside the table-backed path unless a later validation proves that broader work is necessary.

Guardrails: keep the local source boundary conservative, do not auto-widen access outside the existing safe-root rules, keep the global recursive hard limit for generic filesystem traversal, avoid introducing pagination or a new browse protocol unless the primary acceptance path still fails without it, and do not let this sprint expand into session-cache redesign for folders above `10_000` items.

While implementing each sprint, update this document continuously, especially the Progress Log, Validation and Acceptance section, and Artifacts and Handoff. After each sprint is complete, add clear handoff notes before moving on.

For minor script-level uncertainties such as exact test placement or helper-file location, proceed according to this plan to maintain momentum. After the sprint, record the choice here and apply follow-up adjustments only if the result is materially awkward.

Delegate subagents early to find the real codepaths and diff surface when that reduces context load or speeds up execution. Let those subagents run long enough to produce useful results; if work is still in progress after 10 minutes, ask for a short progress update and the reason more time is needed.

### Sprint Plan

1. Sprint 1 restores explicit metric contract and metric hygiene.
   Sprint goal: make metric availability explicit and remove internal parquet index columns from user-visible metrics.
   Demo outcome: folder payloads expose `metricKeys` including `quality_score` and excluding `__index_level_0__`.
   Tasks:
   - T1. Filter internal parquet index columns such as `__index_level_0__` out of both scalar-column and nested `metrics`-map extraction paths, and add targeted backend tests for both sources.
   - T2. Add `metricKeys` to `FolderIndex` payload generation with stable ordering and backend coverage for table-backed folders.

2. Sprint 2 removes the large-table browse failure on the real parquet path.
   Sprint goal: large table-backed scopes should load instead of failing the recursive browse path at `10_000` items.
   Demo outcome: `/folders` for the user parquet root and large child folder returns browseable data instead of `413`.
   Tasks:
   - T3. Add a narrow table-only bypass for the recursive hard-limit path so table-backed scopes above `10_000` items succeed while generic filesystem recursive traversal keeps returning `413`.
   - T4. Add backend regression tests proving that table recursive `>10k` succeeds while filesystem recursive `>10k` still returns `413`.
   - T5. Re-validate the real parquet path with direct API checks against the user dataset.

3. Sprint 3 wires the frontend to the explicit metric contract and validates the end-to-end user path.
   Sprint goal: normal browse sort and filter controls should use backend-provided metric keys rather than guessed keys from partially loaded items.
   Demo outcome: the UI offers `quality_score` for sort and metric-range filtering on the user parquet path.
   Tasks:
   - T6. Update shared folder types plus one central normal-browse metric source so browse mode consumes `FolderIndex.metricKeys`, and delete item-derived browse inference plus obsolete tests tied to that fallback path.
   - T7. Add frontend tests for metric sort/filter option visibility, add a focused browser acceptance probe on the recursive large-table path by extending existing Playwright tooling, rebuild packaged frontend assets, and run the primary real-scenario validation.

### Task gate routine

0. Plan gate (fast)
   Before each task, restate the goal, acceptance criteria, and exact files to touch in one short note.

1. Implement gate (correctness-first)
   Implement the smallest coherent slice that satisfies the task.
   Run the minimal verification signal immediately after the change, such as targeted pytest, targeted vitest, or a direct API probe.

2. Cleanup gate (reduce noise before review)
   After each sprint is complete, spawn a subagent and instruct it to use the `code-simplifier` skill to scan the current sprint changes conservatively.

### code-simplifier routine

Use the cleanup pass for non-semantic improvements first: formatting and lint autofixes, obvious dead code removal, small readability edits that do not change behavior, and comments or docs that reflect what is already true. Do not expand the pass into semantic refactors unless explicitly approved.

3. Review gate (review the ship diff)
   After cleanup, spawn a fresh agent and request a code review using the `code-review` skill. Apply fixes, then rerun review when needed to confirm the diff is ready.

### review routine

The review should focus on the post-cleanup sprint diff and specifically check for behavior regressions on large table browse, accidental weakening of path boundaries, missing contract alignment between backend and frontend, and insufficient validation against the real parquet scenario.


## Validation and Acceptance


Primary acceptance checks must prove the actual user path works, not merely that small fixtures pass.

Primary checks:

1. Launch the real parquet path:

       lenslet /local/yada/dev/aeslib/ongoing/11_retrain_old_scores_on_siglip2/outputs/vqr1_concat.parquet --share

   Expected outcome: startup completes without boundary-related item loss, the app is browseable, and no large-scope folder load fails with `413`.

2. Validate direct API behavior on the real parquet path.

       GET /folders?path=/
       GET /folders?path=/&recursive=true
       GET /folders?path=/pixai-aes-1.2-train-val-images
       GET /folders?path=/pixai-aes-1.2-train-val-images&recursive=true

   Expected outcome: all four payloads are successful, neither recursive request returns `413`, table-backed recursive results remain browseable above `10_000` items, and the successful folder payloads contain `metricKeys` including `quality_score` while excluding `__index_level_0__`.

3. Validate UI behavior in the real scenario with browser automation.

   Expected outcome: on the recursive large-table browse path for the real parquet or an equivalent large-table fixture, the sort menu exposes `quality_score`, the metrics panel exposes `quality_score`, changing metric sort direction reorders visible items, and a `quality_score` range filter visibly narrows the result set. The same UI path must not expose `__index_level_0__`. Prefer extending the existing Playwright probe infrastructure rather than relying on manual inspection alone.

Secondary fast checks:

1. Backend targeted tests.

       pytest tests/test_parquet_ingestion.py tests/test_table_index_pipeline.py

2. Add and run focused backend tests for metric hygiene and recursive browse behavior.

       pytest <new backend test targets covering scalar metrics, metrics-map metrics, table recursive >10k, and filesystem recursive >10k>

3. Frontend targeted tests.

       cd frontend && npm run test -- --run <new metric browse tests covering payload-driven metric keys>

4. Focused Playwright acceptance.

       python scripts/gui_smoke_acceptance.py
       python scripts/gui_jitter_probe.py <targeted args or extended probe path>

5. Repo lint.

       python scripts/lint_repo.py

6. Frontend package sync after any frontend code change.

       cd frontend && npm run build
       rsync -a --delete frontend/dist/ src/lenslet/frontend/

Sprint 1 completed checks on 2026-03-08:

    pytest tests/test_table_index_pipeline.py -q
    pytest tests/test_parquet_ingestion.py -q
    pytest tests/test_table_index_pipeline.py tests/test_parquet_ingestion.py -q
    python scripts/lint_repo.py

Observed outcome: the new table-index coverage proves synthetic parquet index columns are removed from both scalar metric-column extraction and nested `metrics`-map extraction, table-backed folder payloads now expose sorted `metricKeys` on both non-recursive and recursive fixture paths, and repo lint passes.

Overall acceptance is not met until the real parquet scenario can browse and expose `quality_score` for sort/filter without leaking `__index_level_0__` and without widening the local source boundary beyond the safe-root rules already in place.


## Risks and Recovery


The main risk is solving the metric UI symptom while leaving the large-table browse path unstable. That would preserve the user’s real failure under load or on another large parquet. The plan therefore requires at least one sprint to change the large-table browse path directly rather than only patching frontend metric inference.

Another risk is broadening recursive responses so far that generic filesystem traversal regresses. Recovery should be storage-specific. If a table-backed fast path proves too heavy, roll back only the table-specific branch and keep the existing filesystem cap intact.

The payload contract change should stay additive at the wire level but hard-cutover in normal browse behavior. Recovery should prefer making `metricKeys` available on all `FolderIndex` payloads rather than reintroducing item-derived inference in normal browse mode. Search and similarity are intentionally excluded from this plan unless they block the primary acceptance path.

Idempotent retry strategy: after any failed sprint, restore a clean worktree, rerun the direct API probes against the user parquet, then reapply only the smallest missing slice. Do not stack speculative fixes across multiple layers before the primary scenario is retested.


## Progress Log


- [x] 2026-03-08 07:18 UTC Reproduced the standalone parquet `0`-results failure caused by an overly strict local root derived from the parquet parent directory.
- [x] 2026-03-08 07:29 UTC Shipped and pushed the safe standalone parquet root detection and clearer boundary logging fix in commit `b410d4d`.
- [x] 2026-03-08 07:41 UTC Verified the real parquet’s non-recursive folder payload contains `quality_score` in item metrics.
- [x] 2026-03-08 07:41 UTC Verified the same payload also contains synthetic `__index_level_0__`, confirming metric hygiene work is needed.
- [x] 2026-03-08 07:42 UTC Verified recursive `/folders` requests for `/` and `/pixai-aes-1.2-train-val-images` fail at the current `10_000` hard limit.
- [x] 2026-03-08 07:44 UTC Confirmed frontend metric sort/filter discovery is based on loaded gallery items rather than an explicit metric schema.
- [x] 2026-03-08 07:54 UTC Locked the Sprint 1 backend contract: `FolderIndex.metricKeys` is the explicit browse metric schema, and parquet metric hygiene is enforced at table extraction time rather than filtered in the frontend.
- [x] 2026-03-08 07:59 UTC Completed T1 in `src/lenslet/storage/table_index.py` by filtering synthetic `__index_level_<n>__` keys from both scalar metric columns and nested `metrics` maps, with focused coverage in `tests/test_table_index_pipeline.py`.
- [x] 2026-03-08 08:00 UTC Completed T2 in `src/lenslet/server_models.py` and `src/lenslet/server_browse.py` by exposing sorted `metricKeys` on folder payloads and covering both non-recursive and recursive table-backed API responses in `tests/test_parquet_ingestion.py`.
- [x] 2026-03-08 08:01 UTC Ran Sprint 1 validation (`pytest tests/test_table_index_pipeline.py tests/test_parquet_ingestion.py -q` and `python scripts/lint_repo.py`); all checks passed and no Sprint 1 cleanup/review blockers were found.
- [ ] Next operator: keep the unrelated local `pyproject.toml` edit out of the next commit unless it is explicitly approved.
- [ ] Next operator: start Sprint 2 in `src/lenslet/server_browse.py` with a table-only recursive-limit bypass and regression coverage that keeps generic filesystem recursive traversal capped at `10_000`.


## Artifacts and Handoff


Observed API notes from the real parquet path:

    /folders?path=/pixai-aes-1.2-train-val-images -> 200
    first item metrics keys -> ['__index_level_0__', 'quality_score']
    first item quality_score -> 4.85

    /folders?path=/pixai-aes-1.2-train-val-images&recursive=true -> 413

Relevant codepaths already identified:

    backend metric extraction: src/lenslet/storage/table_index.py
    backend folder payload model: src/lenslet/server_models.py
    backend folder assembly and recursive limit: src/lenslet/server_browse.py
    frontend folder load path: frontend/src/app/hooks/useAppDataScope.ts
    frontend metric-key inference: frontend/src/app/model/appShellSelectors.ts
    frontend metric sort/filter wiring: frontend/src/app/AppShell.tsx
    inspector metric rendering: frontend/src/features/inspector/sections/BasicsSection.tsx

Sprint 1 artifacts:

    backend contract change:
    FolderIndex.metricKeys now ships sorted metric keys on folder payloads.

    metric hygiene change:
    synthetic parquet index keys matching __index_level_<n>__ are excluded from scalar metric columns and nested metrics maps before item metrics are assembled.

    focused validation:
    tests/test_table_index_pipeline.py
    tests/test_parquet_ingestion.py

Handoff notes:

Continue from the current worktree and keep unrelated edits out of the next diff unless they become intentionally relevant. Sprint 1 is closed; the next slice is the narrow table-only recursive browse fix in `src/lenslet/server_browse.py` plus regression coverage proving filesystem recursive traversal still returns `413` above `10_000` items. Treat the real parquet command above plus the two recursive `/folders` calls as the primary acceptance target for every remaining sprint. Do not expand this work into large-folder session-cache redesign unless the primary path still fails after the narrow table-only browse fix. When revising this document, add a short note at the bottom describing what changed and why.

Revision note, 2026-03-08: tightened the plan after review feedback to require explicit recursive acceptance checks, remove normal-browse fallback language, collapse browse-mode metric contract work into one hard-cutover task, narrow Sprint 2 to a table-only recursive-limit bypass, add stronger regression-test requirements, add Playwright-backed UI validation, and replace an unsafe worktree-cleanup instruction with a commit-scope instruction.
Revision note, 2026-03-08 08:01 UTC: recorded Sprint 1 completion, documented the shipped `metricKeys` backend contract and parquet metric hygiene change, added the exact Sprint 1 validation commands/outcomes, and updated handoff notes to point the next operator at the table-only recursive-limit bypass in Sprint 2.
