# Table Query and Annotation Latency Investigation

Date: 2026-07-17  
Status: investigation complete; no implementation in this document

## Outcome

Lenslet's current table browse path does not scale with the amount of data actually needed by an interaction. Every query reconstructs rich Python records for the full scoped population, and the facets request independently repeats most of that work. Annotation handling then globally resets browse queries and invalidates facets, so a one-row star change can trigger the expensive analysis twice: once after the mutation response and again when the same update returns through collaboration sync.

The reported progressive slowdown is not caused by scanning annotation history or by 300 rated sidecars. Sidecar lookup during a query is an O(1) dictionary lookup per table row. A synthetic 2,000-row reproduction with 20 metrics, a `Rating is None` filter, and three additional metric filters remained around 0.16-0.21 seconds for query plus facets with either zero or 300 rated rows. The observed 1-20 second tail is instead consistent with repeated query/facet fan-out, stale work continuing after browser cancellation, browser cache-index amplification, response expansion and repeated conversion, synchronous thumbnail-cache I/O, retry delays, and synchronous annotation durability.

The correct architectural direction is to preserve backend-authoritative membership, order, and counts without treating every annotation as a reason to discard the current page. Lenslet needs a shared columnar query-analysis layer and one dependency-aware annotation reconciliation path.

## User Scenario

- About 2,000 table rows.
- Roughly 300 images annotated with one star.
- Active filter includes `Rating is None` plus three other conditions.
- Expected: annotation presentation updates immediately and a filter response is subsecond.
- Observed: annotations appear to refresh the page, and filtering can take 20 seconds or more.

In the filter contract, an unrated item is represented as `star is None` internally and matched as the synthetic star value `0`. The backend implementation is direct membership checking, not a sequential search through rated records (`src/lenslet/browse/query.py:793-798`).

## Measurements

### Named Parquet file

`E:/Datasets/otome_artists_real/pixai_aes1_2_1_clip_dedupe_unrated_rank1.parquet` was inspected read-only:

- 1,585 rows
- 42 Parquet columns
- 30 exposed numeric metrics
- 6 exposed categorical fields
- 465,560-byte Parquet file

Despite the small compressed source, a normal 1,000-item `/folders/query` response expands to about 2.33 MB because each result repeats the metric names and values. Local timings were:

| Operation | Observed time |
| --- | ---: |
| `TableStorage.query_browse_scope`, 1,000-item window | about 0.12-0.15 s |
| HTTP `/folders/query`, 1,000-item window | about 0.33-0.41 s |
| HTTP `/folders/facets` | about 0.17-0.27 s |
| One query and facet reconciliation | about 0.5-0.7 s of server work |

The endpoint scales with returned window size as well as scoped row count. Measured HTTP response sizes/times were approximately 40 KB/0.14 s for 10 rows, 248 KB/0.14 s for 100 rows, 1.17 MB/0.24 s for 500 rows, and 2.33 MB/0.33 s for 1,000 rows.

### Sidecar-count reproduction

A synthetic 2,000-row table with 20 scalar metrics was queried using `Rating is None`, three metric ranges, and name sorting. Medians across repeated runs were:

| Sidecar state | Query + facets |
| --- | ---: |
| No sidecars | about 0.16-0.21 s |
| 300 existing but unrated sidecars | about 0.17 s |
| 300 one-star sidecars | about 0.17-0.20 s |
| 1,000 one-star sidecars | about 0.20 s |

There was no monotonic relationship between the number of annotations and steady-state query time. Rated rows rejected by `Rating is None` can slightly reduce downstream filter/facet work.

In a profiled 2,000-row, 20-metric derived-query case, almost all time was spent constructing full query records. Metric extraction performed 40,000 coercions per endpoint. Sidecar read/copy time was only about 11-13 ms per endpoint.

Table width, rather than annotation count, produced clear linear growth in the same 2,000-row/300-rated scenario: query plus facets took about 0.17 seconds with 20 metrics, 0.56 seconds with 100 metrics, and 1.46 seconds with 300 metrics. Every detected scalar metric is expanded even though the query references only three of them.

