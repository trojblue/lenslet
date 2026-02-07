# Touch Readiness Implementation Plan (Tablet Entry, Mobile Baseline)


## Purpose / Big Picture


This plan defines a lightweight implementation path to make the current Lenslet frontend touch-ready for core workflows on tablets, then reliably viewable and navigable on mobile phones. After delivery, users should be able to open item actions without right-click, move files without drag-and-drop, upload without drag-and-drop, and inspect images with touch gestures. On phones, the interface should remain understandable and navigable even if power-user workflows are reduced.

The scope is intentionally constrained to high-frequency interaction hotpaths and foundational responsive behavior. The plan avoids large architecture rewrites and new dependency-heavy UI systems.

No `PLANS.md` (or equivalent canonical planning file) is present in this repository. This document is the canonical implementation plan for this change set.


## Progress


- [x] 2026-02-07 20:38:07Z Completed frontend survey of touch/mobile risks across hotpaths and responsive layout behavior.
- [x] 2026-02-07 20:38:07Z Scoped work to tablet-first touch parity and mobile baseline navigation/viewability, with explicit scope guards to prevent overbuild.
- [x] 2026-02-07 20:38:07Z Drafted sprint plan and atomic tickets with validation per task.
- [x] 2026-02-07 20:43:27Z Ran required subagent review and captured gaps around task sizing, touch-action behavior, coordinate-space clamping, and device coverage.
- [x] 2026-02-07 20:43:27Z Incorporated review feedback by splitting oversized tickets, adding input model rules, and adding explicit iOS/Android validation checklist work.
- [x] 2026-02-07 20:43:27Z Finalized this plan document under `docs/`.


## Surprises & Discoveries


The most frequent action entrypoints are still gated behind desktop interaction assumptions. Context actions are opened by right-click handlers in both grid and tree flows (`frontend/src/app/AppShell.tsx:1746`, `frontend/src/app/AppShell.tsx:1857`, `frontend/src/features/browse/components/VirtualGrid.tsx:514`, `frontend/src/features/folders/FolderTree.tsx:278`), which creates immediate touch dead-ends.

Item movement and upload flows currently depend on drag-and-drop in primary paths (`frontend/src/features/browse/components/VirtualGrid.tsx:510`, `frontend/src/features/folders/hooks/useFolderTreeDragDrop.ts:35`, `frontend/src/app/AppShell.tsx:1534`). That behavior works on desktop but creates reliability and discoverability issues on tablets and phones.

Image inspection is optimized for wheel and mouse drag interactions (`frontend/src/features/viewer/Viewer.tsx:92`, `frontend/src/features/viewer/hooks/useZoomPan.ts:37`, `frontend/src/features/compare/hooks/useCompareZoomPan.ts:61`), so core quality-check behavior under touch is currently degraded.

Responsive handling is shallow and centered on one narrow threshold (`frontend/src/shared/ui/Toolbar.tsx:99`, `frontend/src/styles.css:714`). Several controls and handles remain too small or too mouse-specific for touch ergonomics (`frontend/src/app/components/LeftSidebar.tsx:190`, `frontend/src/features/folders/FolderTree.tsx:269`, `frontend/src/styles.css:908`).

Menu placement behavior currently risks edge overflow on narrow screens and requires explicit coordinate-space handling when menus are rendered in portal/fixed contexts (`frontend/src/app/menu/ContextMenu.tsx:20`, `frontend/src/shared/ui/Dropdown.tsx:141`).


## Decision Log


2026-02-07, author: assistant. The delivery target is split into two user-facing thresholds: tablet touch parity first, then mobile viewability/navigation baseline. This sequencing protects hotpaths early without blocking on full mobile feature parity.

2026-02-07, author: assistant. The implementation will prefer explicit controls over hidden gestures for high-frequency actions. Long-press support is added, but visible item actions remain available to preserve discoverability and intuitive use.

2026-02-07, author: assistant. The plan will not introduce new third-party gesture or layout libraries. Existing React and browser Pointer Events APIs are sufficient and keep scope light.

2026-02-07, author: assistant. Drag-and-drop remains supported on desktop but will no longer be the only path for move and upload workflows.

2026-02-07, author: assistant. Tablet behavior will prioritize content readability over panel simultaneity by collapsing or constraining sidebars in medium-width touch viewports.

2026-02-07, author: assistant. Mobile scope is intentionally limited to viewability and navigation continuity, not full parity with desktop productivity flows.

