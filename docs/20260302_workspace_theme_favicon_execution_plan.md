# 20260302 Workspace Theme and Dynamic Favicon Execution Plan


## Outcome + Scope Lock


After implementation, a user can choose a theme per browse workspace, keep that choice persisted locally for that workspace, and see the browser tab favicon recolor to the active theme accent so tabs are visually distinguishable during multi-workspace switching.

Goals are to ship a minimal robust theme selector for browse mode, preserve current default appearance when no theme is chosen, and add dynamic favicon recoloring tied to active theme state. The scope includes desktop and narrow-screen entry points for the same settings control.

Non-goals are free-form custom color authoring, account-synced theme profiles, broad design-system rewrites, and ranking-mode theme controls in this pass.

Behavior approvals are locked as follows. Pre-approved: settings cog under the GitHub icon, a mobile-drawer settings mount, workspace-scoped local persistence for theme selection, and dynamic favicon accent coloring. Requires sign-off: new backend endpoints beyond `/health`, ranking-mode behavior changes, new dependency introduction, or migration of unrelated persisted settings keys.

Deferred and out-of-scope work includes ranking-mode theme support, custom palette editor UI, import/export of theme presets, and workspace-scoping for non-theme localStorage keys.


## Context


Theme tokens are currently static CSS variables in `frontend/src/theme.css`, consumed by `frontend/src/styles.css`. Existing palette variants are documented in `docs/theme_variants.md` but are not user-switchable at runtime.

The left rail and GitHub icon are implemented in `frontend/src/app/components/LeftSidebar.tsx`, and narrow-screen behavior collapses sidebars, so settings must also be reachable from the mobile drawer path.

Favicon is currently static `.ico` via `frontend/index.html` and shipped `src/lenslet/frontend/index.html`, which prevents tab-level color differentiation.

Health payloads are mode-dependent and frontend typing does not include `workspace_id`. A minimal health contract extension is needed for safe workspace-scoped keying without raw path leakage.

No `PLANS.md` or equivalent top-level planning contract file was found; this document is the execution source of truth and follows AGENTS/repo guidance.

Scope-lock decisions from request context are that per-workspace theme differentiation is required, settings should live under the existing GitHub icon area, local persistence is desired, and favicon color should follow theme accent.


## Interfaces and Dependencies


This plan adds one interface extension in browse modes (`memory`, `table`, `dataset`): `/health` includes `workspace_id` as an opaque deterministic identifier. Ranking-mode `/health` is unchanged in this pass and explicitly deferred.

Frontend `HealthResponse` is extended to type optional `workspace_id`, with deterministic fallback behavior only when absent.

No new third-party dependency is introduced. Existing React/FastAPI and current utility patterns are sufficient.


## Plan of Work


Implementation proceeds in two sprints and eight atomic tasks. Each sprint is demoable and testable.

Scope budget is capped at two sprints, eight tasks, and the minimum module touch set required for browse-theme runtime, favicon updates, settings UI mounts, and targeted validation. Theme preset scope is capped to three shipped presets in this pass to prevent design-scope creep.

Quality guardrails are fixed to minimum robust: correctness and fallback safety first, maintainability with shared UI/state paths second, and complexity ceiling enforced by avoiding speculative abstractions and dependency expansion.

Implementation instruction for operators: while implementing each sprint, update this plan continuously, especially Progress Log plus any impacted validation and handoff sections. After each sprint completes, add explicit handoff notes before starting the next sprint.

Implementation instruction for uncertainties: for minor script-level uncertainties such as helper file placement, proceed with the approved plan to maintain momentum; after sprint completion, request clarification and apply focused follow-up adjustments.

Every task follows this gate sequence.

0) Plan gate (fast): restate task goal, acceptance signal, and files to touch.

1) Implement gate (correctness-first): implement smallest coherent slice and run targeted verification.

2) Cleanup gate (reduce noise before review): after sprint completion, run code-simplifier routine.

3) Review gate (review the ship diff): run review routine on post-cleanup diff and close findings.

### code-simplifier routine

