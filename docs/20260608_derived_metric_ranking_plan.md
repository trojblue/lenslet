# Derived Metric Ranking Implementation Plan



## Outcome + Scope Lock



After implementation, a user browsing a table-backed gallery can open Metrics, define one active derived score from numeric fields such as `q1` through `q6` plus categorical bonuses such as `dataset_from == "gt"`, rank the gallery by that score, inspect images in that order, and save or restore the same ranking through local settings and Smart Folders.

The goals are to make the derived score behave like a first-class numeric metric, fix the existing null/non-finite metric ordering bug before the feature depends on it, expose q-style numeric inputs without undoing large-table projection discipline, persist the derived definition atomically with sort/filter state, and keep invalid saved definitions visible instead of silently deleting or misapplying them.

The non-goals are multiple active derived scores in v1, a free-form formula language, derived metrics as inputs to other derived metrics, backend global derived sorting, writing scores back into source datasets, a new top-level ranking tab, a new parser/runtime dependency, and compatibility shims for old pre-release saved local settings.

Pre-approved behavior changes are: metric sorts place `null`, `NaN`, `Infinity`, and `-Infinity` after finite values for both ascending and descending order; visible metric summaries, filters, rails, and sort-value checks treat non-finite numbers as missing; the v1 derived score uses a stable opaque id under `@derived/`; the score name is a display label only; missing numeric terms support only `zero` or `invalid`; Metrics-panel ranking is disabled in similarity mode, scan-stable sort-locked mode, invalid spec state, and no-valid-score state; q-style numeric scalar columns become formula-eligible browse metrics; formula-eligible numeric columns are owned by Metrics and are not duplicated under "Other table fields"; invalid saved derived definitions are retained and shown as unavailable.

Changes requiring explicit sign-off are: backend sorted windows for global top-N over unloaded rows, a text formula parser, weighted-average or `omit` missing semantics, derived-on-derived dependency graphs, exporting derived score columns, adding CLI flags for arbitrary formula column selection, broad all-numeric metric promotion, multiple score management, and cross-dataset score preset libraries.

Deferred work is limited to backend evaluation/sorted paging, multiple saved score presets, categorical many-value weight tables, batch export, calibration plots, and richer rubric comparison views.



## Context



No repository-level `PLANS.md` was found during drafting. This plan follows the active `AGENTS.md` instructions for `/fsx/yada/dev/lenslet` and treats `docs/` as the active planning area while excluding `docs/agents_archive/` as source of truth.

The existing browse pipeline already has the right integration points. Browse items carry `metrics` and `categoricals`, the Metrics panel receives `metricKeys` and `categoricalKeys`, toolbar sorting already accepts metric sort specs, and Smart Folders store `ViewState`. The right product shape is therefore a Metrics-panel score builder whose output is injected into each item `metrics` map before filters, sort, metric-key resolution, and metric UI rendering consume the item pool.

The reviewer found one blocker that must land first. Metric sorting currently sorts ascending and reverses the entire array for descending, which moves null metric values from the end to the front. The same loose finite checks appear in metric filters, metric value collection, metric rail behavior, and metric sort-value detection. The user explicitly asked to add a sprint if this bug exists elsewhere in Lenslet, so metric value semantics are a separate stabilization sprint before derived scoring.

The current table backend also blocks the `q1` through `q6` example. Table metric exposure is name-based and only promotes metric-like names such as `score`, `quality`, `rating`, `confidence`, and `prob`. q-style columns are not projected for large Parquet browse payloads and likely remain only as inspector table fields. The plan fixes this with explicit formula-eligible numeric exposure, not by redefining all numeric scalar columns as metrics.

Commit `6c69bf0` added table source-column switching and cache invalidation. It does not directly change metric sorting, but it adds an invalidation path derived specs must tolerate. After a source-column switch, the derived definition should remain in `ViewState`, be revalidated against the new metric/categorical keys, and disable ranking if inputs are unavailable.

