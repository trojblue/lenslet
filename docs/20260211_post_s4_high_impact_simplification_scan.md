# Post-S7 High-Impact Simplification Plan (Updated from Post-S4 Scan)


## Purpose / Big Picture


This document replaces the earlier post-S4 scan with a post-S7, post-sprints-21-36 cleanup plan that reflects current code reality. After this plan is implemented, the frontend refactor will be structurally cleaner: Inspector responsibilities will be split into clearer boundaries, metadata rendering will be safer and easier to evolve, AppShell filter-chip behavior will be declarative, and residual legacy/dead code paths will be removed.

Users should see unchanged product behavior, but maintainers should see lower change risk and faster local reasoning. The easiest observable proof will be that each targeted area has smaller, testable ownership units and that editing one unit no longer requires touching unrelated state orchestration.

This repository does not currently contain a `PLANS.md`-style canonical planning file. This file is therefore the canonical execution plan for this specific cleanup pass.


## Progress


- [x] 2026-02-12T02:09:28Z Re-audited the last three commits (`793f35e`, `cf74e87`, `b61ee83`) and current file state for `AppShell`, `Inspector`, and `Metrics` domains.
- [x] 2026-02-12T02:09:28Z Removed outdated findings that were already addressed during S4-S7 completion work.
- [x] 2026-02-12T02:09:28Z Re-ranked current simplification opportunities by impact and converted the scan into an executable sprint/task plan.
- [x] 2026-02-12T02:11:29Z Ran mandatory subagent review and incorporated missing dependency ordering, task splits, validation gaps, and parity assertions.
- [x] 2026-02-12T02:24:49Z Completed Sprint S8 `T1` by extracting Inspector UI state orchestration into `frontend/src/features/inspector/hooks/useInspectorUiState.ts` (section persistence, section toggles, metrics expansion toggle, and copy-toast timers) and slimming `frontend/src/features/inspector/Inspector.tsx` to composition/wiring.
- [x] 2026-02-12T02:24:49Z Validation for `T1`: `cd frontend && npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T02:28:50Z Completed Sprint S8 `T3a` by splitting `frontend/src/features/inspector/hooks/useInspectorMetadataWorkflow.ts` into `useInspectorSingleMetadata`, `useInspectorCompareMetadata`, and `useInspectorCompareExport`, while preserving the existing workflow return contract consumed by `frontend/src/features/inspector/Inspector.tsx`.
- [x] 2026-02-12T02:28:50Z Validation for `T3a`: `cd frontend && npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T02:34:48Z Completed Sprint S8 `T3b` by adding explicit request-context guards for stale metadata responses in `frontend/src/features/inspector/hooks/useInspectorSingleMetadata.ts` and `frontend/src/features/inspector/hooks/useInspectorCompareMetadata.ts`, backed by shared guard helpers in `frontend/src/features/inspector/hooks/metadataRequestGuards.ts`.
- [x] 2026-02-12T02:34:48Z Validation for `T3b`: `cd frontend && npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts src/features/inspector/hooks/__tests__/metadataRequestGuards.test.ts` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T02:39:52Z Completed Sprint S8 `T4` by hardening `frontend/src/features/inspector/hooks/useInspectorSidecarWorkflow.ts` with explicit draft reset semantics keyed by sidecar/path context, dirty-state guards for notes/tags inputs, and semantic no-op suppression on blur commits. Added shared draft guard helpers in `frontend/src/features/inspector/hooks/sidecarDraftGuards.ts`.
- [x] 2026-02-12T02:39:52Z Validation for `T4`: `cd frontend && npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts src/features/inspector/hooks/__tests__/metadataRequestGuards.test.ts src/features/inspector/hooks/__tests__/sidecarDraftGuards.test.ts` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T02:44:24Z Completed Sprint S8 `T2a` by introducing typed metadata render nodes in `frontend/src/features/inspector/model/metadataCompare.ts` (`buildJsonRenderNode` + typed node contracts), wiring `frontend/src/features/inspector/sections/MetadataSection.tsx` to prefer typed rendering, and retaining the legacy HTML renderer as an explicit fallback path.
- [x] 2026-02-12T02:44:24Z Validation for `T2a`: `cd frontend && npm run test -- src/features/inspector/model/__tests__/metadataCompare.test.ts src/features/inspector/__tests__/exportComparison.test.tsx` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T02:49:02Z Completed Sprint S8 `T2b` by removing legacy HTML metadata rendering (`renderJsonValue` + `dangerouslySetInnerHTML`) and replacing serialized `data-json-path` decoding with direct typed-path callbacks across single and compare metadata sections (`frontend/src/features/inspector/sections/JsonRenderCode.tsx`, `frontend/src/features/inspector/sections/MetadataSection.tsx`, `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`, and `frontend/src/features/inspector/Inspector.tsx`).
- [x] 2026-02-12T02:49:02Z Validation for `T2b`: `cd frontend && npm run test -- src/features/inspector/model/__tests__/metadataCompare.test.ts src/features/inspector/__tests__/exportComparison.test.tsx` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T02:50:22Z Completed Sprint S8 `T11` by centralizing metadata path-copy payload derivation in `frontend/src/features/inspector/model/metadataCompare.ts` (`buildMetadataPathCopyPayload`) and adding parity-oriented tests across model/guard/section suites (`frontend/src/features/inspector/model/__tests__/metadataCompare.test.ts`, `frontend/src/features/inspector/hooks/__tests__/metadataRequestGuards.test.ts`, `frontend/src/features/inspector/sections/__tests__/metadataSections.test.tsx`).
- [x] 2026-02-12T02:50:22Z Validation for `T11`: `cd frontend && npm run test -- src/features/inspector/model/__tests__/metadataCompare.test.ts src/features/inspector/hooks/__tests__/metadataRequestGuards.test.ts src/features/inspector/sections/__tests__/metadataSections.test.tsx src/features/inspector/__tests__/exportComparison.test.tsx` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T02:50:22Z Completed Sprint S8 acceptance and added explicit sprint handover notes in the Sprint Plan section.
- [x] 2026-02-12T03:00:05Z Completed Sprint S9 `T5` by replacing the in-component filter-chip `if/else` chain in `frontend/src/app/AppShell.tsx` with a typed declarative registry (`frontend/src/app/model/filterChips.ts`) that pairs clause readers with clear actions.
- [x] 2026-02-12T03:00:05Z Validation for `T5`: `cd frontend && npm run test -- src/app/model/__tests__/filterChips.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceUi.test.ts` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T03:02:12Z Completed Sprint S9 `T6` by removing the dead breadcrumb/path bar branch guarded by `false` in `frontend/src/app/AppShell.tsx`, including its unreachable inline path-segmentation and clipboard handlers.
- [x] 2026-02-12T03:02:12Z Validation for `T6`: `cd frontend && npm run test -- src/app/model/__tests__/filterChips.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceUi.test.ts` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T03:05:05Z Completed Sprint S9 `T7` by deduplicating compare metadata A/B pane rendering into a shared `CompareMetadataPane` inside `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`, preserving copy/PIL toggle/toast behavior.
- [x] 2026-02-12T03:05:05Z Validation for `T7`: `cd frontend && npm run test -- src/features/inspector/sections/__tests__/metadataSections.test.tsx src/features/inspector/__tests__/exportComparison.test.tsx` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T03:05:05Z Completed Sprint S9 acceptance and added explicit sprint handover notes in the Sprint Plan section.
- [x] 2026-02-12T03:08:41Z Completed Sprint S10 `T8` by extracting shared metric-number formatting into `frontend/src/lib/util.ts` (`formatMetricNumber`) and wiring both metrics and inspector basics call sites to the shared utility (`frontend/src/features/metrics/model/histogram.ts`, `frontend/src/features/inspector/sections/BasicsSection.tsx`).
- [x] 2026-02-12T03:08:41Z Validation for `T8`: `cd frontend && npm run test -- src/features/metrics/model/__tests__/histogram.test.ts src/features/metrics/model/__tests__/metricValues.test.ts src/lib/__tests__/util.test.ts` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T03:11:15Z Completed Sprint S10 `T9` by removing redundant item-level metric collection from `frontend/src/features/metrics/model/histogram.ts` (`collectMetricValues`) so runtime extraction remains canonical in `frontend/src/features/metrics/model/metricValues.ts`.
- [x] 2026-02-12T03:11:15Z Validation for `T9`: `cd frontend && npm run test -- src/features/metrics/model/__tests__/histogram.test.ts src/features/metrics/model/__tests__/metricValues.test.ts` (pass), `cd frontend && npx tsc --noEmit` (pass).
- [x] 2026-02-12T03:15:59Z Completed Sprint S10 `T10` by removing Inspector `valueHeights` runtime measuring in `frontend/src/features/inspector/Inspector.tsx` and replacing Basics copy-value rendering in `frontend/src/features/inspector/sections/BasicsSection.tsx` with a CSS-only overlay pattern that preserves row height while showing `Copied`.
- [x] 2026-02-12T03:15:59Z Validation for `T10` and final acceptance: `cd /home/ubuntu/dev/lenslet/frontend && npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceUi.test.ts src/features/metrics/model/__tests__/histogram.test.ts src/features/metrics/model/__tests__/metricValues.test.ts` (pass), `cd /home/ubuntu/dev/lenslet/frontend && npx tsc --noEmit` (pass), `cd /home/ubuntu/dev/lenslet/frontend && npm run build` (pass).
- [x] 2026-02-12T03:15:59Z Completed Sprint S10 acceptance and added explicit sprint handover notes in the Sprint Plan section.


