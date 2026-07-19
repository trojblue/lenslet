## Verdict

The plan is **directionally right**, but I would **not ship it as-is**. The core idea is good: derived scores should become numeric metrics, not a separate ranking mode. The structured spec is the right call. Client-side evaluation is a reasonable first cut.

The changes I would require are mostly integration safeguards: sort semantics, projection discipline, persistence normalization, invalid-state handling, and feature-mode gates. Without those, this feature will work in the happy path but create confusing failures when combined with saved views, table source switching, partial recursive loads, similarity mode, or missing values.

I reviewed the uploaded repo paths directly. I did not modify the repo or run the full test suite.

---

## What is already good in the plan

The strongest parts of the plan are worth keeping:

1. **Treating the score as a first-class metric** is exactly the right integration model. The frontend already has `metrics?: Record<string, number | null>` on `BrowseItemPayload`, folder-level `metric_keys`, metric sort specs, and metric range filters in `frontend/src/lib/types.ts:18`, `frontend/src/lib/types.ts:34`, and `frontend/src/lib/types.ts:216-233`.

2. **Putting the builder in the Metrics panel** fits the product model. The Metrics panel already receives `items`, `filteredItems`, `metricKeys`, `categoricalKeys`, selected metric state, and filter callbacks in `frontend/src/features/metrics/MetricsPanel.tsx:12-24`.

3. **Avoiding a formula parser** is the right first-cut decision. A structured weighted-sum spec will be easier to validate, persist, and eventually send to the backend.

4. **Client-side first, backend global sort later** is reasonable. The frontend already sorts loaded items locally in `frontend/src/features/browse/model/apply.ts:29-42`, and recursive browse currently loads a bounded first page of 5,000 items from `useAppDataScope` at `frontend/src/app/hooks/useAppDataScope.ts:26` and `frontend/src/app/hooks/useAppDataScope.ts:128-133`.

So the proposal is not wrong. It just needs some hardening before implementation.

---

## Required changes before implementation

### 1. Fix metric sort null handling first

This is the biggest concrete blocker I found.

Current metric sort puts missing values last for ascending:

```ts
if (va == null) return 1
if (vb == null) return -1
```

That lives in `frontend/src/features/browse/model/sorters.ts:20-29`.

But `applySort` handles descending by sorting ascending and then reversing the whole array:

```ts
const arr = [...items].sort(cmp)
return sort.dir === 'desc' ? arr.reverse() : arr
```

That is `frontend/src/features/browse/model/apply.ts:41-42`.

So if derived scores are sorted descending, missing or null scores move to the **front**, exactly opposite of the proposed rule: “sort after scored items.”

This should be fixed before derived metrics land. Make metric sorting direction-aware instead of reversing the final array, or use a comparator that always places invalid values last regardless of direction.

Also treat `NaN`, `Infinity`, and `-Infinity` as invalid everywhere. Right now several paths only check `Number.isNaN`, for example:

* metric collection: `frontend/src/features/metrics/model/metricValues.ts:26-28` and `frontend/src/features/metrics/model/metricValues.ts:44-46`
* metric rail activation: `frontend/src/app/model/appShellSelectors.ts:8-13`
* metric scrollbar: `frontend/src/features/browse/components/MetricScrollbar.tsx:19-23`
* metric range filter does not guard `NaN` at all: `frontend/src/features/browse/model/filters.ts:100-106`

Use a shared helper like:

```ts
export function finiteMetricValue(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
```

Then use it in sort, filters, histograms, metric rail, and the derived evaluator.

---

### 2. Inject derived metrics before metric-key resolution, filtering, and sorting

The plan says “before filtering and sorting,” which is right, but in this repo the ordering needs to be exact.

Today `useAppDataScope` builds `poolItems`, then resolves `metricKeys`, then applies filters and sort:

* pool items: `frontend/src/app/hooks/useAppDataScope.ts:190-196`
* metric/categorical keys: `frontend/src/app/hooks/useAppDataScope.ts:221-226`
* filters and sort: `frontend/src/app/hooks/useAppDataScope.ts:228-235`

Derived evaluation should happen after raw `poolItems` are assembled, but **before**:

* `resolveMetricKeys`
* `applyFilters`
* `applySort`
* `hasMetricSortValues`
* metric rail rendering
* Metrics panel data

Otherwise a saved sort like `@derived/dm_123` can be reset before the derived key appears. AppShell currently resets any metric sort whose key is not in `metricKeys` at `frontend/src/app/AppShell.tsx:595-602`.