Scope decisions incorporated from review are: v1 supports exactly one active derived score per `ViewState`; local persistence hard-cuts to one atomic persisted `ViewState` JSON key; source q-columns promoted to metrics are shown in Metrics/inspector metrics rather than duplicated as "Other table fields"; missing categorical keys invalidate a score, while missing categorical values simply contribute no bonus; and browser acceptance must test regenerated packaged frontend assets.



## Interfaces and Dependencies



The frontend `ViewState` interface gains an optional singular `derivedMetric?: DerivedMetricSpec | null` field. A spec has `version: 1`, an opaque stable `id`, a display `name`, finite `intercept`, numeric weighted terms, and categorical additive terms. The computed key is `derivedMetricKey(spec) = @derived/<id>`. Source metric keys beginning with `@derived/` are reserved and must not be accepted as raw table metrics or v1 inputs.

The frontend needs a small shared `finiteMetricValue` helper used by sorters, filters, metric value collection, metric rail logic, metric sort-value detection, and the derived evaluator. It should return a number only for finite numeric values and `null` otherwise.

The derived evaluator is a pure frontend model helper. It receives source items, source metric keys, source categorical keys, the optional derived spec, loaded-count metadata, and returns augmented items, effective metric keys, display-name metadata, and validation/status diagnostics. It must not mutate React Query payloads or source item objects in place.

Metric display names become an explicit frontend interface, for example `MetricDisplayNames = Record<string, string>` plus a helper that falls back to the raw key. The map must be threaded to toolbar sort options, Metrics panel selectors and titles, filter chips, inspector metric labels, and metric rail labels. Do not use `metric_labels` for derived display names because that existing field represents categorical labels for coded numeric metrics.

The backend table layer needs an explicit formula-eligible numeric column helper used by Parquet browse projection and table metric extraction. It should keep existing metric-like numeric columns, add short eval fields matching `q` followed by digits, and keep exclusions for source/path/name/mime, dimensions, size, timestamps, ids, row indices, booleans, internal columns, and obvious bookkeeping counters. It should not globally redefine `is_metric_column_name`.

Browse metric keys need a storage-level path for table mode, mirroring the existing categorical storage escape hatch, so schema-backed formula inputs appear in `metric_keys` even when the loaded window has only null values.

No new runtime dependency is planned. The backend `/views` route should not need a schema change if it continues accepting arbitrary JSON view payloads, but frontend normalizers must accept and sanitize the singular `derivedMetric` field.



## Plan of Work



While implementing each sprint, update this plan continuously, especially Progress Log and Artifacts and Handoff. After each sprint is complete, add clear handoff notes describing changed files, validation evidence, and any remaining risk. For minor script-level uncertainties such as exact helper file placement, proceed according to this approved plan to maintain momentum, then ask for clarification after the sprint and apply follow-up adjustments if needed.

For every ticket with non-trivial code changes, the implementing agent must use the `better-code` skill before and during implementation. The ticket implementation must state material assumptions and ambiguous interpretations before coding, choose the smallest non-speculative approach, touch only files tied to the request, invariants, or verification, remove only unused code introduced by the change, and attach a concrete verification check to the ticket.

Delegate subagents early when identifying real codepaths or reviewing changes would reduce context load or speed execution. Let subagents continue long enough to produce useful results. If work is still in progress after 10 minutes, ask for a brief progress update plus why more time is needed. Do not terminate cleanup or review subagents early just to keep the main loop moving.

Scope budget: five sprints, each with no more than four substantive tasks. This is one sprint larger than the moderate default because the user explicitly requested a cross-Lenslet null/non-finite metric semantics pass before derived metrics ship. The preferred write scope is frontend metric/browse model code, Metrics panel components, app shell state/persistence hooks, focused table storage/projection code, and targeted tests. Do not touch generated frontend assets unless running the full frontend build for serving, and document whether `src/lenslet/frontend/` was regenerated.

Quality guardrails: no parser, no `eval` or `new Function`, no derived-on-derived in v1, no all-numeric table promotion, no source dataset writes, no broad refactors hidden inside feature work, no in-place mutation of cached browse/search payloads, and no silent empty-gallery behavior for unavailable derived filters. The debloat/removal targets are the ambiguous `missing: "omit"` policy, name-derived metric keys, duplicated metric finite checks, speculative score preset infrastructure, multiple-score UI management, and any proposed new tab.

