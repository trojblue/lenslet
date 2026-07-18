# Sprint 10 row-group and table-source evidence

Date: 2026-07-18 UTC

This note records the independent Sprint 10 conditional gates. The fixtures are synthetic, generated in temporary directories, and do not write user source data.

## S10-T1: multi-row-group detail gate

Command:

```bash
python scripts/perf/table_row_group_detail.py \
  --output-json docs/20260718_table_row_group_detail_result.json
```

The production launch path created a 4,000-row Parquet file with eight 500-row groups and twelve deferred scalar fields. The probe alternated `GET /item` reads over a four-group working set. A controlled one-group-cache prefix on the identical fixture performed 80 measured row-group reads at 5.391 ms p95. Because query-column preload did not eliminate repeated conversions, the plan's conjunctive skip gate was not met even though latency was below 50 ms.

The exact four-group LRU warmed each group once, then performed zero measured reads over 80 requests. It retained exactly four groups and measured 1.169 ms p95. The retained machine-readable prefix and result are:

- `docs/20260718_table_row_group_detail_prefix.json`
- `docs/20260718_table_row_group_detail_result.json`

Focused tests also prove exact eviction after a fifth group, reuse after eviction, serialization of concurrent PyArrow access, and retention of good cached groups when another group fails.

Decision: implement S10-T1's bounded four-row-group LRU.

## S10-T2: source-version detection

Local Parquet launches capture an opaque fingerprint before source reads and verify the same generation after them. The fingerprint covers device, inode, size, modification time, change time, and up to eight 4 KiB content samples. Intentional launch-time dimension rewrites are guarded, then recaptured and checked against the exact Arrow table Lenslet wrote before lazy providers are opened. A runtime-owned one-second monitor performs the two stats plus bounded 32 KiB sample read/hash off the event loop. An atomic source replacement produces one `table-source` sync transition to `restart-required`; subsequent polls are deduplicated. Health exposes the same live state and disables refresh with an actionable restart message. Paths and raw fingerprint fields are absent from health and sync payloads.

The replacement integration fixture proves that the served storage remains one complete old snapshot: source rows, gallery rows, and total images all stay at one after replacing the file with a two-row table. The complete immutable `launch_session` payload stays byte-for-byte equal, while only `table_launch_status.source_refresh` changes. Deferred row-group fields and embeddings already loaded into memory remain on the old generation; an uncached source-backed read after a change fails closed with `409 table_source_changed` instead of mixing generations. Remote/unversioned sources start in explicit `restart-required` state because Lenslet has no safe version primitive for them.

Focused validation:

```bash
python -m pytest -q \
  tests/storage/table/test_table_source_refresh.py \
  tests/web/routes/test_table_source_settings.py \
  tests/web/app/test_launch_session_health.py \
  tests/cli/test_browse_table_launch.py \
  tests/embeddings/test_embeddings_search.py
# 38 passed

cd frontend
npm test -- --run \
  src/api/__tests__/client.events.test.ts \
  src/shared/ui/__tests__/ThemeSettingsMenu.test.tsx
# 18 passed
npx tsc --noEmit
# passed
```

Decision: implement cheap detection and explicit restart-required state without rebuilding the live table.

## S10-T3: atomic automatic refresh gate

Automatic live refresh is not required by the source-change gate. S10-T2 satisfies the Sprint 10 demo and acceptance contract by clearly reporting restart required while continuing to serve one immutable old snapshot. Building an automatic replacement would additionally have to recreate generation-captured embedding, query, thumbnail, persistence, and route ownership safely; no observed workflow requires that expansion.

Startup-only detail labels no longer embed a row count. Current counts are derived exclusively from live `table_launch_status`, so immutable launch provenance cannot conflict with mutable source status.

Decision: skip S10-T3 successfully. A future live-refresh requirement must reopen it with the planned off-side rebuild, old-or-new atomic swap, canonical-path sidecar transfer, and failed-build fallback contract.
