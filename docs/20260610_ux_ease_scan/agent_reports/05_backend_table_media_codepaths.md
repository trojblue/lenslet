# Backend/Table/Media Codepath Scan

## Scope And Files Inspected

Inspected backend/table/media/source behavior only. No code was modified.

Primary files: `src/lenslet/cli/browse.py`, `src/lenslet/cli/browse_args.py`, `src/lenslet/cli/hf_table.py`, `src/lenslet/storage/table/launch.py`, `src/lenslet/storage/table/storage.py`, `src/lenslet/storage/table/row_scan.py`, `src/lenslet/storage/table/row_store.py`, `src/lenslet/storage/table/source_detection.py`, `src/lenslet/storage/table/launch_sources.py`, `src/lenslet/storage/table/schema.py`, `src/lenslet/storage/source/paths.py`, `src/lenslet/storage/source/media.py`, `src/lenslet/storage/source/probe.py`, `src/lenslet/storage/source/probe_headers.py`, `src/lenslet/web/routes/media.py`, `src/lenslet/web/media.py`, `src/lenslet/web/routes/table_settings.py`, `src/lenslet/web/app/table.py`, `src/lenslet/web/app/storage.py`, `src/lenslet/web/app/local.py`, `src/lenslet/web/app/health.py`, `src/lenslet/web/models.py`, `src/lenslet/workspace.py`, `src/lenslet/http_safety.py`.

Relevant tests inspected: `tests/storage/table/test_parquet_ingestion.py`, `tests/storage/table/test_table_index_pipeline.py`, `tests/web/routes/test_table_source_settings.py`, `tests/web/media/test_media_error_contract.py`, `tests/web/hotpath/test_hotpath_sprint_s4.py`, `tests/cli/test_browse_table_launch.py`, `tests/cli/test_hf_table_loading.py`, workspace and health tests found by targeted `rg`.

## Concise Architecture Map

- CLI resolves target in `cli/browse.py`: local directory, local `.parquet`, `items.parquet`, HF dataset, or other remote URI.
- Local parquet launch goes through `prepare_table_launch()`: detect source/path columns, project browse columns, inspect dimensions, optionally probe/cache dimensions, resolve root, then create `TableStorage`.
- Remote HF launch downloads selected parquet shards through `hf_hub_download`, detects source column on local cached files, reads all shards into one Arrow table, then creates `TableStorage` with `allow_local=False`.
- Generic remote table launch uses `unibox.loads()` and converts table-like results with `to_pandas()` before passing to `TableStorage`.
- `TableStorage` normalizes table input into column arrays/lists, resolves source/path/name/mime/dimension columns, builds a row-native `TableRowStore`, and keeps item materialization lazy at API boundaries.
- Source resolution is centralized in `storage/source/paths.py`: S3 and HTTP logical paths derive from URI components; local paths resolve under `root` with lexical and realpath boundary checks.
- Media routes use logical paths only. `/file` streams local files via `FileResponse` when possible; remote sources fall back to backend byte reads. `/thumb` schedules thumbnail generation and optionally uses disk thumbnail cache.
- Runtime table settings expose and switch source columns only. They do not expose path/base-dir contracts, skipped-row counts, dimension-probe state, or selected backend root.

## Ranked Findings

1. **High - Default parquet dimension caching mutates the source table**
   - User impact: Launching a local parquet can rewrite `items.parquet` just to add/fill `width` and `height`. That surprises users who expect source data to stay read-only, risks data churn in versioned datasets, and makes startup failure modes scarier.
   - Root files: `cli/browse_args.py` (`cache_dimensions=True` default), `storage/table/launch.py` (`cache_missing_dimensions()`, `write_missing_dimensions()`), `cli/browse.py` (`--no-write` normalization).
   - Suggested fix shape: Hard cut over to immutable source tables by default. Store discovered dimensions in the workspace/parquet cache directory keyed by table signature and row identity. Add an explicit opt-in such as `--write-dimensions-to-parquet` only if in-place mutation remains needed.
   - Effort: M.
   - Performance/code-bloat risk: Low-to-medium. A sidecar dimension store adds one small contract but avoids full-table rewrites.
   - Validation: Focused pytest that launches a parquet with missing dimensions and asserts the parquet file hash/mtime is unchanged while `/folders`, `/metadata`, and `/thumb` see cached dimensions. Keep a separate opt-in test for parquet mutation if retained.