The safer flow is:

```ts
rawPoolItems
  -> apply local star overrides
  -> compute source metric/categorical keys
  -> validate derived specs against source keys
  -> inject derived metric values into cloned item objects
  -> append valid derived keys to metricKeys
  -> apply filters
  -> apply sort
```

Do not mutate React Query payloads or source items in place. The plan already notes this in tests; I would make it a hard rule. Mutation would leak stale `@derived/...` metrics into cached folder/search items after the spec changes or is deleted.

---

### 3. Use stable IDs for derived metric keys, not names

The proposed key format is:

```text
@derived/new_score
```

I would change that to an opaque stable ID:

```text
@derived/dm_8f3a...
```

The display name can still be `new_score`.

Reason: if the metric key is derived from the editable name, renaming a score can break saved sorts, filters, Smart Folders, selected metric state, and metric rail state. You can update those references during rename, but it is easy to miss one. A stable ID avoids that entire class of bugs.

Recommended model:

```ts
export type DerivedMetricSpec = {
  version: 1
  id: string
  name: string
  intercept: number
  numericTerms: Array<{
    metricKey: string
    weight: number
    missing: 'zero' | 'invalid'
  }>
  categoricalTerms: Array<{
    categoricalKey: string
    equals: string
    weight: number
  }>
}

export function derivedMetricKey(spec: DerivedMetricSpec): string {
  return `@derived/${spec.id}`
}
```

I would also reserve the `@derived/` prefix and reject or escape any real source metric with that prefix.

---

### 4. Remove or precisely define `missing: 'omit'`

The proposed missing policy has:

```ts
missing: 'zero' | 'omit' | 'invalid'
```

For a simple weighted sum, `omit` and `zero` are effectively the same unless you introduce normalization. Both mean “this term contributes nothing.”

That ambiguity will confuse users and complicate validation.

For the first cut, I would use only:

```ts
missing: 'zero' | 'invalid'
```

Where:

* `zero`: missing/non-finite input contributes `0`
* `invalid`: the whole derived score becomes `null`

If you later add weighted averages, then add an explicit aggregation mode:

```ts
aggregation: 'sum' | 'weightedAverage'
```

At that point `omit` can mean “exclude missing terms from the denominator.” Until then, leave it out.

---

### 5. Do not allow derived metrics as inputs in v1

The metric selector should exclude keys starting with `@derived/` as numeric inputs.

Otherwise you immediately introduce:

* dependency ordering
* cycles
* stale values
* confusing saved-spec behavior
* backend evaluation complexity later

For v1, derived metrics should be leaf outputs only. Derived-on-derived can be added later with a dependency graph and cycle detection.

---

### 6. Broaden table metric exposure carefully, not globally

The plan correctly identifies the backend issue: `q1`, `q2`, `q3` will not currently appear as metric inputs.

In the repo, metric-like table columns are detected by name keywords such as `score`, `quality`, `rating`, `prob`, and `confidence` in `src/lenslet/storage/table/index.py:20-33`. Candidate metric columns must pass `is_metric_column_name` at `src/lenslet/storage/table/index.py:75-99`, and `q1` will fail that.

Projected Parquet browse columns have the same constraint:

```py
if not is_metric_column_name(column):
    continue
if not is_numeric_browse_column(schema, column):
    continue
if not is_browse_scalar_column(schema, column):
    continue
add(column)
```

That is `src/lenslet/storage/table/launch.py:310-319`.

However, I would **not** simply redefine `is_metric_column_name` to mean “all numeric scalar columns.” That helper is also used to hide metric-like columns from inspector table fields in `src/lenslet/storage/table/index.py:172-197` and `src/lenslet/storage/table/storage.py:1454-1472`. A broad change there can unexpectedly remove numeric table fields from the inspector and clutter the Metrics panel.

Better:

* add a new helper such as `is_formula_numeric_column(schema, column)`
* use it in Parquet projection and TableStorage metric exposure
* keep strong exclusions for IDs, row indices, dimensions, paths, sizes, timestamps, booleans, internal columns, and bookkeeping counters
* include obvious short eval fields like `q1`, `q2`, `q3`
* consider a cap or launch option if a table has hundreds of numeric columns

The key point is: make formula input exposure part of the browse projection contract, but do not accidentally undo the large-preload fix.

---

### 7. Add storage-level metric keys for table mode

