# Table Row-View Backend Plan


## Outcome + Scope Lock


After implementation, Lenslet table mode should browse a 500k-row HTTP parquet without constructing a dense `TableBrowseItem` object graph at startup. Users should keep the same visible browse, search, media, thumbnail, sidecar, and embedding behavior, but internally table storage should keep compact columnar row state and materialize item-like objects only at API/media boundaries.

Goals are to replace dense table-mode item/index construction, keep existing FastAPI payload contracts stable, preserve logical path and original parquet row identity, keep media dimension and size updates persistent through row overlays, and prove the result on the existing 500k HTTP parquet scenario. The expected performance target is `prepare_table_launch` near or below 2.0s and peak RSS below 750MB on the same machine where the merged optimized baseline measured 2.37-2.55s and about 0.98-0.99GB. If exact timing varies, the implementation must still show that the dense object graph is gone and identify the new measured bottleneck.

Non-goals are Rust FFI, a new query language, full server-side sort/filter UI, multi-file or distributed parquet planning, bloom filters, SIMD kernels, custom Arrow JSON serialization, and frontend redesign. Hard cutover of table storage internals is approved because Lenslet is pre-release alpha, but breaking existing user-facing browse/search/media/sidebar behavior is not approved.

Pre-approved behavior changes are table-mode internal representation changes, removal of dense table item maps/lists, narrow table-specific storage hooks, deterministic preservation of current duplicate-path disambiguation, and targeted test/benchmark scripts. Require sign-off before changing public browse payload fields, disabling sidecars, disabling embeddings, removing local/S3 table support, adding Rust/native build requirements, or replacing the frontend browse model.

Deferred work is true row-group lazy parquet reads, rich server-side filters/sorts, trie/trigram search indexes, frontend pagination redesign, and deeper nested Arrow table-cell fidelity. These can be revisited only after the row-view backend lands and measurements show they are still needed.


## Context


The current merged main is `72e2b41`, including PR #23. The current target benchmark is documented in `docs/20260603_io_speed_optimization_progress.md`: 500k HTTP parquet `prepare_table_launch` best 2.37s, peak RSS around 983MB, repeated full-scan search miss median around 0.17s. The old baseline before optimization was about 27s and 2.4-2.5GB RSS. There is no repo-level `PLANS.md` convention to comply with.

Current table mode still constructs dense objects. `src/lenslet/storage/table/storage.py` defines `TableBrowseItem`, calls `build_table_indexes(... item_factory=TableBrowseItem ...)`, binds `result.items`, builds `_sorted_paths` and `_sorted_items`, and searches over `_sorted_items`. `src/lenslet/storage/table/row_scan.py` has the uniform HTTP fast path, but it still builds `items`, `path_to_row`, `row_to_path`, `row_dimensions`, folder indexes, and item objects. `src/lenslet/storage/index_assembly.py` is the generic dense assembly path and should not be broadly rewritten until table startup no longer depends on it.

The hidden dependencies are important. `src/lenslet/storage/source/backed.py` assumes `_items` for `exists`, `size`, `etag`, media reads, thumbnail cache keys, local-file resolution, sidecar defaults, and row lookup. Media dimension loading mutates item width/height/size today, so the row-view cutover needs a persistent dimension/size overlay, not disposable item objects. `src/lenslet/web/browse.py` converts item-like objects to response payloads. `src/lenslet/web/app/shared.py` builds embeddings from `storage.row_index_map()`, and embedding row identity must stay the original parquet row index, not window position. Sidecars remain keyed by canonical logical path strings.

Duplicate canonical logical paths must preserve current behavior: the first row keeps its normalized path and later duplicate rows receive deterministic `dedupe_path` suffixes. `path_to_row`, `row_to_path`, sidecars, media routes, and embedding lookup use the deduped logical path while `row_idx` remains the original parquet row index.

Other codebases support this direction. `dataio-rs` has filtered/windowed parquet readers in `/data/yada/dev_docs/dataio-rs/crates/dataio-parquet/src/reader.rs`, with projection, `offset`, `limit`, row filters, and row-group pruning. `parquet-rs` has gallery APIs in `/data/yada/dev_docs/parquet-rs/src/server/handler.rs` that return bounded page payloads, plus frontend table virtualization/pagination in `/data/yada/dev_docs/parquet-rs/templates/gallery_js.html`. These are reference patterns only; transfer the columnar/window materialization pattern, not their broader query engine.