## Surprises & Discoveries


The previous scan mixed two different states of the codebase: true unresolved items and items that were already planned or implemented in later S4-S7 tickets. That made priority noisy and created stale guidance.

The largest remaining simplification opportunities are not raw file length anymore. They are boundary quality issues, especially in `frontend/src/features/inspector/Inspector.tsx` where state orchestration and prop fan-out still dominate.

A few non-trivial legacy behaviors remain in plain sight and are easy to miss during normal development, especially constant-guarded UI branches and duplicated compare-pane rendering paths.

Hook and rendering tasks are coupled more tightly than they first appear. Rendering migration, compare-pane deduplication, and async lifecycle splits can interfere if applied in the wrong sequence.

Inspector currently has no dedicated component-level tests for section persistence/copy-toast UI behavior, so this iteration validated via existing inspector model/export suites and typecheck; focused Inspector interaction coverage remains part of `T11`.

During `T3a`, compare-workflow reset semantics proved intentionally asymmetric: labels/embed reset only when compare context is inactive, while export mode/error reset on every compare context change. Keeping this behavior unchanged is now an explicit parity anchor for `T3b`.

`T3b` confirmed a previously implicit race in single-metadata fetches: when selection/context changed mid-request, late responses could repopulate cleared metadata state. Compare metadata already had request-id suppression, but now both flows share the same explicit “request id + context key must match” contract.

