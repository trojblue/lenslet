# Lenslet IO Speed Optimization Progress

Date: 2026-06-03

This is the working intent/progress log for the "extreme speed optimizations for data loading and image browsing" goal. If a long-running session loses context, resume from this file.

## Goal

Make Lenslet fast for large image tables, especially HTTP-backed Parquet datasets like:

`/data/yada/dev_new/pclb2/outputs/dit03_pretrain_pool_sample_500k_l0l1_multihead_http/dit03_pretrain_pool_sample_500k_l0l1_multihead_http.parquet`

Primary target:

- 500k-row HTTP image Parquet should become usable in under 5 seconds from launch where practical.
- Initial image browsing should show useful content quickly and avoid blocking on all-row Python object construction.
- Filtering, search, scrolling, and thumbnail/file fetches should avoid full scans and avoid avoidable network setup.

## Current Baseline

Measured with the full 500k Parquet, explicit `source_column='s3key'`, default `skip_dimension_probe=True`.

Important measurement note: run all Lenslet benchmarks from this checkout with `PYTHONPATH=src`. An early baseline accidentally imported the sibling `/data/yada/dev_new/lenslet` checkout, so only measurements that state the corrected import path should be treated as exact before/after evidence for this repo.

| Stage | Time | Notes |
| --- | ---: | --- |
| `load_parquet_schema` | ~0.001s | Footer/schema is not the bottleneck. |
| `select_browse_columns` | ~0.23s | Selects 41 columns, including 37 numeric metric columns. |
| `pyarrow.parquet.read_table` projected columns | ~0.13s | Arrow read itself is fast. |
| `inspect_table_dimensions` | ~0.32s | Converts width/height to Python lists and scans for missing dims. |
| `TableStorage(...)` construction | ~27.3s wall-clock baseline | Dominant bottleneck. |
| `TableStorage(...)` under cProfile | ~70.4s | Profiler overhead is large; use only for attribution. |
| `count_in_scope('/')` | ~0.00001s | Existing sorted-path scope count is fine. |
| `items_in_scope_window('/', 0, 5000)` | ~0.00014s | Window slicing is already fine after index construction. |
| `storage.search(..., '/', 100)` | ~1.3s/query | Full scoped scan with haystack construction. |
| Peak RSS in measured process | ~2.4 to 2.5GB | Dense Python objects and dicts are too expensive. |

Corrected measurements after the first local optimization passes (`PYTHONPATH=src`):

| Pass | `TableStorage(...)` | Peak RSS | Search miss/hit shape | Notes |
| --- | ---: | ---: | --- | --- |
| Lazy item metrics + slots + fast URL names | ~15.4s | ~1.9GB | ~1.3s/query | Removed eager per-row metric dict construction. |
| Partial Arrow retention for metric columns | ~8.8s | ~1.2GB | ~1.3s/query | Avoided converting metric columns to Python lists at startup. |
| Fast HTTP logical path + remote mtime | ~7.2s | ~1.2GB | ~1.3s/query | Avoided generic URL parsing/time calls for uniform HTTP rows. |
| Fast trusted-HTTP scanner + fixed index assembly + lazy search cache | ~4.2s storage, ~4.7s `prepare_table_launch` | ~1.15GB before first search, ~1.25GB after miss/source cache | cold common path hit ~0.13s, first miss ~0.48-0.60s, repeated miss ~0.28-0.30s, warm common hit ~0.0001s | 500k HTTP parquet is now under the 5s backend launch target. |
| Continued HTTP fast-path pass | ~2.1s storage, ~2.37-2.55s `prepare_table_launch` | ~0.98-0.99GB | common prefix hit warm ~0.0000s, repeated full miss median ~0.17s | Fused HTTP scan+assembly, skipped aliased path/source columns, disabled GC during bulk object creation, converted numeric startup columns to NumPy, removed redundant source/name search. |
| Table row-view backend final | 3.339s `prepare_table_launch` | 827.4 MiB after launch, 856.9 MiB after recursive browse/search checks | repeated full miss median 0.168s in harness; live warm miss median 0.129s | Removed retained dense table item graph and folder item lists; first recursive 5k window 0.949s in harness, 0.387s over live HTTP probe. Target RSS remains above 750 MiB due to retained Arrow/NumPy metric columns and Python row/path/source/search caches. |

