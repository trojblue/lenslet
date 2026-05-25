# 20260304 UI Jitter Implementation Plan


## Outcome + Scope Lock


This plan implements the UI stability work in [docs/20260304_ui_jitter_review.md](/local/yada/dev/lenslet/docs/20260304_ui_jitter_review.md) so that viewer transitions, compare metadata interactions, and inspector metadata autoload no longer cause layout jitter or interaction ambiguity.

Planning baseline reference: [docs/20260303_improvement_plans.md](/local/yada/dev/lenslet/docs/20260303_improvement_plans.md). This plan follows repository guidance and intentionally narrows to jitter-review outcomes.

Goals:
1. Stabilize toolbar geometry across browse, viewer, compact, and narrow layouts, including `Back`, `Nav`, `Upload`, `Search`, and `Refresh` controls.
2. Stabilize top-stack and grid geometry when status/similarity/filter-chip visibility and metric scrollbar mode change.
3. Stabilize inspector metadata transitions with Quick View reservation and remove single-image grouping friction.
4. Improve inspector micro-interactions requested in the review, including copy affordance density and compare-table click-vs-pan priority.

Non-goals:
1. No backend, API, storage, or schema changes.
2. No dependency additions.
3. No implementation of unrelated inspector roadmap items from [docs/20260303_improvement_plans.md](/local/yada/dev/lenslet/docs/20260303_improvement_plans.md), including section drag-reorder, PNG metadata extraction, or expanded multi-image metadata compare limits.
4. No broad visual redesign outside jitter and interaction-clarity paths.

Approval matrix:
1. Pre-approved: frontend behavior and layout changes directly listed in [docs/20260304_ui_jitter_review.md](/local/yada/dev/lenslet/docs/20260304_ui_jitter_review.md), including compare-table click-vs-pan prioritization and related test updates.
2. Requires sign-off: shortcut behavior changes, removal of user-visible actions, or new dependency adoption.
3. Requires sign-off: any behavior change outside toolbar, top-stack/grid, and inspector jitter scope.

Deferred and out-of-scope:
1. Feature expansion from [docs/20260303_improvement_plans.md](/local/yada/dev/lenslet/docs/20260303_improvement_plans.md) not listed above.
2. Performance optimizations not needed to close the stated jitter paths.


## Context


Explorer subagents mapped all jitter findings to concrete frontend files and confirmed the root path is conditional mount/unmount and mode-dependent geometry changes, not backend latency or data-loading throughput.

Scope-lock decision used here: “implement them” means findings `1-7` and all additional proposals in [docs/20260304_ui_jitter_review.md](/local/yada/dev/lenslet/docs/20260304_ui_jitter_review.md), including compare metadata table click-vs-pan behavior.

Non-obvious terms:
1. Top stack means the status/error/similarity/filter-chip region above the browse grid.
2. Metric rail means the right-side area hosting metric-scrollbar UI.
3. Quick View reservation means retaining a temporary section footprint while metadata for a newly selected item is pending.

Pass/fail thresholds locked for this plan:
1. Geometry stability threshold is `<= 1 CSS px` delta for tracked anchors and reserved bands across transition checks.
2. Hidden controls must be non-interactive and not keyboard-focusable when visually suppressed.
3. Quick View reservation must not leak stale metadata from out-of-order responses.


## Plan of Work


Implementation sequence is toolbar stability first, then top-stack/grid stability, then inspector continuity and interaction polish. This keeps each sprint independently demoable and reduces cross-sprint rollback risk.

Scope budget:
1. Three sprints.
2. Twelve atomic tasks total.
3. Maximum four tasks per sprint, satisfying the requested cap of five.
4. Frontend-only module touch set.

Quality guardrails:
1. Quality floor: preserve accessibility, disabled semantics, and pointer intent clarity.
2. Maintainability floor: every task is committable with an explicit validation step.
3. Complexity ceiling: no speculative framework refactor; implement only minimal stable layout primitives.

Required implementation instructions:
1. While implementing each sprint, update this document continuously, especially `Progress Log`, `Validation and Acceptance`, and `Artifacts and Handoff`.
2. After each sprint is complete, add clear handoff notes before proceeding.
3. For minor script-level uncertainty such as exact file placement, proceed under this approved plan to maintain momentum, then ask for clarification after sprint completion and apply follow-up adjustments.

