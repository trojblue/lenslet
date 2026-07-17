# Table Query and Annotation Latency Remediation Execution Plan


## Purpose / Big Picture


This plan turns the findings in `D:\dev\lenslet\docs\20260717_table_query_annotation_latency_investigation.md` into modular implementation work. After completion, a labeller can rate or edit an item and see the change within 100 milliseconds without the gallery clearing or visibly refreshing. If the edit affects active membership, order, totals, or facets, that browser session performs at most one active reconciliation plus one coalesced trailing reconciliation while retaining the current page. Other browsers remain independent and receive the same update through collaboration sync.

Filtering the named Parquet dataset and the required 2,000-row synthetic fixture remains under one second for the combined query and facet interaction after warmup. Rapid filter typing and annotation bursts cannot leave an unbounded queue of stale Python analysis. Query windows and facets reuse one columnar analysis, rich item payloads are built only for requested rows and fields, and the browser patches one normalized entity instead of rewriting every cached query variant.

Annotation acceptance becomes memory-first and observable. Normal idle edits are flushed promptly, continuous edits complete append, flush, and `fsync` no later than 15 seconds after the oldest accepted unsaved edit on healthy storage, and graceful shutdown forces a final flush. A crash can lose only the not-yet-durable portion of that window. A server boot epoch prevents clients from confusing pre-crash accepted IDs with post-restart state, and reconnect forces affected paths back to durable server truth. The UI exposes pending, saved, and failed persistence states so this weaker durability contract is explicit rather than silent.

There is no repository-wide `PLANS.md`. This plan follows `D:\dev\lenslet\AGENTS.md`, the active-document convention under `D:\dev\lenslet\docs`, and the backend-authority constraints established by `D:\dev\lenslet\docs\20260609_backend_browse_query_plan.md`.


## Progress


- [x] 2026-07-17: Investigated query, facet, annotation, frontend cache, thumbnail, and persistence latency.
- [x] 2026-07-17: Confirmed that annotation count does not cause the steady-state slowdown and documented the broader execution audit.
- [x] 2026-07-17: Locked scope, user-visible targets, per-session reconciliation semantics, and the 15-second lazy-persistence bound with the user.
- [x] 2026-07-17: Drafted the sprint and ticket decomposition.
- [x] 2026-07-17: Completed independent plan review and incorporated crash recovery, concrete bounds, ticket splits, and validation clarifications.
- [ ] Sprint 0: Establish repeatable latency and request-count evidence.
- [ ] Sprint 1: Remove annotation page refreshes and duplicate per-session reconciliation.
- [ ] Sprint 2: Introduce the columnar table query engine.
- [ ] Sprint 3: Share, bound, deduplicate, and cancel backend analysis.
- [ ] Sprint 4: Cut over to lean window payloads and normalized frontend entities.
- [ ] Sprint 5: Bound filter-input and Metrics-panel work.
- [ ] Sprint 6: Isolate thumbnail work from the async event loop.
- [ ] Sprint 7: Implement observable lazy annotation persistence with a 15-second hard bound.
- [ ] Sprint 8: Address measured operational tail causes.
- [ ] Sprint 9: Address conditional table-source refresh and row-group behavior.


## Surprises & Discoveries


The reported progressive slowdown is not a scan through annotation history. In the 2,000-row reproduction, zero, 300, and 1,000 rated sidecars all kept query-plus-facet time near 0.16 to 0.21 seconds. Sidecars are already held in memory and contribute only an O(1) lookup per row. Table width is the stronger steady-state multiplier: the same workload grew from about 0.17 seconds at 20 metrics to 1.46 seconds at 300 metrics because every endpoint expands every metric for every row.

The refresh is a historical regression rather than an unavoidable result of backend authority. The June 9 backend-query cutover introduced global `folder-query` resets after direct mutations and collaboration events. A June 10 correction restored live item patching but left both resets in place. Current code therefore patches the item, discards query data, and may repeat the discard when the originating event returns over sync.

Browser cancellation does not cancel the synchronous FastAPI calculation. The client releases its two-request budget slot and starts newer work while the old GIL-bound query or facet calculation continues in a server thread. Query and facet execution showed almost no two-thread speedup, so rapid changes can create a CPU backlog that looks sequential even though the current query itself is small.

The named 1,585-row Parquet file is only about 466 KB, but a 1,000-item query response expands to about 2.33 MB. Storage evaluation, web conversion, categorical extraction, Pydantic construction, and frontend normalization repeat work across boundaries. DOM virtualization does not prevent full-window JavaScript passes or unbounded Metrics “Show all” rendering.

Thumbnail cache hits and misses perform synchronous disk work inside an async route. Label-log append and `fsync` currently occur while the event broker lock is held. Warm local measurements do not prove either is the reported 20-second idle-filter cause, but slow, mapped, synchronized, or antivirus-scanned storage can turn both into global tail-latency amplifiers.


## Decision Log


2026-07-17, user: Include conditional findings in the execution plan, but place them after the confirmed high-impact work. The plan therefore defers polling, retry, row-group, and source-refresh changes until measured gates in Sprints 8 and 9.

2026-07-17, user: Replace per-mutation durable acknowledgment with lazy persistence. A healthy process must flush an idle batch promptly and must make the oldest pending accepted edit durable within 15 seconds. Graceful shutdown flushes synchronously. A crash may lose the pending window, and persistent disk failure must be surfaced visibly.

2026-07-17, user and Codex: “At most one reconciliation” is scoped per browser session, not globally across editors. A session may have one active reconciliation and one dirty trailing pass so changes arriving during the active pass are not lost. Independent sessions may legitimately request the same analysis; the backend coordinator deduplicates identical work where possible.

2026-07-17, user: Accept visible annotation projection within 100 milliseconds, no page-clearing refresh, subsecond combined query-plus-facet behavior on the named and synthetic fixtures, and bounded work during typing and 100-edit bursts.

2026-07-17, Codex: Preserve backend authority over membership, order, counts, filtering, and facets. Immediate frontend projection may remove an already-loaded item when the new value conclusively fails the active filter, but a backend reconciliation remains responsible for authoritative pagination repair and for items entering from unloaded pages.

2026-07-17, Codex: Use a hard cutover and existing dependencies. The columnar engine uses Python and the already-required PyArrow package; the frontend uses existing TanStack Query and TanStack Virtual packages. Do not add a database, generic query language, NumPy requirement, or compatibility branch.

2026-07-17, Codex: Separate analysis identity from window projection. Filtering and derived-score analysis are keyed independently of offset, limit, and returned fields; ordering is keyed from the filtered analysis plus sort state; window projection is applied only after row IDs are known.

2026-07-17, plan review and Codex: Do not duplicate query-dependency semantics in Python and TypeScript. The backend returns an authoritative dependency manifest with query/facet results; the frontend only intersects mutation `changed_fields` with that manifest and treats `unknown` as requiring reconciliation.

2026-07-17, plan review and Codex: Bound every long-lived coordinator. The app admits at most 32 distinct queued analyses, retains eight filter and eight order analyses, tracks at most 256 inactive session entries for five minutes, and applies round-robin session fairness. Each browser retains the active plus two recent query variants and 512 seen mutation IDs for ten minutes. Projection requests allow at most 64 metrics and 32 categoricals; facet batches request at most 24 fields.