HTTP media benchmark on 24 `img.metanomaly.co` URLs:

| Fetch mode | Wall time | p50 | p95 | Notes |
| --- | ---: | ---: | ---: | --- |
| urllib sequential, 8 images | ~1.08s | ~0.086s | ~0.194s | Fresh stdlib request path. |
| shared httpx sequential, 8 images | ~0.74s | ~0.066s | ~0.157s | Keep-alive client. |
| urllib concurrent, 24 images, 8 workers | ~0.51s | ~0.083s | ~0.228s | Existing style. |
| shared httpx concurrent, 24 images, 8 workers | ~0.37s | ~0.065s | ~0.167s | New pooled media path. |

Next active targets if continuing:

- Further reduce retained row-view memory only with new scope: avoid duplicated path/source/name/search arrays, narrow row lookup structures, or move toward true lazy/windowed parquet reads.
- Add a true server-side filter/sort endpoint for large table scopes instead of filtering only loaded React pages.
- Consider a compact substring/token index if repeated full-scan miss latency (~0.17s at 500k) becomes user-visible at million-row scale.

The 10k sample shows the same shape at smaller scale: Arrow read is milliseconds, Python storage/index construction dominates.

## Profiler Attribution

cProfile on 500k rows showed the main Python costs:

- `_resolve_row_identity`: ~38s cumulative under profiler.
- `extract_name`: ~24s cumulative, called around 1M times.
- `_collect_row_metrics`: ~12.5s cumulative, with ~18.5M `coerce_float` calls.
- `urlparse` / `urlsplit`: ~15s cumulative combined.
- `table_to_columns`: ~5.9s under profiler, caused by `table.to_pydict()`.
- `assemble_indexes`: ~2.0s cumulative.
- `compute_local_prefix`: ~1.3s even for HTTP data, because it still checks every source as possible local.

Interpretation:

- Parquet IO is not the problem.
- Python per-row normalization, repeated URL/path parsing, per-item dataclasses, per-row metric dicts, and search haystack construction are the problem.
- For this HTTP dataset, Lenslet is doing too much generic local/S3/HTTP work per row despite a uniform source column.

## Rust Reference Lessons

Inspected:

- `/data/yada/dev_docs/parquet-rs`
- `/data/yada/dev_docs/dataio-rs`

Transferable patterns:

- Keep data Arrow-native as long as possible; avoid Arrow -> Python dict/list/object conversion for all rows.
- Use two-phase query/filter paths: evaluate filters on minimal columns, then project only the requested window.
- Use compact row selections/ranges/bitmaps instead of dense Python object graphs.
- Cache schema/metadata once and make request paths operate on already prepared indexes.
- For strings, avoid repeated generic URL parsing; specialize common uniform-column cases.
- For HTTP, use pooled persistent clients, bounded concurrency, and range requests. `urllib.request.urlopen` per image is not acceptable for remote-heavy browsing.
- For local files, prefer OS-backed streaming/zero-copy paths and avoid per-row `exists`/`realpath` unless required.

## Direction

This should be a hard cutover, not a compatibility layer. The project is alpha and the user explicitly requested boiling the ocean.

## Implemented in This Session