2026-02-07, author: assistant. Each task must be atomic and committable, with either automated tests or explicit manual validation when gesture simulation is not practical in current test harnesses.

2026-02-07, author: assistant. Gesture behavior must have explicit thresholds and cancel semantics to avoid accidental triggers. Long-press timing and movement thresholds are defined in plan-level input rules before implementation starts.

2026-02-07, author: assistant. Breakpoint behavior will be consolidated in one shared definition to avoid drift between CSS and TS logic.


## Outcomes & Retrospective


At this planning milestone, the main outcome is a concrete and constrained execution path that resolves the highest-impact touch blockers without overbuilding. The plan converts survey findings into small, testable tasks tied to observable behavior.

The key lesson from the survey is that usability gaps are concentrated in action entrypoints and interaction assumptions, not in visual styling. A lightweight improvement strategy should therefore focus on input-model parity and control discoverability before broader UI redesign.

After subagent review, the plan improved in three ways: oversized gesture/layout tasks were split into smaller units, input-model rules were made explicit to reduce ambiguity, and device coverage now includes specific iOS Safari and Android Chrome checks.


## Context and Orientation


The primary frontend shell is `frontend/src/app/AppShell.tsx`, which coordinates folder navigation, item actions, context menu state, and upload/drop behavior. The browse surface is `frontend/src/features/browse/components/VirtualGrid.tsx`, where selection, open behavior, and grid item actions are currently desktop-biased.

Folder interactions are implemented in `frontend/src/features/folders/FolderTree.tsx` and drag/drop helpers in `frontend/src/features/folders/hooks/useFolderTreeDragDrop.ts`. Viewer and compare gesture logic resides in `frontend/src/features/viewer/hooks/useZoomPan.ts` and `frontend/src/features/compare/hooks/useCompareZoomPan.ts`.

Core API operations relevant to this work are `api.uploadFile(dest: string, file: File)` at `frontend/src/api/client.ts:691`, `api.moveFile(src: string, dest: string)` at `frontend/src/api/client.ts:705`, and `api.deleteFiles(paths: string[])` at `frontend/src/api/client.ts:718`.

In this plan, “tablet-first” means touch-first behavior at roughly 768px to 1199px viewport widths. “Mobile baseline” means the UI remains viewable and navigable at roughly 360px to 767px, even where interaction density is reduced.

In this plan, “input model” means precedence and cancellation rules across tap, long-press, drag/pan, and pinch interactions. “Coordinate space” means the viewport-relative coordinate system used to place floating menus in scroll and portal contexts.


## Plan of Work


Implementation proceeds in three demoable sprints. The first sprint removes desktop-only blockers from high-frequency actions. The second sprint fixes touch ergonomics in viewer and layout control paths. The third sprint ensures small-screen navigation continuity and final hardening.

Scope management is explicit: no new state management architecture, no full redesign of panel systems, and no wholesale rewrite of browse or viewer components. The approach extends current flows with touch-compatible entrypoints and responsive constraints.

### Input Model Spec


Long-press delay is set to 500ms by default, with configurable bounds between 450ms and 600ms only if real-device testing requires adjustment. Long-press is canceled on pointer movement greater than 8 CSS pixels, any scroll start on the same container, pointer cancel, pointer up before threshold, or multi-touch initiation.

Single tap retains primary-selection semantics and never fires long-press actions in the same interaction sequence. Action-button taps take priority over row/cell selection handlers to keep intent explicit.

Viewer and compare surfaces use `touch-action: none` in active gesture regions and must handle `pointercancel` cleanly. General UI controls use `touch-action: manipulation` to preserve scroll/tap performance while avoiding accidental gesture capture.

### Sprint Plan


1. Sprint S1: Action Access Parity for Tablet.
Goal: make frequent item and folder actions usable without right-click or drag-only affordances.
Demo outcome: on a touch tablet profile, users can open item actions, move items via explicit destination selection, and upload files without drag-and-drop.
Linked tasks: T1, T2, T3, T4, T5, T6, T7.

2. Sprint S2: Viewer and Layout Touch Ergonomics.
Goal: make image inspection and panel behavior usable on touch-first medium-width screens.
Demo outcome: users can pan/zoom in viewer and compare with touch gestures, and side panels do not crowd content at tablet widths.
Linked tasks: T8, T9, T10, T11, T12, T13.