2. **High - Remote dimension header probes can stall startup without a timeout**
   - User impact: Default dimension caching can force probing missing remote dimensions. The regular probe path uses `urllib.request.urlopen()` without an explicit timeout, so a slow HTTP host can make Lenslet appear hung before the UI is usable.
   - Root files: `storage/source/probe_headers.py`, `storage/source/media.py`, `storage/table/storage.py`, `storage/source/probe.py`.
   - Suggested fix shape: Route all remote header probes through one timeout-bounded client policy, preferably the existing reusable `httpx.Client`, with per-request timeout, per-host concurrency, and a total probe budget. Treat failures as degraded row metadata, not startup blockers.
   - Effort: M.
   - Performance/code-bloat risk: Medium. Must avoid replacing a simple header read with a large retry subsystem.
   - Validation: Add a fake hanging/slow HTTP probe test that completes within a fixed wall-clock budget and leaves rows browseable with `(0, 0)` dimensions plus a surfaced degraded count.

3. **High - Corrupt parquet row groups only degrade optional table fields, not core startup**
   - User impact: Optional `table_fields` enrichment gracefully skips a bad row group, but the core projected `read_table()` path can still fail the whole table if a row group is corrupt in selected source/path/dimension columns. Users lose all good rows because one row group is bad.
   - Root files: `storage/table/launch.py`, `storage/table/storage.py`, `ParquetRowFieldProvider` in `storage/table/launch.py`.
   - Suggested fix shape: Make row-group tolerant parquet ingestion the canonical backend path: scan row groups for required browse columns, skip only unreadable groups, record skipped row-group counts, and keep optional field enrichment on the same row-group failure ledger.
   - Effort: L.
   - Performance/code-bloat risk: Medium. Done well, it improves memory behavior; done poorly, it duplicates ingestion logic.
   - Validation: Synthetic parquet/monkeypatch tests where one row group raises on read; assert valid row groups browse, skipped counts are reported, and item enrichment remains empty for failed optional groups.

4. **High - HTTP original media is fully buffered through the backend**
   - User impact: For HTTP sources, `/file` downloads the entire original image into server memory and then returns it. Large originals, rapid viewer navigation, or compare prefetch can waste bandwidth and memory even though the item payload already exposes the HTTP URL.
   - Root files: `web/media.py`, `storage/source/media.py`, `web/routes/media.py`, `storage/table/row_store.py`.
   - Suggested fix shape: Define an HTTP-original contract: direct URL handoff or 307 redirect for safe public HTTP sources, with backend streaming fallback when direct access is disabled or credentials/proxy behavior is required. If proxying, stream chunks instead of using `response.content`.
   - Effort: M.
   - Performance/code-bloat risk: Medium. Keep policy small: direct, stream, or backend-fallback; avoid a general download manager.
   - Validation: Hotpath tests asserting HTTP originals do not call full `read_bytes()` in direct mode; streaming test with a large fake response; browser smoke for viewer and compare prefetch.

5. **High - Source detection is split across launch and storage with slightly different semantics**
   - User impact: The launch detector picks a source column from the first parquet batch, while `TableStorage` later computes "usable" samples and may fallback among projected candidates. If the true image column is not projected, runtime fallback cannot recover. This can yield empty galleries with a plausible but wrong source column.
   - Root files: `storage/table/launch_sources.py`, `storage/table/source_detection.py`, `storage/table/launch.py`, `storage/table/storage.py`, `storage/table/schema.py`.
   - Suggested fix shape: Make one backend source-selection contract used by both launch and runtime settings. Score "usable gallery rows", not just loadable strings, over multiple batches/row groups within a bounded sample. Always include top candidate columns in projection with reason metadata.
   - Effort: M.
   - Performance/code-bloat risk: Low-to-medium if implemented as a shared selector returning structured decisions.
   - Validation: Tests with misleading first-batch columns, null-heavy first row group, page URL vs image URL, extensionless image URL with dimensions, and local relative paths requiring `base_dir`.

