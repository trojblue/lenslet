# Safe Fallback Removal Plan (2026-02-19)


## Outcome + Scope Lock


After implementation, Lenslet removes all seven "Safe" fallback code paths from the 2026-02-19 audit across backend and frontend, with tests updated so the current API and UI behavior are the only supported path. The codebase should read as if these fallbacks never existed.

Goals: remove the audited safe fallbacks in code and tests, keep changes localized to the audited files and directly related tests, and avoid new dependencies or abstractions.

Non-goals: removing any "Caution" or "Risky" fallbacks, adding new compatibility layers, changing storage backends, updating `docs/fallback_audit_20260219.md`, or rebuilding the bundled frontend output in `src/lenslet/frontend/` unless explicitly requested.

Approvals: removal of the seven "Safe" entries is pre-approved. Any behavior changes outside those entries or any removal of "Caution"/"Risky" fallbacks requires explicit sign-off.

Deferred/out-of-scope: new migration tooling for older clients, broader UI refactors, or regenerating the bundled frontend output (note this explicitly in handoff if needed later).


## Context


The audit in `docs/fallback_audit_20260219.md` lists seven "Safe" fallbacks with locations in `src/lenslet/` and `frontend/src/`. The user confirmed the scope is code removal only, all safe entries are in-scope, and validation should be `pytest` only (with tests updated as needed). No `PLANS.md` exists in this repo.

Key safe fallbacks and locations from the audit are: legacy query param guard in `src/lenslet/server_routes_common.py` (plus tests), legacy `/presence` heartbeat usage and client ID migration in `frontend/src/api/client.ts`, legacy `leftW` sidebar key in `frontend/src/app/layout/useSidebars.ts`, legacy `stars` filter clause in `frontend/src/features/browse/model/filters.ts`, sort parse fallback to last-known spec in `frontend/src/shared/ui/Toolbar.tsx`, and mutation error message fallback in `frontend/src/app/hooks/useAppActions.ts`. Backend `/presence` still exists in `src/lenslet/server_routes_presence.py` and will be removed to fully eliminate the legacy route.


## Interfaces and Dependencies


This change removes compatibility surfaces: legacy query parameters (`legacy_recursive`, `page`, `page_size`), the legacy `/presence` heartbeat route, the legacy client ID storage key, the legacy sidebar width key, the legacy `stars` filter clause, the sort parse fallback to last-known spec, and the mutation error message fallback. The backend and frontend remain coupled through the current APIs; no new external dependencies are introduced.


## Plan of Work


While implementing each sprint, update this plan document continuously, especially the Progress Log and any sections impacted by discoveries. After each sprint is complete, add clear handoff notes in Artifacts and Handoff.

For minor script-level uncertainties (for example, exact file placement), proceed according to this plan to maintain momentum. Do not use this clause to decide behavior changes; behavior decisions must remain explicit and approved. After the sprint, ask for clarifications and then apply follow-up adjustments.

Before Sprint 1, reconcile the seven safe fallback entries against the current code (using the audit doc and a quick file scan) to confirm there are no drifted locations. If additional safe fallback locations are discovered, pause for scope confirmation before proceeding.

### Scope Budget and Guardrails


Scope budget: 2 sprints, 7 tasks, touching only the files listed in the audit plus directly related tests. No new modules, no new dependencies, and no cross-cutting refactors.

Quality guardrail: remove the fallbacks completely and adjust tests for the new behavior, but do not add extra abstraction or widen the scope beyond the audited safe items. If a sprint fails primary acceptance, keep it open and add explicit closure tasks before moving on.

Deletion targets: remove (1) legacy query param guard for `legacy_recursive`, `page`, `page_size`, (2) legacy `/presence` heartbeat route, (3) legacy client ID migration and `/presence` usage in the frontend client, (4) legacy `leftW` sidebar key support, (5) legacy `stars` filter clause support, (6) sort parse fallback to last-known spec, and (7) mutation error message fallback.

Net-change measurement: capture `git diff --stat` and use the file-specific removal checks in Validation and Acceptance to confirm each target is eliminated.

### Sprint Plan


1. Sprint 1: Backend legacy compatibility removal. Demo outcome is `pytest` passing with legacy query params ignored (no explicit guard) and `/presence` heartbeat removed. Tasks: S1-T1, S1-T2.
2. Sprint 2: Frontend safe fallback removal. Demo outcome is `pytest` passing with all frontend safe fallback code removed and related TS tests aligned. Tasks: S2-T1, S2-T2, S2-T3, S2-T4, S2-T5.

### Task Details


