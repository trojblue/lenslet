# Metrics/Filters Codepath Scan

## Scope and Files Inspected

This scan focused on Lenslet metrics, filtering, sorting, derived-score, facet, and option-selection codepaths. It did not modify application code.

Primary frontend files inspected:

- `frontend/src/app/AppShell.tsx`
- `frontend/src/app/hooks/useAppDataScope.ts`
- `frontend/src/app/model/appShellSelectors.ts`
- `frontend/src/app/model/filterChips.ts`
- `frontend/src/app/model/smartFolders.ts`
- `frontend/src/app/routing/viewStateUrl.ts`
- `frontend/src/api/folders.ts`
- `frontend/src/lib/types.ts`
- `frontend/src/features/browse/model/apply.ts`
- `frontend/src/features/browse/model/filters.ts`
- `frontend/src/features/browse/model/sorters.ts`
- `frontend/src/features/metrics/MetricsPanel.tsx`
- `frontend/src/features/metrics/DerivedScorePanel.tsx`
- `frontend/src/features/metrics/components/CategoricalCard.tsx`
- `frontend/src/features/metrics/components/CategoricalPanel.tsx`
- `frontend/src/features/metrics/components/DerivedMetricMiniHistogram.tsx`
- `frontend/src/features/metrics/components/DerivedScoreCard.tsx`
- `frontend/src/features/metrics/components/MetricCategoryCard.tsx`
- `frontend/src/features/metrics/components/MetricHistogramCard.tsx`
- `frontend/src/features/metrics/components/MetricRangePanel.tsx`
- `frontend/src/features/metrics/model/categoricalValues.ts`
- `frontend/src/features/metrics/model/derivedMetric.ts`
- `frontend/src/features/metrics/model/derivedMetricDraft.ts`
- `frontend/src/features/metrics/model/histogram.ts`
- `frontend/src/features/metrics/model/metricValues.ts`
- `frontend/src/shared/ui/Dropdown.tsx`
- `frontend/src/shared/ui/Toolbar.tsx`
- `frontend/src/shared/ui/dropdownSearch.ts`
- `frontend/src/shared/ui/toolbar/ToolbarFilterMenu.tsx`

Primary backend files inspected:

- `src/lenslet/web/routes/folders.py`
- `src/lenslet/web/models.py`
- `src/lenslet/web/browse.py`
- `src/lenslet/browse/query.py`
- `src/lenslet/metrics.py`
- `src/lenslet/storage/table/storage.py`
- `src/lenslet/storage/table/index.py`
- `src/lenslet/storage/table/schema.py`
- `src/lenslet/storage/table/display.py`
- `src/lenslet/storage/table/categoricals.py`
- `src/lenslet/web/cache/browse_snapshot.py`

Tests inspected:

- `frontend/src/features/metrics/__tests__/MetricsPanel.test.tsx`
- `frontend/src/features/metrics/components/__tests__/MetricRangePanel.test.tsx`
- `frontend/src/features/metrics/model/__tests__/derivedMetric.test.ts`
- `frontend/src/features/metrics/model/__tests__/derivedMetricDraft.test.ts`
- `frontend/src/app/__tests__/appShellSelectors.test.ts`
- `frontend/src/app/hooks/__tests__/useAppDataScopeBackendQuery.test.ts`
- `frontend/src/api/__tests__/folders.test.ts`
- `frontend/src/shared/ui/__tests__/dropdownSearch.test.ts`
- `frontend/src/shared/ui/toolbar/__tests__/Toolbar.test.tsx`
- `frontend/src/app/__tests__/settingsPersistence.test.ts`
- `frontend/src/app/routing/__tests__/viewStateUrl.test.ts`
- `frontend/src/app/model/__tests__/smartFolders.test.ts`
- `tests/browse/test_query_evaluator.py`
- `tests/web/routes/test_browse_query.py`
- `tests/storage/table/test_table_browse_query_storage.py`
- `tests/storage/table/test_table_formula_metrics.py`
- `tests/storage/table/test_table_index_pipeline.py`
- `tests/storage/table/test_parquet_ingestion.py`

## Architecture Map

