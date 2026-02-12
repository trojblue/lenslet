# S3 / T10: Table Index Pipeline Extraction and Loop De-duplication

Timestamp: 2026-02-11T05:25:21Z

## Goal

Extract the `TableStorage` index build path into a dedicated module with explicit scan/assemble phases, and remove repeated per-row work in hot loops while preserving existing browse/search semantics.

## Changes

1. `src/lenslet/storage/table_index.py`
   - Added `build_table_indexes(...)` as the new index-build entrypoint.
   - Split the flow into explicit phases:
     - `build_index_columns(...)` precomputes source/path/metadata/metrics column views once.
     - `scan_rows(...)` performs row validation and item construction.
     - `assemble_indexes(...)` materializes folder/item indexes and row-path maps.
   - Added `ProgressTicker` to centralize progress-throttled updates.
   - Added delegated helpers `extract_row_metrics(...)` and `extract_row_metrics_map(...)`.

2. `src/lenslet/storage/table.py`
   - Replaced inlined `_build_indexes(...)` body with a delegation call to `build_table_indexes(...)`.
   - Kept `_extract_metrics(...)` and `_extract_metrics_map(...)` as compatibility wrappers, now delegating to `table_index.py`.

3. Optimization details in `scan_rows(...)`
   - Precomputed column vectors and metric column selectors once per build (removed repeated `dict.get(..., [None] * row_count)` allocation in row loops).
   - Reused resolved local paths for existence/size/mtime/dimension checks instead of resolving repeatedly per row.
   - Preserved all existing skip/warning semantics and remote-dimension probe scheduling behavior.

4. `tests/test_table_index_pipeline.py`
   - Added regression coverage for metric merge precedence (`metrics` map overrides scalar columns).
   - Added regression coverage for duplicate logical-path dedupe and row-index mapping continuity.

## Validation

- `pytest -q tests/test_table_index_pipeline.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py tests/test_import_contract.py`
  - Result: `14 passed in 0.92s`.
- `pytest -q --durations=10 tests/test_table_index_pipeline.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_remote_worker_scaling.py`
  - Result: `7 passed in 0.73s`.
- `python -m compileall -q src/lenslet/storage/table.py src/lenslet/storage/table_index.py && echo compile-ok`
  - Result: `compile-ok`.
- Import-contract probe script
  - Result: `import-contract-ok`.

## Before/After Benchmark Snapshot

Benchmark harness: synthetic local dataset (`1200` rows, each with scalar + nested metrics columns), `TableStorage(rows, skip_indexing=True)`, median/mean across 5 construction rounds.

- Before (`pre-T10`): `median=0.0259s`, `mean=0.0267s`.
- After (`T10`): `median=0.0192s`, `mean=0.0196s`.

Observed delta on this harness:
- median improved by ~25.9%
- mean improved by ~26.6%

This is synthetic and local-only, but it validates reduced index-construction loop overhead without changing external behavior.