3. Sprint S3: Mobile Viewability and Navigation Baseline.
Goal: ensure phone-sized layouts are navigable and core flows remain accessible.
Demo outcome: users can navigate folders/items, open images, move through viewer items, and access key actions on narrow screens without hidden desktop-only gestures.
Linked tasks: T14, T15, T16, T17, T18, T19.


## Concrete Steps


All commands below run from `/home/ubuntu/dev/lenslet` unless a different working directory is shown.

    cd /home/ubuntu/dev/lenslet
    pip install -e . && pip install -e ".[dev]"
    cd /home/ubuntu/dev/lenslet/frontend && npm install
    cd /home/ubuntu/dev/lenslet/frontend && npm run test
    cd /home/ubuntu/dev/lenslet/frontend && npm run build
    cd /home/ubuntu/dev/lenslet && pytest -q
    cd /home/ubuntu/dev/lenslet && lenslet ./data --reload --port 7070

    cd /home/ubuntu/dev/lenslet/frontend && npm run dev
    # Open http://127.0.0.1:5173 and validate in device emulation profiles:
    # iPad Air (820x1180), iPad Mini (768x1024), iPhone 12 Pro (390x844).
    # Perform spot checks in Safari iOS and Chrome Android on hardware when available.

### Task/Ticket Details


1. T1 - Create shared touch interaction constants and long-press utility. Goal: define explicit long-press duration and cancel thresholds before wiring component behavior. Affected areas: `frontend/src/lib` (new touch utility module), `frontend/src/styles.css` for shared interaction classes. Validation: unit tests for timer, movement-threshold cancel, pointercancel handling, and no-fire-on-scroll behavior.

2. T2 - Integrate long-press action opening on grid items and preserve right-click behavior. Goal: provide touch action access on the highest-traffic surface with no desktop regression. Affected areas: `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/app/AppShell.tsx`. Validation: manual tablet check plus unit coverage for callback dispatch on long-press path.

3. T3 - Add explicit action buttons for grid and folder rows and convert folder expand/collapse affordance to button semantics. Goal: improve discoverability and tap reliability for frequent actions and navigation. Affected areas: `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/features/folders/FolderTree.tsx`, `frontend/src/styles.css`. Validation: manual check confirms button visibility, larger touch targets, and `aria-expanded` behavior.

4. T4 - Implement touch-safe “Move to…” flow reusing `api.moveFile` and define dialog UX. Goal: remove drag-only move dependency with a simple destination picker. Affected areas: `frontend/src/app/AppShell.tsx`, `frontend/src/features/folders` (new picker dialog or sheet), existing `api.moveFile` call sites. Validation: manual run moves one and multiple selected items to a chosen folder and handles cancel path correctly.

5. T5 - Add explicit upload button/file picker fallback while retaining drag-drop and mapping backend write restrictions to clear UI errors. Goal: ensure upload is possible on touch devices and failures are understandable. Affected areas: `frontend/src/app/AppShell.tsx`, `frontend/src/shared/ui/Toolbar.tsx` or `frontend/src/app/components/LeftSidebar.tsx`, `frontend/src/styles.css`. Validation: manual file-picker upload success path and backend-error display path.

6. T6 - Add menu positioning coordinate-space guard and viewport clamping for context and dropdown menus. Goal: prevent off-screen menus on narrow devices and scrolled containers. Affected areas: `frontend/src/app/menu/ContextMenu.tsx`, `frontend/src/shared/ui/Dropdown.tsx`, `frontend/src/styles.css`. Validation: unit tests for clamped coordinates and manual edge-open checks at 390px and 768px widths.

7. T7 - Add Sprint S1 regression coverage and smoke script updates. Goal: lock non-right-click action entrypoints and non-drag upload/move behavior. Affected areas: frontend tests under `frontend/src`, and lightweight manual script note in `docs/`. Validation: `cd frontend && npm run test` plus scripted manual S1 smoke run.

8. T8 - Implement viewer single-pointer pan with pointer events and `touch-action` handling. Goal: replace mouse-only drag with touch pan while preserving desktop behavior. Affected areas: `frontend/src/features/viewer/hooks/useZoomPan.ts`, `frontend/src/features/viewer/Viewer.tsx`, `frontend/src/styles.css`. Validation: manual tablet pan behavior and desktop drag/wheel non-regression check.