Task gate routine for every task `T1` through `T12`:
0. Plan gate (fast): restate goal, acceptance criteria, and touched files.
1. Implement gate (correctness-first): ship the smallest coherent slice and run its minimum verification signal.
2. Cleanup gate (reduce noise): run conservative cleanup at sprint boundary.
3. Review gate (ship diff review): run review on post-cleanup diff, apply fixes, rerun review if needed.

### code-simplifier routine


After each completed sprint, spawn a subagent and instruct it to use `code-simplifier` on that sprint diff only. Limit this pass to non-semantic cleanup: formatting/lint autofix, dead-code removal, small readability improvements, and comments/docs that match current behavior. Do not expand into semantic refactors without explicit approval.

### review routine


After each completed sprint and after the cleanup routine, spawn a fresh agent and run `code-review` on the post-cleanup diff. Resolve blocking findings and rerun review until the sprint’s acceptance gates are satisfied.

Sprint plan:

1. Sprint 1 goal: stabilize toolbar map and narrow-layout offsets.
   Demo outcome: viewer transitions and narrow/mobile search transitions keep anchors and overlay offsets stable.
   Tasks:
   - [x] `T1` Implement persistent toolbar slots for `Back`, `Nav`, `Upload`, `Search`, and `Refresh` in [Toolbar.tsx](/local/yada/dev/lenslet/frontend/src/shared/ui/Toolbar.tsx) with slot sizing rules in [styles.css](/local/yada/dev/lenslet/frontend/src/styles.css); validation: targeted toolbar tests pass.
   - [x] `T2` Keep compact and mobile-search footprints persistent in [Toolbar.tsx](/local/yada/dev/lenslet/frontend/src/shared/ui/Toolbar.tsx) with hide/disable states instead of mount/unmount; validation: hidden controls are not focusable and `--toolbar-h` remains stable through toggle flow.
   - [x] `T3` Stabilize dynamic widths and badge mounting in [ToolbarFilterMenu.tsx](/local/yada/dev/lenslet/frontend/src/shared/ui/toolbar/ToolbarFilterMenu.tsx), [ToolbarMobileDrawer.tsx](/local/yada/dev/lenslet/frontend/src/shared/ui/toolbar/ToolbarMobileDrawer.tsx), and [styles.css](/local/yada/dev/lenslet/frontend/src/styles.css); validation: no lateral control drift when label text and counts change.
   - [x] `T4` Add a lightweight jitter probe for toolbar geometry thresholds in `scripts/` and/or frontend test harness with explicit `<=1px` assertions for anchor and toolbar-offset transitions; validation: probe passes in local run.

2. Sprint 2 goal: stabilize top-stack and metric-mode grid geometry.
   Demo outcome: status/similarity/filter-chip transitions and builtin/metric sort toggles keep vertical and horizontal geometry stable.
   Tasks:
   - [x] `T5` Add persistent [GridTopStack.tsx](/local/yada/dev/lenslet/frontend/src/app/components/GridTopStack.tsx) and migrate top-stack rendering in [AppShell.tsx](/local/yada/dev/lenslet/frontend/src/app/AppShell.tsx) to always-mounted bands; validation: top-stack bands stay mounted while visibility toggles.
   - [x] `T6` Refactor [AppShell.tsx](/local/yada/dev/lenslet/frontend/src/app/AppShell.tsx) and [styles.css](/local/yada/dev/lenslet/frontend/src/styles.css) to use a persistent metric rail slot with stable right gutter; validation: tracked grid content width delta stays within threshold across sort-mode toggles.
   - [x] `T7` Remove `hideScrollbar` mode switching in [VirtualGrid.tsx](/local/yada/dev/lenslet/frontend/src/features/browse/components/VirtualGrid.tsx) and adapt [MetricScrollbar.tsx](/local/yada/dev/lenslet/frontend/src/features/browse/components/MetricScrollbar.tsx) to slot layout; validation: no scroll-root class flip tied to mode.
   - [x] `T8` Extend jitter probe for top-stack height and grid-width threshold checks, including large-tree fixture path as sprint-exit verification; validation: probe output and large-tree smoke output stay within accepted bounds.

