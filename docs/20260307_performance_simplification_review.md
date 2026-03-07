# 2026-03-07 Performance + Simplification Review

## Scope

This review used the `better-code`, `code-review`, and `code-simplifier` lenses together.

I kept only changes with direct code evidence, a local repro, build output, or existing test coverage. I did not elevate file length or abstraction style by itself into a finding.

Working acceptance criteria:

- warm local startup on a reused preindex should not require a full filesystem walk
- recursive browse on `MemoryStorage` should use the lightweight descendant path on the real request path
- `/refresh` must update every served surface, not only request-scoped API routes
- logical paths must stay stable across dataset mode, table mode, and S3-backed rows
- frontend mode switching should not ship the inactive app on the hot browse path
- duplicated layers should survive only if they preserve a real invariant

Evidence used:

- local code inspection across `src/lenslet/` and `frontend/src/`
- `npm run build` in `frontend/`
  - produced one `dist/assets/index-CeQnSrCd.js` chunk at `554.60 kB` minified / `171.04 kB` gzip, with Vite's chunk-size warning
- `pytest -q tests/test_preindex_fastpath.py tests/test_refresh.py tests/test_import_contract.py`
  - `14 passed in 0.89s`
- delegated storage review validation:
  - `pytest -q tests/test_table_index_pipeline.py tests/test_search_text_contract.py tests/test_search_source_contract.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_dataset_http.py tests/test_table_security.py tests/test_remote_worker_scaling.py`
  - `34 passed in 1.24s`

## Priority Order

### P0

1. Stop doing a full scan on warm preindex startup.
   - Why: `ensure_local_preindex()` scans before it can decide reuse, so a reused preindex still pays whole-tree startup latency.
   - Evidence: `src/lenslet/preindex.py:78-99`, `src/lenslet/server_factory.py:470-511`, `src/lenslet/server_factory.py:578-585`
   - Concrete change: collapse freshness/reuse into one contract. Either:
     - Tier 2: persist and trust a cheaper reuse token, rebuilding only on mismatch or explicit refresh
     - Tier 3: optimistic reuse plus background validation/invalidation
   - Missing guardrail: current tests assert fast local validation wiring, but not warm-start no-scan behavior.

2. Put recursive browse on the actual lightweight index path.
   - Why: `_collect_recursive_cached_items()` and `warm_recursive_cache()` descend through `get_index()` instead of `get_index_for_recursive()`, so the first recursive browse still pays full stat/dimension work.
   - Evidence: `src/lenslet/server_browse.py:169-210`, `src/lenslet/server_browse.py:365-391`, `src/lenslet/storage/memory.py:170-177`
   - Concrete change: route recursive traversal and warmup through the lightweight index path, then hydrate only when a non-recursive folder view actually needs full metadata.
   - Follow-on: either wire `hydrate_recursive_items()` into the real path or delete it as residue.

3. Remove refresh split-brain between request routes and closure-captured routes.
   - Why: `/refresh` swaps the request-scoped storage via `StorageProxy`, but OG, index, and views routes keep using the original captured `storage` and `workspace`.
   - Evidence: `src/lenslet/server_factory.py:709-755`, `src/lenslet/server_routes_index.py:72-101`, `src/lenslet/server_routes_og.py:108-127`, `src/lenslet/server_routes_views.py:14-35`
   - Concrete change: introduce a single mutable app context on `app.state` for `storage`, `workspace`, and runtime services, and have every route resolve through that context.
   - This is both a correctness fix and a simplification. The current mixed closure/request model is iteration residue.

4. Fix logical path correctness before more storage refactors land.
   - Why:
     - dataset mode collapses everything to `/{dataset}/{basename}`, which loses nested structure and silently overwrites duplicate basenames
     - table mode ignores explicit `path_column` values for S3 rows
   - Evidence: `src/lenslet/storage/dataset.py:310-363`, `src/lenslet/storage/table_index.py:197-214`
   - Concrete change:
     - move dataset logical-path construction onto the same path normalization/dedup path as table mode
     - honor `path_column` consistently for S3 rows
   - These are correctness bugs, not cleanup opportunities.

### P1

5. Make search read-only and stop allocating metadata for misses.
   - Why: both dataset and table search call `get_metadata()` inside the scan loop, and `get_metadata()` creates/stores a default dict when none exists. A first search over a large corpus becomes `O(n)` object creation with permanent `_metadata` growth.
   - Evidence: `src/lenslet/storage/dataset.py:544-555`, `src/lenslet/storage/dataset.py:562-588`, `src/lenslet/storage/table_facade.py:152-174`, `src/lenslet/storage/table_facade.py:183-208`
   - Concrete change: add a no-create metadata read path for search, then cache canonical search text explicitly if search latency still matters.
   - This is a clear `better-code` issue: read paths should not mutate global state.

6. Hard-cut duplicated dataset storage code onto shared storage helpers.
   - Why: `DatasetStorage` still carries a second implementation of S3 client creation, presigning, remote header probing, thumbnail generation, dimension parsing, search, and metadata defaults, while table mode already extracted shared helpers.
   - Evidence: `src/lenslet/storage/dataset.py:104-235`, `src/lenslet/storage/dataset.py:414-688`, `src/lenslet/storage/table_facade.py:43-149`, `src/lenslet/storage/table_media.py`, `src/lenslet/storage/table_probe.py`
   - Concrete change:
     - Tier 2: move dataset mode onto the shared helper surface immediately
     - Tier 3: remove `DatasetStorage` as a separate path model and run programmatic datasets through the table/index pipeline
   - Rationale: this repo is pre-release alpha and explicitly does not require backward compatibility.