`T4` surfaced a subtle stale-draft risk in sidecar notes/tags: the previous workflow did not explicitly reset drafts when selection changed to a path whose sidecar had not loaded yet, so the UI could temporarily show prior-item values. The new reset contract now treats path/sidecar context as authoritative draft source.

`T2a` confirmed that one metadata surface can move to typed rendering without changing click-copy behavior by preserving existing `data-json-path` markers on key spans. Keeping the HTML path as a fallback in this step reduced migration risk and isolates `T2b` to strict legacy-path removal.

`T2b` validated that removing serialized path encoding/decoding is straightforward once both metadata surfaces share one typed renderer contract. The remaining parity risk is now concentrated in interaction coverage (`T11`) rather than renderer implementation drift.

`T11` showed that parity coverage can be strengthened in this codebase without introducing a new DOM harness: server-rendered section snapshots plus pure model/guard tests are enough to lock copy-path label text, copied payload formatting, and compare-pane A/B state labeling contracts.

Path-copy derivation had drift risk because single and compare handlers each rebuilt label/value formatting manually in `Inspector.tsx`; promoting that logic to one model helper now keeps copy semantics testable and consistent.

`T5` confirmed that AppShell chip behavior can be centralized without UI regressions by treating each filter clause as data (`read` + `clear`) in a registry. Legacy `stars` and canonical `starsIn` clauses now intentionally share one clear action contract, which reduces branch drift risk ahead of `T6`.

`T6` confirmed the dead breadcrumb block in `AppShell` was fully unreachable and self-contained; deleting it required no routing/state changes and reduced render noise ahead of compare-pane deduplication in `T7`.

`T7` confirmed compare metadata pane duplication can be removed without behavior churn by extracting one shared pane subcomponent and passing side-specific state/handlers. The highest remaining risk in this area is now accidental prop-wiring drift, not rendering-logic divergence.

`T8` confirmed metrics and inspector can share one number-format utility with no display threshold regressions. A third formatter still exists in `frontend/src/features/browse/components/MetricScrollbar.tsx`, but it intentionally uses `'-'` for null values (vs `'–'`), so it remains out of scope for this parity-preserving sprint.

`T9` confirmed histogram-level metric extraction had become pure duplication: `collectMetricValues` was no longer used by runtime paths and only remained as a parallel test seam. Removing it tightened boundaries so histogram owns numeric/domain math and `metricValues.ts` remains the single source of item-to-metric extraction semantics.

`T10` confirmed Inspector basics row-jitter protection does not need runtime DOM measurement state: preserving the original value text in layout flow (hidden) while rendering `Copied` as an absolute overlay keeps row height stable and removes transient state/callback complexity.


## Decision Log