6. **Medium - CLI banner is printed before table preparation and omits effective table contracts**
   - User impact: The banner can say only "Table index" and workspace mode before source detection, root auto-detection, skipped-row reporting, dimension probing, or total image count is known. Users cannot tell whether Lenslet chose the expected source/path column until the UI loads or warnings scroll by.
   - Root files: `cli/browse.py`, `terminal_banner.py`, `storage/table/launch.py`, `storage/table/storage.py`.
   - Suggested fix shape: Print a short "preparing table" line before app creation, then a final ready/status block after storage creation with source column, path column, effective root/base-dir, usable rows/total rows, skipped rows by reason, dimension probe/cache policy, and server URL.
   - Effort: S.
   - Performance/code-bloat risk: Low.
   - Validation: CLI unit tests for banner/status output in local parquet, directory `items.parquet`, remote HF, `--no-write`, and auto-detected-root cases.

7. **Medium - Table settings expose source switching but not the full backend contract**
   - User impact: `/table/source-columns` helps when the source column is wrong, but users still cannot see or fix path-column choice, base-dir/root, skipped local boundary counts, dimension status, or why rows are degraded. Frontend inference would have to guess.
   - Root files: `web/routes/table_settings.py`, `web/models.py`, `storage/table/storage.py`, `web/app/health.py`.
   - Suggested fix shape: Add a backend-owned `table contract/status` payload: selected source column, selected path column, root/base-dir, source kind, row totals, skipped counts, dimension probe summary, and warnings. Keep mutation narrow: source switch now, path switch later only if the required columns are loaded or a reload is triggered.
   - Effort: M.
   - Performance/code-bloat risk: Low. Mostly exposing existing state plus a few counters.
   - Validation: API contract tests for local, remote, no-write, missing local rows, bad extensionless source, and switched source column.

8. **Medium - Skipped/degraded rows are printed but not retained as structured status**
   - User impact: Missing local files, paths outside `base_dir`, symlink escapes, and remote probe failures can leave a smaller gallery. Today some local skips print to stdout, but the UI and `/health` do not expose a durable explanation.
   - Root files: `storage/table/row_store.py`, `storage/table/storage.py`, `web/app/health.py`, `web/models.py`.
   - Suggested fix shape: Persist a `TableLoadReport` on `TableStorage` with total rows, loaded rows, skipped reasons, failed row groups, remote probe attempted/succeeded/failed, and source/path decisions. Surface it in health and table settings.
   - Effort: S/M.
   - Performance/code-bloat risk: Low if it is append-only counters, not per-row error storage.
   - Validation: Existing local boundary tests can assert structured counters in addition to stdout. Add remote probe failure counter tests.

9. **Medium - Remote/HF table loading materializes too much before Lenslet can project**
   - User impact: HF loads all selected parquet shards and concatenates them; generic remote loading may convert to pandas. Large hosted datasets can be slow or memory-heavy before the user sees anything, even though Lenslet only needs a narrow browse projection plus lazy table fields.
   - Root files: `cli/hf_table.py`, `cli/browse.py`, `storage/table/input.py`, `storage/table/launch.py`.
   - Suggested fix shape: Keep remote table data in Arrow/parquet fragments where possible. Detect schema/source from metadata plus bounded samples, then build the same projected row-store pipeline used for local parquet. Avoid `to_pandas()` in the generic remote path unless explicitly necessary.
   - Effort: L.
   - Performance/code-bloat risk: Medium. Best implemented by unifying local and remote parquet launch rather than adding a second remote-only path.
   - Validation: HF shard fixture tests with many columns, mixed schemas, and a large synthetic row count; assert only selected columns are read and memory stays bounded by batches.

