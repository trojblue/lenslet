# 20260303 Inspector Behavior and Metadata Improvements Execution Plan


## Outcome + Scope Lock


After implementation, users can keep the left icon rail visible while collapsing only the active left content panel, toggle collapse directly by clicking the active `Folder` or `Metrics` tab, resize the right inspector substantially wider, reorder inspector sections with drag-and-drop, compare metadata for multi-selection directly in the inspector, auto-show comparison when `Auto Load Image Meta` is enabled, compare up to six images in a structured table, see GIF mode limits via `Export GIF` hover tooltip instead of persistent inline text, and use a PNG quick-view section with clickable copy actions plus configurable JSON field paths.

Goals are to deliver these ten requested behavior changes as small, testable increments without new dependencies or broad rewrites. Non-goals are redesigning side-by-side viewing beyond two-image visual compare, increasing compare-export limits, changing ranking mode behavior, or adding backward-compatibility shims.

Approvals are locked as follows.

Pre-approved behavior changes are left panel interaction changes, inspector ordering and drag reorder persistence, six-item metadata compare cap, autoload-triggered compare behavior, GIF notice relocation to tooltip, and additive PNG quick-view extraction/display fields.

Requires sign-off are any new backend routes, any breaking removal/rename of existing metadata response keys, side-by-side viewer architecture changes, or new third-party dependencies.

Deferred and out-of-scope work includes compare of more than six selected images, remote/shared persistence of quick-view field preferences, semantic fuzzy metadata matching, and broad inspector visual redesign.

User-requested sprint shape is enforced: each sprint closes at most four small tasks, and work is intentionally spread across multiple sprints instead of compressed.


## Context


`docs/20260303_improvement_plans.md` defines ten concrete inspector and metadata improvements. Explorer subagents reviewed repository seams and identified primary touchpoints in `frontend/src/app/AppShell.tsx`, `frontend/src/app/components/LeftSidebar.tsx`, `frontend/src/lib/breakpoints.ts`, `frontend/src/app/layout/useSidebars.ts`, `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/inspector/inspectorWidgets.tsx`, inspector metadata hooks/model/sections, and `src/lenslet/metadata.py`.

Current constraints to remove are left-sidebar all-or-nothing collapse semantics, metadata compare coupling to side-by-side state, two-image compare assumptions, persistent inline GIF notice copy, and fixed inspector section order.

No `PLANS.md` or equivalent top-level plan contract file was found in this repository. This document is the execution source of truth and follows AGENTS.md plus the provided `plan-writer` requirements.

Scope-lock decisions applied from available context are that default order should place Metadata above Basics, right-inspector widening is accepted only if measurable thresholds are met, over-cap compare truncation uses first-six selection order with explicit `+N not shown`, and custom quick-view path syntax is intentionally strict (`dot` and `[index]` only) to prevent parser bloat.


## Interfaces and Dependencies


No new runtime dependency is planned. Drag reorder uses existing `@dnd-kit` packages already present in the frontend ranking feature.

The backend metadata route remains `/metadata` with additive fields only. `src/lenslet/metadata.py` adds derived `quick_view_defaults` values (`prompt`, `model`, `lora`) from PNG metadata (notably `qfty_meta`) while preserving current keys.

Frontend persistence adds additive local keys for inspector section order and quick-view custom field paths. Existing open/closed section persistence remains intact.


## Plan of Work


Implementation proceeds in six sprints with twenty-four atomic tasks. Each sprint is demoable, runnable, and testable.

Scope budget intentionally exceeds the default plan-writer baseline because the requested scope covers ten separate behaviors and the user explicitly requested many small sprints. Budget is capped at six sprints, twenty-four tasks, and only the modules required for requested outcomes.

Quality guardrails are minimum-robust: preserve correctness and failure handling first, maintain readability and focused tests second, and reject speculative abstractions or future-proofing work with no direct outcome value.

Implementation instruction: while implementing each sprint, update this plan continuously, especially Progress Log and affected validation/handoff sections. After each sprint completes, add explicit sprint handoff notes before starting the next sprint.

