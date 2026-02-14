# Medium-Tier Simplification Sprint Plan (Lenslet)


## Outcome + Scope Lock


After this plan, the `/folders` API contract is explicit and no longer advertises ignored parameters, documentation no longer references a nonexistent legacy rollback flag, and refresh behavior is consistent between backend modes and UI affordances. The scope is limited to removing medium-severity misleading surfaces without introducing new features.

Goals are to align `/folders` query semantics to one supported contract, make legacy-recursive rollback messaging truthful, and ensure refresh actions are clearly unavailable in static (dataset/table) modes while remaining functional in memory mode. All changes should be minimal and compatible with internal callers.

Non-goals for this plan are implementing true pagination for `/folders`, adding dataset/table refresh semantics, or adding a legacy rollback env var. Those items are deferred unless explicitly approved in a follow-on plan.

Approvals required before implementation are: rejecting `legacy_recursive`, `page`, or `page_size` with a 400 response; disabling or annotating refresh UI in static modes; and any change that adds a new env var or extends refresh semantics. Doc-only corrections that reflect current behavior are pre-approved.

Deferred/out-of-scope items include low-tier dead-code cleanup, unused API client methods, legacy localStorage keys, and duplicate test scripts identified in the scan.


## Context


The `/folders` route now rejects unsupported `page`, `page_size`, and `legacy_recursive` params with a 400 error and always returns pagination fields as null when using the supported contract (`src/lenslet/server_routes_common.py`, `src/lenslet/server_browse.py`, `tests/test_folder_recursive.py`). The browse responsiveness doc previously referenced a legacy rollback flag; it has been corrected in `docs/20260213_browse_responsiveness_execution_plan.md`. Refresh is a no-op outside memory mode while the UI always calls it (`src/lenslet/server_factory.py`, `frontend/src/app/AppShell.tsx`). There is no `PLANS.md` in this repo.


## Interfaces and Dependencies


This plan changes public HTTP contracts and UI behavior. `/folders` query parameters and error responses will change if unsupported params are rejected. Refresh availability in the UI will depend on `health.mode` from `/health`, which is already exposed by the backend. Documentation in `docs/20260213_browse_responsiveness_execution_plan.md` must align with the chosen contract.


## Plan of Work


Sprint Plan:

1. Sprint S1 — `/folders` contract alignment. Goal: remove dead paging/legacy knobs by rejecting unsupported params and align tests/docs. Demo: `/folders` returns 400 when unsupported params are present and docs match the new contract.
2. Sprint S2 — Refresh UX alignment for static modes. Goal: refresh actions are disabled or annotated in dataset/table modes while remaining available in memory mode. Demo: UI reflects backend modes and tests cover the new UX contract.

Tasks:

1. T1 (S1) — Enforce the `/folders` query contract by removing `page`, `page_size`, and `legacy_recursive` from the route signature and returning a 400 error when any are provided, with a clear error payload. This is the canonical path for S1 and requires approval.
2. T2 (S1) — Update tests and docs for the `/folders` contract. Adjust `tests/test_folder_recursive.py` to assert the new 400 behavior and update `docs/20260213_browse_responsiveness_execution_plan.md` to remove the legacy rollback mention and describe the explicit rejection of unsupported params.
3. T3 (S2) — Expose `health.mode` in UI state via `frontend/src/app/hooks/useAppPresenceSync.ts` and thread it to `frontend/src/app/AppShell.tsx` so refresh availability can be decided centrally.
4. T4 (S2) — Disable or annotate refresh actions when `mode` is `dataset` or `table` and keep them enabled for `memory`. Update `frontend/src/app/menu/AppContextMenuItems.tsx` to surface a clear tooltip or label such as “Refresh unavailable in read-only mode,” and add a focused unit test to lock the behavior. Update any refresh-related docs that describe availability.

Scope Budget: two sprints, four tasks, touching only the folders route, refresh flow, health-mode wiring, and the browse responsiveness doc. Net-change measurement will be captured via `git diff --stat` after each sprint.

Debloat/removal targets are limited to medium-tier surface mismatches: unused `/folders` params and the stale legacy rollback mention in docs. No low-tier removals are included.

Quality guardrail: prefer deletion and explicit errors over adding new feature paths. Avoid new abstractions or compatibility layers unless explicitly approved.

