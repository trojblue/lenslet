I would **approve the direction**, but I would **not approve this plan as implementation-ready yet**.

The core diagnosis is right: the bug is not a grid-loading bug; it is a query-ownership bug. In this codebase, `useAppDataScope.ts` loads a finite raw page through `/folders`, then treats `applyFilters` and `applySort` over that loaded page as authoritative. That is exactly how a valid category outside the first raw page becomes an apparent empty gallery. Moving folder/table browse semantics to the backend is the right fix.

But the plan still has several red flags where a plausible implementation could quietly recreate the same class of bug, just in more sophisticated clothing.

## Highest-risk red flags

### 1. The filter contract is not precise enough

The plan says “categorical, metric, star, text, date, and dimension filters,” but the codebase already has exact frontend semantics in `frontend/src/features/browse/model/filters.ts`. Those details matter.

For example, current frontend behavior includes:

* `star ?? 0`, so missing star is treated as `0`.
* `notesContains` on missing notes returns `false`.
* `notesNotContains` on missing notes also returns `false`, which is slightly non-intuitive but currently real.
* URL filters use `item.source ?? item.url ?? ""`, not “source OR url.”
* date-only max bounds are expanded to the end of the day.
* metric filters reject missing, null, and non-finite values.
* metric sorts place missing/non-finite values after valid values for both ascending and descending.
* metric sort tie-breaks by name.

If the backend evaluator merely implements “reasonable” semantics, you will get subtle regressions. The plan should require a **golden parity suite** copied from the existing frontend filter/sort fixtures, including the weird edge cases. A good backend-filtering system is not just “server-side”; it is **contracted, validated, and constrained**. Mature API frameworks treat filtering/search/ordering as server-side concerns and recommend explicitly restricting allowed ordering fields rather than accepting broad arbitrary input. ([Django REST Framework][1])

My recommendation: add a dedicated backend filter model with discriminated clauses and explicit validators, then add tests that say: “for this serialized frontend AST, these exact rows match.” Do not accept loose dictionaries where malformed or multi-key clauses can slip through.

### 2. The table implementation must stay row-id based all the way until the final slice

The plan says table storage should evaluate over row ids and materialize only the returned window. That is correct, and the codebase is already set up for it:

* `TableRowStore.rows_in_scope(...)`
* `TableRowStore.rows_in_scope_window(...)`
* `TableRowStore.materialized_item_count`
* `TableStorage._metrics_for_row(...)`
* `TableStorage.facet_summary_for_scope(...)`
* `TableStorage.search(...)`

Those are the right primitives.

The red flag is sidecar-dependent fields: stars, notes, and possibly mutated metadata. Those are not purely row-store fields. A naive implementation may call `materialize_item()` for every candidate row just to evaluate star or notes filters. That would satisfy correctness while violating the performance intent.

The plan should explicitly require row-level helpers for sidecar lookup, for example:

* get canonical path for row id;
* read sidecar state without creating/mutating it;
* evaluate star/notes from that sidecar state;
* only call `materialize_item(row_id)` after filtering, sorting, and slicing.

Tests should assert that a filtered query over a six-row fixture with limit two materializes exactly two items, not six. There should also be a larger test where a star or notes filter is used, because that is where accidental materialization is most likely.

### 3. Sort stability is underspecified

Offset pagination only works correctly if the backend ordering is total and deterministic. The plan mentions deterministic random ordering, but it does not fully specify tie-breakers.

Current frontend sorting is not strong enough as a backend contract:

* name sort can tie;
* added date can tie;
* metric values can tie;
* missing metrics are grouped;
* seeded random order needs to be stable across offset windows.

For backend pagination, every sort should end with a stable final tie-breaker, probably canonical path or row id. Otherwise page 1 and page 2 can overlap or skip items when Python sort order, provider order, or row iteration order changes.

For random sorting, I would avoid reproducing the frontend’s full Fisher–Yates shuffle over item payloads. Instead, compute a deterministic per-row random score from `(seed, stable_row_identity)` and sort by that score plus path/row id. That gives stable pages without materializing all payloads. It may not match the old frontend random order, but that is acceptable if the backend contract defines the new behavior clearly.

