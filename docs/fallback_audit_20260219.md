# Fallback Audit (2026-02-19)

## Scope
- Scanned: `src/lenslet/`, `frontend/src/`, `tests/`, `scripts/experimental/`.
- Skipped: `docs/agents_archive/`, generated bundles under `src/lenslet/frontend/assets/`.

## Rating Scales
- Duplication level:
  - Low: single fallback or single-layer guard.
  - Medium: two-layer fallback or repeated in a couple of places.
  - High: repeated in multiple files or stacked fallbacks for the same behavior.
- Cleanup safety rating:
  - Safe: removal unlikely to break core flows under a hard cutover.
  - Caution: removal may reduce robustness or require refactors.
  - Risky: removal likely breaks common flows or data access.

## Fallbacks
| Category | Fallback behavior | Locations | Duplication | Cleanup safety | Notes |
| --- | --- | --- | --- | --- | --- |
| Legacy/compat | Server import/monkeypatch facade + import contract | `src/lenslet/server.py`, `tests/test_import_contract.py` | Low | Caution | Compatibility layer for external monkeypatch callers. |
| Legacy/compat | Table import facade + import contract | `src/lenslet/storage/table.py`, `tests/test_import_contract.py` | Low | Caution | Compatibility layer for external imports. |
| Legacy/compat | Legacy query param awareness (`legacy_recursive`, `page`, `page_size`) | `src/lenslet/server_routes_common.py`, `tests/test_folder_recursive.py`, `frontend/src/api/__tests__/folders.test.ts` | Low | Safe | Rejects/guards legacy params. |
| Legacy/compat | Client ID migration from legacy localStorage key | `frontend/src/api/client.ts` | Medium | Safe | Migrates `lenslet.client_id` to session key. |
| Legacy/compat | Legacy presence heartbeat route (`/presence`) | `frontend/src/api/client.ts` | Low | Safe | Alias of new join/move/leave API. |
| Legacy/compat | Legacy sidebar width key (`leftW`) | `frontend/src/app/layout/useSidebars.ts`, `frontend/src/app/layout/__tests__/useSidebars.test.ts` | Low | Safe | Reads prior persisted key if new keys missing. |
| Legacy/compat | Legacy stars filter clause (`stars`) | `frontend/src/features/browse/model/filters.ts` | Low | Safe | Accepts old filter AST. |
| Legacy/compat | Legacy media query listeners (`addListener/removeListener`) | `frontend/src/shared/hooks/useMediaQuery.ts` | Low | Caution | Drops older browser support if removed. |
| Runtime | Default views payload on missing/invalid `views.json` | `src/lenslet/workspace.py` | Low | Risky | Hard-failing on missing views would break first run or bad file. |
| Runtime | OG image fallback when disabled or no tiles | `src/lenslet/server_routes_og.py`, `src/lenslet/og.py` | Medium | Caution | Avoids blank OG responses. |
| Runtime | Stream-local file fallback to `read_bytes` for remote sources | `src/lenslet/server_media.py`, `tests/test_hotpath_sprint_s4.py` | Low | Risky | Required for non-local storage. |
| Runtime | Export annotation fallback when annotation hook fails | `src/lenslet/server.py` | Low | Caution | Keeps compare export working with broken annotator. |
| Runtime | Table import fallback for missing name/mime | `src/lenslet/storage/table_index.py`, `scripts/experimental/fast_table_source_index.py` | Medium | Caution | Drops rows if removed; breaks weak metadata tables. |
| Runtime | Cache/index generation token default (`"default"`) | `src/lenslet/server_browse.py`, `src/lenslet/server_factory.py` | High | Caution | Avoids empty generation tokens when storage lacks signature. |
| Runtime | Presence prune interval fallback from `app.state` | `src/lenslet/server_factory.py` | Low | Caution | Guards missing runtime state. |
| Runtime | EventSource retry fallback to polling after max attempts | `frontend/src/api/client.ts` | Medium | Caution | Without it, offline clients stop updating. |
| Runtime | `sendBeacon` fallback to keepalive `fetch` | `frontend/src/api/client.ts` | Low | Caution | Without it, leave/keepalive may be dropped in some browsers. |
| Runtime | Polling interval fallbacks for folder/search/sidecar | `frontend/src/api/folders.ts`, `frontend/src/api/search.ts`, `frontend/src/api/items.ts` | High | Caution | Used when polling is enabled (typically after SSE fails). |
| Runtime | Default sidecar on empty patch | `frontend/src/api/items.ts` | Low | Caution | Prevents undefined sidecar on no-op patch. |
| UI/data | Build fallback item when metadata missing | `frontend/src/app/utils/appShellHelpers.ts`, `frontend/src/app/hooks/useAppDataScope.ts` | Low | Caution | Avoids blank UI entries if item lacks meta. |
| UI/data | Metadata compare fallback node + styling | `frontend/src/features/inspector/model/metadataCompare.ts`, `frontend/src/features/inspector/sections/JsonRenderCode.tsx`, `frontend/src/theme.css` | Medium | Caution | Avoids crashes on unexpected JSON shapes. |
| UI/data | Sort parse fallback to last-known spec | `frontend/src/shared/ui/Toolbar.tsx` | Low | Safe | Prevents invalid sort strings from breaking UI. |
| UI/data | Mutation error message fallback | `frontend/src/app/hooks/useAppActions.ts` | Low | Safe | Ensures non-empty UI message. |