Every ticket follows this gate routine:

1. Plan gate: restate the goal, acceptance criteria, material assumptions/ambiguities, and files to touch. If behavior would differ based on an ambiguity, stop and ask. For substantive code, invoke `better-code` and record the key invariants, smallest robust approach, and expected evidence.
2. Implement gate: implement the smallest coherent slice that satisfies the ticket. Avoid speculative features, one-off abstractions, unrelated cleanup, and broad refactors. Run the ticket's targeted verification.
3. Cleanup gate: after each complete sprint, run the code-simplifier routine below.
4. Review gate: after cleanup, run the review routine below and treat it as blocking unless the user explicitly approves a downgrade or the subagent is unavailable or fails after a reasonable wait.

### code-simplifier routine



After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan the current sprint changes. Start with non-semantic cleanup: formatting/lint autofixes, obvious dead code introduced by the sprint, small readability edits that do not change behavior, and doc/comments that reflect what is already true. Keep this conservative and do not expand into semantic refactors unless explicitly approved. Once the cleanup subagent starts, do not interrupt or repurpose it to save time. If it runs long, wait or request a progress update; only fall back to manual cleanup review if the subagent is unavailable, fails, or the user explicitly approves the downgrade.

### review routine



After each complete sprint and after the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Instruct the review subagent to be constructively adversarial: actively look for ways the change could fail, where scope or validation is weak, and what should be removed or simplified, while keeping feedback actionable and focused on shipping a robust result. Use the best available model in the environment with `reasoning_effort` set to `medium` for this review subagent; do not default to mini/fast models for review unless the user explicitly approves that downgrade. Review the post-cleanup diff, apply fixes, then rerun review when needed to confirm resolution. Manual diff review is a fallback only when the review subagent is unavailable, fails, or the user explicitly approves that downgrade.

Sprint 1, Metric Value Semantics Stabilization, makes finite metric handling consistent across Lenslet's visible metric sort/filter/summary paths. Demo outcome: a fixture with finite, null, `NaN`, `Infinity`, and `-Infinity` metric values sorts finite values correctly in both directions with invalid values last, and visible metric summaries ignore invalid numbers.

1. [x] T1.1 Add a shared `finiteMetricValue` helper and audit metric-specific source consumers. Candidate files are `frontend/src/features/browse/model/sorters.ts`, `frontend/src/features/browse/model/filters.ts`, `frontend/src/features/metrics/model/metricValues.ts`, `frontend/src/app/model/appShellSelectors.ts`, `frontend/src/features/browse/components/MetricScrollbar.tsx`, and inspector metric display helpers. Validation: targeted frontend tests prove `NaN` and infinities are missing in every touched metric path, and `rg` is used only to confirm no remaining metric-specific `Number.isNaN`-only checks in relevant metric files.
2. [x] T1.2 Make metric sorting direction-aware and leave built-in sort behavior alone unless explicitly approved. Use finite validity first, metric value second, and name tie-break last, with invalid values last for both directions. Validation: add tests for `applySort` or `sortByMetric` covering asc and desc with finite, null, `NaN`, `Infinity`, and `-Infinity` values.
3. [x] T1.3 Fix metric range filters, histograms, selected metric summaries, metric sort activation, and the metric scrollbar to use the same finite semantics. Validation: update existing filters, `metricValues`, `appShellSelectors`, and `MetricScrollbar` tests or add focused tests where coverage is missing.
4. [x] T1.4 Add metric-specific finite coercion on backend metric output paths rather than changing unrelated numeric coercion broadly. Candidate files are `src/lenslet/storage/table/schema.py`, `src/lenslet/storage/table/index.py`, `src/lenslet/web/cache/browse_snapshot.py`, and `src/lenslet/web/sync/labels.py`. Validation: focused pytest coverage proves non-finite metric values are omitted from browse/cache/sync metric payloads and do not serialize as `NaN` or `Infinity`.