Categorical keys already have a storage-level escape hatch:

```py
storage_keys = _categorical_keys_from_storage(storage)
if storage_keys is not None:
    return storage_keys
```

That is `src/lenslet/web/browse.py:219-221`.

Metric keys do not have the same equivalent. Recursive folder payloads currently derive metric keys from the current snapshots/window at `src/lenslet/web/browse.py:196-208` and `src/lenslet/web/browse.py:590-596`.

That means a projected numeric column could be part of the table schema but fail to appear in `metric_keys` if it has no non-null value in the currently loaded window. For saved derived specs, this can create false “missing input” errors.

I would add something like `TableStorage.metric_keys()` returning schema-backed metric columns plus known metrics-map keys where available, then have `_metric_keys_for_folder` prefer that when present, mirroring categoricals.

---

### 8. Persist derived specs atomically with sort and filters

`ViewState` currently contains only:

```ts
filters
sort
selectedMetric?
```

See `frontend/src/lib/types.ts:239-243`.

Smart Folders store `view: ViewState` at `frontend/src/lib/types.ts:247-252`, and activation sets the stored view back into state at `frontend/src/app/hooks/useSmartFolders.ts:87-91`.

Local settings currently persist `sortSpec`, `filterAst`, and `selectedMetric`, but not derived specs, in `frontend/src/app/hooks/usePersistedAppShellSettings.ts:55-83` and restore them at `frontend/src/app/hooks/usePersistedAppShellSettings.ts:172-189`.

Add:

```ts
derivedMetrics?: DerivedMetricSpec[]
```

to `ViewState`, and persist it in the same transaction as sort/filter/selectedMetric. This matters because a persisted sort key like `@derived/dm_123` is meaningless unless the spec is restored at the same time.

Backend Smart Folder storage probably does not need a schema change because `/views` accepts arbitrary JSON objects: `src/lenslet/web/models.py:306-308`.

---

### 9. Keep invalid saved definitions visible, but avoid silent destructive behavior

The plan says invalid definitions should be retained and reported. Good. I would extend that to filters too.

Current metric range filters simply check `item.metrics?.[key]`; if the key is missing, every item fails that filter. See `frontend/src/features/browse/model/filters.ts:100-106`.

That means a saved Smart Folder with a derived metric filter can silently produce an empty gallery if the derived spec is invalid or unavailable.

At minimum, the UI needs a visible “score unavailable” state. Ideally, unavailable derived-metric filters should become disabled filter chips rather than silently filtering everything out. If you keep the current behavior, then show a blocking warning explaining that the active filter references an unavailable derived score.

Silent zero results will feel like data loss.

---

### 10. Respect existing disabled-sort modes

Toolbar sorting is disabled when similarity mode is active or indexing has locked sort:

```tsx
sortDisabled={similarityActive || indexingBrowseMode.sortLocked}
```

That is `frontend/src/app/AppShell.tsx:924-926`.

Similarity mode also bypasses normal sorting entirely in `useAppDataScope`: when `similarityState` exists, it only applies filters and does not call `applySort` at `frontend/src/app/hooks/useAppDataScope.ts:228-231`.

So the “Rank by score” button must be disabled in:

* similarity mode
* scan-stable/indexing sort-locked mode
* invalid derived spec state
* no valid score values

The button should not set sort behind the user’s back when the gallery will ignore it.

---

## UI adjustments I would make

The planned UI shape is good, but a few details matter.

First, the Metrics panel currently returns early when there are no metrics or categoricals:

```tsx
if (!metricKeys.length && !categoricalKeys.length) {
  return ...
}
```

That is `frontend/src/features/metrics/MetricsPanel.tsx:78-88`.

A Derived Score card should still render in that state, even if disabled, because saved invalid definitions need somewhere to appear.

Second, the toolbar and metric selector currently display raw metric keys. Toolbar metric labels come from `metricKeys.map((key) => ({ label: key }))` in `frontend/src/shared/ui/Toolbar.tsx:201-203`, and the metric selector renders `{key}` in `frontend/src/features/metrics/components/MetricRangePanel.tsx:109-110`.

That will look bad for `@derived/dm_123`.

Add a frontend display-name helper or map:

```ts
type MetricDisplayNames = Record<string, string>
```

Use it in:

* toolbar sort menu
* Metrics panel selector
* histogram/card titles
* filter chips
* inspector metrics
* metric rail tooltip/title if present