Implementation instruction: for minor script-level uncertainties (for example exact helper file placement), proceed according to this approved plan to maintain momentum; after the sprint, ask for clarification and apply focused follow-up adjustments. For user-visible ambiguity (for example truncation order semantics, tooltip copy, or path syntax behavior), clarify before implementation of that task.

Each task follows this gate routine.

0) Plan gate (fast): restate goal, acceptance criteria, and files to touch before coding.

1) Implement gate (correctness-first): implement the smallest coherent slice that satisfies the ticket, then run targeted verification.

2) Cleanup gate (reduce noise before review): after each complete sprint, run code-simplifier routine.

3) Review gate (review the ship diff): after cleanup, run review routine and close findings before sprint closure.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill against the sprint diff. Keep this pass conservative and non-semantic first: formatting/lint autofixes, obvious dead code removal, small readability edits, and doc/comment updates that reflect current behavior. Do not expand into semantic refactors unless explicitly approved.

### review routine


After the cleanup subagent finishes, spawn a fresh subagent and request review using the `code-review` skill on the post-cleanup diff. Apply fixes and rerun review when needed until findings are resolved or explicitly accepted with rationale.

### Sprint Plan


1. Sprint 1 goal is left/right inspector layout behavior corrections. Demo outcome is left rail always visible when left content is collapsed, active-tab click collapse works, and right inspector can be widened to a measurable target.

   T1. [x] Split left rail visibility from left content expansion in `AppShell` and `LeftSidebar` so collapse preserves rail and hides only active large panel. Completed 2026-03-03.
   Validation: targeted behavior test for `Ctrl+B`, toolbar toggle, and computed `--left` width behavior.

   T2. [x] Replace raw `setLeftTool` wiring with active-tab toggle handler so clicking active `Folder` or `Metrics` collapses/expands content predictably. Completed 2026-03-03.
   Validation: focused component interaction test for active vs inactive tab clicks.

   T3. [x] Separate left/right width clamp policies and raise right inspector max with explicit desktop target: at 1440px viewport, right inspector max width must reach at least 560px while center content remains at least 520px. Completed 2026-03-03.
   Validation: `breakpoints` and `useSidebars` tests covering numeric thresholds and center safety.

   T4. [x] Add Sprint 1 UI acceptance coverage for left-panel collapse and right resize behavior to Playwright smoke flow. Completed 2026-03-03.
   Validation: `python scripts/gui_smoke_acceptance.py` includes and passes the new checks.

2. Sprint 2 goal is reorderable inspector sections with updated defaults. Demo outcome is drag reorder persistence across reload, with default order moving Metadata above Basics.

   T5. [x] Define canonical widget-order model and default order list in inspector model/widgets, including stable IDs for all sections. Completed 2026-03-03.
   Validation: `inspectorWidgetOrder` model tests verify default order, stable IDs, and sanitize behavior.

   T6. [x] Add persistent section order storage key `lenslet.inspector.sectionOrder.v2` with sanitize logic (dedupe/remove unknown/append missing). Completed 2026-03-03.
   Validation: persisted-order parsing tests verify stale/invalid payloads self-heal to canonical order.

   T7. [x] Add drag-and-drop reorder affordance in `InspectorSection`/`Inspector` using existing dnd-kit while preserving click-to-toggle behavior. Completed 2026-03-03.
   Validation: interaction/state test confirms reorder and section-toggle state coexist without coupling.

   T8. [ ] Add reload persistence acceptance test path in Playwright smoke for reordered section sequence. Blocked 2026-03-03.
   Validation: blocked by existing `python scripts/gui_smoke_acceptance.py` flake in the multi-select step (`[role='gridcell']` second-cell click timeout) before reorder assertions execute.