This is a known pagination concern: paginated APIs commonly return a total count plus a result window, and cursor-style pagination relies on a unique, stable ordering to avoid duplicate or missing results as data changes. Even if you keep offset/limit for v1, you still need the same discipline around deterministic ordering. ([Django REST Framework][2])

### 4. The response shape should not reuse old `total_items` semantics casually

Current backend `BrowseFolderPayload` has `total_items`, and current frontend code already uses a mix of:

* `data.items.length`
* `data.total_items`
* locally computed `filteredCount`
* raw loaded page length

That ambiguity is part of the bug.

The plan says the new response should make it impossible to confuse loaded count with filtered total. Good. But that should be enforced structurally.

I would strongly recommend a separate response model, not a lightly modified `BrowseFolderPayload`:

```ts
{
  path: string
  generated_at: string
  generation_token: string | number

  scope_total: number
  filtered_total: number

  offset: number
  limit: number
  items: BrowseItem[]

  folders: BrowseFolderEntry[]

  metric_keys: string[]
  categorical_keys: string[]

  facets?: BrowseFacetPayload
}
```

Avoid `total_items` on the new endpoint. Name the counts so the frontend cannot accidentally treat loaded item count as authoritative.

I would also include either a canonicalized query echo or request token in the response. The frontend already has stale-response issues around path/filter/sort/search changes; the new endpoint should make stale replacement easy to detect.

### 5. Facet semantics are still too muddy

The plan says:

* `population_count` means raw scoped count.
* `filtered_total` means rows after text and filters.
* per-value `filtered_count` is optional.

That is a reasonable v1 contract, but it clashes with the current frontend metrics code.

In the current Metrics panel flow, backend facets provide raw population options, but filtered counts are derived from `filteredItems` when the item population is considered complete. After backend pagination, `filteredItems` will usually be only the returned window, not the full filtered population. That creates a trap: the UI could show per-value counts derived from the current page and accidentally present them as truth.

So either:

1. do not show per-value filtered counts in backend browse mode unless the backend returns authoritative `filtered_count`; or
2. implement authoritative per-value filtered counts now.

The plan currently wants backend-owned counts but also says per-value filtered counts are optional. That is fine only if the frontend is explicitly changed to stop showing loaded-window counts as filtered truth.

This is one of the most likely places the old bug will survive.

### 6. Search must be folded into the same backend query path

The plan says query order is:

> scope, text search, filters, sort, offset, limit.

That is correct.

But the current frontend has a separate search path in `useAppDataScope.ts`: when there is a search query, it uses `useSearch(...)`, then applies local filters/sorts over those results. If that remains, then text search plus categorical/metric filters can still be evaluated over a bounded result set instead of the full browse scope.

The hard cutover must include search. Normal folder/table browse should not have one backend endpoint for “folder” and a separate locally-filtered path for “search.” `/folders/query` should accept the text query and evaluate it before filters and sort.

The good news: `TableStorage.search(...)` already contains useful row-level search behavior over path/name/source/url and sidecar text. The new evaluator should reuse or port that logic rather than maintaining two definitions of search truth.

### 7. Frontend query keys and cancellation need a sharper design

The plan says to add React Query keys and handle cancellation/stale responses. That is right but too vague.

The current frontend has manual state merging in `useAppDataScope.ts`: `setData`, `mergeFolderPage`, `pageRequestTokenRef`, `loadedFolderItems`, and local filtering. If you keep that structure and bolt `/folders/query` onto it, the implementation will be fragile.

A better shape is a dedicated backend browse query hook, ideally using an infinite-query pattern:

```ts
[
  "folder-query",
  {
    path,
    recursive,
    filters: canonicalFilters,
    sort: canonicalSort,
    textQuery,
    randomSeed,
    limit
  }
]
```

Then each page request uses the same canonical query plus the next offset.

TanStack Query’s own guidance is that query keys should include every variable the query function depends on, and keys are deterministically hashed for serializable objects, while array item order remains significant. ([tanstack.com][3]) That matters here: filter AST order, sort spec, path, recursive flag, search text, seed, offset/window size, and unsupported derived states all need deliberate keying or canonicalization.