## Interfaces and Dependencies


The external `BrowseStorage` contract should continue returning item-like objects at API boundaries. Internally, table storage may replace dense `TableBrowseItem` ownership with row ids and compact arrays. Any materialized table item must expose `path`, `name`, `mime`, `width`, `height`, `size`, `mtime`, `url`, `source`, `metrics`, `metric_labels`, and `row_idx` for existing code.

The row-view backend must provide row-native implementations for the methods already consumed by Lenslet: folder index loading, scoped counts/windows, search, path validation, source lookup, media bytes, size/etag, thumbnail cache keys, local-file resolution, dimension loading, row index lookup, sidecar enrichment, browse signature, and indexing progress. Prefer table-specific overrides or narrow hooks over broad new storage protocol methods.

The implementation should prefer Python and PyArrow/NumPy already in the project. No new runtime dependency should be added unless a sprint explicitly proves the existing stack cannot meet acceptance.


## Plan of Work


The implementation should continuously update this plan document while working, especially the Progress Log and sprint handoff notes. After each sprint, add what changed, what was validated, and what remains risky. For minor script-level uncertainties, such as exact benchmark helper placement, proceed according to this approved plan to maintain momentum; ask for clarifications after the sprint and apply follow-up adjustments.

Every non-trivial code ticket must use the `better-code` skill before and during implementation. The implementing agent must state material assumptions and ambiguous interpretations before coding, prefer the smallest non-speculative solution, touch only lines tied to the request, invariants, or verification, remove only unused code introduced by the change, and attach a concrete verification check to each step.

Delegate subagents early when that reduces context load or speeds discovery. Let cleanup and review subagents continue long enough to produce useful results; if still running after 10 minutes, ask for a progress update and why more time is needed. Do not terminate those agents early just to move faster.

### Scope Budget and Guardrails


The budget is four sprints and twelve substantive tickets. The likely file set is `src/lenslet/storage/table/storage.py`, `src/lenslet/storage/table/row_scan.py`, `src/lenslet/storage/table/index.py`, `src/lenslet/storage/table/index_types.py`, `src/lenslet/storage/source/backed.py`, `src/lenslet/storage/source/catalog.py`, `src/lenslet/storage/source/state.py`, focused storage/web tests, browser smoke scripts, and this plan/progress documentation. Touch `src/lenslet/web/browse.py` only if row-store APIs cannot preserve the existing item boundary. Touch `src/lenslet/storage/index_assembly.py` only after tests prove a table-specific dense startup path is unused.

Quality floor: existing browse/search/media/sidecar/embedding behavior must remain self-consistent after cutover. Maintainability floor: table row-view ownership must be explicit and tests must cover every old dense assumption it replaces. Complexity ceiling: do not build row-group lazy IO, a query language, a generic table engine, or frontend redesign in this plan unless primary acceptance fails and the user approves expansion.

Memory invariants are explicit. Startup must not allocate one `TableBrowseItem` per row, must not allocate per-row metric dicts, must not store folder indexes as item-object lists, and must not rebuild dense path maps internally as compatibility crutches without measuring and documenting the memory cost. Benchmarks must separate Arrow table memory, Python path/source caches, sidecar state, thumbnail cache, row overlays, and materialized item counts as much as the available tools allow.

Search invariants are also explicit. Always-cached search fields are logical path and, only when needed, normalized name/source/url text. Sidecar text is optional and should only inspect existing sidecar state; search must not create sidecars, hydrate metrics, or materialize all items. A full miss may scan compact arrays, but it must not allocate row objects.

Browse signatures should reflect table identity, schema, row count, source/path columns, sampled row payloads, and file/cache identity. Avoid full metric hashing. If metrics come from the parquet file, the file signature seed plus sampled metric values is enough.

Debloat targets are dense table-mode `_items` as the primary source of truth, `_sorted_items`, folder indexes carrying full item lists, and table-specific use of `IndexAssemblyResult.items`. Keep generic dense assembly for dataset/local backends unless table cutover makes code demonstrably unused.

### Sprint Plan


