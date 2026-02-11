# S3 T11: Probe and Media Reader Extraction

Date: 2026-02-11

## Summary

`TableStorage` probe and dimension-reader internals were extracted from `src/lenslet/storage/table.py` into dedicated collaborators:

- `src/lenslet/storage/table_probe.py`
  - `effective_remote_workers(...)`
  - `parse_content_range(...)`
  - `get_remote_header_bytes(...)`
  - `get_remote_header_info(...)`
  - `probe_remote_dimensions(...)`
- `src/lenslet/storage/table_media.py`
  - `read_dimensions_from_bytes(...)`
  - `read_dimensions_fast(...)`
  - `read_jpeg_dimensions(...)`
  - `read_png_dimensions(...)`
  - `read_webp_dimensions(...)`

`TableStorage` keeps compatibility wrappers (`_probe_remote_dimensions`, `_effective_remote_workers`, `_parse_content_range`, `_get_remote_header_*`, `_read_dimensions_*`, and format-specific readers), so callers and monkeypatch surfaces remain unchanged.

## Line-Budget Effect

- `src/lenslet/storage/table.py`: `855` -> `710` lines

## Validation

- `python -m compileall -q src/lenslet/storage/table.py src/lenslet/storage/table_probe.py src/lenslet/storage/table_media.py` -> `compile-ok`
- `pytest -q tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_import_contract.py` -> `12 passed`
- `pytest -q --durations=10 tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py` -> `6 passed`; slowest case `0.10s`
- `pytest -q tests/test_table_index_pipeline.py` -> `2 passed`
- import probe -> `import-contract-ok`