Sprint 2, Formula-Eligible Table Inputs, makes q-style numeric table columns available to the score builder without undoing large-table projection discipline. Demo outcome: a Parquet fixture with `q1`, `q2`, `q3`, `dataset_from`, and an image source opens with `q1`/`q2`/`q3` in `metric_keys` and `dataset_from` in `categorical_keys`.

1. T2.1 Add formula-eligible numeric column selection beside, not inside, `is_metric_column_name`. Include existing metric-like numeric columns and short eval fields matching `q` followed by digits; exclude ids, row indices, source/path/name/mime, dimensions, size, timestamps, booleans, internal columns, and obvious counters/bookkeeping fields. Validation: unit tests cover included `q1`/`q2`/`q10` and excluded id/width/height/size/timestamp/boolean/path-like fields.
2. T2.2 Use the helper in Parquet browse projection and table metric extraction without projecting arbitrary numeric schemas. Promoted formula-eligible numeric columns are owned by Metrics, so they should appear in item metrics and inspector Metrics, not duplicated under "Other table fields." Validation: table launch/index/display tests prove q-style columns are present as browse metrics and absent from table fields when their value is metric-owned.
3. T2.3 Add storage-level `metric_keys()` support for table mode and make `src/lenslet/web/browse.py` prefer it when available, mirroring categorical key behavior. This is a hard acceptance criterion for Sprint 2 because null-only windows otherwise create false missing-input errors. Validation: route/storage tests prove schema-backed metric keys appear even if the loaded window has only null values for a formula input.
4. T2.4 Verify the recent source-column switching path preserves projection and invalidation behavior. Validation: run `tests/web/routes/test_table_source_settings.py` plus a focused test where switching source columns keeps q-style `metric_keys` when the table schema still supports them.

Sprint 3, Derived Metric Model and Evaluation, adds the pure model layer and wires it into the browse pipeline before filters and sorting. Demo outcome: one derived spec computes a score over loaded items, exposes `@derived/<id>` as a metric key with a display name, and can drive existing metric sort without mutating source payloads.

1. T3.1 Add `DerivedMetricSpec`, `derivedMetricKey`, and `normalizeViewState` helpers to frontend model code. Use `version: 1`, stable id, display name, finite intercept/weights, numeric missing policy `zero` or `invalid`, and categorical exact-match additive terms. Reject derived metric keys as inputs. Validation: model tests cover normalization, stable key generation, missing-policy rejection, non-finite weights, and derived-as-input rejection.
2. T3.2 Add a pure evaluator for the singular `ViewState.derivedMetric`. It returns augmented items, the effective derived metric key, display names, valid/invalid counts, missing-input diagnostics, and partial-load warning metadata. Clone only changed item/metrics objects and return original item arrays when there is no valid derived spec. Validation: tests cover weighted numeric terms, categorical bonuses/penalties, missing categorical key versus absent categorical value, no mutation, all-invalid scores, and loaded-window metadata.
3. T3.3 Wire evaluation into `useAppDataScope` after pool items/local star overrides and source key resolution, but before effective `metricKeys`, `applyFilters`, `applySort`, metric sort-value checks, metric rail, and Metrics panel data. Validation: hook/model tests or focused component tests prove a saved sort key `@derived/<id>` is not reset before the derived key is appended.
4. T3.4 Update AppShell sort and selected-metric validation. Missing raw metric sorts may keep the current reset behavior, but unavailable `@derived/...` sorts must be retained with diagnostics so invalid saved definitions remain visible. Validation: tests cover rename preserving sort by stable id, missing input retaining unavailable derived sort, and selectedMetric following a valid derived score.

Sprint 4, Atomic Persistence and Invalid-State UX, stores the derived definition with the view and prevents silent empty-gallery failures. Demo outcome: local settings and Smart Folders restore the derived spec atomically with sort/filter state, and unavailable derived sorts or filters show a visible warning instead of silently destroying the user's view.

