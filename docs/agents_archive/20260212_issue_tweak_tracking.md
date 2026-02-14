# Foundational Execution Plan: Lenslet Issue and Tweak Tracking (2026-02-12)


## Purpose / Big Picture


No `PLANS.md` (or equivalent canonical planning file) exists in this repository, so this document is the canonical execution plan for this change set.

After implementation, users should be able to re-enter folders without jumpy context loss, search by source/path tokens consistently across storage backends, resize sidebars without scrollbar drag conflicts, see deterministic indexing progress at startup, and trigger compare/export actions directly from the inspector multi-select context.

This plan treats each requested change as if it had been a foundational product assumption from day one. The implementation strategy therefore prioritizes first-class contracts and shared abstractions over local patches.


## Progress


- [x] 2026-02-12 14:28:30Z Captured source issue brief from `docs/20260212_issue_tweak_tracking.md` and confirmed required scope includes Issues 1-3 and Tweaks 1-2.
- [x] 2026-02-12 14:28:30Z Audited referenced architecture paths in frontend and backend, including `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/features/inspector/Inspector.tsx`, `src/lenslet/storage/memory.py`, `src/lenslet/storage/parquet.py`, `src/lenslet/storage/table_facade.py`, and `src/lenslet/server_factory.py`.
- [x] 2026-02-12 14:28:30Z Mapped current validation assets in `tests/` and `frontend/src/**/__tests__/` and identified missing coverage for scroll-anchor restore, search parity contracts, sidebar hitbox geometry, and indexing status UI.
- [x] 2026-02-12 14:28:30Z Drafted this full execution plan in plan-writer format with sprint and atomic ticket breakdowns.
- [x] 2026-02-12 14:31:52Z Ran mandatory subagent review prompt and captured actionable feedback on scope split, validation gaps, hidden dependencies, and export capability negotiation.
- [x] 2026-02-12 14:31:52Z Integrated subagent review feedback into sprint/task structure and finalized this handoff-ready plan document.
- [x] 2026-02-12 15:58:08Z Completed Sprint S1 / T1 by adding shared search contract helpers in `src/lenslet/storage/search_text.py` and wiring `memory`, `parquet`, `table`, and `dataset` search call paths to one `path_in_scope` + `build_search_haystack` implementation.
- [x] 2026-02-12 15:58:08Z Added backend contract coverage in `tests/test_search_text_contract.py` for name/path/tags/notes parity across all storage backends and source/url toggles for dataset/table modes.
- [x] 2026-02-12 15:58:08Z Validated T1 with `pytest -q tests/test_search_text_contract.py tests/test_dataset_http.py tests/test_parquet_ingestion.py` and `pytest -q tests/test_import_contract.py` (all passing).
- [x] 2026-02-12 16:05:56Z Completed Sprint S1 / T2 by updating `src/lenslet/storage/memory.py` search haystack assembly to include optional source/url-like metadata fields when present while preserving path-based search as a first-class token.
- [x] 2026-02-12 16:05:56Z Added memory-specific regression coverage in `tests/test_search_text_contract.py` for partial path-token matching with in-scope/out-of-scope assertions and optional source-like metadata token queries.
- [x] 2026-02-12 16:05:56Z Validated T2 with `pytest -q tests/test_search_text_contract.py` and `pytest -q tests/test_import_contract.py` (all passing).
- [x] 2026-02-12 16:05:56Z Reconciled Sprint S1 task bookkeeping to mark T3a/T3b complete based on iteration 1's shipped parquet/table/dataset shared-contract refactor plus parity coverage in `tests/test_search_text_contract.py`.
- [x] 2026-02-12 16:10:30Z Completed Sprint S1 / T4 by adding API-level `/search` source-token regression coverage in `tests/test_search_source_contract.py` across table and dataset app modes with include-source enabled/disabled assertions and scoped-search negative checks.
- [x] 2026-02-12 16:10:30Z Validated T4 with `pytest -q tests/test_search_source_contract.py tests/test_search_text_contract.py` (all passing).
- [x] 2026-02-12 16:15:35Z Completed Sprint S1 / T4b by introducing a canonical frontend search-request contract (`buildCanonicalSearchRequest`, scope-path normalization, and scope-aware placeholder retention) in `frontend/src/api/search.ts`, wiring `frontend/src/app/hooks/useAppDataScope.ts` to consume it, and tightening shared exports in `frontend/src/shared/api/search.ts`.
- [x] 2026-02-12 16:15:35Z Added frontend regression coverage in `frontend/src/api/__tests__/search.test.ts` for source-token query normalization and stable placeholder behavior within-scope while preventing stale cross-scope renders.
- [x] 2026-02-12 16:15:35Z Validated T4b with `npm run test -- src/api/__tests__/search.test.ts src/api/__tests__/folders.test.ts`, `npm run test -- src/app/__tests__/appShellSelectors.test.ts`, and `npm run build` (all passing).
- [x] 2026-02-12 16:19:10Z Completed Sprint S2 / T5 by introducing directional sidebar-resize geometry tokens in `frontend/src/styles.css` and wiring explicit side classes in `frontend/src/app/components/LeftSidebar.tsx` and `frontend/src/features/inspector/Inspector.tsx`.
- [x] 2026-02-12 16:19:10Z Moved left-pane clipping responsibility from the panel shell to the inner content container so the left resize hitbox can sit fully outside the scrollbar lane while keeping panel content clipping behavior.
- [x] 2026-02-12 16:19:10Z Validated T5 automated checks with `npm run test -- src/lib/__tests__/breakpoints.test.ts src/app/__tests__/appShellSelectors.test.ts` and `npm run build` (all passing); manual desktop/coarse-pointer interaction verification remains queued for T6.
- [x] 2026-02-12 16:25:24Z Completed Sprint S2 / T6 by extracting explicit sidebar resize and persistence contract helpers (`clampLeftSidebarWidth`, `clampRightSidebarWidth`, `readPersistedSidebarWidths`, and `persistSidebarWidth`) in `frontend/src/app/layout/useSidebars.ts` and wiring the hook to consume them.
- [x] 2026-02-12 16:25:24Z Added targeted regression coverage in `frontend/src/app/layout/__tests__/useSidebars.test.ts` for left/right clamp bounds, legacy `leftW` fallback loading, and per-side localStorage persistence keys.
- [x] 2026-02-12 16:25:24Z Validated T6 with `npm run test -- src/app/layout/__tests__/useSidebars.test.ts src/lib/__tests__/breakpoints.test.ts src/app/__tests__/appShellSelectors.test.ts` and `npm run build` (all passing).
- [x] 2026-02-12 16:30:49Z Completed Sprint S3 / T7 by adding `frontend/src/app/hooks/useFolderSessionState.ts` with first-class folder session contracts for hydrated snapshots, top-anchor capture, and explicit exact/subtree invalidation helpers.
- [x] 2026-02-12 16:30:49Z Wired folder session persistence into `frontend/src/app/hooks/useAppDataScope.ts` (hydrated snapshot writes) and `frontend/src/app/AppShell.tsx` (top-anchor capture from visible grid paths while preserving presence tracking).
- [x] 2026-02-12 16:30:49Z Added lifecycle/invalidation unit coverage in `frontend/src/app/hooks/__tests__/useFolderSessionState.test.ts` and validated T7 with `npm run test -- src/app/hooks/__tests__/useFolderSessionState.test.ts src/app/layout/__tests__/useSidebars.test.ts src/app/__tests__/appShellSelectors.test.ts` plus `npm run build` (all passing).
- [x] 2026-02-12 16:38:14Z Completed Sprint S3 / T8 by introducing explicit `VirtualGrid` top-anchor restore/report contracts (`restoreToTopAnchorToken`, `restoreToTopAnchorPath`, and `onTopAnchorPathChange`) plus tokenized restore arbitration that keeps selection-triggered restores independent from folder top-anchor restores.
- [x] 2026-02-12 16:38:14Z Added foundational virtual-grid session contract helpers in `frontend/src/features/browse/model/virtualGridSession.ts` and wired `frontend/src/features/browse/components/VirtualGrid.tsx` plus `frontend/src/app/AppShell.tsx` to consume them for deterministic top-anchor emission and restore behavior.
- [x] 2026-02-12 16:38:14Z Validated T8 with `npm run test -- src/features/browse/model/__tests__/virtualGridSession.test.ts src/features/browse/hooks/__tests__/useKeyboardNav.test.ts src/app/hooks/__tests__/useFolderSessionState.test.ts`, `npm run test -- src/app/__tests__/appShellSelectors.test.ts`, and `npm run build` (all passing).
- [x] 2026-02-12 16:43:15Z Completed Sprint S3 / T9 by wiring cache-first scope hydration in `frontend/src/app/hooks/useAppDataScope.ts` (seed from folder session snapshot on scope change) and adding paged rehydration gating in `frontend/src/features/browse/model/pagedFolder.ts` to skip first-page-only emissions when a cached snapshot is already rendered.
- [x] 2026-02-12 16:43:15Z Wired `frontend/src/app/AppShell.tsx` to pass `getHydratedSnapshot` into `useAppDataScope`, making re-entry restoration deterministic without transient data clears before fresh hydration finishes.
- [x] 2026-02-12 16:43:15Z Added two-phase hydration regression coverage in `frontend/src/features/browse/model/__tests__/pagedFolder.test.ts` and validated T9 with `npm run test -- src/features/browse/model/__tests__/pagedFolder.test.ts` plus `npm run build` (all passing).
- [x] 2026-02-12 16:46:55Z Completed Sprint S3 / T9b by adding delayed-hydration anti-jump regression coverage in `frontend/src/features/browse/model/__tests__/pagedFolder.test.ts` using a deferred page fetch that simulates late merge completion.
- [x] 2026-02-12 16:46:55Z Validated T9b with `npm run test -- src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/virtualGridSession.test.ts` and `npm run build` (all passing).
- [x] 2026-02-12 16:52:18Z Completed Sprint S3 / T10 by adding explicit folder-session invalidation contracts for incompatible scope transitions, wiring refresh/subtree invalidation in `frontend/src/app/AppShell.tsx`, and introducing `sessionResetToken` handling in `frontend/src/app/hooks/useAppDataScope.ts` so same-scope refresh clears stale cached snapshots immediately.
- [x] 2026-02-12 16:52:18Z Added re-entry invalidation regression coverage in `frontend/src/app/hooks/__tests__/useFolderSessionState.test.ts` for hierarchy-compatible transitions versus cross-branch invalidation behavior.
- [x] 2026-02-12 16:52:18Z Validated T10 with `npm run test -- src/app/hooks/__tests__/useFolderSessionState.test.ts src/app/__tests__/appShellHelpers.test.ts`, `npm run test -- src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/virtualGridSession.test.ts`, and `npm run build` (all passing); manual refresh/re-entry smoke workflow remains recommended.
- [x] 2026-02-12 16:53:47Z Completed Sprint S4 / T11 by adding a shared indexing lifecycle contract in `src/lenslet/indexing_status.py`, wiring deterministic `running`/`ready`/`error` transitions into `src/lenslet/server_factory.py`, and exposing lifecycle payloads from all `/health` app modes.
- [x] 2026-02-12 16:53:47Z Added storage progress snapshot plumbing via `ProgressBar.snapshot()` plus `indexing_progress()` adapters in `src/lenslet/storage/memory.py`, `src/lenslet/storage/table.py`, and `src/lenslet/storage/dataset.py` so health indexing payloads can include optional `done`/`total` counters when available.
- [x] 2026-02-12 16:53:47Z Added backend regression coverage in `tests/test_indexing_health_contract.py` for memory warm-index `running -> ready`, warm-index failure `error`, and table/dataset static `ready` payload contracts.
- [x] 2026-02-12 16:53:47Z Validated T11 with `pytest -q tests/test_indexing_health_contract.py` and `pytest -q tests/test_hotpath_sprint_s3.py::test_health_exposes_hotpath_metrics tests/test_parquet_ingestion.py::test_parquet_items_and_metrics_inline` (all passing).
- [x] 2026-02-12 17:04:34Z Completed Sprint S4 / T12 by extending frontend health typing (`frontend/src/lib/types.ts`) and wiring `useAppPresenceSync` health polling to keep checking `/health` while `indexing.state` is `running`, then stop banner polling when startup indexing reaches a terminal state.
- [x] 2026-02-12 17:04:34Z Updated `frontend/src/app/components/StatusBar.tsx` and `frontend/src/app/AppShell.tsx` to render indexing lifecycle banners (`running` progress and `error` failure) from shared health payloads while preserving existing persistence/zoom/off-view banner behavior.
- [x] 2026-02-12 17:04:34Z Added frontend indexing banner regression coverage in `frontend/src/app/components/__tests__/StatusBar.test.tsx` and validated T12 with `npm run test -- src/app/components/__tests__/StatusBar.test.tsx src/app/__tests__/appShellSelectors.test.ts` plus `npm run build` (all passing).
- [x] 2026-02-12 17:13:36Z Completed Sprint S4 / T13 by extending `IndexingLifecycle` with subscriber hooks in `src/lenslet/indexing_status.py`, wiring app-factory `indexing_listener` callbacks in `src/lenslet/server_factory.py`, and connecting CLI startup messaging in `src/lenslet/cli.py` through `CliIndexingReporter` so CLI transitions come from the same lifecycle source as `/health`.
- [x] 2026-02-12 17:13:36Z Refactored frontend indexing lifecycle parsing/polling into `frontend/src/app/hooks/healthIndexing.ts` and rewired `frontend/src/app/hooks/useAppPresenceSync.ts` to consume shared normalize/equality/poll helpers while keeping non-terminal (`idle`/`running`) polling behavior explicit.
- [x] 2026-02-12 17:13:36Z Added regression coverage in `tests/test_indexing_status_contract.py`, expanded listener coverage in `tests/test_indexing_health_contract.py`, and added frontend helper tests in `frontend/src/app/hooks/__tests__/healthIndexing.test.ts`.
- [x] 2026-02-12 17:13:36Z Validated T13 with `pytest -q tests/test_indexing_health_contract.py tests/test_indexing_status_contract.py`, `npm run test -- src/app/hooks/__tests__/healthIndexing.test.ts src/app/components/__tests__/StatusBar.test.tsx src/app/__tests__/appShellSelectors.test.ts`, and `npm run build` (all passing).
- [x] 2026-02-12 17:20:26Z Completed Sprint S5 / T14 by introducing multi-select inspector action affordances in `frontend/src/features/inspector/sections/SelectionActionsSection.tsx` and wiring them into `frontend/src/features/inspector/sections/OverviewSection.tsx` so side-by-side and export entry points are visible where selection context is shown.
- [x] 2026-02-12 17:20:26Z Wired compare-open action flow from `frontend/src/app/AppShell.tsx` through `frontend/src/features/inspector/Inspector.tsx` into overview selection actions, keeping existing compare-viewer behavior while enforcing exact-two side-by-side enablement messaging.
- [x] 2026-02-12 17:20:26Z Added section-level regression coverage in `frontend/src/features/inspector/sections/__tests__/metadataSections.test.tsx` for exact-two enabled actions and explicit `>2` disabled-reason text.
- [x] 2026-02-12 17:20:26Z Validated T14 with `npm run test -- src/features/inspector/sections/__tests__/metadataSections.test.tsx src/features/inspector/__tests__/exportComparison.test.tsx src/app/__tests__/appShellSelectors.test.ts` and `npm run build` (all passing).
- [x] 2026-02-12 17:26:03Z Completed Sprint S5 / T15 by extracting compare export form controls into `frontend/src/features/inspector/sections/SelectionExportSection.tsx` and wiring the section into multi-select `OverviewSection` rendering so export affordances remain visible independent of compare-metadata section visibility.
- [x] 2026-02-12 17:26:03Z Removed export control props/UI from `frontend/src/features/inspector/sections/CompareMetadataSection.tsx` and rewired `frontend/src/features/inspector/Inspector.tsx` + `frontend/src/features/inspector/sections/OverviewSection.tsx` to keep export execution on the existing compare workflow hook while rendering controls in selection context.
- [x] 2026-02-12 17:26:03Z Added/updated section regressions in `frontend/src/features/inspector/sections/__tests__/metadataSections.test.tsx` for active-compare export controls, compare-closed visibility guidance, and `>2` disabled messaging; validated T15 with `npm run test -- src/features/inspector/sections/__tests__/metadataSections.test.tsx src/features/inspector/__tests__/exportComparison.test.tsx src/app/__tests__/appShellSelectors.test.ts` and `npm run build` (all passing).
- [x] 2026-02-12 17:32:48Z Completed Sprint S5 / T16 by locking `v: 1` pair-only comparison export validation in `src/lenslet/server_models.py` and aligning pair-only export messaging/type usage in `frontend/src/lib/types.ts`, `frontend/src/features/inspector/exportComparison.ts`, `frontend/src/features/inspector/hooks/useInspectorCompareExport.ts`, and `frontend/src/features/inspector/sections/SelectionExportSection.tsx`.
- [x] 2026-02-12 17:32:48Z Added explicit pair-only regression coverage in `tests/test_compare_export_endpoint.py` (`>2` paths and `>2` labels invalid-request messaging) plus frontend helper/section messaging assertions in `frontend/src/features/inspector/__tests__/exportComparison.test.tsx` and `frontend/src/features/inspector/sections/__tests__/metadataSections.test.tsx`.
- [x] 2026-02-12 17:32:48Z Validated T16 with `pytest -q tests/test_compare_export_endpoint.py`, `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/sections/__tests__/metadataSections.test.tsx src/api/__tests__/client.exportComparison.test.ts`, and `npm run build` (all passing).
- [x] 2026-02-12 17:39:41Z Completed Sprint S5 / T17 by introducing a versioned comparison-export request contract (`v: 1` pair-only + `v: 2` multi-path) in `src/lenslet/server_models.py`, switching route validation in `src/lenslet/server_routes_common.py` to the shared adapter, and generalizing export label/path ordering helpers in `src/lenslet/server.py` for 2..N payloads.
- [x] 2026-02-12 17:39:41Z Extended frontend compare-export contract utilities by adding `v: 2` request typing in `frontend/src/lib/types.ts` and multi-path payload builder support in `frontend/src/features/inspector/exportComparison.ts`, while preserving existing pair-only inspector UX flows for capability-gated follow-up in T17b.
- [x] 2026-02-12 17:39:41Z Validated T17 with `pytest -q tests/test_compare_export_endpoint.py`, `npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/api/__tests__/client.exportComparison.test.ts src/features/inspector/sections/__tests__/metadataSections.test.tsx`, and `npm run build` (all passing).
- [x] 2026-02-13 02:59:29Z Completed Sprint S5 / T17b by adding explicit compare-export capability negotiation from `/health.compare_export` into frontend polling (`frontend/src/app/hooks/healthCompareExport.ts`, `frontend/src/app/hooks/useAppPresenceSync.ts`, and `frontend/src/app/AppShell.tsx`) and wiring inspector export gating through `frontend/src/features/inspector/Inspector.tsx` + workflow hooks.
- [x] 2026-02-13 02:59:29Z Extended selection-export behavior in `frontend/src/features/inspector/sections/SelectionExportSection.tsx` and `frontend/src/features/inspector/hooks/useInspectorCompareExport.ts` so pair exports remain compare-gated (`v: 1`) while `>2` export is only enabled when server capability explicitly advertises `v: 2` with a discoverable `max_paths_v2` limit.
- [x] 2026-02-13 02:59:29Z Added capability regression coverage in `frontend/src/app/hooks/__tests__/healthCompareExport.test.ts`, updated inspector section capability tests in `frontend/src/features/inspector/sections/__tests__/metadataSections.test.tsx`, and added backend `/health` capability assertions in `tests/test_indexing_health_contract.py`.
- [x] 2026-02-13 02:59:29Z Validated T17b with `pytest -q tests/test_indexing_health_contract.py tests/test_compare_export_endpoint.py`, `npm run test -- src/app/hooks/__tests__/healthCompareExport.test.ts src/app/hooks/__tests__/healthIndexing.test.ts src/features/inspector/sections/__tests__/metadataSections.test.tsx src/features/inspector/__tests__/exportComparison.test.tsx src/api/__tests__/client.exportComparison.test.ts`, and `npm run build` (all passing).
- [x] 2026-02-13 03:10:28Z Executed the next acceptance slice by launching `python -m lenslet.cli /tmp/lenslet-smoke-vC1MCl --port 7070 --host 127.0.0.1 --verbose` and validating live smoke endpoints for `/health`, `/folders`, `/search`, `/thumb`, and `/export-comparison` (`v: 1` and `v: 2`) against generated local image fixtures.
- [x] 2026-02-13 03:10:42Z Re-ran targeted acceptance suites mapped to S1-S5 outcomes: `pytest -q tests/test_search_text_contract.py tests/test_search_source_contract.py tests/test_indexing_health_contract.py tests/test_compare_export_endpoint.py`, `npm run test -- src/features/browse/model/__tests__/pagedFolder.test.ts src/app/layout/__tests__/useSidebars.test.ts src/features/inspector/sections/__tests__/metadataSections.test.tsx src/app/hooks/__tests__/healthIndexing.test.ts src/app/hooks/__tests__/healthCompareExport.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/api/__tests__/search.test.ts`, and `npm run build` (all passing).
- [x] 2026-02-13 03:10:42Z Logged the remaining blocker for full manual acceptance closure: this terminal run cannot directly verify browser-only pointer/scroll UX interactions (left-scrollbar drag isolation and visible no-jump folder re-entry), so a GUI browser smoke pass is still required.
- [x] 2026-02-13 03:31:23Z Completed Sprint S6 / T18 by adding `scripts/gui_smoke_acceptance.py`, a headless browser acceptance harness that bootstraps fixture data, runs Lenslet, and verifies sidebar drag-lane geometry, folder re-entry anchor behavior, path-token search, and inspector multi-select compare/export entry actions.
- [x] 2026-02-13 03:31:23Z Validated T18 with `python scripts/gui_smoke_acceptance.py --output-json /tmp/lenslet-gui-smoke-result.json` and `python -m py_compile scripts/gui_smoke_acceptance.py` (command pass with warnings captured for fast-index banner visibility and exact re-entry anchor drift).
- [x] 2026-02-13 03:31:23Z Logged remaining acceptance warnings from scripted browser smoke: startup indexing can complete before banner sampling in local fixture runs, and folder re-entry top-anchor restoration is not exact in the current sibling-folder scenario (`/alpha/alpha_1584.jpg` baseline vs `/alpha/alpha_1599.jpg` settled).
- [x] 2026-02-13 03:32:16Z Confirmed the S7 blocker in strict mode with `python scripts/gui_smoke_acceptance.py --strict-reentry-anchor --output-json /tmp/lenslet-gui-smoke-strict-result.json`, which fails on exact folder re-entry anchor mismatch (`before=/alpha/alpha_1584.jpg`, `restored=/alpha/alpha_0199.jpg`, `settled=/alpha/alpha_1599.jpg`).
- [x] 2026-02-13 03:35:51Z Re-ran `python scripts/gui_smoke_acceptance.py --output-json /tmp/lenslet-gui-smoke-result.json` after adding explicit Playwright dependency-guard messaging in the script; run remained stable with the same two warnings and no new regressions.
- [x] 2026-02-13 03:44:56Z Completed Sprint S7 / T18b by updating folder re-entry restore behavior: `frontend/src/features/browse/components/VirtualGrid.tsx` now captures top-anchor from DOM-visible grid cells (with virtual-row fallback), and `frontend/src/app/AppShell.tsx` now preserves folder session state across scope switches so sibling-folder re-entry can restore exact anchors.
- [x] 2026-02-13 03:44:56Z Rebuilt and synced the served frontend bundle with `npm run build && cp -r dist/* ../src/lenslet/frontend/` so CLI-served acceptance smoke validates current UI behavior.
- [x] 2026-02-13 03:45:37Z Hardened `scripts/gui_smoke_acceptance.py` indexing validation to accept deterministic `/health.indexing` lifecycle proof (`state=ready` with valid `started_at`/`finished_at`) when startup indexing finishes before visible banner sampling.
- [x] 2026-02-13 03:45:58Z Validated T18b with `npm run test -- src/features/browse/model/__tests__/virtualGridSession.test.ts`, `python -m py_compile scripts/gui_smoke_acceptance.py`, `python scripts/gui_smoke_acceptance.py --output-json /tmp/lenslet-gui-smoke-result-iter22.json`, and `python scripts/gui_smoke_acceptance.py --strict-reentry-anchor --output-json /tmp/lenslet-gui-smoke-strict-result-iter22e.json` (all passing; warnings empty in default and strict runs).