1. 2026-02-12, assistant. Supersede the old post-S4 table-based scan with a post-S7 execution plan because most S4 items were completed and no longer actionable.
2. 2026-02-12, assistant. Scope this update to findings that are current in the frontend refactor surface touched by sprints 21-36, and remove stale “covered later” entries that are now complete.
3. 2026-02-12, assistant. Keep behavior parity as a strict guardrail while permitting internal restructuring and interface cleanup where it materially improves maintainability.
4. 2026-02-12, assistant. Prioritize Inspector architecture cleanup before smaller utility and dead-code cleanups because Inspector still carries the highest coupling and review risk.
5. 2026-02-12, assistant. Preserve this file path (`docs/20260211_post_s4_high_impact_simplification_scan.md`) for continuity, but update its content to serve as an implementation-ready plan rather than a static findings table.
6. 2026-02-12, assistant. Split oversized rendering and workflow tickets into staged sub-tasks (`T2a`/`T2b`, `T3a`/`T3b`) to reduce rollback complexity and make validation checkpoints explicit.
7. 2026-02-12, assistant. Add explicit dependency order and manual parity checklist to prevent hidden regressions in copy-path behavior, stale-request handling, and compare metadata interactions.
8. 2026-02-12, assistant. Implement `T1` by introducing a dedicated `useInspectorUiState` hook that preserves existing localStorage keys and toast timing semantics while moving section/copy UI orchestration out of `Inspector.tsx`.
9. 2026-02-12, assistant. Implement `T3a` as a pure composition refactor: keep `useInspectorMetadataWorkflow` as the compatibility wrapper and move single-metadata, compare-metadata, and export lifecycles into dedicated hooks to reduce coupling without changing `Inspector` call sites.
10. 2026-02-12, assistant. Preserve existing compare export reset behavior exactly during extraction (inactive context resets labels/embed/mode/error; active context resets mode/error only) so `T3b` can focus only on stale-response hardening.
11. 2026-02-12, assistant. Implement `T3b` with a shared `metadataRequestGuards` module and apply the same gating predicate to both single and compare metadata hooks so stale suppression semantics are centralized and testable.
12. 2026-02-12, assistant. Implement `T4` with two complementary safeguards: dirty refs to avoid blur-triggered writes without user edits, and semantic comparison helpers (notes exact-match, tags normalized comma parsing) so writes occur only when meaningfully changed.
13. 2026-02-12, assistant. Implement `T2a` as a bridge migration: introduce typed render-node contracts and typed rendering in `MetadataSection` first, while keeping legacy HTML rendering available as fallback so `T2b` can remove old HTML/decode paths in a separate, parity-focused step.
14. 2026-02-12, assistant. Implement `T2b` with a shared typed renderer component (`JsonRenderCode`) consumed by both single and compare metadata sections, and move copy-path behavior to direct typed-path callbacks so no serialized DOM path decoding remains.
15. 2026-02-12, assistant. Implement `T11` with a model-first test strategy in the existing Node Vitest environment: centralize metadata path-copy payload derivation in one helper and lock UI semantics with SSR section rendering tests instead of introducing new DOM runtime dependencies mid-sprint.
16. 2026-02-12, assistant. Implement `T5` by extracting filter-chip clause handling into a typed AppShell registry helper (`buildFilterChips`) and keeping `AppShell.tsx` responsible only for wiring filter clear actions.
17. 2026-02-12, assistant. Implement `T6` by deleting the constant-false breadcrumb/path bar branch outright rather than preserving dormant UI code, because no active behavior referenced it and parity is better protected by removal than by keeping unreachable JSX.
18. 2026-02-12, assistant. Implement `T7` by introducing a local shared `CompareMetadataPane` component in `CompareMetadataSection.tsx` and reusing it for sides A/B, so copy/PIL/toast semantics are parameterized instead of duplicated inline.
19. 2026-02-12, assistant. Implement `T8` by introducing `formatMetricNumber` in `frontend/src/lib/util.ts` as the single threshold source and preserving `histogram.ts`'s `formatNumber` API as a thin compatibility wrapper; defer `MetricScrollbar` formatter unification to avoid changing its distinct null glyph contract in this ticket.
20. 2026-02-12, assistant. Implement `T9` by deleting `collectMetricValues` from `frontend/src/features/metrics/model/histogram.ts` and moving the finite-value collection assertion into `metricValues` tests, so item metric extraction has one canonical implementation path (`collectMetricValuesByKey`).
21. 2026-02-12, assistant. Implement `T10` by removing `valueHeights` runtime measurement entirely and using a CSS-only copy-state overlay in `BasicsSection`, because this preserves row-height parity while reducing Inspector state and callback surface.


## Outcomes & Retrospective