7. Split browse and ranking code at the bundle boundary, not only at runtime.
   - Why: `AppModeRouter` statically imports both `AppShell` and `RankingApp`, the app blocks on `/health`, and the shipped build remains one large JS chunk.
   - Evidence: `frontend/src/app/AppModeRouter.tsx:1-40`, `frontend/src/app/boot/bootHealth.ts`, `src/lenslet/server_routes_index.py:72-101`, build output from `npm run build`
   - Concrete change:
     - Tier 2: lazy-load ranking mode with `import()`
     - Tier 3: serve separate browse/ranking entrypoints or SPA shells
   - This is imitation-code shaped today: there is a runtime mode boundary, but no delivery-path win.

8. Stop cloning every cached result set on each live item update.
   - Why: `updateItemCaches()` maps every cached `folder` and `search` query array on each `item-updated` and `metrics-updated` event. On large recursive scopes, one metadata update becomes main-thread `O(total cached items)`.
   - Evidence: `frontend/src/app/AppShell.tsx:366-405`, `frontend/src/app/hooks/useAppPresenceSync.ts:373-521`
   - Concrete change: move to path-addressable cache updates keyed by item path, and keep toolbar-only sync state out of the main shell render fan-out.
   - Secondary fix: debounce or idle-commit the `localStorage` persistence effect in `frontend/src/app/AppShell.tsx:957`.

### P2

9. Stop throwing away unrelated recursive cache windows.
   - Why: `invalidate_path()` removes matching memory entries, then clears the entire persisted disk cache. Small refreshes destroy unrelated recursive locality.
   - Evidence: `src/lenslet/browse_cache.py:243-260`
   - Concrete change: make disk invalidation path-scoped like memory invalidation.

10. Share recursive count and recursive payload traversal work.
   - Why: `count_only` recursive requests use a separate subtree walk and do not read or seed the snapshot cache. The folder tree then pays for one walk to count and another for the actual recursive payload.
   - Evidence: `src/lenslet/server_browse.py:404-430`, `frontend/src/features/folders/FolderTree.tsx:101`, `frontend/src/api/client.ts:499`
   - Concrete change: unify recursive count and recursive payload behind one cached representation.

11. Remove the shadow frontend API layer and stale ranking asset.
   - Why:
     - `frontend/src/shared/api/*` is a pure re-export shim layer
     - there are 27 imports of that shim tree in `frontend/src`
     - `frontend/src/features/ranking/ranking_old.css` is unreferenced
   - Evidence: `frontend/src/shared/api/client.ts`, `frontend/src/shared/api/folders.ts`, `frontend/src/shared/api/items.ts`, `frontend/src/features/ranking/ranking_old.css`
   - Concrete change: Tier 2 cutover to direct `frontend/src/api/*` imports, then delete `shared/api` and `ranking_old.css`.
   - This is low-risk debloat with clear evidence.

12. Remove duplicated client-side folder discovery and duplicate thumbnail caching.
   - Why:
     - opening the move dialog triggers a breadth-first crawl of up to 600 folders via serial `/folders` calls
     - `ThumbCard` adds a second blob URL cache and one `IntersectionObserver` per card on top of the shared thumb cache
   - Evidence: `frontend/src/app/hooks/useAppActions.ts:70-100`, `frontend/src/app/hooks/useAppActions.ts:142-155`, `frontend/src/features/browse/components/ThumbCard.tsx:1-143`, `frontend/src/api/client.ts:659`
   - Concrete change:
     - source move targets from already-indexed folder data or a dedicated backend endpoint
     - collapse thumbnail URL handling onto the shared cache/hook path

13. Retire the internal `lenslet.server` seam as a dependency knot.
   - Why: route modules still import back through the facade module they were extracted from, which preserved the import knot instead of removing it.
   - Evidence: `src/lenslet/server.py:1-91`, `src/lenslet/server_routes_common.py:56`, `src/lenslet/server_routes_common.py:106`
   - Concrete change:
     - Tier 2: move shared helpers into leaf modules and inject them explicitly
     - Tier 3: keep `server.py` as public re-export facade only, not an internal seam anchor

## Tiered Simplification Batch

### Tier 1: safe cleanup to batch with real fixes

- rename or split `warm_recursive_cache()` because it does not always warm the recursive cache
- remove dead private wrappers identified in `dataset.py`, `table.py`, and `table_index.py`
- replace JSON deep-clone/equality helpers in `AppShell` with one canonical helper
- cache the frontend shell HTML once per process instead of rereading `index.html` on every request

### Tier 2: allowed by current repo policy

- app-state context cutover for `storage` and `workspace`
- dataset-mode cutover onto shared storage helpers
- direct frontend `api/*` imports and deletion of `shared/api/*`
- debounced `localStorage` persistence in `AppShell`
- path-scoped recursive disk cache invalidation

### Tier 3: approval gate before implementation

- optimistic preindex reuse with background validation
- full removal of `DatasetStorage` as a separate path model
- separate browse/ranking entrypoints or shells
- full retirement of the internal `lenslet.server` seam

## Missing Tests Worth Adding

- warm-start startup test that fails if reused preindex still scans the full tree
- recursive browse test proving `get_index_for_recursive()` is used on the first recursive request
- refresh test covering OG/index/views after storage/workspace replacement
- dataset-mode test for nested source paths and duplicate basenames
- table ingest test for S3 rows with explicit `path_column`
- search test that asserts a miss does not grow `_metadata`
- frontend regression test for item-update cache churn on large cached query sets

## Recommendation

The cleanest execution order is:

1. fix the correctness bugs first: refresh split-brain, dataset path collapse, S3 `path_column`
2. fix the real hot paths next: warm preindex startup, recursive browse fast path, live update cache churn
3. then hard-cut duplicate layers: shared dataset helpers, frontend `shared/api`, stale ranking asset, server facade knot

That order removes the highest-risk drift before investing in larger cuts.
