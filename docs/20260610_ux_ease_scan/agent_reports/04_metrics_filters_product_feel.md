# Metrics/Filters Product Feel Scan

## Journeys Inspected

- Discover available numeric metrics and categorical fields from a table-backed gallery via the left Metrics / Filters panel, toolbar Filters menu, and toolbar Sort dropdown.
- Filter a categorical field, especially values that may be outside the current loaded browse window.
- Sort by raw metrics, random order, filename, date added, and a derived score.
- Create a derived score from numeric terms and categorical bonuses, apply it, rank by it, clear it, and recover when inputs are missing or invalid.
- Import and export derived score formula text using the generated formula code area.
- Read metric histograms, categorical bucket counts, selected-item summaries, mini histograms, and the right-side metric rail.
- Recover from unsupported or partial states: no metrics, missing derived inputs, all-invalid derived scores, similarity mode ranking disabled, incomplete result population, stale saved derived keys.

## Current Strengths

- Backend-owned query semantics are now strong: `/folders/query` owns filtering, text search, sorting, derived metric evaluation, totals, and paging for normal browse. This is the right foundation for user trust.
- Facets stay separate on `/folders/facets`, so histograms and category populations do not make every browse query heavier.
- Metrics UI already avoids showing page-local filtered counts when the item population is incomplete, which prevents a subtle but serious product lie.
- Dropdowns are searchable once option counts are large enough, and they search labels, values, and raw keywords.
- Derived scores are structured, not arbitrary code, and formula import is parsed into the same safe draft model.
- Metric display names are threaded into core surfaces, so derived scores can read as "Rubric score" instead of raw `@derived/...`.
- Filter chips give the user a persistent, removable summary outside the sidebar.
- Tests already cover key product invariants: backend full-scope filtering, separated facets, derived ranking, formula diagnostics, invalid finite metric handling, and loaded-window count suppression.

## Ranked Opportunities

1. **Make incomplete facet/filter count state visible in the Metrics panel**
   - Severity: High
   - User impact: Users see `Population` but not why `Filtered` disappears or why some values show only raw counts. That can feel like a bug during experimentation.
   - Likely code area: `frontend/src/features/metrics/MetricsPanel.tsx`, `MetricRangePanel.tsx`, `CategoricalPanel.tsx`, `MetricHistogramCard.tsx`, `CategoricalCard.tsx`.
   - Fix concept: Add a compact inline note when `itemPopulationComplete` is false, e.g. "Showing full population counts; filtered value counts load after the full result set is loaded." Keep it one line and only in cards where counts are affected.
   - Effort: S
   - Performance/code-bloat risk: Low; copy-only plus existing state.
   - Validation method: MetricsPanel render tests for incomplete population with facets; Playwright smoke with a paged fixture.

2. **Add direct "Sort by this metric" / "Sort descending" actions on metric cards**
   - Severity: High
   - User impact: The current workflow requires finding a metric in the Metrics panel, then finding the same metric again in the toolbar Sort dropdown. That slows score exploration.
   - Likely code area: `MetricHistogramCard.tsx`, `MetricCategoryCard.tsx`, `MetricRangePanel.tsx`, `AppShell.tsx`, `LeftSidebar.tsx`.
   - Fix concept: Add a small sort icon button in the metric card header when a metric is active. It should call the existing `onSortChange` path, not create a second sort model.
   - Effort: M
   - Performance/code-bloat risk: Low if it reuses existing sort state and icons; medium if it grows separate controls for every card in Show all mode.
   - Validation method: Component test that clicking the card action emits `{ kind: "metric", key, dir: "desc" }`; browser smoke for sort order and metric rail activation.

3. **Clarify derived score validity with a compact diagnostics block**
   - Severity: High
   - User impact: The card shows `Valid: N Invalid: N`, but invalid reasons are compressed into one status line. Users need to know whether invalid means missing metric, missing categorical field, no valid values, or disabled mode.
   - Likely code area: `DerivedScoreCard.tsx`, `derivedMetricDraft.ts`, `derivedMetric.ts`, `StatusBar.tsx`.
   - Fix concept: Replace the single low-contrast status line with a small diagnostics row: valid count, invalid count, missing inputs, current rank availability. Keep the top banner for global saved-state issues.
   - Effort: M
   - Performance/code-bloat risk: Low; diagnostics already exist.
   - Validation method: DerivedScoreCard render tests for missing inputs, invalid intercept, no valid values, and similarity-mode rank disabled.

