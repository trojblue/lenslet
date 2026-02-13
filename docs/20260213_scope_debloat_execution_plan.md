# 20260213 Scope Debloat Execution Plan (Rewritten to Lean Standard)


## Outcome + Scope Lock


This plan executes a debloat pass that removes dead and legacy code while preserving important product behavior. After implementation, Lenslet should keep public sharing (`--share`) and inspector compare export, while removing unused ParquetStorage and legacy presence lifecycle compatibility. The expected result is lower maintenance overhead, fewer patch-like branches, and a measurable net LOC reduction.

Goals for this plan are to remove dead backend paths, collapse presence to the modern lifecycle contract, preserve compare-export behavior while reducing coupling, and hit a minimum net deletion target of 500 lines. Stretch target is 700+ lines if cleanup lands cleanly.

Non-goals are touch/mobile UX redesign, compare-export feature removal, share-flow removal, or broad architecture redesign beyond approved scope.

Scope lock decisions confirmed with user are as follows. ParquetStorage removal is approved. `--share` must be retained. Full lifecycle-v1 compatibility removal is approved. Inspector compare export must remain functional, but modularization is desired. Touch/mobile simplification is deferred to a separate session.

Approval matrix for this plan is as follows. Tier A changes are pre-approved and include dead-code cleanup and non-behavioral simplification. Tier B changes are approved for this session and include mild behavior changes tied to legacy presence removal. Tier C changes are not pre-approved and require explicit sign-off before implementation.


## Context


The current codebase is a post-refactor state where several simplification passes already ran but left behind dead paths and compatibility scaffolding. The highest-value cleanup areas are backend storage and presence lifecycle plumbing, plus inspector compare-export coupling boundaries.

Primary paths in scope are `src/lenslet/storage/parquet.py`, `tests/test_search_text_contract.py`, `src/lenslet/cli.py`, `src/lenslet/server_factory.py`, `src/lenslet/server_runtime.py`, `src/lenslet/server_routes_presence.py`, and inspector compare-export modules under `frontend/src/features/inspector/`.

Motivating context comes from `docs/20260212_issue_tweak_tracking.md` and `docs/20260211_foundational_long_file_refactor_plan.md`, plus direct user intent to reduce scope and remove leftover complexity.

Key terms used here are precise. “Debloat” means reducing unnecessary code and branches while keeping robust behavior. “Lifecycle-v1 compatibility” means legacy presence fallback behavior that is now approved for removal. “Modularization” means behavior-preserving boundary cleanup that lowers accidental coupling.


## Plan of Work


Implementation order is deletion-first, then legacy-branch removal, then boundary cleanup, then acceptance/accounting. This sequence front-loads guaranteed value and minimizes accidental scope expansion.

### Scope Budget and Guardrails

This plan uses a hard budget of 4 sprints and 10 tasks. Any additional task requires explicit justification and user confirmation before inclusion. Prefer deletion over new abstraction when both solve the same problem.

While implementing each sprint, update this plan continuously in `Progress Log` and relevant sections, and add handoff notes after each sprint. For minor script-level uncertainties, proceed according to this approved plan to maintain momentum, then request clarifications and apply follow-up adjustments.

### Sprint Plan

1. Sprint S1: Remove dead ParquetStorage path.
   Goal is to eliminate unused backend storage code and preserve search contract coverage through active storage types.
   Demo outcome is backend startup and search contract tests passing without `ParquetStorage`.
   Tasks: T1, T2, T3.

2. Sprint S2: Collapse presence to v2-only lifecycle.
   Goal is to remove legacy lifecycle branches and flags while preserving active presence behavior.
   Demo outcome is no lifecycle-v1 flag/branch usage in code or active docs/scripts, with backend and frontend presence tests passing.
   Tasks: T4, T5, T6.

3. Sprint S3: Keep compare export, reduce coupling.
   Goal is no feature removal, only module-boundary cleanup for compare export.
   Demo outcome is unchanged compare-export behavior with narrower import boundaries and green tests.
   Tasks: T7, T8.

4. Sprint S4: Verify, measure, and hand off.
   Goal is consolidated validation, LOC accounting, and explicit deferred-scope handoff.
   Demo outcome is acceptance suite passing and KPI recorded.
   Tasks: T9, T10.

### Task Details

- T1: Delete `src/lenslet/storage/parquet.py` and remove direct references.
- T2: Migrate `tests/test_search_text_contract.py` off `ParquetStorage` to `TableStorage`-backed fixture coverage.
- T3: Run dead-reference scan and startup smoke to confirm removal did not break startup/import paths.
- T4: Remove `--presence-lifecycle-v2` and `--no-presence-lifecycle-v2` from CLI while retaining `--share`.
- T5: Remove lifecycle-v1 branches from presence route/runtime/factory plumbing.
- T6: Update tests and active docs/scripts to remove lifecycle-flag usage and confirm v2-only expectations.
- T7: Create explicit compare-export boundary module and isolate internals behind it.
- T8: Rewire inspector consumers to boundary-only imports and keep compare-export behavior unchanged.
- T9: Run consolidated acceptance checks (backend, frontend, and smoke checks).
- T10: Record net LOC delta, per-area deletions, and final handoff notes including deferred touch/mobile scope.

### Execution Commands

Run from repository root unless otherwise noted.

    git checkout -b chore/debloat-v2-presence-parquet
    git status --short
    rg -n -e "ParquetStorage|storage.parquet" src tests
    rg -n -e "presence-lifecycle-v2" -e "presence_lifecycle_v2" src tests docs scripts frontend