After each sprint completes, spawn a subagent instructed to use the `code-simplifier` skill on that sprint diff. Keep it conservative and non-semantic first: formatting/lint autofixes, obvious dead code removal, small readability edits, and comments/docs that match behavior. Do not perform semantic refactors without explicit approval.

### review routine

After cleanup completes, spawn a fresh subagent instructed to review using the `code-review` skill on the post-cleanup sprint diff. Apply fixes, then rerun review when needed until findings are resolved or explicitly accepted with rationale.

Sprint plan and tasks:

1. Sprint 1 goal is deterministic workspace-scoped theme runtime and boot-safe apply in browse mode. Demo outcome is that browse app boot applies persisted theme and accent-colored favicon before first interactive paint.

   T1. Extend browse-mode backend `/health` payloads to include `workspace_id` with deterministic opaque derivation.
   Validation: backend health contract tests covering memory/table/dataset mode payloads.
   Status: completed in iteration 1 (2026-03-02).

   T2. Extend frontend health typing and create a single boot health source for `mode + workspace_id`, then apply theme and favicon from that source before first browse paint.
   Validation: frontend unit tests for boot health parsing and early apply ordering.
   Status: completed in iteration 1 (2026-03-02).

   T3. Build a single theme runtime engine that owns preset tokens and favicon link updates together, with idempotent apply and static `.ico` fallback.
   Validation: frontend unit tests for token apply idempotence and favicon recolor updates.
   Status: completed in iteration 1 (2026-03-02).

   T4. Add workspace-scoped theme storage helper with key shape `lenslet.v2.theme.<workspace_hash>`, plus deterministic fallback behavior when `workspace_id` is absent.
   Validation: frontend unit tests proving no raw-path leakage in key names, stable same-workspace key across reloads, distinct keys across workspaces, and deterministic fallback keying.
   Status: completed in iteration 1 (2026-03-02).

2. Sprint 2 goal is user-facing settings controls and acceptance completion with shared UI logic across desktop/mobile mounts. Demo outcome is selecting different themes in two workspaces and seeing persistent theme + favicon differentiation.

   T5. Implement shared `ThemeSettingsMenu` UI logic and mount it under a new cog button below GitHub icon in left rail.
   Validation: component tests for open/close, selection, keyboard escape, and outside-click close.

   T6. Mount the same shared `ThemeSettingsMenu` in the mobile drawer path (no duplicated state logic).
   Validation: narrow-screen component test and manual responsive check.

   T7. Add targeted tests and acceptance checks for per-workspace persistence behavior, no-regression default theme behavior, and tab favicon differentiation between two workspaces.
   Validation: frontend targeted tests plus recorded real-scenario acceptance transcript.

   T8. Update docs with only shipped preset set, persistence behavior, and favicon behavior; run final build/lint/smoke and write handoff notes.
   Validation: docs/code consistency check, frontend build sync, lint, and browse smoke acceptance.


## Validation and Acceptance


Validation hierarchy distinguishes primary real-scenario acceptance from secondary proxy checks.

Primary acceptance gates:

1. Run two browse workspaces on separate ports, choose different themes, and verify both tabs show distinct accent-colored favicons and persist per-workspace choices after reload.

2. Verify settings are functional from both mounts: left-rail cog and mobile drawer, with shared behavior and no divergence.

3. Verify default visual behavior remains unchanged when no theme is explicitly selected.

4. Verify theme localStorage key names contain no raw workspace paths and remain stable/deterministic under reload.

Secondary acceptance gates:

1. Targeted frontend tests.

    cd frontend && npm run test -- src/app src/shared/ui src/lib

2. Typecheck.

    cd frontend && npx tsc --noEmit

3. Frontend build and shipping bundle sync.

    cd frontend && npm run build && rsync -a --delete dist/ ../src/lenslet/frontend/

4. Repository lint guardrail.

    python scripts/lint_repo.py

5. Browse smoke regression.

    python scripts/gui_smoke_acceptance.py