9. T9 - Add viewer pinch-to-zoom support with pointer distance tracking and cancel safety. Goal: complete touch zoom parity in primary viewer. Affected areas: `frontend/src/features/viewer/hooks/useZoomPan.ts`, `frontend/src/features/viewer/Viewer.tsx`. Validation: manual pinch in tablet profile and stable reset behavior after pinch end/cancel.

10. T10 - Implement compare viewer single-pointer pan plus `touch-action`/cancel handling. Goal: align compare interaction baseline with viewer behavior. Affected areas: `frontend/src/features/compare/hooks/useCompareZoomPan.ts`, `frontend/src/features/compare/CompareViewer.tsx`, `frontend/src/styles.css`. Validation: manual compare pan across both images without interaction lockups.

11. T11 - Add compare viewer pinch-to-zoom and sync-preserving behavior. Goal: provide touch zoom parity in compare mode without breaking compare semantics. Affected areas: `frontend/src/features/compare/hooks/useCompareZoomPan.ts`, `frontend/src/features/compare/CompareViewer.tsx`. Validation: manual pinch in compare mode and existing compare alignment behavior checks.

12. T12 - Convert sidebar resize handling to pointer-aware events. Goal: remove mouse-only dependency for panel width adjustments. Affected areas: `frontend/src/app/layout/useSidebars.ts`, `frontend/src/app/components/LeftSidebar.tsx`, `frontend/src/features/inspector/Inspector.tsx`, `frontend/src/features/folders/FolderTree.tsx`. Validation: manual tablet resize behavior and desktop pointer-device check.

13. T13 - Widen resize handles, define shared breakpoint constants, and add tablet panel constraints. Goal: avoid tiny touch targets and prevent center-content starvation at medium widths. Affected areas: `frontend/src/styles.css`, `frontend/src/shared/ui/Toolbar.tsx`, `frontend/src/app/AppShell.tsx`, and a shared breakpoint definition module in `frontend/src/lib`. Validation: manual checks at 1180px, 1024px, 900px, and 768px confirm usable content area and discoverable panel toggles.

14. T14 - Add tap-friendly open behavior and remove hover-only dependency in grid affordances. Goal: ensure users can open images and discover actions without desktop hover/double-click assumptions. Affected areas: `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/app/AppShell.tsx`, `frontend/src/styles.css`. Validation: manual tablet and phone checks for open behavior with clear action affordances.

15. T15 - Define and implement viewer navigation visibility rules by breakpoint, including narrow-screen controls. Goal: keep next/previous traversal reachable on phones. Affected areas: `frontend/src/features/viewer/Viewer.tsx`, `frontend/src/shared/ui/Toolbar.tsx`, `frontend/src/styles.css`. Validation: manual mobile check at <=480px and tablet check at >=768px confirm correct control mode switching.

16. T16 - Add lightweight mobile multi-select mode toggle. Goal: replace Shift/Ctrl dependence with explicit touch-select state. Affected areas: `frontend/src/app/AppShell.tsx`, `frontend/src/features/browse/components/VirtualGrid.tsx`, `frontend/src/shared/ui/Toolbar.tsx`. Validation: manual phone profile can enter/exit select mode and apply move/delete actions to selected items.

17. T17 - Normalize touch target sizes for critical controls and verify with style audit. Goal: reduce mis-taps and improve baseline touch accessibility. Affected areas: `frontend/src/styles.css`, `frontend/src/features/folders/FolderTree.tsx`, `frontend/src/shared/ui/Toolbar.tsx`, `frontend/src/app/components/LeftSidebar.tsx`. Validation: style audit confirms primary controls are at or near 44px targets on mobile and tablet breakpoints.

18. T18 - Create and execute device coverage checklist for iOS Safari and Android Chrome. Goal: catch browser-specific pointer/touch issues before signoff. Affected areas: new `docs/touch_readiness_checklist.md` and manual QA notes. Validation: completed checklist with pass/fail entries for iOS Safari and Android Chrome runs.

19. T19 - Final regression/documentation/packaging pass. Goal: lock behavior and handoff deployable assets and docs. Affected areas: frontend tests in `frontend/src`, `README.md`, `DEVELOPMENT.md`, and generated assets in `src/lenslet/frontend/`. Validation: `cd frontend && npm run test`, `cd frontend && npm run build`, `pytest -q`, packaged frontend smoke run.


## Validation and Acceptance


Validation is behavior-first and organized by sprint deliverables plus a final regression pass.

1. Sprint S1 acceptance requires that all frequent item and folder actions have a non-right-click path on touch, move actions succeed without drag-and-drop by calling `api.moveFile`, upload works through explicit file picker controls, and menu surfaces stay on-screen.

