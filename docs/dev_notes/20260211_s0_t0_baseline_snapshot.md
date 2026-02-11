# S0 T0 Baseline Snapshot

Timestamp (UTC): `2026-02-11T04:12:31Z`  
Branch: `main`  
Plan ticket: `T0`

## Baseline Validation Results

### Backend parity matrix

Command:

```bash
pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py
```

Result:

- `63 passed in 3.49s`
- Wall-clock envelope (`/usr/bin/time`): `elapsed=0:04.06 user=3.01 sys=0.30 maxrss_kb=208356`

### Import compatibility probe

Command:

```bash
python - <<'PY'
import lenslet.server as server
import lenslet.storage.table as table
assert hasattr(server, 'create_app')
assert hasattr(server, 'create_app_from_datasets')
assert hasattr(server, 'create_app_from_table')
assert hasattr(server, 'create_app_from_storage')
assert hasattr(server, 'HotpathTelemetry')
assert hasattr(server, '_file_response')
assert hasattr(server, '_thumb_response_async')
assert hasattr(server, 'og')
assert hasattr(table, 'TableStorage')
assert hasattr(table, 'load_parquet_table')
assert hasattr(table, 'load_parquet_schema')
print('import-contract-ok')
PY
```

Result:

- `import-contract-ok`

## Hotpath Timing Snapshot

Command:

```bash
pytest -q --durations=10 tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py
```

Result:

- `19 passed in 0.84s`
- Wall-clock envelope (`/usr/bin/time`): `elapsed=0:01.19 user=1.51 sys=0.11 maxrss_kb=118612`
- Slowest case: `tests/test_hotpath_sprint_s3.py::test_thumb_disconnect_cancels_inflight_work_and_worker_stays_healthy` at `0.10s`

## Notes

- This file is the pre-refactor baseline reference for S1+ parity and hotpath comparisons.