3. Sprint 3 goal: stabilize inspector autoload transitions and interaction clarity.
   Demo outcome: Quick View reservation behaves deterministically, single-item grouping is simpler, and compare-table copy interactions are reliable.
   Tasks:
   - [x] `T9` Implement Quick View reservation and stale-response protection in [Inspector.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/Inspector.tsx) and [useInspectorSingleMetadata.ts](/local/yada/dev/lenslet/frontend/src/features/inspector/hooks/useInspectorSingleMetadata.ts), with an out-of-order completion test; validation: no stale Quick View hydration after rapid selection changes.
   - [x] `T10` Remove single-image `Item` section path in [OverviewSection.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/sections/OverviewSection.tsx) and [inspectorWidgets.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/inspectorWidgets.tsx), then place filename with thumbnail grouping in [Inspector.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/Inspector.tsx); validation: multi-select behavior remains unchanged.
   - [x] `T11` Relocate `Find similar` access to [BasicsSection.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/sections/BasicsSection.tsx) and [AppContextMenuItems.tsx](/local/yada/dev/lenslet/frontend/src/app/menu/AppContextMenuItems.tsx) with disabled-reason parity; validation: action visibility and disabled messaging are preserved in both entry points.
   - [x] `T12` Apply micro-tweaks in [QuickViewSection.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/sections/QuickViewSection.tsx), [BasicsSection.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/sections/BasicsSection.tsx), and [CompareMetadataSection.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/sections/CompareMetadataSection.tsx) for icon-copy, left alignment, and click-priority over pan; validation: copy clicks win on interactive cells while drag pan remains available on non-interactive gaps.


## Interfaces and Dependencies


This plan changes frontend interfaces in a limited but explicit way. [VirtualGrid.tsx](/local/yada/dev/lenslet/frontend/src/features/browse/components/VirtualGrid.tsx) will remove `hideScrollbar`, requiring callsite updates in [AppShell.tsx](/local/yada/dev/lenslet/frontend/src/app/AppShell.tsx). A new [GridTopStack.tsx](/local/yada/dev/lenslet/frontend/src/app/components/GridTopStack.tsx) component introduces a stable top-band rendering contract. Inspector action wiring depends on [AppContextMenuItems.tsx](/local/yada/dev/lenslet/frontend/src/app/menu/AppContextMenuItems.tsx) and existing selection/embedding state from [AppShell.tsx](/local/yada/dev/lenslet/frontend/src/app/AppShell.tsx). No backend interface changes are planned.


## Validation and Acceptance


Primary acceptance gates (real scenario):
1. Sprint 1 toolbar geometry gate.
   Commands:
      cd frontend && npm run test -- src/shared/ui/toolbar/__tests__/Toolbar.test.tsx src/shared/ui/toolbar/__tests__/ToolbarMobileDrawer.test.tsx
      python scripts/gui_jitter_probe.py --scenario toolbar --max-delta-px 1
   Expected outcome: anchor deltas and toolbar-offset deltas are `<=1px`, and hidden controls remain non-focusable.
   Execution result (2026-03-04 17:42 UTC): passed. Probe artifact: [docs/ralph/20260304_ui_jitter_implementation/toolbar_probe_iteration1.json](/local/yada/dev/lenslet/docs/ralph/20260304_ui_jitter_implementation/toolbar_probe_iteration1.json). Reported `max_anchor_delta_px=0.0`, `max_toolbar_delta_px=0.0`.
2. Sprint 2 grid geometry gate.
   Commands:
      python scripts/gui_jitter_probe.py --scenario grid --max-delta-px 1
      python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json
   Expected outcome: top-stack height and grid-width deltas are `<=1px` in the probe; no major regression in large-tree smoke output versus current baseline.
   Execution result (2026-03-04 18:43 UTC): passed.
   - `cd frontend && npm run test -- src/app/components/__tests__/GridTopStack.test.tsx src/app/components/__tests__/StatusBar.test.tsx` -> passed (8 tests).
   - `python scripts/gui_jitter_probe.py --scenario grid --max-delta-px 1 --output-json docs/ralph/20260304_ui_jitter_implementation/grid_probe_iteration2.json` -> passed (`max_top_stack_delta_px=0.0`, `max_grid_width_delta_px=0.0`), with metric-rail activation and metric sort persistence asserted.
   - `python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json data/fixtures/large_tree_40k_smoke_result.json` -> passed (`first-grid=4.83s` on final run; one earlier run in this iteration measured `5.17s` and failed threshold).
   - `python scripts/lint_repo.py` -> passed.
