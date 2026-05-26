# 2026-05-26 Interaction Polish Execution Plan


## Outcome + Scope Lock


After implementation, Lenslet should feel reliable in the interaction paths called out in `docs/20260525_re_review.md`: toolbar zoom requests survive image-load races, compare image loading cannot reset an active inspection, viewer and compare keyboard navigation does not fire from controls or background handlers, pan/zoom and resize work is frame-coalesced and cancellable, divider dragging survives normal lifecycle edges, and `VirtualGrid.tsx` no longer leaves scroll timers or animation frames behind.

Goals:

1. Fix the remaining local source issues behind the reviewer's zoom, compare, keyboard, transform, resize, divider, and browse lifecycle concerns.
2. Preserve the previous responsive and overall cleanup work; this plan is a follow-up to `docs/20260525_overall_cleanup_execution_plan.md`, not a replacement.
3. Use existing local primitives such as `imageTransform.ts`, `useModalFocusTrap`, responsive layout policy, and browser evidence scripts.
4. Add browser evidence for already-fixed phone, coarse-pointer, and reduced-motion promises without turning those into implementation tickets unless they fail.
5. Keep the work small enough to review sprint by sprint, with no new dependency and no broad grid or styling rewrite.

Non-goals:

1. Do not rewrite the frontend stack, add a gallery/gesture/modal/accessibility library, or change backend storage/API contracts.
2. Do not perform the full proposed `VirtualGrid.tsx` split into every possible hook.
3. Do not change keyboard shortcut meanings, except to scope them away from controls, modifier combos, inactive dialogs, and background surfaces.
4. Do not add deep zoom, image tiling, persistent preview generation, ranking-mode polish, or repo-wide formatting.
5. Do not remediate npm audit/tooling findings in this plan.

Pre-approved behavior changes:

1. Viewer zoom requests may remain pending until the active image, container, and transform geometry can honor them; a request is consumed only after success.
2. `useZoomPan` may expose a readiness or geometry-version signal, or otherwise retry pending zoom requests from image-load and resize readiness.
3. Compare may fit a new pair once after both current blob URLs have loaded and both natural sizes are valid, unless the user has already interacted with that pair.
4. Viewer and compare transform state may be internally represented as one object and flushed at most once per animation frame, while keeping the visible UI contract unchanged.
5. ResizeObserver work may be coalesced through stored RAF ids and canceled on cleanup.
6. `restoreImageTransformForCenter` may accept clamp options so viewer pan slack remains consistent across resize.
7. Viewer, compare, and background keyboard handlers may ignore buttons, menus, inputs, textareas, selects, contenteditable nodes, modifier-key combos, and non-topmost dialog contexts.
8. Compare divider dragging may move into a local hook that recomputes stage geometry and owns listener/capture cleanup.
9. Viewer and compare image alt text may use file labels or paths instead of generic labels, and dialog focus styling may be restored where blanket outline suppression hides useful focus.

Requires sign-off before implementation:

1. Adding or upgrading npm, Python, or system dependencies.
2. Replacing the existing transform hooks with a third-party viewer, gesture, or pan/zoom library.
3. Broadly rewriting `VirtualGrid.tsx`, `styles.css`, `AppShell.tsx`, or all keyboard handling outside viewer/compare/background shortcut scoping.
4. Removing commands or changing shortcut meanings rather than scoping when they apply.
5. Changing persisted localStorage/workspace schema or backend API payloads.
6. Accepting an implementation sprint without the primary browser evidence for that sprint unless the user explicitly approves the downgrade.

Deferred or out of scope:

1. Full `VirtualGrid.tsx` decomposition into selection, keyboard, long-press, drag-ghost, hover-preview, and rendering layers is deferred.
2. Ranking fullscreen keyboard/motion polish is deferred.
3. A full accessibility audit outside viewer/compare and touched browse controls is deferred.
4. New browser harness architecture is deferred; extend the existing evidence path or add small fixture helpers only where needed.
5. Large CSS re-theming or animation design changes are deferred.


## Context


No `PLANS.md` was found in the current repo scan. This document follows the user-provided repository instructions, the Lenslet skill guidance, and the `plan-writer` plan format. `docs/agents_archive/` remains historical context only.