2026-07-17, plan review and Codex: A persistence deadline is satisfied only when append, flush, and `fsync` complete. The writer uses monotonic time, begins a deadline flush no later than 13 seconds to reserve two seconds for I/O, and declares storage unhealthy on error or deadline breach. It admits at most 10,000 pending events or 16 MiB, whichever comes first.


## Outcomes & Retrospective


Planning and independent review are complete. No implementation has begun. Update this section at every sprint boundary with the demo result, measured before/after evidence, remaining risks, and any deliberate deviation from the interfaces below. Do not mark a sprint complete when only unit tests pass but its runnable demo outcome has not been observed.

At final completion, record the named-dataset and synthetic-fixture latency distributions, annotation projection latency, request and analysis counts for burst scenarios, persistence watermark behavior, event-loop responsiveness during thumbnail misses, and any conditional Sprint 8 or Sprint 9 tickets that were skipped because their trigger was not met.


## Context and Orientation


The public browse request contract is defined in `D:\dev\lenslet\src\lenslet\web\models.py` and served by `D:\dev\lenslet\src\lenslet\web\routes\folders.py`. Storage-neutral query specifications and the generic row-object evaluator live in `D:\dev\lenslet\src\lenslet\browse\query.py`. Table execution is concentrated in `D:\dev\lenslet\src\lenslet\storage\table\storage.py`, with facets in `D:\dev\lenslet\src\lenslet\storage\table\facets.py` and row/index structures under `D:\dev\lenslet\src\lenslet\storage\table`.

The frontend issues browse and facet requests from `D:\dev\lenslet\frontend\src\api\folders.ts`, applies mutations from `D:\dev\lenslet\frontend\src\api\items.ts`, and receives collaboration events in `D:\dev\lenslet\frontend\src\app\hooks\useAppSyncEvents.ts`. Query membership indexing and item patching currently live in `D:\dev\lenslet\frontend\src\app\model\appShellStateSync.ts`. `D:\dev\lenslet\frontend\src\app\AppShell.tsx` subscribes the index to broad TanStack Query cache events. `D:\dev\lenslet\frontend\src\app\hooks\useAppDataScope.ts` flattens pages and performs several whole-window transformations.

“Projection” means an immediate local update to an already-known entity and, only when provably correct, its loaded-window membership. “Reconciliation” means a background backend request that restores authoritative membership, ordering, totals, pagination, and facets without clearing the current view. “Analysis” means the filtered row-ID population, derived scores, and ordered row IDs produced before offset/limit slicing. “Window projection” means materializing only the requested row IDs and fields into the response.

For the persistence contract, “healthy storage” means the current write attempt completes append, flush, and `fsync` without error within the reserved two-second I/O margin. A write that eventually succeeds after that margin still records a deadline breach and leaves the UI in an unsaved/error state until the durable watermark confirms recovery.

The mutation path is implemented by `D:\dev\lenslet\src\lenslet\web\routes\items.py`, `D:\dev\lenslet\src\lenslet\web\app\shared.py`, and `D:\dev\lenslet\src\lenslet\web\sync\events.py`. Label snapshots and compaction are managed by `D:\dev\lenslet\src\lenslet\web\sync\labels.py` and durable workspace primitives in `D:\dev\lenslet\src\lenslet\workspace.py`. Runtime and shutdown ownership live in `D:\dev\lenslet\src\lenslet\web\runtime.py` and `D:\dev\lenslet\src\lenslet\web\lifecycle.py`.

Thumbnail delivery is implemented by `D:\dev\lenslet\src\lenslet\web\media.py` and the disk cache in `D:\dev\lenslet\src\lenslet\web\cache\thumbs.py`. The current async route directly calls blocking reads, generation, atomic writes, `fsync`, and eviction.

The working tree may contain unrelated user changes. Every implementation ticket must inspect `git status --short`, preserve unrelated edits, and limit its commit to the ticket’s files. Built frontend assets under `D:\dev\lenslet\src\lenslet\frontend` are regenerated only after the relevant frontend sprint passes tests.


## Plan of Work


Begin by making the current failure observable without changing behavior. Add one reusable backend probe and one live-browser scenario that report endpoint phases, request counts, analysis counts, response bytes, DOM continuity, and annotation projection latency. These instruments become acceptance gates for later sprints and prevent a fast unit-level implementation from hiding browser or queueing regressions.

Fix annotation behavior before replacing the query engine. Centralize mutation response and SSE echo handling around the existing idempotency key, have the backend return the authoritative fields on which an analysis depends, patch the known item immediately, and replace global resets with a single-flight per-session reconciliation scheduler. This produces the first user-visible improvement while retaining the existing backend evaluator as the authority.

Next, build a table-specific columnar engine behind parity tests. Pre-normalize immutable row fields once, maintain compact mutable annotation columns and dependency generations, evaluate only referenced columns, and materialize rich objects only after slicing. Then place a bounded coordinator around that engine so windows and facets share analysis, identical in-flight work is joined, and superseded or disconnected subscribers stop obsolete work at chunk checkpoints.

After backend analysis is bounded, hard-cut the API and frontend to lean projected windows and a normalized entity store. Query pages retain stable path order and metadata; entity patches notify only consumers of the changed path. Remove broad item-to-query reindexing for normalized browse pages and move derived-field cleanup to ingestion or server contracts.

Bound the remaining UI work by separating draft and committed free-text filters, requesting facet fields lazily, and virtualizing broad Metrics panels. Isolate thumbnail disk and encoding work in dedicated bounded workers. Finally, replace synchronous annotation durability with a monitored write buffer whose idle and hard-deadline flush behavior is explicit.

Only after the core acceptance suite passes should the implementation enter conditional work. Use the collected evidence to decide whether polling/retry coordination, multi-row-group caching, or live table-source refresh is necessary. Conditional tickets have explicit triggers and must not delay the core fix when the trigger is absent.


### Sprint Plan