3. Sprint 3 goal is explicit metadata compare state ownership and multi-select activation. Demo outcome is metadata compare works independently from side-by-side viewer state and autoload can activate compare for multi-select.

   T9. Introduce dedicated `metadataCompareActive` ownership in inspector state, separate from viewer `compareOpen`, with clear wiring boundaries.
   Validation: state tests proving metadata compare toggles do not alter side-by-side mode.

   T10. Add explicit inspector metadata compare action for `selectedCount >= 2` and decouple compare section visibility from side-by-side gating.
   Validation: section tests proving compare appears from inspector action without side-by-side.

   T11. Remove multi-selection autoload suppression and auto-activate metadata compare when autoload is ON and `selectedCount >= 2`.
   Validation: hook tests for autoload ON/OFF behavior across 1, 2, and 3 selections.

   T12. Add regression tests for browser back/popstate behavior and side-by-side flow stability after compare-state split.
   Validation: targeted tests around history transitions and compare viewer unaffected behavior.

4. Sprint 4 goal is complete six-item metadata compare engine and table UI. Demo outcome is structured comparison for 2..6 images with deterministic over-cap behavior.

   T13. Refactor compare request/guard logic from two-path to list-based flow with `MAX_INSPECTOR_COMPARE_PATHS = 6` and deterministic first-six truncation.
   Validation: request-guard tests for stable keys and reload behavior at 2..6 items.

   T14. Replace pairwise compare model with N-way row matrix model plus summary outputs (differences, missing values, truncation notice).
   Validation: model tests for mixed metadata shapes and stable row ordering.

   T15. Build table-oriented `CompareMetadataSection` with sticky key column and horizontal overflow handling for six columns.
   Validation: component tests for multi-column rendering and sticky key semantics.

   T16. Add over-cap message behavior (`+N not shown`) and Playwright smoke coverage for selecting 7 items.
   Validation: `python scripts/gui_smoke_acceptance.py` verifies over-cap messaging path.

5. Sprint 5 goal is GIF notice relocation and backend PNG quick-view defaults. Demo outcome is no persistent GIF notice line and backend provides stable quick-view defaults.

   T17. Move GIF mode explanatory text from persistent inline block to hover tooltip on `Export GIF`, including disabled-state tooltip behavior.
   Validation: section tests confirming inline notice removal and tooltip text for standard/high-quality modes.

   T18. Extend PNG metadata parsing in `src/lenslet/metadata.py` to derive `quick_view_defaults.prompt/model/lora` from `qfty_meta` and fallbacks.
   Validation: parser tests for primary and fallback extraction paths.

   T19. Extend metadata endpoint tests to assert additive quick-view defaults, including fixture coverage using `docs/test_meta.png`.
   Validation: `pytest tests/test_metadata_endpoint.py -q` plus targeted parser tests pass.

   T20. Add backend-forward compatibility guard so missing/invalid quick-view defaults return safe empty values without endpoint failure.
   Validation: negative parser tests for malformed metadata payloads.

6. Sprint 6 goal is PNG quick-view frontend UX and final integration closure. Demo outcome is top-positioned quick-view section with clickable copy and configurable JSON paths, fully integrated with reorder and acceptance gates.

   T21. Add PNG Quick View section for single-selection autoload metadata with default rows `Prompt`, `Model`, `LoRA` and click-to-copy interactions.
   Validation: section tests for render/copy feedback and hidden-state behavior when prerequisites are unmet.

   T22. Add custom quick-view JSON field configuration with strict supported syntax (`dot` and `[index]` only), persistence, and invalid-path rejection messaging.
   Validation: model/state tests for parse, persistence reload, and rejection behavior.

   T23. Integrate Quick View into section-order persistence with one-time migration rule so existing persisted orders place Quick View at top when first introduced.
   Validation: migration test with preexisting `sectionOrder.v2` data and reload confirmation.

   T24. Run final acceptance sweep, update this plan’s progress/handoff notes, and synchronize docs for shipped behavior.
   Validation: primary gates pass, targeted tests pass, `python scripts/lint_repo.py` passes, and `python scripts/gui_smoke_acceptance.py` passes.


## Validation and Acceptance