The reviewer notes in `docs/20260525_re_review.md` were written from a GitHub source review and flagged several items that are already partly addressed in the local working tree. Current local source shows `.viewer-mobile-nav` is explicitly displayed under `@media (max-width: 480px)`, grid and folder action buttons are explicit under `@media (pointer: coarse)`, broad reduced-motion CSS exists, modal focus trapping exists in `useModalFocusTrap`, and `scripts/overall_cleanup_browser.py` already covers adaptive layout, hover preview, viewer/compare resize focus, browse `Ctrl+wheel`, and comparison export.

The remaining source-level problems are still direct and worth fixing. `Viewer.tsx` consumes `requestedZoomPercent` even when `zoomToPercent` returns `false`. `useZoomPan.ts` and `useCompareZoomPan.ts` push multiple React state updates for each pointer/pinch/wheel step and schedule uncanceled resize RAF callbacks. `restoreImageTransformForCenter` clamps strictly and cannot preserve the viewer's pan-slack contract. `CompareViewer.tsx` calls `fitAndCenter()` from both image-load callbacks, so a late image can reset a user who has already started inspecting. Viewer and compare install broad window keydown listeners, while `AppShell.tsx` also has a background shortcut listener that must stay inert under viewer/compare. `VirtualGrid.tsx` does not clear its scroll-idle timeout or cancel its scroll animation RAF on unmount. The compare divider drag stores a stale rect and owns global listeners in an inline pointer handler. Viewer and compare still expose generic image alt text.

Scope lock decisions: no user-blocking questions are needed before drafting because the reviewer notes define the desired product direction, this is a pre-release alpha, and this plan keeps behavior changes within the requested polish areas. Minor script placement uncertainties should be resolved during implementation with the smallest local choice and then recorded in this plan's Progress Log.

Plan review feedback incorporated: the plan was reduced from four sprints to three implementation sprints; evidence-only phone/coarse/reduced-motion work moved into preflight/final evidence; the standalone `VirtualGrid` extraction ticket was removed; zoom retry, compare initial-fit semantics, background keyboard handling, transform scheduling invariants, and browser fixture requirements were made explicit.


## Plan of Work


The plan uses one preflight evidence step, three implementation sprints, and nine implementation tickets. Each implementation sprint must produce a runnable browser state and update this document continuously, especially Progress Log and Artifacts and Handoff. After each sprint is complete, add clear handoff notes before starting the next sprint.

For minor script-level uncertainties, such as whether a route-delay helper belongs directly in `scripts/overall_cleanup_browser.py` or a small shared helper, proceed according to this approved plan to maintain momentum. After the sprint, ask for clarification and apply follow-up adjustments if the user wants a different placement.

For any ticket with non-trivial code changes, the implementing agent must use the `better-code` skill before and during implementation. The agent must state the acceptance criteria, core invariants, smallest robust approach, and evidence-backed validation before editing. Skip this only for copy-only docs edits or similarly trivial non-code work.

Delegate subagents early to find real codepaths/files to change when that reduces context load or speeds execution. Let those subagents continue long enough to produce useful results; if work is still in progress after 10 minutes, ask for a brief progress update plus why more time is needed. Do not terminate subagents early to return faster. This applies especially to cleanup and review subagents once those gates start.

### Scope Budget and Guardrails


Scope budget is three implementation sprints, nine implementation tickets, and a narrow frontend file set: `Viewer.tsx`, `useZoomPan.ts`, `CompareViewer.tsx`, `useCompareZoomPan.ts`, `imageTransform.ts`, `keyboard.ts` or a small dialog-key helper, `AppShell.tsx` only for background shortcut scoping if needed, `VirtualGrid.tsx` plus an optional small scroll helper, `styles.css` only for focus/label polish if evidence requires it, targeted Vitest files, `scripts/overall_cleanup_browser.py`, and packaged frontend assets at final handoff.

Debloat and removal targets:

1. Remove false-success zoom request consumption.
2. Remove compare load-time refits after user interaction.
3. Remove broad dialog/background key handling that fires from controls or inactive contexts.
4. Remove duplicated uncoalesced RAF/ResizeObserver lifecycle paths in viewer and compare.
5. Remove strict resize clamping where viewer pan slack is the active interaction contract.
6. Remove `VirtualGrid` timeout/RAF leak paths; extract `useVirtualGridScrollState` only if it reduces lifecycle risk or makes cleanup testable.
7. Track net effect with `git diff --stat`, focused `rg` checks, and line counts for touched large files.

Quality guardrails:

1. Browser evidence is primary for reviewer-visible polish; unit tests and builds are secondary fast gates.
2. Do not hide interaction failures with CSS opacity, z-index, or clipping while leaving behavior broken.
3. Prefer small shared primitives over broad refactors, but do not keep copy-pasted lifecycle bugs just to avoid adding a helper.
4. Keep each ticket atomic, committable, and tied to a reviewer concern.
5. If implementation grows beyond the named file set or changes shortcut semantics, stop and request sign-off.

### Preflight Evidence


Before Sprint 1 implementation, extend or run the existing browser evidence path for already-fixed promises: phone viewer Prev/Next at `390x844`, coarse-pointer grid/folder action buttons visible without hover, and reduced-motion emulation disabling nonessential animations. If any preflight assertion fails, fix it in the closest sprint that owns the failing surface rather than creating a broad new sprint.

Browser fixture requirements should be concrete. For zoom-load-race and compare-late-load checks, add local route throttling, delayed media response helpers, or fixture-specific request interception in the browser harness so the tests exercise real delayed readiness rather than a proxy wait. For coarse pointer and reduced motion, use Playwright emulation. For divider resize, drive an actual divider drag and viewport resize around it.

### Sprint Plan


Sprint 1 goal: close correctness races and keyboard scope.

Demo outcome: a quick toolbar zoom survives viewer load timing; compare late image load cannot reset an active inspection; viewer, compare, and background shortcuts do not navigate or mutate state from controls or inactive contexts; viewer/compare full-size images have useful labels.

Tasks:

1. `IP-1`: Fix pending viewer zoom requests.
   Change `Viewer.tsx` so `onZoomRequestConsumed` runs only when `zoomToPercent` returns `true`. Add a real retry signal, such as a `geometryVersion` from `useZoomPan`, or retry from image-load and resize readiness so a failed request does not remain pending forever. Preserve the toolbar slider contract in `AppShell.tsx`. Validation: a focused test or browser route-delay scenario opens viewer, requests 200% before full image readiness, waits for load, and observes the final zoom label or transform near 200%; the request clears only after a successful transform.
2. `IP-2`: Prevent compare late-load refits after interaction.
   Introduce pair-generation and user-interaction tracking for compare. Fit the pair once after both current blob URLs have loaded and both natural image sizes are valid, unless user interaction has already happened for that pair. If only one side loads and the user pans, zooms, pinches, drags the divider, or explicitly resets, the late second load must not refit. Explicit reset remains the user-controlled way to fit again. Validation: focused hook/component tests cover initial fit, late-load freeze, and explicit reset; browser evidence delays one compare-side load, applies user transform, and proves the transform remains stable when the late side becomes ready.
3. `IP-3`: Scope viewer, compare, and background navigation keys.
   Add a small shared dialog navigation helper or equivalent route that is active only for the current topmost dialog, ignores controls, contenteditable nodes, disabled navigation states, and modifier-key combos such as `Ctrl+A`, `Meta+A`, and `Alt+ArrowLeft`, and composes with `useModalFocusTrap` for Escape/Tab. Ensure `AppShell.tsx` background shortcuts remain inert while viewer or compare is active. Validation: tests cover ignored targets, modifier combos, disabled navigation, active-dialog checks, and background shortcut suppression; browser evidence proves A/D/arrows do not navigate while focus is on close/prev/next/slider controls.
4. `IP-4`: Apply viewer/compare label and focus polish tied to touched components.
   Use file names or paths in full-size viewer/compare alt text where helpful, keep decorative thumbnails empty or explicitly decorative, and remove only focus-outline suppression that hides meaningful keyboard focus in touched dialog controls. Validation: tests or browser assertions confirm full-size labels are no longer generic and keyboard focus remains visible on dialog controls.

