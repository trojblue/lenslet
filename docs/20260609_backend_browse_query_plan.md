# Backend Browse Query Filtering Plan


## Outcome + Scope Lock


After implementation, Lenslet users can apply categorical, metric, star, text, date, and dimension filters and the gallery will show the correct result window even when matching rows are not present in the first unfiltered page. Pagination is a transport detail only. It must not decide filter truth, sort order, filtered counts, facet options, or whether a view is empty.

The locked scope is backend-owned browse query semantics. The frontend may hold UI state, serialize requests, render returned windows, and handle non-authoritative UI presentation, but it owns no authoritative filtering, sorting, counting, search, facet population, or pagination semantics for normal folder/table browse views. The server must evaluate the requested browse view over the full folder/table scope and return a filtered, sorted result window plus authoritative totals.

The implementation defaults are locked by this plan. Do not pause the run for human decision-making on the choices below. If an implementation detail is minor and not behavior-changing, choose the smallest repo-consistent option and record it in the Progress Log. If a requested behavior would exceed this plan, do not implement that expansion during this run; use the locked fallback behavior described here.

Goals are to add a typed backend browse-query contract, implement exact backend parity for current non-derived browse filters and sort specs, make table/parquet storage execute row-level query windows without materializing every candidate item payload, keep facets backend-owned and independent of loaded gallery pages, and hard-cut the frontend folder/table browse path away from local page filtering.

Non-goals are a generic query language, SQL or Arrow predicate pushdown, a new search engine, filtered folder-tree aggregation, export-all-filtered-results, thumbnail/media delivery changes, provider-specific behavior, broad frontend redesign, full filtered facet counts, query-result caching, and backend derived metric evaluation. Similarity mode remains a separate bounded top-K workflow unless explicitly brought into a later backend query scope.

Locked behavior changes are the hard cutover from page-local frontend filtering to backend browse queries, a new POST browse-query endpoint, request/response schema changes needed for that cutover, removal of authoritative uses of frontend `applyFilters` and `applySort` for normal folder/table browse, deterministic hash-based backend random sort, a smaller backend query page size around 1000, and unsupported/too-large responses for large non-table recursive filtering rather than materializing everything.

Locked v1 fallback behavior is fail-closed for unsupported query-authoritative features. Derived metric filters or sorts in normal folder/table browse show a visible unavailable warning, do not send a misleading query that silently omits the clause, and do not locally filter loaded items. Large non-table recursive filtering uses a bounded fallback only; if the scope is beyond the existing hard limit, return a clear unsupported or too-large response. Metrics may stop showing per-value filtered counts unless the backend returns authoritative counts for them.


## Context


Active working docs live directly under `docs/`; `docs/README.md` says completed dated plans, reviews, audits, and stale notes move to `docs/agents_archive/`. No current `PLANS.md` convention was found, so this file follows the repository `AGENTS.md` instructions and the active-docs convention.

The current failure path is in the browse data flow. `frontend/src/app/hooks/useAppDataScope.ts` loads `/folders?recursive=1&offset=0&limit=5000`, derives `poolItems` from that finite page, and applies `applyFilters` and `applySort` locally. `frontend/src/features/browse/components/VirtualGrid.tsx` requests more rows only when rendered `items` approaches the end. If a categorical filter matches rows outside the first unfiltered page, the rendered array can be zero and the grid never asks for more.

Metrics facets already use backend data through `/folders/facets`, and table storage can count rows in scope efficiently. That is why the Metrics panel can correctly show thousands of `source_column = v0603_ema14k_image_url` rows while the gallery renders zero. The root fix must change the browse query path directly; a grid load-more workaround would still leave query truth coupled to hydration order.

Semantic decisions for this plan are locked. Backend query owns normal folder/table browse filters, sort, text search, counts, facet populations, and result windows. Query order is scope, then text search if present, then filters, then sort, then offset and limit. Folder navigation entries remain raw navigation entries unaffected by item filters. `scope_total` means raw scoped item count. `filtered_total` means rows after active text search and filters. Loaded window length is never a total.