### Existing persisted state

The label log and snapshot beside the named Parquet were also inspected read-only. At investigation time they contained 47 distinct annotated paths, with an approximately 9 KB log and 11 KB snapshot. Parsing each file took less than one millisecond. Runtime filtering does not reread either file; they are loaded at startup and queries use the in-memory sidecar dictionary.

Snapshot construction and log compaction do have future linear costs as annotation history grows, but the current files are far too small to explain the reported filter latency.

## What Changed Historically

The refresh behavior is a real regression in interaction design, introduced as part of a correctness-motivated architectural cutover.

### Before the backend-query cutover

Before commit `ed556fe628291df15617455b74675084ba9a5857` (`feat: use backend browse queries in frontend`, 2026-06-09):

- A mutation updated the sidecar cache without resetting gallery queries.
- Collaboration events patched visible item caches in place.
- `useAppDataScope` overlaid local star changes and applied filters/sorts in the browser.
- Annotation therefore appeared immediately without a browse refresh.

That behavior was fast, but it was not globally correct: local filtering only knew about the hydrated page, so matches outside that page could be omitted.

### The June 9 hard cutover

Commit `ed556fe` moved normal browse membership, ordering, filtering, and totals to backend `/folders/query` windows. It also added:

- `resetQueries({ queryKey: ['folder-query'] })` and facet invalidation after direct mutation success (`frontend/src/api/items.ts:373-378`);
- the same reset/invalidation after every `item-updated` and `metrics-updated` sync event (`frontend/src/app/hooks/useAppSyncEvents.ts:67-101`).

This was deliberate. `docs/20260609_backend_browse_query_plan.md` required backend-owned query truth and chose invalidation/refetch as the recovery mechanism for sidecar-dependent membership. Query-result caching was explicitly deferred.

The backend half of the cutover was introduced in commit `ba2e7be` (`feat: add table browse query execution`). It kept final `TableRowViewItem` materialization bounded to the returned window, but still constructs a `BrowseQueryRecord` containing all metrics, categoricals, sidecar data, and search text for every row before filtering and slicing (`src/lenslet/storage/table/storage.py:1316-1406`). The test boundary verified final item materialization, not the expensive intermediate record construction.

### The incomplete June 10 correction

Commit `a04eb862f2e00e3bfbccb5b7622854c06d77187a` (`feat: unify canonical browse analysis state`, 2026-06-10) restored live patching for paged `folder-query` results. `ItemQueryPathIndex` now finds the loaded queries containing a path, and `patchIndexedItemQueries` updates star/notes/metrics inside infinite-query pages (`frontend/src/app/model/appShellStateSync.ts:202-224`). Tests confirm that behavior.

However, the global resets from `ed556fe` were not removed. Current behavior therefore does both:

1. patch the loaded item immediately;
2. reset every matching browse query and invalidate facets;
3. repeat the reset when the originating update is echoed through sync.

There is no current test asserting that one mutation plus its owner echo produces at most one scoped reconciliation without discarding visible data.

## Why the Slowdown Can Look Progressive or Sequential

### Full-scope record reconstruction

`TableStorage.query_browse_scope` retrieves every row in scope and constructs a rich record for each one before calling the generic evaluator (`src/lenslet/storage/table/storage.py:1376-1406`). `_metrics_for_row` iterates every detected metric column for every row, even if the active filters reference only three fields (`src/lenslet/storage/table/storage.py:1007-1024`).

The evaluator then scans, filters, fully sorts, and only afterward slices the requested window (`src/lenslet/browse/query.py:256-301`). A `Rating is None` condition does not allow the backend to skip building metrics, categoricals, or search text.

### Facets repeat the analysis

`facet_summary_for_query` reconstructs the same full set of records independently (`src/lenslet/storage/table/storage.py:1754-1777`). `build_table_query_facet_summary` reevaluates the filters and iterates all surviving metrics/categoricals (`src/lenslet/storage/table/facets.py:29-101`). Facet counts do not depend on ordering, yet the generic evaluator also sorts their population.

