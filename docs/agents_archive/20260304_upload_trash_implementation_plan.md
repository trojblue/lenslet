# Upload, Trash, and Delete Implementation Plan (2026-03-04)


## Outcome + Scope Lock


After implementation, users running `lenslet <dir>` can edit metadata as they do today, while source file mutations are disabled by default. File mutations become available only with `--allow-file-operations`. Permanent delete is additionally gated by `--dangerously-delete-files`.

Users will get these behaviors:

- Default local browse: upload disabled, trash is virtual, recover restores to `original_position` only.
- Local browse with `--allow-file-operations`: upload/move/trash become real filesystem operations under dataset root, including real `/_trash_` folder.
- Local browse with both flags: permanent delete in trash scope is enabled and still requires confirm in UI.
- Unsupported modes (remote/dataset/table-only non-local): controls are greyed out with reason text.

Goals:

- Close the broken path where mutation controls exist but backend returns `405`.
- Make support boundaries explicit and capability-driven.
- Keep API and implementation lean, with minimum-robust semantics.

Non-goals:

- Remote/object-store file operations.
- Multi-user trash conflict resolution.
- Endpoint versioning/future-proof schema expansion.
- Backward-compatibility shims beyond this alpha cutover.

Approval matrix:

- Pre-approved now: keep endpoint surface lean (`POST /file`, `POST /move`, `POST /delete`), add new CLI flags, add health capability fields, implement virtual trash default + real trash with flag, enforce dangerous delete gate, add frontend disabled states/messages and rename banners.
- Requires explicit sign-off: adding new endpoint families (for example `/restore`), changing persisted metadata schema format beyond additive fields, or enabling file operations outside local browse.

Deferred/out-of-scope:

- Remote-mode mutation support.
- Trash retention policies.
- Undo history beyond recover.


## Context


Current state is documented in [20260304_upload_trash_behavior_audit.md](/local/yada/dev/lenslet/docs/20260304_upload_trash_behavior_audit.md): frontend calls mutation endpoints, but backend currently exposes only `GET /file`, so mutation requests fail with `405`.

No repository `PLANS.md` was found. This document is the execution plan source of truth.

Important scope-lock decisions captured from the user on 2026-03-04:

- Default local behavior: metadata writable, data-file mutation not writable.
- Virtual trash is used in default mode.
- Upload is disabled in default mode.
- Flags: `--allow-file-operations`, `--dangerously-delete-files`.
- Upload keeps leaf-folder-only restriction.
- Upload collision handling: auto-rename and show dismissable rename banner.
- Recover behavior: restore to `original_position` only.
- Recover collision handling in real mode: auto-rename using recovered naming pattern (for example `__RECOVERED_...`).

Subagent review changes adopted:

- Capability gating is based on explicit health capabilities, not raw `mode` string.
- Recover path is explicitly allowed in virtual mode while generic non-trash moves remain disallowed.
- Cache invalidation is a concrete task.
- Validation commands are concrete and tied to added tests.
- Response schema remains minimal to avoid scope creep.


## Plan of Work


Implementation will be delivered in 3 sprints and 10 tasks (within budget: max 4 sprints / 12 tasks). The plan prioritizes root-path closure first (mutation route availability and policy), then semantics, then UX alignment.

While implementing each sprint, update this plan continuously, especially Progress Log and impacted sections. After each sprint is complete, add clear handoff notes.

For minor script-level uncertainties (for example exact helper placement or naming details), proceed with this approved plan to keep momentum. After sprint completion, ask clarifications and apply follow-up adjustments.

Debloat/removal targets are removal of implicit `405`-driven frontend behavior assumptions, removal of stale mutation fallbacks, and consolidation to one capability-driven disabled-reason pathway. Net-change measurement is tracked with:

    rg -n "status === 405|Upload and move actions are disabled|file_operations|moveFile\(|uploadFile\(|deleteFiles\(" frontend/src src/lenslet
    git diff --stat

Scope and quality guardrails:

- Quality floor: strict path canonicalization, explicit policy errors, deterministic rename behavior.
- Maintainability floor: central policy helper and shared capability model, no duplicate per-route policy branches.
- Complexity ceiling: no new endpoint family and no generic job system in this phase.

Sprint plan:

1. Sprint 1: Capability and route foundation.

   Demo outcome: mutation endpoints exist and return policy-driven responses instead of `405`; health advertises capability state.

   Tasks:

   - T1: Add CLI flags and runtime state for `--allow-file-operations` and `--dangerously-delete-files`.
   - T2: Extend health payload with `file_operations` capability object (`supported`, `enabled`, `dangerous_delete_enabled`, `reason`).
   - T3: Implement `POST /file`, `POST /move`, `POST /delete` in common routes with minimal response shape `{ok, failures:[{path,reason}], renamed:[...]}` and shared policy guard helpers.

2. Sprint 2: Local semantics (virtual trash default, real ops when enabled).

   Demo outcome: default mode supports virtual trash + recover, enabled mode supports real upload/move/trash, and dangerous delete is enforced.

   Tasks:

   - T4: Upload semantics in local mode when enabled: leaf-folder-only guard, collision auto-rename, renamed list in response.
   - T5: Move semantics: virtual trash and virtual recover-only in default mode; real move/trash/recover in enabled mode.
   - T6: Delete semantics: reject unless both flags are active; enforce canonical safety checks and minimal failure reporting.
   - T7: Virtual-trash visibility and cache invalidation: hide trashed items in normal scopes, show in trash scope, invalidate browse/search caches on trash/recover/delete/move.

3. Sprint 3: Frontend capability-driven UX and feedback.

   Demo outcome: UI accurately reflects supported operations by mode/flag; users see clear reason text and rename feedback.

   Tasks:

   - T8: Read `/health.file_operations` and drive disabled states for upload/move/trash/delete across toolbar and context menu.
   - T9: Update action flows for virtual recover-only behavior in default mode and unsupported-mode reason popover/message.
   - T10: Add dismissable rename banner for upload/recover collision renames, including recovered naming pattern display.

Gate routine applied to every task T1-T10:

- 0) Plan gate (fast): restate ticket goal, acceptance criteria, and files to touch.
- 1) Implement gate (correctness-first): implement smallest coherent slice plus targeted verification.
- 2) Cleanup gate (reduce noise before review): run conservative cleanup after sprint completion.
- 3) Review gate (review ship diff): run post-cleanup review, fix findings, rerun focused checks.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill on that sprint’s diff. Run non-semantic cleanup only first: formatting/lint autofixes, obvious dead code removal, tiny readability edits, and doc/comment alignment. Do not expand into semantic refactors unless explicitly approved.

### review routine


After each complete sprint and after cleanup, spawn a fresh agent and request a code review using the `code-review` skill on the post-cleanup diff. Apply fixes, rerun affected validations, and rerun review when needed until high-severity findings are closed.


## Validation and Acceptance


Validation hierarchy distinguishes primary user-path checks from secondary fast checks.

Primary acceptance gates (real scenario):

1. Default local mode behavior.

      lenslet /tmp/lenslet-fixture

   Expected: upload disabled with explicit reason; `Move to trash` succeeds virtually; item disappears from normal browse/search; item appears in trash scope; source file remains at original disk path.

2. Enabled real file operations.

      lenslet /tmp/lenslet-fixture --allow-file-operations

   Expected: upload enabled in leaf folders only; upload collision triggers auto-rename; dismissable rename banner appears; move-to-trash physically moves file under `/_trash_`.

3. Dangerous delete gate.

      lenslet /tmp/lenslet-fixture --allow-file-operations --dangerously-delete-files

   Expected: permanent delete is enabled only in trash scope; confirm prompt is required; confirmed delete removes file from disk.

Secondary acceptance gates (fast/proxy):

1. Backend API policy matrix and semantics.

      pytest tests/test_file_operations_api.py -q
      pytest tests/test_virtual_trash_visibility.py -q

   Expected: route statuses and policy reasons match capability states; virtual trash/recover filtering and invalidation are verified.