The backend evaluator must intentionally match the current frontend filter and sort contract in `frontend/src/features/browse/model/filters.ts` and `frontend/src/features/browse/model/sorters.ts`, including edge cases that may look odd. Missing star is treated as `0`. Empty filter values normalize away. Missing notes return false for both `notesContains` and `notesNotContains`. URL filters use `item.source ?? item.url ?? ""`. Date-only upper bounds expand to the end of the day. Width and height filters reject missing, non-finite, and non-positive values. Metric filters reject missing, null, and non-finite values. Metric sorts put missing or non-finite values after valid values in both directions, use name as the first tie-breaker, and the backend must add a final stable path or row-id tie-breaker for pagination.

Derived metrics are intentionally not hidden in this scope. Current derived metric evaluation is frontend-side. Because the corrected requirement is that nothing query-authoritative is frontend-owned, derived metric filters/sorts are unavailable in normal backend browse v1. Similarity mode may continue using local derived metric evaluation only because it is a bounded top-K workflow outside this browse-query contract.

The plan review in `docs/20260609_backend_browse_query_plan_review.md` was checked on 2026-06-09 and incorporated into this revision. The review accepted the direction but required tighter contracts around exact filter parity, stable ordering, row-id table execution, sidecar invalidation, search composition, facet count semantics, response naming, bounded non-table fallback, separated facets, and storage-neutral internal models. It also stated that no major human decision is needed; this plan now asserts those defaults.


## Interfaces and Dependencies


Add a narrow backend browse-view contract:

    POST /folders/query

The request includes canonical folder path, recursive flag, offset, limit, filter AST, sort spec, optional text query, and optional random seed for deterministic random ordering. It does not accept an arbitrary query language or loose multi-key dictionaries. Use typed discriminated filter clauses and explicit validators so malformed or ambiguous clauses fail at the API boundary instead of being interpreted differently by route, storage, and frontend code.

The query response is a separate model from the existing `BrowseFolderPayload`. Do not reuse `total_items` on the new endpoint. The response uses unambiguous count names:

    {
      "path": "/",
      "generated_at": "...",
      "generation_token": "...",
      "request_token": "...",
      "scope_total": 6,
      "filtered_total": 2,
      "offset": 0,
      "limit": 2,
      "items": [...],
      "folders": [...],
      "metric_keys": [...],
      "categorical_keys": [...]
    }

`request_token` may be a canonical query echo or generated token; it exists so the frontend can reject stale responses after rapid path, filter, sort, search, or seed changes. `folders` are raw navigation entries. `items` is only the returned filtered and sorted window. `scope_total`, `filtered_total`, and `items.length` must remain structurally distinct.

Keep facet population on the dedicated facet path for v1 instead of returning full histograms and categorical populations on every browse query. `/folders/query` returns the result window, totals, folders, and keys. `/folders/facets` remains the source for raw scoped metric histograms and categorical value populations. Per-value filtered facet counts are omitted in v1 unless they are made authoritative by the backend; the frontend must not substitute loaded-window counts as truth.

Define storage-neutral internal query models below the web layer, for example in `src/lenslet/browse/query.py` or `src/lenslet/storage/base.py`. Pydantic request/response models stay in `src/lenslet/web/models.py`. The route adapts web models into storage-neutral `BrowseQuerySpec` objects, storage returns storage-neutral `BrowseQueryResult` objects, and the route converts those into the public API response. `TableStorage` must not import web Pydantic models.

Storage gains a narrow optional capability such as `query_browse_scope(...)` or `browse_query_window(...)`. The name should stay tied to browse view windows, not generic predicates. Table storage implements it over row ids: determine scoped rows, evaluate text and filters over row-level fields, compute `filtered_total`, sort matching row ids with a stable final tie-breaker, slice the requested window, and materialize only that returned window.

Sidecar-dependent query fields must be row-level lookups, not item materialization. Add or reuse helpers to resolve canonical path for a row id, read sidecar star/notes state without creating or mutating state, and evaluate star/notes filters and search text from that state. Only call item materialization after filtering, sorting, and slicing.