1. Sprint 1: Baseline, Payload Golden Tests, and Row-Store Interface Proof.

   Demo outcome: a row-native table store can derive logical paths, row ids, folder dirs, scoped bounds, materialized item windows, and a narrow source-backed lookup path in tests without changing production behavior yet.

   - S1-T1: Add or formalize a benchmark/check harness for current main plus a small fixture parity harness. It should record 500k launch time, RSS, first recursive window latency, search miss latency, materialized item counts, and small-table payload parity for root browse, recursive window, search hit/miss, media metadata, sidecar-enriched item, and embedding row lookup. Validation: the harness runs with `PYTHONPATH=src` and records the merged baseline.
   - S1-T2: Introduce the minimal row-store data model for table mode: row paths, sources, names, mime, dimensions, size, mtime, sorted row indices, path-to-row, row-to-path, folder children, row dimension/size overlays, and materialization counters. Validation: focused unit tests cover HTTP path/source aliases, duplicate-path disambiguation, scope bounds, folder dirs, memory invariants, and original row-id preservation.
   - S1-T3: Prove the table/source-backed boundary before browse cutover. Implement or spike row-native `exists`, `get_source_path`, `read_bytes`, `size`, `get_dimensions`, and `row_index_for_path` against the row store without dense `_items`. Validation: targeted tests prove these methods work and do not allocate all row items.

2. Sprint 2: Browse Cutover.

   Demo outcome: table storage no longer builds dense `TableBrowseItem` objects at startup for the target HTTP table, while `/folders` windows return the same item payload shape.

   - S2-T1: Replace table-mode startup assembly with compact row-store construction for HTTP and generic table rows. Keep current source/path derivation and validation behavior from `row_scan.py`, but output row arrays and folder row references instead of item objects. Validation: existing table ingestion/index pipeline tests pass, startup materialized item count is zero or bounded, and no table startup path calls `TableBrowseItem` factory.
   - S2-T2: Reimplement `load_index`, `load_recursive_index`, `items_in_scope`, `items_in_scope_window`, and `count_in_scope` from row-store scopes. Folder indexes should expose dirs and materialize only requested item windows. Validation: web folder recursive tests and direct folder payload tests pass; recursive window materialized count is at most `limit + fixed_overhead`.
   - S2-T3: Recompute browse signature and indexing progress from row arrays instead of `_items`, then run the 500k benchmark immediately. Validation: health/workspace generation tests pass, browse signature changes on relevant sampled payload changes, and 500k launch/RSS numbers are recorded before moving to Sprint 3.

3. Sprint 3: Search, Media, Sidecars, and Embeddings.

   Demo outcome: search, media routes, thumbnail generation, sidecars, row metadata enrichment, and embedding lookup work from row ids without depending on dense item maps.

   Closure requirement carried from the Sprint 2 500k run: Sprint 3 must either reduce or explicitly profile the current regressions (`prepare_table_launch` 3.277s, peak RSS 842.8 MiB, repeated search miss median 0.480s). Search latency is owned by S3-T1. Launch/RSS profiling should identify whether retained cost is Arrow table memory, path/source/name arrays, `path_to_row`/`row_to_path`, folder row refs, or search lowercase caches; if this cannot be fixed inside Sprint 3 without scope expansion, add a concrete Sprint 4 fix ticket before deletion/acceptance work closes.

   - S3-T1: Reimplement table search over compact row path/source/name caches and sidecar text, returning materialized row items only for bounded hits. Validation: search contract tests pass, source/url toggle still works, search miss materialized item count is zero, and 500k repeated miss remains no worse than the merged baseline unless a measured tradeoff is documented.
   - S3-T2: Complete media and dimension overlay behavior. `load_dimensions` and `get_or_build_thumbnail` must write through width/height/size overlays so rematerialized items and default sidecars see updated values. Validation: dataset HTTP tests, table security tests, media route tests, and overlay persistence tests pass.
   - S3-T3: Preserve sidecar inventory/enrichment and embedding identity. `sidecar_enrichment_for_path`, refresh sidecar preservation, `row_index_for_path`, `path_for_row_index`, and `row_index_map` must use deduped logical paths and original parquet row indices. If `row_index_map()` recreates a large dict, measure it; if it breaks the memory target, add a narrower embedding lookup path instead of hiding the cost. Validation: item sidecar route tests, refresh tests, table display/enrichment tests, embedding cache/search tests, and a 500k benchmark after this sprint pass or produce explicit fix tickets.