## Surprises & Discoveries


The `ParquetStorage` implementation in `src/lenslet/storage/parquet.py` is currently not wired into active app factory flows, yet it still contains divergent search behavior. This means search consistency can regress silently in code paths that appear dormant, so the foundational plan treats parity there as a contract hardening task rather than ignoring it.

The comparison export image builder in `src/lenslet/server.py` already accepts a list of images and labels, but the API request contract in `src/lenslet/server_models.py` and frontend typing in `frontend/src/lib/types.ts` currently force exactly two paths. This reveals a partial implementation of multi-image export capability with no explicit product contract.

Scroll restoration in `frontend/src/features/browse/components/VirtualGrid.tsx` is currently selection-token based and has no persisted top-visible anchor model. Combined with scope resets in `frontend/src/app/hooks/useAppDataScope.ts`, this makes restoration sensitive to hydration timing.

Health payloads returned from `src/lenslet/server_factory.py` do not expose indexing lifecycle state, so the frontend cannot distinguish "app is healthy and still indexing" from "app is fully ready." This explains why startup can appear idle on large trees.

The left and right panes share `.sidebar-resize-handle` geometry in `frontend/src/styles.css`, but only the left pane places the handle adjacent to the same edge as its scrollbar interaction zone.

Dataset and table storage already carried source metadata (`_source_paths`, `item.url`, `item.source`), but memory/parquet search never carried logical path tokens in their haystack. Converging all search paths onto one helper immediately removed these path-token blind spots without changing route contracts.