The immediate outcome of this update is a clean, current target list with explicit execution order and validation requirements. The stale entries that depended on pre-S7 assumptions are no longer present.

Sprint S8 is complete (`T1`, `T2a`, `T2b`, `T3a`, `T3b`, `T4`, `T11`), Sprint S9 is complete (`T5`, `T6`, `T7`), and Sprint S10 is complete (`T8`, `T9`, `T10`). Inspector basics no longer depends on runtime value-height measuring, while copy-state behavior remains parity-preserving through CSS-only layout retention. Final acceptance command matrix, typecheck, and production build are all green.


## Context and Orientation


This plan targets the frontend architecture after completion of sprints 21-36 recorded in `progress.txt` and `docs/20260211_foundational_long_file_refactor_plan.md`.

The primary modules in scope are `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/inspector/hooks/useInspectorMetadataWorkflow.ts`, `frontend/src/features/inspector/hooks/useInspectorSidecarWorkflow.ts`, `frontend/src/features/inspector/model/metadataCompare.ts`, `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`, `frontend/src/features/inspector/sections/BasicsSection.tsx`, `frontend/src/features/metrics/model/histogram.ts`, `frontend/src/features/metrics/model/metricValues.ts`, and `frontend/src/app/AppShell.tsx`.

In this plan, “boundary quality” means whether one file owns one coherent responsibility with minimal cross-domain state entanglement. “behavior parity” means no intended user-visible change in Inspector, AppShell filter controls, metadata display semantics, or metrics filtering behavior. “stale request” means an async response that should be ignored because user selection or compare context changed after request start.


## Plan of Work


The implementation sequence starts with high-coupling Inspector orchestration issues, then addresses AppShell and compare UI structural duplication, and ends with utility-level convergence and residual legacy cleanups. This order minimizes risk because the earliest sprints reduce complexity in the highest-churn domains before touching lower-risk utilities.

The updated findings ranked by impact are as follows.

1. `P1` Simplify Inspector orchestration by extracting UI-state and action wiring from `frontend/src/features/inspector/Inspector.tsx` so the component becomes a thin composition shell.
2. `P1` Replace string-HTML metadata rendering pipeline (`renderJsonValue` + `dangerouslySetInnerHTML`) with typed render nodes/components to remove brittle path encoding/decoding behavior.
3. `P1` Split `frontend/src/features/inspector/hooks/useInspectorMetadataWorkflow.ts` into smaller hooks for single-item metadata, compare metadata, and export workflow, each with explicit stale-response handling.
4. `P1` Add dirty-state and semantic no-op guards in `frontend/src/features/inspector/hooks/useInspectorSidecarWorkflow.ts` to prevent unnecessary writes on blur and stale local drafts.
5. `P2` Replace AppShell filter-chip `if/else` chain with a declarative clause registry in `frontend/src/app/AppShell.tsx`.
6. `P2` Remove dead breadcrumb block in `frontend/src/app/AppShell.tsx` guarded by constant `false`.
7. `P2` Deduplicate A/B compare metadata panes in `frontend/src/features/inspector/sections/CompareMetadataSection.tsx` using a shared subcomponent.
8. `P2` Remove runtime `valueHeights` measuring from Inspector basics display if CSS/layout constraints can provide stable rendering.
9. `P3` Consolidate duplicate metric number formatting into one shared utility used by Metrics and Inspector.
10. `P3` Remove or narrow `collectMetricValues` in `frontend/src/features/metrics/model/histogram.ts` now that `metricValues.ts` is the canonical runtime path.

### Sprint Plan


1. Sprint S8: Inspector Boundary Hardening. Goal: make Inspector orchestration modular and deterministic. Demo outcome: `Inspector.tsx` acts primarily as composition/wiring, metadata rendering is migrated in controlled stages, and metadata workflows are split with explicit stale-request contract. Linked tasks: `T1`, `T2a`, `T2b`, `T3a`, `T3b`, `T4`, `T11`.
2. Sprint S9: AppShell and Compare UI Simplification. Goal: remove legacy/dead branches and eliminate major duplication in compare metadata rendering and filter-chip derivation. Demo outcome: AppShell filter chips come from declarative rules and compare A/B metadata panes are rendered by one reusable unit. Linked tasks: `T5`, `T6`, `T7`.
3. Sprint S10: Utility Convergence and Residual Cleanup. Goal: reduce utility drift and remove low-value legacy measurement paths. Demo outcome: one shared metric format utility and no redundant runtime metric collector path in histogram model, with Inspector basics rendering unchanged for users. Linked tasks: `T8`, `T9`, `T10`.

#### Sprint S8 Handover (2026-02-12T02:50:22Z)