The new query endpoint initially bypasses the existing recursive browse cache. The current cache is keyed around scope, scan sort, and generation; reusing it without canonical filter, sort, text query, random seed, and sidecar generation keys would risk wrong windows. Query caching is deferred until correctness and real scenario validation pass.

Normal folder/table browse search is folded into `/folders/query`. The frontend must stop using `/search` plus local filtering/sorting for normal browse. The backend query evaluator should reuse or port the existing table search behavior over path, name, source/url, and sidecar text so text search plus categorical/metric filters is evaluated over the full scope before offset/limit.

Frontend API code adds typed request/response models and a dedicated backend browse query hook, preferably shaped like an infinite query. Query keys include every variable the request depends on: path, recursive flag, canonical filters, canonical sort, text query, random seed, page size, and unsupported derived state. Page requests use the same canonical query plus the next offset. The query function must consume or bridge TanStack Query's abort signal so stale or inactive requests cannot replace newer view state.

Existing filter UI helpers may remain for building and displaying filter state, chips, request serialization, and tests. `applyFilters` and `applySort` may remain only for non-authoritative utility use and explicitly out-of-scope similarity top-K mode. They must not decide membership or order for normal folder/table browse.


## Plan of Work


While implementing each sprint, update this plan document continuously, especially Progress Log and Artifacts and Handoff. After each sprint is complete, add clear handoff notes describing changed files, validation evidence, and remaining risks. For minor script-level uncertainties, such as exact test file placement, proceed according to this plan to maintain momentum and record the choice after the sprint.

For any ticket with non-trivial code changes, the implementing agent must use the `better-code` skill before and during implementation. Each substantive ticket must follow Karpathy-style execution guardrails: state material assumptions and ambiguous interpretations before coding, choose the smallest non-speculative solution, touch only lines tied to the request, invariants, or verification, remove only unused code introduced by the change, and attach a concrete verification check.

Do not add human-decision blockers to the run. The plan's defaults are the execution boundary. When a behavior choice appears open, assert the locked default from Outcome + Scope Lock, Interfaces and Dependencies, or Risks and Recovery. If a tool, dependency, or external environment problem prevents a validation command from running, fix it when it is locally actionable; otherwise record the exact failure and keep the affected sprint incomplete rather than marking a proxy as success.

Delegate subagents early to find real codepaths or review changes when that reduces context load or speeds execution. Let those subagents continue long enough to produce useful results. If work is still in progress after 10 minutes, request a brief progress update plus why more time is needed. Do not terminate cleanup or review subagents early just to keep the main loop moving.

### Scope Budget and Guardrails


The budget is four sprints and eleven substantive tickets. The likely backend file set is `src/lenslet/web/models.py`, `src/lenslet/web/routes/folders.py`, `src/lenslet/web/browse.py`, `src/lenslet/storage/base.py`, a new storage-neutral query module if appropriate, `src/lenslet/storage/table/storage.py`, `src/lenslet/storage/table/row_store.py`, and focused tests under `tests/web` and `tests/storage/table`. The likely frontend file set is `frontend/src/api/client.ts`, `frontend/src/api/folders.ts`, `frontend/src/lib/types.ts`, `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/features/metrics/*`, and focused frontend tests.

Core invariants are: backend evaluates membership/order/counts over the full scope before slicing; table/parquet stays row-id based until the final returned window; every sort order is total and stable across offset pages; loaded gallery pages never produce authoritative facet/filter counts; sidecar mutations invalidate and refetch backend query truth before membership/count/order changes are trusted.

Quality floor: a valid filter whose matches start after the first unfiltered page must never render as an authoritative empty gallery. Maintainability floor: browse query semantics have one backend source of truth, with frontend code only serializing state and rendering returned results. Complexity ceiling: do not build a generic DSL, database engine, parquet predicate pushdown subsystem, speculative cache layer, or all-storage materialization engine in this plan.

Debloat and removal targets are authoritative folder/table uses of frontend `applyFilters` and `applySort`, `/search` plus local filter/sort for normal browse, page-local metrics filtered counts presented as truth, grid-driven source-row discovery, and any compatibility branch that says "filtered result is zero" while backend totals disagree. Keep pure frontend helper tests for UI state and request serialization where they still serve the new contract.