Memory metadata in local mode has historically been treated as notes/tags-only, but it can safely carry source-like fields (`source`, `source_path`, `url`, `source_url`) in imported or migrated sessions. Explicitly extracting these keys in memory search keeps cross-backend query semantics aligned without introducing a new mode flag.

`create_app_from_table(..., show_source=...)` only controls response/source field visibility and does not reconfigure `TableStorage` search indexing behavior. API regression coverage for include-source toggles must therefore construct `TableStorage` instances with explicit `include_source_in_search` values before wiring the app.

React Query `placeholderData` carries prior query data across search key changes unless explicitly constrained. Frontend search needs scope-aware placeholder retention so query typing remains smooth inside one folder while preventing stale results from briefly rendering after folder scope changes.

Left resize hitboxes cannot be moved outside the panel while `app-left-panel` uses `overflow-hidden`; outward handle placement requires `overflow-visible` on the shell and explicit overflow clipping on the inner content container.

`useSidebars` packed clamp math and storage parsing into pointer handlers, which made T5 geometry edits harder to verify. Splitting these into pure contract helpers enabled deterministic regression tests for both drag bounds and localStorage semantics without DOM-heavy harnesses.

`VirtualGrid` visible-path emission already preserves top-to-bottom iteration order for rendered rows, so the first emitted visible path can serve as a deterministic top-anchor signal without introducing a DOM measurement dependency at this stage.

Clearing top-anchor on transient empty visible sets (during load/hydration transitions) would erase useful re-entry context, so anchor updates should ignore empty viewport emissions and rely on explicit invalidation triggers for reset.

Selection and top-anchor restores can both be pending during folder transitions; treating them as independent token channels allows deterministic precedence (selection first when resolvable) while still letting top-anchor restore proceed when selection targets are temporarily unavailable.

`hydrateFolderPages` emitted first-page snapshots immediately even when a full cached folder snapshot was already on screen, which caused avoidable re-entry list contraction before late pages merged; cache-first rehydration needs explicit first-page emission gating.

Delayed-page rehydration can now be validated without brittle DOM scroll timing by asserting a saved anchor path remains present in both the cached pre-merge snapshot and the final post-merge snapshot when `fetchPage` resolves late.

Explicit refresh does not change `current` scope, so dropping stale cached scope data requires an additional refresh-driven token in `useAppDataScope`; invalidating folder-session state alone is insufficient to clear currently rendered stale snapshots.

Cross-branch session invalidation in `AppShell` erased destination folder anchors before sibling re-entry, so exact restore could regress even when snapshot hydration contracts were healthy; preserving per-folder sessions across scope switches and keeping explicit refresh invalidation as the stale-data boundary restores deterministic sibling-folder return behavior.