Sprint 2 goal: remove transform and resize lifecycle jitter.

Sprint 1 handoff notes, 2026-05-26 02:38 UTC: closed in iteration 1. The viewer now retries pending toolbar zoom requests through a hook geometry-version signal and consumes the request only after `zoomToPercent` succeeds. Compare now tracks pair readiness and pair interaction state so the first successful fit happens only after both current images are loaded and never after user inspection begins. Viewer, compare, and AppShell background shortcuts now share scoped keyboard helpers that ignore controls, modifiers, disabled directions, and non-topmost modal contexts while preserving existing `Ctrl+B` and `Ctrl+Alt+B` sidebar behavior. Full-size viewer/compare images have label/path-based alt text, decorative compare thumbnails are hidden from assistive text, and touched dialog surfaces no longer suppress useful focus outlines. Browser Sprint 1 evidence is available at `/tmp/lenslet-interaction-polish-sprint1.json`, with success screenshots under `/tmp/lenslet-overall-cleanup-browser-screenshots/`.

Demo outcome: viewer and compare keep canonical transforms in refs, flush React-visible transform state at most once per animation frame, cancel pending frame work on cleanup, and preserve the same inspection region across resize without pan-slack snap.

Tasks:

5. `IP-5`: Make center restoration accept clamp options.
   Extend `restoreImageTransformForCenter` with optional clamp options and update existing callers deliberately. Viewer resize should pass `VIEWER_PAN_SLACK`; compare can remain strict unless tests show a product reason to add slack there. Validation: `frontend/src/lib/__tests__/imageTransform.test.ts` covers strict and slack restore behavior for wide, tall, and smaller-than-container images.
6. `IP-6`: Frame-schedule viewer transform rendering and resize work.
   Update `useZoomPan.ts` with this invariant: canonical transform lives in refs; React-visible transform is a single object flushed at most once per RAF; pending transform and resize RAF ids are canceled on cleanup; the toolbar zoom label does not read stale scale after the final flush. Coalesce ResizeObserver callbacks with a stored `resizeRafRef` and avoid four independent state updates per pointer move. Validation: hook tests with fake RAF timers cover scheduler behavior, cleanup, and resize coalescing; browser evidence repeats viewer wheel/pan/resize checks with stable center tolerance and no stale update errors.
7. `IP-7`: Frame-schedule compare transform rendering and resize work.
   Apply the same scheduling and cleanup invariant to `useCompareZoomPan.ts`, keeping the public hook return shape stable unless a small object-shaped internal state is cleaner. Run a small pre-test or spike on the single-transform-state shape before changing both images' flush path. Validation: compare hook tests cover paired transform flushing, resize RAF coalescing, cleanup, and existing browser compare resize checks remain green.

Sprint 2 handoff notes, 2026-05-26 03:06 UTC: closed in iteration 2. `restoreImageTransformForCenter` now accepts clamp options, with viewer resize restoration using `VIEWER_PAN_SLACK`. Viewer and compare hooks now keep canonical transform state in refs, expose the same public return shape, and coalesce React-visible transform updates through a shared cancellable RAF scheduler. ResizeObserver work is coalesced and canceled on cleanup in both hooks. Browser evidence showed compare short-height resize also needed resize-only pan slack, so compare resize restoration uses the same bounded slack while normal compare pan/zoom remains strict. The toolbar zoom request path now waits for `imageReady`, avoids duplicate ready resets, handles range `input` events, and keeps requested zoom visible while geometry catches up. Evidence is available at `/tmp/lenslet-interaction-polish-sprint2.json`.

Sprint 3 goal: harden remaining lifecycle edges and finish evidence.

Demo outcome: divider dragging behaves through resize/capture loss/unmount, `VirtualGrid` no longer leaves scroll timers or scroll RAFs behind, preflight/final reviewer promises are covered by browser evidence, frontend assets are regenerated when needed, and cleanup/review gates have no unresolved blockers.

Tasks:

8. `IP-8`: Extract and harden compare divider dragging.
   Move divider drag handling into `useDividerDrag` or a similarly local helper owned by compare. Recompute the stage rect on move or from current stage bounds, handle `lostpointercapture`, and clean up listeners on unmount. RAF-throttle `setSplitPct` only if direct updates are measurably noisy or tests show churn. Validation: tests cover clamping, stale rect avoidance, cleanup, and lost capture; browser evidence drags the divider, resizes during or after drag, and asserts split stays between 5 and 95 without stuck listeners.
9. `IP-9`: Fix `VirtualGrid` scroll lifecycle cleanup.
   Clear the scroll-idle timeout and cancel `scrollAnimRef` on unmount. Extract `useVirtualGridScrollState` only if keeping this inside the large component makes cleanup or tests awkward; do not extract `GridCell` or unrelated behavior for line-count optics. Validation: targeted tests cover timeout and RAF cancellation, existing keyboard scroll-into-view behavior still works, and the large-tree probe is required only if the change alters grid behavior/rendering beyond cleanup and helper extraction.

Sprint 3 handoff notes, 2026-05-26 03:26 UTC: closed in iteration 3. Compare divider dragging now lives in `useDividerDrag`, recomputes current stage bounds on every move, clamps split to 5-95, and cleans pointer listeners/capture on pointer end, cancel, lost capture, and unmount. `VirtualGrid` now clears the scroll-idle timeout and cancels any pending scroll animation frame during cleanup through a tiny tested lifecycle helper; grid rendering behavior was not otherwise changed, so the conditional large-tree probe was not triggered. The final browser evidence includes real divider drag, resize-after-drag, and lost-capture stability checks. Final validation also exposed a `Ctrl+B` regression from focused rail controls; `AppShell` now lets the sidebar hotkey run from non-text controls while still ignoring text inputs and modal contexts. Packaged frontend assets were regenerated from the final production build.

### Task Gate Routine


Every implementation ticket must use this gate routine.

0. Plan gate.
   The code agent briefly restates the ticket goal, acceptance criteria, material assumptions, and files expected to change. If the ticket includes substantive code work, invoke the `better-code` skill first and state the key invariants, smallest robust approach, and verification evidence. If an ambiguity would change behavior outside the approval matrix, stop and ask.
1. Implement gate.
   Implement the smallest coherent slice that satisfies the ticket. Avoid speculative features, one-off abstractions, unrelated cleanup, broad refactors, and behavior changes outside the approval matrix. Run the ticket-specific validation before moving on.
2. Cleanup gate.
   After each complete implementation sprint, run the `code-simplifier` routine below and apply only conservative cleanup.
3. Review gate.
   After cleanup, run the review routine below. Address findings and rerun review when needed before closing the sprint.

### code-simplifier routine


After each complete implementation sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan the current sprint changes. Start with non-semantic cleanup only: formatting or lint autofixes, obvious dead code removal, small readability edits that do not change behavior, and docs/comments that reflect what is already true.

Keep this pass conservative. Do not expand into semantic refactors unless explicitly approved. Once this cleanup subagent starts, do not interrupt or repurpose it just to save time. If it runs long, wait or request a progress update; fall back to manual cleanup review only if the subagent is unavailable, fails, or the user explicitly approves the downgrade.

### review routine


After each complete implementation sprint and after the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Use the best available model in the environment with `reasoning_effort` set to `medium`. Review the post-cleanup diff, apply fixes, and rerun review when needed to confirm resolution.

Once the review subagent starts, do not interrupt, repurpose, or terminate it to save time or reclaim control of the thread. Treat the review gate as blocking unless the user explicitly approves a downgrade, or the subagent is unavailable or fails after a reasonable wait plus progress check. Manual diff review is a fallback only when the review subagent is unavailable, fails, or the user explicitly approves that downgrade.


## Validation and Acceptance


Primary acceptance checks are live-browser checks that reproduce the reviewer's interaction paths. Secondary checks are fast unit, component, build, lint, and source-inspection gates.

Primary per-sprint checks:

1. Preflight.
   Run phone, coarse-pointer, and reduced-motion evidence. Expected: mobile viewer nav buttons are visible and navigate at `390x844`; coarse-pointer grid/folder action buttons are visible without hover; reduced-motion emulation disables nonessential animations/transitions. If any fail, fix in the closest owning sprint.