Validation hierarchy is explicit: primary gates prove user-facing outcomes in realistic interaction paths, and secondary gates provide fast regression proxies.

Primary acceptance gates by sprint:

1. Sprint 1 primary gate: on desktop browse mode, `Hide Left Panel` and `Ctrl+B` collapse only left content while icon rail remains visible; clicking active `Folder` or `Metrics` toggles collapse; at 1440px viewport, right inspector reaches at least 560px max while center remains at least 520px.

2. Sprint 2 primary gate: user drags section order, reloads, and sees order preserved. Clean-storage default order places Metadata before Basics.

3. Sprint 3 primary gate: with autoload OFF and 3 selected images, inspector compare action opens metadata compare; with autoload ON and 3 selected images, compare appears automatically; side-by-side viewer state remains unaffected.

4. Sprint 4 primary gate: selecting 6 images shows six-column compare table; selecting 7 shows six compared plus `+1 not shown` indicator.

5. Sprint 5 primary gate: GIF mode copy is absent from persistent inspector body and present as `Export GIF` tooltip; metadata endpoint includes additive quick-view defaults for supported PNG metadata.

6. Sprint 6 primary gate: PNG Quick View appears in single-select autoload context, values copy correctly, custom field paths persist across reload, and first-time migration places Quick View at top for users with older saved order data.

Secondary acceptance gates and commands:

1. Frontend targeted inspector/layout tests.

    cd frontend && npm run test -- src/lib/__tests__/breakpoints.test.ts src/app/layout/__tests__/useSidebars.test.ts src/features/inspector/hooks/__tests__/metadataRequestGuards.test.ts src/features/inspector/model/__tests__/metadataCompare.test.ts src/features/inspector/sections/__tests__/metadataSections.test.tsx

2. Backend metadata tests.

    pytest tests/test_metadata_endpoint.py -q

3. Type safety check.

    cd frontend && npx tsc --noEmit

4. Frontend build and shipping bundle sync.

    cd frontend && npm run build && rsync -a --delete dist/ ../src/lenslet/frontend/

5. Repository lint/file-size guardrail.

    python scripts/lint_repo.py

6. End-to-end GUI smoke with newly added inspector scenarios.

    python scripts/gui_smoke_acceptance.py

Expected acceptance outcome is all primary gates logged as pass/fail with concrete notes and all secondary commands passing before final closure.

Sprint 1 execution notes (2026-03-03):

1. Primary gate result: pass. Desktop smoke run confirmed left rail persists when collapsed, active tab clicks toggle left content, and at 1440px viewport right inspector reached 605px while center remained 595px.
2. Targeted frontend tests: `cd frontend && npm run test -- src/app/layout/__tests__/sidebarLayout.test.ts src/app/layout/__tests__/useSidebars.test.ts src/lib/__tests__/breakpoints.test.ts` passed (19 tests).
3. Type safety gate: `cd frontend && npx tsc --noEmit` passed.
4. Shipping bundle sync: `cd frontend && npm run build && rsync -a --delete dist/ ../src/lenslet/frontend/` passed and updated packaged UI assets.
5. GUI smoke gate: `python scripts/gui_smoke_acceptance.py` passed with new Sprint 1 checks.
6. Repository lint gate: `python scripts/lint_repo.py` passed.

Sprint 2 execution notes (2026-03-03):

1. `T5` + `T6` pass: introduced canonical inspector widget order model (`Metadata` above `Basics`) and persisted sanitize/self-heal path for `lenslet.inspector.sectionOrder.v2`.
2. `T7` pass: added dnd-kit reorder handles on inspector section headers, wired sortable ordering in `Inspector`, and preserved title-button collapse toggles.
3. Targeted frontend gates passed: `npm run test` for inspector model/section tests, `npx tsc --noEmit`, `npm run build && rsync -a --delete dist/ ../src/lenslet/frontend/`, and `python scripts/lint_repo.py`.
4. `T8` blocked: existing Playwright smoke harness fails before reorder checks during the preexisting two-item multi-select action (`[role='gridcell']` second-cell click timeout). Reorder persistence smoke path is deferred until this harness instability is stabilized.