### One annotation can schedule duplicate analysis

Direct mutation success resets browse queries. The collaboration event for that same mutation patches the cache and resets it again. If Metrics is mounted, each reconciliation can include both `/folders/query` and `/folders/facets`.

The browser request budget limits active folder fetches to two (`frontend/src/api/requestBudget.ts:24-35`), but browser abort only stops waiting for a response. `/folders/query` and `/folders/facets` are synchronous FastAPI handlers (`src/lenslet/web/routes/folders.py:177-227`); work already running on the server is not cancelled when the fetch is aborted. Rapid annotations/filter changes can therefore leave stale full scans completing while newer requests contend for CPU. The resulting backlog can feel like Lenslet is processing annotations sequentially.

The browser releases its request-budget slot immediately after aborting a fetch, so it can start another request while the abandoned server calculation is still running. Query and facet calculations are Python/GIL-bound: on the named file, running them from two threads produced essentially no speedup over sequential execution. Client-side concurrency limits therefore do not bound the amount of stale server CPU work created during rapid interaction.

Retries can add explicit one- and two-second delays to marginal failures (`frontend/src/api/items.ts:362-366`, `frontend/src/api/folders.ts:201-223`).

### Cached analysis variants amplify annotation work in the browser

Browse-query variants for the current path remain cached for 60 seconds (`frontend/src/api/folders.ts:216-223`). `ItemQueryPathIndex` maintains reverse item-to-query membership, but `syncQuery` first removes all previously indexed paths and then re-extracts/re-adds every loaded path (`frontend/src/app/model/appShellStateSync.ts:118-184`). AppShell sends every QueryCache event through this process, without checking whether query data identity or page membership changed (`frontend/src/app/AppShell.tsx:368-385`).

After trying `K` filters over an `N`-item window, a later annotation can synchronously patch several cached variants and cause repeated `O(K * N)` Map/Set churn. Each `setQueryData` also emits another cache event and reindexes the affected result. This is normally tens of milliseconds, but many variants, loaded pages, or a burst of collaboration events can make it visible before any network response arrives.

### Free-text attribute filters create request storms

Filename, notes, and URL contains/not-contains controls commit filter state directly on every input `onChange` (`frontend/src/features/metrics/components/AttributesPanel.tsx:167-235`). Unlike the toolbar search, they do not have a draft state or debounce boundary. With Metrics open, typing ten characters can start ten query requests and ten facet requests. Browser cancellation prevents stale display, but it does not stop synchronous server calculations already running.

Free-form controls should separate draft from committed query state and commit on a short debounce, Enter, Apply, or blur. Discrete filters such as star/categorical toggles should remain immediate.

### Window payload construction repeats work

The table query record already contains normalized metrics, categoricals, and sidecar values. The returned window is nevertheless converted through several additional boundaries:

- `_materialize_query_record_item` recoerces the already-normalized metric mapping (`src/lenslet/storage/table/storage.py:1435-1445`);
- `_query_result_payload` converts every result through `to_item` (`src/lenslet/web/browse.py:949-982`);
- `build_item_payload` normalizes metrics again, rereads sidecar state and categoricals, reparses media source policy, and creates Pydantic item models (`src/lenslet/web/browse.py:138-185`).

On the named file, constructing the 1,000-item web payload added roughly 80 ms after storage query evaluation. Repeating categorical extraction accounted for about 35 ms. The 1,000-item response is about 2.32 MB, versus about 479 KB at a 200-item window. A lean window DTO should be created once from evaluated row IDs, while inspector-only fields and broad metric detail should be fetched lazily or supplied through a normalized entity/detail cache.

### Frontend whole-window recomputation remains despite DOM virtualization