`/health` indexing lifecycle needs app-factory ownership (not ad-hoc storage flags): warm-index failures happened on background threads that only logged warnings, so explicit `IndexingLifecycle` state is required to make error/readiness visible to API consumers.

Storage progress bars already tracked `done/total` internally for CLI output but exposed no API surface; adding a `snapshot()` read path enabled optional health progress counters without coupling health handlers to tqdm internals.

Frontend health polling should stay active only for non-terminal startup states (`idle` and `running`); once `/health.indexing.state` reaches `ready` or `error`, continuing aggressive polls just creates UI churn without user value.

Unifying CLI output with startup indexing lifecycle is safer as an app-factory callback subscription than as a separate `/health` polling loop, because callback wiring avoids race windows where fast indexing transitions can complete before a poller observes `running`.

Inspector selection affordances are clearer when compare/export entry points are rendered alongside selection count and size in the `Selection` overview, instead of being hidden behind left-sidebar iconography or compare-mode-only metadata sections.

Decoupling export control visibility from `CompareMetadataSection` works best when compare execution stays hook-owned (`useInspectorCompareExport`) and section-local UI only moves between inspector blocks; this avoids contract drift while making disabled-state guidance explicit when compare is closed or selection count is not exactly two.

`Field(min_length=..., max_length=...)` count checks in `ExportComparisonRequest` produce generic list-length errors; explicit field validators are needed to preserve deterministic pair-only `v: 1` messaging for both path and label count violations.

TypeScript widens sanitized label arrays to `string[]`; preserving the pair-only request contract in `ExportComparisonRequest` requires explicit tuple-shape conversion before payload serialization.

Pydantic discriminated unions prepend branch-location prefixes (for example, `1.paths` / `2`) in validation error locations. Route-level tests should assert stable semantic substrings rather than brittle exact-location prefixes when locking `v: 1` and `v: 2` export-contract failures.

Frontend startup health polling already fetched `/health` for indexing/persistence state, but compare-export capability data was not being parsed or normalized. Adding a dedicated capability normalizer (`healthCompareExport`) made backward-compatible fallback (`v: 1` only) explicit and kept `>2` affordance gating deterministic when older servers omit capability fields.

The canonical comparison-export HTTP route is `/export-comparison`; using `/compare/export` returns HTTP 405. Acceptance smoke checks should target `/export-comparison` for both `v: 1` and `v: 2` payload validation.

Headless terminal smoke execution can validate CLI startup plus API contracts end-to-end, but it cannot directly confirm visual browser interaction ergonomics (scrollbar drag conflict and no-jump viewport restoration) without a GUI-driven pass.

A headless Chromium run is now feasible in this environment via Playwright, but local-memory indexing can complete in ~40ms on generated fixtures, which means `Indexing in progress` banner visibility is timing-sensitive and may not be observed even though lifecycle contracts are healthy.

`scripts/gui_smoke_acceptance.py` runs against the packaged frontend under `src/lenslet/frontend/`; source edits in `frontend/src` do not affect acceptance smoke outcomes until the frontend bundle is rebuilt and copied.

Fast local-memory startup can complete indexing before browser paint-sampling observes `Indexing in progress`; deterministic `/health.indexing` lifecycle timestamps (`started_at`/`finished_at`) provide a stronger acceptance proof than timing-sensitive banner visibility alone in this environment.


## Decision Log


1. 2026-02-12, assistant. The plan will update `docs/20260212_issue_tweak_tracking.md` in place instead of creating a new file, because the user explicitly requested conversion of this exact file.
2. 2026-02-12, assistant. No new requirements are invented beyond the existing issue brief; ambiguities are resolved with explicit decision gates and optional branches.
3. 2026-02-12, assistant. Search behavior will be standardized through one shared haystack construction contract used by all relevant storage backends (`memory`, `parquet`, `table`, and `dataset`).
4. 2026-02-12, assistant. Re-entry stability will be designed around a first-class folder session state model (snapshot plus top-anchor), not just selection-based restoration.
5. 2026-02-12, assistant. Sidebar resize behavior will use directional handle geometry and shared CSS tokens so the left pane no longer overlaps scrollbar drag hit areas.
6. 2026-02-12, assistant. Indexing progress will become an explicit backend-to-frontend contract via `/health`, with deterministic CLI messaging and UI state.
7. 2026-02-12, assistant. Inspector actions will become selection-context-first; side-by-side entry remains exact-two, while export behavior has an explicit phase split for pair-only versus optional >2 support.
8. 2026-02-12, assistant. Export >2 support is treated as a gated contract extension and must not be implicitly introduced under the existing `v: 1` request schema.
9. 2026-02-12, assistant. Every sprint will ship a runnable, demoable increment with validation tied to concrete files and commands.
10. 2026-02-12, assistant plus subagent review. Oversized tickets and hidden cross-layer dependencies must be split explicitly, especially for multi-backend search refactors, delayed-hydration viewport guarantees, indexing lifecycle ownership, and export capability negotiation.
11. 2026-02-12, assistant. Shared search behavior is now defined in one storage-level module (`search_text.py`) so backend search fixes land once and are consumed by memory/parquet/table/dataset call sites without duplicated scope logic.
12. 2026-02-12, assistant. `MemoryStorage.search` should include source-like metadata fields only when they exist in metadata, so local-mode defaults stay unchanged while imported metadata sessions retain source-token parity with table/dataset search.
13. 2026-02-12, assistant. API `/search` contract tests for source-token behavior will cover dataset and table app modes directly, using explicit include-source toggles at storage construction time to avoid false confidence from UI-only source visibility flags.
14. 2026-02-12, assistant. Frontend search will canonicalize query + scope-path once and retain placeholder rows only when staying in the same scope path, preserving in-scope typing stability without cross-folder stale-result flashes.
15. 2026-02-12, assistant. Sidebar resizing uses directional handle classes (`left`/`right`) backed by one shared hitbox token; the left handle is offset outside the pane edge while the right handle keeps existing inner-edge placement to avoid introducing unnecessary behavior drift.
16. 2026-02-12, assistant. Sidebar resize clamp math and persistence semantics are now codified as pure helpers inside `useSidebars` so hitbox/layout changes can be validated via targeted unit tests instead of fragile pointer-DOM integration tests.
17. 2026-02-12, assistant. Folder re-entry state is now modeled via a dedicated `useFolderSessionState` contract with pure snapshot/top-anchor upsert and invalidation helpers, keeping lifecycle rules testable without React DOM harnesses.
18. 2026-02-12, assistant. Top-anchor capture is wired at the `AppShell` visible-path callback boundary so presence tracking and session tracking share one viewport event stream and avoid duplicate grid instrumentation.
19. 2026-02-12, assistant. `VirtualGrid` restore semantics are now tokenized as two independent channels (selection and top-anchor) with explicit arbitration, so top-anchor re-entry restoration no longer depends on selection-token triggers and can retry safely as hydration fills item indexes.
20. 2026-02-12, assistant. Cache-first re-entry hydration now seeds `useAppDataScope` from folder-session snapshots and suppresses first-page-only emissions during paged refresh, so users keep stable viewport context until fresh merged snapshots are ready.
21. 2026-02-12, assistant. Delayed-hydration anti-jump acceptance will be enforced in `pagedFolder` contract tests using deferred page resolution plus anchor-path presence assertions before and after merge completion, because that invariant directly captures viewport-stability guarantees without coupling tests to browser scroll timing.
22. 2026-02-12, assistant. T10 invalidates refreshed folder-session subtrees and destination sessions for cross-branch scope transitions only, while preserving ancestor/descendant re-entry sessions; a dedicated `sessionResetToken` now forces stale snapshot drop for same-scope refresh flows.
23. 2026-02-12, assistant. Backend indexing status is now modeled through one app-factory `IndexingLifecycle` contract shared by all `/health` routes, while storage progress remains an optional adapter (`indexing_progress()`) so readiness/error state is deterministic even when no progress counters are available.
24. 2026-02-12, assistant. Frontend indexing polling is lifecycle-gated in `useAppPresenceSync`: poll immediately, continue only while `/health.indexing.state` is non-terminal (`idle` or `running`), and stop on `ready`/`error` so status banners remain informative without becoming persistent noise.
25. 2026-02-12, assistant. `IndexingLifecycle` is now the single producer for startup-indexing transitions consumed by both `/health` payload assembly and CLI startup lines via listener subscriptions (`indexing_listener` + `CliIndexingReporter`), eliminating parallel lifecycle inference paths.
26. 2026-02-12, assistant. T14 surfaces side-by-side and export entry points via a dedicated multi-select inspector action block, but keeps pair-only compare/export execution paths unchanged so contract changes remain isolated to later S5 tickets.
27. 2026-02-12, assistant. T15 moves export form controls into a dedicated `Selection Export` inspector section while keeping compare export request construction/execution in `useInspectorCompareExport`, so visibility is decoupled from compare-metadata rendering without introducing a new API contract.
28. 2026-02-12, assistant. T16 enforces pair-only `v: 1` export behavior through explicit backend request validators and shared frontend pair-only copy/constants, so >2 selection attempts fail with deterministic messaging ahead of any optional `v: 2` capability rollout.
29. 2026-02-12, assistant. T17 introduces a discriminated versioned export request contract (`v: 1` + `v: 2`) at the API boundary and keeps label/path ordering logic version-agnostic in shared server helpers, so multi-path support lands without regressing pair-only behavior or duplicating export execution code paths.
30. 2026-02-13, assistant. T17b treats `>2` export as capability-negotiated behavior only: frontend enables multi-select `v: 2` export only when `/health.compare_export` explicitly advertises `supported_versions` including `2` plus a discoverable `max_paths_v2 > 2`, otherwise it falls back to pair-only `v: 1` UX semantics.
31. 2026-02-13, assistant. Overall acceptance is validated with a dual-layer approach: live CLI/API smoke on generated fixtures plus targeted backend/frontend regression suites mapped to each sprint outcome, rather than rerunning unrelated broad suites.
32. 2026-02-13, assistant. Final closure requires one GUI browser pass for pointer-drag and viewport-no-jump verification; this is tracked explicitly as a blocker instead of inferred from headless API/test success.
33. 2026-02-13, assistant. Acceptance closure now includes a reproducible browser harness (`scripts/gui_smoke_acceptance.py`) that provisions fixtures, runs Lenslet, and checks pointer-lane resize isolation, folder re-entry anchors, path-token search, and inspector multi-select compare/export actions in one command.
34. 2026-02-13, assistant. The browser harness defaults to warning (not hard-failing) on exact re-entry anchor mismatch and missed indexing-banner visibility so the command remains usable as a repeatable acceptance probe while unresolved UX gaps stay explicit and tracked.
35. 2026-02-13, assistant. Folder-session state should persist across sibling scope switches to preserve exact re-entry anchors; stale cache invalidation remains explicit via refresh/subtree invalidation rather than automatic cross-branch purges.
36. 2026-02-13, assistant. Top-anchor capture in `VirtualGrid` should prefer DOM-visible cell ordering (matching user-observed viewport) with virtual-row heuristics as fallback, because overscan-based row anchors can drift from what users actually see.
37. 2026-02-13, assistant. Acceptance harness indexing checks should treat `/health.indexing` lifecycle timestamps as deterministic proof when banner sampling misses fast startup windows, eliminating timing-only false warnings while preserving lifecycle contract rigor.