- Completed:
  - `T1`, `T2a`, `T2b`, `T3a`, `T3b`, `T4`, `T11`.
  - Inspector metadata copy-path logic is now centralized via `buildMetadataPathCopyPayload` and parity-covered in model + section suites.
- Validations run and outcomes:
  - `cd frontend && npm run test -- src/features/inspector/model/__tests__/metadataCompare.test.ts src/features/inspector/hooks/__tests__/metadataRequestGuards.test.ts src/features/inspector/sections/__tests__/metadataSections.test.tsx src/features/inspector/__tests__/exportComparison.test.tsx` (pass).
  - `cd frontend && npx tsc --noEmit` (pass).
- Known risks/follow-ups:
  - Rapid selection/compare stale-response behavior is covered at guard-contract level; there is still no full DOM interaction harness for end-to-end Inspector click flows in this repo.
  - AppShell simplification (`T5`/`T6`) remains untouched and is the next major legacy-risk surface.
- First step for the next sprint:
  - Start Sprint S9 with `T5`: replace AppShell filter-chip clause branching in `frontend/src/app/AppShell.tsx` with a declarative typed clause registry while preserving label/clear behavior parity.

#### Sprint S9 Handover (2026-02-12T03:05:05Z)

- Completed:
  - `T5`, `T6`, `T7`.
  - AppShell filter chips now come from one typed registry, the dead breadcrumb block is removed, and compare metadata A/B panes now render through one shared pane component.
- Validations run and outcomes:
  - `cd frontend && npm run test -- src/app/model/__tests__/filterChips.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceUi.test.ts` (pass).
  - `cd frontend && npm run test -- src/features/inspector/sections/__tests__/metadataSections.test.tsx src/features/inspector/__tests__/exportComparison.test.tsx` (pass).
  - `cd frontend && npx tsc --noEmit` (pass).
- Known risks/follow-ups:
  - Compare metadata parity is still protected by SSR section tests and manual inspection rather than a browser interaction harness, so full click-through behavior remains a lightweight manual checklist item.
  - Sprint S10 will touch shared metric formatting paths used by both metrics and inspector basics; threshold parity should be locked with focused model tests before any additional cleanup.
- First step for the next sprint:
  - Start Sprint S10 with `T8`: extract a shared metric-number formatting utility and wire it into metrics/inspector call sites with unchanged display thresholds.

#### Sprint S10 Handover (2026-02-12T03:15:59Z)

- Completed:
  - `T8`, `T9`, `T10`.
  - Inspector basics now removes `valueHeights` measurement state and keeps copy-row height stable via CSS-only copy overlays in `BasicsSection`.
- Validations run and outcomes:
  - `cd /home/ubuntu/dev/lenslet/frontend && npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceUi.test.ts src/features/metrics/model/__tests__/histogram.test.ts src/features/metrics/model/__tests__/metricValues.test.ts` (pass).
  - `cd /home/ubuntu/dev/lenslet/frontend && npx tsc --noEmit` (pass).
  - `cd /home/ubuntu/dev/lenslet/frontend && npm run build` (pass).
- Known risks/follow-ups:
  - Inspector basics still has no browser-level interaction harness for visual jitter/clipping assertions; parity is currently guarded by code-path simplification plus the existing regression suite.
  - Manual parity checklist item 7 (mixed short/long basics values) should still be spot-checked in the running app when convenient.
- First step for the next sprint:
  - No further sprint is scheduled in this plan; if a new cleanup sprint is opened, first step should be adding a browser-level Inspector basics interaction test harness to cover visual copy-state parity directly.

### Dependency Order


1. `T1` then `T3a` then `T3b` then `T4` to stabilize state and workflow contracts before final rendering cleanup.
2. `T2a` then `T2b` so typed metadata rendering lands behind a parity checkpoint before old path removal.
3. `T2b` before `T7` so compare-pane deduplication uses the final rendering model.
4. `T5` then `T6` to replace filter logic before deleting dead AppShell branch paths.
5. `T8` then `T9` to converge metric formatting and data collection in deterministic order.
6. `T10` last because layout simplification has the highest visual regression risk and depends on prior behavior stabilization.


## Concrete Steps


Execute all commands from repository root unless otherwise stated.

    cd /home/ubuntu/dev/lenslet
    cd frontend && npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts
    cd frontend && npm run test -- src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceUi.test.ts
    cd frontend && npm run test -- src/features/metrics/model/__tests__/histogram.test.ts src/features/metrics/model/__tests__/metricValues.test.ts
    cd frontend && npx tsc --noEmit
    cd frontend && npm run build

### Task/Ticket Details