Do **not** use `item.metric_labels` for this. In this repo, `metric_labels` are interpreted as categorical metric labels in `collectMetricCategoriesByKey`, especially `frontend/src/features/metrics/model/metricValues.ts:91-95`. Using them for derived display names would accidentally make numeric derived scores look like categorical buckets.

Third, consider making the builder draft-based. Updating weights on every keystroke could resort the gallery and invalidate virtualized layout repeatedly. A good first UX is:

* edit draft terms locally
* show formula preview and valid-count preview
* apply/update the spec on blur, debounce, or explicit “Apply”
* “Rank by score” applies and sets sort descending

When ranking by a derived score, also set `selectedMetric` to that derived key so the histogram follows the score.

---

## Performance review

Client-side evaluation is fine for the current loaded-window sizes if implemented carefully.

The current recursive page size is 5,000 items (`frontend/src/app/hooks/useAppDataScope.ts:26`), and the backend recursive window cap is 10,000 (`src/lenslet/web/browse.py:231-232`). A weighted sum over 5,000–10,000 items and a handful of terms is cheap; sorting will cost more than scoring.

The main performance risks are not the evaluator. They are:

1. **Projection bloat**: loading too many numeric Parquet columns after broadening metric exposure.
2. **UI bloat**: hundreds of metric keys in the Metrics panel and Toolbar.
3. **Live resort churn**: resorting the gallery on every input keystroke.
4. **Deep cloning**: copying every item and metrics object when there are no derived metrics or when a spec has not changed.

Implementation rule:

* if there are no valid derived specs, return the original item array
* when injecting, clone only each item’s `metrics` map, not the whole payload deeply
* never write derived values into React Query cache
* use `Number.isFinite`
* debounce or transition expensive edits

The partial-load warning is also important. `useAppDataScope` already knows whether there are more items via `hasMoreFolderItems` at `frontend/src/app/hooks/useAppDataScope.ts:243-248`. If a derived metric is selected for sort and `data.items.length < data.total_items`, show:

> Ranking is over the loaded 5,000 of 40,000 items.

That warning should appear near the Derived Score card and/or toolbar sort state.

---

## Revised first-cut implementation order

I would reorder the proposed first cut like this:

1. **Fix metric finite/missing behavior**

   * direction-aware metric sort
   * missing values always last for asc and desc
   * `NaN`/infinity treated as missing in sort, filters, histograms, metric rail

2. **Add backend formula-eligible numeric exposure**

   * do not globally redefine `is_metric_column_name`
   * add explicit formula/browse numeric eligibility
   * keep Parquet projection bounded
   * add `q1`/`q2`/`q3` tests
   * add storage-level `metric_keys()` if possible

3. **Add derived metric types and normalization**

   * `version`
   * stable `id`
   * display `name`
   * `@derived/<id>` key
   * finite weights/intercept only
   * no derived-as-input in v1
   * no ambiguous `omit`

4. **Add pure evaluator and validation model**

   * no mutation
   * returns augmented items plus status
   * valid count / invalid count
   * missing input diagnostics
   * partial-load warning metadata

5. **Wire evaluator into `useAppDataScope`**

   * before filters and sort
   * before effective `metricKeys`
   * works for folder/search pools
   * filters may still apply in similarity mode, but ranking remains disabled there

6. **Persist specs**

   * `ViewState.derivedMetrics`
   * localStorage settings
   * Smart Folder roundtrip
   * invalid specs retained, not auto-deleted

7. **Add the Metrics panel builder**

   * draft editing
   * formula preview
   * valid/invalid item count
   * rank button sets sort and selected metric
   * disabled states for similarity/sort-locked/invalid/no-values
   * display names for derived keys

8. **Add acceptance and regression tests**

   * descending missing values last
   * evaluator weighted terms
   * categorical exact match
   * missing policy
   * no mutation
   * saved Smart Folder restores derived sort
   * invalid saved spec remains visible
   * q1-style numeric columns exposed
   * partial recursive load warning

---

## Bottom line

Keep the architecture, but tighten the integration contract.

The plan’s central idea is right: derived scores should become normal numeric metrics. The unsafe parts are mostly around the edges: current descending metric sort is wrong for nulls, `q1` fields are not projected as metrics, invalid saved derived filters can silently empty the gallery, and display/persistence need stable IDs rather than name-based keys.

With those changes, this can integrate cleanly with the existing gallery, Metrics panel, toolbar sort, metric rail, inspector, Smart Folders, and the recent table source-column switching work.