4. Sprint 4: Deletion and Real Acceptance.

   Demo outcome: the table backend is internally row-native, the old dense table startup path is removed only where proven unused, and the 500k scenario meets acceptance or has a measured profile explaining the remaining bottleneck.

   - S4-T1: Remove only proven-unused dense table startup code. Keep generic dataset/local assembly intact and avoid broad cleanup of `index_assembly.py` unless call graph and tests prove the removed code is table-only dead code. Validation: lint and focused storage tests pass; no table-mode startup calls `build_table_indexes(... item_factory=TableBrowseItem ...)`.
   - S4-T2: Use the Sprint 3 retained-category profile to make one measured memory/launch trim if a narrow table-row cache reduction is available, then run the 500k benchmark and update `docs/20260603_io_speed_optimization_progress.md` plus this plan with results, retained object categories, materialization counts, and remaining bottlenecks. Validation: recorded launch time, RSS, first window, search miss, memory category notes, and any accepted/declined cache-trim decision are present.
   - S4-T3: Run full validation and browser smoke. Validation: `PYTHONPATH=src python scripts/lint_repo.py`, `PYTHONPATH=src python -m pytest -q`, `PYTHONPATH=src python -m scripts.browser.gui_smoke.acceptance`, and the target 500k live browse/search smoke all pass or have explicit fix tickets before handoff.

### Gate Routine for Every Ticket


0. Plan gate: the code agent restates the ticket goal, acceptance criteria, material assumptions/ambiguities, and expected files to touch. If ambiguity would change behavior, stop and ask. If the ticket includes substantive code work, invoke `better-code` first and restate the key invariants, smallest robust approach, and verification evidence.

1. Implement gate: implement the smallest coherent slice that satisfies the ticket. Avoid speculative features, one-off abstractions, unrelated cleanup, and broad refactors unless explicitly approved. Attach minimal verification signals to the ticket before moving on.

2. Cleanup gate: after each complete sprint, run the `code-simplifier routine` below.

3. Review gate: after cleanup, run the `review routine` below and fix findings before closing the sprint.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan the current sprint changes. Start with non-semantic cleanup: formatting/lint autofixes, obvious dead code removal, small readability edits that do not change behavior, and docs/comments that reflect what is already true. Keep the pass conservative; do not expand into semantic refactors unless explicitly approved. Once the cleanup subagent starts, do not interrupt or repurpose it to save time. If it runs long, wait or request a progress update; fall back to manual cleanup only if the subagent is unavailable, fails, or the user approves the downgrade.

### review routine


After each complete sprint and after the cleanup subagent finishes, spawn a fresh subagent and request a code review using the `code-review` skill. Instruct the review subagent to be constructively adversarial: actively look for failure modes, weak validation, removable work, and scope creep while keeping feedback actionable. Use the best available model with `reasoning_effort` set to `medium`; do not default to mini/fast models unless the user approves that downgrade. Review the post-cleanup diff, apply fixes, and rerun review when needed. Once the review starts, do not interrupt, repurpose, or terminate it to save time. Manual diff review is a fallback only when the subagent is unavailable, fails after a reasonable wait plus progress check, or the user approves the downgrade.


## Validation and Acceptance


Primary validation must run against the real user scenario, not only fixtures. Use the 500k HTTP parquet:

    /data/yada/dev_new/pclb2/outputs/dit03_pretrain_pool_sample_500k_l0l1_multihead_http/dit03_pretrain_pool_sample_500k_l0l1_multihead_http.parquet

Primary acceptance gates:

- 500k launch benchmark with `PYTHONPATH=src` reports `prepare_table_launch` near or below 2.0s, peak RSS below 750MB, and no dense table item graph at startup. If timing misses but object graph removal succeeds, profile before expanding scope.
- Memory evidence reports at least peak RSS, materialized item count, and best-effort retained categories for Arrow table memory, Python path/source caches, sidecar state, thumbnail cache, and row overlays.
- First recursive `/folders?recursive=1&offset=0&limit=5000` window returns correct payload shape and does not materialize all rows.
- Search over the 500k table returns correct scoped hits and repeated full-scan miss latency remains no worse than the merged baseline median around 0.17s unless a measured new cache tradeoff is documented.
- Media and thumbnail reads for HTTP URLs still work, and dimension/size updates persist through row overlays.
- Sidecar edits, sidecar enrichment, and embedding search remain consistent with deduped logical paths and original parquet row ids.
- Browser acceptance smoke passes, and a target live-server browse/search probe on the 500k parquet shows initial grid usability without backend full materialization.

