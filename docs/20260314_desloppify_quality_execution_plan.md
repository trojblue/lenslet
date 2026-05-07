# Desloppify Quality Execution Plan


This repository does not currently have a `PLANS.md`-style execution file, so this document is the authoritative plan for the current code-health pass.


## Outcome + Scope Lock


After this pass, Lenslet should present one coherent server entry surface, one honest storage contract family, and one consistent read-only mutation boundary. The code paths that `desloppify` is repeatedly flagging should be simplified at their roots rather than patched around, and the review findings should map cleanly to code changes, tests, and docs.

Goals:

- Raise `desloppify` strict score materially above the current `74.9/100` by removing root-cause clusters rather than chasing isolated nits.
- Collapse the split server ownership between `src/lenslet/server.py`, `src/lenslet/server_factory.py`, and `src/lenslet/server_routes_common.py`.
- Make the storage layer honest about read-only behavior, browse contracts, and index/item typing.
- Remove wrapper-shell code and hidden private protocols in the table/dataset storage stack.
- Update docs and tests so the runtime structure and write-permission semantics match the implementation.

Non-goals:

- Do not design or ship a full authentication system in this pass.
- Do not redesign ranking UX or broad frontend interaction flows.
- Do not introduce backwards-compatibility scaffolding for old internal APIs; this repo is alpha and can take hard cutovers.
- Do not broaden scope into unrelated cleanup unless the change directly improves the current review clusters or unblocks validation.

Approval matrix:

- Pre-approved: internal refactors, file moves/extractions, deletion of duplicate helpers, tightening internal protocols, removal of silent no-op APIs, test updates, and doc updates.
- Pre-approved: enforcing `workspace.can_write` consistently on mutating routes where the current behavior is internally contradictory.
- Requires sign-off: adding mandatory authentication or auth configuration, changing externally documented CLI behavior, or changing persisted workspace file formats.

Deferred / out of scope for this pass:

- The review finding `missing_server_auth_boundary` will be documented and reduced in blast radius where possible, but a real auth feature requires explicit product direction.
- Low-signal mechanical noise outside the server/storage/api/doc clusters stays deferred unless it blocks the score or the sprint acceptance gates.


## Context


The current `desloppify` run has completed its first full scan and holistic review import. The codebase moved from `strict 17.7/100` to `strict 74.9/100`, with `53` review work items now open. The highest-signal repeated findings are not random; they converge on a few structural problems:

- The public server surface is split across `src/lenslet/server.py`, `src/lenslet/server_factory.py`, and duplicated comparison-export helpers in `src/lenslet/server_routes_common.py`.
- The storage layer presents a hidden protocol through `src/lenslet/storage/table_facade.py`, wide wrapper shells in `src/lenslet/storage/table.py` and `src/lenslet/storage/dataset.py`, and a misleading writable `Storage` protocol in `src/lenslet/storage/base.py`.
- Route-level write semantics are inconsistent: some paths respect `workspace.can_write`, while sibling mutation routes still succeed in read-only contexts.
- Programmatic launch and factory entrypoints duplicate option plumbing and hide mode-specific semantics behind broad signatures.
- `frontend/update_header_css.py` emits repeated syntax warnings during every scan, creating avoidable analysis noise.

The current review output shows the most leverage in the following issue families:

- `review::.::holistic::cross_module_architecture::server_facade_still_runtime_hub`
- `review::.::holistic::high_level_elegance::server_facade_still_owns_duplicate_export_logic`
- `review::.::holistic::abstraction_fitness::storage_facade_implicit_protocol`
- `review::.::holistic::abstraction_fitness::table_storage_wrapper_shell`
- `review::.::holistic::api_surface_coherence::localstorage_write_contract_is_silent_noop`
- `review::.::holistic::authorization_consistency::can_write_is_not_a_route_permission_boundary`

The repo has no standing plan file to align against. This plan therefore sets scope, validation, and handoff rules for the remainder of the `desloppify` loop.


## Interfaces and Dependencies


This pass changes internal interfaces and one public import surface.

- `src/lenslet/server.py` remains the public import surface, but should become a passive facade that re-exports stable entrypoints and monkeypatch seams without owning route logic.
- Comparison-export helpers and constants should move into a single internal module so route wiring and export logic stop diverging.
- `src/lenslet/storage/base.py` should stop advertising a writable protocol to read-only backends. The code should distinguish low-level byte access from browse-oriented storage behavior.
- Storage backends should converge on one explicit `get_index()` contract. Shared browse item/index types should only be introduced if they directly replace the hidden protocol instead of creating a second migration layer.
- Route modules that mutate state should share the same read-only gating policy instead of depending on backend quirks or `Workspace` fallbacks.