1. User-facing state starts in `ViewState`: `filters`, `sort`, `selectedMetric`, and `derivedMetric` are held in `AppShell.tsx`, persisted through settings/smart folders, and partly serialized to the URL.
2. Toolbar sort controls create `SortSpec` values. Metrics panels create `FilterAst` clauses via `setMetricRangeFilter` and `setCategoricalInFilter`. The derived-score panel applies or ranks a `DerivedMetric` through `applyDerivedMetricToViewState` and `rankByDerivedMetricInViewState`.
3. `useAppDataScope.ts` passes `viewState.filters`, `viewState.sort`, `viewState.derivedMetric`, text search, random seed, and a browse limit into `useBrowseQuery`.
4. `frontend/src/api/folders.ts` serializes the request as `BrowseQueryRequest` and sends it to `POST /folders/query`. It uses a limit of `1000` normally and `50000` for metric sorts.
5. `src/lenslet/web/routes/folders.py` converts the request into backend dataclasses and calls `build_folder_query`.
6. `src/lenslet/web/browse.py` delegates to `storage.query_browse_scope` when available, otherwise falls back to in-memory evaluation capped by `BROWSE_QUERY_FALLBACK_MAX_ITEMS`.
7. `src/lenslet/storage/table/storage.py` materializes browse records for table-backed scopes and calls `evaluate_browse_records`.
8. `src/lenslet/browse/query.py` owns canonical query evaluation order: normalize derived metric, apply derived score if needed, text search, filters, sort, offset, and limit. It also creates request tokens.
9. The query response returns a paginated item window, `scope_total`, `filtered_total`, `metric_keys`, `categorical_keys`, and `request_token`.
10. After the backend response, `useAppDataScope.ts` still locally evaluates the active derived metric over the loaded returned items to append a derived display key and score values.
11. Metric/categorical facets use a separate `GET /folders/facets` endpoint keyed only by `path` and `recursive`. It does not include active filters, text query, sort, or derived metric state.
12. `MetricsPanel`, `MetricRangePanel`, and `CategoricalPanel` combine raw backend facets with loaded-window item counts. `DerivedScoreCard` uses facet histograms when available and falls back to loaded item values.
13. Similarity mode is the main path that still applies filters and sorts locally in the frontend.

## Ranked Findings

### 1. High: Facets Are Not Query-Shaped, So Counts and Options Drift From Active Filters

- User impact: Metrics and categorical panels can show population/options from the raw scope while the visible item list is narrowed by active filters, search, sort windowing, or derived-score state. This makes counts look authoritative when they are not, especially in large folders where the loaded window is incomplete.
- Root files: `src/lenslet/web/routes/folders.py`, `src/lenslet/web/models.py`, `src/lenslet/web/browse.py`, `frontend/src/api/folders.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/features/metrics/model/metricValues.ts`, `frontend/src/features/metrics/model/categoricalValues.ts`.
- Cause: `GET /folders/facets` accepts only `path` and `recursive`. The metrics UI then merges raw facet summaries with loaded item counts instead of receiving facet truth for the same canonical query as `POST /folders/query`.
- Suggested fix shape: Add a query-owned facet contract. Either include bounded facet summaries in `POST /folders/query` or add `POST /folders/facets/query` with the same normalized query fields and request token. Return explicit `population_count`, `filtered_count`, and count source metadata, or omit filtered counts when the backend cannot compute them.
- Effort: L.
- Performance/code-bloat risk: Medium. Facets can be expensive for large scopes; use bounded histograms, top-N buckets, request-token caching, and lazy panel fetches.
- Validation method: Backend API tests where a categorical filter changes facet filtered counts across unloaded rows. Frontend tests where active filters do not display loaded-window counts as full filtered truth. Playwright smoke with large fixture and active filters.

### 2. High: Derived Scores Have Split Ownership Between Backend Query and Frontend Re-Evaluation

- User impact: Derived score values, histograms, warnings, and valid counts can disagree with backend sort/filter behavior. Z-normalized scores are especially risky because the backend scores over the full scope before filtering/windowing, while the frontend re-evaluates over returned items.
- Root files: `src/lenslet/browse/query.py`, `src/lenslet/storage/table/storage.py`, `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/features/metrics/model/derivedMetric.ts`, `frontend/src/features/metrics/components/DerivedScoreCard.tsx`.
- Cause: The backend already applies derived metrics in canonical query evaluation. The frontend still calls `evaluateDerivedMetric` on the loaded item window and sets `totalItems` to `sourceItems.length`, which hides partial-load warnings on the normal backend path.
- Suggested fix shape: Make backend-derived results authoritative for normal browse. Return a `derived_metric_status` payload with `status`, `key`, `display_name`, `valid_count`, `invalid_count`, `input_keys`, and score values already attached to items. Keep local evaluation only for similarity mode and clearly local draft previews.
- Effort: L.
- Performance/code-bloat risk: Medium. Avoid adding multiple parallel status models; define one backend-owned contract consumed by toolbar, chips, panels, and derived score UI.
- Validation method: Add a z-normalized derived sort test where displayed score values match full-scope backend scores, not page-local recomputation. Add a UI test for valid/invalid counts on a paginated folder.

