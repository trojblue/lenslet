# UX Improvement Plan Review

Review stance: Review this sprint/task plan with a constructively adversarial stance: actively try to find missing work, removable work, oversized tasks, under-engineered shortcuts, unclear assumptions, non-surgical edits, speculative abstractions, validation gaps, hidden dependencies, and scope-creep risks. Suggest concise, actionable improvements and explicit de-scoping opportunities while preserving robustness.

## Findings

### High: Sprint 1 surfaces table trust issues but does not fix the riskiest root cause

Affected sections/tasks: Sprint 1, especially S1-T1; Risks and Recovery; Validation and Acceptance.

The backend reports identify default Parquet dimension caching/mutation as a high-severity trust issue: local Parquet launches can rewrite source tables by default. The plan mentions "dimension coverage" and "cache/write policy" in status, but that can become a cosmetic disclosure while preserving surprising writes. This conflicts with the plan's trust goal and the repo guidance that source datasets stay read-only.

Suggested edit: make "source Parquet immutable by default" an explicit Sprint 1 task or split S1-T1 into two tasks: first change the dimension persistence contract to workspace/cache-backed by default, then expose the launch summary. If in-place mutation remains, require an explicit opt-in flag and test it separately.

Validation gap: add a focused pytest that launches a Parquet with missing dimensions and asserts the source file hash/mtime is unchanged while browse, metadata, and thumbnails still see cached dimensions. Keep `--no-write`, `--no-cache-dimensions`, and explicit mutation flag tests.

### High: The plan is too broad to be an executable sprint plan without a first-cut release boundary

Affected sections/tasks: Scope Budget and Guardrails; all six sprints.

Six sprints and 28 tickets cover backend contracts, media loading, URL semantics, table query optimization, recursive API policy, request queues, accessibility primitives, ranking, and workspace settings. Many are valid findings, but as one implementation plan this is closer to a roadmap than a controlled sprint plan. It increases the chance that implementers start broad infrastructure work before the trust/continuity failures are closed.

Suggested edit: define a Phase 1 release boundary of two or three sprints: Sprint 1 trust/status/failure root fixes, Sprint 2 browse/media continuity, and the bounded subset of Sprint 3 that removes misleading metric truth. Move Sprint 4-6 into "approved backlog candidates" unless the user explicitly approves the full UX roadmap. Keep the plan's gate routine, but avoid running heavyweight cleanup/review subagents after every tiny ticket if the implementation environment cannot actually support them.

De-scope opportunity: defer ranking URL substate, smart-folder similarity URL state, broad keyboard parity for manipulation controls, and folder-path native listing until the primary trust and context-restoration paths pass browser validation.

### High: Backend media and remote-source behavior needs a clearer policy, not just frontend failure states

Affected sections/tasks: S1-T2, S5-T5, Risks and Recovery.

The plan correctly asks for visible media failures, but the backend reports also flag HTTP originals being fully buffered through the backend and direct browser HTTP originals being unreliable for CORS/auth/hotlink cases. S1-T2 may produce good error UI while leaving the underlying original-loading strategy inconsistent and memory-heavy.

Suggested edit: add a narrow media policy task before or inside S1-T2: direct URL handoff only when safe, streaming backend proxy when proxying is required, and explicit fallback behavior when direct image display fails. Avoid a general download manager.

Validation gap: include a fake large HTTP original test proving proxy mode streams instead of buffering all bytes, plus a browser test where direct image display fails but backend fetch succeeds.

### Medium-High: Navigation scope boundaries are underrepresented

Affected sections/tasks: Sprint 2; Sprint 4.

The navigation report calls out a high-severity issue where folder navigation can leave stale selection/inspector state from the previous scope. The plan emphasizes restore continuity, compare URLs, and shared state, but does not explicitly require clearing or revalidating selection on scope changes. This is a smaller and more surgical trust fix than much of Sprint 4.

Suggested edit: add a Sprint 2 task: "Treat folder scope changes as a selection boundary; clear selection/inspector unless entering from a viewer hash that explicitly selects a path." This should precede compare URL work.

Validation gap: browser or component test selecting an item in folder A, opening folder B, and asserting inspector path, selected paths, compare eligibility, and sidecar edit target are cleared.