1. S1-T1 Remove the legacy query param guard for `legacy_recursive`, `page`, and `page_size` from `register_folder_route` in `src/lenslet/server_routes_common.py`. Expected behavior: requests containing those params are treated as if the params are absent (no 400), and only `path`, `recursive`, and `count_only` drive results. Update related tests, including `tests/test_folder_recursive.py` and `frontend/src/api/__tests__/folders.test.ts` if they asserted the legacy error. Validation: run `pytest tests/test_folder_recursive.py` and confirm it passes; confirm the guard block is gone with `rg -n "legacy_recursive|page_size|unsupported_query_params" src/lenslet/server_routes_common.py`. Gate routine: 0 Plan gate restate goal, acceptance, and files; 1 Implement gate smallest coherent slice plus minimal verification signals; 2 Cleanup gate run the code-simplifier routine after Sprint 1 completes; 3 Review gate run the review routine after cleanup.
2. S1-T2 Remove the legacy `/presence` heartbeat route (`@app.post("/presence")`) from `src/lenslet/server_routes_presence.py` and any server-side references used only for that route. Expected behavior: `/presence` returns 404 and only `/presence/join`, `/presence/move`, and `/presence/leave` remain. Update any tests if present. Validation: confirm the handler is removed with `rg -n "presence_heartbeat|@app.post\(\"/presence\"\)" src/lenslet/server_routes_presence.py`. Gate routine: 0 Plan gate restate goal, acceptance, and files; 1 Implement gate smallest coherent slice plus minimal verification signals; 2 Cleanup gate run the code-simplifier routine after Sprint 1 completes; 3 Review gate run the review routine after cleanup.
3. S2-T1 Remove legacy client ID migration and legacy `/presence` usage from `frontend/src/api/client.ts`, keeping only the current session key and join/move/leave API usage. Expected behavior: `lenslet.client_id` is ignored and `/presence` is never called. Update any related frontend tests if present. Validation: confirm removal with `rg -n "lenslet\.client_id|/presence" frontend/src/api/client.ts`. Gate routine: 0 Plan gate restate goal, acceptance, and files; 1 Implement gate smallest coherent slice plus minimal verification signals; 2 Cleanup gate run the code-simplifier routine after Sprint 2 completes; 3 Review gate run the review routine after cleanup.
4. S2-T2 Remove legacy sidebar width key (`leftW`) support in `frontend/src/app/layout/useSidebars.ts` and update `frontend/src/app/layout/__tests__/useSidebars.test.ts` to match the new behavior. Expected behavior: only current sidebar keys are respected, and `leftW` is ignored. Validation: confirm removal with `rg -n "leftW" frontend/src/app/layout/useSidebars.ts frontend/src/app/layout/__tests__/useSidebars.test.ts`. Gate routine: 0 Plan gate restate goal, acceptance, and files; 1 Implement gate smallest coherent slice plus minimal verification signals; 2 Cleanup gate run the code-simplifier routine after Sprint 2 completes; 3 Review gate run the review routine after cleanup.
5. S2-T3 Remove legacy `stars` clause support from `frontend/src/features/browse/model/filters.ts`, including matching and normalization helpers, so only `starsIn` and `starsNotIn` remain. Expected behavior: legacy `stars` clauses are dropped/ignored rather than applied. Update any related frontend tests. Validation: confirm removal with `rg -n "'stars' in clause|stars' in c" frontend/src/features/browse/model/filters.ts`. Gate routine: 0 Plan gate restate goal, acceptance, and files; 1 Implement gate smallest coherent slice plus minimal verification signals; 2 Cleanup gate run the code-simplifier routine after Sprint 2 completes; 3 Review gate run the review routine after cleanup.
6. S2-T4 Remove the sort parse fallback to last-known spec in `frontend/src/shared/ui/Toolbar.tsx` by eliminating the fallback parameter and handling only valid `metric:` or `builtin:` values. Expected behavior: invalid sort values do not silently reuse the prior spec and should surface as a developer error or remain unreachable via UI-controlled inputs. Validation: confirm the fallback parameter is gone with `rg -n "parseSort\(value: string, fallback" frontend/src/shared/ui/Toolbar.tsx`. Gate routine: 0 Plan gate restate goal, acceptance, and files; 1 Implement gate smallest coherent slice plus minimal verification signals; 2 Cleanup gate run the code-simplifier routine after Sprint 2 completes; 3 Review gate run the review routine after cleanup.
7. S2-T5 Remove the mutation error message fallback in `frontend/src/app/hooks/useAppActions.ts` by eliminating the fallback argument and returning only explicit error messages. Expected behavior: no generic fallback string is synthesized when errors lack messages. Validation: confirm removal with `rg -n "formatMutationError\(error: unknown, fallback" frontend/src/app/hooks/useAppActions.ts`. Gate routine: 0 Plan gate restate goal, acceptance, and files; 1 Implement gate smallest coherent slice plus minimal verification signals; 2 Cleanup gate run the code-simplifier routine after Sprint 2 completes; 3 Review gate run the review routine after cleanup.

