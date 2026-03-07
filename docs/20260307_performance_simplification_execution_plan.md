# Lenslet Performance + Simplification Execution Plan


## Outcome + Scope Lock


After implementation, Lenslet closes every item in `docs/20260307_performance_simplification_review.md` except the user-deferred warm preindex startup scan. Users should be able to refresh and see every served surface update from the same storage/workspace state, browse recursively without paying the full metadata/stat path on the first recursive request, keep logical paths stable across dataset mode and table mode, search without mutating metadata state on misses, switch browse versus ranking mode without shipping the inactive app on the browse hot path, and open move/thumb flows without duplicate client work.

Goals: fix the remaining correctness and hot-path issues from the 2026-03-07 review, remove duplicate layers that no longer protect a real invariant, keep the work in hard-cutover form consistent with the repo’s alpha policy, and validate each sprint against the real browse path rather than proxy-only microbenchmarks.

Non-goals: changing warm preindex startup behavior, adding backward-compatibility shims, doing a full browse/ranking multi-entry rewrite, fully deleting `DatasetStorage` as a public mode, or fully removing `lenslet.server` as a public import facade.

Approvals: the following are pre-approved because they are direct closure of reviewed bugs or duplicate-layer cuts: introducing one mutable app context on `app.state`, hard-cutting `DatasetStorage` onto shared helper seams, path-scoped recursive disk invalidation, direct frontend `api/*` imports with deletion of `shared/api/*`, lazy loading ranking mode, deleting `ranking_old.css`, and adding one additive backend endpoint for move-target folder paths. Explicit sign-off is still required for separate browse/ranking entrypoints, full `DatasetStorage` removal as a distinct mode, full retirement of `lenslet.server` as a public facade, or any change to the deferred warm preindex behavior.

Deferred and out-of-scope items: “Stop doing a full scan on warm preindex startup,” optimistic preindex reuse/background validation, separate browse/ranking shells or entrypoints, full `DatasetStorage` removal as a separate path model, and repo-wide thumbnail URL unification outside the grid hot path unless Sprint 4 exposes a shared correctness bug.


## Context


No repo-level `PLANS.md` exists. This plan follows the active execution-doc style already used in `docs/20260219_safe_fallback_removal_plan.md` and `docs/20260217_500k_perf_execution_plan.md`.

The current server wiring already proves the root split: `src/lenslet/server_factory.py` swaps `StorageProxy` on `/refresh`, but `src/lenslet/server_routes_index.py`, `src/lenslet/server_routes_og.py`, and `src/lenslet/server_routes_views.py` still close over the original `storage` and `workspace`. The recursive browse hot path is also still split: `src/lenslet/server_browse.py` has `_recursive_index_getter()`, but `_collect_recursive_cached_items()` and `warm_recursive_cache()` still descend through `get_index()`, and `count_only` uses a separate walk that does not seed or reuse the snapshot cache. `src/lenslet/browse_cache.py` invalidates memory by scope but clears all persisted disk windows on any scoped refresh.

The storage layer still has two correctness bugs and one mutation bug. `src/lenslet/storage/dataset.py` still constructs `/{dataset}/{basename}` logical paths and silently overwrites duplicate basenames. `src/lenslet/storage/table_index.py` only honors `path_column` for non-S3 sources. `src/lenslet/storage/dataset.py`, `src/lenslet/storage/table_facade.py`, and `src/lenslet/storage/memory.py` all route search through `get_metadata()`, which creates default metadata on first read and permanently grows `_metadata` during a search-only miss path.