- Table ingestion no longer eagerly converts metric columns from Arrow to Python lists when a source column is explicit.
- Per-row public metric dictionaries are lazy; visible rows still expose the same API payload.
- Uniform HTTP source tables use a specialized trusted-extensionless scanner that avoids generic row identity, local-resolution, URL parsing, and dict-construction overhead.
- Index assembly no longer constructs discarded folder index objects via `dict.setdefault(... index_factory(...))`.
- Launch dimension scanning skips full width/height missing-count conversion unless dimension caching needs it.
- Table search bypasses the generic source-backed search path and uses compact on-demand path/source search arrays plus dynamic sidecar matching.
- HTTP media reads use a pooled `httpx.Client` with keep-alive limits instead of per-request `urllib.request.urlopen`.
- The measurement protocol is now explicitly `PYTHONPATH=src` to avoid importing the sibling checkout.
- Continued pass changes:
  - `prepare_table_launch` keeps projected auto path columns separate from explicit user path-column intent, so storage can fold duplicate HTTP `path` columns away.
  - Auto path/source alias detection treats `path == source` and `path == derive_http_logical_path(source)` as derived for HTTP tables.
  - The uniform HTTP path now directly builds `IndexAssemblyResult`, avoiding the temporary `ScannedRow` list and generic assembly pass.
  - The fast path no longer stores duplicate `source_paths`, avoids `path_to_row` when dimension probing is skipped, and stores `row_to_path` as a compact list.
  - Cyclic GC is paused during bulk table index/path-index construction for large row counts.
  - Null-free numeric startup columns use Arrow/NumPy conversion instead of `to_pylist()`.
  - HTTP-derived names are treated as covered by path search, avoiding per-row `item.name.lower()` in large miss scans.
  - HTTP logical-path derivation, MIME suffix guessing, and folder/name extraction were tightened in the fast loop.
  - Table mode now uses a row-view backend instead of retaining dense `TableBrowseItem` objects at startup.
  - Removed the old table-specific dense scan/build entrypoints while keeping generic dataset/local index assembly intact.
  - `TableRowStore.row_to_slot` is identity-lazy, so no-skip tables do not retain a redundant 500k-entry slot map.

### Backend Data Model

Replace eager dense browse-item construction for table mode with a columnar/lazy table index:

- Keep the `pyarrow.Table` or per-column arrays in `TableStorage`.
- Build only compact mandatory indexes at startup:
  - row count
  - source column
  - logical path column or derived path column
  - sorted row order by logical path, if required for scope windows
  - path -> row and row -> path maps only if needed for sidecars/embedding lookup
  - folder directory index
  - metric column names and Arrow arrays, not per-row metric dicts
- Materialize `TableRowViewItem` only for the requested API window or item route.
- Avoid storing `metrics: dict[str, float]` per row. Build metrics on payload conversion for visible/search/result rows.
- Add fast uniform-source handling:
  - if the source column is detected/explicit HTTP, use string prefix/path operations, not `urlparse` for every row.
  - if the logical path column is present, trust it after normalization and avoid deriving from source.
  - skip local prefix computation for explicit HTTP/S3 sources.
- Replace search full scans with a precomputed lowercase search corpus or columnar search index:
  - lowest-risk first step: store one normalized lowercase string per row for path/name/source and search that list.
  - next step: optional trigram/token inverted index for repeated substring search.
- Preserve existing FastAPI contracts unless the frontend can take better paged/search contracts immediately.

### Backend HTTP Media

Remote image fetch path needs a pooled client:

- Replace per-request `urllib.request.urlopen` for normal remote media reads with a persistent connection pool.
- Prefer `httpx` only if adding the dependency is acceptable; otherwise investigate stdlib limits and document why a dependency is required.
- Use timeouts and bounded concurrency.
- Keep `/thumb` generation queue bounded, but let HTTP keep-alive reuse connections across visible thumbnails.
- Consider serving remote originals by redirecting to source URLs for public HTTP sources when safe and configured, but default proxy behavior must still work.

### API/Browse Flow

Current frontend already uses recursive pages of 5000 items. Keep and strengthen that model:

- `/folders?recursive=1&offset=0&limit=5000` should not materialize all rows.
- `metric_keys` should come from known metric columns, not scan the whole folder window or full scope.
- Search should return bounded results and should not build sidecar state/haystacks for every row.
- Consider adding server-side filter/sort endpoints for large datasets instead of applying filters/sorts to only loaded pages in React. This is needed for correct filtering across 500k rows.

### Frontend

The frontend is already virtualized and paged. Main risks:

- Filtering/sorting only on currently loaded pages is fast but semantically wrong for 500k full-scope filters.
- Adaptive layout can be O(loaded items) and grows as more pages load.
- Thumbnail request budget is 6 concurrent. That is safe but may be slow for remote HTTP if each request pays new connection setup.

