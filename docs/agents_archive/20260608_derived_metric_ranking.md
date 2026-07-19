# Derived Metrics For Gallery Ranking

Lenslet already has most of the right pieces for "create a score, then rank by it":

- table-backed browse payloads expose numeric `metrics` and string `categoricals`
- the Metrics panel already lets users inspect and filter those fields
- gallery sorting already accepts a metric key
- Smart Folders already persist filters and sort state

The clean implementation should treat a user-built score as a first-class derived metric. Once computed, it should behave like any other numeric metric: it appears in the metric selector, can drive the histogram/metric rail, can be used by the toolbar sort control, and can be saved with the current view.

## Why This Matters

The current Metrics panel is good at answering "what does this dataset contain?" and "how do I filter by one field?". The missing workflow is "combine several judgments into the order I actually want to inspect".

For evaluation datasets, a single scalar rarely captures the useful ranking. Users often have several question columns, model outputs, or review dimensions, plus categorical context that should affect priority. Sorting by one raw column forces users to mentally combine the rest. That does not scale when the task is to inspect hundreds or thousands of images.

Derived metrics make the workflow explicit:

- encode an evaluation rubric once
- sort the gallery by that rubric
- inspect the highest or lowest scoring cases visually
- save the rubric as part of a Smart Folder
- revise the weights when the rubric changes

This is especially useful for comparison/eval tables where columns like `q1` through `q6` are not independent destinations. They are inputs to a human-defined aggregate score.

## User Shape

The motivating workflow is a table with fields such as `q1` through `q6` and a categorical such as `dataset_from`.

Example:

```text
new_score =
  q1 * 1.0
  + q2 * 1.0
  + q3 * 0.8
  + 1.0 if dataset_from == "gt"
```

Then the gallery should sort images by `new_score`, usually descending.

## Existing System Fit

The best place for this is the Metrics panel, not a new top-level tab. Metrics is already where scalar distributions, categorical buckets, and filter controls meet. A derived score builder belongs next to those source fields.

The current frontend sort path is:

1. load folder or search items
2. apply filters
3. apply sort

Metric sorting reads `item.metrics[key]`, so a derived metric only needs to be added to each item's `metrics` map before filtering and sorting run.

This is why the feature should be built as "derived metrics" rather than as a separate "ranking mode". Lenslet already has a ranking mode, but that mode is for manual rank assignment over configured ranking datasets. The requested workflow is browse-time ranking over table fields. It should stay inside browse because the user still wants the normal gallery, filters, viewer, compare, inspector, and Smart Folder behavior.

## Design Goals

- Make scoring fast to create for simple weighted sums.
- Keep the resulting score interoperable with existing metric UI and sorting.
- Avoid expression execution or new parser dependencies for the first cut.
- Keep the score definition stable enough to persist in Smart Folders.
- Make missing fields obvious instead of silently producing misleading rankings.
- Preserve large-table performance by being explicit about what fields need to be loaded.

## Non-Goals

- This is not a general spreadsheet formula language.
- This is not a replacement for the existing manual ranking mode.
- This should not write derived score columns back into source datasets by default.
- This should not require backend work for the first usable client-side version, although backend sorted windows remain the right next step for very large datasets.

## Important Backend Constraint

Today table mode only auto-promotes numeric columns whose names look metric-like, for example names containing `score`, `quality`, `rating`, `prob`, or `confidence`.

Short question columns such as `q1`, `q2`, and `q3` are likely to stay as inspector table fields instead of appearing in the Metrics panel. That means a useful derived-score builder needs one of these backend adjustments:

- broaden browse metrics to include numeric scalar columns that are formula-eligible
- or add explicit table launch options for metric/formula input columns
- or add a separate browse payload section for numeric table fields

For the pre-release alpha, the cleanest hard cutover is to broaden `metrics` to mean "numeric scalar fields available for metric work", while still excluding obvious identifiers and internal bookkeeping columns.

The reason to handle this in browse payloads is practical: the score builder needs values for every visible item, not just the selected item. Inspector table fields are loaded per item and are not a good foundation for gallery-wide sorting.