React virtualization limits mounted thumbnail cards, but an annotation or new query response still causes several full-window passes: flatten pages, clone all loaded items for local-star overrides, rebuild path/selection maps, scan metric mappings for derived-key cleanup, recompute adaptive layout, and recalculate metric-scrollbar arrays/histograms. Relevant paths include `frontend/src/app/hooks/useAppDataScope.ts:290-395`, `frontend/src/features/metrics/model/derivedMetric.ts:280-300,546-596`, `frontend/src/features/browse/hooks/useVirtualGrid.ts:70-85`, and `frontend/src/features/browse/components/VirtualGrid.tsx:179-222`.

This is normally secondary at 1,000 rows, but wide tables or multiple pages can turn it into hundreds of milliseconds of main-thread work. Normalized entities should preserve path/order identity when one item changes, and derived-key cleanup should be an ingestion/server contract rather than an every-render scan.

### Metrics "Show all" is deliberately unbounded

Metric and categorical helpers explicitly nest requested keys over population, filtered, and selected arrays (`frontend/src/features/metrics/model/metricValues.ts:18-81,132-154`; `frontend/src/features/metrics/model/categoricalValues.ts:14-95`). "Show all" renders every card without virtualization (`frontend/src/features/metrics/components/MetricRangePanel.tsx:49-76,158-165`; `frontend/src/features/metrics/components/CategoricalPanel.tsx:32-55,113-120`).

This is modest in the default single-key view but can become seconds of aggregation and DOM/SVG work on very wide tables. Backend columnar facets should supply aggregates, "Show all" should be virtualized, and selected summaries should compute only requested/visible keys.

### Thumbnail-cache I/O blocks async response and sync scheduling

The thumbnail route is async, but disk-cache access is synchronous inside the event-loop handler (`src/lenslet/web/media.py:170-208`). Cache hits call `Path.read_bytes()` directly. Cache misses write a temporary file, flush and `fsync` it, replace the destination, and potentially scan/evict while holding one thumbnail-cache lock (`src/lenslet/web/cache/thumbs.py:64-117`).

The named dataset currently has 1,632 cached WebP files totaling about 19.5 MB. Warm reads measured about 0.25 ms per file, so warm cache access is not proven as the present 20-second bottleneck. Cold files, antivirus scanning, cache misses, or a mapped/synchronized drive can nevertheless serialize many small reads/writes on the event loop and delay unrelated HTTP completion and SSE delivery while the grid hydrates.

Best-effort cache reads/writes and image encoding should stay in bounded workers. Generated thumbnails can be returned before best-effort persistence completes. Best-effort thumbnail files do not require the same per-object durability contract as accepted annotations.

### Durable append holds the event broker lock

`EventBroker.publish_after_commit` holds the broker lock while the commit callback performs label-log append/flush/`fsync` (`src/lenslet/web/sync/events.py:91-105`, `src/lenslet/web/app/shared.py:115-131`). The effective order includes sidecar lock, broker lock, log lock, and disk I/O. A slow workspace drive can therefore block all annotation publication, event replay/client registration, and collaboration delivery—not just the originating request.

Event sequencing should reserve/order an event without holding the broker lock across disk. A small crash-safe WAL append should complete on the durable workspace, then the committed event can be enqueued for broadcast. Snapshot and compaction should remain outside broker/request/sidecar critical sections.

### Conditional and lower-impact inefficiencies

- After repeated SSE failures, fallback polling independently schedules browse/facet/folder requests every 15 seconds and sidecars every 12 seconds. Timers can align into periodic request herds while SSE reconnect/replay duplicates fresh work (`frontend/src/api/client.ts:270-329`, `frontend/src/api/folders.ts:192-289`, `frontend/src/api/items.ts:326-337`).
- Generic retries can turn transient failures into explicit multi-second tails (`frontend/src/App.tsx:11-24`).
- Facet aggregation sorts its population even though histogram/count results are order-independent (`src/lenslet/storage/table/facets.py:42-62`).
- Date filters reparse invariant bounds for every record, and descending name/added sorts construct reverse Unicode strings per row (`src/lenslet/browse/query.py:866-883,903-932,985-986`). These are measurable but not a 20-second cause at 2,000 rows.
- `ParquetRowFieldProvider` caches only one row group (`src/lenslet/storage/table/launch.py:909-957`). Jumping between rows in multiple row groups can repeatedly reread/convert whole groups. The named file has one row group, so it is unaffected.
- Table mode is static after launch. If the source Parquet changes, the running process keeps its old row/index state until restart. This is a correctness/staleness issue rather than an execution bottleneck.