## Risks and Recovery


Highest risk is regression from splitting metadata-compare state ownership away from side-by-side viewer state. Recovery is explicit state boundary tasking in Sprint 3 plus back/popstate and side-by-side regression tests before Sprint 3 closure.

Second risk is compare-table usability/performance at six columns. Recovery is deterministic cap, sticky key column, overflow support, and Playwright validation for 7-selection over-cap behavior.

Third risk is PNG metadata variability across generators. Recovery is additive fallback extraction, strict quick-view path syntax limits, malformed-metadata tests, and safe empty-state behavior.

Fourth risk is Playwright smoke instability in the existing multi-select interaction path, which currently blocks Sprint 2 `T8` acceptance expansion. Recovery is to stabilize deterministic multi-select in `scripts/gui_smoke_acceptance.py` first, then add reorder-reload assertions as a focused follow-up.

Rollback path is sprint-scoped revert in reverse order, preserving completed prior sprint behavior. Because each sprint is atomic and validated, rollback can target one sprint without full feature removal.

Idempotent retry strategy is rerunning failed sprint gates with the same commands; storage sanitize/migration and additive metadata fields are deterministic and safe under repeated execution.


## Progress Log


- [x] 2026-03-03 17:28:52Z Read `docs/20260303_improvement_plans.md` and extracted ten requested improvements.
- [x] 2026-03-03 17:28:52Z Spawned three explorer subagents to gather file-level implementation details for all item clusters.
- [x] 2026-03-03 17:28:52Z Consolidated explorer outputs into sprint-ready scope and module touchpoints.
- [x] 2026-03-03 17:28:52Z Drafted initial concrete six-sprint plan with gate routines and acceptance structure.
- [x] 2026-03-03 17:34:38Z Ran mandatory plan-review subagent with required verbatim prompt.
- [x] 2026-03-03 17:34:38Z Incorporated review findings: explicit compare-state ownership, measurable width targets, quick-view order migration rule, split oversized tasks, expanded Playwright acceptance paths, and strict custom-path de-scope.
- [x] 2026-03-03 17:41:40Z Sprint 1 plan gate restated with Sprint 1-only scope (`T1`..`T4`) and unchanged non-goals.
- [x] 2026-03-03 17:45:20Z Completed `T1` + `T2`: added left rail/content split, active-tab collapse/expand behavior, and explicit keyboard/toolbar toggle helpers with targeted tests.
- [x] 2026-03-03 17:46:20Z Completed `T3`: introduced asymmetric left/right constraint policy, exported shared center-width floor logic, and updated clamp tests for numeric thresholds.
- [x] 2026-03-03 17:47:30Z Completed `T4`: expanded Playwright smoke to validate rail-preserving collapse, active-tab toggles, `Ctrl+B` reopen, and 1440px right-width/center-width thresholds.
- [x] 2026-03-03 17:48:20Z Ran Sprint 1 targeted validations: focused Vitest suite passed, frontend build+bundle sync completed, GUI smoke passed, `tsc --noEmit` passed, and `python scripts/lint_repo.py` passed.
- [x] 2026-03-03 17:48:40Z Sprint 1 closed; handoff notes and artifact list updated for Sprint 2 start.
- [x] 2026-03-03 18:12:00Z Sprint 2 plan gate restated with Sprint 2-only scope (`T5`..`T8`) and unchanged non-goals.
- [x] 2026-03-03 18:18:00Z Completed `T5` + `T6`: added canonical inspector widget order model (`Metadata` before `Basics`) and persisted order sanitize/self-heal for `lenslet.inspector.sectionOrder.v2`.
- [x] 2026-03-03 18:22:00Z Completed `T7`: integrated dnd-kit sortable section handles in `InspectorSection`/`Inspector` while preserving section toggle behavior.
- [x] 2026-03-03 18:31:02Z Ran Sprint 2 targeted validations: inspector model/section Vitest suite passed, `npx tsc --noEmit` passed, frontend build+bundle sync passed, and `python scripts/lint_repo.py` passed.
- [ ] 2026-03-03 18:34:00Z `T8` blocked: `python scripts/gui_smoke_acceptance.py` fails in preexisting two-item multi-select step (`[role='gridcell']` second-cell click timeout) before reorder assertions can run.