Sprint 2 interim result, recorded in `docs/ralph/20260603_table_row_view_backend/iteration2_browse_cutover_harness.json`: table startup no longer retains dense item objects (`dense_items=0`, `sorted_items=0`, `folder_item_refs=0`) and the first 5k recursive window materialized exactly 5k row items. Performance acceptance is not yet met: `prepare_table_launch` was 3.277s, peak RSS was 842.8 MiB, and repeated search miss median was 0.480s. The remaining measured costs are the Arrow table plus Python path/source/search row caches and row lookup maps, not `TableBrowseItem` ownership.

Sprint 3 interim result, recorded in `docs/ralph/20260603_table_row_view_backend/iteration3_search_media_harness.json`: search miss materialization remains zero and repeated 500k full-miss median returned to the merged baseline range at 0.153s after the first cold cache build. Primary performance acceptance is still not met: `prepare_table_launch` was 3.259s, peak RSS was 877.1 MiB after recursive browse plus search caches, and the first recursive 5k window was 0.959s. The retained-category profile points to projected Arrow/NumPy data columns, Python source/path/name row arrays, `path_to_row`/`row_to_path`/`row_to_slot`, folder row refs, and lowercased path/name search caches after search. No dense table item graph is retained.

Secondary fast gates:

- Focused table/storage tests after each sprint:

    PYTHONPATH=src python -m pytest -q tests/storage/table tests/storage/search/test_search_text_contract.py tests/storage/dataset/test_dataset_http.py

- Focused web/embedding tests after Sprint 3:

    PYTHONPATH=src python -m pytest -q tests/web tests/embeddings

- Repo-wide checks before handoff:

    PYTHONPATH=src python scripts/lint_repo.py
    PYTHONPATH=src python -m pytest -q
    PYTHONPATH=src python -m scripts.browser.gui_smoke.acceptance

Completion honesty rule: a sprint cannot be marked complete if its demo outcome fails, even when smaller fixture tests pass. If the primary 500k scenario fails after Sprint 2 or Sprint 3, add explicit closure tasks before moving on.


## Risks and Recovery


The main risk is hidden item-object mutation. Recovery is to prove the source-backed/media adapter in Sprint 1, keep row materialized items write-through for dimensions and size, and add tests that rematerialize after mutation. If a media path still reaches `SourceBackedStorageBase._items`, override that table method or introduce a narrow row-aware hook; do not recreate a dense dict to satisfy the base class.

The second risk is row identity drift. Sorted windows and duplicate logical paths must never replace original parquet row indices. Recovery is to preserve current deterministic `dedupe_path` behavior, keep `row_idx` as the original input row, and add tests around duplicates, sorted folders, embeddings, and `path_for_row_index`.

The third risk is accidental full materialization through recursive browse, search, embeddings, or cache warming. Recovery is to instrument materialization counts in tests and fail the 500k acceptance if bounded windows or search misses build all rows. If `row_index_map()` for embeddings becomes the remaining dense structure, measure it and choose between accepting the explicit cost or changing the embedding manager interface with user sign-off.

The fourth risk is over-scoping into a parquet query engine. Recovery is to keep row-group lazy reads, full server-side filters/sorts, and Rust/native work deferred unless the row-view backend removes the dense object graph and still cannot meet acceptance.

Rollback is straightforward at sprint boundaries: revert the sprint commit or restore the previous dense `TableStorage` path. Because this is hard cutover alpha work, do not keep a long-lived compatibility flag unless needed temporarily inside a sprint for comparison tests.

Retries are idempotent if the plan keeps row-store construction pure from the table and sidecar/cache state separate. Benchmark scripts should be rerunnable without writing to source datasets.


## Progress Log