### Persistence can add annotation tail latency, but not idle filter latency

Each accepted annotation appends, flushes, and `fsync`s the label log before committing the in-memory update (`src/lenslet/web/app/shared.py:101-133`, `src/lenslet/workspace.py:298-308`). This happens while annotation/event locks are held. The first update and later interval/count thresholds may also synchronously write an atomic snapshot (`src/lenslet/web/sync/labels.py:47-121`). A mapped, synchronized, or antivirus-scanned dataset drive can add seconds here.

This persistence cost affects the mutation and sync path. It does not explain a single filter request issued after the system is idle, because filtering reads the already-loaded in-memory sidecar dictionary.

## Root-Cause Assessment

Are we solving symptoms, or are we solving ROOT problems in the architecture design/decision?

The root problem is not simply that the page size is 1,000 or that invalidation lacks a debounce. The foundational coupling is:

- backend authority is implemented as global cache disposal rather than immediate projection plus scoped reconciliation;
- immutable columnar table data is converted into a full row-object graph for every interaction;
- query windows and facets independently calculate the same analysis;
- browser cancellation does not cancel or deduplicate stale server analysis;
- cached query membership is rebuilt in response to broad cache events;
- free-text filter drafts are treated as committed backend queries;
- rich window fields are reconstructed and normalized repeatedly across storage, web, and frontend boundaries;
- mutation response and owner-echo event are treated as two unrelated invalidation events;
- best-effort thumbnail disk I/O blocks the async event loop;
- durable persistence is performed while request, event, and broker critical sections are held.

Reducing page size, adding a debounce, or suppressing facets would improve symptoms but leave the same failure mode for wider tables, more editors, new annotation fields, and future analysis consumers.

## Recommended Architecture

### 1. Separate projection updates from query-truth reconciliation

An annotation is first an entity update and only sometimes a query-membership update.

- Patch the changed star/notes/metrics into every loaded entity/window immediately.
- Do not clear currently displayed pages.
- Inspect the canonical active analysis key to determine whether the changed field can affect membership, order, totals, text search, derived scores, or facets.
- If it cannot, no browse request is needed.
- If it can, retain current data and perform one background reconciliation of the affected active analysis.
- Conservatively reconcile when dependency classification is unknown.

For the common `Rating is None` flow, changing a visible item from None to one star can be projected as an immediate removal from the loaded filtered window, followed by one backend reconciliation for authoritative count/pagination repair. An item entering a filtered result from outside loaded pages remains backend-owned and arrives during reconciliation.

Use stale-while-revalidate invalidation rather than `resetQueries`, so reconciliation never presents as a page refresh.

### 2. Give mutations one identity and one reconciliation owner

Mutation response and collaboration echo must represent the same logical command.

- Carry a stable mutation/client identity through the persisted event and response, or deduplicate by a robust equivalent contract.
- Apply a local optimistic projection once.
- Reconcile at most once for the command.
- Coalesce a rapid burst or bulk edit into one reconciliation per affected analysis.
- Continue delivering remote-editor events and version conflicts normally.

### 3. Keep table queries columnar through filtering and sorting

Introduce a `TableQueryEngine` over the existing row store:

- immutable arrays for path, name, dimensions, metric columns, and categorical columns;
- compact mutable arrays for star/notes and an annotation generation;
- boolean row masks using only fields referenced by the query;
- precomputed/static orderings where useful, with stable row-id tie-breaking;
- materialization of rich records/items only for the returned window;
- response metrics attached only to returned items.

Avoid solving this by prebuilding a large dictionary-rich `BrowseQueryRecord` for every row. That would trade latency for substantial memory growth while retaining row-object overhead.