## Outcomes & Retrospective


This document now functions as an implementation-grade execution plan plus live handover log. It captures foundational redesign choices, dependencies, risks, explicit contracts, and validation pathways while recording completed implementation slices.

Code execution now includes Sprint S1/T1-T4b (shared backend search contract, memory path/source refinements, route-level `/search` source-token regression coverage, and frontend source-token contract wiring with scope-aware placeholder stability tests), Sprint S2/T5-T6 (directional sidebar resize hitbox geometry and explicit resize/persistence contract helpers with regression tests), Sprint S3/T7-T10 (folder session abstraction, `VirtualGrid` top-anchor restore/report contracts, cache-first deterministic re-entry hydration, delayed-hydration anti-jump verification, and refresh/scope-transition invalidation contracts), Sprint S4/T11-T13 (backend lifecycle contract, frontend indexing banner polling/visibility transitions, and CLI lifecycle callback unification), Sprint S5/T14-T17b (inspector multi-select actions, decoupled selection export controls, pair-only `v: 1` lock, versioned `v: 2` export contract, and capability-gated frontend fallback wiring), Sprint S6/T18 (scripted browser acceptance harness in `scripts/gui_smoke_acceptance.py`), and Sprint S7/T18b (exact sibling-folder anchor restoration plus deterministic indexing lifecycle proof integration in acceptance smoke). Sprint S1, Sprint S2, Sprint S3, Sprint S4, Sprint S5, Sprint S6, and Sprint S7 are complete.


## Context and Orientation


The affected frontend orchestration currently spans `frontend/src/app/AppShell.tsx`, `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/app/components/LeftSidebar.tsx`, `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/inspector/sections/OverviewSection.tsx`, and `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`.

The affected backend behavior spans `src/lenslet/server_factory.py`, `src/lenslet/server_models.py`, `src/lenslet/server_routes_common.py`, `src/lenslet/server.py`, `src/lenslet/storage/memory.py`, `src/lenslet/storage/parquet.py`, and `src/lenslet/storage/table_facade.py`.

In this plan, "hydrated snapshot" means a fully merged paginated `FolderIndex` response ready for stable render, and "top-anchor" means the first visible item path used to reconstruct viewport context when re-entering a folder.

In this plan, "search haystack" means the normalized searchable text built from item identity and metadata fields, and "indexing state" means explicit readiness lifecycle (`idle`, `running`, `ready`, or `error`) with optional progress counters.


## Plan of Work


Implementation begins by standardizing contracts that cut across multiple features, then applies targeted UI and lifecycle redesigns. The sequence intentionally addresses backend search parity and resize conflict before tackling re-entry restoration, because scroll restore correctness depends on stable data snapshots and predictable interaction geometry.

Indexing feedback is then implemented as an end-to-end state contract from storage to health endpoint to frontend banner. Inspector compare/export affordances are redesigned last because they depend on final decisions about pair-only versus multi-export API support.

- While implementing each sprint, update the plan document continuously (Progress, Decision Log, Surprises & Discoveries, and relevant sections). After each sprint is complete, add clear handover notes.
- For minor script-level uncertainties (for example, exact file placement), proceed according to the approved plan to maintain momentum. After the sprint, ask for clarifications and then apply follow-up adjustments.

### Sprint Plan


1. Sprint S1: Search Contract Unification (Issue 2).
   Goal: guarantee identical source/path/url search behavior across storage backends.
   Demo outcome: searching by source token returns consistent matches in memory/table/dataset/parquet-backed search paths, and frontend search flows validate the same contract end-to-end.
   Linked tasks: T1, T2, T3a, T3b, T4, T4b.
   Status: completed 2026-02-12 16:15:35Z.
2. Sprint S2: Sidebar Interaction Geometry (Issue 3).
   Goal: eliminate left scrollbar versus resize-handle hitbox overlap without regressing right-pane resize behavior.
   Demo outcome: dragging left panel scrollbar remains reliable with deep folder trees while resize remains responsive.
   Linked tasks: T5, T6.
   Status: completed 2026-02-12 16:25:24Z.
3. Sprint S3: Re-entry Context Stability (Issue 1).
   Goal: restore top-visible context deterministically on folder re-entry with hydration-safe behavior.
   Demo outcome: re-entering a folder preserves top viewport context before and after late hydration merges, with automated delayed-hydration anti-jump proof.
   Linked tasks: T7, T8, T9, T9b, T10.
   Status: completed 2026-02-12 16:52:18Z.
4. Sprint S4: Startup Indexing Visibility (Tweak 1).
   Goal: expose and display deterministic indexing state through CLI, API health, and frontend banners.
   Demo outcome: users can see indexing is running and when first stable readiness is reached, and CLI/API/frontend all consume one shared lifecycle source.
   Linked tasks: T11, T12, T13.
   Status: completed 2026-02-12 17:13:36Z.
5. Sprint S5: Inspector Selection Actions and Export Affordances (Tweak 2).
   Goal: move compare/export actions to inspector selection context and define pair-only versus optional >2 export contract.
   Demo outcome: exact-two side-by-side action is obvious in inspector, export actions are available in multi-select context, >2 behavior is explicit, and capability negotiation prevents unsupported client/server combinations.
   Linked tasks: T14, T15, T16, T17, T17b.
   Status: completed 2026-02-13 02:59:29Z.
6. Sprint S6: Browser Acceptance Harness (Acceptance closure support).
   Goal: codify remaining browser interaction checks into a reproducible one-command smoke harness.
   Demo outcome: a scripted browser pass verifies sidebar drag-lane isolation, folder re-entry anchor behavior, path-token search, and inspector compare/export entry actions on generated fixture data.
   Linked tasks: T18.
   Status: completed 2026-02-13 03:31:23Z.
7. Sprint S7: Warning Closure for Final Acceptance.
   Goal: resolve remaining S6 warning conditions so acceptance criterion 4 can be marked fully satisfied.
   Demo outcome: scripted/browser/manual acceptance captures exact re-entry anchor restoration and an observed indexing-lifecycle banner (or an equivalent deterministic contract proof) without caveats.
   Linked tasks: T18b.
   Status: completed 2026-02-13 03:45:58Z.

### Sprint Handover Notes

Sprint S1 handover (completed 2026-02-12 16:15:35Z):
- Completed: T1-T4b shipped across backend and frontend, including shared backend haystack contract, memory source/path parity fixes, API `/search` source-token contract tests, and frontend canonical search-request + scoped placeholder stability tests.
- Validations run: `pytest -q tests/test_search_text_contract.py tests/test_dataset_http.py tests/test_parquet_ingestion.py`, `pytest -q tests/test_import_contract.py`, `pytest -q tests/test_search_source_contract.py tests/test_search_text_contract.py`, `npm run test -- src/api/__tests__/search.test.ts src/api/__tests__/folders.test.ts`, `npm run test -- src/app/__tests__/appShellSelectors.test.ts`, and `npm run build` (all passed).
- Known risks/follow-ups: frontend search regression coverage currently focuses on the canonical request/placeholder contract helpers; full interaction checks for resize and re-entry behaviors remain in upcoming S2/S3 work.
- First step for Sprint S2: implement T5 by repositioning left sidebar resize-handle geometry away from the native scrollbar lane while keeping right-pane resize behavior unchanged.

Sprint S2 handover (completed 2026-02-12 16:25:24Z):
- Completed: T5-T6 shipped with directional sidebar handles in layout/components and a foundational `useSidebars` contract refactor that isolates drag bounds plus localStorage persistence logic into reusable helpers.
- Validations run: `npm run test -- src/lib/__tests__/breakpoints.test.ts src/app/__tests__/appShellSelectors.test.ts`, `npm run test -- src/app/layout/__tests__/useSidebars.test.ts src/lib/__tests__/breakpoints.test.ts src/app/__tests__/appShellSelectors.test.ts`, and `npm run build` (all passed).
- Known risks/follow-ups: a live manual smoke pass for desktop and coarse-pointer scrollbar-versus-resize interaction remains advisable, though clamp and persistence semantics are now covered by automated tests.
- First step for Sprint S3: implement T7 by adding `useFolderSessionState` and wiring it into `useAppDataScope` and `AppShell`.