### 3. High: Table Browse Can Advertise a Derived Metric Key Even When Inputs Are Unavailable

- User impact: A user can see or select a derived metric that has no computed values. That creates phantom sort/filter options and confusing zero/empty histogram states.
- Root files: `src/lenslet/storage/table/storage.py`, `src/lenslet/browse/query.py`, `frontend/src/app/model/appShellSelectors.ts`, `frontend/src/shared/ui/Toolbar.tsx`.
- Cause: `TableStorage.query_browse_scope` appends the derived key to `metric_keys` whenever the spec normalizes, even though `apply_derived_metric_to_records` may return records without scores if required inputs are missing.
- Suggested fix shape: Append the derived key only when the backend actually applied the metric, or return it with explicit `unavailable` status and reason. The frontend should key enablement from status, not from metric-key presence.
- Effort: M.
- Performance/code-bloat risk: Low.
- Validation method: Backend test with a derived spec referencing a missing metric: response should either exclude the derived key or include `derived_metric_status: unavailable`; toolbar should not expose it as an enabled sort.

### 4. High: Numeric Metric Discovery Is Too Broad and Pollutes Metrics Workflows

- User impact: Large tables can flood metrics and derived-score dropdowns with arbitrary numeric metadata. Important table fields may disappear from "Other table fields" because they were heuristically promoted to metrics.
- Root files: `src/lenslet/storage/table/index.py`, `src/lenslet/storage/table/display.py`, `tests/storage/table/test_table_formula_metrics.py`, `tests/storage/table/test_table_index_pipeline.py`, `frontend/src/features/metrics/components/DerivedScoreCard.tsx`, `frontend/src/shared/ui/Toolbar.tsx`.
- Cause: `is_metric_column_name` currently delegates to broad formula-metric heuristics, so almost any finite numeric, non-excluded column can become a metric. The same list is used for display metrics, sorting, filtering, and derived-score inputs.
- Suggested fix shape: Split field capabilities. Keep a concise backend-owned `metric_keys` list for user-facing metric panels and sorting, and expose a broader `numeric_input_keys` or `formula_input_keys` list for derived-score formulas. Include source/type metadata so the UI can group options without frontend heuristics.
- Effort: M.
- Performance/code-bloat risk: Medium if over-modeled; keep one small capability payload rather than many ad hoc lists.
- Validation method: Fixture with many numeric metadata columns. Verify metrics panel stays focused while derived-score builder can still search eligible numeric inputs.

### 5. Medium: Active Sort State Can Lose Its Label When the Metric Becomes Unavailable

- User impact: The toolbar can show a generic placeholder for a still-active metric sort if the current key is not present in the option list. Users cannot tell whether they are sorted by a missing metric, a derived metric, or no metric.
- Root files: `frontend/src/shared/ui/Toolbar.tsx`, `frontend/src/shared/ui/Dropdown.tsx`, `frontend/src/app/AppShell.tsx`, `frontend/src/app/model/appShellSelectors.ts`.
- Cause: Metric sort options are built only from current `metricKeys`. `Dropdown` resolves the trigger label only from available options and otherwise falls back to the placeholder.
- Suggested fix shape: Build sort options from a canonical registry that includes the active sort key as a disabled/unavailable option when necessary. Pair it with the existing unavailable-sort reset/warning behavior instead of hiding context.
- Effort: S.
- Performance/code-bloat risk: Low.
- Validation method: Component test with `sort: metric:old_key` and `metricKeys` missing `old_key`; toolbar should show `old_key (unavailable)` or equivalent disabled label.

### 6. Medium: Count Labels Mix Backend Scope Counts With Loaded-Window Counts