## Plan of Work


The plan is intentionally narrow: fix the repeated root causes first, then rescan and let `desloppify` surface what remains. Every sprint must leave the repo runnable, testable, and ready for a fresh scan.

Scope budget:

- One preflight gate plus four sprints.
- Twelve execution tasks total, not counting the required `initialization_coupling` re-review.
- Primary file focus: `src/lenslet/server*.py`, `src/lenslet/api.py`, `src/lenslet/storage/*.py`, `src/lenslet/workspace.py`, `tests/`, `README.md`, `frontend/README.md`, and `frontend/update_header_css.py`.
- Debloat target: end the pass with fewer duplicate export helpers, fewer method trampolines, fewer hidden underscore-protocol call sites, and no silent write no-op API.

Guardrails:

- Prefer extraction-plus-deletion over extraction-plus-wrapper.
- Do not add a new abstraction unless it deletes more incidental complexity than it introduces.
- Keep each sprint mergeable on its own with targeted validation before moving on.
- Treat `desloppify` state as part of the implementation, not post-hoc bookkeeping. At the end of each sprint, check `desloppify show review --status open`, resolve the review IDs actually closed by the sprint with `desloppify plan resolve "<id>" --note "<what changed>" --confirm`, rerun the sprint-level validation, and record the resulting score change.
- While implementing each sprint, update this plan continuously, especially the Progress Log and any sections affected by discoveries or scope changes. After each sprint is complete, add explicit handoff notes here before proceeding.
- For minor script-level uncertainties such as exact helper placement, proceed with the approved structure to maintain momentum. After the sprint, ask for clarification only if the remaining uncertainty changes behavior or validation.
- Delegate subagents early when that reduces context load or accelerates file-path discovery. Let those subagents run long enough to produce useful output; if one is still active after ten minutes, request a brief progress update and the reason it needs more time.

Sprint plan:

0. Sprint 0 is a blocking preflight gate.

   R0. Re-run the `initialization_coupling` review dimension with `desloppify review --prepare --force-review-rerun --dimensions initialization_coupling` followed by the matching `review --run-batches --runner codex --parallel --scan-after-import` flow.

   R1. Confirm the rerun imports cleanly, record any changed assessment or issue IDs in the Progress Log, and do not start code edits until the subjective baseline is trustworthy again.

   Demo outcome: the plan starts from a clean review baseline rather than a knowingly suspect dimension score.

1. Sprint 1 closes the server-surface split.

   Q1. Extract the comparison-export constants, runtime object, and helper functions into a single new internal module, likely `src/lenslet/server_compare_export.py`.

   Q2. Make `src/lenslet/server.py` a pure facade again and remove the runtime back-edge from `src/lenslet/server_factory.py` into `lenslet.server`.

   Q3. Update import-contract tests and runtime docs so the new ownership model is explicit and stable.

   Demo outcome: one authoritative owner for export logic, one passive `lenslet.server` surface, no `server_factory -> server` runtime hop.

2. Sprint 2 makes storage and mutation contracts honest.

   Q4. Replace the current writable `Storage` protocol with read-only and browse-specific contracts that reflect real backend behavior.

   Q5. Converge `get_index()` behavior and missing-path semantics across memory, table, and dataset storage without introducing a second migration layer.

   Q6. Enforce one consistent read-only write boundary for `/item`, `/views`, refresh, ranking-save or equivalent mutating flows, and the collaboration paths currently covered by `tests/test_collaboration_sync.py`.

   Demo outcome: read-only apps fail writes consistently, storage backends expose one discoverable contract, and the silent write no-op is gone.

3. Sprint 3 deletes the hidden storage protocol and wrapper-shell code.

   Q7. Collapse `src/lenslet/storage/table_facade.py` and related `Any`-based hidden protocol into explicit typed behavior owned by the storage implementations.

   Q8. Remove or inline the dense trampoline blocks in `src/lenslet/storage/table.py` and `src/lenslet/storage/dataset.py`, keeping only wrappers that bind real state or policy.

   Q9. Introduce shared browse item/index types only if they are the direct replacement for the deleted hidden protocol and reduce backend branching immediately.

   Demo outcome: the storage stack reads as explicit code instead of an `Any`-based facade plus method trampolines.