### Gate Routine for Every Ticket


0. Plan gate: the code agent restates the ticket goal, acceptance criteria, material assumptions or ambiguities, expected files to touch, and the locked default that resolves any behavior choice. For substantive code, invoke `better-code` and record the key invariants, smallest robust approach, and expected verification evidence.

1. Implement gate: implement the smallest coherent slice that satisfies the ticket. Avoid speculative features, one-off abstractions, unrelated cleanup, and broad refactors outside this plan. Run the ticket's focused verification before moving on.

2. Cleanup gate: after each complete sprint, run the `code-simplifier routine` below.

3. Review gate: after cleanup, run the `review routine` below. If a subagent is unavailable or fails after a reasonable wait plus progress check, continue with manual cleanup or manual diff review and record the fallback; do not pause for human decision-making.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan current sprint changes. Start with non-semantic cleanup: formatting or lint autofixes, obvious dead code removal, small readability edits that do not change behavior, and docs or comments that reflect what is already true. Keep the pass conservative. Do not expand into semantic refactors outside this plan. Once the cleanup subagent starts, do not interrupt or repurpose it just to save time. If it runs long, wait or request a progress update. Manual cleanup review is the fallback if the subagent is unavailable or fails.

### review routine


After each complete sprint and after the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Instruct the review subagent to be constructively adversarial: actively look for ways the change could fail, where scope or validation is weak, and what should be removed or simplified, while keeping feedback actionable and focused on shipping a robust result. Use the best available model in the environment with `reasoning_effort` set to `medium`; do not default to mini or fast models. Review the post-cleanup diff, apply fixes, and rerun review if needed. Manual diff review is the fallback if the review subagent is unavailable or fails.

### Sprint Plan


1. Sprint 1: Backend query contract and evaluator.

   Demo outcome: a focused backend test posts a categorical filter whose first matching row is beyond the raw first page and receives the correct first filtered window plus filtered total.

   - S1-T1: Add storage-neutral query dataclasses/protocols, typed browse-query request/response models, and `POST /folders/query`. Validation: route tests verify offset, limit, path, recursive flag, discriminated filter AST validation, sort spec, text query, random seed, `scope_total`, `filtered_total`, stale/request token, and malformed request handling; response tests verify the new model does not expose `total_items`.
   - S1-T2: Implement backend filter evaluator for the raw browse filters used by the current UI: `starsIn`, `starsNotIn`, `nameContains`, `nameNotContains`, `notesContains`, `notesNotContains`, `urlContains`, `urlNotContains`, `dateRange`, `widthCompare`, `heightCompare`, `metricRange`, and `categoricalIn`. Validation: golden parity tests cover missing category, missing metric, non-finite metric, missing star as zero, empty filter normalization, missing notes for both notes clauses, date-only upper bounds, URL source-vs-url precedence, width/height zero and missing values, and representative serialized frontend ASTs.
   - S1-T3: Implement backend sort evaluator for builtin added/name/random and metric sorts. Every sort gets a final stable path or row-id tie-breaker. Backend random sort uses deterministic `hash(random_seed, stable_row_identity)` rather than materializing all items and reproducing frontend shuffle. Validation: tests cover asc and desc metric sort with missing or non-finite values after valid values, duplicate metric/name/date tie cases, final stable tie-breakers, seeded random stability across non-overlapping offset windows, and offset 0/limit 2 over a six-row fixture whose matches are rows 4 and 5.

2. Sprint 2: Table row-query implementation and backend facets.

   Demo outcome: table storage evaluates a categorical filter across all rows in scope, returns only a bounded item window, reports correct totals, and exposes raw facet populations without relying on frontend hydration.

   - S2-T1: Add the narrow storage query capability and implement it in `TableStorage` using row ids all the way until final slice materialization. Validation: table tests assert `filtered_total` is correct, returned rows are correct, and materialized item count equals returned window length, not scope size or filtered candidate count.
   - S2-T2: Add row-level helpers for query fields that would otherwise trigger item materialization, especially canonical path, source/url text, dimensions, metrics, categoricals, star, and notes. Validation: table tests cover star and notes filters over sidecar state without materializing unsliced candidate rows.
   - S2-T3: Keep raw facet population data backend-owned and separate from query windows. Wire query totals and keys to `/folders/query`; keep full raw populations on `/folders/facets`; do not emit loaded-window filtered facet counts as truth. Validation: table/web tests verify all categorical options appear before any gallery scrolling, `population_count` is raw scope population, `filtered_total` matches the active query result, and a category absent from the returned window still appears in Metrics with backend population.