2. Frontend capability-driven behavior and banners.

      cd frontend && npm test -- --runInBand --watch=false

   Expected: disabled states/messages, recover-only virtual-mode behavior, and rename banner coverage pass.

3. Repository safety checks.

      python scripts/lint_repo.py
      python scripts/gui_smoke_acceptance.py

   Expected: no lint regressions and no core browse UX regressions.

Sprint closure rules:

- Sprint 1 cannot close if mutation routes still return `405`.
- Sprint 2 cannot close if virtual trash leaks items into normal scopes.
- Sprint 3 cannot close if unsupported modes still show active mutation controls.


## Risks and Recovery


Risk: capability detection may incorrectly disable local preindex/table-backed browse. Recovery: derive support from explicit local-root mutability/capability computation and test both memory and preindex-backed local runs.

Risk: virtual trash filtering and cache invalidation can drift, causing stale UI. Recovery: centralize virtual-trash state helpers and enforce invalidation on every mutation path that changes visibility.

Risk: destructive behavior from delete path. Recovery: hard backend enforcement of dual flags plus frontend confirm prompt; reject delete requests otherwise.

Rollback path: if regressions occur, disable file mutation by capability default and revert sprint commits in reverse order.

Idempotent retry strategy: mutation handlers return deterministic outcomes with minimal failure lists; repeated virtual trash/recover requests are no-op safe; collision rename is deterministic.


## Progress Log


- [x] 2026-03-04T16:26:00Z Scope-lock decisions captured from user for flags, virtual trash, upload restrictions, and dangerous delete gate.
- [x] 2026-03-04T16:31:00Z Initial plan drafted.
- [x] 2026-03-04T16:38:00Z Subagent review completed and findings recorded.
- [x] 2026-03-04T16:40:00Z Final lock: recover is `original_position` only; real-mode recover collision uses `__RECOVERED_...` naming pattern.
- [ ] 2026-03-04T00:00:00Z Sprint 1 in progress.
- [ ] 2026-03-04T00:00:00Z Sprint 2 in progress.
- [ ] 2026-03-04T00:00:00Z Sprint 3 in progress.


## Artifacts and Handoff


Primary artifacts to produce during implementation:

- Backend route and capability changes in `src/lenslet/server_factory.py`, `src/lenslet/server_routes_common.py`, and `src/lenslet/cli.py`.
- Virtual-trash state/filter helpers and invalidation updates in browse/storage path.
- Frontend capability-driven action gating and rename banner updates in `frontend/src/app/hooks/useAppActions.ts`, `frontend/src/app/menu/AppContextMenuItems.tsx`, and toolbar/context-menu components.
- New targeted tests: `tests/test_file_operations_api.py`, `tests/test_virtual_trash_visibility.py`, plus frontend tests for gating and banners.

Handoff notes for implementer:

- Execute sprints in order; do not start Sprint 2 before Sprint 1 route/capability acceptance is green.
- Keep response schema minimal in this phase.
- Treat unsupported-mode UX as capability-driven, not mode-string heuristics.


## Interfaces and Dependencies


CLI/runtime interface changes:

- New flag: `--allow-file-operations` (default false).
- New flag: `--dangerously-delete-files` (default false, effective only when file operations are enabled).

Health interface change:

- Add `file_operations` capability object used directly by frontend gating.

HTTP mutation interfaces (kept lean):

- `POST /file`
- `POST /move`
- `POST /delete`

Response contract remains minimal and consistent across mutation handlers:

- `{ ok: boolean, failures?: [{ path, reason }], renamed?: [{ from, to, reason }] }`

Operational dependency:

- Real trash target path is dataset-root `/_trash_`.


Revision note: revised after subagent review and final user clarifications to (1) switch capability gating from mode-based to explicit health capability, (2) specify recover-only exception in virtual mode, (3) add cache invalidation as explicit task, (4) tighten validation commands to concrete test modules, and (5) de-scope response complexity to a minimal contract.
