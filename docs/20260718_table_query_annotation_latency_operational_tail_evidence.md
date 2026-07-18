# Sprint 9 Operational Tail Gate Evidence


## Scope


This note evaluates the conditional Sprint 9 gates after Sprint 8. The required fixture is the generated 2,000-row Parquet table with 300 persisted ratings. The private named Parquet path was not supplied, so no private input was read or modified.


## Commands


    python scripts/perf/table_query_latency.py --synthetic --repetitions 20 --output-json docs/20260718_table_query_annotation_latency_s9_table_post.json
    python -m scripts.browser.annotation_latency.acceptance --output-json docs/20260718_table_query_annotation_latency_s9_browser_post.json
    python scripts/perf/table_scalar_tail.py --output-json docs/20260718_table_query_annotation_latency_s9_scalar_post.json

`scripts/perf/table_scalar_tail.py` is the exact `cProfile` driver. It performs 20 direct `TableQueryEngine` calls on 2,000 accepted HTTP-source rows and emits function call counts plus self/cumulative time. Direct engine calls intentionally bypass coordinator caching so the measured share represents scalar analysis work. The retained pre-change artifact was generated against Sprint 8 commit `7667568` with the same driver on `PYTHONPATH`; the worktree command and output are reproducible without modifying the active checkout.

    profile_root=$(mktemp -d /tmp/lenslet-s9-pre.XXXXXX)
    git worktree add --detach "$profile_root/repo" 7667568
    PYTHONPATH="$profile_root/repo/src" python -m scripts.perf.table_scalar_tail --output-json "$profile_root/scalar_pre.json"
    PYTHONPATH="$profile_root/repo/src" python "$profile_root/repo/scripts/perf/table_query_latency.py" --synthetic --repetitions 20 --output-json "$profile_root/table_pre.json"
    git worktree remove "$profile_root/repo"

The retained `*_pre.json` files are copies of those completed temporary outputs. Reproduction does not write into the active checkout; the two raw files remain under the printed `$profile_root` for inspection and deliberate cleanup.


## Post-Sprint-8 Evidence


The Sprint 0 baseline was 293.798 milliseconds combined p95 (203.699 query and 89.445 facets), 1,524,101 decoded response bytes, and 70.932 milliseconds analysis p95 before the core cutovers. The post-Sprint-8 stable query/facet probe passed with unchanged inputs and correct totals at 74.336 milliseconds combined p95 (42.248 query and 33.479 facets), 648,302 response bytes p95, and only two analyses started. That is about 75 percent lower combined p95 and 57 percent fewer response bytes than Sprint 0. Warm query analysis and ordering p95 were 0.040 and 0.015 milliseconds because the coordinator reused the completed analysis.

The accepted two-session browser scenario measured 60.530 milliseconds annotation projection. Each relevant mutation caused one query and one facet request per session, normal mutation phases had no failed requests, and every phase reached zero in-flight requests. The deliberate supersession check produced only its expected aborted stale query/facet pair, followed by one successful fresh pair. Ten filter characters committed one query/facet pair in 627.011 milliseconds, and the backend finished with zero active or queued analysis work.

The SSE/polling ownership audit found that `EventSource.onopen` disables fallback polling. Polling becomes eligible only after five failed reconnect attempts, and folder, facet, and sidecar intervals are conditional on that single state. The accepted live-SSE run did not enter that fallback state or incur a retry delay.

Cold scalar profiling found material work outside the standard warm query:

- Date filtering: 20 analyses took 517.990 milliseconds; 80,000 bound parses consumed 212.977 milliseconds cumulatively, about 41 percent of wall time.
- Descending name ordering: 20 orders took 788.110 milliseconds; 80,000 reverse-Unicode key constructions consumed 743.614 milliseconds cumulatively, about 94 percent of wall time.
- Descending added ordering: 20 orders took 824.484 milliseconds; 80,000 reverse-Unicode key constructions consumed 750.250 milliseconds cumulatively, about 91 percent of wall time.

Facet aggregation already consumes filtered row IDs without sorting the population, and categorical values are normalized into the column store rather than converted with `.as_py()` during each request.


## Decisions


S9-T2 is skipped. Healthy SSE does not coexist with fallback polling in the measured path, timers did not create overlapping browse work, and no retry delay contributed to accepted-path p95. The gate can be revisited only with recorded disconnect/failure evidence.

S9-T3 is triggered for exactly two changes: parse invariant date bounds once per analysis and replace descending name/added complemented-string allocation with a shared lightweight comparison key that preserves the prior code-point, prefix, tie, missing-date, and invalid-date order. Facet ordering, categorical conversion, polling, and retry policy remain unchanged because their triggers were not met.


## Post-Change Evidence


The same retained cold profile reduced 20 date-filter analyses from 517.990 to 288.968 milliseconds. Bound parsing fell from 80,000 calls and 212.977 cumulative milliseconds to 40 calls and 0.214 milliseconds. Twenty descending name orders fell from 788.110 to 90.961 milliseconds, and 20 descending added orders fell from 824.484 to 84.677 milliseconds. No complemented string is constructed; the existing prefix/tie behavior remains explicit in independent expected-order tests.

Focused generic/table semantic and invariant checks passed 42 tests, including prefix names, same-name identity prefixes, Unicode, unequal and tied dates, missing/invalid dates, malformed bounds, and once-per-analysis/evaluation bound parsing. The table engine also has a direct equal-basename fixture that independently asserts stable-identity prefix, Unicode, positive, zero, and missing-time order. A focused route-inclusive post-review gate passed 68 tests. The unchanged-input final 20-repetition synthetic probe passed at 74.332 milliseconds combined p95, with correct totals, 648,302 response bytes p95, and two analyses started.

The final-worktree browser rerun passed at 56.975 milliseconds annotation projection, one query and one facet reconciliation per relevant session/mutation, no page clear, bounded stale-request cancellation, and zero active/queued analysis work after quiescence. Final broad validation is recorded in the execution plan and Ralph progress log.


## Retained Artifacts


- `docs/20260718_table_query_annotation_latency_s9_table_pre.json`
- `docs/20260718_table_query_annotation_latency_s9_table_post.json`
- `docs/20260718_table_query_annotation_latency_s9_browser_pre.json`
- `docs/20260718_table_query_annotation_latency_s9_browser_post.json`
- `docs/20260718_table_query_annotation_latency_s9_scalar_pre.json`
- `docs/20260718_table_query_annotation_latency_s9_scalar_post.json`