## Validation and Acceptance


Per-sprint acceptance is required before moving on.

Sprint S1 acceptance requires `ParquetStorage` removed, search contract tests green, and startup/help smoke check passing.

Sprint S2 acceptance requires lifecycle flags removed, legacy branches removed, backend and frontend presence tests passing, and no active lifecycle flag usage in docs/scripts outside archived historical notes.

Sprint S3 acceptance requires compare-export behavior unchanged, boundary import cleanup complete, and targeted compare-export tests passing.

Sprint S4 acceptance requires consolidated checks passing, net LOC reduction at or above 500 lines, and explicit handoff notes recorded.

Validation command baseline:

    pytest -q tests/test_search_text_contract.py
    pytest -q tests/test_presence_lifecycle.py
    python -m lenslet.cli --help
    cd frontend && npm run test -- src/api/__tests__/client.presence.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/api/__tests__/client.exportComparison.test.ts && npx tsc --noEmit
    cd /home/ubuntu/dev/lenslet && rg -n -e "presence-lifecycle-v2" -e "presence_lifecycle_v2" docs scripts README.md

Sprint S1 execution evidence (2026-02-13 iteration 1):

    pytest -q tests/test_search_text_contract.py  # 9 passed in 0.35s
    python -m lenslet.cli --help                  # passed
    rg -n "ParquetStorage|storage\.parquet" src tests  # no matches

Overall acceptance means approved capabilities are preserved (`--share`, compare export), approved legacy behavior is removed (presence v1), deferred touch/mobile scope remains untouched, and deletion KPI is achieved.


## Risks and Recovery


Main risks are hidden lifecycle-flag dependencies in scripts/docs, accidental compare-export behavior drift during modularization, and over-broad edits that exceed budget.

Mitigations are evidence-based scans, sprint-level test gates, and narrow file targeting per task. If a sprint fails, revert only that sprint’s commit range and re-run validation before proceeding.

Use non-destructive rollback patterns. Prefer `git revert <commit>` for failed sprint slices. Keep commits small and scoped so retries are straightforward.


## Progress Log


- [x] 2026-02-13T16:25:17Z Scope approvals captured: remove ParquetStorage, keep `--share`, remove legacy presence, keep compare export, defer touch/mobile.
- [x] 2026-02-13T16:27:16Z Previous plan version incorporated subagent feedback.
- [x] 2026-02-13T16:48:19Z Rewrote plan to lean standard with 8 core sections, scope budget, and reduced task set.
- [x] 2026-02-13T16:56:33Z Implementation started in plan mode iteration 1 (`max_tasks_per_iteration=6`).
- [x] 2026-02-13T16:57:02Z Sprint S1 T1 completed: removed `src/lenslet/storage/parquet.py` and all direct code/test references.
- [x] 2026-02-13T16:57:20Z Sprint S1 T2 completed: rewired `tests/test_search_text_contract.py` from `ParquetStorage` to `TableStorage` loaded via parquet fixture.
- [x] 2026-02-13T16:57:41Z Sprint S1 T3 completed: dead-reference scan clean (`src/tests`), search contract tests green, and CLI help smoke passes.
- [x] 2026-02-13T16:57:55Z Sprint S1 completed and handoff note added.
- [ ] Sprint S2 completed and handoff note added.
- [ ] Sprint S3 completed and handoff note added.
- [ ] Sprint S4 completed and final handoff note added.


## Artifacts and Handoff


Baseline LOC anchors from planning pass:

    501 src/lenslet/storage/parquet.py
    228 tests/test_search_text_contract.py
    927 src/lenslet/cli.py
    746 src/lenslet/server_factory.py
    310 src/lenslet/server_routes_presence.py
    1324 frontend/src/app/AppShell.tsx
    208 frontend/src/features/inspector/hooks/useInspectorCompareExport.ts
    121 frontend/src/features/inspector/sections/SelectionExportSection.tsx

Handoff checklist for the next implementation session:

- Keep edits within the 10-task budget unless user approves expansion.
- Preserve compare-export behavior and `--share` capability.
- Treat touch/mobile as deferred and do not absorb that scope into this pass.
- Record per-sprint notes directly in this file during execution.
- Report net LOC delta and notable behavior impacts at completion.

Sprint S1 handoff (completed 2026-02-13T16:57:55Z):

- Completed tasks: `T1`, `T2`, `T3`.
- Files changed: deleted `src/lenslet/storage/parquet.py`; updated `tests/test_search_text_contract.py`.
- Validation outcomes: `pytest -q tests/test_search_text_contract.py` passed (`9 passed`); `python -m lenslet.cli --help` passed; `rg -n "ParquetStorage|storage\.parquet" src tests` returned no matches.
- Assumption used: legacy parquet-only storage path is dead and safe to delete because active app paths use `TableStorage`; no runtime references remained in `src/tests`.


## Interfaces and Dependencies (Conditional)


Presence contract changes are expected to remove lifecycle-v1 compatibility branches and flags. Active client behavior for v2 presence paths must remain stable and validated by backend and frontend presence tests.

Compare-export contract should remain centered on existing `POST /export-comparison` behavior and current client/test payloads. Modularization must not alter endpoint semantics.

Operational dependencies include active docs/scripts/automation that may still reference removed lifecycle flags. These references must be updated in the same change set.

Revision note (2026-02-13): Rewrote this plan to the lean 8-section standard with explicit scope budget, reduced task count, and tighter anti-bloat guardrails.