10. **Medium - Uniform HTTP fast path is based on sampled source kind**
   - User impact: `source_kind` is sampled from up to 1024 values. If later rows mix HTTP with S3/local values, the uniform HTTP fast path can silently skip non-HTTP rows instead of using the general mixed-source path. This is rare but confusing in merged tables.
   - Root files: `storage/table/storage.py`, `storage/table/row_store.py`.
   - Suggested fix shape: Either compute source kind over the full selected source column with cheap vectorized/string scanning, or make the fast path prove homogeneity while scanning and fall back to the general path if it sees a mixed source.
   - Effort: S/M.
   - Performance/code-bloat risk: Low. A full pass over the selected source column is already in startup territory and cheaper than bad indexing.
   - Validation: Table with first 1024 HTTP rows and later S3/local rows; assert all valid rows are included or a structured mixed-source fallback is recorded.

11. **Medium - Logical path normalization lacks a strict backend namespace contract**
   - User impact: Explicit path-column values are normalized for slashes but not validated as a clean Lenslet namespace. Values with `..`, empty segments, schemes, or very long path strings can produce confusing folders, sidecar keys, and media route paths.
   - Root files: `storage/source/paths.py`, `storage/table/row_scan.py`, `web/paths.py`.
   - Suggested fix shape: Introduce one `LogicalPath` normalization/validation helper used by table ingestion and routes. Reject or degrade rows with empty paths, `.`/`..` segments, control characters, and overlong paths. Continue special handling for source URL aliases before validation.
   - Effort: S/M.
   - Performance/code-bloat risk: Low.
   - Validation: Unit tests for explicit `path_column` values with traversal-like segments, duplicated paths, HTTP URL aliases, S3 aliases, and normal nested paths.

12. **Low - `--no-write` messaging is technically correct but easy to misread**
   - User impact: When `--no-write` disables dimension caching, the CLI says "use --no-cache-dimensions to silence." That reads like the user did something wrong even though `--no-write` is the safer mode.
   - Root files: `cli/browse_args.py`, `cli/browse.py`.
   - Suggested fix shape: Reword as status: "No-write: parquet dimension caching disabled; using temp workspace ..." and only mention `--no-cache-dimensions` in verbose/help text.
   - Effort: S.
   - Performance/code-bloat risk: None.
   - Validation: Existing CLI normalization tests with updated expected output.

## 3 Quick Wins

1. Reword `--no-write` and dimension-cache status messages so safe/read-only behavior sounds intentional, not like a warning.
2. Add selected source column, path column, effective root/base-dir, loaded row count, and skipped row count to CLI post-launch status and `/health` or `/table/source-columns`.
3. Add explicit timeout handling to regular remote header probes and count probe failures instead of leaving them invisible.

## 3 Medium Projects

1. Move dimension persistence out of source parquet files into a workspace-backed dimension cache keyed by table signature and row identity.
2. Unify source-column detection, projection, and runtime source switching around one structured selector that scores usable image rows across bounded columnar samples.
3. Replace all-at-once parquet startup with row-group-aware ingestion that can skip corrupt groups, preserve valid rows, and keep optional table fields lazy.

## Things Not To Do

- Do not push source/path inference into the frontend; the backend owns media loading, row degradation, and logical path contracts.
- Do not add broad compatibility shims for old table naming conventions beyond the current recognized columns; this is pre-release, so prefer a clean `--source-column`/`--path-column`/status contract.
- Do not keep mutating parquet files by default just because it improves later startup. Put cache data in Lenslet workspace/cache state unless the user explicitly opts into table rewrite.
- Do not implement a general remote download manager for HTTP originals. Prefer direct URL handoff or streaming proxy with small, explicit policy.
- Do not hide skipped rows as stdout-only messages. If a row does not appear, the backend should expose the reason in structured status.

## Top 5 Recommendations

1. Make source parquet immutable by default; move dimension caching to Lenslet workspace/cache state.
2. Put timeouts, budgets, and structured degraded counts around remote dimension probing.
3. Unify source-column detection and runtime source settings under one backend-owned contract.
4. Add table contract/status reporting to CLI and API: source, path, root, row totals, skipped reasons, and dimension state.
5. Build a row-group tolerant parquet ingestion path so one bad row group does not prevent valid rows from browsing.