1. T4.1 Hard-cut local settings to one persisted `ViewState` JSON key for filters, sort, selectedMetric, and derivedMetric. Stop relying on separate `sortSpec`, `filterAst`, and `selectedMetric` keys for restored view state; no compatibility migration is required for this pre-release alpha. Validation: settings persistence tests prove a derived metric sort and its spec restore together from a single key.
2. T4.2 Preserve `derivedMetric` through Smart Folder save, export, activation, and stale-view detection. Normalize saved view state on activation and keep invalid definitions rather than deleting them. Validation: Smart Folder model/hook tests cover roundtrip, invalid spec retention, and active-view staleness when a derived spec changes.
3. T4.3 Add unavailable-derived warnings for active sorts and metricRange filters referencing invalid or missing derived keys. Avoid silently filtering every item without explanation; if a derived filter is unavailable, show a blocking warning or disabled filter chip state rather than a mysterious zero-result gallery. Validation: filter-chip/status tests cover unavailable derived filters and expected warning text.
4. T4.4 Validate source-column switching and folder/search changes against saved derived specs. Validation: source-switch tests or browser workflow confirm definitions remain in `ViewState`, ranking is disabled when inputs disappear, and ranking re-enables if the next scope exposes the inputs again.

Sprint 5, Metrics Panel Builder and Browser Acceptance, ships the user-facing workflow in the existing Metrics panel. Demo outcome: the user creates `new_score` from `q1`/`q2`/`q3` plus `dataset_from == "gt"`, clicks Rank by score, sees the gallery ordered by that score, reloads, and restores the same ranking from a Smart Folder.

1. T5.1 Add a Derived Score card to `MetricsPanel` that renders even when there are no current metrics or categoricals. Use draft editing for one score, score name, intercept, numeric term rows, categorical bonus rows, formula preview, valid/invalid count, and clear disabled states. Validation: component tests cover empty-input state, draft apply, formula preview, missing fields, and valid/invalid counts.
2. T5.2 Add metric display-name plumbing via a `metricDisplayNames` map/helper, not ad hoc string replacement. Apply it to toolbar sort options, Metrics panel selectors and titles, filter chips, inspector metric labels, and metric rail labels. Validation: component tests prove raw `@derived` ids are not visible in the primary UI surfaces.
3. T5.3 Implement Rank by score behavior. The action applies the current draft/spec, sets sort to the derived metric descending, sets selectedMetric to the derived key, and is disabled in similarity mode, scan-stable/indexing sort-locked mode, invalid spec state, and no-valid-score state. Validation: component or app-shell tests cover each disabled reason and the successful sort/selectedMetric update.
4. T5.4 Add the representative browser acceptance path. Build a small table-backed fixture with `q1` through `q6`, `dataset_from`, expected scores, and enough rows to verify ordering; include a second fixture or generated page count to verify partial-load warning when loaded items are fewer than `total_items`. Validation: build and copy the frontend bundle before running browser acceptance so packaged assets are current.



## Validation and Acceptance



Primary acceptance checks exercise the user's real workflow rather than only isolated helpers.

1. Primary: run focused table backend tests.

        pytest tests/storage/table/test_table_index_pipeline.py tests/storage/table/test_parquet_ingestion.py tests/web/routes/test_table_source_settings.py -q

   Expected outcome: q-style formula inputs are projected and exposed, `metric_keys()` can come from table storage even when values are null in the loaded window, metric-owned q columns are not duplicated under "Other table fields", source-column switching does not regress cache invalidation or metric key exposure, and non-finite metric values are omitted.

2. Primary: run focused frontend model/component tests.

        cd frontend && npm test -- --run src/features/browse/model src/features/metrics src/app

   Expected outcome: metric null/non-finite semantics, derived evaluator behavior, atomic view persistence, Smart Folder restore, UI disabled states, and display names pass in fast tests.

3. Primary: build packaged frontend assets before browser acceptance.

        npm --prefix frontend run build
        rsync -a --delete frontend/dist/ src/lenslet/frontend/

   Expected outcome: `src/lenslet/frontend/` contains the current UI bundle. The handoff must state that packaged assets were regenerated.

4. Primary: run the browser acceptance suite after adding a derived-score scenario.

        python -m scripts.browser.gui_smoke.acceptance

   Expected outcome: a table-backed fixture opens, `q1`/`q2`/`q3` appear as score inputs, the user flow creates `new_score` with a categorical `dataset_from == "gt"` bonus, Rank by score orders the first visible cards by expected descending score, reload/Smart Folder restore keeps the derived ranking, invalid source changes show an unavailable state, and partial loaded ranking displays an explicit loaded-window warning.