2. Sprint 1.
   Run zoom-load-race, compare-late-load, dialog-keyboard, background-shortcut, label, and focus evidence. Expected: a pre-readiness 200% zoom request is honored and consumed only after success; compare late load does not reset a user transform; A/D/arrows and AppShell shortcuts do not fire from dialog controls or background contexts; full-size image labels are useful and focus is visible.
3. Sprint 2.
   Run viewer/compare zoom, pan, resize, and cleanup browser checks. Expected: frame-coalesced transforms preserve the inspected region within tolerance, resize callbacks are coalesced, pending RAF work is canceled on close/navigation, and viewer pan slack does not snap away during resize.
4. Sprint 3.
   Run divider-drag, browse lifecycle, preflight reviewer promises, packaged asset, cleanup, and review checks. Expected: divider split remains sane through drag/resize/capture loss; no stuck listeners remain; grid keyboard scroll and scroll idle still work; all prior sprint scenarios remain green.

Primary final gates:

1. Run the interaction-polish browser evidence:

       python scripts/overall_cleanup_browser.py --output-json /tmp/lenslet-interaction-polish-final.json

2. Run the existing GUI smoke:

       python scripts/gui_smoke_acceptance.py

3. Run the responsive geometry harness to protect previous resize work:

       python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry-interaction-polish.json

4. Run the large-tree probe only if `VirtualGrid` behavior or rendering changes beyond timeout/RAF cleanup and a small scroll helper:

       python scripts/playwright_large_tree_smoke.py --dataset-dir data/fixtures/large_tree_40k --output-json /tmp/lenslet-large-tree-interaction-polish.json

   Iteration 3 result: not run because `VirtualGrid` changed only timeout/RAF cleanup plus a tiny tested helper, with no rendering or behavior changes beyond lifecycle cleanup.

5. Manually check one phone viewport (`390x844`), one short desktop viewport (`1024x480`), one half-width desktop viewport, and one coarse-pointer emulation. Expected: no invisible commands, no stale image reset, no keyboard surprise from controls, no janky resize snap, and no document horizontal overflow.

Secondary gates:

1. Run focused frontend tests while developing each sprint:

       cd frontend && npm run test -- src/lib/__tests__/imageTransform.test.ts src/features/viewer/hooks/__tests__/useZoomPan.test.ts

2. Run any new focused tests for compare, keyboard, divider, and grid lifecycle:

       cd frontend && npm run test -- src/features/compare src/shared/hooks src/features/browse

3. Run the full frontend suite before handoff:

       cd frontend && npm run test

4. Build and sync frontend assets if UI output changed:

       cd frontend && npm run build
       rsync -a --delete frontend/dist/ src/lenslet/frontend/

5. Run repository lint before handoff:

       python scripts/lint_repo.py

6. Use source checks as evidence of removed failure paths:

       rg -n "onZoomRequestConsumed|requestAnimationFrame\\(\\(\\) => preserveCenterAfterResize|fitAndCenter\\(\\)|window.addEventListener\\('keydown'|scrollAnimRef|viewer-mobile-nav|pointer: coarse" frontend/src
       wc -l frontend/src/features/browse/components/VirtualGrid.tsx frontend/src/features/viewer/hooks/useZoomPan.ts frontend/src/features/compare/hooks/useCompareZoomPan.ts

Acceptance requires at least one direct primary gate for each root failure path. A sprint cannot be closed if the reviewer-visible behavior still fails in its main browser scenario, even if unit tests pass.


## Risks and Recovery


The main risk is turning targeted polish into a broad interaction rewrite. Recovery is to keep each sprint shippable, land direct fixes first, and defer full grid/hook decomposition unless a task cannot be made reliable without it.

Transform scheduling can introduce stale UI labels or missed updates if refs and React state diverge. Recovery is to keep canonical state in refs, flush a single React-visible transform object per frame, preserve current hook outputs during migration, and use browser assertions for zoom labels/transforms.

Pending zoom retry can get stuck if no readiness signal changes after a failed attempt. Recovery is to expose a concrete geometry/readiness signal from the hook or retry directly from image-load/resize readiness and test delayed media responses.