### 4. Share analysis between windows and facets

Compute a canonical analysis result such as filtered row IDs, total, ordering, and derived scores once per query identity and relevant generation. Query windows slice it; facets aggregate from the same filtered row IDs and column arrays. Facet aggregation should not sort its population.

Cache keys must include every semantic query variable plus the generations of mutable fields on which the analysis depends.

Analysis execution must also be cancellable and deduplicated. A newer request with the same canonical identity should join an existing in-flight analysis rather than start another scan. An obsolete query should stop at bounded row-chunk checkpoints. Releasing a browser request slot must not permit abandoned server work to accumulate without a bound.

### 5. Bound frontend query and projection work

- Keep explicit draft state for free-text filters and commit through a debounce, Enter, Apply, or blur boundary.
- Retain only the current analysis and a small, deliberate set of recent variants rather than every attempted filter for 60 seconds.
- Rebuild item-to-query membership only when page data or membership actually changes, not for every cache notification.
- Normalize window entities once, preserve path/order identity, and patch a changed entity without replacing unrelated window objects.
- Preserve the visible window during background reconciliation instead of resetting it to a loading state.
- Virtualize broad metric/categorical panels and compute aggregates only for requested or visible fields.

### 6. Move cache and durability work to the correct concurrency boundaries

Do not remove `fsync` merely to hide latency. Instrument mutation phases first. If durable writes are a contributor:

- place the writable workspace/WAL on explicitly fast local storage;
- keep the critical durable append small;
- move snapshot construction and compaction outside broker/request locks;
- rotate or truncate log entries covered by a successful snapshot;
- define acknowledgment and crash-recovery semantics explicitly.

Best-effort thumbnail and browse caches have a different contract from accepted annotation state. Their disk reads and writes should run in bounded workers, cache writes may complete after the response, and cache failure should degrade performance rather than stall event delivery.

## Validation Required for a Fix

1. Unfiltered star edit patches the visible item with no browse/facet request.
2. `Rating is None` edit removes the visible item immediately, retains the page, and causes exactly one scoped background reconciliation.
3. Direct mutation plus its owner sync echo does not duplicate reconciliation.
4. A remote editor's update follows the same projection/reconciliation rules.
5. A burst of 100 edits produces bounded query/facet work rather than 100-200 full refreshes.
6. Query results remain correct when an edited item enters from an unloaded page or changes sort position.
7. A 2,000-row, 30-metric, 300-rated fixture with four filters remains subsecond at steady state.
8. Zero, 300, 1,000, and 2,000 sidecars show no superlinear query growth.
9. Performance tests measure intermediate query-record allocations, not only final item materialization count.
10. Instrumentation separates mutation log append/fsync, snapshot, query analysis, facet aggregation, serialization, request queue time, and stale/aborted server work.
11. Rapidly typing a ten-character attribute filter produces one committed analysis, not ten stale scans.
12. Accumulating many cached query variants does not make annotation cost scale with the number of cached windows.
13. Cancelling an obsolete query stops or supersedes backend work at bounded checkpoints.
14. Query windows and facets join one in-flight or cached canonical analysis.
15. A one-item patch preserves path/order identity and does not rescan all metric mappings for derived-key cleanup.
16. Thumbnail cache hits and misses do not block the event loop or delay collaboration event delivery.
17. A slow label-log append does not hold the event broker lock.
18. Metrics "Show all" remains responsive on a wide-table fixture through virtualization or lazy aggregation.

## Immediate Diagnostic Distinction

For the reported 20-second case, distinguish two states:

- If it occurs during or immediately after annotation/filter churn, duplicate resets and non-cancellable stale server work are the leading explanation.
- If it occurs for one filter request after several idle seconds, the measured 2,000-row steady-state path does not explain it. Capture endpoint phase timings and the exact active filter/derived-metric payload; investigate unusually wide/nested metrics, retries, and external process contention rather than annotation count.

The implementation should solve both the confirmed architectural inefficiency and preserve instrumentation for the unexplained idle-tail case.