5. Primary: run repository lint after feature completion.

        python scripts/lint_repo.py

   Expected outcome: ruff and file-size guardrails pass.

Secondary checks are fast proxies used inside sprints.

1. Secondary Sprint 1: frontend tests for sorters, filters, `metricValues`, `appShellSelectors`, and `MetricScrollbar` pass with finite/null/`NaN`/`Infinity` cases, and backend metric coercion tests prove non-finite metric output is omitted.
2. Secondary Sprint 2: pytest coverage for formula-eligible table columns passes and confirms no arbitrary all-numeric projection.
3. Secondary Sprint 3: pure evaluator tests prove no mutation, stable ids, categorical exact matches, missing policies, missing-key diagnostics, and loaded-window warnings.
4. Secondary Sprint 4: settings and Smart Folder tests prove the singular derived spec persists atomically with sort/filter state and invalid definitions remain visible.
5. Secondary Sprint 5: MetricsPanel and Toolbar tests prove score labels replace raw `@derived` ids and Rank by score respects disabled modes.

A sprint cannot be marked complete if its demo outcome fails, even when isolated unit tests pass.



## Risks and Recovery



The biggest hidden dependency is table projection. If formula input exposure is too broad, large Parquet launches can regress the recent preload fix. Recovery is to keep Sprint 2 limited to existing metric-like columns plus q-number eval fields, and to defer arbitrary numeric input selection until explicitly approved.

The second risk is cached item mutation. If derived metrics are written into React Query payload objects, deleting or editing a spec can leave stale `@derived` values in search/folder caches. Recovery is to make the evaluator pure, add no-mutation tests, and revert only the evaluator wiring if stale cache behavior appears.

The third risk is saved invalid state. A Smart Folder can reference a derived score whose inputs no longer exist after folder changes or source-column switching. Recovery is to retain the spec, mark it unavailable, disable ranking/actions, and show diagnostics rather than deleting the spec or silently resetting derived sort/filter state.

The fourth risk is global-order confusion on recursive tables. Client-side derived sort is correct only for loaded items. Recovery is to show loaded-window warnings whenever a derived sort is active and `data.items.length` is less than `total_items`. Backend global sorted windows remain deferred and require sign-off.

The fifth risk is local settings churn from the atomic persistence hard cut. Because Lenslet is pre-release alpha, no compatibility migration is required. Recovery is to normalize missing or invalid persisted `ViewState` to the default browse view and continue.

Rollback is sprint-scoped. Sprint 1 can ship independently as a metric correctness fix. Sprint 2 can be reverted without losing frontend derived code if projection risk appears. Sprints 3 and 4 can remain hidden without Sprint 5 UI wiring. No sprint writes to source datasets, and Smart Folder/view changes are JSON state only.



## Progress Log