Expected outcome is all secondary commands pass and each primary gate is logged as pass/fail with concrete notes in Progress Log.


## Risks and Recovery


Main risk is unstable `workspace_id` derivation creating persistence churn. Recovery is deterministic derivation contract per browse mode, tested for stability and uniqueness, with fallback behavior only when `workspace_id` is missing.

Second risk is browser favicon caching delaying visual updates. Recovery is deterministic favicon link replacement with cache-busting fragments while retaining `.ico` fallback.

Third risk is boot-order race causing theme flash. Recovery is explicit boot health source and early theme/fav icon apply before first browse paint, with tests asserting ordering behavior.

Rollback path is straightforward: disable runtime theme selection and favicon recolor flow while keeping existing static theme tokens and static favicon behavior. This rollback does not affect dataset/state persistence.

Idempotent retry strategy relies on pure reapplication semantics for token and favicon update functions, so repeated execution converges to the same DOM state. Storage failures remain non-fatal and fall back to session-only state.


## Progress Log


- [x] 2026-03-02 15:25:36Z Initial plan draft created from repo scan and user scope.
- [x] 2026-03-02 15:25:36Z Required subagent review executed with verbatim plan-writer review prompt.
- [x] 2026-03-02 15:25:36Z Incorporated subagent feedback: narrowed `workspace_id` scope to browse modes, added explicit boot apply task, tightened key-leakage validation, selected mobile drawer path, capped shipped presets, and collapsed to two sprints.
- [x] 2026-03-02 15:44:08Z Sprint 1 implementation executed for T1-T4: browse-mode `/health` now emits deterministic opaque `workspace_id`; frontend boot health source introduced; theme runtime+dynamic favicon engine added; workspace-scoped theme storage helper landed.
- [x] 2026-03-02 15:44:08Z Sprint 1 targeted validations passed for new work: backend workspace-id contract test (`3 passed`), frontend boot/runtime/storage tests (`14 passed`), and frontend typecheck (`npx tsc --noEmit` clean).
- [x] 2026-03-02 16:03:26Z Sprint 1 cleanup/review loop completed: required `code-simplifier` pass executed; first `code-review` pass found table workspace-id collision risk and 32-bit key collision risk; fixes applied (table seed includes browse signature when root is shared, storage hash upgraded to 64-bit); second `code-review` pass reported no actionable findings.
- [x] 2026-03-02 16:03:26Z Post-fix validations passed: `pytest tests/test_indexing_health_contract.py -k "workspace_id or table_workspace_id" -q` (`4 passed`), frontend targeted tests (`14 passed`), `cd frontend && npx tsc --noEmit` clean, `python scripts/lint_repo.py` pass, and frontend build+sync completed (`npm run build && rsync -a --delete dist/ ../src/lenslet/frontend/`).


## Artifacts and Handoff


Plan artifact path:

    docs/20260302_workspace_theme_favicon_execution_plan.md

Planned implementation touchpoints:

    src/lenslet/server_factory.py
    frontend/src/app/AppModeRouter.tsx
    frontend/src/app/boot/bootHealth.ts
    frontend/src/app/boot/bootTheme.ts
    frontend/src/theme/runtime.ts
    frontend/src/theme/storage.ts
    tests/test_indexing_health_contract.py
    frontend/src/app/boot/__tests__/bootHealth.test.ts
    frontend/src/theme/__tests__/runtime.test.ts
    frontend/src/theme/__tests__/storage.test.ts
    src/lenslet/frontend/index.html
    src/lenslet/frontend/assets/*

Sprint 1 handoff note (closed 2026-03-02): browse-mode workspace identity contract, boot-time theme/fav apply, runtime theming engine, and workspace-scoped persistence keying are complete and validated for the sprint scope.

Sprint 2 start note: implement shared `ThemeSettingsMenu` UI once under left-rail cog and once under mobile drawer mount, reusing Sprint 1 runtime/storage APIs without duplicating state logic.

Revision note (2026-03-02): tightened scope and validation after required subagent review to remove ambiguity and prevent overbuild while preserving robustness.