4. Sprint 4 simplifies launch APIs, docs, tests, and scan signal.

   Q10. Simplify `src/lenslet/server_factory.py` and `src/lenslet/api.py` so table launch, dataset launch, and app construction stop repeating the same option plumbing through wide signatures.

   Q11. Add targeted regression coverage for server import/export behavior, read-only mutation rejection, storage index behavior, and programmatic launch paths, then update only the README sections affected by server surface, launch APIs, and write-behavior semantics.

   Q12. Fix analysis-noise sources such as `frontend/update_header_css.py` warnings, remove dead dependency/config noise where justified, rerun `desloppify`, and close or explicitly defer residual high-impact findings.

   Demo outcome: programmatic entrypoints are smaller and clearer, the docs match the changed runtime surface, and the scan focuses on remaining real issues.

Gate routine for every task Q1-Q12:

0. Plan gate (fast): restate the ticket goal, acceptance signal, and touched files in one short note before editing.

1. Implement gate (correctness-first): implement the smallest coherent slice that closes the ticket and run its minimal validation immediately.

2. Cleanup gate (reduce noise before review): after each completed sprint, run a conservative cleanup pass before requesting review.

### code-simplifier routine

After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan the current sprint diff. Limit this pass to formatting and lint autofixes, obvious dead-code removal, small readability improvements, and doc/comment updates that reflect already-true behavior. Do not let this pass grow into new semantic refactors without explicit approval.

3. Review gate (review the ship diff): after the cleanup pass, request a fresh code review against the post-cleanup diff and resolve findings before moving on.

### review routine

After each complete sprint and after the cleanup subagent finishes, spawn a fresh agent and request a review using the `code-review` skill. Review the post-cleanup diff, apply fixes, and rerun review when needed until the sprint no longer carries unresolved high-signal defects.

Queue-sync routine after every sprint:

1. Run `conda run -n conda313 desloppify show review --status open` and map the sprint diff to the specific open review IDs it closed.

2. Resolve only those closed IDs with `conda run -n conda313 desloppify plan resolve "<id>" --note "<what changed>" --confirm`.

3. Run the sprint validation commands again, then rerun `conda run -n conda313 desloppify scan --path .` at the end of the sprint to refresh the score and queue.

4. Record the before/after strict score and any remaining blocked IDs in the Progress Log before proceeding.


## Validation and Acceptance


Primary acceptance means behavior in the real runtime path, not only local unit proxies. Secondary checks are fast gates that catch regressions earlier but do not replace the primary gates.

Sprint validation:

1. Sprint 1 primary checks:

   `pytest tests/test_import_contract.py tests/test_compare_export_endpoint.py`

   A direct import sanity check such as `python - <<'PY'\nfrom lenslet import server\nprint(callable(server.create_app))\nPY`

   Expected outcome: import contract remains stable, export route still works, and there is no runtime import back-edge from factory to facade.

   Sprint 1 secondary checks:

   `python scripts/lint_repo.py`

   `python - <<'PY'\nfrom pathlib import Path\ntext = Path('src/lenslet/server_factory.py').read_text()\nprint('from .server import' not in text and 'import .server' not in text)\nPY`

   A targeted assertion that both route wiring and `lenslet.server` reexports import comparison-export behavior from the same new module.

2. Sprint 2 primary checks:

   Targeted pytest coverage for read-only mutation behavior, including `/item`, `/views`, refresh, ranking-save or equivalent mutating routes, collaboration-sync write paths, and storage-specific index lookups.

   Expected outcome: read-only apps reject mutations consistently and storage backends expose one consistent missing-path contract.

   Sprint 2 secondary checks:

   `python scripts/lint_repo.py`

   Targeted module tests under `tests/test_refresh.py`, `tests/test_programmatic_api.py`, and any new storage contract tests added in the sprint.

3. Sprint 3 primary checks:

   Programmatic launch tests for dataset and table mode plus targeted route smoke tests for the storage backends whose hidden protocol was collapsed in the sprint.

   Expected outcome: hidden `Any`-based protocol code is gone or drastically reduced, wrappers are gone or reduced to stateful policy, and the storage backends still serve the same browse flows.

   Sprint 3 secondary checks:

   `python scripts/lint_repo.py`

   `pytest` for the touched server/storage/api modules.