Sprint S3 handover (completed 2026-02-12 16:52:18Z):
- Completed: T7-T10 shipped with folder session snapshot/top-anchor contracts, virtual-grid top-anchor restore arbitration, cache-first paged hydration with delayed anti-jump verification, and explicit stale-state invalidation on refresh plus cross-branch scope transitions.
- Validations run: `npm run test -- src/app/hooks/__tests__/useFolderSessionState.test.ts src/app/__tests__/appShellHelpers.test.ts`, `npm run test -- src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/virtualGridSession.test.ts`, and `npm run build` (all passed).
- Known risks/follow-ups: plan-level manual workflow verification for explicit refresh + folder re-entry remains advisable to confirm end-to-end UX behavior under real browser scroll state.
- First step for Sprint S4: implement T11 by introducing backend indexing status lifecycle fields in `/health` with deterministic state transitions and targeted API coverage.

Sprint S4 handover (completed 2026-02-12 17:13:36Z):
- Completed: T11-T13 shipped with shared startup-indexing lifecycle contracts in backend, frontend health/banner lifecycle handling, and CLI lifecycle transition messaging via `IndexingLifecycle` listeners instead of separate lifecycle inference.
- Validations run: `pytest -q tests/test_indexing_health_contract.py tests/test_indexing_status_contract.py`, `npm run test -- src/app/hooks/__tests__/healthIndexing.test.ts src/app/components/__tests__/StatusBar.test.tsx src/app/__tests__/appShellSelectors.test.ts`, and `npm run build` (all passed).
- Known risks/follow-ups: CLI lifecycle messages now emit from app-factory indexing transitions; a manual long-running local folder smoke run is still advisable to observe full terminal output timing under real startup load.
- First step for Sprint S5: implement T14 by redesigning inspector selection actions so side-by-side and export affordances are presented directly in multi-select inspector context.

Sprint S5 handover (completed 2026-02-13 02:59:29Z):
- Completed: T14-T17b shipped with inspector-side selection actions, decoupled selection export controls, pair-only `v: 1` lock, versioned `v: 2` multi-path export API, and capability-negotiated frontend gating/fallback via `/health.compare_export`.
- Validations run: `pytest -q tests/test_indexing_health_contract.py tests/test_compare_export_endpoint.py`, `npm run test -- src/app/hooks/__tests__/healthCompareExport.test.ts src/app/hooks/__tests__/healthIndexing.test.ts src/features/inspector/sections/__tests__/metadataSections.test.tsx src/features/inspector/__tests__/exportComparison.test.tsx src/api/__tests__/client.exportComparison.test.ts`, and `npm run build` (all passed).
- Known risks/follow-ups: acceptance smoke is now partially closed via terminal-driven CLI/API checks and targeted automated suites, but GUI browser interaction confirmation is still required for pointer/scroll behaviors (left scrollbar drag isolation and visible no-jump folder re-entry).
- First step for Sprint S6: implement a reproducible browser smoke harness to replace ad-hoc manual GUI verification.

Sprint S6 handover (completed 2026-02-13 03:31:23Z):
- Completed: T18 shipped by adding `scripts/gui_smoke_acceptance.py` as a one-command browser acceptance harness that creates local fixtures, launches Lenslet, and validates sidebar drag-lane behavior, folder re-entry anchor behavior, path-token search, and inspector multi-select compare/export entry actions.
- Validations run: `python scripts/gui_smoke_acceptance.py --output-json /tmp/lenslet-gui-smoke-result.json`, `python scripts/gui_smoke_acceptance.py --strict-reentry-anchor --output-json /tmp/lenslet-gui-smoke-strict-result.json` (expected strict-mode failure on re-entry anchor mismatch), and `python -m py_compile scripts/gui_smoke_acceptance.py`.
- Known risks/follow-ups: the harness currently reports two warnings in this environment: startup indexing often reaches `ready` before banner sampling, and exact sibling-folder re-entry top-anchor restoration is not observed (`anchor_reentry_exact=false`).
- First step for Sprint S7: investigate and resolve exact re-entry anchor drift in browser interaction flow, then determine a deterministic indexing-banner visibility proof path (or explicit contract-level equivalent) for final acceptance closure.

Sprint S7 handover (completed 2026-02-13 03:45:58Z):
- Completed: T18b shipped by correcting exact sibling-folder re-entry restoration (`VirtualGrid` now captures top-anchor from DOM-visible cells with virtual fallback and `AppShell` no longer purges destination folder-session state on scope switches) and by hardening the browser harness with deterministic `/health.indexing` lifecycle proof fallback when banner visibility sampling is too fast.
- Validations run: `npm run test -- src/features/browse/model/__tests__/virtualGridSession.test.ts`, `npm run build && cp -r dist/* ../src/lenslet/frontend/`, `python -m py_compile scripts/gui_smoke_acceptance.py`, `python scripts/gui_smoke_acceptance.py --output-json /tmp/lenslet-gui-smoke-result-iter22.json`, and `python scripts/gui_smoke_acceptance.py --strict-reentry-anchor --output-json /tmp/lenslet-gui-smoke-strict-result-iter22e.json` (all passed; `warnings=[]`, `anchor_reentry_exact=true`, `indexing_lifecycle_proof=true`).
- Known risks/follow-ups: default smoke now relies on lifecycle timestamp proof when startup indexing is too fast for visible banner sampling; if product requirements later mandate visually observed banner display on tiny fixtures, add a deterministic indexing delay fixture mode to the harness.
- First step for the next sprint: none; planned sprint/ticket scope is complete and acceptance criteria are satisfied.


## Concrete Steps


All commands are run from the repository root unless another directory is explicitly listed.

    Working directory: /home/ubuntu/dev/lenslet

    rg -n "search\(|haystack|include_source_in_search" src/lenslet/storage
    rg -n "restoreToSelectionToken|onVisiblePathsChange|hydrateFolderPages" frontend/src
    rg -n "sidebar-resize-handle|onResizeLeft|onResizeRight" frontend/src
    rg -n "ExportComparisonRequest|paths: \[string, string\]|onComparisonExport" src/lenslet frontend/src
    rg -n "getHealth\(|HealthResponse|/health" src/lenslet frontend/src
    python scripts/gui_smoke_acceptance.py --output-json /tmp/lenslet-gui-smoke-result.json

Validation command skeleton by domain:

    Working directory: /home/ubuntu/dev/lenslet

    pytest -q tests/test_folder_pagination.py tests/test_parquet_ingestion.py tests/test_compare_export_endpoint.py tests/test_import_contract.py

    Working directory: /home/ubuntu/dev/lenslet/frontend

    npm run test -- src/features/browse/model/__tests__/pagedFolder.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/sections/__tests__/metadataSections.test.tsx src/api/__tests__/folders.test.ts
    npm run build

### Task/Ticket Details


1. T1: Create a shared search text contract module.
   Goal: define one canonical haystack builder and scope matcher for all storage backends.
   Affected files and areas: add `src/lenslet/storage/search_text.py`; wire into `src/lenslet/storage/memory.py`, `src/lenslet/storage/parquet.py`, `src/lenslet/storage/table_facade.py`, and `src/lenslet/storage/dataset.py`.
   Validation: add backend unit tests that assert identical search matching for name, logical path, source, URL, tags, and notes across backends.
   Status: completed 2026-02-12 15:58:08Z (iteration 1) with validation in `tests/test_search_text_contract.py`.
2. T2: Make memory-backed search include logical path and optional source-like fields consistently.
   Goal: ensure local filesystem mode can match path tokens, not only basename and metadata.
   Affected files and areas: `src/lenslet/storage/memory.py`.
   Validation: add tests covering partial path token query within scope and outside scope.
   Status: completed 2026-02-12 16:05:56Z (iteration 2) with validation in `tests/test_search_text_contract.py`.
3. T3a: Bring parquet and table search paths to the shared contract and close drift.
   Goal: remove duplicated haystack assembly in table/parquet flows while preserving scoped search semantics.
   Affected files and areas: `src/lenslet/storage/parquet.py`, `src/lenslet/storage/table_facade.py`.
   Validation: targeted backend tests pass for table/parquet source/path/url token matching.
   Status: completed 2026-02-12 15:58:08Z (iteration 1) with shared-contract wiring plus table/parquet parity assertions in `tests/test_search_text_contract.py`.
4. T3b: Bring dataset search to the shared contract with shared fixture coverage.
   Goal: keep dataset mode behavior aligned with table/memory semantics while preserving remote-source handling.
   Affected files and areas: `src/lenslet/storage/dataset.py`, shared search fixtures/tests under `tests/`.
   Validation: dataset search parity tests pass against shared fixtures.
   Status: completed 2026-02-12 15:58:08Z (iteration 1) with dataset shared-contract wiring plus dataset parity assertions in `tests/test_search_text_contract.py`.
5. T4: Add API-level regression tests for source-token search.
   Goal: lock end-to-end behavior from `/search` route to frontend expectations.
   Affected files and areas: add `tests/test_search_source_contract.py`.
   Validation: `pytest -q tests/test_search_source_contract.py` passes with both positive and negative cases.
   Status: completed 2026-02-12 16:10:30Z (iteration 3) with API route coverage in `tests/test_search_source_contract.py`.