## Proposed Data Model

Add derived metric definitions to `ViewState` so local persistence and Smart Folders can reopen a score-backed ranking view.

```ts
type DerivedMetricSpec = {
  id: string
  name: string
  intercept: number
  numericTerms: Array<{
    metricKey: string
    weight: number
    missing: 'zero' | 'omit' | 'invalid'
  }>
  categoricalTerms: Array<{
    categoricalKey: string
    equals: string
    weight: number
  }>
}
```

The computed metric key can be namespaced to avoid collisions with table columns, for example:

```text
@derived/new_score
```

The display name can stay `new_score`.

The spec is intentionally structured rather than textual. A text formula such as `q1 + q2 + if(dataset_from == "gt", 1, 0)` looks attractive, but it creates immediate problems:

- parser or expression-runtime dependency
- escaping and field-name syntax for columns with punctuation
- unclear missing-value behavior
- validation that is harder to present in the UI
- security concerns if evaluation is implemented carelessly

Structured terms keep the first cut boring and inspectable. The UI can still show a generated formula preview so users can confirm the score reads the way they expect.

## Evaluation Rules

Use structured rules, not arbitrary expression execution.

For each item:

1. start with `intercept`
2. add each numeric metric value times its weight
3. apply the missing-value policy for numeric inputs
4. add each categorical rule weight when the item's categorical value matches
5. store the result in `item.metrics[derivedMetricKey]`

If any required term is invalid under the selected missing-value policy, the derived score should be `null` and sort after scored items.

This avoids `eval`, `new Function`, parser dependencies, and ambiguous expression syntax while still covering the main scoring use case.

Categorical terms should be additive bonuses or penalties. That keeps them easy to reason about:

```text
+1 if dataset_from == "gt"
-0.5 if model == "baseline"
```

More advanced categorical transforms, such as mapping many labels to many weights, can be added later as a compact table editor if needed.

## UI Shape

Add a "Derived score" card near the top of the Metrics panel.

Expected controls:

- score name input
- numeric term rows with metric selector, weight input, missing-value mode, remove button
- categorical bonus rows with categorical selector, value selector, weight input, remove button
- intercept input
- expression preview generated from the structured rules
- "Rank by score" action that sets sort to the derived metric descending

The derived score should then appear in the normal Metric selector and toolbar Sort menu.

The user should not have to leave the Metrics panel to rank by the new score. The sequence should be:

1. open Metrics
2. create or edit `new_score`
3. click "Rank by score"
4. inspect the gallery in that order

The same score should remain selectable in the toolbar Sort menu because toolbar sort is the canonical place for gallery order. The Metrics panel creates and edits the metric; the toolbar remains the global sort control.

## Tradeoffs Considered

### Metrics Panel vs New Tab

Keeping this in Metrics is the better first design. The score is built from metrics and categoricals, and the output is a metric. A new tab would create a separate mental model for something that should reuse the existing one.

A new tab might make sense only if the feature grows into a larger rubric editor with saved presets, multi-score comparisons, calibration plots, or batch exports. That is not needed for the first useful version.

### Client-Side Evaluation vs Backend Evaluation

Client-side evaluation is the smallest useful implementation:

- no API contract change for the first cut
- reuses existing item payloads
- easy to unit test in frontend model code
- works immediately for loaded folder/search results

The tradeoff is paging. If only the first 5,000 rows are loaded, sorting by a derived score only sorts those loaded rows. That is acceptable for an initial browse-side feature if the UI communicates it clearly, but it is not enough for "top N across a 40k dataset".

Backend evaluation is the right long-term solution for large datasets:

- score can be computed across the full scope
- `/folders` can return a globally sorted window
- scrolling can remain paged without lying about order

The tradeoff is a larger API and storage change. The structured spec keeps that future path open.

### Broaden `metrics` vs Add Formula Inputs

Broadening `metrics` is simpler for users and for the existing UI. Numeric fields become sortable/filterable without another concept.