Compare late-load changes can regress initial fit for legitimate new pairs. Recovery is to make pair generation explicit, test both-images-ready and post-interaction cases separately, and keep explicit reset as the user-controlled fit path.

Keyboard scoping can accidentally disable shortcuts or leave background shortcuts active. Recovery is to keep shortcut meanings unchanged, add target/modifier/topmost-dialog tests, and verify both keyboard and button navigation in browser.

Browser evidence can become too large if all assertions are added inline. Recovery is to extract common helpers into `scripts/smoke_harness.py` or a small local helper while keeping one primary command for the final gate. This is a script-organization adjustment, not a product behavior change.

Rollback is sprint-based. If a sprint regresses primary behavior, revert or isolate only that sprint's changes, keep earlier sprint evidence intact, and update Progress Log with the failure and recovery decision. Retrying is idempotent: browser scripts write to `/tmp`, frontend builds overwrite `frontend/dist`, and packaged assets can be regenerated from the current frontend build.


## Progress Log


- [x] 2026-05-26 01:59 UTC: Read `docs/20260525_re_review.md`, existing planning docs, Lenslet skill guidance, and current frontend codepaths.
- [x] 2026-05-26 01:59 UTC: Locked scope as a follow-up interaction polish plan; no new dependencies, no backend changes, no full `VirtualGrid` rewrite.
- [x] 2026-05-26 01:59 UTC: Ran required subagent review with `reasoning_effort=medium`; incorporated de-scoping, zoom retry, compare fit, keyboard, transform invariant, and browser fixture feedback.
- [x] Preflight: Add or run phone/coarse/reduced-motion evidence and convert failures into owning sprint work.
- [x] Sprint 1: Implement zoom request retry, compare late-load freeze, dialog/background keyboard scope, and label/focus polish.
- [x] Sprint 2: Implement pan-slack restoration plus frame-coalesced viewer/compare transforms and resize RAF cleanup.
- [x] Sprint 3: Implement divider drag lifecycle cleanup, `VirtualGrid` scroll cleanup, final validation, packaged asset sync, and handoff.
- [x] 2026-05-26 02:38 UTC: Iteration 1 closed Sprint 1. Added `--only-sprint1` browser evidence covering phone viewer nav, coarse pointer action visibility, reduced motion, delayed viewer zoom request retention, compare late-load freeze, keyboard scoping from controls/modifiers, useful full-size labels, and Sprint 1 success screenshots.
- [x] 2026-05-26 02:38 UTC: Validated with focused Vitest checks, full frontend suite, production build plus packaged asset sync, Sprint 1 browser evidence, repo lint, conservative cleanup scan, and two code-review passes. Review findings on `Ctrl+Alt+B` and screenshot artifacts were fixed and rereviewed clean.
- [x] 2026-05-26 02:38 UTC: Noted that the full legacy browser command still reaches the planned Sprint 2 viewer resize center-drift failure; keep this as the next sprint target rather than accepting the final browser gate yet.
- [x] 2026-05-26 02:44 UTC: Iteration 2 started Sprint 2. Acceptance criteria: `restoreImageTransformForCenter` gets explicit clamp options, viewer resize restores with `VIEWER_PAN_SLACK`, viewer and compare transforms keep canonical refs while React-visible state is RAF-coalesced, and ResizeObserver work is coalesced/canceled.
- [x] 2026-05-26 02:48 UTC: Initial Sprint 2 browser evidence cleared the prior viewer short-height failure and exposed compare B short-height center drift under strict resize clamping; applying pan slack only to compare resize restoration while keeping normal compare pan/zoom strict.
- [x] 2026-05-26 02:52 UTC: The next browser run caught a Sprint 1 regression where the complete-image fallback could reset an already-ready viewer image after a pending toolbar zoom; made viewer image readiness idempotent per resource before rerunning evidence.
- [x] 2026-05-26 02:56 UTC: Follow-up browser evidence showed the toolbar zoom request could still run before fitted image geometry if natural dimensions were available early. The viewer now gates pending zoom consumption on `imageReady`, keeping the request pending until initial fit has completed.
- [x] 2026-05-26 03:00 UTC: Tightened the toolbar zoom slider contract to emit pending zoom requests on `input` as well as `change` and keep the requested value visible while the viewer waits for ready geometry.
- [x] 2026-05-26 03:06 UTC: Iteration 2 closed Sprint 2 with focused tests, full frontend tests, production build plus packaged asset sync, full interaction-polish browser evidence, repo lint, conservative cleanup subagent, and code-review subagent. No review findings remain.
- [x] 2026-05-26 03:14 UTC: Iteration 3 started Sprint 3. Acceptance criteria: compare divider dragging must survive current-stage geometry changes, pointer end/cancel/lost capture, resize, and unmount; `VirtualGrid` must clear its scroll-idle timeout and cancel scroll animation RAF work on cleanup without changing grid rendering.
- [x] 2026-05-26 03:18 UTC: Implemented `useDividerDrag` with testable clamping/session helpers and wired compare to use it instead of inline global pointer listeners. Added browser evidence for real divider drag, resize-after-drag, and lost-capture stability.
- [x] 2026-05-26 03:18 UTC: Implemented `virtualGridScrollLifecycle` helper coverage and wired `VirtualGrid` cleanup to clear scroll idle timeout and cancel pending scroll animation frames on unmount.
- [x] 2026-05-26 03:21 UTC: Final GUI smoke initially failed because `Ctrl+B` was ignored while focus remained on the collapsed rail Folder button. Repaired AppShell shortcut ordering so sidebar hotkeys work from non-text controls while text/editable controls and modal contexts remain scoped out.
- [x] 2026-05-26 03:24 UTC: Responsive geometry harness initially failed because it still queried generic viewer/compare alt text that Sprint 1 intentionally replaced. Updated the harness to use stable `data-viewer-image` and `data-compare-image` selectors.
- [x] 2026-05-26 03:26 UTC: Iteration 3 closed Sprint 3 and final acceptance with focused tests, full frontend tests, production build plus packaged asset sync, final interaction-polish browser evidence, GUI smoke, responsive geometry harness, repo lint, source checks, conservative cleanup gate, and code-review gate. No review findings remain; large-tree probe was not required.