4. Sprint 4 primary checks:

   `pytest`

   `conda run -n conda313 desloppify scan --path .`

   Expected outcome: strict score improves from `74.9/100`, the updated review IDs are actually resolved in `desloppify`, no targeted behavior regresses, and the rescan reflects real issue reduction rather than cosmetic changes.

   Sprint 4 secondary checks:

   `python scripts/lint_repo.py`

   `python scripts/gui_smoke_acceptance.py` if frontend API contracts or UI-integrated flows changed during the pass.

Overall acceptance:

- The server surface is structurally simpler and no longer split across duplicate export implementations.
- Storage/write semantics are explicit instead of implied by hidden protocols and silent no-ops.
- The highest-impact review findings in the server/storage/api clusters are resolved in code and removed or downgraded on the next scan.
- The `initialization_coupling` rerun is completed and no longer leaves the overall score on a suspect baseline.
- Remaining high-impact issues, if any, are either directly queued for the next pass or explicitly deferred with a reason that matches the scope lock.


## Risks and Recovery


The highest risk is changing ownership boundaries without preserving stable import seams. `lenslet.server` is a known touchpoint for tests and callers, so Sprint 1 must preserve import names even while moving implementation elsewhere.

The second risk is changing storage semantics in a way that breaks route assumptions across memory, dataset, and table modes. Sprint 2 must keep contract changes explicit and test-backed, with one backend-wide rule for read-only writes and missing indexes.

The third risk is allowing a cleanup sprint to turn into a broad rewrite. The scope budget and gate routine are the defense here: if a change does not close a current review cluster or its acceptance gate, cut it.

Recovery path:

- Keep each sprint in its own commit boundary.
- If a refactor destabilizes runtime behavior, revert only the affected call sites and keep the extracted module/type additions if they still reduce complexity safely.
- Use rescans as idempotent checkpoints: after any failed attempt, rerun the targeted tests and `desloppify scan --path .` to confirm the repo is back in a known state before retrying.


## Progress Log