Implementation instructions: While implementing each sprint, update this plan document continuously (especially Progress Log and any impacted sections). After each sprint is complete, add clear handoff notes. For minor script-level uncertainties (for example, exact file placement), proceed according to the approved plan to maintain momentum. After the sprint, ask for clarifications and then apply follow-up adjustments.

Gate routine: Each task follows this sequence.
0) Plan gate (fast): restate the goal, acceptance criteria, and files to touch.
1) Implement gate (correctness-first): implement the smallest coherent slice that satisfies the ticket and run the minimal verification signals.
2) Cleanup gate (reduce noise before review): run the code-simplifier routine after each sprint.
3) Review gate (review the ship diff): run the review routine after each sprint and fix issues found.

### code-simplifier routine

After each sprint, spawn a subagent with the `code-simplifier` skill to scan the sprint diff. Apply only non-semantic cleanup (formatting, obvious dead code removal, small readability edits, and doc/comment alignment). Do not expand into semantic refactors without explicit approval.

### review routine

After cleanup, spawn a fresh subagent with the `code-review` skill to review the post-cleanup diff. Apply fixes, then rerun review if needed to confirm resolution.


## Validation and Acceptance


Sprint S1 primary checks (real contract behavior):

1. `pytest tests/test_folder_recursive.py` — confirms `/folders` rejects unsupported params and no longer pretends to paginate.

Sprint S1 secondary checks (fast proxies):

1. `rg -n "legacy_recursive.*rollback" docs/20260213_browse_responsiveness_execution_plan.md` — should return no matches after doc update.
2. `python scripts/lint_repo.py` — ensures lint/file-size guardrails pass.

Sprint S2 primary checks (real contract behavior):

1. `cd frontend && npm run test -- src/app/menu/__tests__/AppContextMenuItems.test.tsx` — verifies refresh actions are disabled or annotated when `mode` is `dataset` or `table`.

Sprint S2 secondary checks (fast proxies):

1. `pytest tests/test_refresh.py` — confirms backend refresh behavior remains consistent across modes.

Overall acceptance:

1. `pytest tests/test_folder_recursive.py tests/test_refresh.py` with updated assertions.
2. Docs in `docs/20260213_browse_responsiveness_execution_plan.md` align with implemented behavior.


## Risks and Recovery


Rejecting previously accepted query params may break external callers that depended on ignored parameters. Recovery is to revert to the prior “ignore” behavior or to design a compatibility toggle in a follow-on plan if evidence shows active use. Disabling refresh in static modes may surprise users; recovery is to revert the UI change while keeping backend notes intact. All changes are local and revertible by reverting the specific commits.


## Progress Log


- [x] 2026-02-14: Plan drafted; approvals for `/folders` rejection assumed per execution request (refresh UX changes still pending for S2).
- [x] 2026-02-14: Sprint S1 complete (T1-T2) — `/folders` rejects unsupported params, tests/docs updated. Validation: `pytest tests/test_folder_recursive.py`, `rg -n "legacy_recursive.*rollback" docs/20260213_browse_responsiveness_execution_plan.md`, `python scripts/lint_repo.py`.
- [ ] 2026-02-14: Sprint S2 start placeholder and handoff notes.

Sprint S1 handoff notes (2026-02-14):
- `/folders` now rejects `page`, `page_size`, and `legacy_recursive` with `unsupported_query_params`; recursive responses remain full-list with null pagination fields.
- Test coverage updated in `tests/test_folder_recursive.py` and `tests/test_hotpath_sprint_s4.py` to match the new contract.
- Browse responsiveness doc now reflects explicit 400 rejection and no rollback-flag mention.
- Code-simplifier scan (Tier 1) found no must-apply cleanup; no changes applied.
- Code-review subagent was unresponsive; manual review found no actionable issues.


## Artifacts and Handoff


Primary artifact is this plan at `docs/20260214_medium_tier_simplification_plan.md`. Key files likely to change include `src/lenslet/server_routes_common.py`, `src/lenslet/server_browse.py`, `src/lenslet/server_factory.py`, `frontend/src/app/hooks/useAppPresenceSync.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/app/menu/AppContextMenuItems.tsx`, `tests/test_folder_recursive.py`, `tests/test_refresh.py`, and `docs/20260213_browse_responsiveness_execution_plan.md`.