1. `T1` Extract Inspector UI-state controller from `frontend/src/features/inspector/Inspector.tsx`. Goal: isolate section open-state persistence, copy-toast timers, and section toggles into a dedicated hook or controller module; affected files: `frontend/src/features/inspector/Inspector.tsx` and new `frontend/src/features/inspector/hooks/useInspectorUiState.ts`; validation: Inspector section open/close persistence and copy toast behavior remain unchanged.
2. `T2a` Introduce typed metadata render nodes alongside existing HTML-string path. Goal: add structured render output and wire it into one metadata surface while preserving legacy rendering fallback; affected files: `frontend/src/features/inspector/model/metadataCompare.ts`, `frontend/src/features/inspector/sections/MetadataSection.tsx`; validation: copy-path payload and click behavior match current output under both paths.
3. `T2b` Remove legacy HTML-string rendering and serialized path decoding. Goal: complete migration to typed render output and delete `dangerouslySetInnerHTML`-dependent path logic; affected files: `frontend/src/features/inspector/model/metadataCompare.ts`, `frontend/src/features/inspector/Inspector.tsx`, metadata section components; validation: parity assertions pass for copied value text, path labels, and visual metadata visibility.
4. `T3a` Split metadata workflow hook without behavior change. Goal: separate single-item metadata lifecycle, compare-metadata lifecycle, and export workflow into smaller hooks with unchanged external API; affected files: `frontend/src/features/inspector/hooks/useInspectorMetadataWorkflow.ts` and new hook modules under `frontend/src/features/inspector/hooks/`; validation: existing inspector metadata/export tests remain green without new behavior deltas.
5. `T3b` Add stale-request guards with explicit contract. Goal: enforce “last active selection/context wins” for metadata and compare requests; affected files: extracted metadata hooks from `T3a`; validation: fast selection switch and rapid compare toggle scenarios do not surface stale content.
6. `T4` Harden sidecar workflow commits. Goal: commit on blur only when semantic changes exist and ensure local draft reset semantics are explicit when sidecar/path changes; affected files: `frontend/src/features/inspector/hooks/useInspectorSidecarWorkflow.ts`; validation: notes/tags/star conflict flows, local typing signals, and multi-select bulk behavior remain unchanged.
7. `T5` Build declarative AppShell filter-chip registry. Goal: replace clause-type branching with a typed mapping of clause readers and clear actions; affected files: `frontend/src/app/AppShell.tsx` and optional new helper under `frontend/src/app/model/`; validation: chip labels and per-chip clear actions match current behavior across all filter types.
8. `T6` Remove dead breadcrumb branch. Goal: delete constant-false breadcrumb block and related dead inline helpers; affected files: `frontend/src/app/AppShell.tsx`; validation: no regression in browsing, routing, or path switching and no behavior changes in active views.
9. `T7` Deduplicate compare metadata pane rendering. Goal: introduce one shared compare-side component used for both A and B panes; affected files: `frontend/src/features/inspector/sections/CompareMetadataSection.tsx`; validation: copy buttons, PIL toggles, copied-path toasts, and rendered metadata content remain identical.
10. `T8` Unify metric number formatting. Goal: move formatting logic to one shared utility and consume it from both metrics and inspector sections; affected files: `frontend/src/features/metrics/model/histogram.ts`, `frontend/src/features/inspector/sections/BasicsSection.tsx`, plus a shared util module if required; validation: number display thresholds remain exactly the same in both UI surfaces.
11. `T9` Remove redundant runtime metric collector in histogram model. Goal: keep one canonical metric-value collection path and avoid parallel collectors with diverging behavior; affected files: `frontend/src/features/metrics/model/histogram.ts`, `frontend/src/features/metrics/model/metricValues.ts`, and related tests; validation: histogram and metric-value unit tests pass with no behavior regression.
12. `T10` Remove Inspector `valueHeights` runtime measuring if CSS-equivalent layout is sufficient. Goal: reduce transient layout state and callback complexity in basics section; affected files: `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/inspector/sections/BasicsSection.tsx`; validation: no visible jitter/regression in basics rows; fallback: retain guarded measurement path if parity fails.
13. `T11` Add parity regression coverage for critical Inspector flows. Goal: lock copy payloads, copy path labels, stale-request suppression, and compare metadata interaction behavior with focused tests; affected files: inspector model and section test suites under `frontend/src/features/inspector/`; validation: new tests fail on deliberate path/copy or stale-response regressions.


## Validation and Acceptance


Each sprint is accepted only when targeted tests, typecheck, and production build pass without introducing new expected-failure baselines.