- User impact: Histogram and categorical cards show `Population`, `Filtered`, and `Selected` as if they are the same kind of count. In reality, population often comes from backend facets, while filtered counts can come from the loaded browser window or be hidden depending on completeness.
- Root files: `frontend/src/features/metrics/components/MetricHistogramCard.tsx`, `frontend/src/features/metrics/components/MetricCategoryCard.tsx`, `frontend/src/features/metrics/components/CategoricalCard.tsx`, `frontend/src/features/metrics/model/metricValues.ts`, `frontend/src/features/metrics/model/categoricalValues.ts`, `frontend/src/app/AppShell.tsx`.
- Cause: The UI relies on `itemPopulationComplete` and `items.length >= filteredCount` to decide whether loaded item counts are complete enough. That is a local inference layered on top of raw facets and paginated browse results.
- Suggested fix shape: Add explicit count provenance to the data model. Labels should distinguish `scope`, `query result`, and `loaded window`, or show only backend-provided query counts in normal browse.
- Effort: M.
- Performance/code-bloat risk: Low. Most of the work is contract cleanup and label/conditional simplification.
- Validation method: Frontend tests for a paginated result where filtered counts are not complete; cards should avoid exact-looking filtered ratios from loaded rows.

### 7. Medium: Formula Import Fails Open When Terms Are Missing

- User impact: A pasted formula with a typo or missing field can still apply a partial score. The user may rank by a materially different formula than intended.
- Root files: `frontend/src/features/metrics/model/derivedMetricDraft.ts`, `frontend/src/features/metrics/components/DerivedScoreCard.tsx`, `frontend/src/features/metrics/model/__tests__/derivedMetricDraft.test.ts`.
- Cause: `applyDerivedMetricFormulaCode` records diagnostics for missing metrics/categoricals but can still return `applied: true` if at least one usable term or intercept remains.
- Suggested fix shape: Fail closed on missing referenced terms. If partial import is useful, make it a deliberate secondary action with explicit UI text and no automatic draft mutation.
- Effort: S.
- Performance/code-bloat risk: Low.
- Validation method: Unit test that a formula referencing `[quality] + [typo]` does not mutate/apply until the missing term is resolved or explicitly discarded.

### 8. Medium: Long Metric and Categorical Dropdowns Lack Enough Backend Metadata

- User impact: Users with many metrics/categoricals must search through long flat option lists with similar labels. Raw keys are search keywords but not consistently visible, and options do not communicate source, type, count availability, or whether a value is stale/unavailable.
- Root files: `frontend/src/shared/ui/Dropdown.tsx`, `frontend/src/shared/ui/dropdownSearch.ts`, `frontend/src/features/metrics/components/DerivedScoreCard.tsx`, `frontend/src/features/metrics/components/MetricRangePanel.tsx`, `frontend/src/features/metrics/components/CategoricalPanel.tsx`.
- Cause: Dropdown options are mostly `{ value, label, keywords }`. The backend does not provide a compact field metadata contract, so the frontend cannot reliably group or annotate choices.
- Suggested fix shape: Add backend field metadata for metric/categorical/formula-input capabilities, labels, source column, value type, and availability. Render compact grouped options with raw-key subtitles/tooltips and counts where authoritative.
- Effort: M.
- Performance/code-bloat risk: Medium. Keep rendering virtualized only if needed; first solve ownership and metadata shape.
- Validation method: Browser test fixture with 200 metrics and overlapping display names; search, selected labels, and unavailable labels remain understandable.

### 9. Medium: Metric Display Names Are Derived-Only, So Backend Field Labels Do Not Travel With Metrics

- User impact: Table-backed metrics mostly surface raw column names even when a source schema or sidecar could provide friendlier labels. Derived metrics get display names, but ordinary metrics do not have the same path.
- Root files: `frontend/src/app/hooks/useAppDataScope.ts`, `frontend/src/app/model/filterChips.ts`, `frontend/src/features/metrics/model/derivedMetric.ts`, `src/lenslet/web/models.py`, `src/lenslet/storage/table/storage.py`.
- Cause: `metricDisplayNames` is assembled in the frontend for derived metrics. Existing `metric_labels` on item payloads are value-label maps, not field display metadata.
- Suggested fix shape: Add optional backend metric metadata keyed by field. Use it everywhere options, chips, histogram titles, and toolbar labels are rendered. Keep raw keys visible in tooltips or subtitles.
- Effort: M.
- Performance/code-bloat risk: Low.
- Validation method: Table fixture with configured field labels; verify toolbar, chips, metrics panel, and derived builder use the same backend label.

### 10. Medium: URL Sharing Drops Applied Derived-Score Definitions Unless They Affect Query Semantics