2. Sprint S2 acceptance requires that viewer and compare support touch pan and pinch zoom with `pointercancel` resilience and `touch-action` compatibility, with no regression to desktop mouse and wheel behavior.

3. Sprint S3 acceptance requires that at phone widths the UI remains navigable end-to-end for folder browse, item open, action access, selection mode, and viewer traversal, with clear action discoverability and no critical controls hidden.

4. Device coverage acceptance requires at least one completed pass on iOS Safari and one on Android Chrome using `docs/touch_readiness_checklist.md`, including long-press, move-to flow, upload fallback, viewer gestures, and menu edge placement.

5. Overall acceptance requires green backend/frontend test suites, successful frontend production build, and a local packaged frontend smoke run using the same dataset for desktop/tablet/mobile checks.


## Idempotence and Recovery


Each task is designed to be independently committable and safe to re-run. Re-executing the command set in this plan should not corrupt repository state, though generated frontend assets in `src/lenslet/frontend/` may be refreshed during UI packaging steps.

Recovery strategy is commit-scoped rollback, not repo-wide reset. If a task introduces regressions, revert only the affected commit(s), preserve unrelated local changes, and rerun the relevant sprint validation plus full `npm run test` and `pytest -q`.

Desktop behaviors remain available during migration by keeping existing right-click and drag paths while touch alternatives are introduced. This permits partial retry of touch-specific tasks without blocking daily desktop usage.


## Artifacts and Notes


Survey-derived hotpath risk snapshot used to scope this plan:

    Desktop-only blockers: right-click context actions, drag-only move/upload.
    Tablet risks: wheel/mouse-based viewer gestures, narrow resize handles, sidebar crowding.
    Mobile baseline gaps: hidden navigation controls, off-screen menus, modifier-key multi-select.

Expected sprint demo script for reviewers:

    1) Tablet profile: open actions from grid item without right-click, move selected item to folder, upload from file picker.
    2) Tablet profile: open viewer and compare, pan and pinch zoom with touch.
    3) Phone profile: browse folders, open image, navigate next/prev, access actions without hover or right-click.

Packaging note:

    If UI assets change, run `cd frontend && npm run build` and copy `frontend/dist/*` into `src/lenslet/frontend/` before final handoff.

Input-model thresholds used by this plan:

    Long-press delay: 500ms default.
    Long-press move-cancel threshold: 8 CSS px.
    Cancel conditions: pointercancel, scroll-start, pointer-up before threshold, or multi-touch start.


## Interfaces and Dependencies


No new runtime dependency is required for this plan. Implementation should use existing React, TypeScript, and browser Pointer Events APIs.

Required interface updates are intentionally minimal and centered on input parity.

1. `frontend/src/features/browse/components/VirtualGrid.tsx` should expose a touch action callback in props so long-press and explicit action-button paths can open the same action model as desktop context menu. A practical signature is `onItemActionRequest?: (path: string, anchor: { x: number; y: number }, source: 'contextmenu' | 'longpress' | 'button') => void`.

2. `frontend/src/app/menu/ContextMenu.tsx` should support viewport-safe positioning and optional close callbacks for touch interaction loops. A practical addition is `onRequestClose?: () => void` alongside clamped coordinate handling in viewport coordinate space.

3. `frontend/src/features/viewer/hooks/useZoomPan.ts` should expose pointer-based handlers (`handlePointerDown`, `handlePointerMove`, `handlePointerUp`, `handlePointerCancel`) while preserving current `handleWheel` support for desktop.

4. `frontend/src/features/compare/hooks/useCompareZoomPan.ts` should mirror the same pointer-handler model so compare and viewer modes behave consistently.

5. Move and upload fallbacks should continue to use existing API contracts in `frontend/src/api/client.ts`, specifically `api.moveFile(src: string, dest: string)` and `api.uploadFile(dest: string, file: File)`, to avoid backend contract expansion in this phase.

6. Responsive breakpoint values should be centralized in a shared definition consumed by both TS and CSS-adjacent logic to avoid drift between `frontend/src/shared/ui/Toolbar.tsx` and stylesheet media rules.


Revision note: updated on 2026-02-07 after required subagent review to split oversized gesture/layout tickets, add explicit input-model rules, add coordinate-space clamping scope, and include iOS Safari plus Android Chrome checklist validation.