4. **Make formula import/export feel safer and more discoverable**
   - Severity: Medium-High
   - User impact: "Formula code" and "Use current" are ambiguous. A user may not realize this is a share/import surface, or may fear overwriting the structured editor.
   - Likely code area: `DerivedScoreCard.tsx`, `derivedMetricDraft.ts`.
   - Fix concept: Rename to "Formula text", add explicit "Import formula" and "Reset from editor" labels, and show diagnostics as success/warning/error with skipped terms listed compactly.
   - Effort: S
   - Performance/code-bloat risk: Low.
   - Validation method: Existing formula import tests plus a component test for diagnostic copy after missing inputs.

5. **Expose categorical value search inside long category cards**
   - Severity: Medium-High
   - User impact: Field dropdowns are searchable, but once inside a high-cardinality categorical card, users scroll a `max-h-72` list manually.
   - Likely code area: `CategoricalCard.tsx`, `MetricCategoryCard.tsx`, shared dropdown search helpers if reused.
   - Fix concept: Add a local value search input only when bucket count exceeds a threshold. Filter visible buckets client-side from the already fetched facet values.
   - Effort: M
   - Performance/code-bloat risk: Low for simple string filtering; avoid virtualization unless proven necessary.
   - Validation method: Component tests for search, active value persistence, and empty state; browser test with 50+ categories.

6. **Show active metric/categorical context in the panel header area**
   - Severity: Medium
   - User impact: Metrics and categorical controls are separate dropdowns; users can lose track of which field is driving active filters, especially after returning to the panel.
   - Likely code area: `MetricsPanel.tsx`, `MetricRangePanel.tsx`, `CategoricalPanel.tsx`, `filterChips.ts`.
   - Fix concept: Add small active-state badges next to "Metric" and "Categorical" labels when that selected field has an active filter. Do not duplicate all filter chips.
   - Effort: S
   - Performance/code-bloat risk: Low.
   - Validation method: Render tests for active metric/categorical filters; screenshot smoke for dense sidebar layout.

7. **Reduce "Show all" risk for large schemas**
   - Severity: Medium
   - User impact: "Show all" can create many cards with histograms and bucket lists. That is useful but may feel heavy or slow on wide metric schemas.
   - Likely code area: `MetricRangePanel.tsx`, `CategoricalPanel.tsx`.
   - Fix concept: Convert Show all into "Show first N" plus field search, or cap expanded cards with a "Load more fields" button. Keep backend facets as the population source.
   - Effort: M
   - Performance/code-bloat risk: Medium if implemented with unnecessary virtualization; low if capped.
   - Validation method: Component test for capped rendering; performance smoke with a synthetic 100-metric payload.

8. **Add an explicit empty-result recovery path**
   - Severity: Medium
   - User impact: When filters produce zero images, the user sees chips and can clear all, but there is no targeted hint about which filter is most restrictive.
   - Likely code area: `VirtualGrid.tsx`, `GridTopStack.tsx`, `filterChips.ts`, `AppShell.tsx`.
   - Fix concept: In empty filtered state, show a compact grid-empty action row: "No matches. Clear latest filter" and "Clear all filters." Backend should still own the zero count.
   - Effort: M
   - Performance/code-bloat risk: Low.
   - Validation method: Playwright empty-filter scenario; unit test for latest filter action if added.

9. **Make metric rail discoverability stronger when sorting by a metric**
   - Severity: Medium
   - User impact: The rail is useful but visually narrow and mostly implicit. Users may not know they can scrub/jump by metric value.
   - Likely code area: `MetricScrollbar.tsx`, `styles.css`, maybe `Toolbar.tsx`.
   - Fix concept: Add a tiny hover tooltip or value pill on first hover, and ensure the rail title includes the metric label and "click to jump." Avoid persistent instructional text.
   - Effort: S
   - Performance/code-bloat risk: Low.
   - Validation method: Component/screenshot test for hover label; Playwright pointer interaction smoke.