3. Sprint 3: Frontend hard cutover to backend browse views.

   Demo outcome: applying `source_column = v0603_ema14k_image_url` causes the frontend to request a backend filtered view and render returned items without waiting for grid scroll or local page filtering.

   - S3-T1: Add frontend API/types/query keys for the browse-query endpoint and serialize current path, recursive flag, filters, sort, text query, offset, limit, and random seed into the request. Use a backend browse page size around 1000. Validation: API tests assert body shape, canonical query-key invalidation on path/filter/sort/search/random changes, and abort-signal/request budget coverage for browse-query requests.
   - S3-T2: Refactor `useAppDataScope` so normal folder/table browse uses backend query results for `items`, `filteredCount`, `scopeTotal`, metric keys, categorical keys, and load-more windows. Remove `/search` plus local filter/sort as a normal browse path; send text query through `/folders/query`. Validation: hook tests spy or mock to prove normal folder/table browse does not call authoritative local `applyFilters` or `applySort`, text search combines with filters backend-side, and load-more requests carry the same query with the next offset.
   - S3-T3: Update Metrics panel data flow so authoritative population and query counts come from backend query/facet payloads, not loaded item arrays, when browsing folder/table scopes. Validation: metrics tests prove a category absent from rendered items still appears with backend count, selecting it sends a backend query, and the UI does not show page-local filtered counts as truth.
   - S3-T4: Handle unsupported derived metric filters/sorts explicitly. Validation: frontend tests prove active `@derived/...` filter or sort in normal backend browse mode shows a visible unavailable warning, does not send a misleading query, and does not run a local loaded-window fallback. Similarity mode remains separately covered as bounded top-K behavior.

4. Sprint 4: Real scenario validation and packaged frontend.

   Demo outcome: the user-reported parquet launches, filtering by `source_column = v0603_ema14k_image_url` shows nonzero visible images, and final packaged assets are current.

   - S4-T1: Add or update browser smoke coverage for backend-owned filtered browse. Use a fixture with six or more rows, page size smaller than the first matching index, and matches only after the first raw page. Validation: the browser applies the categorical filter and renders nonzero results without scrolling.
   - S4-T2: Run the real parquet scenario before packaging and record evidence. Validation: launch `lenslet /fsx/yada/dev/new-aes-workspace/outputs/09_aiimg_mining/rapidata_labeling_setup/xgboost_feature_experiments_r1300_x15/rapidata_best_xgboost_image_scores_tall.parquet`, apply `source_column = v0603_ema14k_image_url`, and record filtered count plus visible nonzero grid items.
   - S4-T3: Build, copy frontend assets, and run final gates. Validation: `cd frontend && npm test -- --run`, `cd frontend && npm run build`, `rsync -a --delete frontend/dist/ src/lenslet/frontend/`, `python scripts/lint_repo.py`, and `python -m scripts.browser.gui_smoke.acceptance` pass. If a validation dependency is missing, fix the local dependency path where possible and keep the sprint incomplete until the real gate passes or the exact environment failure is recorded.


## Validation and Acceptance


Primary acceptance is the real user scenario. Launch the reported parquet path, open Metrics, filter categorical key `source_column` to value `v0603_ema14k_image_url`, and verify the toolbar/grid reports a nonzero filtered count and visible images without requiring scroll. The expected result is approximately the backend facet count previously observed around 3.2k, not zero.

Primary backend acceptance is a table fixture where the first unfiltered page contains no matching category and later rows contain matches. A backend query for that category with offset 0 and limit 2 must return the matching items, `filtered_total = 2`, and `scope_total = 6` for the six-row fixture.

