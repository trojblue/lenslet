# Foundational Refactor and Performance Plan for Longest Core Files


## Purpose / Big Picture


No `PLANS.md` (or equivalent canonical planning file) exists in this repository, so this document is the canonical execution plan for this change set. After implementation, users should see unchanged Lenslet behavior and API contracts, but with materially better maintainability and targeted runtime speedups in hot paths. The redesign assumes modular boundaries and performance budgets were first-day assumptions, not retrofit constraints.

This plan now explicitly allows bold internal refactors and algorithmic optimizations. The guardrail is strict behavioral parity at public interfaces: same endpoints, same payload contracts, same user-visible semantics, same workspace data model, and no broad product-scope changes.


## Progress


- [x] 2026-02-11 03:55:02Z Confirmed target scope and measured file-length hotspots for `src/lenslet/server.py`, `src/lenslet/storage/table.py`, `frontend/src/app/AppShell.tsx`, `frontend/src/features/inspector/Inspector.tsx`, and `frontend/src/features/metrics/MetricsPanel.tsx`.
- [x] 2026-02-11 03:55:02Z Mapped structural hotspots (route density, hook density, large methods/components) and existing automated test coverage in `tests/` and `frontend/src/**/__tests__/`.
- [x] 2026-02-11 04:01:34Z Captured user directive to permit larger, performance-oriented refactors while preserving behavior and contracts.
- [x] 2026-02-11 04:01:34Z Completed mandatory subagent review using the required prompt and integrated findings (architecture gate, compatibility matrix, validation expansion, ticket splits, artifact sync).
- [x] 2026-02-11 04:01:34Z Finalized this plan as implementation handoff under `docs/`.
- [x] 2026-02-11 04:12:31Z Completed S0 `T0` baseline snapshot capture: backend parity matrix (`63 passed`), import-contract probe (`import-contract-ok`), and hotpath timing baseline (`19 passed`, slowest case `0.10s`) recorded in `docs/dev_notes/20260211_s0_t0_baseline_snapshot.md`.
- [x] 2026-02-11 04:21:23Z Completed S0 `T1` seam-map capture: added per-file extraction map in `docs/dev_notes/20260211_s0_t1_seam_map.md` plus `S0/T1 seam anchors` comments in `src/lenslet/server.py`, `src/lenslet/storage/table.py`, `frontend/src/app/AppShell.tsx`, `frontend/src/features/inspector/Inspector.tsx`, and `frontend/src/features/metrics/MetricsPanel.tsx`; validation: backend slice (`11 passed`), import probe (`import-contract-ok`), frontend slice (`19 passed`).
- [x] 2026-02-11 04:22:50Z Completed S0 `T2a` architecture decision gate: added module-structure artifact `docs/dev_notes/20260211_s0_t2a_server_module_structure_gate.md`, explicitly locked module-only extraction (`server.py` + sibling helpers), and recorded the no-package-conversion constraint before S1 edits; validation: architecture-link check and module import probe (`server-module-import-ok`).
- [x] 2026-02-11 04:25:18Z Completed S0 `T2b` import-compatibility contract checks: added `tests/test_import_contract.py` to lock public/de-facto symbol exposure (`create_app*`, `HotpathTelemetry`, `_file_response`, `_thumb_response_async`, `og`, `TableStorage`, parquet loaders) plus the monkeypatch-sensitive `lenslet.server.og.subtree_image_count` path; validation: `pytest -q tests/test_import_contract.py` (`2 passed`) and import probe (`import-contract-ok`).
- [x] 2026-02-11 04:27:13Z Completed S1 `T3` runtime extraction: added `src/lenslet/server_runtime.py` with `build_app_runtime` and `AppRuntime`, rewired `create_app`, `create_app_from_datasets`, and `create_app_from_storage` through shared runtime construction while preserving `lenslet.server` facade symbols and health payload semantics; validation: `pytest -q tests/test_hotpath_sprint_s3.py tests/test_presence_lifecycle.py tests/test_refresh.py tests/test_import_contract.py` (`21 passed`), `pytest -q tests/test_hotpath_sprint_s4.py tests/test_collaboration_sync.py` (`14 passed`), and import probe (`import-contract-ok`).
- [x] 2026-02-11 04:38:56Z Completed S1 `T4a` common-route extraction: added `src/lenslet/server_routes_common.py` and moved folder/item/metadata/export/events/thumb/file/search route registration (plus route-local item-update helper) out of `src/lenslet/server.py`, while preserving `lenslet.server` facade symbols and behavior contracts; validation: `pytest -q tests/test_folder_pagination.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_collaboration_sync.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_import_contract.py` (`42 passed`) and import probe (`import-contract-ok`).
- [x] 2026-02-11 04:43:53Z Completed S1 `T4b` presence-route extraction: added `src/lenslet/server_routes_presence.py` and moved presence diagnostics/payload/prune-loop/route registration helpers out of `src/lenslet/server.py`, while keeping `lenslet.server` facade aliases (`_register_presence_routes`, `_touch_presence_edit`, `_presence_runtime_payload`, `_install_presence_prune_loop`) for compatibility; validation: `pytest -q tests/test_presence_lifecycle.py tests/test_collaboration_sync.py tests/test_hotpath_sprint_s4.py tests/test_import_contract.py` (`24 passed`) and import probe (`import-contract-ok`).
- [x] 2026-02-11 04:45:14Z Completed S1 `T4c` embeddings/views-route extraction: added `src/lenslet/server_routes_embeddings.py` and `src/lenslet/server_routes_views.py`, moved `/embeddings`, `/embeddings/search`, and `/views` registration out of `src/lenslet/server.py`, and preserved `_register_embedding_routes` plus `_register_views_routes` facade aliases through sibling-module imports; validation: `pytest -q tests/test_embeddings_search.py tests/test_parquet_ingestion.py tests/test_embeddings_cache.py tests/test_import_contract.py` (`9 passed`) and import probe (`import-contract-ok`).
- [x] 2026-02-11 04:52:09Z Completed S1 `T4d` index/OG/media extraction: added `src/lenslet/server_media.py`, `src/lenslet/server_routes_index.py`, and `src/lenslet/server_routes_og.py`, moved media response helpers plus index/OG route registration out of `src/lenslet/server.py`, and preserved `lenslet.server` facade aliases (`_thumb_response_async`, `_file_response`, `_register_index_routes`, `_register_og_routes`, `NoCacheIndexStaticFiles`) via sibling-module imports; validation: `pytest -q tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_compare_export_endpoint.py tests/test_import_contract.py` (`31 passed`) and import probe (`import-contract-ok`).
- [x] 2026-02-11 04:54:19Z Completed S1 `T5` facade stabilization: added `src/lenslet/server_browse.py` and `src/lenslet/server_factory.py`, reduced `src/lenslet/server.py` to a 335-line facade that re-exports compatibility touchpoints while retaining monkeypatch-sensitive comparison-export helpers/constants on `lenslet.server`; validation: `pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py tests/test_import_contract.py` (`65 passed`) plus import probe (`import-contract-ok`).
- [x] 2026-02-11 05:02:54Z Completed S2 `T6` recursive traversal hotpath optimization: updated `src/lenslet/server_browse.py` to window non-legacy recursive pagination during traversal (`limit=page*page_size`) while still counting full recursive totals, preserved legacy recursive full-result behavior, and recorded before/after evidence in `docs/dev_notes/20260211_s2_t6_recursive_traversal_windowing.md`; validation: `pytest -q tests/test_folder_pagination.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py` (`30 passed`), `pytest -q --durations=10 tests/test_folder_pagination.py tests/test_hotpath_sprint_s4.py` (`15 passed`, recursive hot case `0.14s` -> `0.13s`), `pytest -q tests/test_import_contract.py` (`2 passed`), and import probe (`import-contract-ok`).
- [x] 2026-02-11 05:10:38Z Completed S2 `T7` thumb/file response optimization: updated `src/lenslet/server_media.py` so local file resolution returns a precomputed `stat_result` and `_file_response` forwards it to `FileResponse(...)`, reducing blocking filesystem work on the local streaming path without changing headers or remote fallback semantics; added parity assertion in `tests/test_hotpath_sprint_s2.py` and recorded evidence in `docs/dev_notes/20260211_s2_t7_media_stat_reuse.md`; validation: `pytest -q tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s4.py tests/test_metadata_endpoint.py tests/test_import_contract.py` (`18 passed`), `pytest -q --durations=10 tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s4.py` (`14 passed`), and import probe (`import-contract-ok`).
- [x] 2026-02-11 05:15:47Z Completed S2 `T8` presence/sync incidental-overhead optimization: added no-op delta fast-pathing in `src/lenslet/server_routes_presence.py`, reduced `PresenceTracker` prune/count allocation churn plus `EventBroker.replay` no-new-event scanning in `src/lenslet/server_sync.py`, and added replay-contract regression coverage in `tests/test_presence_lifecycle.py`; recorded implementation/validation evidence in `docs/dev_notes/20260211_s2_t8_presence_sync_fastpaths.md`; validation: `pytest -q tests/test_presence_lifecycle.py tests/test_collaboration_sync.py tests/test_hotpath_sprint_s4.py tests/test_import_contract.py` (`25 passed`), `pytest -q --durations=10 tests/test_presence_lifecycle.py tests/test_collaboration_sync.py` (`13 passed`), and import probe (`import-contract-ok`).
- [x] 2026-02-11 05:20:14Z Completed S3 `T9` table schema/path extraction: added `src/lenslet/storage/table_schema.py` and `src/lenslet/storage/table_paths.py`, rewired `src/lenslet/storage/table.py` to delegate source/path/coercion helpers while preserving `TableStorage` method contracts, and reduced `table.py` from 1272 to 1100 lines; validation: `pytest -q tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_import_contract.py` (`6 passed`), `pytest -q tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py` (`6 passed`), compile check (`compile-ok`), and import probe (`import-contract-ok`).
- [x] 2026-02-11 05:25:21Z Completed S3 `T10` table index pipeline extraction/optimization: added `src/lenslet/storage/table_index.py` with explicit `build_index_columns` -> `scan_rows` -> `assemble_indexes` phases, delegated `TableStorage._build_indexes` plus metric-extraction helpers through the new module, added regression coverage in `tests/test_table_index_pipeline.py`, and reduced `table.py` from 1100 to 855 lines; validation: `pytest -q tests/test_table_index_pipeline.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py tests/test_import_contract.py` (`14 passed`), `pytest -q --durations=10 tests/test_table_index_pipeline.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_remote_worker_scaling.py` (`7 passed`), compile check (`compile-ok`), import probe (`import-contract-ok`), and benchmark note `docs/dev_notes/20260211_s3_t10_table_index_pipeline.md` (`median 0.0259s` -> `0.0192s`, `mean 0.0267s` -> `0.0196s`).
- [x] 2026-02-11 05:37:46Z Completed S3 `T11` probe/media extraction: added `src/lenslet/storage/table_probe.py` and `src/lenslet/storage/table_media.py`, rewired `src/lenslet/storage/table.py` to keep compatibility wrappers while delegating remote-header probing and fast dimension readers/parsers, and reduced `table.py` from 855 to 710 lines; validation: `pytest -q tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_import_contract.py` (`12 passed`), `pytest -q --durations=10 tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py` (`6 passed`, slowest case `0.10s`), `pytest -q tests/test_table_index_pipeline.py` (`2 passed`), compile check (`compile-ok`), and import probe (`import-contract-ok`); artifact: `docs/dev_notes/20260211_s3_t11_probe_media_extraction.md`.
- [x] 2026-02-11 05:39:21Z Completed S3 `T12` facade delegation: added `src/lenslet/storage/table_facade.py`, rewired `src/lenslet/storage/table.py` to keep constructor/public/private method contracts as thin wrappers while delegating table-shape parsing, byte I/O, thumbnail generation, dimensions/metadata/search, and S3 presign-client helpers, and reduced `table.py` from 710 to 532 lines; validation: `pytest -q tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py tests/test_table_index_pipeline.py tests/test_import_contract.py` (`18 passed`), `pytest -q tests/test_hotpath_sprint_s4.py` (`10 passed`), `pytest -q --durations=10 tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py` (`6 passed`, slowest case `0.10s`), compile check (`compile-ok`), and import probe (`import-contract-ok`); artifact: `docs/dev_notes/20260211_s3_t12_table_facade_delegate.md`.
- [x] 2026-02-11 05:39:21Z Completed S0 `T2c` API freeze checkpoint after S3: recorded backend-contract sign-off before frontend refactors using completed S1-S3 parity slices, import-contract probe continuity, and S3 handover acceptance notes.
- [x] 2026-02-11 05:49:36Z Completed S4 `T13a` AppShell data-scope extraction: added `frontend/src/app/hooks/useAppDataScope.ts` and rewired `frontend/src/app/AppShell.tsx` so recursive folder hydration, query-cache cleanup, search/embeddings loading, and pool/similarity/item derivation run through the new hook while selection/presence/mutation flows remain unchanged; validation: `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`39 passed`), `npm run build` (success), and `npx tsc --noEmit` (fails due pre-existing repo type errors in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).
- [x] 2026-02-11 05:58:53Z Completed S4 `T13b` AppShell selection/viewer/compare extraction: added `frontend/src/app/hooks/useAppSelectionViewerCompare.ts` and rewired `frontend/src/app/AppShell.tsx` so selection state, viewer/compare history semantics, compare derivations, and image navigation live in the new hook while data-scope, presence, and mutation domains remain unchanged; reduced `AppShell.tsx` from `2125` to `2020` lines; validation: `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`39 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures remain in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).
- [x] 2026-02-11 06:00:15Z Completed S4 `T13c` AppShell presence/sync extraction: added `frontend/src/app/hooks/useAppPresenceSync.ts` and rewired `frontend/src/app/AppShell.tsx` so presence scope lifecycle, event subscriptions, connection status handling, and activity derivations (off-view summary/highlights/recent touches) are owned by the new hook while data-scope, selection/viewer/compare, and mutation domains remain unchanged; reduced `AppShell.tsx` from `2020` to `1664` lines; artifact `docs/dev_notes/20260211_s4_t13c_presence_sync_hook.md`; validation: `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`39 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures remain in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).
- [x] 2026-02-11 06:08:15Z Completed S4 `T13d` AppShell mutation/actions extraction: added `frontend/src/app/hooks/useAppActions.ts` and rewired `frontend/src/app/AppShell.tsx` so upload/move/context-menu state, drag-drop upload handling, destination-folder loading, and mutation error formatting live in the new hook while AppShell retains folder-refresh primitives and view persistence flows; reduced `AppShell.tsx` from `1664` to `1429` lines; validation: `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`39 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures remain in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).
- [x] 2026-02-11 09:38:22Z Completed S4 `T14` AppShell selector/model extraction: added `frontend/src/app/model/appShellSelectors.ts` and `frontend/src/app/__tests__/appShellSelectors.test.ts`, rewired `frontend/src/app/AppShell.tsx` to use pure selectors for metric-scrollbar eligibility, star-count aggregation, metric-key collection, and similarity/display label derivations, and reduced `AppShell.tsx` from `1429` to `1385` lines; validation: `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures remain in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).
- [x] 2026-02-11 09:44:52Z Completed S4 `T15` AppShell listener-lifecycle optimization: added `frontend/src/shared/hooks/useLatestRef.ts` and rewired `frontend/src/app/AppShell.tsx` so hash-sync, global-keyboard, and pinch-resize listeners read latest state via stable refs instead of re-registering on routine state churn; recorded implementation/perf evidence in `docs/dev_notes/20260211_s4_t15_listener_lifecycle_stabilization.md`; validation: `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures remain in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).
- [x] 2026-02-11 09:48:03Z Completed S5 `T16` Inspector metadata/compare model extraction: added `frontend/src/features/inspector/model/metadataCompare.ts` and `frontend/src/features/inspector/model/__tests__/metadataCompare.test.ts`, rewired `frontend/src/features/inspector/Inspector.tsx` to consume pure metadata display/path/copy helpers plus compare-diff derivation, and reduced `Inspector.tsx` from `1567` to `1313` lines while preserving compare/export UI behavior; validation: `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts` (`15 passed`) and `npm run build` (success).
- [x] 2026-02-11 09:55:59Z Completed S5 `T17` Inspector typed section split: added `frontend/src/features/inspector/sections/InspectorSection.tsx`, `OverviewSection.tsx`, `CompareMetadataSection.tsx`, `BasicsSection.tsx`, `MetadataSection.tsx`, and `NotesSection.tsx`; rewired `frontend/src/features/inspector/Inspector.tsx` to delegate overview/compare/basics/metadata/notes rendering through typed section components while preserving existing state/effect ownership and interaction contracts; line budget moved from `1313` to `865` lines for `frontend/src/features/inspector/Inspector.tsx`; validation: `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts` (`15 passed`) and `npm run build` (success).
- [x] 2026-02-11 10:05:03Z Completed S5 `T18` Inspector async workflow extraction: added `frontend/src/features/inspector/hooks/useInspectorSidecarWorkflow.ts` (typing + sidecar conflict/apply/keep flows) and `frontend/src/features/inspector/hooks/useInspectorMetadataWorkflow.ts` (metadata load/reload, compare metadata fetch lifecycle, comparison export submit), rewired `frontend/src/features/inspector/Inspector.tsx` to consume both hooks while preserving existing copy/render interactions, and reduced `Inspector.tsx` from `865` to `714` lines; validation: `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts` (`15 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures remain in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).
- [x] 2026-02-11 11:20:25Z Completed S5 `T19` Inspector render-path optimization: added normalized-metadata reuse helpers in `frontend/src/features/inspector/model/metadataCompare.ts` (`normalizeMetadataRecord`, `buildDisplayMetadataFromNormalized`, `buildCompareMetadataDiffFromNormalized`), rewired `frontend/src/features/inspector/Inspector.tsx` to reuse normalized compare metadata and gate heavy compare/metadata rendering work to open sections, memoized heavy section components in `frontend/src/features/inspector/sections/CompareMetadataSection.tsx` and `frontend/src/features/inspector/sections/MetadataSection.tsx`, and added parity coverage in `frontend/src/features/inspector/model/__tests__/metadataCompare.test.ts`; validation: `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts` (`16 passed`), `npm run build` (success), `npx tsc --noEmit` (known pre-existing failures remain in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`), and benchmark note `docs/dev_notes/20260211_s5_t19_inspector_render_optimization.md` (`median 12.88ms` -> `10.65ms`, `mean 13.43ms` -> `10.93ms` on synthetic large compare payload).
- [x] 2026-02-11 11:28:25Z Completed S6 `T20` Metrics component split: extracted `frontend/src/features/metrics/components/AttributesPanel.tsx`, `frontend/src/features/metrics/components/MetricRangePanel.tsx`, and `frontend/src/features/metrics/components/MetricHistogramCard.tsx`, and reduced `frontend/src/features/metrics/MetricsPanel.tsx` from `1024` to `150` lines as a composition facade; validation: `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures unchanged).
- [x] 2026-02-11 13:40:15Z Completed S6 `T21` histogram math utility extraction: added `frontend/src/features/metrics/model/histogram.ts` and `frontend/src/features/metrics/model/__tests__/histogram.test.ts`, rewired `frontend/src/features/metrics/components/MetricHistogramCard.tsx`, `frontend/src/features/metrics/components/MetricRangePanel.tsx`, and `frontend/src/features/metrics/MetricsPanel.tsx` to consume pure histogram/range/formatting helpers, and preserved histogram/filter interaction semantics while moving numeric edge-case handling under dedicated unit coverage; validation: `npm run test -- src/features/metrics/model/__tests__/histogram.test.ts` (`8 passed`), `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures unchanged in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).
- [x] 2026-02-11 13:48:25Z Completed S6 `T22` histogram interaction hook extraction: added `frontend/src/features/metrics/hooks/useMetricHistogramInteraction.ts` with a dedicated drag/hover/commit state-machine hook plus exported transition helpers, rewired `frontend/src/features/metrics/components/MetricHistogramCard.tsx` to consume the hook while preserving drag-to-filter and click-to-clear behavior, and added unit coverage in `frontend/src/features/metrics/hooks/__tests__/useMetricHistogramInteraction.test.ts`; validation: `npm run test -- src/features/metrics/model/__tests__/histogram.test.ts src/features/metrics/hooks/__tests__/useMetricHistogramInteraction.test.ts` (`12 passed`), `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures unchanged in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).
- [x] 2026-02-12 01:26:58Z Completed S6 `T23` metrics computation reuse: added `frontend/src/features/metrics/model/metricValues.ts` plus unit coverage in `frontend/src/features/metrics/model/__tests__/metricValues.test.ts`, rewired `frontend/src/features/metrics/MetricsPanel.tsx` and `frontend/src/features/metrics/components/MetricRangePanel.tsx` to reuse keyed metric-value caches across selected-summary and histogram cards, and rewired `frontend/src/features/metrics/components/MetricHistogramCard.tsx` to consume precomputed value slices instead of per-card rescans; recorded profiling evidence in `docs/dev_notes/20260212_s6_t23_metrics_computation_reuse.md`; validation: `npm run test -- src/features/metrics/model/__tests__/metricValues.test.ts src/features/metrics/model/__tests__/histogram.test.ts src/features/metrics/hooks/__tests__/useMetricHistogramInteraction.test.ts` (`14 passed`), `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), and `npm run build` (success).
- [x] 2026-02-12 01:28:22Z Completed S7 `T24a` fixed-matrix execution pass (validation only, no fixes): backend matrix `pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py` (`64 passed`), import probe (`import-contract-ok`), frontend parity slice (`45 passed`), and frontend production build (success); failing domains captured for follow-up ownership in `T24b`: `[frontend-typecheck]` `npx tsc --noEmit` errors in `frontend/src/api/__tests__/client.presence.test.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/app/components/StatusBar.tsx`, and `frontend/src/features/inspector/Inspector.tsx`; `[packaging-tooling]` `python -m build` failed with `No module named build`.
- [x] 2026-02-12 01:40:37Z Completed S7 `T24b` frontend ownership slice (`[frontend-typecheck]`): fixed TypeScript failures in `frontend/src/api/__tests__/client.presence.test.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/app/components/StatusBar.tsx`, and `frontend/src/features/inspector/Inspector.tsx` via typed mock-call narrowing, `ResizeObserver` constructor guard typing, nullable `StatusBar` return typing, and inspector star-value narrowing to `StarRating`; validation: `cd frontend && npx tsc --noEmit` (pass) and `cd frontend && npm run test -- src/api/__tests__/client.presence.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/app/__tests__/presenceUi.test.ts` (`14 passed`). Remaining `T24b` scope: `[packaging-tooling]`.
- [x] 2026-02-12 01:43:06Z Completed S7 `T24b` packaging ownership slice (`[packaging-tooling]`): added `build>=1.2` to `pyproject.toml` `dev` extras so packaging tooling is part of the documented editable-dev install contract; validation: `python -m pip install -e '.[dev]'` (success, `build` present) and `python -m build` (success, produced sdist and wheel).
- [x] 2026-02-12 01:45:33Z Completed S7 `T25` frontend artifact sync: rebuilt `frontend/dist` with `npm run build`, mirrored it into `src/lenslet/frontend/` with stale-asset deletion, and verified FastAPI static serving returns the shipped shell bytes and current hashed asset path; validation: `cd frontend && npm run build` (success), `rsync -a --delete frontend/dist/ src/lenslet/frontend/` (success), and Python `TestClient` shell probe (`frontend-shell-serve-ok`).
- [x] 2026-02-12 01:50:43Z Completed S7 `T26` docs/module-map closeout: updated `README.md` and `DEVELOPMENT.md` with the implemented backend/storage/frontend module boundaries, standardized operational commands (`rsync -a --delete` frontend artifact mirroring + fixed acceptance matrix), and aligned this plan’s module-map/command references; validation: full acceptance matrix pass (`pytest` backend slice `64 passed`, import probe `import-contract-ok`, frontend parity slice `45 passed`, `npx tsc --noEmit` pass, `npm run build` success, `python -m build` success).


## Surprises & Discoveries


`src/lenslet/server.py` currently mixes app factory composition, route registration, media/export helpers, presence logic, embeddings wiring, OG handling, and cache/runtime configuration in one 2314-line module. The module has 26 route decorators and many private helpers, so coupling is operationally high.

`src/lenslet/storage/table.py` currently acts as parser, path resolver, index builder, remote probe client, media dimension reader, metadata mutator, and search service. `_build_indexes` is 219 lines and dominates initialization complexity.

`frontend/src/app/AppShell.tsx` has high orchestration density (many state/effect/callback hooks), which increases stale closure risk and diff complexity for every feature adjustment.

Subagent review surfaced a critical architectural ambiguity: the first draft mixed a module facade (`src/lenslet/server.py`) with a package path proposal (`src/lenslet/server/*`). Python import precedence makes that risky. This plan resolves it by choosing a module-only layout with sibling helper modules (for example `server_runtime.py`, `server_routes_*.py`), preserving `lenslet.server` import stability.

Subagent review also found gaps in the first validation matrix. Additional existing suites are now required for parity: `tests/test_hotpath_sprint_s2.py`, `tests/test_metadata_endpoint.py`, and `tests/test_embeddings_cache.py`.

Initial baseline run for S0 `T0` completed quickly (`63 backend tests` in `3.49s` pytest time) with the current slowest hotpath test at `0.10s`, giving a concrete pre-refactor latency reference for S1+ comparisons.

Seam mapping confirmed that all three frontend target files interleave domain logic and UI rendering in the same component body; extraction should start from pure helpers and async workflows first to avoid stale-closure regressions during hook/component splits.

While closing S0 `T2a`, the architecture risk proved broader than import precedence alone: creating a `src/lenslet/server/` package would also destabilize de facto monkeypatch surfaces (`lenslet.server.og`) used in tests. Keeping sibling helper modules preserves both import path and patch target continuity.

For S0 `T2b`, the import contract needed one additional assertion beyond raw symbol presence: retaining `lenslet.server.og.subtree_image_count` as a concrete monkeypatch target to avoid hidden breakage in existing hotpath tests.

For S1 `T3`, extracting runtime wiring into a sibling module was safest when done with callable hooks (`build_thumb_cache`, prune-loop installer, hotpath factory) to avoid circular imports while still centralizing lock/sync/presence/queue setup.

For S1 `T4a`, a coupling edge surfaced during extraction: route handlers in `server_routes_common.py` intentionally dereference helpers through `lenslet.server` to avoid circular imports and preserve module-level monkeypatch behavior, so `server.py` must continue importing select `server_sync` helpers as module attributes until later route-domain extraction tickets fully decouple those dependencies.

For S1 `T4b`, preserving `lenslet.server` as a stable monkeypatch surface required explicit alias re-exports from `server_routes_presence.py` back through `server.py` (not direct callsite rewrites) because `server_routes_common.py` still dereferences presence helpers via `lenslet.server` attributes.

For S1 `T4c`, embeddings-route extraction needed to keep canonical-path and image-validation calls routed through `lenslet.server` inside the new module (`from . import server as _server`) so existing helper touchpoints stay patchable and circular-import risk remains low.

For S1 `T4d`, index/OG/media extraction needed a compatibility nuance: preserving `NoCacheIndexStaticFiles` on `lenslet.server` is low-risk and prevents silent breakage for de facto imports, so `server.py` now intentionally re-exports that class from `server_routes_index.py` alongside `_thumb_response_async`/`_file_response` aliases.

For S1 `T5`, compare-export tests exposed an additional facade constraint: monkeypatches target `lenslet.server.MAX_EXPORT_*` and `lenslet.server._get_unibox_image_utils`, so those constants/helpers must remain implemented on `server.py` even after extracting broader browse/app-factory logic.

For S2 `T6`, the highest-impact low-risk optimization was pagination-window traversal, not traversal-order changes: keeping only the smallest `page * page_size` canonical paths during traversal reduced sort work in the primary paged path while preserving recursive ordering semantics and legacy full-recursive behavior.

For S2 `T7`, local file streaming optimization needed to preserve Starlette response semantics: passing a precomputed `stat_result` to `FileResponse` cut one filesystem stat call in the request harness while retaining `accept-ranges` behavior and remote `read_bytes` fallback logic.

For S2 `T8`, prune/replay workloads showed a high no-op rate in steady state, so the safest optimization was explicit no-op fast paths (`previous == current` delta short-circuit and `last_id >= newest_event_id` replay short-circuit) plus reduced temporary allocations inside `PresenceTracker` loops, which lowers churn without changing emitted payloads.

For S3 `T9`, preserving `TableStorage` private-method contracts was important for low-risk incremental extraction, so `table.py` keeps thin delegating methods while pure schema/path logic now lives in `table_schema.py` and `table_paths.py`.

For S3 `T10`, the largest avoidable cost in table indexing was repeated row-loop dictionary lookups with per-access fallback list allocations (`dict.get(..., [None] * row_count)`), so extraction into `table_index.py` now precomputes column views and metric selectors once and separates scan versus index-assembly phases to reduce churn while preserving row-order, dedupe, and remote-probe semantics.

For S3 `T11`, a compatibility nuance surfaced around worker-scaling tests: `tests/test_remote_worker_scaling.py` monkeypatches `lenslet.storage.table.os.cpu_count`, so the extracted worker-cap helper must accept an injected callable and `TableStorage._effective_remote_workers` must delegate with `table.py`'s `os.cpu_count` to preserve existing monkeypatch behavior.

For S3 `T12`, the lowest-risk way to complete the facade target was to extract full method bodies into `table_facade.py` while keeping all existing `TableStorage` method names/signatures in `table.py` as wrappers; this preserved monkeypatch/import touchpoints and reduced class coupling without call-site churn.

For S4 `T13a`, extracting only the data-scope layer first (folder/search/embeddings queries plus recursive hydration and derived item pools) kept the change atomic and minimized stale-closure risk; full `npx tsc --noEmit` currently reports pre-existing type issues in unrelated files, so sprint validation continues to rely on targeted vitest slices plus build output until broader type-cleanup work is scheduled.

For S4 `T13b`, AppShell hash-sync logic must be declared after hook-derived callbacks to avoid TypeScript block-scope initialization errors; keeping hash scope resolution in `AppShell.tsx` while delegating selection/viewer/compare state transitions to `useAppSelectionViewerCompare` preserved behavior and compile parity.

For S4 `T13c`, extracting presence/sync safely worked best by keeping item-cache mutation semantics in `AppShell` via an injected callback (`updateItemCaches`) while moving lease lifecycle, reconnect behavior, and activity/event subscriptions into `useAppPresenceSync`; this kept event payload handling identical and avoided cross-domain coupling regressions.

For S4 `T13d`, keeping mutation cache/refresh primitives (`refetch`, derived-count invalidation) injected from `AppShell` into `useAppActions` allowed upload/move/context-action extraction without coupling the hook to unrelated data/presence domains, while preserving read-only error messaging and drag-drop/context-menu behavior.

For S4 `T14`, preserving metric-key scan semantics required keeping the original early-exit condition (`scanLimit` only applies after at least one key is found), so selector extraction into `appShellSelectors.ts` intentionally continues scanning past 250 items when earlier items have no metrics.

For S4 `T15`, the lowest-risk churn reduction path was listener lifecycle stabilization rather than feature-level callback rewrites: keeping `hashchange`, global `keydown`, and pinch listeners mounted while reading current state from `useLatestRef` eliminated repeated attach/remove cycles during selection, scope, viewer, and grid-size updates without changing shortcut/hash/touch semantics.

For S5 `T16`, extraction landed cleanly as a pure-model seam: metadata normalization/rendering/path/copy helpers and compare-diff derivation moved into `frontend/src/features/inspector/model/metadataCompare.ts`, which let `Inspector.tsx` delegate deterministic transforms without changing async side-effect ownership; the most useful test-shape adjustment was separating pil-info inclusion assertions from truncation assertions so limit-window expectations stay deterministic.

For S5 `T17`, keeping `Inspector.tsx` as the state/effects owner while moving only section rendering into typed components was the lowest-risk split: this reduced component-body density significantly (`1313` -> `865` lines) without changing compare/export or sidecar conflict flows, and preserved `T18` headroom for async-hook extraction without cross-file state churn.

For S5 `T18`, the cleanest async split was two hooks with explicit ownership boundaries: `useInspectorSidecarWorkflow` now owns typing-state notifications and sidecar conflict/apply/keep semantics, while `useInspectorMetadataWorkflow` owns metadata fetch/reload, compare-metadata request invalidation, and comparison-export submit state. Keeping metadata reset semantics tied to `path` + `sidecar.updated_at` preserved prior UX parity (no stale loaded metadata after item/sidecar shifts) while reducing `Inspector.tsx` orchestration density.

For S5 `T19`, most avoidable Inspector churn came from duplicated metadata normalization and rendering work that occurred even when compare/metadata sections were collapsed; separating normalized-data helpers and gating heavy HTML/diff transforms to open sections preserved behavior while reducing sampled large-payload compare render latency and avoiding diff-grid remaps during unrelated export-form state updates.

For S6 `T20`, strict component extraction was the lowest-risk entry point: moving metrics attributes/range/histogram UI into `features/metrics/components/*` preserved the existing prop contract and filter wiring while collapsing `MetricsPanel.tsx` into a thin facade. Running the standard frontend parity slice, build, and repo-baseline typecheck confirmed the split introduced no new regressions.

For S6 `T21`, preserving histogram parity required keeping population-domain anchoring as the canonical binning baseline for filtered/selected overlays (`computeHistogramFromValues(filtered, bins, population)`), while moving all numeric helpers (`normalizeRange`, input parsing/formatting, clamping, tolerant comparisons) into `model/histogram.ts` so edge behavior is directly unit tested rather than implied by component rendering tests.

For S6 `T22`, preserving histogram interaction parity required keeping the existing 4px drag threshold and click-to-clear fallback (`activeRange` clears on non-drag pointer-up) while moving pointer transitions into `useMetricHistogramInteraction`; exporting pure helpers (`histogramValueFromClientX`, `didPointerDrag`, `rangeFromDrag`, `resolvePointerUpOutcome`) provided focused unit coverage for state-machine edge cases without changing UI wiring.

For S6 `T23`, the first cache attempt (generic `Object.entries` scans) regressed dense-metric synthetic timing, so the final design uses keyed bucket collection plus metric-scope narrowing (`show all` vs `show one`) to keep single-metric interactions lightweight while materially reducing repeated full-panel recomputation.

For S7 `T24a`, running the fixed matrix without edits confirmed functional parity in backend/frontend test slices and frontend production build, but surfaced two explicit closeout blockers: `[frontend-typecheck]` repo typecheck still fails in four known files, and `[packaging-tooling]` packaging sanity fails in this environment because the `build` module is unavailable (`python -m build` -> `No module named build`).

For S7 `T24b` frontend ownership, Vitest mock-call inference in `client.presence` tests surfaced as `[][]` under the current type context, so tuple-index assertions were rewritten with explicit `unknown[][]` narrowing to preserve assertions without introducing `any`. In `AppShell`, `'ResizeObserver' in window` narrowed the fallback branch to `never`; switching to a typed constructor lookup preserved the runtime fallback semantics while satisfying strict typecheck.

For S7 `T24b` packaging ownership, the failure mode was environment reproducibility rather than build backend behavior: `python -m build` worked immediately once `build` was installed, so the durable fix was to encode `build>=1.2` into `pyproject.toml` `dev` extras to match the documented dev-install path instead of relying on ad-hoc local package installs.

For S7 `T25`, direct `cp -r dist/*` sync risks stale hashed assets in `src/lenslet/frontend/assets`; using `rsync --delete` keeps the shipped static bundle deterministic and aligned to `index.html`. A `TestClient` probe against `/` and `/index.html` verified Python-served shell bytes match the shipped artifact, and the referenced hashed JS asset is served under the static mount.

For S7 `T26`, the remaining operational drift risk was documentation divergence across `README.md`, `DEVELOPMENT.md`, and this plan. Copying the same acceptance matrix and deterministic frontend-sync command into both docs made closeout/release steps mechanically consistent and removed legacy `cp -r` guidance that could leave stale hashed assets in packaged frontend output.


## Decision Log


1. 2026-02-11, user plus assistant. Internal refactors may be large and bold if behavior remains stable and performance materially improves in targeted hot paths.
2. 2026-02-11, assistant. `src/lenslet/server.py` remains a module (not converted into a package). Internal decomposition uses sibling modules to avoid import collisions and maintain compatibility.
3. 2026-02-11, assistant. Public and de facto-private compatibility contracts are explicit and tested, including `create_app*`, `HotpathTelemetry`, `_file_response`, `_thumb_response_async`, `lenslet.server.og`, and table loader symbols.
4. 2026-02-11, assistant. Backend API-contract freeze gate is required before frontend refactor sprints begin.
5. 2026-02-11, assistant. Oversized tickets are split into atomic domain tickets (routes by domain, AppShell domains, validation execution vs regression-fix execution).
6. 2026-02-11, assistant. Line-count reduction is secondary. Primary success criteria are readability, separable responsibilities, and measurable speed improvements with stable behavior.
7. 2026-02-11, assistant. Frontend artifact sync to `src/lenslet/frontend/` is mandatory in closeout when UI files are changed.
8. 2026-02-11, assistant. S0 `T0` performance baseline comparisons use the recorded hotpath `pytest --durations=10` snapshot in `docs/dev_notes/20260211_s0_t0_baseline_snapshot.md` as the before-reference unless a ticket defines a narrower benchmark harness.
9. 2026-02-11, assistant. S0 `T1` will use dual seam artifacts (a detailed `docs/dev_notes` map and lightweight in-file `S0/T1 seam anchors`) so later extraction tickets can move quickly without re-discovering boundaries.
10. 2026-02-11, assistant. S0 `T2a` is considered complete only with an explicit architecture artifact under `docs/dev_notes/` and an explicit prohibition on creating a `src/lenslet/server/` package during S1 extraction.
11. 2026-02-11, assistant. S0 `T2b` compatibility locking is implemented as a dedicated pytest module (`tests/test_import_contract.py`) so it runs naturally in the existing test workflow and enforces both symbol presence and `lenslet.server.og.subtree_image_count` monkeypatch continuity.
12. 2026-02-11, assistant. S1 `T3` runtime extraction uses `server_runtime.build_app_runtime` plus a thin `_initialize_runtime` facade wrapper in `server.py` so app factories share one runtime path without changing `lenslet.server` exports or monkeypatch touchpoints.
13. 2026-02-11, assistant. S1 `T4a` route extraction keeps helper lookups routed through `lenslet.server` module attributes in `server_routes_common.py`; this avoids circular imports, preserves existing patch/import touchpoints, and requires retaining select `server_sync` helper imports in `server.py` as intentional facade exports.
14. 2026-02-11, assistant. S1 `T4b` presence extraction moves lifecycle/diagnostic/route helpers into `server_routes_presence.py` but keeps `server.py` alias exports for `_register_presence_routes`, `_touch_presence_edit`, `_presence_runtime_payload`, and `_install_presence_prune_loop` so existing route modules and runtime wiring continue to target `lenslet.server` without behavioral drift.
15. 2026-02-11, assistant. S1 `T4c` embeds `/embeddings` and `/views` route handlers in sibling modules while keeping server-facade aliases (`_register_embedding_routes`, `_register_views_routes`) and routing embeddings helper calls through `lenslet.server` attributes for compatibility/circular-safety.
16. 2026-02-11, assistant. S1 `T4d` extracts media/index/OG helpers into `server_media.py`, `server_routes_index.py`, and `server_routes_og.py` while retaining facade alias exports in `server.py` (`_thumb_response_async`, `_file_response`, `_register_index_routes`, `_register_og_routes`, and `NoCacheIndexStaticFiles`) to keep compatibility and monkeypatch continuity.
17. 2026-02-11, assistant. S1 `T5` finalizes the facade split by moving browse/runtime-factory logic into `server_browse.py` and `server_factory.py`, while intentionally keeping comparison-export constants/helpers in `server.py` so existing monkeypatch tests on `lenslet.server` remain behaviorally identical.
18. 2026-02-11, assistant. S2 `T6` implements recursive-page windowing in `server_browse`: non-legacy recursive requests parse pagination first, collect only the smallest `page * page_size` canonical paths while still computing full `totalItems`, and keep legacy recursive mode on full traversal output to preserve existing response semantics.
19. 2026-02-11, assistant. S2 `T7` reduces local `/file` path blocking work by threading a precomputed `stat_result` through `_resolve_local_file_path` into `FileResponse`, preserving local streaming/headers and remote fallback semantics while removing one filesystem stat call in the measured request harness.
20. 2026-02-11, assistant. S2 `T8` uses behavior-preserving fast paths in presence/sync internals (no-op delta short-circuit, no-new-event replay short-circuit, lower-allocation prune/count loops) rather than changing lifecycle state transitions, event shapes, or diagnostics contracts.
21. 2026-02-11, assistant. S3 `T9` extracts schema/path/coercion logic into `table_schema.py` and `table_paths.py` but keeps delegate methods on `TableStorage` to preserve private-call and monkeypatch compatibility while reducing class-body complexity.
22. 2026-02-11, assistant. S3 `T10` defines table indexing as an explicit three-phase pipeline (`build_index_columns`, `scan_rows`, `assemble_indexes`) in `table_index.py`; scan-phase optimizations must stay semantics-preserving (same skip/warn behavior, same dedupe ordering, same remote-dimension task scheduling), and `TableStorage` retains delegating private methods for compatibility.
23. 2026-02-11, assistant. S3 `T11` extracts remote probing and dimension reader/parsers into `table_probe.py` and `table_media.py`, while keeping `TableStorage` private probe/media methods as compatibility wrappers; worker-scaling delegation explicitly injects `table.py`'s `os.cpu_count` so existing monkeypatch-based tests remain valid.
24. 2026-02-11, assistant. S3 `T12` keeps `TableStorage` as the compatibility facade by delegating table-shape parsing, read/thumbnail/dimensions/metadata/search flows, and S3 presign-client helpers into `table_facade.py`, while preserving constructor and method signatures on `table.py`.
25. 2026-02-11, assistant. S0 `T2c` API-freeze checkpoint is signed off post-S3; S4+ frontend refactors must treat backend route and storage contracts as frozen unless explicitly tagged as regression fixes in S7.
26. 2026-02-11, assistant. S4 `T13a` introduces `useAppDataScope` as the sole owner of AppShell data-scope concerns (recursive folder hydration/query cleanup, search + embeddings loading, and pool/similarity/item derivations), while `AppShell.tsx` keeps selection, presence/sync, and mutation domains untouched for low-risk incremental decomposition.
27. 2026-02-11, assistant. S4 `T13b` introduces `useAppSelectionViewerCompare` as the sole owner of AppShell selection/viewer/compare state, history, and navigation semantics, while `AppShell.tsx` keeps hash-scope resolution and non-selection domains unchanged for low-risk incremental decomposition.
28. 2026-02-11, assistant. S4 `T13c` introduces `useAppPresenceSync` as the sole owner of AppShell presence-lease lifecycle, event subscriptions, connection-state updates, and activity derivations (off-view summary/highlights/recent touches + edit recency labels), while `AppShell.tsx` retains injected cache-mutation helpers and indicator composition to preserve behavior parity.
29. 2026-02-11, assistant. S4 `T13d` introduces `useAppActions` as the sole owner of AppShell upload/move/context-action state and lifecycle (including drag-drop uploads, destination-folder discovery, and context-menu dismissal), while `AppShell.tsx` supplies only scope/callback dependencies (`current`, selected paths, `refetch`, and derived-count invalidation) to preserve mutation UX/error parity with lower orchestration density.
30. 2026-02-11, assistant. S4 `T14` centralizes AppShell pure derived selectors in `frontend/src/app/model/appShellSelectors.ts` (star counts, metric keys, metric-scrollbar eligibility, similarity/display labels) with dedicated unit coverage, keeping callback-producing logic in `AppShell.tsx` to preserve interaction contracts while reducing component orchestration density.
31. 2026-02-11, assistant. S4 `T15` stabilizes AppShell high-frequency listeners with `useLatestRef` (`hashchange`, `keydown`, pinch touch handlers), preferring mount-once listener ownership plus latest-state refs over dependency-driven re-registration to reduce effect churn while keeping interaction contracts unchanged.
32. 2026-02-11, assistant. S5 `T16` establishes `frontend/src/features/inspector/model/metadataCompare.ts` as the canonical pure-transform layer for Inspector metadata (normalization, display masking/rendering, path/value helpers, and compare-diff derivation), keeping `Inspector.tsx` responsible for state/effects only and preserving existing compare/export interaction contracts.
33. 2026-02-11, assistant. S5 `T17` keeps `Inspector.tsx` as the orchestration owner while moving section rendering into typed `frontend/src/features/inspector/sections/*` components (`InspectorSection`, `OverviewSection`, `CompareMetadataSection`, `BasicsSection`, `MetadataSection`, `NotesSection`), so UI decomposition lands with low behavior risk and positions `T18` to extract async workflows cleanly.
34. 2026-02-11, assistant. S5 `T18` splits Inspector async responsibilities across two dedicated hooks (`useInspectorSidecarWorkflow` and `useInspectorMetadataWorkflow`) so typing/conflict and metadata/compare/export lifecycles are isolated from render composition, while preserving prior reset triggers (`path`, `sidecar.updated_at`, compare scope transitions) for behavior parity.
35. 2026-02-11, assistant. S5 `T19` standardizes normalized metadata as a reusable Inspector render primitive and gates heavy metadata/compare transforms to open-section paths, while memoizing compare-diff rendering so export-form edits do not remap large diff tables unless diff inputs actually change.
36. 2026-02-11, assistant. S6 `T20` establishes typed metrics UI boundaries in `frontend/src/features/metrics/components/*` and treats `MetricsPanel.tsx` as a pure composition facade, preserving existing filter/range contracts while deferring math and interaction-state extraction to `T21`/`T22`.
37. 2026-02-11, assistant. S6 `T21` defines `frontend/src/features/metrics/model/histogram.ts` as the canonical pure math/formatting layer for metrics histograms (value collection, binning with optional base-domain anchoring, range normalization/clamping, tolerant comparisons, and numeric input formatting/parsing), and metrics UI components now consume these helpers instead of owning duplicated numeric logic.
38. 2026-02-11, assistant. S6 `T22` centralizes histogram pointer interaction ownership in `frontend/src/features/metrics/hooks/useMetricHistogramInteraction.ts`, preserving prior drag/hover/commit/clear semantics (including the 4px drag threshold and click-clear fallback) while exposing deterministic transition helpers for unit testing.
39. 2026-02-12, assistant. S6 `T23` reuses keyed metric-value caches across `MetricsPanel` selection summaries and `MetricRangePanel` histogram cards, with `MetricHistogramCard` now consuming precomputed population/filtered/selected slices and range panel collection scoped to visible metrics (`show all` vs `show one`) to reduce repeated work while preserving filter semantics.
40. 2026-02-12, assistant. S7 `T24a` records failing-domain ownership tags without code fixes: `[frontend-typecheck]` for `npx tsc --noEmit` failures and `[packaging-tooling]` for missing `python -m build` dependency in the current environment; `T24b` must resolve or explicitly baseline these failures before acceptance closeout.
41. 2026-02-12, assistant. S7 `T24b` resolves the `[frontend-typecheck]` failure domain with behavior-preserving type-level changes only (test mock-call narrowing, optional `ResizeObserver` constructor lookup, nullable `StatusBar` return type, and inspector star narrowing to `StarRating`), while keeping `[packaging-tooling]` as remaining closeout scope for the same ticket.
42. 2026-02-12, assistant. S7 `T24b` resolves the `[packaging-tooling]` failure domain by promoting `build>=1.2` into `pyproject.toml` `dev` extras and validating `python -m build` in the same environment, so documented `pip install -e '.[dev]'` setup now satisfies packaging sanity without ad-hoc dependency installation.
43. 2026-02-12, assistant. S7 `T25` standardizes frontend artifact shipping as a deterministic mirror (`rsync --delete` from `frontend/dist/` to `src/lenslet/frontend/`) and validates with FastAPI `TestClient` that `/` and `/index.html` serve the shipped HTML and referenced hashed assets.
44. 2026-02-12, assistant. S7 `T26` treats `README.md` + `DEVELOPMENT.md` as the canonical operator surface for post-refactor boundaries and release checks, and keeps both docs aligned to the fixed acceptance matrix plus deterministic frontend artifact mirroring (`rsync -a --delete`) to prevent stale-asset drift.


## Outcomes & Retrospective


Execution is complete across S0-S7. The plan now serves as both historical implementation log and operational handover: module boundaries are documented, compatibility/performance decisions are recorded, and the fixed acceptance matrix has passed with packaging and shipped-frontend verification in the final sprint.


## Context and Orientation


Target backend files are `src/lenslet/server.py` and `src/lenslet/storage/table.py`. Target frontend files are `frontend/src/app/AppShell.tsx`, `frontend/src/features/inspector/Inspector.tsx`, and `frontend/src/features/metrics/MetricsPanel.tsx`.

Current backend constraints include route behavior, presence lifecycle semantics, and hotpath counters/timers. Existing tests already lock meaningful behavior in `tests/test_presence_lifecycle.py`, `tests/test_hotpath_sprint_s2.py`, `tests/test_hotpath_sprint_s3.py`, `tests/test_hotpath_sprint_s4.py`, `tests/test_refresh.py`, `tests/test_folder_pagination.py`, `tests/test_collaboration_sync.py`, `tests/test_compare_export_endpoint.py`, `tests/test_metadata_endpoint.py`, `tests/test_embeddings_search.py`, `tests/test_embeddings_cache.py`, `tests/test_table_security.py`, `tests/test_remote_worker_scaling.py`, and `tests/test_parquet_ingestion.py`.

Current frontend constraints include app utility and behavior tests in `frontend/src/app/__tests__/appShellHelpers.test.ts`, `frontend/src/app/__tests__/presenceActivity.test.ts`, `frontend/src/app/__tests__/presenceUi.test.ts`, `frontend/src/features/inspector/__tests__/exportComparison.test.tsx`, `frontend/src/features/browse/model/__tests__/filters.test.ts`, `frontend/src/features/browse/model/__tests__/pagedFolder.test.ts`, `frontend/src/features/browse/model/__tests__/prefetchPolicy.test.ts`, `frontend/src/api/__tests__/client.events.test.ts`, and `frontend/src/api/__tests__/client.presence.test.ts`.

Compatibility touchpoints outside direct imports also matter. Some tests monkeypatch `lenslet.server.og.subtree_image_count`, so `lenslet.server` must continue exposing an `og` module attribute.

In this plan, "behavioral parity" means unchanged external semantics for API responses and UI interactions. "Performance optimization" means reducing latency, CPU, memory churn, or redundant work in hot paths without changing result correctness.


## Plan of Work


The sequence starts with explicit baselines and architectural gates, then extracts backend modules first because frontend flows depend on stable runtime semantics. Once backend contracts are frozen, frontend decomposition proceeds by domain state ownership and pure-model extraction, with targeted optimization inside each domain. The final sprint runs an expanded validation matrix, performs packaging checks, and verifies bundled frontend artifact synchronization.

Every sprint must produce a demoable and testable increment. Every ticket is atomic and committable, with validation tied to that ticket.

- While implementing each sprint, update the plan document continuously (Progress, Decision Log, Surprises & Discoveries, and relevant sections). After each sprint is complete, add clear handover notes.
- For minor script-level uncertainties (for example, exact file placement), proceed according to the approved plan to maintain momentum. After the sprint, ask for clarifications and then apply follow-up adjustments.

### Sprint Plan


1. S0: Baseline, architecture gate, and compatibility matrix.
   Goal: lock current behavior, establish performance baseline snapshots, and finalize non-ambiguous server/layout decisions before code movement.
   Demo outcome: baseline tests pass; architecture decision note is committed; import-contract check script passes.
   Linked tasks: T0, T1, T2a, T2b, T2c.
2. S1: Backend modular extraction of `server.py` using module-only helper layout.
   Goal: split runtime wiring and route registration into domain modules while preserving `lenslet.server` import surface.
   Demo outcome: app boots and serves in directory, dataset, and table modes with unchanged endpoint behavior.
   Linked tasks: T3, T4a, T4b, T4c, T4d, T5.
3. S2: Backend hotpath optimization and parity lock.
   Goal: optimize recursive folders, thumbnail/file fast paths, and unnecessary work in route handlers while keeping outputs stable.
   Demo outcome: benchmark snapshots show same correctness with improved hotpath timings or lower work for representative cases.
   Linked tasks: T6, T7, T8.
4. S3: TableStorage decomposition and ingestion/runtime optimization.
   Goal: split schema/path/index/probe/media responsibilities and optimize expensive loops/conversions where safe.
   Demo outcome: table-backed browsing and search semantics are unchanged; initialization and hotpath metrics improve on sampled datasets.
   Linked tasks: T9, T10, T11, T12.
5. S4: AppShell decomposition and interaction-path optimization.
   Goal: separate state domains into hooks/selectors/components and reduce avoidable rerenders/effect churn.
   Demo outcome: browse/viewer/compare/selection/presence/upload workflows remain stable and smoother under heavy item sets.
   Linked tasks: T13a, T13b, T13c, T13d, T14, T15.
6. S5: Inspector decomposition and metadata/compare-path optimization.
   Goal: isolate section logic, pure metadata/compare utilities, and async workflows; optimize heavy compare rendering paths.
   Demo outcome: inspector parity remains intact, and compare metadata interactions feel faster on large metadata payloads.
   Linked tasks: T16, T17, T18, T19.
7. S6: Metrics panel decomposition and histogram-path optimization.
   Goal: isolate metrics UI from math and interaction logic; cache expensive calculations to reduce repeated work.
   Demo outcome: metric range filtering behavior is unchanged and histogram interactions remain responsive on large metric sets.
   Linked tasks: T20, T21, T22, T23.
8. S7: Consolidation, packaging, and acceptance closeout.
   Goal: run full fixed validation matrix, split regression fixes by domain, sync frontend artifacts, and publish module-map docs.
   Demo outcome: all validation passes; packaged app serves latest frontend bundle; module ownership is documented.
   Linked tasks: T24a, T24b, T25, T26.


## Concrete Steps


All commands below run from the repository root unless noted.

    Working directory: /home/ubuntu/dev/lenslet

    rg -n "def create_app|def create_app_from_|def _register_|class HotpathTelemetry" src/lenslet/server.py
    rg -n "^    def " src/lenslet/storage/table.py
    rg -n "export default function AppShell|useState\(|useEffect\(|useMemo\(|useCallback\(" frontend/src/app/AppShell.tsx
    rg -n "export default function Inspector|function InspectorSection|handleComparisonExport" frontend/src/features/inspector/Inspector.tsx
    rg -n "export default function MetricsPanel|function MetricHistogramCard|computeHistogramFromValues" frontend/src/features/metrics/MetricsPanel.tsx

Baseline parity and compatibility run:

    Working directory: /home/ubuntu/dev/lenslet

    pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py

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

Frontend parity run:

    Working directory: /home/ubuntu/dev/lenslet/frontend

    npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts

    npx tsc --noEmit

Packaging sanity and shipped-asset sync:

    Working directory: /home/ubuntu/dev/lenslet/frontend

    npm run build
    rsync -a --delete dist/ ../src/lenslet/frontend/

    Working directory: /home/ubuntu/dev/lenslet

    python -m build

### Task/Ticket Details


1. T0: Capture behavioral and performance baseline snapshots.
   Goal: record baseline correctness and hotpath numbers before major refactor begins.
   Affected files and areas: test outputs and sprint notes.
   Validation: baseline command set passes and baseline timing snapshot for representative flows is saved.
   Status: completed at `2026-02-11T04:12:31Z`; artifact `docs/dev_notes/20260211_s0_t0_baseline_snapshot.md`.

2. T1: Produce per-file extraction seam map.
   Goal: define responsibility boundaries and extraction order by domain.
   Affected files and areas: `docs/dev_notes/` note plus anchors in target files.
   Validation: each target file has a committed seam map with ticket references.
   Status: completed at `2026-02-11T04:21:23Z`; artifact `docs/dev_notes/20260211_s0_t1_seam_map.md` plus in-file seam comments in all five target long files.

3. T2a: Resolve server module structure decision gate.
   Goal: lock module-only extraction shape (`server.py` + sibling helper modules), avoiding package conversion ambiguity.
   Affected files and areas: this plan and architecture note.
   Validation: documented decision approved before S1 code edits begin.
   Status: completed at `2026-02-11T04:22:50Z`; artifact `docs/dev_notes/20260211_s0_t2a_server_module_structure_gate.md`; approval recorded in Decision Log item `10`.

4. T2b: Add explicit import-compatibility contract checks.
   Goal: codify compatibility for public and currently relied-on private symbols.
   Affected files and areas: small compatibility test/script under `tests/` or CI helper script.
   Validation: check script passes pre- and post-refactor.
   Status: completed at `2026-02-11T04:25:18Z`; artifact `tests/test_import_contract.py`; validation `pytest -q tests/test_import_contract.py` (`2 passed`) and import probe (`import-contract-ok`).

5. T2c: Add API freeze checkpoint before frontend refactors.
   Goal: guarantee backend route contracts are stable before S4 starts.
   Affected files and areas: sprint handoff note and decision log updates.
   Validation: checkpoint recorded and signed off after S3.
   Status: completed at `2026-02-11T05:39:21Z`; sign-off recorded in `S3 handover` notes plus Decision Log item `25` using completed S1-S3 validations and import-contract continuity.

6. T3: Extract app runtime wiring into sibling runtime module.
   Goal: move shared setup for workspace, sync state, presence, queue, and telemetry to a dedicated runtime constructor.
   Affected files and areas: `src/lenslet/server.py`, new `src/lenslet/server_runtime.py`.
   Validation: `/health` payload semantics remain unchanged in existing tests.
   Status: completed at `2026-02-11T04:27:13Z`; artifacts `src/lenslet/server_runtime.py` and runtime-facade updates in `src/lenslet/server.py`; validation `pytest -q tests/test_hotpath_sprint_s3.py tests/test_presence_lifecycle.py tests/test_refresh.py tests/test_import_contract.py` (`21 passed`), `pytest -q tests/test_hotpath_sprint_s4.py tests/test_collaboration_sync.py` (`14 passed`), plus import probe (`import-contract-ok`).

7. T4a: Extract common route registration domain.
   Goal: isolate folders/item/thumb/file/search route registration.
   Affected files and areas: `src/lenslet/server.py`, new `src/lenslet/server_routes_common.py`.
   Validation: route-focused tests pass with no response-shape changes.
   Status: completed at `2026-02-11T04:38:56Z`; artifacts `src/lenslet/server_routes_common.py` and extracted-route wiring updates in `src/lenslet/server.py`; validation `pytest -q tests/test_folder_pagination.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_collaboration_sync.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_import_contract.py` (`42 passed`) plus import probe (`import-contract-ok`).

8. T4b: Extract presence route registration domain.
   Goal: isolate presence endpoints, diagnostics, and lifecycle helpers.
   Affected files and areas: `src/lenslet/server.py`, new `src/lenslet/server_routes_presence.py`.
   Validation: `tests/test_presence_lifecycle.py` and related sync tests pass unchanged.
   Status: completed at `2026-02-11T04:43:53Z`; artifacts `src/lenslet/server_routes_presence.py` and facade-alias updates in `src/lenslet/server.py`; validation `pytest -q tests/test_presence_lifecycle.py tests/test_collaboration_sync.py tests/test_hotpath_sprint_s4.py tests/test_import_contract.py` (`24 passed`) plus import probe (`import-contract-ok`).

9. T4c: Extract embeddings and views route registration domains.
   Goal: isolate embeddings and views routes from common route bundle.
   Affected files and areas: `src/lenslet/server.py`, new `src/lenslet/server_routes_embeddings.py`, new `src/lenslet/server_routes_views.py`.
   Validation: embeddings and views tests pass; no route regressions.
   Status: completed at `2026-02-11T04:45:14Z`; artifacts `src/lenslet/server_routes_embeddings.py`, `src/lenslet/server_routes_views.py`, and alias-wiring updates in `src/lenslet/server.py`; validation `pytest -q tests/test_embeddings_search.py tests/test_parquet_ingestion.py tests/test_embeddings_cache.py tests/test_import_contract.py` (`9 passed`) plus import probe (`import-contract-ok`).

10. T4d: Extract index/OG/media route helpers and wiring.
    Goal: isolate index/meta/OG route responsibilities and media helper dependencies.
    Affected files and areas: `src/lenslet/server.py`, new `src/lenslet/server_routes_index.py`, new `src/lenslet/server_routes_og.py`, new `src/lenslet/server_media.py`.
    Validation: `tests/test_hotpath_sprint_s2.py`, `tests/test_hotpath_sprint_s3.py`, `tests/test_hotpath_sprint_s4.py`, and `tests/test_compare_export_endpoint.py` pass.
    Status: completed at `2026-02-11T04:52:09Z`; artifacts `src/lenslet/server_media.py`, `src/lenslet/server_routes_index.py`, `src/lenslet/server_routes_og.py`, and facade-alias updates in `src/lenslet/server.py`; validation `pytest -q tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_compare_export_endpoint.py tests/test_import_contract.py` (`31 passed`) plus import probe (`import-contract-ok`).

11. T5: Keep `server.py` as stable facade module.
    Goal: reduce `server.py` to composition and stable exports while preserving import/monkeypatch touchpoints.
    Affected files and areas: `src/lenslet/server.py`, new `src/lenslet/server_browse.py`, new `src/lenslet/server_factory.py`.
    Validation: compatibility script and import-heavy tests pass.
    Status: completed at `2026-02-11T04:54:19Z`; artifacts `src/lenslet/server_browse.py`, `src/lenslet/server_factory.py`, and facade rewrite in `src/lenslet/server.py`; validation `pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py tests/test_import_contract.py` (`65 passed`) plus import probe (`import-contract-ok`).

### Sprint Handover Notes

S1 handover (`2026-02-11T04:54:19Z`):
1. Completed: `T3`, `T4a`, `T4b`, `T4c`, `T4d`, and `T5`; `server.py` is now a stable 335-line compatibility facade and domain logic is split across sibling modules (`server_runtime.py`, `server_routes_*.py`, `server_media.py`, `server_browse.py`, `server_factory.py`).
2. Validations run and outcomes: `pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py tests/test_import_contract.py` -> `65 passed`; import probe -> `import-contract-ok`.
3. Known risks/follow-ups: route modules still intentionally dereference some helpers through `lenslet.server` for monkeypatch/circular-safety; S2 optimizations should preserve these touchpoints unless paired with explicit compatibility assertions.
4. First step for S2: execute `T6` by profiling recursive folder traversal in the extracted browse path (`server_browse._collect_recursive_cached_items` and pagination helpers) and recording before/after hotpath timing deltas.

12. T6: Optimize recursive folder and traversal hotpaths.
    Goal: remove redundant work in recursive item collection/paging paths without changing ordering and pagination semantics.
    Affected files and areas: extracted folder route/domain modules.
    Validation: `tests/test_folder_pagination.py` and hotpath tests pass; timing snapshot shows lower traversal overhead.
    Status: completed at `2026-02-11T05:02:54Z`; artifacts `src/lenslet/server_browse.py` and `docs/dev_notes/20260211_s2_t6_recursive_traversal_windowing.md`; validation `pytest -q tests/test_folder_pagination.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py` (`30 passed`), `pytest -q --durations=10 tests/test_folder_pagination.py tests/test_hotpath_sprint_s4.py` (`15 passed`, recursive hot case `0.14s` -> `0.13s`), `pytest -q tests/test_import_contract.py` (`2 passed`), and import probe (`import-contract-ok`).

13. T7: Optimize thumb/file response work.
    Goal: reduce avoidable byte reads and blocking work on file/thumb paths while preserving headers and behavior.
    Affected files and areas: `src/lenslet/server_media.py` and related route glue.
    Validation: hotpath tests and metadata tests pass; endpoint semantics unchanged.
    Status: completed at `2026-02-11T05:10:38Z`; artifacts `src/lenslet/server_media.py`, `tests/test_hotpath_sprint_s2.py`, and `docs/dev_notes/20260211_s2_t7_media_stat_reuse.md`; validation `pytest -q tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s4.py tests/test_metadata_endpoint.py tests/test_import_contract.py` (`18 passed`), `pytest -q --durations=10 tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s4.py` (`14 passed`), and import probe (`import-contract-ok`).

14. T8: Optimize presence and sync-path incidental overhead.
    Goal: reduce unnecessary churn in presence publish/prune paths while preserving lifecycle semantics.
    Affected files and areas: presence route/runtime modules.
    Validation: `tests/test_presence_lifecycle.py` and `tests/test_collaboration_sync.py` pass with no behavior diffs.
    Status: completed at `2026-02-11T05:15:47Z`; artifacts `src/lenslet/server_routes_presence.py`, `src/lenslet/server_sync.py`, `tests/test_presence_lifecycle.py`, and `docs/dev_notes/20260211_s2_t8_presence_sync_fastpaths.md`; validation `pytest -q tests/test_presence_lifecycle.py tests/test_collaboration_sync.py tests/test_hotpath_sprint_s4.py tests/test_import_contract.py` (`25 passed`), `pytest -q --durations=10 tests/test_presence_lifecycle.py tests/test_collaboration_sync.py` (`13 passed`), and import probe (`import-contract-ok`).

S2 handover (`2026-02-11T05:15:47Z`):
1. Completed: `T6`, `T7`, and `T8`; backend hotpaths now include recursive-window traversal, local-file stat reuse on `/file`, and presence/sync no-op fast paths with reduced internal allocation churn.
2. Validations run and outcomes: `pytest -q tests/test_folder_pagination.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py` -> `30 passed`; `pytest -q tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s4.py tests/test_metadata_endpoint.py tests/test_import_contract.py` -> `18 passed`; `pytest -q tests/test_presence_lifecycle.py tests/test_collaboration_sync.py tests/test_hotpath_sprint_s4.py tests/test_import_contract.py` -> `25 passed`; duration checks `pytest -q --durations=10 tests/test_folder_pagination.py tests/test_hotpath_sprint_s4.py` (`15 passed`) and `pytest -q --durations=10 tests/test_presence_lifecycle.py tests/test_collaboration_sync.py` (`13 passed`); import probes remained `import-contract-ok`.
3. Known risks/follow-ups: `T2c` API-freeze checkpoint remains intentionally pending until post-`S3`; `TableStorage` internals are still monolithic and should be split with strict constructor/method compatibility guards during `S3`.
4. First step for S3: execute `T9` by extracting schema/path-source derivation logic from `src/lenslet/storage/table.py` into dedicated collaborators (`table_schema.py`, `table_paths.py`) with parity checks in parquet/table-security suites.

15. T9: Extract table schema/path resolution modules.
    Goal: move column detection/coercion and path/source derivation out of monolithic class body.
    Affected files and areas: `src/lenslet/storage/table.py`, new `src/lenslet/storage/table_schema.py`, new `src/lenslet/storage/table_paths.py`.
    Validation: `tests/test_parquet_ingestion.py` and `tests/test_table_security.py` pass unchanged.
    Status: completed at `2026-02-11T05:20:14Z`; artifacts `src/lenslet/storage/table_schema.py`, `src/lenslet/storage/table_paths.py`, and delegating updates in `src/lenslet/storage/table.py`; validation `pytest -q tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_import_contract.py` (`6 passed`), `pytest -q tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py` (`6 passed`), compile check (`compile-ok`), and import probe (`import-contract-ok`).

16. T10: Extract and optimize table index build pipeline.
    Goal: split row scan and index assembly into explicit phases, then remove obvious repeated work in loops.
    Affected files and areas: `src/lenslet/storage/table.py`, new `src/lenslet/storage/table_index.py`.
    Validation: browse/search parity tests pass; index build baseline metrics improve on sampled datasets.
    Status: completed at `2026-02-11T05:25:21Z`; artifacts `src/lenslet/storage/table_index.py`, delegating updates in `src/lenslet/storage/table.py`, `tests/test_table_index_pipeline.py`, and `docs/dev_notes/20260211_s3_t10_table_index_pipeline.md`; line budget moved from `1100` to `855` lines for `src/lenslet/storage/table.py`; validation `pytest -q tests/test_table_index_pipeline.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py tests/test_import_contract.py` (`14 passed`), `pytest -q --durations=10 tests/test_table_index_pipeline.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_remote_worker_scaling.py` (`7 passed`), compile check (`compile-ok`), import probe (`import-contract-ok`), and table-build benchmark (`median 0.0259s` -> `0.0192s`; `mean 0.0267s` -> `0.0196s` on 1200-row synthetic dataset).

17. T11: Extract remote probing and fast-dimension readers.
    Goal: isolate remote header fetch/parsing and format-specific dimension readers for focused optimization.
    Affected files and areas: `src/lenslet/storage/table.py`, new `src/lenslet/storage/table_probe.py`, new `src/lenslet/storage/table_media.py`.
    Validation: `tests/test_remote_worker_scaling.py` and hotpath tests pass.
    Status: completed at `2026-02-11T05:37:46Z`; artifacts `src/lenslet/storage/table_probe.py`, `src/lenslet/storage/table_media.py`, delegate-wiring updates in `src/lenslet/storage/table.py`, and note `docs/dev_notes/20260211_s3_t11_probe_media_extraction.md`; line budget moved from `855` to `710` lines for `src/lenslet/storage/table.py`; validation `pytest -q tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_import_contract.py` (`12 passed`), `pytest -q --durations=10 tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py` (`6 passed`), `pytest -q tests/test_table_index_pipeline.py` (`2 passed`), compile check (`compile-ok`), and import probe (`import-contract-ok`).

18. T12: Keep `TableStorage` as facade while enabling delegated collaborators.
    Goal: preserve constructor and method contracts while reducing internal complexity and coupling.
    Affected files and areas: `src/lenslet/storage/table.py`, new `src/lenslet/storage/table_facade.py`.
    Validation: embedding and search tests that instantiate `TableStorage` pass without call-site changes.
    Status: completed at `2026-02-11T05:39:21Z`; artifacts `src/lenslet/storage/table_facade.py`, delegate-wiring updates in `src/lenslet/storage/table.py`, and note `docs/dev_notes/20260211_s3_t12_table_facade_delegate.md`; line budget moved from `710` to `532` lines for `src/lenslet/storage/table.py`; validation `pytest -q tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py tests/test_table_index_pipeline.py tests/test_import_contract.py` (`18 passed`), `pytest -q tests/test_hotpath_sprint_s4.py` (`10 passed`), `pytest -q --durations=10 tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py` (`6 passed`), compile check (`compile-ok`), and import probe (`import-contract-ok`).

S3 handover (`2026-02-11T05:39:21Z`):
1. Completed: `T9`, `T10`, `T11`, and `T12`; `TableStorage` now delegates schema/path/index/probe/media plus facade-operation method bodies through sibling collaborators (`table_schema.py`, `table_paths.py`, `table_index.py`, `table_probe.py`, `table_media.py`, `table_facade.py`) while preserving constructor/private/public method contracts.
2. Validations run and outcomes: `pytest -q tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_parquet_ingestion.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py tests/test_table_index_pipeline.py tests/test_import_contract.py` -> `18 passed`; `pytest -q tests/test_hotpath_sprint_s4.py` -> `10 passed`; `pytest -q --durations=10 tests/test_remote_worker_scaling.py tests/test_hotpath_sprint_s3.py` -> `6 passed` with slowest case `0.10s`; compile check `compile-ok`; import probe `import-contract-ok`.
3. Known risks/follow-ups: `src/lenslet/storage/table.py` remains slightly above the final guidance target (`532` vs `<=500` lines), so future reductions should come from frontend sprint churn or S7 docs/cleanup tickets only if they preserve compatibility wrappers and private touchpoints.
4. First step for S4: execute `T13a` by extracting AppShell data-scope loading/derivation logic into `frontend/src/app/hooks/useAppDataScope.ts` while preserving query-key semantics and existing app helper/presence tests.

19. T13a: Extract AppShell data-scope domain hook.
    Goal: isolate folder/search/similarity data loading and derived lists.
    Affected files and areas: `frontend/src/app/AppShell.tsx`, new hook under `frontend/src/app/hooks/`.
    Validation: browse/search/similarity behavior remains unchanged in tests and manual smoke.
    Status: completed at `2026-02-11T05:49:36Z`; artifacts `frontend/src/app/hooks/useAppDataScope.ts` and data-scope rewiring in `frontend/src/app/AppShell.tsx`; validation `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`39 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).

20. T13b: Extract AppShell selection/viewer/compare domain hook.
    Goal: isolate selection, viewer state, compare state, and navigation semantics.
    Affected files and areas: `frontend/src/app/AppShell.tsx`, new hook under `frontend/src/app/hooks/`.
    Validation: viewer and compare flows behave identically.
    Status: completed at `2026-02-11T05:58:53Z`; artifacts `frontend/src/app/hooks/useAppSelectionViewerCompare.ts` and selection/viewer/compare rewiring in `frontend/src/app/AppShell.tsx`; validation `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`39 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).

21. T13c: Extract AppShell presence/sync domain hook.
    Goal: isolate event subscriptions, connection status, and activity derivation.
    Affected files and areas: `frontend/src/app/AppShell.tsx`, new hook under `frontend/src/app/hooks/`.
    Validation: presence indicators and reconnect behaviors stay stable.
    Status: completed at `2026-02-11T06:00:15Z`; artifacts `frontend/src/app/hooks/useAppPresenceSync.ts`, presence/sync rewiring in `frontend/src/app/AppShell.tsx`, and note `docs/dev_notes/20260211_s4_t13c_presence_sync_hook.md`; line budget moved from `2020` to `1664` lines for `frontend/src/app/AppShell.tsx`; validation `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`39 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).

22. T13d: Extract AppShell mutation/actions domain hook.
    Goal: isolate upload/move/context actions and error handling.
    Affected files and areas: `frontend/src/app/AppShell.tsx`, new hook under `frontend/src/app/hooks/`.
    Validation: action UX and errors match current behavior.
    Status: completed at `2026-02-11T06:08:15Z`; artifacts `frontend/src/app/hooks/useAppActions.ts` and mutation/context-action rewiring in `frontend/src/app/AppShell.tsx`; line budget moved from `1664` to `1429` lines for `frontend/src/app/AppShell.tsx`; validation `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`39 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).

23. T14: Extract AppShell selectors and pure helper models.
    Goal: move list transforms and derived state into pure tested functions.
    Affected files and areas: `frontend/src/app/model/`, `frontend/src/app/utils/`.
    Validation: added unit tests for extracted selectors pass.
    Status: completed at `2026-02-11T09:38:22Z`; artifacts `frontend/src/app/model/appShellSelectors.ts`, `frontend/src/app/__tests__/appShellSelectors.test.ts`, and selector-consumer rewiring in `frontend/src/app/AppShell.tsx`; line budget moved from `1429` to `1385` lines for `frontend/src/app/AppShell.tsx`; validation `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).

24. T15: Reduce AppShell rerender/effect churn.
    Goal: optimize memo boundaries, event listener lifecycles, and expensive derivations.
    Affected files and areas: `frontend/src/app/AppShell.tsx` and new hooks/helpers.
    Validation: interaction semantics remain identical; profiling snapshots show reduced render work.
    Status: completed at `2026-02-11T09:44:52Z`; artifacts `frontend/src/shared/hooks/useLatestRef.ts`, listener-lifecycle updates in `frontend/src/app/AppShell.tsx`, and note `docs/dev_notes/20260211_s4_t15_listener_lifecycle_stabilization.md`; line budget moved from `1385` to `1400` lines for `frontend/src/app/AppShell.tsx` (with lower effect/listener churn); validation `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).

S4 handover (`2026-02-11T09:44:52Z`):
1. Completed: `T13a`, `T13b`, `T13c`, `T13d`, `T14`, and `T15`; AppShell now has domain hooks (`useAppDataScope`, `useAppSelectionViewerCompare`, `useAppPresenceSync`, `useAppActions`), pure selectors (`appShellSelectors.ts`), and stabilized high-frequency listener lifecycles via `useLatestRef`.
2. Validations run and outcomes: `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` -> `45 passed`; `npm run build` -> success; `npx tsc --noEmit` retains known pre-existing failures (`src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, `src/features/inspector/Inspector.tsx`).
3. Known risks/follow-ups: `AppShell.tsx` remains above the final guidance target (`1400` vs `<=850` lines) and global repo typecheck is still red due pre-existing issues outside `T15`; `S5` should preserve the stabilized listener patterns while moving Inspector-heavy logic out of `Inspector.tsx`.
4. First step for S5: execute `T16` by extracting Inspector metadata normalization and comparison-diff derivations into `frontend/src/features/inspector/model/` with dedicated model-level tests before splitting section components.

25. T16: Extract Inspector pure metadata and compare model utilities.
    Goal: isolate metadata normalization/rendering/flattening and compare diff generation.
    Affected files and areas: `frontend/src/features/inspector/model/`, `frontend/src/features/inspector/Inspector.tsx`.
    Validation: inspector export comparison tests and new model tests pass.
    Status: completed at `2026-02-11T09:48:03Z`; artifacts `frontend/src/features/inspector/model/metadataCompare.ts`, `frontend/src/features/inspector/model/__tests__/metadataCompare.test.ts`, and model-consumer rewiring in `frontend/src/features/inspector/Inspector.tsx`; line budget moved from `1567` to `1313` lines for `frontend/src/features/inspector/Inspector.tsx`; validation `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts` (`15 passed`) and `npm run build` (success).

26. T17: Split Inspector sections into typed components.
    Goal: separate overview/compare/basics/metadata/notes section responsibilities.
    Affected files and areas: `frontend/src/features/inspector/sections/`, `frontend/src/features/inspector/Inspector.tsx`.
    Validation: visual/interaction parity in manual and automated checks.
    Status: completed at `2026-02-11T09:55:59Z`; artifacts `frontend/src/features/inspector/sections/InspectorSection.tsx`, `frontend/src/features/inspector/sections/OverviewSection.tsx`, `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`, `frontend/src/features/inspector/sections/BasicsSection.tsx`, `frontend/src/features/inspector/sections/MetadataSection.tsx`, `frontend/src/features/inspector/sections/NotesSection.tsx`, and delegate-rewiring updates in `frontend/src/features/inspector/Inspector.tsx`; line budget moved from `1313` to `865` lines for `frontend/src/features/inspector/Inspector.tsx`; validation `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts` (`15 passed`) and `npm run build` (success).

27. T18: Extract Inspector async workflows into hooks.
    Goal: isolate metadata fetch, compare export submit, typing state, and conflict logic.
    Affected files and areas: `frontend/src/features/inspector/hooks/`, `frontend/src/features/inspector/Inspector.tsx`.
    Validation: async loading/error/success semantics unchanged.
    Status: completed at `2026-02-11T10:05:03Z`; artifacts `frontend/src/features/inspector/hooks/useInspectorSidecarWorkflow.ts`, `frontend/src/features/inspector/hooks/useInspectorMetadataWorkflow.ts`, and async-workflow rewiring updates in `frontend/src/features/inspector/Inspector.tsx`; line budget moved from `865` to `714` lines for `frontend/src/features/inspector/Inspector.tsx`; validation `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts` (`15 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures remain in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).

28. T19: Optimize heavy Inspector render paths.
    Goal: reduce expensive compare/metadata rendering churn without changing what is shown.
    Affected files and areas: inspector sections and model utilities.
    Validation: parity tests pass; sampled interaction latency improves on large metadata payloads.
    Status: completed at `2026-02-11T11:20:25Z`; artifacts `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/inspector/model/metadataCompare.ts`, `frontend/src/features/inspector/model/__tests__/metadataCompare.test.ts`, `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`, `frontend/src/features/inspector/sections/MetadataSection.tsx`, and note `docs/dev_notes/20260211_s5_t19_inspector_render_optimization.md`; line budget moved from `714` to `740` lines for `frontend/src/features/inspector/Inspector.tsx` (with reduced heavy render churn); validation `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts` (`16 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures remain in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).

S5 handover (`2026-02-11T11:20:25Z`):
1. Completed: `T16`, `T17`, `T18`, and `T19`; Inspector now separates pure metadata/compare transforms (`metadataCompare.ts`), section rendering (`sections/*`), async workflows (`useInspectorSidecarWorkflow`, `useInspectorMetadataWorkflow`), and render-path optimizations (normalized-data reuse + open-section gating + memoized compare diff table).
2. Validations run and outcomes: `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts` -> `16 passed`; `npm run build` -> success; `npx tsc --noEmit` retains known pre-existing failures (`src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, `src/features/inspector/Inspector.tsx`); synthetic compare-render benchmark (`node --experimental-strip-types ...`) improved from `median 12.88ms`/`mean 13.43ms` pre-`T19` to `median 10.65ms`/`mean 10.93ms` post-`T19` with equal checksum.
3. Known risks/follow-ups: `frontend/src/features/inspector/Inspector.tsx` remains above the final guidance target (`740` vs `<=700` lines), and repo-wide `tsc` remains red due pre-existing type issues outside `T19`; future tickets should keep new normalized-model helpers as the canonical compare/metadata transform path to avoid reintroducing duplicate normalization work.
4. First step for S6: execute `T20` by splitting `frontend/src/features/metrics/MetricsPanel.tsx` into typed `features/metrics/components/*` cards (attributes/range/histogram) while preserving current filter behavior and existing metrics test expectations.

29. T20: Split MetricsPanel into cards/components.
    Goal: separate attributes, range panel, and histogram card UI components.
    Affected files and areas: `frontend/src/features/metrics/components/`, `frontend/src/features/metrics/MetricsPanel.tsx`.
    Validation: metrics filtering behavior unchanged.
    Status: completed at `2026-02-11T11:28:25Z`; artifacts `frontend/src/features/metrics/components/AttributesPanel.tsx`, `frontend/src/features/metrics/components/MetricRangePanel.tsx`, `frontend/src/features/metrics/components/MetricHistogramCard.tsx`, and composition-facade rewrite in `frontend/src/features/metrics/MetricsPanel.tsx` (`1024` -> `150` lines); validation `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).

30. T21: Extract histogram math utilities into pure module.
    Goal: isolate binning/range/formatting helpers and edge-case behavior.
    Affected files and areas: `frontend/src/features/metrics/model/histogram.ts` and related files.
    Validation: dedicated utility tests pass on edge values.
    Status: completed at `2026-02-11T13:40:15Z`; artifacts `frontend/src/features/metrics/model/histogram.ts`, `frontend/src/features/metrics/model/__tests__/histogram.test.ts`, and histogram-helper rewiring in `frontend/src/features/metrics/components/MetricHistogramCard.tsx`, `frontend/src/features/metrics/components/MetricRangePanel.tsx`, and `frontend/src/features/metrics/MetricsPanel.tsx`; validation `npm run test -- src/features/metrics/model/__tests__/histogram.test.ts` (`8 passed`), `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures remain in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).

31. T22: Extract histogram interaction state machine hook.
    Goal: isolate drag/hover/commit transitions in a testable hook.
    Affected files and areas: `frontend/src/features/metrics/hooks/`, metrics components.
    Validation: histogram drag and clear behavior remains identical.
    Status: completed at `2026-02-11T13:48:25Z`; artifacts `frontend/src/features/metrics/hooks/useMetricHistogramInteraction.ts`, `frontend/src/features/metrics/hooks/__tests__/useMetricHistogramInteraction.test.ts`, and interaction-wiring updates in `frontend/src/features/metrics/components/MetricHistogramCard.tsx`; validation `npm run test -- src/features/metrics/model/__tests__/histogram.test.ts src/features/metrics/hooks/__tests__/useMetricHistogramInteraction.test.ts` (`12 passed`), `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), `npm run build` (success), and `npx tsc --noEmit` (known pre-existing failures remain in `src/api/__tests__/client.presence.test.ts`, `src/app/AppShell.tsx`, `src/app/components/StatusBar.tsx`, and `src/features/inspector/Inspector.tsx`).

32. T23: Optimize metrics computation reuse.
    Goal: avoid repeated recomputation across filters/selections where result can be safely reused.
    Affected files and areas: metrics model and hooks/components.
    Validation: same filter outcomes, fewer expensive recalculations in profiling.
    Status: completed at `2026-02-12T01:26:58Z`; artifacts `frontend/src/features/metrics/model/metricValues.ts`, `frontend/src/features/metrics/model/__tests__/metricValues.test.ts`, `frontend/src/features/metrics/MetricsPanel.tsx`, `frontend/src/features/metrics/components/MetricRangePanel.tsx`, `frontend/src/features/metrics/components/MetricHistogramCard.tsx`, and profiling note `docs/dev_notes/20260212_s6_t23_metrics_computation_reuse.md`; validation `npm run test -- src/features/metrics/model/__tests__/metricValues.test.ts src/features/metrics/model/__tests__/histogram.test.ts src/features/metrics/hooks/__tests__/useMetricHistogramInteraction.test.ts` (`14 passed`), `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), and `npm run build` (success); profiling snapshot (synthetic) preserved output checksum and improved show-all recomputation (`median 18.12ms` -> `9.33ms`, `mean 18.23ms` -> `9.87ms`) with sub-millisecond show-one overhead (`median +0.11ms`).

S6 handover (`2026-02-12T01:26:58Z`):
1. Completed: `T20`, `T21`, `T22`, and `T23`; metrics area now has split UI components (`components/*`), pure histogram math (`model/histogram.ts`), isolated interaction state machine (`hooks/useMetricHistogramInteraction.ts`), and shared keyed metric-value cache reuse (`model/metricValues.ts`) wired through `MetricsPanel` + `MetricRangePanel`.
2. Validations run and outcomes: `npm run test -- src/features/metrics/model/__tests__/metricValues.test.ts src/features/metrics/model/__tests__/histogram.test.ts src/features/metrics/hooks/__tests__/useMetricHistogramInteraction.test.ts` -> `14 passed`; `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` -> `45 passed`; `npm run build` -> success.
3. Known risks/follow-ups: `show one` mode now incurs a small cache-construction overhead in synthetic timing (`~0.11ms` median) while `show all` improves substantially; preserve the current scoped-key strategy (`[activeMetric]` vs full metric list) to keep this overhead bounded. Repo-wide `npx tsc --noEmit` remains red on known pre-existing files outside S6 scope.
4. First step for S7: execute `T24a` by running the fixed backend/frontend/type/build validation matrix exactly as specified and record failing domains before any fixes.

33. T24a: Execute fixed validation matrix only.
    Goal: run all required backend/frontend/type/build checks without mixing fixes.
    Affected files and areas: none (execution-only ticket).
    Validation: all checks pass, or failures are captured with failing domain tags.
    Status: completed at `2026-02-12T01:28:22Z`; validation `pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py` (`64 passed`), import probe (`import-contract-ok`), `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), and `npm run build` (success); failing domains tagged for `T24b`: `[frontend-typecheck]` `npx tsc --noEmit`, `[packaging-tooling]` `python -m build` (`No module named build`).

34. T24b: Fix regressions by explicit domain ownership.
    Goal: resolve failures in scoped follow-up commits by backend/table/frontend ownership lanes.
    Affected files and areas: only files implicated by failing checks.
    Validation: previously failing checks pass; no new failures introduced.
    Status: completed at `2026-02-12T01:43:06Z`; resolved `[frontend-typecheck]` domain with artifacts `frontend/src/api/__tests__/client.presence.test.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/app/components/StatusBar.tsx`, and `frontend/src/features/inspector/Inspector.tsx` (validation: `cd frontend && npx tsc --noEmit` pass; `cd frontend && npm run test -- src/api/__tests__/client.presence.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/app/__tests__/presenceUi.test.ts` -> `14 passed`) and resolved `[packaging-tooling]` by adding `build>=1.2` to `pyproject.toml` `dev` extras (validation: `python -m pip install -e '.[dev]'` success; `python -m build` success).

35. T25: Regenerate shipped frontend assets and verify Python-served shell.
    Goal: ensure packaged app serves updated frontend after UI refactor.
    Affected files and areas: `src/lenslet/frontend/` generated assets.
    Validation: build copy succeeds and app serves expected `index.html` content via FastAPI static mount.
    Status: completed at `2026-02-12T01:45:33Z`; regenerated shipped assets in `src/lenslet/frontend/index.html` and `src/lenslet/frontend/assets/index-CAfycEDX.css` + `src/lenslet/frontend/assets/index-B5RaBndO.js`; validation `cd frontend && npm run build` (success), `rsync -a --delete frontend/dist/ src/lenslet/frontend/` (success), and shell-serve probe (`frontend-shell-serve-ok`).

36. T26: Update docs with new module map and operational notes.
    Goal: document new boundaries and maintenance guidance for future contributors.
    Affected files and areas: `DEVELOPMENT.md`, `README.md`, and this plan progress section as needed.
    Validation: docs reflect final module layout and verification workflow.
    Status: completed at `2026-02-12T01:50:43Z`; artifacts `README.md`, `DEVELOPMENT.md`, and module-map/command alignment updates in this plan; validation `pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py` (`64 passed`), import probe (`import-contract-ok`), `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` (`45 passed`), `npx tsc --noEmit` (pass), `npm run build` (success), and `python -m build` (success).

S7 handover (`2026-02-12T01:50:43Z`):
1. Completed: `T24a`, `T24b`, `T25`, and `T26`; closeout now includes green fixed validation matrix, resolved typecheck/packaging regressions, deterministic shipped-frontend artifact mirroring, and updated operator docs for final module boundaries/workflows.
2. Validations run and outcomes: backend matrix `pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py` -> `64 passed`; import probe -> `import-contract-ok`; frontend parity slice `npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts` -> `45 passed`; `npx tsc --noEmit` -> pass; `npm run build` -> success; `python -m build` -> success.
3. Known risks/follow-ups: line-budget guidance remains non-blocking in two files (`frontend/src/app/AppShell.tsx` at ~`1401` lines vs `<=850`, `frontend/src/features/inspector/Inspector.tsx` at ~`740` lines vs `<=700`) and one backend facade (`src/lenslet/storage/table.py` at `532` lines vs `<=500`); further reductions should be optional maintenance-only refactors with compatibility guards, not acceptance blockers.
4. First step for post-plan maintenance: keep the fixed acceptance matrix and deterministic frontend asset sync (`rsync -a --delete frontend/dist/ src/lenslet/frontend/`) as required release gates for future changes.


## Validation and Acceptance


Sprint acceptance remains behavior-first, but now includes performance evidence where optimization tickets are claimed complete.

1. S0 acceptance requires passing baseline matrix, documented architecture decision gate, and import-contract script success.
2. S1 acceptance requires unchanged backend route behavior with compatibility checks passing.
3. S2 acceptance requires hotpath endpoint parity and measurable improvement in at least one tracked backend hotpath metric without regressions elsewhere.
4. S3 acceptance requires table-backed parity plus measured reduction in index/probe overhead on representative input.
5. S4 acceptance requires AppShell workflow parity and reduced avoidable rerender/effect churn.
6. S5 acceptance requires Inspector parity and faster heavy metadata/compare interactions on representative payloads.
7. S6 acceptance requires Metrics behavior parity and reduced expensive recomputation in histogram/filter interactions.
8. S7 acceptance requires full matrix pass, artifact sync completion, packaging sanity, and updated docs.

Overall acceptance criteria are:

1. Public APIs, CLI flags, and user-visible semantics are unchanged.
2. Existing tests pass without semantic weakening.
3. Compatibility script for private/de facto surfaces passes.
4. Performance claims are backed by before/after snapshots captured during the sprint.
5. Target long files are materially reduced and responsibilities are cleanly separated.

Required validation matrix:

    Working directory: /home/ubuntu/dev/lenslet

    pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py

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

    Working directory: /home/ubuntu/dev/lenslet/frontend

    npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts

    npx tsc --noEmit
    npm run build
    rsync -a --delete dist/ ../src/lenslet/frontend/

    Working directory: /home/ubuntu/dev/lenslet

    python -m build

Performance evidence expectations per optimization sprint:

1. Capture before/after measurement for target operations using the same dataset and command path.
2. Keep correctness checks in the same run so performance does not regress semantics.
3. Record measured deltas in sprint notes under `docs/` for reproducibility.


## Idempotence and Recovery


This plan is idempotent at ticket granularity. Re-running extraction commits should not mutate data formats or route contracts. Optimization tickets must retain exact output semantics, so rollback is straightforward to the previous behavior-safe commit.

Recovery is domain-scoped.

1. If backend extraction regresses behavior, revert affected backend extraction ticket commits and re-run backend matrix before continuing.
2. If frontend extraction regresses behavior, revert only affected frontend domain ticket commits and re-run frontend matrix.
3. If an optimization improves speed but changes semantics, drop that optimization and keep structural refactor only.

No storage migration is introduced in this plan, so rollback does not require data repair.


## Artifacts and Notes


Subagent review artifact for this plan is stored at `docs/20260211_foundational_long_file_refactor_plan_review.txt`.

S0 `T2a` architecture-gate artifact is stored at `docs/dev_notes/20260211_s0_t2a_server_module_structure_gate.md`.

Proposed backend target module shape (module-only; no `server/` package conversion):

    src/lenslet/server.py                              # public facade + stable exports
    src/lenslet/server_runtime.py                      # shared runtime wiring
    src/lenslet/server_routes_common.py                # folders/item/thumb/file/search
    src/lenslet/server_routes_presence.py              # presence routes and diagnostics
    src/lenslet/server_routes_embeddings.py            # embeddings routes
    src/lenslet/server_routes_views.py                 # views routes
    src/lenslet/server_routes_index.py                 # index/meta routes
    src/lenslet/server_routes_og.py                    # OG routes
    src/lenslet/server_media.py                        # media/export helper stack

Proposed table-storage internal split while preserving `TableStorage` facade:

    src/lenslet/storage/table.py                       # public class facade and imports
    src/lenslet/storage/table_facade.py                # facade-operation delegates (I/O, metadata/search, presign)
    src/lenslet/storage/table_schema.py                # column detection and coercion
    src/lenslet/storage/table_paths.py                 # source/path derivation and safety
    src/lenslet/storage/table_index.py                 # index build pipeline
    src/lenslet/storage/table_probe.py                 # remote headers/dimensions
    src/lenslet/storage/table_media.py                 # local fast-dimension readers/thumbnail helpers

Final frontend module shape (implemented):

    frontend/src/app/AppShell.tsx
    frontend/src/app/hooks/useAppDataScope.ts
    frontend/src/app/hooks/useAppSelectionViewerCompare.ts
    frontend/src/app/hooks/useAppPresenceSync.ts
    frontend/src/app/hooks/useAppActions.ts
    frontend/src/app/model/*.ts
    frontend/src/features/inspector/Inspector.tsx
    frontend/src/features/inspector/sections/*.tsx
    frontend/src/features/inspector/model/*.ts
    frontend/src/features/inspector/hooks/*.ts
    frontend/src/features/metrics/MetricsPanel.tsx
    frontend/src/features/metrics/components/*.tsx
    frontend/src/features/metrics/model/histogram.ts
    frontend/src/features/metrics/model/metricValues.ts
    frontend/src/features/metrics/hooks/*.ts

Target line-budget outcomes after completion are guidance only:

    src/lenslet/server.py <= 350 lines
    src/lenslet/storage/table.py <= 500 lines
    frontend/src/app/AppShell.tsx <= 850 lines
    frontend/src/features/inspector/Inspector.tsx <= 700 lines
    frontend/src/features/metrics/MetricsPanel.tsx <= 550 lines


## Interfaces and Dependencies


Public interfaces that must remain stable include:

    from lenslet.server import create_app, create_app_from_datasets, create_app_from_table, create_app_from_storage
    from lenslet.storage.table import TableStorage, load_parquet_table, load_parquet_schema

De facto compatibility surfaces that are currently exercised and must remain stable during this refactor include:

    lenslet.server.HotpathTelemetry
    lenslet.server._file_response
    lenslet.server._thumb_response_async
    lenslet.server.og

Backend internal interface targets are:

    build_runtime(...) -> AppRuntime
    register_common_routes(app: FastAPI, runtime: AppRuntime, to_item: Callable[..., Item]) -> None
    register_presence_routes(app: FastAPI, runtime: AppRuntime) -> None
    register_embedding_routes(app: FastAPI, runtime: AppRuntime) -> None

Table-storage internal interface targets are:

    resolve_source_column(columns: list[str], data: dict[str, list[Any]], source_column: str | None) -> str
    build_indexes(...) -> BuildIndexesResult
    probe_remote_dimensions(tasks: list[ProbeTask], workers: int) -> list[ProbeResult]
    read_dimensions_from_bytes(data: bytes, ext: str | None) -> tuple[int, int] | None

Frontend interface targets are:

    useAppDataScope(...) -> { data, items, metricKeys, refetch, loadingState, errors }
    useAppSelectionViewerCompare(...) -> { selectedPaths, setSelectedPaths, openViewer, closeViewer, compareState }
    useInspectorCompareExport(...) -> { exportState, onExport, onReverseExport }
    computeHistogramFromValues(values: number[], bins: number, base?: Histogram): Histogram | null

Dependencies remain unchanged unless an optimization ticket explicitly justifies a new dependency with measurable benefit and equivalent correctness guarantees. Default path is no new runtime dependencies.

Ownership lanes for implementation are:

1. Backend lane owns S1, S2, and backend portions of S7.
2. Data/table lane owns S3 and table portions of S7.
3. Frontend lane owns S4, S5, S6, and frontend artifact sync in S7.

Revision note (2026-02-11): Updated after user direction to allow bolder performance refactors and after mandatory subagent review; resolved server module-structure ambiguity, expanded compatibility matrix and validation coverage, split oversized tickets, added API freeze gate, and added frontend shipped-asset synchronization requirements.