10. **Give derived score a compact preview histogram of the output score**
    - Severity: Medium
    - User impact: Users see input mini histograms but not the distribution of the score they are creating, which slows tuning weights.
    - Likely code area: `DerivedScoreCard.tsx`, `DerivedMetricMiniHistogram.tsx`, `derivedMetricDraft.ts`.
    - Fix concept: Reuse the existing mini histogram component against the draft evaluation's valid output values. Show it below the formula preview with valid/invalid counts.
    - Effort: M
    - Performance/code-bloat risk: Medium because draft evaluation can scan loaded items on every edit; debounce or compute from existing `draftRankState`.
    - Validation method: DerivedScoreCard render test and a small performance test with thousands of items.

11. **Separate global unsupported warnings from local editor errors**
    - Severity: Medium
    - User impact: A top status banner for saved derived score state and a card status line for the current draft can both talk about "Derived score," which may feel redundant or conflicting.
    - Likely code area: `StatusBar.tsx`, `DerivedScoreCard.tsx`, `appShellSelectors.ts`.
    - Fix concept: Reserve `StatusBar` for active view-state problems that affect the gallery result; reserve the card for draft/edit validation. Use consistent terms: "active score" vs "draft score."
    - Effort: S
    - Performance/code-bloat risk: Low.
    - Validation method: StatusBar tests plus DerivedScoreCard invalid-state tests.

12. **Improve field labels for categoricals**
    - Severity: Low-Medium
    - User impact: Metric display names are supported, but categorical fields still show raw keys. This is fine for `source_column`, less good for long model/eval column names.
    - Likely code area: `lib/types.ts`, `CategoricalPanel.tsx`, `CategoricalCard.tsx`, backend facet/key payloads if label support becomes backend-owned.
    - Fix concept: Add optional display names only if the backend can supply them or a table schema has aliases. Do not invent frontend-only labels that break request serialization.
    - Effort: M
    - Performance/code-bloat risk: Low, but API shape risk is medium.
    - Validation method: Backend model tests and render tests for label fallback to raw key.

## Quick Wins

1. Add an incomplete-population note to Metrics cards when filtered per-value counts are intentionally hidden.
2. Rename derived formula controls from "Formula code" / "Use current" to clearer import/export language.
3. Add active-filter badges beside the selected Metric and Categorical labels.

## Medium Projects

1. Add direct sort actions to metric cards and derived score output, reusing toolbar sort state.
2. Add searchable high-cardinality categorical and metric-category value lists.
3. Add an output-score mini histogram and clearer diagnostics block to the Derived Score card.

## Backend-Owned Boundaries

- Full-scope membership, ordering, totals, text search composition, derived metric filter/sort evaluation, and pagination must remain backend-owned for normal folder/table browse.
- Raw facet populations, metric histograms, categorical value populations, and schema-backed metric/categorical key discovery should remain backend-owned.
- Per-value filtered facet counts should stay hidden unless the backend returns authoritative counts.
- Derived score formulas should remain structured specs sent to the backend for query-authoritative use; the frontend editor can draft and preview, but should not decide normal browse result truth.
- Sidecar-dependent star/notes membership should remain backend-owned after mutation/refetch. Optimistic frontend patches should affect visible presentation only.

## Things Not To Do

- Do not reintroduce local loaded-window filtering or sorting for normal browse as a convenience fallback.
- Do not show page-local filtered bucket counts as if they describe the full result set.
- Do not add a general expression language, `eval`, or a parser dependency for derived formulas.
- Do not add a new metrics state store or a separate sorting model; reuse `ViewState` and existing query serialization.
- Do not make every query response include full facets; keep facets on demand.
- Do not promote all numeric columns blindly into metrics just to help formula creation.
- Do not build virtualization or a new component framework for category lists until a real schema-size performance issue is measured.

## Top 5 Recommendations

1. Make partial/incomplete count semantics visible inside Metrics cards.
2. Add direct sort/rank actions from metric and derived score cards.
3. Improve Derived Score diagnostics and formula import/export wording.
4. Add search within high-cardinality category/value cards.
5. Keep all query-authoritative truth in the backend and avoid any local loaded-window fallback.