### Medium-High: S3/S4 metric and URL work needs stricter sequencing to avoid parallel state models

Affected sections/tasks: S3-T1 through S3-T5; S4-T2 through S4-T5.

The plan asks for query-shaped facets, backend-owned derived metrics, split field capabilities, bounded metric rail, shareable derived state, unsupported shared intent, and smart-folder/similarity URL state. These are related, but if implemented independently they can create multiple "canonical" query identities and URL encodings.

Suggested edit: add one explicit prerequisite contract: a normalized browse query identity used by `/folders/query`, query-shaped facets, derived metric status, metric summaries, and URL round-trips. Then implement only `q`, filters, sort, random seed, and unsupported metric intent first. Defer smart-folder and similarity URL state until the base query identity is stable.

De-scope opportunity: move S4-T5 out of this plan. It is useful but not necessary to fix the reported trust failures, and URL-restored similarity can trigger embedding work with non-trivial cancellation and error semantics.

### Medium: Performance tasks mix "measure first" work with implementation commitments

Affected sections/tasks: Sprint 5; Validation and Acceptance.

S5-T2, S5-T4, S5-T5, and the report findings repeatedly say measurement is required before algorithmic or rendering changes. The plan currently commits to fast paths, folder-path capabilities, and cache/queue budgets in the same sprint. That can lead to speculative optimization and broad API changes without proof.

Suggested edit: split Sprint 5 into S5A measurement and policy enforcement, then S5B targeted fixes only where measurements fail. S5A should include payload bytes, query p95, first grid, first thumbnail, queue peaks, frame gaps, and RSS for 40k/100k scenarios. Only after that should row-native fast paths, memoization, folder-path APIs, or queue policies be selected.

De-scope opportunity: remove render memoization and bundle-splitting work from this plan unless profiler or bundle evidence shows they are current blockers.

### Medium: Accessibility primitive work risks becoming a mini design-system rewrite

Affected sections/tasks: Sprint 6.

The accessibility reports recommend small shared primitives, but Sprint 6 covers menus, popovers, overlays, grid/tree focus, compare divider, metric rail, ranking drag-sort, fullscreen focus, and visual polish. This can sprawl across many components and introduce regressions in virtualized focus.

Suggested edit: limit Sprint 6 to one primitive adoption slice: `AppMenu/AppPopover` plus one modal focus policy applied to the highest-risk overlays. Treat grid focus ownership and ranking drag keyboard semantics as follow-up tickets after the primitive proves out.

Validation gap: add browser tests for actual Tab/Arrow/Escape/focus-return behavior, not just ARIA attributes, and run them against viewer, compare, similarity, ranking fullscreen, and one context menu before expanding.

### Low-Medium: Some quick wins from the reports are missing or delayed

Affected sections/tasks: Sprint 1; Sprint 5.

The reports include small, high-leverage cleanup candidates that are not clearly represented: reword confusing `--no-write`/dimension-cache messaging, bound or retire legacy `/search`, and precompute table display-field extraction helpers for inspector selection. These are smaller than several planned feature tasks.

Suggested edit: add them to a "small cleanup if touched" list, not as mandatory sprint blockers. They are good de-scoped replacements if Sprint 4-6 are trimmed.

## Validation Gaps To Close Before Use

- Add source immutability acceptance for Parquet dimension handling; status-only validation is not enough.
- Add stale selection/inspector scope-change validation.
- Add media streaming/direct-fallback validation for HTTP originals, not only thumbnail/viewer error rendering.
- Define large-table thresholds for "bounded": page payload bytes, query p95, first thumbnail, request queue peak, and RSS.
- Add URL round-trip tests that distinguish shareable analysis state from workspace-scoped local preferences.
- Require browser keyboard tests that exercise behavior paths, not only roles and labels.

## Overall Recommendation

Revise before use. The plan synthesizes the agent reports well and has the right north star, but it is too large for a single executable plan and softens several high-severity backend findings into status/UI work. Make source immutability, media policy, stale selection clearing, and canonical query identity explicit; trim or defer speculative URL, accessibility, and performance work until the core trust and continuity path is validated.