3. Sprint 3 inspector continuity and compare interaction gate.
   Commands:
      cd frontend && npm run test -- src/features/inspector/sections/__tests__/metadataSections.test.tsx src/features/inspector/model/__tests__/quickViewFields.test.ts src/app/menu/__tests__/AppContextMenuItems.test.tsx
      python scripts/gui_jitter_probe.py --scenario inspector --max-delta-px 1
   Expected outcome: no stale reservation hydration, section footprint follows reservation rules, and compare-table interactive-cell click-to-copy is reliable while gap drag still pans.
   Execution result (2026-03-04 19:19 UTC): passed.
   - `cd frontend && npm run test -- src/features/inspector/sections/__tests__/metadataSections.test.tsx src/features/inspector/model/__tests__/quickViewFields.test.ts src/features/inspector/model/__tests__/findSimilarAvailability.test.ts src/features/inspector/hooks/__tests__/useInspectorSingleMetadata.test.ts src/app/menu/__tests__/AppContextMenuItems.test.tsx` -> passed (31 tests).
   - `python scripts/gui_jitter_probe.py --scenario inspector --max-delta-px 1 --output-json docs/ralph/20260304_ui_jitter_implementation/inspector_probe_iteration3.json` -> passed (`max_inspector_delta_px=0.828125`) with stale-response and quick-to-plain reservation-clear checks asserted.
4. Final end-to-end gate after Sprint 3.
   Commands:
      cd frontend && npm run build
      python scripts/lint_repo.py
      python scripts/gui_smoke_acceptance.py
   Expected outcome: build, lint, and GUI smoke checks pass without regressions.
   Execution result (2026-03-04 19:19 UTC): passed.
   - `cd frontend && npm run build` -> passed.
   - `python scripts/lint_repo.py` -> passed (existing file-size warnings only).
   - `python scripts/gui_smoke_acceptance.py` -> passed.

Secondary acceptance gates (fast proxy):
1. Run task-scoped unit tests before each task completion and keep failures at zero.
2. Run `python scripts/lint_repo.py` at each sprint exit.
3. Verify jitter probe JSON artifacts are emitted and archived in sprint handoff notes.
   Sprint 1 execution result (2026-03-04 17:43 UTC): `python scripts/lint_repo.py` passed after sprint changes.


## Risks and Recovery


Hidden dependencies include CSS variable coupling around `--toolbar-h`, focus-order behavior for hidden-but-mounted controls, and grid measurement sensitivity to scroll-root class and gutter changes. Inspector reservation logic has race risk under rapid selection changes and out-of-order metadata completion.

Recovery strategy is sprint-scoped and idempotent. If any primary gate fails, the sprint stays open and only closure work for that gate is added until pass. Each task remains an atomic commit unit so partial rollback is straightforward and does not require reverting unrelated sprint work.

Rollback path is frontend-only. Revert failing task commit(s), rerun that sprint’s gate commands, and restore prior stable behavior before re-attempting the task with a reduced change set.


## Progress Log