1. Sprint S8 acceptance requires stable Inspector behavior across single-select, multi-select, metadata load/reload, compare metadata, conflict apply/keep, and export actions, with no stale-request race defects.
2. Sprint S9 acceptance requires unchanged filter-chip labels and clear semantics, unchanged compare metadata A/B rendering semantics, and complete removal of dead breadcrumb code paths.
3. Sprint S10 acceptance requires utility-level parity in metric formatting and histogram behavior, and no visible regression after removing runtime measurement complexity.
4. Overall acceptance requires all targeted frontend tests green, `npx tsc --noEmit` green, and `npm run build` green.

Manual parity checklist is required in addition to automated tests.

1. Inspector metadata click-to-copy returns the same copied payload text for the same metadata path as before migration.
2. Inspector metadata copied path labels remain unchanged for nested object and array paths.
3. Rapidly changing selected image at least five times does not display stale metadata.
4. Rapidly toggling compare context does not display stale compare metadata.
5. Compare metadata A/B controls behave identically after pane deduplication.
6. AppShell filter chip labels and clear actions remain unchanged across all clause types.
7. Basics section with mixed short and long values shows no row jitter or clipping.

The fixed command matrix for this scope is as follows.

    cd /home/ubuntu/dev/lenslet/frontend && npm run test -- src/features/inspector/__tests__/exportComparison.test.tsx src/features/inspector/model/__tests__/metadataCompare.test.ts src/app/__tests__/appShellSelectors.test.ts src/app/__tests__/presenceUi.test.ts src/features/metrics/model/__tests__/histogram.test.ts src/features/metrics/model/__tests__/metricValues.test.ts
    cd /home/ubuntu/dev/lenslet/frontend && npx tsc --noEmit
    cd /home/ubuntu/dev/lenslet/frontend && npm run build


## Idempotence and Recovery


All refactors in this plan are internal and should be applied in small commits so each ticket can be reverted independently if needed. If a ticket fails validation, revert only that ticket commit range and continue with unaffected tasks.

Hook extraction tasks are idempotent when repeated because they do not change public app contracts. For stale-request hardening tasks, rerun targeted tests after each incremental change before moving to the next ticket.

If typed metadata rendering (`T2a`/`T2b`) destabilizes copy-path behavior, keep typed and legacy renderers in parallel, run parity checklist, and only then remove legacy path. If parity still fails, restore legacy path and capture failing scenario in tests before retry.

If CSS-only layout strategy for `T10` fails parity, keep a guarded measurement fallback and document the exact layout case that requires it.


## Artifacts and Notes


This plan intentionally removes stale items from the old post-S4 scan that were already addressed by S4-S7 work, including AppShell selector/effect extractions and typecheck closure tasks.

Evidence references that shaped this update include:

    frontend/src/app/AppShell.tsx:524
    frontend/src/app/AppShell.tsx:1259
    frontend/src/features/inspector/Inspector.tsx:96
    frontend/src/features/inspector/Inspector.tsx:642
    frontend/src/features/inspector/hooks/useInspectorMetadataWorkflow.ts:50
    frontend/src/features/inspector/hooks/useInspectorSidecarWorkflow.ts:71
    frontend/src/features/inspector/model/metadataCompare.ts:179
    frontend/src/features/metrics/model/histogram.ts:41
    frontend/src/features/metrics/model/metricValues.ts:7

Subagent review summary integrated into this revision:

    - Split oversized tasks into staged migration tickets.
    - Added explicit dependency ordering.
    - Added manual parity checklist for stale-request and copy-path semantics.
    - Added fallback path for layout simplification risk.

Current ranked findings reflect post-S7 state and supersede the original table in this file.


## Interfaces and Dependencies


No new third-party runtime dependencies are required. Existing dependencies remain React, TypeScript, and project-local modules under `frontend/src`.

Planned internal interfaces should preserve existing call-site contracts unless explicitly simplified within this plan. Expected interfaces include a dedicated Inspector UI-state hook returning section-open state and copy-toast actions, smaller metadata workflow hooks for item metadata, compare metadata, and export actions, and a shared compare metadata side component contract that takes side label, PIL toggle state, copy state, rendered metadata content, and click handlers.

Where utility convergence is implemented, one canonical metric number formatter must be exported from a shared module and imported by both metrics and inspector sections so thresholds are defined in exactly one place.

Stale-request contracts must be explicit in extracted metadata hooks: each async result must apply only when its request token matches the current active context key.


Revision note (2026-02-12): Replaced the pre-S7 table scan with a post-S7 execution plan, removed outdated entries already completed in S4-S7, and added ranked current tasks with sprint-level validation. This revision also incorporates mandatory subagent review feedback by splitting oversized tickets, adding dependency order, and tightening acceptance criteria.