The duplication story is also concrete, not stylistic. `DatasetStorage` still duplicates S3 client creation, presigning, remote header probing, thumbnail creation, dimension parsing, metadata defaults, and search logic that table mode already extracted into `table_facade.py`, `table_media.py`, `table_probe.py`, and `table_paths.py`. On the frontend, `frontend/src/app/AppModeRouter.tsx` statically imports both `AppShell` and `RankingApp`, `frontend/src/shared/api/*` is an eight-file pure re-export layer, `frontend/src/features/ranking/ranking_old.css` is unreferenced, `frontend/src/app/AppShell.tsx` patches every cached folder/search result set on each live item update, `frontend/src/app/hooks/useAppActions.ts` ignores existing folder tree query state and starts a root BFS crawl for move targets, and `frontend/src/features/browse/components/ThumbCard.tsx` adds its own object-URL cache on top of the shared blob cache in `frontend/src/lib/blobCache.ts`.

Subagent review was run through local `codex exec` passes over backend/storage and frontend slices before this plan was finalized. Those passes confirmed the root paths above, confirmed that `MemoryStorage.hydrate_recursive_items()` is currently unused residue, and confirmed the current testing gaps: there is no refresh test that proves OG/index/views swap with `/refresh`, no dataset-mode test for nested paths plus duplicate basenames, no table-mode test for S3 `path_column`, no search test that asserts `_metadata` does not grow on misses, no frontend test for bundle splitting, no frontend test for item-update fanout scope, and no frontend test for move-dialog crawl or thumbnail URL lifecycle.

The user explicitly removed the warm preindex startup item from scope for this plan. The repo policy also explicitly allows hard cutovers and does not require backward compatibility, so this plan prefers deleting or collapsing duplicate paths over introducing migration layers.


## Interfaces and Dependencies


This plan introduces one additive backend interface and one internal runtime interface.

Internally, the server will move to a single mutable app context on `app.state` that owns the current `storage`, `workspace`, `runtime`, and cache-bound services. Route modules will resolve current state through that context instead of mixing closure-captured values with request-scoped storage.

At the API boundary, Sprint 4 adds one additive move-target read endpoint, `GET /folders/paths`, returning canonical folder paths for the current storage. The frontend move dialog will use that endpoint instead of client-side root BFS crawling. No existing endpoint is removed or widened by that addition.

The frontend delivery boundary changes in Sprint 4 are build-time only: `RankingApp` becomes a lazy chunk loaded through `import()`, while browse mode keeps the current boot-health contract and does not gain a new runtime API dependency.


## Plan of Work


While implementing each sprint, update this plan document continuously, especially the Progress Log and any sections impacted by discoveries. After each sprint is complete, add clear handoff notes in Artifacts and Handoff.

Before implementing any sprint, read `/root/.codex/skills/public/better-code/SKILL.md` and follow it during the code changes for that sprint.

For minor script-level uncertainties such as exact helper file placement, proceed according to this plan to maintain momentum. Do not use that latitude to make behavior changes silently. After the sprint, ask for clarifications only if the uncertainty affects ownership, naming, or follow-up cleanup.

### Scope Budget and Guardrails


Scope budget: 4 sprints, 12 tasks, touching only the modules on the root paths above plus directly related tests. No new third-party dependencies are allowed. At most one new backend context helper module and one new frontend query-index helper module should be introduced; anything broader needs a fresh scope check.

Quality guardrail: prefer one coherent cutover per root problem, not framework rewrites. For example, use one shared app-context access path instead of a second storage proxy layer, one no-create metadata read path instead of ad hoc search flags per backend, and one thumb URL ownership path instead of adding another browser cache. Do not accept a small-looking shortcut if it leaves the reviewed failure path intact.

Debloat and removal targets for this plan are:

- closure-captured route state in OG/index/views once app context exists
- `MemoryStorage.hydrate_recursive_items()` if no real caller remains after recursive hot-path cutover
- duplicated media/search/metadata helper code in `DatasetStorage`
- `frontend/src/shared/api/*`
- `frontend/src/features/ranking/ranking_old.css`
- the private `ThumbCard` object-URL cache and its per-card fetch path