6. T4b: Wire frontend search usage to the canonical backend contract and add UI regression coverage.
   Goal: ensure `useSearch`/search UI behavior reflects the unified backend search semantics.
   Affected files and areas: `frontend/src/shared/api/search.ts`, `frontend/src/app/hooks/useAppDataScope.ts`, and new frontend regression tests.
   Validation: frontend test simulates source-token query and verifies stable result rendering behavior.
   Status: completed 2026-02-12 16:15:35Z (iteration 4) with canonical query/path normalization and scope-aware placeholder regression coverage in `frontend/src/api/__tests__/search.test.ts`.
7. T5: Redesign sidebar resize hitboxes with directional geometry.
   Goal: move left handle interaction outward so it no longer competes with native scrollbar hit area.
   Affected files and areas: `frontend/src/styles.css`, `frontend/src/app/components/LeftSidebar.tsx`, `frontend/src/features/inspector/Inspector.tsx`.
   Validation: manual interaction validation on desktop and coarse-pointer layouts plus `npm run build`.
   Status: completed 2026-02-12 16:19:10Z (iteration 5) with directional handle classes and shared hitbox tokens; manual interaction verification is carried by T6.
8. T6: Keep resize behavior stable while changing handle geometry.
   Goal: preserve width clamping and persistence semantics while altering handle placement.
   Affected files and areas: `frontend/src/app/layout/useSidebars.ts` (only if needed), relevant handle class usage in component files.
   Validation: verify left/right resize constraints still hold and localStorage width persistence still works.
   Status: completed 2026-02-12 16:25:24Z (iteration 6) with contract helper extraction in `frontend/src/app/layout/useSidebars.ts` and regression coverage in `frontend/src/app/layout/__tests__/useSidebars.test.ts`.
9. T7: Introduce folder session state abstraction for re-entry context.
   Goal: persist per-folder hydrated snapshot metadata and top-anchor path as first-class UI state.
   Affected files and areas: add `frontend/src/app/hooks/useFolderSessionState.ts`; integrate with `frontend/src/app/hooks/useAppDataScope.ts` and `frontend/src/app/AppShell.tsx`.
   Validation: unit tests for state lifecycle and invalidation triggers.
   Status: completed 2026-02-12 16:30:49Z (iteration 7) with new session contract helpers in `frontend/src/app/hooks/useFolderSessionState.ts`, wiring in `frontend/src/app/hooks/useAppDataScope.ts` + `frontend/src/app/AppShell.tsx`, and regression coverage in `frontend/src/app/hooks/__tests__/useFolderSessionState.test.ts`.
10. T8: Extend VirtualGrid with top-anchor restore/report contracts.
   Goal: decouple restore-from-selection from restore-from-top-visible-anchor.
   Affected files and areas: `frontend/src/features/browse/components/VirtualGrid.tsx` and related prop typing consumers.
   Validation: add focused tests for anchor emission and restoration behavior; verify no regressions in keyboard navigation.
   Status: completed 2026-02-12 16:38:14Z (iteration 8) with tokenized top-anchor restore/report contracts in `frontend/src/features/browse/components/VirtualGrid.tsx` + `frontend/src/features/browse/model/virtualGridSession.ts`, AppShell wiring in `frontend/src/app/AppShell.tsx`, and regression coverage in `frontend/src/features/browse/model/__tests__/virtualGridSession.test.ts` plus `frontend/src/features/browse/hooks/__tests__/useKeyboardNav.test.ts`.
11. T9: Make hydration lifecycle deterministic on re-entry.
   Goal: render cached hydrated snapshot immediately, then reconcile with fresh hydration without viewport jumps.
   Affected files and areas: `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/features/browse/model/pagedFolder.ts`.
   Validation: add tests for two-phase hydration (`cached snapshot` then `fresh merge`) and stable ordering.
   Status: completed 2026-02-12 16:43:15Z (iteration 9) with cache-first snapshot seeding in `frontend/src/app/hooks/useAppDataScope.ts`, first-page emission gating in `frontend/src/features/browse/model/pagedFolder.ts`, AppShell snapshot getter wiring, and regression coverage in `frontend/src/features/browse/model/__tests__/pagedFolder.test.ts`.
12. T9b: Add deterministic delayed-hydration anti-jump verification.
   Goal: prove re-entry scroll stability under delayed page hydration and late merge completion.
   Affected files and areas: new automated test under `frontend/src/features/browse` or `frontend/src/app/__tests__/` with mocked delayed hydration.
   Validation: automated test asserts viewport anchor is stable before and after late hydration completion.
   Status: completed 2026-02-12 16:46:55Z (iteration 10) with deferred hydration anti-jump regression coverage in `frontend/src/features/browse/model/__tests__/pagedFolder.test.ts`.
13. T10: Invalidate snapshot and anchor on explicit refresh and incompatible scope transitions.
   Goal: guarantee stale state is dropped when user requests refresh or changes scope semantics.
   Affected files and areas: `frontend/src/app/AppShell.tsx`, `frontend/src/app/hooks/useAppDataScope.ts`, new folder-session hook.
   Validation: integration-level manual workflow test with `refresh` and folder re-entry.
   Status: completed 2026-02-12 16:52:18Z (iteration 11) with refresh-driven folder-session subtree invalidation, hierarchical scope-transition compatibility guards, and `sessionResetToken` cache-reset wiring across `AppShell` + `useAppDataScope` plus regression coverage in `frontend/src/app/hooks/__tests__/useFolderSessionState.test.ts`.
14. T11: Add backend indexing status contract.
   Goal: expose warm-index lifecycle through health payload with deterministic states and optional progress counters.
   Affected files and areas: `src/lenslet/server_factory.py`, storage progress plumbing in `src/lenslet/storage/memory.py` and table-related modules as needed.
   Validation: new backend test asserts `/health` includes indexing state transitions.
   Status: completed 2026-02-12 16:53:47Z (iteration 12) with shared lifecycle helpers in `src/lenslet/indexing_status.py`, `/health` payload wiring across app modes in `src/lenslet/server_factory.py`, progress snapshots in storage backends, and regression coverage in `tests/test_indexing_health_contract.py`.
15. T12: Add frontend indexing banner and polling lifecycle.
   Goal: surface indexing progress until ready and avoid noisy persistent banners.
   Affected files and areas: `frontend/src/lib/types.ts`, `frontend/src/api/client.ts`, `frontend/src/app/hooks/useAppPresenceSync.ts` or a dedicated health hook, and `frontend/src/app/components/StatusBar.tsx`.
   Validation: frontend tests for banner visibility transitions plus manual run on large sample tree.
   Status: completed 2026-02-12 17:04:34Z (iteration 13) with indexing payload typing in `frontend/src/lib/types.ts`, lifecycle-gated health polling in `frontend/src/app/hooks/useAppPresenceSync.ts`, status banner wiring in `frontend/src/app/components/StatusBar.tsx` + `frontend/src/app/AppShell.tsx`, and regression coverage in `frontend/src/app/components/__tests__/StatusBar.test.tsx`.
16. T13: Unify indexing lifecycle ownership across health, CLI, and frontend consumers.
   Goal: prevent drift by ensuring one canonical indexing lifecycle source powers `/health`, frontend banner state, and CLI messaging.
   Affected files and areas: `src/lenslet/server_factory.py`, `src/lenslet/cli.py`, indexing status helper module if added, and frontend health consumer hook.
   Validation: tests and transcript checks confirm all surfaces report coherent state transitions including long-running and failed indexing scenarios.
   Status: completed 2026-02-12 17:13:36Z (iteration 14) with lifecycle listener support in `src/lenslet/indexing_status.py`, app-factory listener wiring in `src/lenslet/server_factory.py`, CLI reporter wiring in `src/lenslet/cli.py`, shared frontend helper extraction in `frontend/src/app/hooks/healthIndexing.ts`, and regression coverage in `tests/test_indexing_status_contract.py`, `tests/test_indexing_health_contract.py`, and `frontend/src/app/hooks/__tests__/healthIndexing.test.ts`.
17. T14: Redesign inspector selection actions around multi-select context.
   Goal: place side-by-side and export actions in inspector where selection context is visible.
   Affected files and areas: `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/inspector/sections/OverviewSection.tsx`, new section component(s) under `frontend/src/features/inspector/sections/`.
   Validation: section tests assert exact-two enablement and >2 disabled reason messaging.
   Status: completed 2026-02-12 17:20:26Z (iteration 15) with `SelectionActionsSection` wiring in `frontend/src/features/inspector/sections/SelectionActionsSection.tsx` + `frontend/src/features/inspector/sections/OverviewSection.tsx`, compare-open callback threading via `frontend/src/features/inspector/Inspector.tsx` and `frontend/src/app/AppShell.tsx`, and section regression coverage in `frontend/src/features/inspector/sections/__tests__/metadataSections.test.tsx`.
18. T15: Move export controls out of compare metadata-only section.
   Goal: decouple export affordance visibility from compare metadata section visibility.
   Affected files and areas: `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`, new selection export section component, inspector workflow hook wiring.
   Validation: existing export helper tests remain green and new section tests verify control visibility in multi-select mode.
   Status: completed 2026-02-12 17:26:03Z (iteration 16) with new `SelectionExportSection` wiring in `frontend/src/features/inspector/sections/SelectionExportSection.tsx` + `frontend/src/features/inspector/sections/OverviewSection.tsx`, compare export hook threading via `frontend/src/features/inspector/Inspector.tsx`, export UI removal from `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`, and section regression coverage updates in `frontend/src/features/inspector/sections/__tests__/metadataSections.test.tsx`.