- [x] 2026-03-04 17:00 UTC: Reviewed [docs/20260304_ui_jitter_review.md](/local/yada/dev/lenslet/docs/20260304_ui_jitter_review.md) and locked target scope.
- [x] 2026-03-04 17:08 UTC: Gathered implementation mapping using explorer subagents for toolbar, grid/top-stack, and inspector tracks.
- [x] 2026-03-04 17:20 UTC: Ran required subagent plan critique and incorporated feedback on missing scope items, objective thresholds, and task sizing.
- [x] 2026-03-04 17:30 UTC: Completed `T1` and `T2` in [Toolbar.tsx](/local/yada/dev/lenslet/frontend/src/shared/ui/Toolbar.tsx) with persistent slots and hidden/non-focusable state wiring.
- [x] 2026-03-04 17:35 UTC: Completed `T3` in [ToolbarFilterMenu.tsx](/local/yada/dev/lenslet/frontend/src/shared/ui/toolbar/ToolbarFilterMenu.tsx), [ToolbarMobileDrawer.tsx](/local/yada/dev/lenslet/frontend/src/shared/ui/toolbar/ToolbarMobileDrawer.tsx), and [styles.css](/local/yada/dev/lenslet/frontend/src/styles.css) for stable dynamic widths and badge mounting.
- [x] 2026-03-04 17:42 UTC: Completed `T4` by adding [scripts/gui_jitter_probe.py](/local/yada/dev/lenslet/scripts/gui_jitter_probe.py) and recording toolbar probe artifact [docs/ralph/20260304_ui_jitter_implementation/toolbar_probe_iteration1.json](/local/yada/dev/lenslet/docs/ralph/20260304_ui_jitter_implementation/toolbar_probe_iteration1.json).
- [x] 2026-03-04 17:43 UTC: Ran sprint cleanup/review routines (`code-simplifier`, `code-review`), resolved hidden-row pointer-events finding, and re-validated sprint gates.
- [x] 2026-03-04 18:12 UTC: Completed `T5`, `T6`, and `T7` across [GridTopStack.tsx](/local/yada/dev/lenslet/frontend/src/app/components/GridTopStack.tsx), [AppShell.tsx](/local/yada/dev/lenslet/frontend/src/app/AppShell.tsx), [VirtualGrid.tsx](/local/yada/dev/lenslet/frontend/src/features/browse/components/VirtualGrid.tsx), [MetricScrollbar.tsx](/local/yada/dev/lenslet/frontend/src/features/browse/components/MetricScrollbar.tsx), and [styles.css](/local/yada/dev/lenslet/frontend/src/styles.css), including persistent top-stack bands and persistent metric rail slot layout.
- [x] 2026-03-04 18:36 UTC: Completed `T8` by extending [scripts/gui_jitter_probe.py](/local/yada/dev/lenslet/scripts/gui_jitter_probe.py) with `grid` scenario assertions, deterministic metric-fixture generation, and dynamic metric option detection for user datasets; recorded artifact [docs/ralph/20260304_ui_jitter_implementation/grid_probe_iteration2.json](/local/yada/dev/lenslet/docs/ralph/20260304_ui_jitter_implementation/grid_probe_iteration2.json).
- [x] 2026-03-04 18:41 UTC: Ran sprint cleanup/review routines (`code-simplifier`, `code-review`) on Sprint 2 diff and fixed the high-severity reservation bug by allowing hidden-band reserve heights to shrink to latest measured height.
- [x] 2026-03-04 18:43 UTC: Re-ran Sprint 2 acceptance gates (targeted tests, grid jitter probe, large-tree smoke, lint) and confirmed pass.
- [x] 2026-03-04 19:05 UTC: Completed `T9` and `T12` by adding context-projected single-metadata state, Quick View reservation placeholders with stable geometry, icon-copy controls, compare copy-target gating over pan, and an inspector jitter probe scenario with fixture-backed stale/transition checks in [scripts/gui_jitter_probe.py](/local/yada/dev/lenslet/scripts/gui_jitter_probe.py).
- [x] 2026-03-04 19:09 UTC: Completed `T10` and `T11` by making overview multi-select only, grouping filename with thumbnail in [Inspector.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/Inspector.tsx), and relocating `Find similar` to [BasicsSection.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/sections/BasicsSection.tsx) plus [AppContextMenuItems.tsx](/local/yada/dev/lenslet/frontend/src/app/menu/AppContextMenuItems.tsx) using shared disabled-reason logic.
- [x] 2026-03-04 19:18 UTC: Ran sprint cleanup/review routines (`code-simplifier`, `code-review`), fixed follow-up findings (context-menu close on `Find similar`, canonical compare-path copy payload), and revalidated.
- [x] 2026-03-04 19:19 UTC: Re-ran Sprint 3 acceptance gates (targeted tests, inspector jitter probe, build, lint, GUI smoke) and confirmed pass.
- [x] Sprint 1 complete.
- [x] Sprint 2 complete.
- [x] Sprint 3 complete.