- [x] 2026-06-03: Merged PR #23 established current optimized baseline: best 500k `prepare_table_launch` 2.37s, RSS about 983MB, repeated search miss median about 0.17s.
- [x] 2026-06-03: Scope locked by user: hard cutover is fine, but Lenslet after the change must be self-consistent and not break user-facing browse behavior.
- [x] 2026-06-03: Explorer review identified dense dependencies in `TableBrowseItem`, `TableStorage.__init__`, `index_assembly.py`, `row_scan.py`, `SourceBackedStorageBase`, web browse payloads, media, sidecars, embeddings, and health signatures.
- [x] 2026-06-03: Rust reference review confirmed `dataio-rs` as the closer backend model and `parquet-rs` as useful API/frontend reference; SIMD, bloom filters, and full query planning are out of scope.
- [x] 2026-06-03: Plan review incorporated: source-backed proof moved into Sprint 1, memory invariants tightened, duplicate-path behavior made explicit, `row_index_map()` risk added, search and browse-signature scope narrowed, and broad `index_assembly.py` cleanup de-scoped.
- [x] 2026-06-03: S1-T1 added `scripts/experimental/table_row_view_harness.py` and recorded `docs/ralph/20260603_table_row_view_backend/iteration1_baseline_harness.json`. Dense 500k baseline from this run: `prepare_table_launch` 3.151s, peak RSS 855.7 MiB after checks, first recursive 5k window 0.944s, repeated miss median 0.269s, 500k dense items, 500k sorted items, and 500k folder item refs.
- [x] 2026-06-03: S1-T2/S1-T3 added `src/lenslet/storage/table/row_store.py` plus focused tests. The row-store proof preserves HTTP path/source aliases, duplicate-path row identity, folder dirs, scoped row windows, dimension/size overlays, and row-native source/media lookup without a dense item map or startup item materialization.
- [x] 2026-06-03: Sprint 1 validation passed: focused table/search/dataset suite, row-store tests, lint repo, 500k harness, and harness `--compare-json` parity check. Cleanup subagent found no Tier 1 edits; review found the harness needed a real compare mode and a direct-run import guard, both fixed and rereviewed with no remaining findings.
- [x] Sprint 1 complete: baseline, payload parity, row-store interface proof.
- [x] 2026-06-03: S2-T1/S2-T2 cut table storage over to `TableRowStore` construction. Table startup now binds empty source-backed item state, builds lightweight folder indexes on demand, serves direct/recursive windows from row ids, keeps row-native source/media/thumbnail/dimension/sidecar defaults, and uses write-through materialized row items for media field mutations.
- [x] 2026-06-03: S2-T3 recomputed browse signatures from sampled row arrays and recorded the 500k cutover harness. Result: `prepare_table_launch` 3.277s, peak RSS 842.8 MiB, first recursive 5k window 0.985s, repeated miss median 0.480s, 0 dense items, 0 sorted items, 0 retained folder item refs, and 5k materialized items after the 5k recursive window.
- [x] 2026-06-03: Sprint 2 validation passed: focused table/search/dataset tests, route/cache/refresh tests, media/storage/embedding contract tests, harness payload parity compare, full 500k harness, and `PYTHONPATH=src python scripts/lint_repo.py`. Lint passed with warn-only large-file notices including `src/lenslet/storage/table/storage.py` at 1240 lines.
- [x] Sprint 2 complete: browse cutover and post-sprint 500k benchmark.
- [x] 2026-06-03: S3-T1 optimized table row-store search. Miss scans now cache lowercased names only when needed, avoid source-cache construction when source search is covered by path, and avoid per-row sidecar path lookup when no sidecars exist. Direct 500k profiling showed warm miss calls around 0.16-0.18s with zero materialized row items.
- [x] 2026-06-03: S3-T2 hardened media overlays. `load_dimensions` and `get_or_build_thumbnail` now persist decoded width/height plus byte size into the row store, and tests rematerialize row items plus default sidecars after the update.
- [x] 2026-06-03: S3-T3 preserved sidecar and embedding identity through existing deduped-path row-store APIs. Focused sidecar/enrichment/embedding tests passed. A separate 500k `row_index_map()` measurement built 500k entries in about 0.05s; the dict container is about 20MB and reuses existing path strings.
- [x] 2026-06-03: Sprint 3 500k harness recorded `prepare_table_launch` 3.259s, peak RSS 877.1 MiB, recursive 5k window 0.959s, repeated search miss median 0.153s, 0 dense items, 0 sorted items, 0 retained folder item refs, and 5k materialized items after the recursive window. Remaining launch/RSS work is now a concrete Sprint 4 retained-cache trim/profile decision.
- [x] 2026-06-03: Sprint 3 validation passed: focused table/search/dataset/media/storage/source/embedding/web suites, small harness parity compare, full 500k harness, and `PYTHONPATH=src python scripts/lint_repo.py`. Cleanup subagent made Tier 1 formatting/readability edits only; review subagent found no code-level issues and the two documentation-state findings were resolved.
- [x] Sprint 3 complete: search/media/sidecar/embedding self-consistency and post-sprint 500k benchmark.
- [ ] Sprint 4 complete: proven-unused dense table startup deletion and real-scenario validation.