## Artifacts and Handoff


Plan artifact path:

    docs/20260303_inspector_metadata_improvements_execution_plan.md

Primary planned touchpoints:

    frontend/src/app/AppShell.tsx
    frontend/src/app/components/LeftSidebar.tsx
    frontend/src/app/layout/sidebarLayout.ts
    frontend/src/app/layout/__tests__/sidebarLayout.test.ts
    frontend/src/app/layout/__tests__/useSidebars.test.ts
    frontend/src/lib/breakpoints.ts
    frontend/src/lib/__tests__/breakpoints.test.ts
    frontend/src/app/layout/useSidebars.ts
    frontend/src/features/inspector/Inspector.tsx
    frontend/src/features/inspector/inspectorWidgets.tsx
    frontend/src/features/inspector/hooks/useInspectorUiState.ts
    frontend/src/features/inspector/hooks/useInspectorMetadataWorkflow.ts
    frontend/src/features/inspector/hooks/useInspectorCompareMetadata.ts
    frontend/src/features/inspector/hooks/metadataRequestGuards.ts
    frontend/src/features/inspector/model/metadataCompare.ts
    frontend/src/features/inspector/model/inspectorWidgetOrder.ts
    frontend/src/features/inspector/model/__tests__/inspectorWidgetOrder.test.ts
    frontend/src/features/inspector/sections/InspectorSection.tsx
    frontend/src/features/inspector/sections/CompareMetadataSection.tsx
    frontend/src/features/inspector/sections/SelectionActionsSection.tsx
    frontend/src/features/inspector/sections/SelectionExportSection.tsx
    src/lenslet/metadata.py
    tests/test_metadata_endpoint.py
    scripts/gui_smoke_acceptance.py

Sprint 1 handoff notes (closed 2026-03-03):

1. Left panel now treats `leftOpen` as content visibility while preserving a desktop icon rail fallback width (`48px`) when collapsed.
2. Active `Folder`/`Metrics` tab clicks toggle collapse/expand; inactive-tab clicks switch tool and force content open.
3. Sidebar constraints now use asymmetric desktop maxima (left conservative, right wide) with shared center-floor logic; desktop right inspector target is validated in both unit and Playwright coverage.
4. Playwright smoke now asserts Sprint 1 primary behavior gates and emits measured widths in JSON summary payload.
5. Packaged frontend assets were rebuilt and synced to `src/lenslet/frontend/` after Sprint 1 changes.
6. Next actionable sprint is Sprint 2 (`T5`..`T8`) with no open blockers from Sprint 1.

Sprint 2 handoff notes (in progress 2026-03-03):

1. `T5`..`T7` are complete: canonical order model, persisted order sanitize/self-heal, and inspector drag-reorder affordance are implemented with targeted test coverage.
2. Default inspector order now places `Metadata` above `Basics` and persisted order uses `lenslet.inspector.sectionOrder.v2`.
3. Section header drag handles are explicit (`Reorder <Section Title>`) and do not override title-button collapse toggles.
4. Sprint 2 is not closed because `T8` remains blocked by a preexisting Playwright smoke flake in the multi-select interaction path.
5. Next actionable task is to stabilize deterministic multi-select in `scripts/gui_smoke_acceptance.py`, then add and validate reorder-reload persistence assertions.

Execution handoff note for the next operator is to implement strictly sprint-by-sprint, preserve each sprint as independently demoable and reviewable, and keep this plan as the authoritative running log of decisions, validations, and closure state.

Revision note (2026-03-03): revised after required subagent review to remove ambiguity and over-compression by adding explicit state ownership, measurable acceptance criteria, migration handling, tighter de-scoping, and fuller primary acceptance coverage.