## Artifacts and Handoff


Reviewer source: `docs/20260525_re_review.md`.

Existing overlap to preserve: `docs/20260525_overall_cleanup_execution_plan.md`, `docs/20260525_responsive_layout_structural_plan.md`, `scripts/overall_cleanup_browser.py`, `scripts/responsive_geometry_harness.py`, and `scripts/gui_smoke_acceptance.py`.

Expected evidence outputs:

1. `/tmp/lenslet-interaction-polish-final.json`
2. `/tmp/lenslet-responsive-geometry-interaction-polish.json`
3. `/tmp/lenslet-large-tree-interaction-polish.json`, only if the conditional large-tree gate is triggered.

Iteration 1 evidence outputs:

1. `/tmp/lenslet-interaction-polish-sprint1.json`
2. `/tmp/lenslet-overall-cleanup-browser-screenshots/viewer_zoom_load_race_success_0_0.png`
3. `/tmp/lenslet-overall-cleanup-browser-screenshots/compare_late_load_success_0_0.png`

Iteration 2 evidence outputs:

1. `/tmp/lenslet-interaction-polish-sprint2.json`
2. `/tmp/lenslet-overall-cleanup-browser-screenshots/viewer_zoom_load_race_success_0_0.png`
3. `/tmp/lenslet-overall-cleanup-browser-screenshots/compare_late_load_success_0_0.png`

Iteration 3 final evidence outputs:

1. `/tmp/lenslet-interaction-polish-final.json`
2. `/tmp/lenslet-responsive-geometry-interaction-polish.json`
3. GUI smoke acceptance passed via `python scripts/gui_smoke_acceptance.py` and emitted JSON evidence to stdout.
4. Large-tree evidence was not produced because the conditional trigger was not met.

Handoff notes for the implementing agent: all planned sprints and tickets are complete. Final browser and smoke evidence passed, packaged frontend assets were regenerated from the production build, cleanup and review gates reported no actionable issues, and no blockers remain.