## Artifacts and Handoff


Read these before implementing:

- `docs/20260603_io_speed_optimization_progress.md` for benchmark history and current performance evidence.
- `scripts/experimental/table_row_view_harness.py` for the row-view benchmark and payload parity harness.
- `docs/ralph/20260603_table_row_view_backend/iteration1_baseline_harness.json` for Sprint 1 dense baseline evidence.
- `docs/ralph/20260603_table_row_view_backend/iteration2_browse_cutover_harness.json` for Sprint 2 row-store cutover evidence.
- `docs/ralph/20260603_table_row_view_backend/iteration3_search_media_harness.json` for Sprint 3 search/media evidence and retained-category profiling.
- `src/lenslet/storage/table/storage.py` for production table storage, row-store browse cutover, and compatibility search.
- `src/lenslet/storage/table/row_store.py` for the Sprint 1 row-store proof model.
- `src/lenslet/storage/table/row_scan.py` for current source/path derivation and uniform HTTP fast path.
- `src/lenslet/storage/source/backed.py` for inherited media, sidecar, dimension, and source lookup assumptions.
- `src/lenslet/web/browse.py` for response materialization and recursive windows.
- `src/lenslet/web/app/shared.py` and `src/lenslet/web/routes/embeddings.py` for embedding row identity.
- `/data/yada/dev_docs/dataio-rs/crates/dataio-parquet/src/reader.rs` for projection/window/filter reader shape, as reference only.
- `/data/yada/dev_docs/parquet-rs/src/server/handler.rs` and `/data/yada/dev_docs/parquet-rs/templates/gallery_js.html` for bounded gallery responses and frontend pagination/virtualization, as reference only.

Important current benchmark transcript from the merged optimization work:

    Target 500k HTTP parquet benchmark: prepare_table_launch measured 2.37s on the best run after PR #23, with peak RSS around 983MB. The index progress loop reported about 395k rows/sec. Repeated full-scan miss search median was about 0.17s.

Sprint 1 handoff note:

The row store is intentionally not wired into production `TableStorage` yet. Sprint 2 should start with S2-T1 and replace table-mode startup assembly with `TableRowStore` construction while keeping current source/path derivation behavior. Use `python scripts/experimental/table_row_view_harness.py --skip-target --compare-json docs/ralph/20260603_table_row_view_backend/iteration1_baseline_harness.json` to catch small payload drift, and rerun the full harness after the browse cutover to compare dense counts, RSS, recursive window, and search miss behavior.

Sprint 2 handoff note:

Production `TableStorage` now owns compact row-store state instead of dense startup items. Sprint 3 should start from S3-T1 and tighten search over compact caches: the current compatibility search preserves payload parity but repeated 500k miss median regressed to 0.480s because it scans cached lowercase paths in Python. Media and sidecar behavior already routes through row overlays, but Sprint 3 should still harden overlay persistence, sidecar inventory/enrichment, and embedding identity against deduped logical paths and original parquet row ids. The main remaining memory categories are Arrow table memory, Python path/source/name arrays, `path_to_row`/`row_to_path`, folder row refs, search lowercase path cache after search, thumbnail cache, sidecar state, and row overlays.

Sprint 3 handoff note:

Search, media overlays, sidecar enrichment, and embedding row identity are self-consistent on focused tests and the 500k harness. Search misses no longer materialize rows and warm repeated miss latency is back near the merged optimized baseline. Sprint 4 should start with S4-T1/S4-T2: remove only proven-unused dense table startup code, then use the Sprint 3 profile to decide whether a narrow retained-cache trim is available before the final benchmark. The most concrete remaining categories are projected Arrow/NumPy metric columns, Python source/path/name row arrays, row lookup structures, folder row refs, and lowercased path/name search caches after first search.