### code-simplifier routine


After each sprint completes, spawn a subagent and instruct it to use the `code-simplifier` skill to scan the current sprint changes. Start with non-semantic cleanup only: formatting/lint autofixes, obvious dead code removal, small readability edits that do not change behavior, and doc/comments that reflect what is already true. Keep this pass conservative and do not expand into semantic refactors unless explicitly approved.

### review routine


After each sprint completes and the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Review the post-cleanup diff, apply fixes, and rerun review when needed to confirm resolution.


## Validation and Acceptance


1. Sprint 1 primary acceptance (real scenario): `pytest` passes with legacy query params ignored and `/presence` removed. Run:

    pytest

Expected outcome: all tests pass with updated assertions reflecting the removal.

2. Sprint 1 secondary checks (fast proxies): confirm removal of legacy backend guards and routes. Run:

    rg -n "legacy_recursive|page_size|unsupported_query_params" src/lenslet/server_routes_common.py
    rg -n "presence_heartbeat|@app.post\(\"/presence\"\)" src/lenslet/server_routes_presence.py

Expected outcome: no matches.

3. Sprint 2 primary acceptance (real scenario): `pytest` passes with frontend safe fallbacks removed and any updated expectations. Run:

    pytest

Expected outcome: all tests pass.

4. Sprint 2 secondary checks (fast proxies): confirm frontend fallback removals in their files. Run:

    rg -n "lenslet\.client_id|/presence" frontend/src/api/client.ts
    rg -n "leftW" frontend/src/app/layout/useSidebars.ts frontend/src/app/layout/__tests__/useSidebars.test.ts
    rg -n "'stars' in clause|stars' in c" frontend/src/features/browse/model/filters.ts
    rg -n "parseSort\(value: string, fallback" frontend/src/shared/ui/Toolbar.tsx
    rg -n "formatMutationError\(error: unknown, fallback" frontend/src/app/hooks/useAppActions.ts

Expected outcome: no matches in those files.

5. Overall primary acceptance (real scenario): full `pytest` run passes after all tasks, and the seven safe fallback paths are absent. Run:

    pytest

Expected outcome: full suite passes.


## Risks and Recovery


Risk: external clients still rely on legacy query params, localStorage keys, or `/presence`; removal could break those clients. Recovery: revert the specific commits or reintroduce narrowly scoped compatibility as a follow-up with explicit approval.

Risk: removing UI fallbacks can surface unhandled input shapes or unexpected sort values. Recovery: keep changes scoped to the audited fallback branches and, if unexpected inputs are discovered, either fix upstream producers or add a targeted guard with approval.

Risk: frontend runtime still serves stale assets if `src/lenslet/frontend/` is used in production. Recovery: rebuild the frontend bundle and copy it into `src/lenslet/frontend/` in a follow-up step if shipping assets is required.

Idempotent retry strategy: each task removal is additive-safe (re-running the task should be a no-op once tokens are gone). Use the file-specific `rg` checks to confirm absence before reattempting.


## Progress Log


- [ ] 2026-02-19: Plan drafted; awaiting implementation.


## Artifacts and Handoff


Quick scan commands to locate legacy fallback code during implementation:

    rg -n "legacy_recursive|page_size|unsupported_query_params" src/lenslet/server_routes_common.py
    rg -n "@app.post\(\"/presence\"\)" src/lenslet/server_routes_presence.py
    rg -n "lenslet\.client_id|/presence" frontend/src/api/client.ts
    rg -n "leftW" frontend/src/app/layout/useSidebars.ts frontend/src/app/layout/__tests__/useSidebars.test.ts
    rg -n "'stars' in clause|stars' in c" frontend/src/features/browse/model/filters.ts
    rg -n "parseSort\(value: string, fallback" frontend/src/shared/ui/Toolbar.tsx
    rg -n "formatMutationError\(error: unknown, fallback" frontend/src/app/hooks/useAppActions.ts

Handoff note: after each sprint, add a short summary here of removed fallback paths, tests updated, and whether frontend bundle regeneration is needed for deployment.
