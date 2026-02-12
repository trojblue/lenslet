# S3 T12 - TableStorage Facade Delegation

Date: 2026-02-11
Ticket: S3 / T12

## Summary

`TableStorage` was kept as the compatibility facade while moving table-shape parsing, byte I/O, thumbnail generation, dimensions/metadata/search operations, and S3 presign-client helpers into a new collaborator module:

- `src/lenslet/storage/table_facade.py`

`src/lenslet/storage/table.py` now delegates those behaviors through thin wrappers so constructor and method contracts stay unchanged for callers and monkeypatch-based tests.

## Structural delta

- `src/lenslet/storage/table.py`: `710` -> `532` lines.
- Added `src/lenslet/storage/table_facade.py` (`250` lines).

## Compatibility choices

1. Kept all existing `TableStorage` public/private method names in `table.py` (`read_bytes`, `get_thumbnail`, `get_dimensions`, `get_metadata`, `set_metadata`, `search`, `_get_s3_client`, `_get_presigned_url`, `_guess_mime`, `_table_to_columns`).
2. Preserved exception and error-message semantics in delegated helpers.
3. Kept worker-scaling monkeypatch behavior via `TableStorage._effective_remote_workers` using `table.py`'s `os.cpu_count`.

## Validation

- `python -m compileall -q src/lenslet/storage/table.py src/lenslet/storage/table_facade.py src/lenslet/storage/table_index.py src/lenslet/storage/table_probe.py src/lenslet/storage/table_media.py` -> `compile-ok`
- `python - <<'PY' ...` import probe -> `import-contract-ok`
- `pytest -q tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py tests/test_table_index_pipeline.py tests/test_import_contract.py` -> `18 passed in 0.98s`
- `pytest -q tests/test_hotpath_sprint_s4.py` -> `10 passed in 0.61s`
- `pytest -q --durations=10 tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py` -> `6 passed in 0.63s` (slowest case `0.10s`)