- User impact: A user can build and apply a derived score, then share or reload a view and lose the score definition if it is not currently used by a sort or filter.
- Root files: `frontend/src/app/routing/viewStateUrl.ts`, `frontend/src/app/routing/__tests__/viewStateUrl.test.ts`, `frontend/src/app/model/smartFolders.ts`.
- Cause: URL serialization includes `derived_metric` only when `viewStateUsesDerivedMetric` is true. That preserves query semantics but not the derived-score workflow state.
- Suggested fix shape: Decide that applied derived metrics are part of canonical view state and include them whenever present. If URL length is a concern, keep smart-folder persistence full fidelity and make URL behavior explicit in UI copy, but avoid silent loss.
- Effort: S.
- Performance/code-bloat risk: Low; possible longer URLs.
- Validation method: URL roundtrip test where a derived metric is applied and selected but not used for sort/filter.

### 11. Low/Medium: Some Backend-Boundary Frontend Tests Assert Source Text Instead of Behavior

- User impact: Regressions in local-vs-backend ownership can slip through because tests check implementation strings rather than runtime behavior.
- Root files: `frontend/src/app/hooks/__tests__/useAppDataScopeBackendQuery.test.ts`.
- Cause: The tests inspect source text for imports and hook usage, such as asserting that local `applySort` is not imported.
- Suggested fix shape: Replace source-text tests with hook/component behavior tests using mocked query pages. Assert that normal backend browse does not locally filter/sort membership, that request payloads contain canonical filters/sorts, and that similarity mode remains local.
- Effort: M.
- Performance/code-bloat risk: Low.
- Validation method: Remove the source-string assertions and run the behavioral replacements through `npm test` or the existing frontend test command.

### 12. Low/Medium: Facet Cache Identity Is Weaker Than Browse Query Identity

- User impact: The metrics panel can momentarily display stale facet summaries after source changes or state transitions because facets are keyed only by path/recursive and checked only by `metricsFacets.path`.
- Root files: `frontend/src/api/folders.ts`, `frontend/src/app/AppShell.tsx`, `src/lenslet/web/models.py`, `src/lenslet/web/browse.py`.
- Cause: Browse query responses carry richer query identity through request tokens. Facets have no equivalent query token or generation identifier in the frontend contract.
- Suggested fix shape: Make facets carry and key on the same normalized scope/query identity as browse results. At minimum include a backend generation token and compare more than path.
- Effort: S/M.
- Performance/code-bloat risk: Low.
- Validation method: Test switching source-column/base-dir or sidecar metadata for the same path and verify old facets are not rendered against new items.

## Quick Wins

1. Show unavailable active metric sorts explicitly in the toolbar instead of falling back to `Select...`.
2. Change formula import to fail closed when referenced metric or categorical terms are missing.
3. Add count provenance labels or hide exact-looking filtered ratios whenever they are loaded-window counts rather than backend query counts.

## Medium Projects

1. Introduce query-shaped facets with canonical request identity and backend-owned count semantics.
2. Move derived-score status and computed-score ownership fully into the backend browse response for normal browse, keeping frontend evaluation only for drafts and similarity mode.
3. Split metric field capabilities into display metrics, sortable/filterable metrics, formula numeric inputs, and categorical inputs with backend-provided metadata.

## Things Not To Do

- Do not add more frontend heuristics to guess whether facets, counts, or derived scores are authoritative.
- Do not broaden metric-name whitelists or blacklists as the main fix for crowded metric dropdowns.
- Do not keep re-normalizing derived scores over whatever item window happens to be loaded in normal browse.
- Do not show exact percentages or ratios when the numerator and denominator come from different scopes.
- Do not solve stale options by forcibly clearing user state without also explaining or preserving the unavailable key.
- Do not add a second derived-score implementation path for table storage, local storage, and frontend; prefer one canonical backend evaluator.
- Do not expand source-text tests as a substitute for query/result behavior tests.

## Top 5 Recommendations

1. Make facets query-shaped and backend-owned, using the same canonical request identity as browse queries.
2. Return derived-score status and values from the backend for normal browse, and stop page-local re-evaluation from driving displayed truth.
3. Split broad numeric field discovery from user-facing metric display so score formulas remain powerful without flooding sort/filter UIs.
4. Add explicit availability/count provenance to metric options, chips, histogram cards, and categorical cards.
5. Replace brittle frontend source-text tests with behavior tests that prove the backend owns filtering, sorting, derived metrics, and facet counts in normal browse.