Primary evaluator acceptance is golden parity with existing frontend filter/sort semantics. Tests must cover missing category, missing/null/non-finite metric values, star missing as zero, missing notes for both contains and not-contains, date-only upper bound expansion, URL source precedence, invalid dimensions, metric asc/desc placement of invalid values, duplicate ties, and final stable tie-breakers.

Primary row-execution acceptance is that table/parquet query execution stays row-id based until the final slice. Tests must prove materialized item count equals the returned window length and that star/notes filters can change membership after sidecar mutation/refetch without optimistic local membership deciding truth.

Primary correctness acceptance is that text query, filters, and sort are evaluated over the full backend scope before window slicing. Offset 0 and offset N are pages of the filtered and sorted result, not pages of the raw result.

Primary frontend acceptance is that normal folder/table browse renders backend query payloads directly. Tests must prove authoritative folder/table browse does not call local `applyFilters` or `applySort` to decide membership or order, does not use `/search` plus local filtering for normal browse, and does not show loaded-window facet counts as authoritative. Similarity mode is explicitly separate and is not accepted as evidence for this fix.

Secondary fast checks include focused pytest, frontend API/hook/model tests, lint, and build:

    pytest -q tests/web tests/storage/table
    cd frontend && npm test -- --run src/api src/app/hooks src/features/metrics
    cd frontend && npm run build
    python scripts/lint_repo.py

Browser acceptance should run:

    python -m scripts.browser.gui_smoke.acceptance

Do not mark Sprint 4 complete from unit tests alone. The real parquet scenario and browser acceptance are the gates that prove this bug is fixed in the intended environment.


## Risks and Recovery


The main risk is accidental frontend fallback. Recovery is to add tests that fail if normal folder/table browse filters or sorts loaded pages locally, and to keep local filter/sort helpers limited to UI state, request serialization, tests, or explicitly out-of-scope similarity mode.

The second risk is search remaining a loophole. Recovery is to route normal browse text search through `/folders/query` and test search plus categorical filter over a fixture whose matches are outside the first raw page.

The third risk is derived metrics. If active derived metric filters or sorts remain frontend-computed in normal browse, the hard cutover is incomplete. Recovery for this plan is to block derived metric query modes with a visible unavailable warning, no misleading request, and no local loaded-window fallback.

The fourth risk is materializing every row item in table queries. Recovery is to keep table query evaluation row-id based and materialize only the returned window. Tests must assert bounded materialization for filtered table queries, including sidecar-dependent filters.

The fifth risk is unstable sort pagination. Recovery is to add a final stable path or row-id tie-breaker to every sort mode and use deterministic hash-based random ordering by `(seed, stable_row_identity)`.

The sixth risk is stale or racing frontend requests. Recovery is to include all query variables in canonical React Query keys, consume or bridge abort signals, and keep stale-token guards so old responses cannot replace newer path, search, filter, sort, or seed state.

The seventh risk is cache misuse. Recovery is to bypass the existing recursive browse cache for query windows until a separate canonical query cache is explicitly designed and keyed by request plus generation and sidecar version.

The eighth risk is optimistic star or notes edits corrupting membership. Recovery is to invalidate and refetch backend browse-query data and facets after sidecar mutations. Local optimistic patches may update visible presentation only; membership, order, totals, and facets come from backend truth.

The ninth risk is making every query request heavy by bundling facets. Recovery is to keep `/folders/query` window-focused and keep raw populations on `/folders/facets` for v1. Do not compute or send full facet histograms on every pagination/filter/sort request.

The tenth risk is unsafe generic non-table fallback. Recovery is to implement full native behavior for table/parquet first, use only bounded fallback for non-table storage, and return a clear unsupported or too-large response for scopes beyond the hard limit.

Rollback is a scoped revert of the new query route/data-flow changes. The plan avoids source dataset writes, so backend query retries are idempotent. Browser and real parquet validation should be rerunnable without changing source data.


## Progress Log