Net-change measurement: capture `git diff --stat` after each sprint and record it in the handoff. For explicit cuts, also run:

    rg -n "hydrate_recursive_items" src tests
    rg -n "shared/api" frontend/src
    rg -n "ranking_old\\.css" frontend/src
    wc -l src/lenslet/storage/dataset.py frontend/src/app/AppShell.tsx frontend/src/features/browse/components/ThumbCard.tsx

Expected outcome: removed targets disappear where planned, and the largest touched files either shrink or move duplicated logic into existing shared helpers.

### Sprint Plan


1. Sprint 1 closes runtime correctness first. Demo outcome: `/refresh` updates request routes, OG, HTML shell, and views from one current app context, and the touched route modules stop depending on the internal `lenslet.server` seam for runtime state.
2. Sprint 2 closes storage correctness next. Demo outcome: dataset-mode paths keep nested structure and dedupe collisions, table-mode honors `path_column` even for S3 rows, and search misses no longer mutate metadata state.
3. Sprint 3 closes the recursive browse hot path. Demo outcome: first recursive browse uses the lightweight descendant path, recursive counts and payloads share one cache/traversal representation, and scoped refresh invalidates only overlapping persisted recursive windows.
4. Sprint 4 closes the frontend delivery and duplication items. Demo outcome: browse mode no longer ships ranking in its initial bundle, direct `api/*` imports replace `shared/api/*`, live item updates stop scanning every cached result set, move targets stop using client BFS, and `ThumbCard` stops owning a second thumb URL cache.

### Task Details