Cancellation should also use the query function’s abort signal if possible. TanStack Query provides an `AbortSignal` to query functions and aborts it when a query becomes stale or inactive if the fetch consumes the signal. ([tanstack.com][4]) The current `fetchJSON` creates its own controller; the new API path should either accept React Query’s signal or very carefully bridge it into the existing request-budget cancellation system.

### 8. Derived metrics blocking is correct, but the UI behavior is underspecified

The plan is right to block derived metric filters/sorts rather than evaluating them locally over the loaded window. That would violate the entire backend-owned query contract.

But the codebase has real derived metric machinery in `useAppDataScope.ts`:

* derived metrics are evaluated frontend-side;
* derived metric keys are added to items;
* filters and sorts can refer to `@derived/...`.

The plan should specify exactly what happens when a user activates a derived metric filter or sort in backend browse mode:

* Is the filter chip rejected?
* Is it shown but disabled?
* Is there a banner?
* Does the query omit the derived clause, or does the whole query fail closed?
* Does Metrics still display derived metric panels?
* Does similarity mode keep allowing derived metrics locally?

My preference: fail closed for normal folder/table browse. Show a visible “Derived metric filtering is unavailable in backend browse mode” warning and do not send a misleading query that silently omits the clause. Similarity mode can remain separate if it is explicitly bounded top-K behavior.

### 9. Sidecar mutation invalidation is a bigger risk than the plan makes it sound

Star and notes filters depend on sidecar state. In the table storage code, source-backed browse generation appears effectively stable: `browse_generation()` returns `0`, while `browse_cache_signature()` is based on table/source selection state, not necessarily sidecar edits.

The plan defers query caching, which helps. But frontend caching still matters. `api.getFolder` currently has a `staleTime` in the hooks layer, and star/notes mutations must invalidate any backend browse query and facet data that could depend on sidecar state.

The plan says:

> Star filters must reflect persisted sidecar state after mutation/refetch and must not rely on local optimistic membership.

That is right, but it should be stronger:

* optimistic updates may patch visible item presentation only;
* membership/order/count/facet truth must come from invalidated/refetched backend query data;
* any future backend query cache must include a sidecar version or be invalidated by sidecar mutations;
* tests should cover an item entering and leaving a star-filtered result set after mutation.

Otherwise a star edit can produce exactly the same class of stale authoritative UI bug.

### 10. The non-table fallback may violate the performance and safety intent

The plan says:

> Non-table storage can use a generic backend fallback over `items_in_scope` for correctness.

That is acceptable only if bounded and explicit.

The existing recursive browse path has hard limits and windowed access to avoid materializing too much. A naive fallback over all `items_in_scope` can become expensive or unsafe on large folder trees.

I would specify one of these:

* table storage supports the full backend query contract;
* non-table fallback is allowed only under an existing hard limit;
* large unsupported scopes return a clear 413/422-style response;
* or fallback iterates lazily and materializes only what it must.

“Correct but materializes everything” is a dangerous footgun here because the endpoint will become the default browse path.

### 11. Returning facets on every browse query could become the new performance bottleneck

The plan says the query response includes metric histograms, category populations, categorical value counts, keys, totals, folders, and item windows.

That is convenient, but it may be too much for every browse request.

Right now, facets are fetched separately through `/folders/facets` and the Metrics panel only asks for them when needed. That separation is valuable. If `/folders/query` recomputes and returns facets on every filter change, search keystroke, sort change, and pagination request, you may fix correctness while making browse feel heavy.

I would split the contract:

* `/folders/query`: result window, `scope_total`, `filtered_total`, keys, folders.
* `/folders/facets` or `/folders/query/facets`: raw population counts and, later, filtered facet counts.
* Or add `include_facets: false | "raw" | "filtered"`.

This is especially important because the plan explicitly defers query-result caching and parquet predicate pushdown.

### 12. The storage/web dependency boundary needs care

The plan says storage gains a capability like `query_browse_scope(...)`.

That is good, but do not make `TableStorage` import Pydantic web request models from `src/lenslet/web/models.py`. That would couple storage to the web API layer.

Better:

* define API request/response schemas in `web/models.py`;
* define storage-neutral query dataclasses or protocols in a lower-level module, perhaps `src/lenslet/browse/query.py` or `src/lenslet/storage/base.py`;
* have the route adapt Pydantic models into the storage-neutral query spec;
* have storage return a storage-neutral query result;
* have the route convert that into the public API response.