- [x] 2026-03-14T06:37:00Z Added `.desloppify/` to `.gitignore` and excluded obvious generated/vendor/cache paths from the scan.
- [x] 2026-03-14T06:40:00Z Ran initial `desloppify scan --path .`, prepared the holistic review packet, and launched the 20-dimension Codex review batch.
- [x] 2026-03-14T06:58:00Z Imported review findings and moved the repo from `strict 17.7` to `strict 74.9`.
- [x] 2026-03-14T06:59:00Z Confirmed repeated root-cause clusters around server surface duplication, storage protocol drift, and inconsistent read-only mutation behavior.
- [x] 2026-03-14T07:00:00Z Drafted this execution plan and completed a subagent review pass to tighten sprint boundaries and queue bookkeeping.
- [ ] 2026-03-14T07:05:00Z Complete the blocking `initialization_coupling` re-review and record any changed assessment or issue IDs. Current blocker: `desloppify review --run-batches` ignored the prepared single-dimension rerun twice and fanned out into a full 20-batch review, so the rerun was stopped instead of burning more time.
- [x] 2026-03-14T07:18:00Z Completed Sprint 1 slice: reduced `src/lenslet/server.py` to a passive facade, removed the `server_factory -> server` runtime hop, and moved comparison-export ownership fully off the public facade. Validation: `pytest tests/test_import_contract.py tests/test_compare_export_endpoint.py`.
- [x] 2026-03-14T07:31:00Z Completed Sprint 2 slice for write-contract honesty: read-only storages now raise explicit write errors, browse-mode mutating routes now reject read-only workspaces with `403`, and `Workspace.save_views()` no longer writes to shadow in-memory state when `can_write` is false. Validation: `pytest tests/test_collaboration_sync.py tests/test_parquet_ingestion.py tests/test_storage_write_contract.py tests/test_compare_export_endpoint.py tests/test_import_contract.py` and `python scripts/lint_repo.py`.
- [x] 2026-03-14T07:42:00Z Rescanned after the validated slices. The scan refreshed to `strict 74.7`, but auto-resolve for review findings still returned `0`, so the score did not reflect the closed subjective items automatically.
- [x] 2026-03-14T07:46:00Z Manually resolved the closed review IDs in the living plan: `server_facade_still_runtime_hub`, `server_facade_still_owns_duplicate_export_logic`, `comparison_export_seam_split`, `localstorage_write_contract_is_silent_noop`, and `can_write_is_not_a_route_permission_boundary`.
- [x] 2026-03-14T08:06:00Z Completed the storage hidden-protocol slice: deleted `src/lenslet/storage/table_facade.py`, introduced `src/lenslet/storage/source_backed.py` as an explicit shared mixin for source-backed storage behavior, moved table-only column normalization into `src/lenslet/storage/table.py`, and trimmed `TableStorage` / `DatasetStorage` wrapper methods that only forwarded into the old hidden facade.
- [x] 2026-03-14T08:15:00Z Validated the storage hidden-protocol slice with `pytest tests/test_search_text_contract.py tests/test_refresh.py tests/test_parquet_ingestion.py tests/test_collaboration_sync.py tests/test_search_source_contract.py tests/test_compare_export_endpoint.py tests/test_import_contract.py` plus `python scripts/lint_repo.py`.
- [x] 2026-03-14T08:23:00Z Forced a rescan with attestation because `desloppify` simultaneously reported `Queue cleared!` and `Scanning mid-cycle regenerates issue IDs`. The forced rescan moved the repo to `strict 74.5`, resolved 28 issues mechanically, opened 13 new ones, and still skipped review auto-resolve.
- [x] 2026-03-14T08:26:00Z Manually resolved the storage hidden-protocol review IDs `storage_facade_implicit_protocol` and `storage_hidden_private_protocol`. Left the remaining wrapper-shell review IDs open because the mixin removed the hidden contract, but `TableStorage` / `DatasetStorage` still need another pass to collapse the remaining helper trampolines.
- [x] 2026-03-14T08:28:00Z Started the next structural cluster from the refreshed plan. Chosen slice: factory/API option-bag simplification plus removal of the remaining generic dataset-vs-table launch dispatcher.
- [x] 2026-03-14T08:35:00Z Re-ran the blocked `initialization_coupling` prepare step and confirmed the runner bug still reproduces: a single-dimension rerun prepared cleanly, but `desloppify review --run-batches --runner codex --parallel --scan-after-import` immediately fanned out into a 20-batch holistic run again (`.desloppify/subagents/runs/20260314_074443/run.log`). This remains a tooling blocker rather than a code blocker.
- [x] 2026-03-14T08:42:00Z Completed the factory/API cutover: removed the public `BrowseAppOptions` bag, made `create_app_from_table()` and `create_app_from_storage()` take aligned explicit keyword args, added one private browse-app helper for the shared runtime path, and split the programmatic launch internals into explicit dataset/table builders and banners instead of a generic `mode/payload` dispatcher. Validation: `pytest tests/test_api_contract.py tests/test_programmatic_api.py tests/test_import_contract.py tests/test_search_source_contract.py tests/test_hotpath_sprint_s4.py tests/test_parquet_ingestion.py tests/test_folder_recursive.py` and `python scripts/lint_repo.py`.
- [x] 2026-03-14T08:45:00Z Manually resolved the review IDs closed by the factory/API cutover: `app_factory_option_bag_chain`, `table_app_factory_passthrough`, and `launch_overloads_dataset_and_table_modes`. I left `factory_family_has_parameter_sprawl_and_reordering` open because the signatures are now explicit and aligned, but still wide enough that the remaining review concern may still stand.
- [x] 2026-03-14T08:49:00Z Removed the repeated Python syntax-warning noise from `frontend/update_header_css.py` by rewriting its replacement strings as plain CSS literals instead of invalid escaped Python strings. Validation: `python -m py_compile frontend/update_header_css.py` and `python scripts/lint_repo.py`.
- [x] 2026-03-14T08:55:00Z Completed the storage-contract slice: standardized `get_index()` misses across memory, table, and dataset storage to return `None`, added a shared browse-storage protocol in `src/lenslet/storage/base.py`, made `MemoryStorage.get_metadata_readonly()` return detached snapshots, and added `tests/test_storage_contracts.py` to cover missing-index, readonly-metadata, and HTTP `404` behavior. Validation: `pytest tests/test_storage_contracts.py tests/test_storage_write_contract.py tests/test_search_text_contract.py tests/test_refresh.py tests/test_folder_recursive.py tests/test_hotpath_sprint_s4.py tests/test_parquet_ingestion.py tests/test_dataset_http.py` and `python scripts/lint_repo.py`.
- [x] 2026-03-14T08:58:00Z Manually resolved the stale storage review IDs `storage_backends_disagree_on_get_index_contract`, `get_index_error_contract_split`, and `readonly_metadata_aliasing`.
- [ ] 2026-03-14T09:00:00Z Restore a trustworthy `desloppify` execution cycle. Current blocker: after the latest resolves, `desloppify status` reports `39 planned` items and `41` open review issues, but `desloppify next` still reports `Queue: 0 items`, and a normal `desloppify scan --path .` still aborts as “mid-cycle”. The current workflow has to stay plan-driven until the tool state is coherent again or another explicit forced rescan is justified.
- [x] 2026-03-16T21:22:08Z Completed the storage-surface follow-up batch: split the base storage contract into read-only vs writable protocols, added explicit browse-item/browse-storage helpers, aligned `join()` on rooted logical paths, gave all browse backends the same cached-item shape, and replaced the remaining server-side reads of storage internals used by media, sync, refresh, and browse health with explicit methods such as `get_cached_thumbnail()`, `get_source_path()`, `metadata_items()`, `replace_metadata()`, and `total_items()`. Validation: `python scripts/lint_repo.py` and `pytest tests/test_storage_contracts.py tests/test_storage_write_contract.py tests/test_search_source_contract.py tests/test_refresh.py tests/test_folder_recursive.py tests/test_hotpath_sprint_s4.py tests/test_parquet_ingestion.py tests/test_dataset_http.py tests/test_import_contract.py tests/test_indexing_health_contract.py`.
- [x] 2026-03-16T21:22:08Z Closed the obvious dependency drift in packaging metadata: added an explicit direct `pydantic` runtime dependency in `pyproject.toml` and removed the unused Radix runtime packages from `frontend/package.json` / `frontend/package-lock.json`.