19. T16: Phase A contract lock for pair-only export.
   Goal: preserve `v: 1` pair-only API while providing clear UX messaging when >2 items are selected.
   Affected files and areas: `src/lenslet/server_models.py`, `frontend/src/lib/types.ts`, inspector export helper messaging.
   Validation: backend and frontend tests enforce max-length two for `v: 1` with explicit error messaging.
   Status: completed 2026-02-12 17:32:48Z (iteration 17) with explicit `ExportComparisonRequest` pair-only validators in `src/lenslet/server_models.py`, frontend pair-only request typing + messaging alignment in `frontend/src/lib/types.ts`, `frontend/src/features/inspector/exportComparison.ts`, `frontend/src/features/inspector/hooks/useInspectorCompareExport.ts`, and `frontend/src/features/inspector/sections/SelectionExportSection.tsx`, plus regression coverage in `tests/test_compare_export_endpoint.py`, `frontend/src/features/inspector/__tests__/exportComparison.test.tsx`, and `frontend/src/features/inspector/sections/__tests__/metadataSections.test.tsx`.
20. T17: Optional Phase B for >2 export API (gated).
   Goal: if approved, introduce a versioned API contract for >2 paths with deterministic label mapping and output metadata.
   Affected files and areas: `src/lenslet/server_models.py`, `src/lenslet/server_routes_common.py`, `src/lenslet/server.py`, `frontend/src/lib/types.ts`, `frontend/src/features/inspector/exportComparison.ts`, related tests.
   Validation: new `v: 2` contract tests for 2..N paths and backward compatibility checks for `v: 1` clients.
   Status: completed 2026-02-12 17:39:41Z (iteration 18) with discriminated `v: 1`/`v: 2` request validation in `src/lenslet/server_models.py`, shared adapter route parsing in `src/lenslet/server_routes_common.py`, N-path label/path resolution updates in `src/lenslet/server.py`, frontend union request typing + `buildExportComparisonPayloadV2` support in `frontend/src/lib/types.ts` and `frontend/src/features/inspector/exportComparison.ts`, and regression coverage in `tests/test_compare_export_endpoint.py`, `frontend/src/features/inspector/__tests__/exportComparison.test.tsx`, and `frontend/src/api/__tests__/client.exportComparison.test.ts`.
21. T17b: Add explicit export capability negotiation and client fallback behavior.
   Goal: ensure clients only offer >2 export when server capability is discoverable and supported.
   Affected files and areas: `/health` capability extension in backend, `frontend/src/lib/types.ts`, and inspector export action gating in frontend.
   Validation: tests verify client hides or disables >2 export when capability is absent and still allows `v: 1` pair export.
   Status: completed 2026-02-13 02:59:29Z (iteration 19) with frontend `/health.compare_export` normalization in `frontend/src/app/hooks/healthCompareExport.ts`, capability polling/state wiring in `frontend/src/app/hooks/useAppPresenceSync.ts` + `frontend/src/app/AppShell.tsx`, capability-gated inspector export execution/UI in `frontend/src/features/inspector/hooks/useInspectorCompareExport.ts` + `frontend/src/features/inspector/sections/SelectionExportSection.tsx`, and capability regression coverage in `frontend/src/app/hooks/__tests__/healthCompareExport.test.ts`, `frontend/src/features/inspector/sections/__tests__/metadataSections.test.tsx`, and `tests/test_indexing_health_contract.py`.
22. T18: Add a reproducible browser acceptance smoke harness for the remaining GUI-only checks.
   Goal: replace ad-hoc manual acceptance with a deterministic scripted browser pass that can run in CI-like terminal environments.
   Affected files and areas: add `scripts/gui_smoke_acceptance.py`.
   Validation: `python scripts/gui_smoke_acceptance.py --output-json /tmp/lenslet-gui-smoke-result.json` and `python -m py_compile scripts/gui_smoke_acceptance.py`.
   Status: completed 2026-02-13 03:31:23Z (iteration 21) with scripted checks for sidebar drag-lane resize isolation, folder re-entry anchor behavior, path-token search, and inspector compare/export action entry points.
23. T18b: Resolve exact re-entry anchor restoration drift and deterministic indexing-banner observability for final acceptance closure.
   Goal: move S6 scripted-browser warnings to green so criterion 4 can be marked fully satisfied.
   Affected files and areas: `frontend/src/app/hooks/useFolderSessionState.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/features/browse/components/VirtualGrid.tsx`, and/or acceptance harness instrumentation in `scripts/gui_smoke_acceptance.py` as needed.
   Validation: rerun `python scripts/gui_smoke_acceptance.py --strict-reentry-anchor --output-json ...` and confirm warnings list is empty (or only explicitly accepted non-product caveats).
   Status: completed 2026-02-13 03:45:58Z (iteration 22) with DOM-visible top-anchor capture/fallback updates in `frontend/src/features/browse/components/VirtualGrid.tsx` + `frontend/src/features/browse/model/virtualGridSession.ts`, scope-switch session-preservation fix in `frontend/src/app/AppShell.tsx`, acceptance-harness lifecycle-proof hardening in `scripts/gui_smoke_acceptance.py`, and passing strict/default smoke reports.


## Validation and Acceptance


Sprint-level acceptance criteria:

1. S1 passes when source/path/url token queries return the same logical matches across memory, parquet, dataset, and table search code paths, and frontend search behavior is validated against this contract.
2. S2 passes when left scrollbar dragging no longer triggers resize during normal scrollbar interaction and existing resize behavior remains intact on both side panels.
3. S3 passes when re-entering a folder restores the prior top-visible context immediately and does not jump after full hydration completes, including delayed-hydration automated verification.
4. S4 passes when `/health` reports indexing lifecycle state, CLI prints deterministic indexing lifecycle messages from the same lifecycle source, and frontend shows an indexing banner until ready.
5. S5 passes when inspector exposes side-by-side for exactly two selections, export controls are available in multi-select context, and >2 behavior is explicit with capability-gated fallback.

Overall acceptance criteria:

1. `pytest` targeted backend suites for search, health, and export all pass.
2. `npm run test` targeted frontend suites for browse hydration and inspector actions all pass.
3. `npm run build` succeeds for frontend.
4. Manual smoke run with `lenslet /path/to/images --reload --port 7070` demonstrates all five issue/tweak outcomes end-to-end.

Status snapshot (2026-02-13 03:45:58Z):
- Criteria 1-3: satisfied (targeted backend/frontend suites and frontend build remain passing).
- Criterion 4: satisfied via scripted browser acceptance with both default and strict harness modes passing (`anchor_reentry_exact=true`) and deterministic indexing lifecycle proof enabled when banner sampling misses fast startup windows.


## Idempotence and Recovery


Each ticket is designed to be committable and reversible without cross-ticket hidden state. Search unification and indexing status work should be landed behind additive interfaces first, then migrated call-sites, then dead-code cleanup only after parity tests pass.

For recovery, if a sprint introduces behavioral uncertainty, revert only the sprint-specific commits and keep prior validated sprints intact. Do not delete baseline tests when failures appear; fix forward or isolate behind a clearly documented compatibility shim.

If optional Phase B (>2 export API) is started and blocked, keep Phase A pair-only behavior as the stable default and ship S5 without changing the `v: 1` contract.


## Artifacts and Notes


Expected health payload extension example:

    {
      "ok": true,
      "mode": "memory",
      "indexing": {
        "state": "running",
        "scope": "/",
        "done": 340,
        "total": 1200,
        "started_at": "2026-02-12T14:40:00Z"
      }
    }

Expected re-entry state artifact example:

    FolderSessionState[path="/shots"] = {
      snapshotGeneratedAt: "2026-02-12T14:41:03Z",
      topAnchorPath: "/shots/base_spine_001086.jpg",
      updatedAtMs: 1770916863000
    }

Expected inspector behavior transcript example:

    Selected 2 items -> Overview shows "Side by side view" enabled.
    Selected 3 items -> Overview shows "Side by side view" disabled with reason.
    Multi-select active -> "Selection Export" section visible in inspector.


## Interfaces and Dependencies


Shared backend search interface contract:

    def build_search_haystack(
        *,
        logical_path: str,
        name: str,
        tags: list[str],
        notes: str,
        source: str | None,
        url: str | None,
        include_source_fields: bool,
    ) -> str: ...

    def path_in_scope(*, logical_path: str, scope_norm: str) -> bool: ...

Frontend folder session contract:

    type FolderSessionState = {
      path: string
      snapshot: FolderIndex
      snapshotGeneratedAt: string | null
      topAnchorPath: string | null
      updatedAtMs: number
    }

    type VirtualGridProps = {
      onTopAnchorChange?: (path: string | null) => void
      restoreTopAnchorPath?: string | null
    }

Health/indexing contract extension:

    type HealthResponse = {
      ok: boolean
      compare_export?: {
        supported_versions?: number[]
        max_paths_v2?: number | null
      }
      indexing?: {
        state: 'idle' | 'running' | 'ready' | 'error'
        scope?: string
        done?: number
        total?: number
        started_at?: string
        finished_at?: string
        error?: string
      }
    }

Export API contract gate:

    class ExportComparisonRequestV1(BaseModel):
        v: Literal[1]
        paths: list[str] = Field(min_length=2, max_length=2)

    class ExportComparisonRequestV2(BaseModel):
        v: Literal[2]
        paths: list[str] = Field(min_length=2, max_length=MAX_EXPORT_PATHS)

Dependencies and tools remain unchanged from current stack: FastAPI, Pydantic, React, Vitest, pytest, and existing Lenslet storage abstractions.


Revision note (2026-02-12): Converted this file from issue tracking notes into the full execution-plan format, expanded each proposed change into foundational architecture tasks, and incorporated mandatory subagent review feedback by splitting oversized tickets and adding explicit validation/dependency gates.