That gives you a stable internal contract and avoids leaking web concerns into table storage.

## Things the plan gets right

The important parts are genuinely right:

* It identifies the true failure mode in `useAppDataScope.ts`.
* It rejects a grid load-more workaround.
* It makes pagination a transport detail rather than a truth mechanism.
* It blocks derived metric filters/sorts instead of allowing a local fallback.
* It says query caching should be deferred.
* It recognizes that table storage already has efficient counting/facet primitives.
* It requires real scenario validation with the reported parquet and `source_column = v0603_ema14k_image_url`.

Those are strong foundations.

The issue is not the direction. The issue is that the plan is still loose around the exact contracts where bugs hide.

## Suggested revised architecture

I would shape the implementation like this.

Backend:

```text
POST /folders/query
  -> validate and canonicalize request
  -> convert API model to BrowseQuerySpec
  -> build_browse_query(storage, spec, to_item)
       if storage supports query_browse_scope:
           use storage-native row-id evaluator
       else:
           use bounded fallback or return unsupported-too-large
  -> return BrowseQueryResponse
```

Storage:

```text
query_browse_scope(spec) -> BrowseQueryResult
```

For `TableStorage`, implementation should be:

```text
candidate row ids in scope
  -> apply text query using row fields + sidecar text
  -> apply filters using row fields + metrics + categoricals + sidecar
  -> compute filtered_total
  -> sort matching row ids with stable tie-breaker
  -> slice offset/limit
  -> materialize only sliced rows
```

Frontend:

```text
useBackendBrowseQuery({
  path,
  recursive,
  filters: canonicalFilters,
  sort: canonicalSort,
  textQuery,
  randomSeed,
  limit
})
```

Then normal folder/table browse renders only:

* `query.items`
* `query.filtered_total`
* `query.scope_total`
* `query.metric_keys`
* `query.categorical_keys`
* backend facet payloads where available

Local `applyFilters` and `applySort` should remain only for:

* pure UI tests,
* request preview/serialization helpers,
* similarity top-K mode,
* maybe small non-authoritative client-side displays explicitly marked as such.

## Specific acceptance tests I would add

These should be blocking.

1. **Backend late-match categorical test**

Six table rows. Limit two. Category appears only on rows four and five. Query at offset zero returns those two rows, `scope_total = 6`, `filtered_total = 2`.

2. **Evaluator parity tests**

Use serialized frontend `FilterAst` fixtures for:

* missing category;
* missing metric;
* non-finite metric;
* `starsIn` with missing star;
* `notesNotContains` with missing notes;
* date-only upper bound;
* URL filter using source-vs-url precedence;
* width/height zero and missing values.

3. **Sort stability tests**

* metric asc/desc with missing values;
* duplicate metric values;
* duplicate names;
* duplicate dates;
* final tie-breaker by path or row id;
* seeded random returns stable non-overlapping offset windows.

4. **Materialization tests**

Assert table row store materialization count equals returned window length, not filtered candidate count or scope size.

5. **Sidecar mutation test**

Star an item, refetch backend query with `starsIn`, verify membership and `filtered_total`. Unstar it, refetch, verify it disappears.

6. **Frontend no-local-authority tests**

For normal folder/table browse, tests should fail if membership/order calls local `applyFilters` or `applySort`.

7. **Facet false-count test**

A category absent from the visible returned window but present in backend facets should still appear. The UI must not show a page-local filtered count as authoritative.

8. **Search-composed-with-filter test**

Text query plus categorical filter should be evaluated backend-side over full scope before offset/limit.

9. **Derived metric blocked test**

A filter or sort using `@derived/...` in normal browse mode shows a visible unavailable state and does not run a local loaded-window fallback.

## Process/documentation concern

The plan contains a lot of agent-process material: subagents, `better-code`, review routines, sprint ceremony, and implementation-agent instructions. That may be useful operationally, but it obscures the engineering contract.

For an implementation plan, I would separate:

* **architecture contract**
* **API/schema**
* **storage algorithm**
* **frontend migration**
* **acceptance tests**
* **manual validation**
* **agent/process appendix**