## Artifacts and Handoff


Current working artifacts:

- `scorecard.png`
- `.desloppify/query.json`
- `.desloppify/plan.json`
- `.desloppify/subagents/runs/20260314_064058/holistic_issues_merged.json`
- `.desloppify/subagents/runs/20260314_070435/` (aborted `initialization_coupling` rerun attempts that fanned out into full review batches)
- `.desloppify/subagents/runs/20260314_074443/` (latest attempted single-dimension rerun; `run.log` shows the codex runner still queued all 20 review batches)
- Forced-rescan command used after the storage hidden-protocol slice: `desloppify scan --path . --force-rescan --attest "I understand this is not the intended workflow and I am intentionally skipping queue completion"`

Current working score:

- `overall 74.6`
- `objective 69.7`
- `strict 74.5`
- `verified 69.7`

Current queue state anomaly:

- `desloppify status` reports `39 planned` review items and `41` open review issues.
- `desloppify next` still returns `Queue: 0 items`.
- `desloppify scan --path .` still refuses to run without a forced rescan because it thinks the queue is mid-cycle.

Current high-priority review clusters to attack first:

- Factory family parameter sprawl and the broader `server_factory.create_app()` lifecycle overload.
- Server auth boundary and other intentionally deferred high-impact review items that still pull subjective scores down.
- Test-health and remaining script-noise items that are now the largest mechanical drag after the server/storage cleanup.
- Deferred but tracked: shared auth boundary and the blocked `initialization_coupling` rerun.

Immediate operator handoff:

- Keep treating `desloppify show review --status open` and `desloppify plan` as the source of truth while `desloppify next` intermittently reports an empty queue.
- The storage hidden-protocol root cause is now removed in code, but `desloppify` still needs manual resolve help for subjective items because review auto-resolve is still skipping closed IDs.
- The factory/API option-bag slice and the storage-contract slice are now complete and validated, so the next structural slice should focus on the residual wrapper shells in `TableStorage` and `DatasetStorage`, then the broader `server_factory.create_app()` overload.
- Before the next subjective-score checkpoint, retry the stalled `initialization_coupling` rerun only if the review runner can be constrained to the requested dimension instead of launching the full 20-batch pass again. The latest failed evidence is in `.desloppify/subagents/runs/20260314_074443/run.log`.
- After the next slice, rerun the targeted validation and `python scripts/lint_repo.py`. Only run a normal `conda run -n conda313 desloppify scan --path .` if the queue state is coherent; otherwise continue manual resolve plus plan-driven execution or do one explicit forced rescan at the end of a larger coherent batch.
- Continue using `conda run -n conda313 desloppify plan resolve` for subjective findings that are demonstrably fixed but were skipped by auto-resolve.

Change note:

This document was revised after a dedicated plan-review subagent identified three gaps: the `initialization_coupling` rerun is now a blocking preflight step, `desloppify` resolve bookkeeping is now explicit, and the former Sprint 3 was split so storage-shell removal and API/factory simplification are no longer bundled into one oversized increment.