## Artifacts and Handoff


Planning artifacts include [docs/20260304_ui_jitter_review.md](/local/yada/dev/lenslet/docs/20260304_ui_jitter_review.md), this implementation plan, and four subagent outputs (three implementation mapping reports plus one required plan critique). These artifacts provide enough implementation context to start `T1` immediately.

Sprint 1 handoff notes:
1. Toolbar control map is now slot-stable across browse/viewer/narrow transitions. Hidden controls are disabled, `tabindex=-1`, and `aria-hidden=true`.
2. Mobile search row remains mounted on narrow layouts with stable geometry; closed state now uses `pointer-events: none` to avoid inert hitbox interception.
3. Toolbar jitter probe lives in [scripts/gui_jitter_probe.py](/local/yada/dev/lenslet/scripts/gui_jitter_probe.py) (currently `--scenario toolbar`), with sprint artifact output captured at [docs/ralph/20260304_ui_jitter_implementation/toolbar_probe_iteration1.json](/local/yada/dev/lenslet/docs/ralph/20260304_ui_jitter_implementation/toolbar_probe_iteration1.json).

Sprint 2 handoff notes:
1. Top-stack rendering is now centralized in [GridTopStack.tsx](/local/yada/dev/lenslet/frontend/src/app/components/GridTopStack.tsx), with persistent mounted `status`, `similarity`, and `filters` bands and measured reserve behavior.
2. Grid body layout now always mounts a right metric rail slot in [AppShell.tsx](/local/yada/dev/lenslet/frontend/src/app/AppShell.tsx) and [styles.css](/local/yada/dev/lenslet/frontend/src/styles.css), so builtin/metric sort toggles keep body width stable.
3. `hideScrollbar` mode switching is removed from [VirtualGrid.tsx](/local/yada/dev/lenslet/frontend/src/features/browse/components/VirtualGrid.tsx); [MetricScrollbar.tsx](/local/yada/dev/lenslet/frontend/src/features/browse/components/MetricScrollbar.tsx) now renders as slot content.
4. Grid jitter probe output is captured at [docs/ralph/20260304_ui_jitter_implementation/grid_probe_iteration2.json](/local/yada/dev/lenslet/docs/ralph/20260304_ui_jitter_implementation/grid_probe_iteration2.json); large-tree smoke output refreshed at `data/fixtures/large_tree_40k_smoke_result.json`.

Sprint 3 handoff notes:
1. Quick View reservation and stale-response protection now run through [useInspectorSingleMetadata.ts](/local/yada/dev/lenslet/frontend/src/features/inspector/hooks/useInspectorSingleMetadata.ts) context projection plus reservation logic in [Inspector.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/Inspector.tsx), with out-of-order projection coverage in [useInspectorSingleMetadata.test.ts](/local/yada/dev/lenslet/frontend/src/features/inspector/hooks/__tests__/useInspectorSingleMetadata.test.ts).
2. Single-image inspector flow no longer renders Overview; filename is grouped with the thumbnail and `Find similar` lives in [BasicsSection.tsx](/local/yada/dev/lenslet/frontend/src/features/inspector/sections/BasicsSection.tsx) and [AppContextMenuItems.tsx](/local/yada/dev/lenslet/frontend/src/app/menu/AppContextMenuItems.tsx), driven by shared availability logic in [findSimilarAvailability.ts](/local/yada/dev/lenslet/frontend/src/features/inspector/model/findSimilarAvailability.ts).
3. Inspector jitter probe now supports `--scenario inspector` in [scripts/gui_jitter_probe.py](/local/yada/dev/lenslet/scripts/gui_jitter_probe.py) with artifact [docs/ralph/20260304_ui_jitter_implementation/inspector_probe_iteration3.json](/local/yada/dev/lenslet/docs/ralph/20260304_ui_jitter_implementation/inspector_probe_iteration3.json).

Revision note (2026-03-04 17:24 UTC): incorporated subagent critique by explicitly covering refresh-slot and compare click-vs-pan scope, splitting inspector simplification work into atomic tasks, replacing verification-bundle tasks with sprint-exit gates, and adding measurable `<=1px` jitter thresholds with explicit probe requirements.