Right now the core invariants are mixed with workflow instructions. That makes it easier for an implementer to “complete the sprint” while missing a semantic invariant.

## Final verdict

The plan is directionally sound and probably the right repair strategy. I would not replace it with a frontend workaround.

But I would block implementation until these points are tightened:

1. exact backend parity for existing filter/sort semantics;
2. stable total ordering for every sort mode;
3. row-id-only table evaluation before slicing;
4. explicit sidecar invalidation behavior;
5. no surviving `/search` plus local-filter loophole;
6. no loaded-window facet counts presented as truth;
7. clear response fields separating `scope_total`, `filtered_total`, and returned window length;
8. bounded or explicitly unsupported non-table fallback;
9. optional/separate facets to avoid making every browse query heavy;
10. storage-neutral internal query models rather than web models leaking into storage.

The plan’s central principle is good: **the backend owns browse truth; the frontend renders a window into that truth.** The danger is implementing only the shape of that principle while leaving small local-authority escape hatches in search, facets, derived metrics, cache invalidation, or sorting. Those escape hatches are where this bug will come back.

[1]: https://www.django-rest-framework.org/api-guide/filtering/ "Filtering - Django REST framework"
[2]: https://www.django-rest-framework.org/api-guide/pagination/ "Pagination - Django REST framework"
[3]: https://tanstack.com/query/v5/docs/framework/react/guides/query-keys?utm_source=chatgpt.com "Query Keys | TanStack Query React Docs"
[4]: https://tanstack.com/query/v5/docs/framework/react/guides/query-cancellation "Query Cancellation | TanStack Query React Docs"

---

No major new human decision is needed. It is mostly: **lock the defaults, then implement in order.**

There *are* a few places where the plan leaves a choice open, but I would not pause and ask. I would assert the following defaults.

## Assertions I would lock

### 1. `/folders/query` returns the browse window only, not full facets

**Decision:** do **not** return full facet histograms/category populations on every query response.

Use:

```text
POST /folders/query
→ items window
→ scope_total
→ filtered_total
→ folders
→ metric_keys
→ categorical_keys
```

Keep raw facet population on the existing `/folders/facets` path, at least for v1.

Why: fastest frontend, less backend work per filter/sort/page request, lower code count. Facets are useful, but recomputing/sending them on every browse page is unnecessary.

---

### 2. No per-value filtered facet counts in v1

**Decision:** omit authoritative per-category/per-metric filtered counts for now.

Keep:

```text
population_count = raw scope count
filtered_total = total matching rows after current query
```

Do **not** show loaded-window “filtered counts” as truth in Metrics.

Why: this avoids the same old bug in a new place. The frontend must not say “0” just because the current returned window lacks a value.

---

### 3. Backend query path owns search too

**Decision:** normal folder/table browse should stop using `/search` plus local filtering.

The new request should include text search:

```json
{
  "path": "/",
  "recursive": true,
  "text_query": "foo",
  "filters": { "and": [...] },
  "sort": { ... },
  "offset": 0,
  "limit": 1000
}
```

Evaluation order:

```text
scope → text search → filters → sort → offset/limit
```

Why: otherwise search remains a loophole where local filtering can still be wrong.

---

### 4. Derived metric filters/sorts are blocked in normal backend browse

**Decision:** fail closed.

If a filter/sort uses `@derived/...` in normal folder/table browse:

```text
show visible unavailable warning
do not send misleading query
do not locally filter loaded items
```

Similarity mode can remain separate because it is already a bounded top-K workflow.

Why: lower code count and no false correctness. Backend-derived metric support can come later, but should not be smuggled in through local fallback.

---

### 5. Table/parquet gets the fast native implementation first

**Decision:** implement real row-id query execution for `TableStorage`.

For table/parquet:

```text
row ids in scope
→ evaluate text/filter over row fields + sidecar
→ compute filtered_total
→ sort row ids
→ slice
→ materialize only returned rows
```

For non-table storage:

```text
small bounded fallback only
large recursive fallback returns clear unsupported/too-large response
```

Do not materialize giant non-table trees just to be “generic.”

Why: the reported bug is table/parquet. Native table query is the important fast path. Generic all-storage support can be minimal and safe.

---

### 6. Query page size should be smaller than the old 5000

**Decision:** use something like:

```ts
BROWSE_QUERY_PAGE_SIZE = 1000
```

The old `FOLDER_PAGE_SIZE = 5000` was compensating for frontend-owned filtering. Once the backend returns the correct filtered window, the frontend does not need to hydrate thousands of raw items just to discover matches.

Why: faster initial render, less JSON, less React work. Backend still evaluates the full scope, but it materializes/sends far fewer item payloads.

---

### 7. Random sort may change implementation

**Decision:** backend random sort should be deterministic by hash, not by reproducing frontend shuffle.

Use conceptual order:

```text
hash(random_seed, stable_row_identity), then stable_row_identity
```

Not:

```text
materialize all items → frontend-style shuffle
```

Why: stable pagination, lower memory pressure, simpler backend windowing. The exact old random order is not worth preserving.

---

### 8. Every sort gets a final stable tie-breaker

**Decision:** final tie-breaker is canonical path or row id.

Examples:

```text
metric value → name → path/row_id
added_at → name → path/row_id
name → path/row_id
random_score → path/row_id
```

Why: offset pagination without stable ordering causes duplicates/skips across pages. This is not optional.

---

### 9. Sidecar edits invalidate/refetch backend query truth

**Decision:** optimistic frontend star/notes updates may patch visible presentation only.

They must not decide membership/count/order.

After star/notes mutation:

```text
invalidate browse-query data
invalidate facets if sidecar-relevant
refetch backend truth
```

Why: star and notes filters depend on sidecar state. Local optimistic membership would recreate the same class of bug.

---

### 10. Use storage-neutral internal query models

**Decision:** Pydantic models stay at the web boundary. Storage gets plain dataclasses/protocols.

Shape:

```text
web/models.py
  BrowseQueryRequest
  BrowseQueryResponse

storage/base.py or browse/query.py
  BrowseQuerySpec
  BrowseQueryResult
  BrowseFilterClause
  BrowseSortSpec
```

Route adapts request → internal spec → response.

Why: lower coupling, fewer weird imports, easier tests.

---

## So the implementation path becomes

### Step 1: Backend contract

Add:

```text
POST /folders/query
```

with explicit request/response models.

Response should avoid `total_items` and use unambiguous names:

```json
{
  "path": "/",
  "generated_at": "...",
  "scope_total": 6,
  "filtered_total": 2,
  "offset": 0,
  "limit": 2,
  "items": [...],
  "folders": [...],
  "metric_keys": [...],
  "categorical_keys": [...]
}
```

### Step 2: Backend evaluator

Implement exact parity for current frontend filters/sorts.

This means copy the weird semantics intentionally, not “clean them up” during the migration.

### Step 3: Table row-query

Implement native `TableStorage.query_browse_scope(...)`.

This is the real fix.

Must prove:

```text
filtered_total correct
returned items correct
materialized item count == returned window size
```

### Step 4: Frontend query hook

Replace normal folder/table browse loading in `useAppDataScope.ts` with backend query results.

Local `applyFilters` / `applySort` may remain for:

```text
similarity mode
UI/helper tests
non-authoritative utilities
```

but not for normal folder/table browse truth.

### Step 5: Metrics panel adjustment

Metrics should use backend facet populations.

It should not derive authoritative filtered counts from the visible/current page.

### Step 6: Validation

Use the six-row fixture and the real parquet case.

The crucial test remains:

```text
raw first page has zero matches
later rows match
filtered query offset 0 returns matches
filtered_total is nonzero
grid renders nonzero without scrolling
```

## The only “human-visible” behavior changes I would explicitly accept

These are not blockers; I would assert them:

1. **Derived metric filtering/sorting unavailable in backend browse v1.**
2. **Random order may differ from old frontend random, but is stable across pages.**
3. **Large non-table recursive filtering may return unsupported/too-large instead of trying to materialize everything.**
4. **Metrics panel may stop showing per-value filtered counts unless backend can prove them.**
5. **Initial page size drops from 5000 to around 1000.**

Those choices fit your principles: fast, correct, lighter.

## Bottom line

I would not send this back for more product decisions.

I would amend the plan with the assertions above and proceed. The important posture is:

> backend query truth first; frontend renders; no local fallback; no expensive generic cleverness.