Planned frontend work after backend:

- Keep initial page small and render as soon as first page arrives.
- Avoid expensive adaptive layout over very large loaded arrays; use fixed grid or chunked adaptive rows for large scopes.
- Push heavy search/filter/sort to server for large table scopes.
- Tune thumb prefetch around visible rows only.

## Experiment Plan

1. Establish backend benchmark script.
   - Measure schema, column selection, Arrow read, storage construction, first folder page, search, and memory.
   - Run on 10k and 500k Parquets.

2. Implement columnar/lazy table storage.
   - Start by keeping API contracts stable.
   - Replace per-row metrics dict construction first, because it is clearly expensive and memory-heavy.
   - Then remove repeated URL parsing/source derivation when a path column exists.
   - Then defer item dataclass materialization to windows.

3. Add indexed search.
   - First version: precomputed row search text and scoped row iteration with early limit.
   - Later version: trigram/token index if repeated search remains slow.

4. Optimize HTTP media reads.
   - Benchmark current `/thumb` or direct `read_bytes` against `img.metanomaly.co` URLs.
   - Add pooled client and compare p50/p95 for concurrent thumbnail fetches.

5. Frontend validation.
   - Run the live server on the 500k HTTP Parquet.
   - Measure time to first grid items, scroll behavior, search latency, and thumbnail load behavior.

## Acceptance Checks

Minimum before handoff:

- `python scripts/lint_repo.py`
- focused table/storage tests
- focused route/search tests if API behavior changes
- frontend tests/build if frontend changes
- live browser smoke when UI behavior changes

Latest validation after the continued HTTP fast-path pass:

- `PYTHONPATH=src python scripts/lint_repo.py` passed. Warn-only file-size notices remain for `frontend/src/styles.css` and `scripts/browser/large_tree/smoke.py`.
- `PYTHONPATH=src python -m pytest -q` passed: 590 tests.
- `PYTHONPATH=src python -m scripts.browser.gui_smoke.acceptance` passed. It still emitted the known non-fatal folder re-entry anchor warning.
- Target 500k HTTP parquet benchmark: `prepare_table_launch` measured 2.37s on the best run after the continued pass, with peak RSS around 983MB. The index progress loop reported about 395k rows/sec. Repeated full-scan miss search median was about 0.17s.

Latest validation after the table row-view backend final pass:

- `PYTHONPATH=src python scripts/lint_repo.py` passed. Warn-only file-size notices remain for `frontend/src/styles.css` and `scripts/browser/large_tree/smoke.py`.
- `PYTHONPATH=src python -m pytest -q` passed: 595 tests.
- `PYTHONPATH=src python -m scripts.browser.gui_smoke.acceptance` passed.
- Target 500k HTTP parquet harness: `prepare_table_launch` 3.339s, RSS 827.4 MiB after launch and 856.9 MiB after checks, recursive 5k window 0.949s, repeated full-scan miss median 0.168s, and no dense table item graph at startup.
- Target live server probe: health ready for 500k rows, recursive 5k window 0.387s, and repeated warm search miss median 0.129s with zero hits.

Performance evidence to collect:

- 500k table startup breakdown before/after.
- First recursive folder page latency before/after.
- Search latency before/after.
- Peak RSS before/after.
- Remote thumbnail/file concurrent fetch benchmark before/after if HTTP client changes.

## Open Decisions

- Whether to add `httpx` as a required dependency for HTTP pooling. It is a boring/stable dependency and likely justified by the remote browsing requirement, but measure first.
- How far to change the browse API for server-side filter/sort. A stable hard cutover is allowed, but preserve the frontend user experience.
- Whether to keep full recursive browse disk cache for table mode. A columnar table index may make full JSON snapshot caches unnecessary or too memory-expensive.

## Resume Checklist

If resuming after context loss:

1. Read this file.
2. Check `git status --short`.
3. Re-run or inspect the benchmark for the current code.
4. Continue with the backend columnar/lazy table storage work first.
5. Do not start with Rust FFI unless Python/Arrow changes are exhausted. The current data shows Python object construction, not Parquet decoding, is the bottleneck.