1. Sprint 0 — Evidence and regression harness. Goal: establish reproducible server and browser measurements before behavior changes. Demo: one command produces JSON showing the synthetic `Rating is None` scenario, per-phase server timing, request/analysis counts, response bytes, and the current annotation refresh. Tasks: [S0-T1 latency fixture and probe](#s0-t1-add-repeatable-latency-fixtures-and-a-probe), [S0-T2 server diagnostics](#s0-t2-instrument-server-phases-and-stale-work), and [S0-T3 browser acceptance scenario](#s0-t3-add-the-live-annotation-and-filter-browser-scenario).

2. Sprint 1 — Immediate annotation projection and scoped reconciliation. Goal: eliminate page-clearing resets and duplicate owner-echo work while the old evaluator remains authoritative. Demo: an unrated visible item disappears immediately under `Rating is None`, the page remains mounted, and each browser session performs no more than one active plus one trailing reconciliation. Tasks: [S1-T1 mutation identity](#s1-t1-carry-one-mutation-identity-through-response-and-sync), [S1-T2 dependency classification](#s1-t2-classify-query-dependencies), [S1-T3 projection and scheduler](#s1-t3-replace-global-resets-with-projection-and-single-flight-reconciliation), and [S1-T4 multi-editor validation](#s1-t4-lock-the-no-refresh-and-multi-editor-contract).

3. Sprint 2 — Columnar table query engine. Goal: stop reconstructing a rich record graph for the full scope. Demo: parity tests return the same rows, totals, derived scores, and order while instrumentation proves that only the requested window is materialized. Tasks: [S2-T1 column store](#s2-t1-build-the-table-query-column-store), [S2-T2 mutable generations](#s2-t2-add-mutable-annotation-columns-and-dependency-generations), [S2-T3 text and built-in filters](#s2-t3-evaluate-text-and-built-in-filters-over-columns), [S2-T4 metric and categorical filters](#s2-t4-evaluate-metric-and-categorical-filters-over-columns), [S2-T5 derived analysis](#s2-t5-evaluate-derived-scores-without-row-records), [S2-T6 ordering](#s2-t6-order-row-ids-with-stable-semantics), and [S2-T7 bounded projection](#s2-t7-materialize-only-the-returned-window).

4. Sprint 3 — Shared, cancellable analysis. Goal: make query and facets reuse globally bounded work and prevent stale browser requests from consuming unlimited server CPU. Demo: concurrent query/facet requests for one analysis execute one filter pass; a superseding revision cancels obsolete work; two sessions can independently subscribe under fair app-wide admission. Tasks: [S3-T1 analysis model](#s3-t1-separate-filter-order-and-window-identities), [S3-T2 coordinator](#s3-t2-add-a-bounded-analysis-coordinator), [S3-T3 session revision protocol](#s3-t3-add-the-browser-session-and-query-revision-protocol), [S3-T4 query/facet integration](#s3-t4-cut-query-and-facets-over-to-shared-analysis), and [S3-T5 contention validation](#s3-t5-prove-deduplication-cancellation-and-bounds).

5. Sprint 4 — Lean payloads and normalized browser entities. Goal: remove repeated conversion and cached-variant amplification. Demo: the named 1,000-row response is at most 1.0 MB for the core-plus-three-metric projection, an item patch touches one entity, and page/path identity remains stable. Tasks: [S4-T1 projection contract](#s4-t1-add-an-explicit-window-projection-contract), [S4-T2 lean payload path](#s4-t2-remove-repeated-window-payload-conversion), [S4-T3 entity store](#s4-t3-implement-the-frontend-entity-store), [S4-T4 query/grid migration](#s4-t4-migrate-query-pages-and-grid-consumers-to-normalized-entities), [S4-T5 retire broad indexing](#s4-t5-retire-broad-query-membership-reindexing), and [S4-T6 whole-window pass removal](#s4-t6-remove-render-time-whole-window-cleanup).

6. Sprint 5 — Bounded filter and Metrics UI work. Goal: prevent input request storms and wide-table main-thread stalls. Demo: typing ten characters commits one revision, and a 300-field “Show all” panel renders only visible cards with backend aggregates. Tasks: [S5-T1 committed filter boundary](#s5-t1-separate-free-text-filter-drafts-from-committed-state), [S5-T2 field-scoped facets](#s5-t2-make-facet-aggregation-field-scoped-and-lazy), [S5-T3 Metrics virtualization](#s5-t3-virtualize-wide-metrics-and-categorical-panels), and [S5-T4 wide-table browser validation](#s5-t4-lock-wide-table-and-input-storm-acceptance).

7. Sprint 6 — Thumbnail concurrency boundary. Goal: keep cache reads, generation, persistence, and eviction off the event loop. Demo: an injected 500-millisecond thumbnail cache operation does not pause an event-loop heartbeat or collaboration SSE. Tasks: [S6-T1 thumbnail coordinator](#s6-t1-add-a-bounded-thumbnail-work-coordinator), [S6-T2 best-effort cache writes](#s6-t2-make-thumbnail-persistence-best-effort), and [S6-T3 event-loop validation](#s6-t3-prove-thumbnail-work-does-not-block-http-or-sse).

8. Sprint 7 — Lazy label persistence. Goal: make annotation mutation and event publication memory-first while guaranteeing healthy-storage flush completion by 15 seconds. Demo: edits broadcast immediately, idle edits become durable promptly, continuous edits cross a durable watermark within 15 seconds, crash/restart returns clients to durable truth, and shutdown flushes. Tasks: [S7-T1 write-buffer contract](#s7-t1-introduce-the-label-write-buffer-and-watermark), [S7-T2 unlock event publication](#s7-t2-remove-disk-io-from-broker-and-sidecar-critical-sections), [S7-T3 durable snapshots](#s7-t3-move-snapshot-and-compaction-behind-the-durable-watermark), [S7-T4 lifecycle and restart](#s7-t4-integrate-writer-lifecycle-boot-epochs-and-shutdown), [S7-T5 persistence UI](#s7-t5-expose-pending-saved-and-failed-persistence-state), and [S7-T6 failure and deadline validation](#s7-t6-lock-the-15-second-crash-and-failure-contract).

9. Sprint 8 — Conditional operational tail cleanup. Goal: fix only tail causes proven by Sprint 0 diagnostics after the core cutover. Demo: the diagnostic report records each gate and, when triggered, shows polling/retry or scalar-query tails removed. Tasks: [S8-T1 gate review](#s8-t1-evaluate-operational-tail-gates), [S8-T2 polling and retry coordination](#s8-t2-coordinate-fallback-polling-and-retries-when-triggered), and [S8-T3 scalar evaluator cleanup](#s8-t3-remove-measured-scalar-evaluator-waste-when-triggered).

10. Sprint 9 — Conditional row-group and source-refresh behavior. Goal: prevent repeated row-group conversion and stale table state only where the fixtures prove those cases matter. Demo: a multi-row-group fixture does not thrash, and a changed local Parquet source either swaps in atomically or clearly reports that restart is required. Tasks: [S9-T1 row-group gate and cache](#s9-t1-gate-and-fix-multi-row-group-thrashing), [S9-T2 source-change detection](#s9-t2-detect-table-source-version-changes), and [S9-T3 atomic source refresh](#s9-t3-add-atomic-local-table-refresh-when-triggered).


## Concrete Steps


Run all commands from `D:\dev\lenslet` unless a command explicitly changes directory. Before every ticket, inspect the working tree and keep unrelated user changes out of the ticket commit.

    git status --short
    python -m pytest <focused test paths>
    cd frontend
    npm test -- <focused test paths>

At each sprint boundary, run the focused backend and frontend suites, build the frontend, copy built assets, run repository lint, and execute the sprint’s live demo. Do not copy assets after a failed frontend test or build.

    python -m pytest tests/browse tests/storage/table tests/web/routes tests/web/sync tests/web/cache
    cd frontend
    npm test
    npm run build
    Copy-Item -Recurse -Force dist\* ..\src\lenslet\frontend\
    cd ..
    python scripts/lint_repo.py
    python -m scripts.browser.gui_smoke.acceptance


### Task/Ticket Details


1. <a id="s0-t1-add-repeatable-latency-fixtures-and-a-probe"></a>**S0-T1: Add repeatable latency fixtures and a probe.** Goal: reproduce the 2,000-row, 30-metric, 300-rated, four-filter case without private data and optionally probe a user-supplied Parquet path read-only. Add a focused fixture builder and `scripts/perf/table_query_latency.py`, with JSON output for warmup count, repetitions, p50/p95 endpoint wall time, response bytes, query/facet phase durations, and sidecar counts. Affected areas: `scripts/perf`, `tests/scripts`, and shared table fixture helpers. Validation: the script produces stable machine-readable output, rejects mutation of its input, and a unit test validates schema and percentile calculation.

2. <a id="s0-t2-instrument-server-phases-and-stale-work"></a>**S0-T2: Instrument server phases and stale work.** Goal: distinguish queue wait, analysis, ordering, facet aggregation, window projection, serialization, thumbnail work, mutation acceptance, writer flush, and cancelled/abandoned work. Add small monotonic timers and counters owned by `AppRuntime`; expose request phase values through `Server-Timing` and aggregate counters through the existing health diagnostics. Affected areas: `src/lenslet/web/runtime.py`, `src/lenslet/web/routes/folders.py`, `src/lenslet/web/browse.py`, `src/lenslet/web/media.py`, and health tests. Validation: route tests assert named timing phases without requiring exact durations, and counter tests prove completed, joined, superseded, and cancelled work are distinct.

3. <a id="s0-t3-add-the-live-annotation-and-filter-browser-scenario"></a>**S0-T3: Add the live annotation and filter browser scenario.** Goal: capture visible refresh, projection latency, request counts, response sizes, and stale-request behavior in a real browser. Add a narrow `scripts/browser/annotation_latency` scenario using the synthetic fixture and Playwright request/response listeners; record gallery-root identity, visible paths, active loading state, query/facet requests, and analysis diagnostics. Validation: the baseline scenario runs independently, writes JSON evidence, and intentionally records current duplicate/reset behavior without treating the pre-fix result as success.

4. <a id="s1-t1-carry-one-mutation-identity-through-response-and-sync"></a>**S1-T1: Carry one mutation identity through response and sync.** Goal: let a browser recognize its mutation response and owner SSE echo as one command. Reuse the existing `Idempotency-Key` as the stable mutation ID, return the Sprint 1 envelope `{sidecar, mutation_id}`, and include the same ID plus `changed_fields` in `item-updated` and `metrics-updated` events. Persistence and event-watermark fields are deliberately added only in Sprint 7. Affected areas: `src/lenslet/web/models.py`, `src/lenslet/web/routes/items.py`, `src/lenslet/web/app/shared.py`, `src/lenslet/web/sync/events.py`, `frontend/src/api/client.ts`, `frontend/src/lib/types.ts`, and collaboration tests. Validation: response-first and event-first tests produce one logical mutation, idempotent retry returns the same identity/result, and a remote browser still receives the event.

5. <a id="s1-t2-classify-query-dependencies"></a>**S1-T2: Publish authoritative query dependencies.** Goal: determine whether star, notes, tags/search text, dimensions, or named metrics can affect one canonical active analysis without duplicating query semantics in TypeScript. Add one backend dependency extractor for the normalized query AST, sort, search, derived metric, and requested facets; return its manifest with query/facet results. The frontend only intersects mutation `changed_fields` with the returned field/key sets, and `unknown: true` conservatively requires reconciliation. Affected areas: `src/lenslet/browse/query.py`, query/facet web models, `frontend/src/lib/types.ts`, and response tests. Validation: backend table-driven tests cover every filter/sort clause, derived terms, text search, facets, irrelevant annotation changes, and unknown future clauses; frontend tests cover only manifest intersection and unknown fallback.

6. <a id="s1-t3-replace-global-resets-with-projection-and-single-flight-reconciliation"></a>**S1-T3: Replace global resets with projection and single-flight reconciliation.** Goal: update a known item immediately while retaining visible data and scheduling only necessary backend repair. Introduce one `AnnotationReconciler` per browser session with 512 seen mutation IDs retained for ten minutes, one active reconciliation, and one dirty trailing pass. Remove mutation and sync `resetQueries(['folder-query'])`; use active-key stale-while-revalidate. Conclusively failing loaded items may be removed locally, while entry from unloaded pages and uncertain order remain backend-owned. Affected areas: `frontend/src/api/items.ts`, `frontend/src/app/hooks/useAppSyncEvents.ts`, `frontend/src/app/model/appShellStateSync.ts`, `frontend/src/app/AppShell.tsx`, and focused frontend tests. Validation: unfiltered star changes cause zero query/facet requests; `Rating is None` changes remove the visible item synchronously and cause one active reconciliation; owner echo cannot schedule a second; a rapid burst permits only one trailing pass; ID retention never exceeds its count or TTL bound.

7. <a id="s1-t4-lock-the-no-refresh-and-multi-editor-contract"></a>**S1-T4: Lock the no-refresh and multi-editor contract.** Goal: prove behavior across two independent browser sessions. Extend the annotation latency browser scenario to open two contexts, annotate from each, and observe remote projection and per-session request counts while preserving the gallery DOM and scroll anchor. Validation: projection p95 is at most 100 milliseconds on the controlled fixture, no page-clearing loading state occurs, each session respects the active-plus-trailing bound, and authoritative counts converge.

8. <a id="s2-t1-build-the-table-query-column-store"></a>**S2-T1: Build the table query column store.** Goal: normalize immutable query fields once at table launch. Add a focused module such as `src/lenslet/storage/table/query_engine.py` with stable row IDs and column vectors for path, name, added time, dimensions, source/url, scalar metrics, and categoricals. Reuse PyArrow conversion where it avoids Python object expansion, but expose a small storage-owned interface rather than PyArrow objects to web code. Validation: fixture tests prove row/path stability, missing and non-finite normalization, one-time conversion, and no more than 16 MiB of reported column buffers for the 2,000-by-300 scalar fixture.

9. <a id="s2-t2-add-mutable-annotation-columns-and-dependency-generations"></a>**S2-T2: Add mutable annotation columns and dependency generations.** Goal: reflect accepted sidecar changes in O(1) row updates and invalidate only analyses that depend on changed fields. Maintain path-to-row lookup plus compact star, notes/search, tags, and dynamic metric state. Track static-source generation and dependency stamps for star, text, and metric keys. Affected areas: the new query engine, `src/lenslet/storage/table/storage.py`, and mutation integration. Validation: one row update changes the correct column/generation only, irrelevant analyses retain valid stamps, and concurrent reads see an immutable analysis snapshot.

10. <a id="s2-t3-evaluate-text-and-built-in-filters-over-columns"></a>**S2-T3: Evaluate text and built-in filters over columns.** Goal: produce candidate row IDs for text search, star, notes, URL, date, width, and height clauses without constructing `BrowseQueryRecord` per candidate. Read only referenced columns and check cancellation at least every 256 rows or 25 milliseconds, whichever comes first. Validation: use the generic evaluator as a golden oracle across randomized fixtures and documented missing-value/date/search edge cases; assert zero full-scope query-record materializations.

11. <a id="s2-t4-evaluate-metric-and-categorical-filters-over-columns"></a>**S2-T4: Evaluate metric and categorical filters over columns.** Goal: apply named metric ranges and categorical membership to candidate row IDs without expanding unreferenced fields. Preserve missing, null, non-finite, and normalization semantics. Validation: randomized golden parity covers wide fixtures, absent keys, non-finite values, categorical nulls, multiple clauses, and cancellation at the 256-row/25-millisecond checkpoint.

12. <a id="s2-t5-evaluate-derived-scores-without-row-records"></a>**S2-T5: Evaluate derived scores without row records.** Goal: compute z-statistics, missing policies, categorical terms, score validity, and derived filters directly from referenced columns while retaining row-ID alignment. Validation: parity tests cover applied, invalid, and unavailable status; missing inputs; zero variance; numeric normalization; categorical terms; and cancellation around each population pass.

13. <a id="s2-t6-order-row-ids-with-stable-semantics"></a>**S2-T6: Order row IDs with stable semantics.** Goal: implement built-in, metric, derived, and deterministic random order over the filtered population with the final stable row-ID tie-breaker. Keep unordered filtered population separate so facets never sort. Validation: parity tests cover missing metrics, duplicate values, name/date direction, deterministic random pages, non-overlapping offsets, and cancellation before and after the ordering stage.

14. <a id="s2-t7-materialize-only-the-returned-window"></a>**S2-T7: Materialize only the returned window.** Goal: cut `TableStorage.query_browse_scope` over to row-ID analysis and slice before any item construction. Keep a temporary test-only generic-oracle path until parity is proven, then hard-delete the production rich-record path rather than retain a compatibility branch. Validation: counters prove a limit-200 request constructs at most 200 window items regardless of scope or metric width; all existing browse-query and Parquet-ingestion tests pass.

15. <a id="s3-t1-separate-filter-order-and-window-identities"></a>**S3-T1: Separate filter, order, and window identities.** Goal: let facets, sort variants, pagination, and projections reuse the correct layer without cache-key ambiguity. Define immutable `TableFilterAnalysis`, `TableOrderAnalysis`, and projection keys. Filter identity includes scope, normalized filters/search/derived terms, source generation, and only relevant mutable dependency stamps; order identity adds sort/random seed; window identity adds offset, limit, and projected fields. Validation: key tests prove semantic changes invalidate the right layer while offset, limit, and projection never trigger a new filter pass.

16. <a id="s3-t2-add-a-bounded-analysis-coordinator"></a>**S3-T2: Add a bounded analysis coordinator.** Goal: execute one GIL-bound analysis worker app-wide, join identical in-flight work, retain at most eight completed filter and eight completed order analyses, and admit at most 32 distinct queued analyses across all storage snapshots. Coalesce superseded queued revisions from one session, schedule admitted sessions round-robin, return `503 analysis_busy` with `Retry-After: 1` when no safe admission is possible, and stop at the 256-row/25-millisecond checkpoint when no live subscriber remains. Affected areas: a new `src/lenslet/storage/table/query_coordinator.py`, `src/lenslet/web/runtime.py`, and lifecycle shutdown. Validation: deterministic concurrency tests prove one execution for identical subscribers, exact cache/queue caps, cross-session fairness, no cross-generation reuse, admission failure without unbounded state, and cancellation within one checkpoint.

17. <a id="s3-t3-add-the-browser-session-and-query-revision-protocol"></a>**S3-T3: Add the browser session and query revision protocol.** Goal: supersede obsolete work even when fetch abort does not cancel the server thread. Generate a per-tab session ID in `sessionStorage`; send it with a monotonically increasing semantic query revision on query and facet requests. Pagination and field projections reuse the same revision; a path/filter/sort/search/derived change increments it. Use explicit headers such as `X-Lenslet-Client-Session` and `X-Lenslet-Query-Revision`; they identify work ownership, not authorization. Validate header lengths and integers, retain no more than 256 inactive session records for five minutes using LRU eviction, and remove disconnected subscribers. Validation: frontend tests cover revision boundaries and server tests prove a newer revision retires only the older revision from the same session while hostile unique headers cannot grow registry state beyond its cap.

18. <a id="s3-t4-cut-query-and-facets-over-to-shared-analysis"></a>**S3-T4: Cut query and facets over to shared analysis.** Goal: make both async routes await the coordinator and derive their window or aggregates from the same filtered analysis. A disconnected request unsubscribes; it does not kill shared work with another subscriber. Generic non-table storage uses the same bounded route boundary but may retain its existing evaluator. Validation: simultaneous query and facet calls report one filter execution, facets report no ordering phase, and output remains contract-compatible with current semantics until Sprint 4’s hard cutover.

19. <a id="s3-t5-prove-deduplication-cancellation-and-bounds"></a>**S3-T5: Prove deduplication, cancellation, and bounds.** Goal: validate the reported churn case, not only isolated functions. Add a slow checkpoint-controlled fake engine and the real 2,000-row fixture. Validation: ten rapid revisions do not complete ten scans, a ten-character committed filter uses one revision, two sessions may share identical work without cancelling each other, 40 distinct requests exercise admission and fairness without exceeding 32 queued, combined browser query-plus-facet p95 is below one second after five warmups and 20 measured repetitions, and coordinator diagnostics return to zero active/queued work after quiescence.

20. <a id="s4-t1-add-an-explicit-window-projection-contract"></a>**S4-T1: Add an explicit window projection contract.** Goal: return core card fields plus only metric/categorical fields required by the current view, while leaving full inspector detail on `/item`. Add a typed projection to the browse request, capped at 64 metric and 32 categorical keys. Projection does not affect analysis identity, but it does affect window/request identity. Affected areas: `src/lenslet/web/models.py`, `src/lenslet/browse/query.py`, `frontend/src/lib/types.ts`, and request serialization tests. Validation: malformed or over-limit projections fail at the boundary, requested fields are present, omitted fields are absent, and inspector detail remains complete.

21. <a id="s4-t2-remove-repeated-window-payload-conversion"></a>**S4-T2: Remove repeated window payload conversion.** Goal: construct the lean web DTO once from returned row IDs without `_materialize_query_record_item` recoercion, generic `to_item`, repeated `build_item_payload`, repeated categorical extraction, or repeated media-policy parsing. Affected areas: `src/lenslet/storage/table/storage.py`, `src/lenslet/web/browse.py`, and route payload tests. Validation: phase counters show one conversion per returned row; the named 1,000-row response with core fields plus three metrics is at most 1.0 MB versus the roughly 2.33 MB baseline; adding unrequested table columns does not change response bytes; query semantics remain exact.

22. <a id="s4-t3-implement-the-frontend-entity-store"></a>**S4-T3: Implement the frontend entity store.** Goal: provide a path-keyed `BrowseEntityStore` with immutable snapshots, per-path subscriptions, batch ingestion, one-path patching, and explicit eviction independent of query-page order. Retain all entities referenced by active pages plus at most 2,000 unreferenced entities for five minutes. Do not migrate consumers in this ticket. Affected areas: a new frontend entity-store module and focused tests. Validation: unrelated entity identities remain unchanged, one path notification fires, batch ingestion is deterministic, active entities cannot be evicted, and unreferenced retention obeys both limits.

23. <a id="s4-t4-migrate-query-pages-and-grid-consumers-to-normalized-entities"></a>**S4-T4: Migrate query pages and grid consumers to normalized entities.** Goal: make query pages retain stable path order and metadata while ingestion writes item DTOs to `BrowseEntityStore`; migrate `useAppDataScope`, grid cards, selection, viewer, and inspector consumers without changing visible behavior. Validation: pagination order, selection, viewer navigation, scroll restoration, and inspector detail pass focused tests and the live browser scenario; a one-item patch does not replace unrelated pages or entities.

24. <a id="s4-t5-retire-broad-query-membership-reindexing"></a>**S4-T5: Retire broad query membership reindexing.** Goal: eliminate `O(K * N)` removal/re-addition for normalized `folder-query` variants and bound retained variants. Remove folder-query dependence on `ItemQueryPathIndex`, ignore cache events without data/membership identity changes for any remaining legacy query types, and retain only the active plus two recent variants per path. Validation: seeding 50 cached variants does not change one annotation’s patch operation count; no `setQueryData` feedback loop occurs; inactive variants are collected deterministically at the three-variant cap.

25. <a id="s4-t6-remove-render-time-whole-window-cleanup"></a>**S4-T6: Remove render-time whole-window cleanup.** Goal: stop cloning all items for local-star overlays and scanning every metric mapping for derived-key cleanup on each render. Make derived-field normalization an ingestion/server invariant and derive path/selection structures from stable path pages. Validation: profiler counters in tests show one-item annotations do not invoke full metric cleanup or rebuild every entity; live scroll anchor and viewer focus remain stable.

26. <a id="s5-t1-separate-free-text-filter-drafts-from-committed-state"></a>**S5-T1: Separate free-text filter drafts from committed state.** Goal: make filename, notes, and URL controls behave like deliberate query inputs. Keep draft text local, commit after a short 250-millisecond idle debounce or immediately on Enter, Apply, or blur, and cancel the timer on unmount. Discrete star/categorical controls remain immediate. Validation: fake-timer tests prove ten keystrokes commit once, Enter commits once without a later duplicate, blur flushes, and reopening reflects committed state.

27. <a id="s5-t2-make-facet-aggregation-field-scoped-and-lazy"></a>**S5-T2: Make facet aggregation field-scoped and lazy.** Goal: avoid aggregating every metric and categorical field when only a few are visible. Extend the facet request with at most 24 validated requested metric/categorical keys per batch and aggregate directly from filtered row IDs and columns. Cache/merge field batches under one analysis key. Validation: one selected metric reads one metric column, over-limit batches fail, a valid batch returns only those keys, derived fields remain correct, and changing requested fields reuses filter analysis.

28. <a id="s5-t3-virtualize-wide-metrics-and-categorical-panels"></a>**S5-T3: Virtualize wide Metrics and categorical panels.** Goal: render visible cards plus four-row overscan using existing TanStack Virtual, request facet batches for the visible range, and remove population-by-field nested scans from render. Preserve search, selection, ordering, expanded cards, and keyboard accessibility. Validation: the controlled 300-field viewport mounts no more than 40 cards, scrolling loads the next aggregate batch, focused controls remain stable, and no loaded-window counts are presented as authoritative.

29. <a id="s5-t4-lock-wide-table-and-input-storm-acceptance"></a>**S5-T4: Lock wide-table and input-storm acceptance.** Goal: exercise the complete UI against a wide synthetic Parquet table. Extend the live scenario to type ten characters, open “Show all,” scroll through fields, annotate, and inspect request/DOM counts. Validation: one committed query and one facet batch are produced per input commit, mounted metric cards stay bounded to viewport plus overscan, first useful panel render remains below 500 milliseconds on the controlled fixture, and combined query-plus-facet wall time remains below one second.

30. <a id="s6-t1-add-a-bounded-thumbnail-work-coordinator"></a>**S6-T1: Add a bounded thumbnail work coordinator.** Goal: move cache reads, decoding, resizing, encoding, and eviction out of the asyncio event loop and deduplicate identical thumbnail keys. Own at most four workers, a 128-job queue, and 256 in-flight deduplication entries in app runtime; apply backpressure with `503 thumbnail_busy` rather than spawning unbounded default-executor work, and shut it down cleanly. Validation: concurrency tests prove exact worker/queue/deduplication limits, identical misses join once, cancellation drops unsubscribed queued work, admission failure is explicit, and media error contracts remain intact.

31. <a id="s6-t2-make-thumbnail-persistence-best-effort"></a>**S6-T2: Make thumbnail persistence best-effort.** Goal: return generated bytes before optional cache persistence completes, remove per-thumbnail `fsync`, preserve atomic replace, and make cache write/eviction failure a logged performance degradation rather than a failed image response. Validation: hit, miss, corrupt cache, failed write, and eviction tests all return or fail according to media semantics rather than cache durability.

32. <a id="s6-t3-prove-thumbnail-work-does-not-block-http-or-sse"></a>**S6-T3: Prove thumbnail work does not block HTTP or SSE.** Goal: inject slow cache reads and writes while serving health, query, and collaboration traffic. Validation: a 500-millisecond thumbnail operation leaves event-loop heartbeat gaps below 100 milliseconds, health and SSE responses complete while it runs, and the annotation browser scenario does not gain a thumbnail-dependent tail.

33. <a id="s7-t1-introduce-the-label-write-buffer-and-watermark"></a>**S7-T1: Introduce the label write buffer and watermark.** Goal: accept ordered label events into memory, flush after approximately one second of idle time, and complete append, flush, and `fsync` by 15 seconds from the oldest pending event. Use monotonic time and begin deadline flush no later than 13 seconds, reserving two seconds for healthy I/O. Admit at most 10,000 pending events or 16 MiB; reject before mutating in-memory state when either cap is full. Define boot epoch, composite accepted event identity, durable watermark, pending count/bytes, oldest age, and healthy/failed state. Affected areas: a new persistence coordinator near `src/lenslet/web/sync`, `src/lenslet/workspace.py`, and runtime diagnostics. Validation: fake-clock tests cover idle flush, continuous traffic, exact count/byte admission caps, ordered batches, retry without duplication, slow successful writes near the deadline, and a completed durable watermark no later than 15 seconds on storage whose flush completes within the reserved two-second margin.

34. <a id="s7-t2-remove-disk-io-from-broker-and-sidecar-critical-sections"></a>**S7-T2: Remove disk I/O from broker and sidecar critical sections.** Goal: reserve event order, mutate in-memory sidecar/query columns, enqueue the label event, and broadcast without holding broker or sidecar locks across disk. Replace `publish_after_commit` with narrow reserve/commit/publish operations whose lock order is documented. Extend the Sprint 1 mutation envelope with `{accepted_event: {boot_epoch, event_id}, persistence, durable_watermark}` only at this cutover. Validation: an injected 500-millisecond writer cannot delay event replay, client registration, another in-memory mutation, or SSE broadcast by more than 100 milliseconds.

35. <a id="s7-t3-move-snapshot-and-compaction-behind-the-durable-watermark"></a>**S7-T3: Move snapshot and compaction behind the durable watermark.** Goal: snapshot only durable state, persist mutation IDs needed for idempotent restart, and compact only log entries at or below the durable watermark. Snapshot construction runs outside request, broker, sidecar, and writer-queue locks. Validation: restart tests reconstruct exactly the durable watermark and durable idempotency index, compaction cannot drop pending events, and a retry of an already-durable mutation does not create a duplicate event.

36. <a id="s7-t4-integrate-writer-lifecycle-boot-epochs-and-shutdown"></a>**S7-T4: Integrate writer lifecycle, boot epochs, and shutdown.** Goal: start the writer with a new opaque boot epoch, expose a reconnect state endpoint containing epoch and durable watermark, and force pending writes before graceful shutdown completes. When a client reconnects to a different epoch, it refetches paths observed above the prior watermark plus the active query/facets; new event IDs cannot be compared to the previous epoch. Affected areas: `src/lenslet/web/lifecycle.py`, runtime/sync routes, frontend connection state, and restart tests. Validation: TestClient shutdown leaves no pending healthy events; restart while edits are pending visibly reconciles owner and remote clients to durable state; retrying a lost non-durable mutation applies once in the new epoch, while retrying a durable mutation reuses its persisted result.

37. <a id="s7-t5-expose-pending-saved-and-failed-persistence-state"></a>**S7-T5: Expose pending, saved, and failed persistence state.** Goal: make the lazy contract visible. Health, reconnect state, and a lightweight sync event expose boot epoch, durable watermark, pending capacity, and failure. The frontend sync indicator shows Saving while local accepted identities exceed the watermark, Saved when caught up in the same epoch, and a persistent actionable error on writer failure or deadline breach. Validation: frontend state-machine tests cover response/event reordering, multiple tabs, epoch change, reconnect path repair, watermark recovery, and failure recovery without claiming data is durable early.

38. <a id="s7-t6-lock-the-15-second-crash-and-failure-contract"></a>**S7-T6: Lock the 15-second, crash, and failure contract.** Goal: prove the chosen durability tradeoff end to end. Add tests for crash simulation before and after flush, slow-but-successful I/O, permanent disk failure, recovery and retry, graceful shutdown, continuous edits, and admission saturation. Once the writer is failed or misses its completion deadline, retain pending memory state, surface the error, and reject new mutations with a clear 503 until persistence recovers. Validation: normal idle changes persist promptly, continuous healthy writes complete by 15 seconds, failure is visible within one writer attempt, lost pre-crash projections reconcile away, durable retries do not duplicate, and no accepted durable watermark is fabricated.

39. <a id="s8-t1-evaluate-operational-tail-gates"></a>**S8-T1: Evaluate operational tail gates.** Goal: compare post-Sprint-7 diagnostics against the Sprint 0 baseline and record whether polling/retry or scalar-evaluator work remains material. Trigger polling/retry work if live SSE coexists with polling, timers create overlapping browse work, or retry delay contributes at least 100 milliseconds p95. Trigger scalar cleanup if parsing/sort-key construction contributes at least ten percent of analysis time. Validation: write a dated evidence note under `docs` with commands, fixture, counters, and explicit proceed/skip decisions.

40. <a id="s8-t2-coordinate-fallback-polling-and-retries-when-triggered"></a>**S8-T2: Coordinate fallback polling and retries when triggered.** Goal: ensure polling is disabled while SSE is healthy, use one jittered fallback scheduler after disconnect, deduplicate overlapping folder/query/facet/sidecar polls, and retry only idempotent operations for at most three attempts with full jitter capped at two seconds. Affected areas: `frontend/src/api/client.ts`, `frontend/src/api/folders.ts`, `frontend/src/api/items.ts`, and query defaults in `frontend/src/App.tsx`. Validation: fake-timer tests prove no live-SSE polls, no aligned herd, no duplicate in-flight key, the three-attempt/two-second cap, and recovery after a simulated disconnect.

41. <a id="s8-t3-remove-measured-scalar-evaluator-waste-when-triggered"></a>**S8-T3: Remove measured scalar evaluator waste when triggered.** Goal: preparse invariant date bounds, avoid reverse-Unicode string construction, skip facet ordering, and remove repeated categorical `.as_py()` conversion only where profiling still shows those paths after the columnar cutover. Validation: golden semantic tests remain unchanged and the triggering phase improves materially without adding a second query engine.

42. <a id="s9-t1-gate-and-fix-multi-row-group-thrashing"></a>**S9-T1: Gate and fix multi-row-group thrashing.** Goal: create a multi-row-group Parquet fixture and alternate detail reads across groups. If query-column preload already removes the repeated work and detail p95 stays below 50 milliseconds, record a skip. Otherwise replace the one-row-group provider cache with a four-row-group LRU keyed by row-group index. Validation: conversion count is bounded by four-entry LRU behavior, memory is capped, and alternating access no longer rereads every group.

43. <a id="s9-t2-detect-table-source-version-changes"></a>**S9-T2: Detect table source version changes.** Goal: prevent a running local table from silently serving an old snapshot after its source file changes. Track a cheap local source fingerprint and expose current, refreshing, stale, or restart-required state through health and sync. Remote providers without a safe version primitive explicitly report restart-required. Validation: replacing a fixture Parquet file triggers one state transition without mixing old and new rows.

44. <a id="s9-t3-add-atomic-local-table-refresh-when-triggered"></a>**S9-T3: Add atomic local table refresh when triggered.** Goal: if live refresh is required by the source-change gate, build a complete new row store/query engine off to the side, preserve sidecars by canonical path, and atomically swap the storage snapshot and generation. Existing requests finish on their captured snapshot; new requests use the new one; the frontend receives one source-generation reconciliation. Validation: a live browser sees either the complete old dataset or complete new dataset, never a mixture; removed/added paths and sidecars behave predictably; failed rebuild leaves the old snapshot active with a visible error.


## Validation and Acceptance


Sprint 0 is accepted when the synthetic fixture and optional named Parquet probe emit repeatable JSON and the browser scenario captures the current refresh and request fan-out. The harness must measure p50 and p95 after warmup and must keep correctness counts separate from performance thresholds.

Sprint 1 is accepted when the next painted animation frame showing the projected annotation occurs within 100 milliseconds of the input event, no gallery-clearing refresh occurs, an irrelevant edit causes no browse/facet request, and a relevant edit causes at most one active plus one trailing reconciliation per browser session. Playwright records the input timestamp and observes the first matching `requestAnimationFrame`. Two browser contexts must converge without suppressing either editor’s independent work.

Sprints 2 and 3 are accepted when generic-evaluator parity passes, only returned rows are materialized, query and facets share one analysis, obsolete work stops within one 256-row/25-millisecond checkpoint, and the required 2,000-row fixture completes combined query-plus-facet p95 below one second. “Combined” is browser wall time from committing the semantic query revision until both the gallery query and required facet batch have settled. Run five warmups followed by 20 measured repetitions. If the named Parquet path is available, it must meet the same threshold read-only.

Sprints 4 and 5 are accepted when the named 1,000-row core-plus-three-metric response is at most 1.0 MB, adding unrequested source columns adds zero response bytes, a one-item patch preserves unrelated entity and page identity, 50 attempted cached variants do not amplify patch work beyond the active-plus-two-recent retention cap, ten rapid characters commit one semantic query revision, and 300-field Metrics “Show all” mounts only viewport plus overscan cards. Inspector data and all filter/sort semantics must remain correct.

Sprint 6 is accepted when an injected 500-millisecond thumbnail hit or miss leaves event-loop heartbeat gaps below 100 milliseconds and does not delay health or collaboration SSE. Cache failure must not turn a successfully generated thumbnail into an HTTP failure.

Sprint 7 is accepted when the normal idle flush occurs in approximately one second, append plus flush plus `fsync` for the oldest continuously pending healthy edit completes within 15 seconds by monotonic time, graceful shutdown leaves no healthy pending edits, and a failed or deadline-breaching writer produces a visible unsaved state and rejects further mutation rather than silently claiming durability. Restart recovery must reproduce exactly the durable watermark, roll the boot epoch, reconcile owner and remote clients that observed lost pending edits, and handle retries of both lost and already-durable mutation IDs without duplication.

Sprints 8 and 9 are accepted ticket by ticket. Each gate must leave explicit evidence even when the implementation ticket is skipped. A skipped conditional ticket is successful only when the stated fixture remains under its threshold and diagnostics show the suspected path is not material.

Overall acceptance requires the full backend and frontend tests, repository lint, frontend production build and copied assets, GUI smoke, the dedicated annotation latency scenario, and the performance probe. The final live scenario must cover `Rating is None` plus three metric filters, 300 pre-rated rows, rapid annotation, ten-character attribute input, Metrics “Show all,” two browser contexts, and thumbnail hydration.

    pytest
    cd frontend
    npm test
    npm run build
    Copy-Item -Recurse -Force dist\* ..\src\lenslet\frontend\
    cd ..
    python scripts/lint_repo.py
    python -m scripts.browser.gui_smoke.acceptance
    python -m scripts.browser.annotation_latency.acceptance
    python scripts/perf/table_query_latency.py --synthetic --repetitions 20 --output-json data/table_latency_result.json


## Idempotence and Recovery


All fixture and probe commands must be safe to repeat. Synthetic datasets are created in explicit temporary or output directories and never overwrite the user’s source Parquet. Optional named-dataset probing is read-only. Generated evidence uses caller-selected paths.

The implementation uses hard cutovers inside small tickets. Before deleting the old rich-record or frontend query-index path, parity and live acceptance must pass. If a sprint fails, revert only that sprint’s commits; earlier runnable increments remain valid. Do not use `git reset --hard` or overwrite unrelated working-tree changes.

The analysis coordinator owns all futures, cache entries, and executor shutdown. A failed or cancelled analysis removes its in-flight entry so a retry can run cleanly. Completed cache entries are immutable and generation-keyed, so restart or source-generation changes naturally discard them.

The label writer keeps pending entries in memory until a successful durable batch advances the watermark, subject to the 10,000-event/16-MiB admission cap. Retry writes are idempotent by composite boot-epoch/event identity, and durable mutation IDs are rebuilt on restart so an HTTP retry cannot duplicate a saved command. Snapshot compaction never crosses the durable watermark. Graceful shutdown retries a final flush and reports failure; it must not claim success or delete pending log data. Unexpected process termination may lose only events above the last durable watermark, which is the deliberate lazy-durability tradeoff. A new boot epoch makes those lost accepted identities incomparable, and reconnect refetches affected paths before clearing the unsaved state.

Atomic table refresh builds a new snapshot separately and swaps one reference only after validation. A failed refresh leaves the old snapshot serving and records stale/error state. Sidecars remain keyed by canonical path, so rebuilding row IDs does not rewrite user annotations.


## Artifacts and Notes


The investigation document is the measurement and rationale source:

    docs/20260717_table_query_annotation_latency_investigation.md

The required baseline result shape should remain stable enough to compare sprint evidence:

    {
      "fixture": "synthetic-2000x30",
      "query_p95_ms": 0,
      "facets_p95_ms": 0,
      "combined_p95_ms": 0,
      "response_bytes_p95": 0,
      "analysis_started": 0,
      "analysis_joined": 0,
      "analysis_superseded": 0,
      "analysis_cancelled": 0
    }

The browser evidence should include the session boundary explicitly:

    {
      "session_id": "opaque-per-tab-id",
      "semantic_revisions": 1,
      "query_requests": 1,
      "facet_requests": 1,
      "gallery_root_replaced": false,
      "annotation_projection_p95_ms": 0
    }

Keep performance assertions out of tiny unit tests when operating-system scheduling would make them flaky. Unit tests assert counts, identity, ordering, deadlines with fake clocks, and bounded operations. Controlled live probes enforce the 100-millisecond and one-second budgets and retain raw JSON evidence.


## Interfaces and Dependencies


The storage layer should expose narrow immutable analysis objects rather than web models. Exact names may follow repository conventions, but the responsibilities and identity boundaries are required:

    @dataclass(frozen=True, slots=True)
    class TableFilterAnalysis:
        key: str
        source_generation: str
        dependency_stamp: str
        row_ids: tuple[int, ...]
        derived_scores: Mapping[int, float]
        derived_status: DerivedMetricStatus

    @dataclass(frozen=True, slots=True)
    class TableOrderAnalysis:
        key: str
        filter_key: str
        ordered_row_ids: tuple[int, ...]

    class TableQueryEngine:
        def analyze_filter(self, spec: BrowseQuerySpec, cancel: CancellationProbe) -> TableFilterAnalysis: ...
        def order(self, analysis: TableFilterAnalysis, sort: BrowseSortSpec, cancel: CancellationProbe) -> TableOrderAnalysis: ...
        def project(self, order: TableOrderAnalysis, window: BrowseWindowSpec, projection: BrowseProjectionSpec) -> BrowseQueryResult: ...
        def facets(self, analysis: TableFilterAnalysis, fields: FacetFieldSpec, bins: int) -> FacetSummary: ...

The backend is the only source of query-dependency semantics. Query and facet results include a manifest that the browser can compare with mutation `changed_fields` without reimplementing the AST evaluator.

    @dataclass(frozen=True, slots=True)
    class QueryDependencyManifest:
        fields: frozenset[str]
        metric_keys: frozenset[str]
        categorical_keys: frozenset[str]
        unknown: bool = False

The coordinator is app-runtime-owned, globally bounded, fair across sessions, and subscriber-aware. It owns one analysis worker, at most 32 distinct queued analyses, eight completed filter entries, eight completed order entries, and 256 inactive session records with a five-minute TTL. Cancellation of one HTTP request removes only that subscriber; computation stops when all subscribers are gone or a generation is obsolete. When safe coalescing or admission is impossible, the route returns `503 analysis_busy` with `Retry-After: 1`.

    async def acquire_analysis(
        spec: BrowseQuerySpec,
        *,
        client_session: str,
        query_revision: int,
        disconnected: Callable[[], Awaitable[bool]],
    ) -> AnalysisLease: ...

Browse and facet requests carry per-tab ownership headers. The server validates length and revision range but never treats them as authentication.

    X-Lenslet-Client-Session: <opaque sessionStorage UUID>
    X-Lenslet-Query-Revision: <monotonic integer>

The item mutation response changes in two explicit hard cutovers. Sprint 1 returns only the sidecar and mutation identity, and collaboration events echo that identity plus authoritative changed fields.

    {
      "sidecar": { "version": 2, "star": 1 },
      "mutation_id": "patch-..."
    }

Sprint 7 extends that envelope after the write buffer and boot epoch exist. The existing idempotency key remains the mutation identity and is persisted with durable events.

    {
      "sidecar": { "version": 2, "star": 1 },
      "mutation_id": "patch-...",
      "accepted_event": { "boot_epoch": "epoch-...", "event_id": 42 },
      "persistence": "pending",
      "durable_watermark": { "boot_epoch": "epoch-...", "event_id": 41 }
    }

The label writer owns the lazy persistence contract. A one-second idle target improves immediate external consumption; successful append, flush, and `fsync` by 15 seconds is the hard healthy-storage requirement. The deadline uses monotonic time, begins its forced flush by 13 seconds, and treats I/O that errors or exceeds the two-second completion reserve as unhealthy.

    class LabelWriteBuffer:
        def accept(self, event: LabelEvent) -> AcceptedEventIdentity: ...
        def status(self) -> LabelPersistenceStatus: ...
        async def flush_due(self) -> None: ...
        async def flush_all(self) -> None: ...

The buffer checks its 10,000-event and 16-MiB limits before the sidecar mutation becomes visible. The reconnect interface returns `boot_epoch`, `durable_watermark`, and writer status. On an epoch change the browser refetches every path it observed above the previous watermark and then reconciles the active query/facets.

Do not add dependencies. Backend work uses the standard library, FastAPI/Pydantic, and existing PyArrow. Frontend work uses React, TanStack Query, and TanStack Virtual already declared in `frontend/package.json`. Keep public dataset sources read-only; only workspace logs, snapshots, generated performance fixtures, and best-effort caches may be written.

Revision note: 2026-07-17 initial execution plan drafted from the completed latency investigation and the user’s decisions to defer conditional work, scope reconciliation per browser session, and use observable lazy persistence with a 15-second hard bound. Independent review then added boot-epoch recovery, completion-based durability, explicit capacity limits and admission behavior, an authoritative dependency manifest, staged mutation contracts, four ticket splits, and precise performance measurements.