- [x] 2026-06-09: User clarified that filtering is backend-owned, not frontend-owned. Scope locked around backend query semantics and no local loaded-page filtering fallback.
- [x] 2026-06-09: Codepath discovery found current coupling in `useAppDataScope` local `applyFilters/applySort`, `VirtualGrid` load-more trigger, `/folders` raw pagination, `/search` plus local filtering, and `/folders/facets` backend counts.
- [x] 2026-06-09: Required subagent plan review completed and incorporated in the first revision. Major incorporated changes: derived metrics are blocked unless backend support exists, text search is part of backend query order, facets and folder entries have explicit v1 semantics, query caching is deferred, and frontend no-local-filter tests are required.
- [x] 2026-06-09: External plan review in `docs/20260609_backend_browse_query_plan_review.md` was applied. This revision locks exact filter/sort parity, stable total ordering, row-id table execution, sidecar invalidation/refetch, search composition, separated query/facet responses, bounded non-table fallback, storage-neutral models, and no human-decision pauses during execution.
- [x] S1 complete: backend query contract and evaluator implemented and tested.
- [ ] S2 complete: table row-query and backend facets implemented and tested.
- [ ] S3 complete: frontend hard cutover implemented and tested.
- [ ] S4 complete: real parquet, browser, build, packaged frontend, and lint validation complete.
- [x] 2026-06-09: Sprint 1 implementation completed. Added storage-neutral browse query dataclasses/evaluator, strict `/folders/query` request and response models, route adapter, bounded generic fallback, sidecar-aware text query composition, deterministic hash random ordering, stable sort tie-breakers, and focused route/evaluator tests.
- [x] 2026-06-09: Sprint 1 cleanup pass completed with the `code-simplifier` routine. No broad formatting was applied because repo lint does not require `ruff format`; small non-semantic cleanups were applied for route typing, strict model reuse, and private helper naming.
- [x] 2026-06-09: Sprint 1 review pass completed with the `code-review` routine. Fixes applied: generic fallback is bounded even when storage reports no limit, fallback over-limit errors are explicit, text search includes sidecar source/url fields, and blank categorical keys are rejected at the API boundary. The remaining large-table native execution concern is deferred to planned Sprint 2 row-query work rather than hidden by the fallback.


## Artifacts and Handoff


The user-reported command/path for final validation is:

    lenslet /fsx/yada/dev/new-aes-workspace/outputs/09_aiimg_mining/rapidata_labeling_setup/xgboost_feature_experiments_r1300_x15/rapidata_best_xgboost_image_scores_tall.parquet

The failing interaction is Metrics panel categorical filtering with key and value:

    source_column = v0603_ema14k_image_url

The minimal regression fixture should include six rows, an initial query limit of two, and a category that appears only on rows four and five. A filtered backend query at offset zero and limit two must return those two rows and `filtered_total = 2`.

Sprint 1 handoff, 2026-06-09: backend query contract and evaluator are in place. New/changed files are `src/lenslet/browse/query.py`, `src/lenslet/browse/__init__.py`, `src/lenslet/web/models.py`, `src/lenslet/web/routes/folders.py`, `src/lenslet/web/browse.py`, `src/lenslet/storage/base.py`, `tests/browse/test_query_evaluator.py`, and `tests/web/routes/test_browse_query.py`. Validation evidence: `pytest -q tests/browse/test_query_evaluator.py tests/web/routes/test_browse_query.py`, `pytest -q tests/web/routes/test_direct_route_helpers.py tests/web/routes/test_folder_recursive.py tests/api/test_import_contract.py`, `pytest -q tests/storage/table/test_parquet_ingestion.py`, and `python scripts/lint_repo.py` passed. Sprint 2 should start with `S2-T1`: implement native `query_browse_scope` in `TableStorage` so large parquet scopes execute row-id based instead of using the bounded generic fallback.

The next operator should start with S2-T1 and keep this plan updated after each sprint. Do not implement another frontend load-more workaround. The root fix is backend-owned browse query semantics with filtered and sorted result windows returned by the server.

Revision note, 2026-06-09: Updated after reading `docs/20260609_backend_browse_query_plan_review.md`. The plan now asserts implementation defaults instead of adding decision gates, narrows `/folders/query` to the browse window and totals, keeps facets separate, requires exact evaluator parity and stable pagination, locks the table row-id algorithm, and removes run-time human-decision blockers.