The risk is clutter. If a table has many numeric bookkeeping columns, the Metrics selector can become noisy. This can be managed with exclusion rules for IDs, internal columns, dimensions, row indices, and obvious counters.

A separate `formula_inputs` payload would be more precise, but it creates more UI plumbing and does not automatically reuse histograms, metric sort, or metric rail. For the alpha, broadening `metrics` is more pragmatic.

### Persist Definitions vs Session-Only Scores

Persisting definitions in `ViewState` is important because a derived score is part of how the user is looking at the data. A Smart Folder that sorts by `new_score` is not meaningful if `new_score` disappears on reload.

The tradeoff is that saved views can break when a different table or source column no longer exposes the referenced fields. That should be handled by validation: keep the definition, show which terms are missing, and disable ranking by the score until fixed.

## Large Dataset Behavior

The first implementation can compute derived scores client-side for loaded items. That matches current frontend sorting behavior and keeps the change small.

There is one limitation: recursive table browsing is paged. A client-side derived sort is globally correct only for the rows already loaded. If users need immediate global ranking over a large dataset, the next step should move sorted windows into the backend:

- accept sort specs and derived metric specs on `/folders`
- compute the score across all rows in scope
- return the requested page in sorted order

The structured `DerivedMetricSpec` above is suitable for both client-side and backend evaluation.

## Effect Of Commit 6c69bf0

The latest commit, `6c69bf0 fix: large preloads when using bigger datasets`, adds table source-column detection, warnings, and a UI/API path for switching which table column supplies images.

Relevant effects:

- source-column switching rebuilds `TableStorage`, clears frontend file/thumb caches, invalidates queries, resets selection/viewer state, and returns to `/`
- this does not change metric sorting, metric key selection, or derived-score feasibility directly
- it does add another invalidation path that derived metric state must tolerate
- it does not solve the `q1` through `q6` exposure issue; those columns still will not become metric inputs unless browse/table launch explicitly includes them

The biggest design implication is table projection. For large Parquet launches, Lenslet intentionally avoids loading every column. A derived-score builder cannot rely on arbitrary table fields being present after startup. The first cut should therefore make formula inputs part of the browse column selection contract:

- include numeric scalar formula fields in the projected browse columns
- expose them as metrics or as a separate formula-input payload
- include selected low-cardinality string categoricals in the projected browse columns

If the user switches the table source column, derived score definitions can remain in `ViewState`, but the UI should validate them against the new `metricKeys` and `categoricalKeys`. Missing inputs should disable ranking by that score until the user edits or removes the broken terms.

## Failure Modes

The feature should make these cases explicit:

- a numeric input column is missing from the current dataset
- a categorical input column is missing from the current dataset
- a selected categorical value no longer appears in the current scope
- a score produces no valid values
- a score is selected for sorting while some items have missing values
- a large recursive folder is only partially loaded, so client-side ordering is not global

Silent fallback would be worse than friction here. Users need to trust that the sorted order corresponds to the rubric they created.

## Testing Notes

Useful focused tests:

- derived evaluator computes weighted numeric terms
- categorical bonus/penalty terms apply only on exact matches
- missing policies behave as expected
- derived metric key is injected without mutating source items in-place
- metric sorting handles derived null scores after valid scores
- saved views preserve derived metric definitions
- invalid saved definitions are retained but reported as unavailable
- table ingestion exposes `q1`-style numeric scalar fields after the metric exposure cutover

Browser acceptance should cover the main workflow: create a score in Metrics, rank by it, verify the first visible cards follow the expected order, reload, and verify the saved view can restore the ranking.

## Suggested First Cut

1. Broaden table browse metric exposure so numeric scalar columns like `q1` through `q6` are available to the Metrics panel.
2. Add derived metric types to frontend view state.
3. Add a pure frontend evaluator that injects derived metric values into browse items before filters and sorts run.
4. Add the Metrics panel score builder.
5. Persist derived metric definitions through local settings and Smart Folders.
6. Add focused unit tests for evaluator behavior, missing values, sort integration, and saved-view persistence.

Backend sorted windows can follow once the local workflow is proven.