1. S1-T1 Introduce a single mutable app context on `app.state` and route accessors that expose the current `storage`, `workspace`, `runtime`, and recursive browse cache. Use that context everywhere a route needs mutable state, including `health()` in `src/lenslet/server_factory.py`, instead of mixing `StorageProxy`, `app.state.workspace`, and closure-captured values. Expected files: `src/lenslet/server_factory.py`, one new small context helper such as `src/lenslet/server_context.py`, and touched route modules. Validation: extend `tests/test_refresh.py` so `/health` asserts current workspace/runtime state after refresh, then run `pytest -q tests/test_refresh.py tests/test_parquet_ingestion.py`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the smallest coherent context cut plus the listed tests. 2 Cleanup gate run the code-simplifier routine after Sprint 1 completes. 3 Review gate run the review routine after cleanup.
2. S1-T2 Rewire OG, HTML shell, and views routes to resolve through the new app context on each request, then make `/refresh` swap only that context and the cache objects derived from it. Cache the frontend HTML shell once per process instead of rereading `index.html` on every request while these routes are open. Expected files: `src/lenslet/server_routes_index.py`, `src/lenslet/server_routes_og.py`, `src/lenslet/server_routes_views.py`, `src/lenslet/server_factory.py`, and refresh tests. Validation: add refresh-surface tests and run `pytest -q tests/test_refresh.py tests/test_hotpath_sprint_s4.py tests/test_parquet_ingestion.py`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the narrow route/context cut plus the listed tests. 2 Cleanup gate run the code-simplifier routine after Sprint 1 completes. 3 Review gate run the review routine after cleanup.
3. S1-T3 Remove the internal `lenslet.server` seam from the Sprint 1 route paths by moving the remaining shared helpers into leaf modules or explicit injected callables, while keeping `server.py` as the public import-contract facade. This is a partial seam retirement only for the touched routes; full facade removal stays deferred. Expected files: `src/lenslet/server.py`, `src/lenslet/server_routes_common.py`, touched route modules, and `tests/test_import_contract.py`. Validation: `pytest -q tests/test_import_contract.py tests/test_refresh.py`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the smallest seam cut that preserves the import contract. 2 Cleanup gate run the code-simplifier routine after Sprint 1 completes. 3 Review gate run the review routine after cleanup.
4. S2-T1 Add a no-create metadata read path for search across storage backends and switch search to it. The clean target is one shared helper contract used by `DatasetStorage`, `TableStorage`, and `MemoryStorage`, so a read-only search pass cannot grow `_metadata` on misses. Expected files: `src/lenslet/storage/table_facade.py`, `src/lenslet/storage/dataset.py`, `src/lenslet/storage/memory.py`, and search tests. Validation: add `_metadata` growth tests and run `pytest -q tests/test_search_text_contract.py`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the no-create read path plus the listed tests. 2 Cleanup gate run the code-simplifier routine after Sprint 2 completes. 3 Review gate run the review routine after cleanup.
5. S2-T2 Hard-cut `DatasetStorage` onto the existing shared helper seams in `table_paths.py`, `table_media.py`, `table_probe.py`, and `table_facade.py`, leaving only the dataset-specific index builder in `dataset.py`. Use that cut to replace `/{dataset}/{basename}` path construction with shared normalize/dedupe handling so nested local, S3, and HTTP sources keep stable logical paths and duplicate basenames dedupe instead of overwriting. Expected files: `src/lenslet/storage/dataset.py`, `src/lenslet/storage/table_paths.py`, shared helper modules, and dataset-path tests. Validation: add nested-path and duplicate-basename tests, then run `pytest -q tests/test_search_text_contract.py tests/test_dataset_http.py tests/test_hotpath_sprint_s4.py`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the shared-helper cutover plus the listed tests. 2 Cleanup gate run the code-simplifier routine after Sprint 2 completes. 3 Review gate run the review routine after cleanup.
6. S2-T3 Honor `path_column` for all rows, including S3 rows, inside `src/lenslet/storage/table_index.py`, then run the same normalize/dedupe path contract after choosing between `path_column` and derived logical path. Do not retain the current `not is_s3_uri(source)` guard. Expected files: `src/lenslet/storage/table_index.py` and `tests/test_table_index_pipeline.py`. Validation: add an S3 `path_column` case and run `pytest -q tests/test_table_index_pipeline.py`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the smallest coherent table-path fix plus the listed tests. 2 Cleanup gate run the code-simplifier routine after Sprint 2 completes. 3 Review gate run the review routine after cleanup.
7. S3-T1 Route recursive traversal, cache warmup, and stale-generation rebuilds through `_recursive_index_getter()` so descendant folders use `get_index_for_recursive()` on the real request path. Preserve full `get_index()` only for direct non-recursive folder views. If no real caller remains after this change, delete `MemoryStorage.hydrate_recursive_items()`. Expected files: `src/lenslet/server_browse.py`, `src/lenslet/storage/memory.py`, and recursive browse tests. Validation: add a first-recursive-request test proving no eager dimension/stat read and run `pytest -q tests/test_memory_index_performance.py tests/test_folder_recursive.py tests/test_hotpath_sprint_s3.py`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the recursive getter cut plus the listed tests. 2 Cleanup gate run the code-simplifier routine after Sprint 3 completes. 3 Review gate run the review routine after cleanup.
8. S3-T2 Unify recursive `count_only` and recursive payload requests behind one snapshot builder and one cached representation. The count path must read or seed the same snapshot cache the payload path uses, so the folder tree does not pay one walk to count and another to fetch payload. Expected files: `src/lenslet/server_browse.py`, `src/lenslet/browse_cache.py`, and folder-count tests. Validation: add count-plus-payload reuse tests and run `pytest -q tests/test_folder_recursive.py tests/test_hotpath_sprint_s3.py tests/test_browse_cache.py`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the shared snapshot path plus the listed tests. 2 Cleanup gate run the code-simplifier routine after Sprint 3 completes. 3 Review gate run the review routine after cleanup.
9. S3-T3 Make persisted recursive cache invalidation path-scoped in `src/lenslet/browse_cache.py` instead of clearing all disk windows on any scoped refresh. Reuse the cache file metadata already stored on disk; do not add a second persistence format. Expected files: `src/lenslet/browse_cache.py` and `tests/test_browse_cache.py`. Validation: add ancestor/descendant persistence cases and run `pytest -q tests/test_browse_cache.py`, then run `python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the scoped invalidation cut plus the listed tests. 2 Cleanup gate run the code-simplifier routine after Sprint 3 completes. 3 Review gate run the review routine after cleanup.
10. S4-T1 Split browse and ranking at the bundle boundary by converting `AppModeRouter` to lazy-load `RankingApp` with `import()` and `Suspense`, keeping browse boot-health parsing synchronous. In the same sprint, hard-cut all `frontend/src/shared/api/*` imports to `frontend/src/api/*` and delete `frontend/src/shared/api/*` plus `frontend/src/features/ranking/ranking_old.css`. Expected files: `frontend/src/app/AppModeRouter.tsx`, import sites under `frontend/src/`, and deleted shim/CSS files. Validation: `cd frontend && npm run test`, `cd frontend && npm run build`, plus `rg -n "shared/api|ranking_old\\.css" frontend/src`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the lazy-load plus direct-import cut and listed validations. 2 Cleanup gate run the code-simplifier routine after Sprint 4 completes. 3 Review gate run the review routine after cleanup.
11. S4-T2 Replace `updateItemCaches()` full query scans with path-addressed query patching and debounce or idle-commit the persisted-settings writes in `AppShell`. The minimal robust target is a small helper that records which query keys currently contain which item paths, then patches only those keys on repeated `item-updated` and `metrics-updated` traffic; do not add a broad client state store. Expected files: `frontend/src/app/AppShell.tsx`, one small helper module if needed, and related tests. Validation: add Vitest coverage for repeated live-update patching and persistence scheduling, then run `cd frontend && npm run test -- src/app/__tests__/liveUpdateCachePatch.test.ts src/app/__tests__/settingsPersistence.test.ts`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the smallest coherent cache-index cut plus the listed tests. 2 Cleanup gate run the code-simplifier routine after Sprint 4 completes. 3 Review gate run the review routine after cleanup.
12. S4-T3 Stop duplicating move-target discovery and thumb URL ownership. Add `GET /folders/paths` backed by current storage indexes for move destinations, switch `useAppActions` and `MoveToDialog` to that endpoint, and collapse `ThumbCard` onto the shared thumb/blob path so it no longer owns its own `BlobUrlCache` or per-card fetch cache. Defer viewer, compare, and inspector `useBlobUrl` unification unless this cut exposes a shared object-URL lifecycle bug. Expected files: `src/lenslet/server_routes_common.py` or a new narrow route helper, `frontend/src/app/hooks/useAppActions.ts`, `frontend/src/app/components/MoveToDialog.tsx`, `frontend/src/features/browse/components/ThumbCard.tsx`, and targeted tests. Validation: add endpoint and UI tests that open the move dialog and prove a single `GET /folders/paths` request replaces the old `/folders` BFS burst, add thumb URL lifecycle tests, run `cd frontend && npm run test -- src/app/__tests__/moveTargets.test.ts src/features/browse/components/__tests__/thumbUrlHook.test.ts`, then run `python scripts/gui_smoke_acceptance.py`. Gate routine: 0 Plan gate restate the task goal, acceptance, and touched files. 1 Implement gate land the endpoint plus shared thumb URL cut and the listed validations. 2 Cleanup gate run the code-simplifier routine after Sprint 4 completes. 3 Review gate run the review routine after cleanup.

### code-simplifier routine


After each sprint completes, spawn a subagent and instruct it to use the `code-simplifier` skill to scan the current sprint changes. Start with non-semantic cleanup only: formatting or lint autofixes, obvious dead-code removal, small readability edits that do not change behavior, and doc/comments that reflect what is already true. Keep this pass conservative and do not expand into semantic refactors unless explicitly approved.

### review routine


After each sprint completes and the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Review the post-cleanup diff, apply fixes, and rerun review when needed to confirm resolution.


## Validation and Acceptance


1. Sprint 1 primary acceptance (real scenario): the app serves one current runtime state after `/refresh`, including `/health`, OG, HTML shell, and views. Run:

    pytest -q tests/test_refresh.py tests/test_parquet_ingestion.py tests/test_hotpath_sprint_s4.py tests/test_import_contract.py

Expected outcome: refresh-specific tests prove `/refresh` updates `/health`, `/og-image`, `/index.html`, and `/views` after a storage/workspace swap, and the public `lenslet.server` import contract still passes.

2. Sprint 1 secondary checks (fast proxies): confirm the route split is gone in the touched files. Run:

    rg -n "workspace\\.load_views\\(|workspace\\.save_views\\(|_dataset_count\\(storage\\)|_dataset_label\\(workspace\\)" src/lenslet/server_routes_views.py src/lenslet/server_routes_index.py src/lenslet/server_routes_og.py

Expected outcome: direct closure-captured runtime usage is replaced by app-context accessors in those route files.

3. Sprint 2 primary acceptance (real scenario): dataset and table logical paths are stable, and search misses stay read-only. Run:

    pytest -q tests/test_search_text_contract.py tests/test_table_index_pipeline.py tests/test_dataset_http.py

Expected outcome: new tests cover nested dataset paths, duplicate basenames, S3 `path_column`, and `_metadata` size stability after search-only misses.

4. Sprint 2 secondary checks (fast proxies): confirm search no longer uses metadata-creating reads in its hot path. Run:

    rg -n "get_metadata\\(item\\.path\\)" src/lenslet/storage/dataset.py src/lenslet/storage/table_facade.py src/lenslet/storage/memory.py

Expected outcome: no search-path matches remain.

5. Sprint 3 primary acceptance (real scenario): recursive browse uses the lightweight path and large-tree browse stays warm-cache friendly. Run:

    pytest -q tests/test_memory_index_performance.py tests/test_folder_recursive.py tests/test_browse_cache.py tests/test_hotpath_sprint_s3.py
    python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json

Expected outcome: first recursive requests prove `get_index_for_recursive()` is used, count and payload share cache/traversal work, and scoped refresh does not wipe unrelated persisted recursive windows.

6. Sprint 3 secondary checks (fast proxies): confirm the recursive hot path no longer descends through full indexes and that unused residue is gone if planned. Run:

    rg -n "storage.get_index\\(child_path\\)|storage.get_index\\(canonical_path\\)" src/lenslet/server_browse.py
    rg -n "hydrate_recursive_items" src tests

Expected outcome: no descendant traversal or warmup calls remain on `get_index()`, and `hydrate_recursive_items` is either deleted or intentionally retained with a real caller.

7. Sprint 4 primary acceptance (real scenario): browse mode stops paying for ranking on boot, repeated live updates stop patching every cached result set, move targets stop using client BFS, and thumbnail loading still works. Run:

    cd frontend && npm run test -- src/app/__tests__/liveUpdateCachePatch.test.ts src/app/__tests__/settingsPersistence.test.ts src/app/__tests__/moveTargets.test.ts src/features/browse/components/__tests__/thumbUrlHook.test.ts
    cd frontend && npm run test
    cd frontend && npm run build
    python scripts/gui_smoke_acceptance.py

Expected outcome: the targeted frontend tests prove repeated `item-updated` and `metrics-updated` traffic only patches affected queries, move dialog loading issues a single `GET /folders/paths` request instead of a `/folders` crawl burst, thumbnail URLs flow through the shared path, the build emits at least one additional async JS asset for ranking mode, and GUI smoke passes with move dialog and browse interactions intact.

8. Sprint 4 secondary checks (fast proxies): confirm the shim layer and stale asset are gone, and the move/thumb hot path no longer uses the deleted layers. Run:

    rg -n "shared/api" frontend/src
    rg -n "ranking_old\\.css" frontend/src
    rg -n "collectMoveFolders|BlobUrlCache" frontend/src/app/hooks/useAppActions.ts frontend/src/features/browse/components/ThumbCard.tsx

Expected outcome: no matches remain.

9. Overall primary acceptance (real scenario): run the repository-level gates after all sprints. Run:

    python scripts/lint_repo.py
    pytest
    cd frontend && npm run test
    python scripts/gui_smoke_acceptance.py
    python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json

Expected outcome: the full suite passes and the reviewed user-facing failure paths are closed without reintroducing the deferred warm preindex work.

10. Overall secondary checks (fast proxies): record the simplification delta and the removal targets. Run:

    git diff --stat
    wc -l src/lenslet/storage/dataset.py frontend/src/app/AppShell.tsx frontend/src/features/browse/components/ThumbCard.tsx
    rg -n "shared/api|ranking_old\\.css|hydrate_recursive_items" frontend/src src tests

Expected outcome: the targeted duplicate layers are gone and the remaining large files have not grown without a documented reason.


## Risks and Recovery


The highest-risk dependency is the server runtime cut in Sprint 1. Refresh, OG, views, and HTML shell behavior all currently depend on slightly different runtime state shapes. Recovery path: revert the Sprint 1 commit as a unit or temporarily reintroduce a narrow compatibility wrapper around the new app context while keeping the new tests in place.

Sprint 2 risks breaking programmatic datasets and remote-source handling because `DatasetStorage` is duplicated today precisely where S3, HTTP, and local behaviors meet. Recovery path: revert the helper cutover as one commit, keep the new path/search tests, and reapply the cut in smaller helper slices until all source kinds pass.

Sprint 3 risks stale or mismatched persisted recursive cache windows if the scoped invalidation logic is wrong. Recovery path: clear the browse cache directory for the active workspace and rerun the targeted recursive tests before retrying. The retry is idempotent because the new invalidation logic only removes overlapping windows and can be rerun safely on an already-pruned cache.

Sprint 4 risks frontend asset drift and browser-side object-URL regressions. Recovery path: rebuild the frontend bundle immediately after the sprint, verify GUI smoke, and if needed revert only the move-target/thumb URL cut while keeping the safe deletions (`shared/api/*`, `ranking_old.css`) intact. If GUI smoke fails because of stale served assets, recopy the rebuilt `frontend/dist/*` bundle into `src/lenslet/frontend/` before retrying.


## Progress Log


- [x] 2026-03-07 02:39 UTC: Read `docs/20260307_performance_simplification_review.md` and locked scope to every item except the user-deferred warm preindex startup scan.
- [x] 2026-03-07 02:39 UTC: Direct code trace confirmed the root paths in server runtime wiring, recursive browse/cache, storage path/search behavior, and frontend delivery/cache churn.
- [x] 2026-03-07 02:40 UTC: Ran backend/storage and frontend subagent review passes via local `codex exec`; both confirmed the reviewed hotspots still exist and highlighted the missing validation around refresh surfaces, nested dataset paths, bundle splitting, move dialog crawl, and thumbnail URL lifecycle.
- [x] 2026-03-07 02:41 UTC: Ran the required plan review subagent and tightened Sprint 1 and Sprint 4 acceptance so `/health`, repeated live-update traffic, and move-dialog request shape are proven directly.
- [x] 2026-03-07 02:52 UTC: Started Sprint 1 and hard-cut the request path onto one `app.state` context, removing `StorageProxy` from the refresh-sensitive route path and binding requests to the current context.
- [x] 2026-03-07 03:01 UTC: Completed `S1-T1` and `S1-T2` by routing `/health`, `/og-image`, `/index.html`, and `/views` through request-time context lookups, caching `index.html` once per process, and adding refresh tests that swap storage, workspace, and runtime cache-bound services.
- [x] 2026-03-07 03:03 UTC: Completed `S1-T3` by removing the `lenslet.server` back-reference from the Sprint 1 route modules, moving shared common-route helpers into leaf modules, and adding import-contract coverage for the touched route files.
- [x] 2026-03-07 03:04 UTC: Validated Sprint 1 with `pytest -q tests/test_refresh.py tests/test_parquet_ingestion.py tests/test_hotpath_sprint_s4.py tests/test_import_contract.py` and `python scripts/lint_repo.py`; the cleanup pass needed no edits, and the review pass surfaced one runtime workspace carryover bug in `snapshotter`/`thumb_cache`, which was fixed and revalidated.
- [x] 2026-03-07 03:10 UTC: Closed the post-review follow-up by routing `/thumb` and `record_update` through the current runtime from app context, rebuilding workspace-bound runtime services on refresh swaps, and adding regression coverage that proves refreshed thumbnail cache and labels snapshot writes land in the new workspace.


## Artifacts and Handoff


Quick scan commands for the implementation pass:

    rg -n "get_index_for_recursive|_collect_recursive_cached_items|count_only|warm_recursive_cache" src/lenslet/server_browse.py
    rg -n "StorageProxy|register_og_routes|register_index_routes|register_views_routes|app.state.workspace" src/lenslet/server_factory.py src/lenslet/server_routes_*.py
    rg -n "path_column|get_metadata\\(item.path\\)|build_search_haystack|_probe_remote_dimensions" src/lenslet/storage/dataset.py src/lenslet/storage/table_index.py src/lenslet/storage/table_facade.py src/lenslet/storage/memory.py
    rg -n "AppModeRouter|updateItemCaches|collectMoveFolders|BlobUrlCache|shared/api|ranking_old\\.css" frontend/src

Handoff notes for the next operator:

- Implement in sprint order. Sprint 1 and Sprint 2 are correctness closures and should not be deferred behind frontend bundle work.
- Do not silently re-scope warm preindex startup into this plan.
- Keep the `lenslet.server` public facade and its import contract unless explicit approval expands scope.
- If Sprint 4 needs more than one new frontend helper module, stop and tighten the design; that is the easiest place for this plan to bloat.

Sprint 1 handoff:

- Completed tasks: `S1-T1`, `S1-T2`, `S1-T3`.
- Key cutover: added `src/lenslet/server_context.py`, moved refresh-sensitive routes onto request-time context lookups, cached the frontend HTML shell once per process, and rebuilt runtime cache-bound services when a refresh swaps to a different workspace root.
- Validation: `pytest -q tests/test_refresh.py tests/test_parquet_ingestion.py tests/test_hotpath_sprint_s4.py tests/test_import_contract.py` passed before and after the runtime follow-up; `python scripts/lint_repo.py` passed; the conservative `code-simplifier` pass reported no extra cleanup; the final re-review found no further actionable issues.
- Diff stat: `src/lenslet/server_browse.py | 3 +-, src/lenslet/server_factory.py | 251 +++++++++------, src/lenslet/server_routes_common.py | 587 ++++++++++++++++++++++++++++++++----, src/lenslet/server_routes_index.py | 17 +-, src/lenslet/server_routes_og.py | 41 +--, src/lenslet/server_routes_views.py | 16 +-, tests/test_import_contract.py | 15 +, tests/test_refresh.py | 126 ++++++++`.
- Next operator should start Sprint 2 with `S2-T1`, keeping the new app-context/runtime path intact while adding the no-create metadata read contract for search.

Revision note: this revised plan reordered the work so runtime and storage correctness land before recursive and frontend delivery changes, tightened the Sprint 4 scope to additive move-path and thumb-path cuts instead of broader UI rewrites, and, after required subagent review, added direct acceptance for `/health`, repeated live-update traffic, and move-dialog request shape.