- [x] 2026-06-08 08:50 UTC: Read `AGENTS.md` instructions, the original derived metric design note, the reviewer note, `plan-writer` guidance, and `better-code` guidance.
- [x] 2026-06-08 08:50 UTC: Verified the reviewer's null-descending-sort finding in `frontend/src/features/browse/model/sorters.ts` and `frontend/src/features/browse/model/apply.ts`.
- [x] 2026-06-08 08:50 UTC: Found related metric finite-value paths in filters, metric value collection, app shell selectors, metric rail, and backend metric normalization.
- [x] 2026-06-08 08:50 UTC: Incorporated the user's request to add a dedicated cross-Lenslet null/non-finite metric semantics sprint.
- [x] 2026-06-08 08:50 UTC: Ran the required adversarial subagent review and incorporated its changes: singular v1 score, atomic `ViewState` persistence, retained unavailable derived sorts, surgical metric sort fix, metric-specific backend finite coercion, q-column ownership, display-name interface, categorical key/value distinction, and packaged-asset acceptance prerequisite.
- [x] 2026-06-08 08:50 UTC: Wrote this plan document to `docs/20260608_derived_metric_ranking_plan.md`.
- [x] 2026-06-08 10:02 UTC: Completed Sprint 1 tasks `T1.1` through `T1.4`. Added shared finite metric helpers, direction-aware metric sorting, finite metric semantics for filters/summaries/rail/inspector, and backend finite metric coercion for table, browse, recursive cache, sidecar, and sync paths.
- [x] 2026-06-08 10:02 UTC: Ran Sprint 1 cleanup and review gates. Cleanup subagent `019ea69c-df3d-7da3-a05f-e34be939d2fd` found Tier 1 cleanup only; review subagent `019ea6a1-8658-75a0-82da-f4a340627d27` found two sync/key-derivation issues, both fixed; follow-up review subagent `019ea6aa-d709-70a1-a077-2bd00aaa3d39` found no remaining actionable issues.
- [x] 2026-06-08 10:02 UTC: Validated Sprint 1 with `npm --prefix frontend test -- --run src/features/browse/model src/features/metrics src/app`, `pytest tests/storage/table/test_table_index_pipeline.py tests/storage/table/test_parquet_ingestion.py tests/web/routes/test_table_source_settings.py tests/web/cache/test_browse_cache.py tests/web/routes/test_direct_route_helpers.py -q`, source `rg` checks for metric `Number.isNaN`-only handling, `git diff --check`, and `python scripts/lint_repo.py`.



## Artifacts and Handoff



Input docs reviewed:

        docs/20260608_derived_metric_ranking.md
        docs/20260608_derived_metric_ranking_review.md

Required subagent review was completed by agent `019ea66f-88c1-7cd2-b8ef-40481fd63a67`. Its main corrections were to reduce v1 to one active score, make persistence truly atomic, retain unavailable derived sorts in AppShell, keep built-in sort behavior unchanged, target metric-specific backend finite coercion, clarify q-column ownership, add a real display-name interface, distinguish missing categorical keys from missing categorical values, and regenerate packaged frontend assets before browser acceptance.

Key local discoveries:

        frontend/src/features/browse/model/apply.ts reverses descending sorts after ascending comparison, which moves null metric values to the front.
        frontend/src/features/browse/model/sorters.ts treats only null as missing and does not reject NaN or infinities.
        frontend/src/features/browse/model/filters.ts, frontend/src/features/metrics/model/metricValues.ts, frontend/src/app/model/appShellSelectors.ts, and frontend/src/features/browse/components/MetricScrollbar.tsx use inconsistent NaN/non-finite checks.
        src/lenslet/storage/table/launch.py projects only is_metric_column_name numeric fields, so q1/q2/q3 are not available to browse scoring today.
        src/lenslet/storage/table/index.py and src/lenslet/storage/table/storage.py hide metric-owned columns from display fields, so q-style formula inputs should follow the same ownership rule once promoted.
        src/lenslet/web/browse.py has a storage-level categorical key path but no equivalent metric key path.
        src/lenslet/storage/table/schema.py and src/lenslet/web/cache/browse_snapshot.py can preserve non-finite metric values unless metric-specific finite coercion is added.

Sprint 1 handoff:

        Added `frontend/src/lib/metrics.ts` and `src/lenslet/metrics.py` for shared finite metric coercion.
        Updated frontend sort/filter/summary/rail/inspector paths so `null`, `NaN`, `Infinity`, and `-Infinity` are missing values.
        Updated backend table, browse, recursive cache, sidecar, and sync metric emitters so non-finite metric keys are omitted and explicit empty metric maps still clear stale sync state.
        Packaged frontend assets were not regenerated in Sprint 1 because no served bundle change was required for this correctness slice.

Next operator should start with Sprint 2, Formula-Eligible Table Inputs. Do not begin derived metric model/UI work until q-style projection and storage-level `metric_keys()` support are covered by tests.

Revision note: this new plan integrates the reviewer's comments into the previous design by adding a prerequisite metric semantics sprint, replacing plural derived metrics with one v1 derived score, hard-cutting local persistence to atomic `ViewState`, retaining unavailable derived state instead of resetting it, clarifying q-column ownership, and making display names plus browser acceptance prerequisites explicit.
