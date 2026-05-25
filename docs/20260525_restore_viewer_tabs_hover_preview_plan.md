# 2026-05-25 Restore Viewer Tabs and Original Hover Preview Plan


## Outcome + Scope Lock


This is a corrective regression plan. The user clarified that the old behaviors were intentional and wanted. The previous overall cleanup plan made changes that broke those behaviors by treating full-viewport viewer/compare overlays and thumbnail-based hover preview as desired outcomes. That was wrong for the product behavior the user expects.

After implementation, opening viewer or compare on desktop/tablet with the left and right side regions visible should keep those side regions visible and visually stable. The image surface should be contained in the center viewer container, not stretched across the whole app viewport. The image should not flash and then disappear. Hover preview should show a large preview from the original image file, materially larger than the grid thumbnail, not a thumbnail-sized preview that looks basically the same as the cell.

Goals:

1. Restore desktop/tablet viewer and compare containment to the center content area while preserving visible left and right side regions when the normal layout can show them.
2. Remove viewer/compare image flashing or disappearing introduced by the previous lazy/fallback/thumbnail/opacity path.
3. Restore hover preview to a large original-file preview, bounded by viewport but not thumbnail-sized.
4. Preserve the useful safety pieces that do not conflict with the old behavior: stale-response guards, URL cleanup, and request cancellation where the fetch path supports it.
5. Add browser evidence for the exact user-reported flows so completion cannot be claimed from proxy checks.

Non-goals:

1. Do not continue the previous full-viewport overlay or thumbnail-hover assumptions.
2. Do not rework justified-row layout, menu semantics, comparison export, or bundle splitting unless directly required by these regressions.
3. Do not add new backend APIs, tiled-image support, server-side preview derivatives, or frontend dependencies.
4. Do not remove the modal focus work wholesale unless it is proven to be the direct source of the side-region regression and a narrower fix fails.
5. Do not force desktop side panels onto phone, narrow, or short-height layouts where the existing responsive policy would normally suppress them.

Pre-approved behavior changes:

1. On desktop/tablet layouts where side regions can fit, viewer/compare overlay mode should not suppress the side regions merely because overlay mode is active.
2. On those layouts, viewer/compare overlay insets should match the effective left/right widths, so the image surface stays in the center container.
3. Side regions should remain visible while viewer/compare is open, but viewer/compare keep modal focus ownership by default. Visible side regions remain decorative/inert under the modal unless the user later asks for them to be interactive.
4. Hover preview may fetch original `/file` content again and should display close to the old large overlay scale, such as up to about `80vw`/`80vh` where viewport size allows.
5. Tests and browser assertions that encode thumbnail-only hover preview or full-viewport overlay assumptions may be removed or rewritten because those assumptions are now known wrong.

Requires sign-off before implementation:

1. Making side regions interactive while viewer/compare is open.
2. Removing modal focus trapping entirely.
3. Removing lazy bundle splitting beyond viewer/compare if a smaller fallback/placement fix is enough.
4. Adding backend preview endpoints, new dependencies, or persistent cache-policy changes.
5. Changing phone/narrow/short-height overlay policy beyond preserving existing responsive behavior.

Deferred or out of scope:

1. Large-image tiling and bandwidth optimization for original hover preview.
2. A broader redesign of fullscreen mode.
3. A full accessibility audit beyond the focus/inert behavior touched by this regression.
4. Re-running the completed cleanup epic except for checks needed to prove these fixes do not regress adjacent behavior.


## Context


No `PLANS.md` was found in the repo scan. This plan follows the user-provided repository instructions, Lenslet skill guidance, and the `plan-writer` process.

The previous plan was implemented through recent commits including `4fba010 feat: harden viewport menus and hover preview`, `2acc740 fix: preserve overlay inspection context`, and `2bb9104 feat: split secondary gallery surfaces`. The user now reports that these changes broke wanted old behavior.

Current source inspection points to two direct regression clusters:

1. `frontend/src/app/layout/responsiveLayoutPolicy.ts` suppresses sidebars when `overlayActive` is true and returns `overlayInsets: { left: 0, right: 0 }`. That makes viewer/compare a whole-app overlay and erases the visible left/right regions that the user wanted preserved.
2. `frontend/src/app/AppShell.tsx` lazy-loads viewer and compare through fallback overlays, and `Viewer.tsx` / `CompareViewer.tsx` combine thumbnail placeholders, `ready` state, opacity transitions, image `onLoad` reset behavior, and lazy fallbacks. Any of these can contribute to the reported flash/disappear behavior.
3. `frontend/src/api/client.ts` currently implements `api.getHoverPreview()` through `/thumb`, and `frontend/src/features/browse/model/hoverPreview.ts` caps the preview surface at `360x280`. That contradicts the user's requirement for a large original-image preview.
4. The old hover code, visible in prior source history, used `api.getFile(path)` and rendered a centered overlay with image bounds near `80vw`/`80vh`. The corrective target should preserve that old product feel while keeping stale-token and cleanup safety from the newer controller.

Scope lock decision:

Visible side regions are expected to remain visible and stable in desktop/tablet viewer/compare. They are not required to be interactive while the modal is open in this corrective plan. If implementation evidence shows the old behavior required interactive side regions, stop and ask before changing `aria-modal`, focus trap ownership, or AppShell inert semantics.


## Interfaces and Dependencies


No new external dependency is approved.

Internal interface changes are expected to be narrow:

1. `buildResponsiveLayoutModel()` may change overlay behavior so desktop/tablet overlay mode reuses normal effective sidebar widths and sets `overlayInsets` to those widths. Phone/narrow/short-height suppression should remain governed by existing responsive constraints unless directly contradicted by browser evidence.
2. `api.getHoverPreview()` should be changed from thumbnail fetch to an original-file fetch shape. Prefer an abortable direct `/file` fetch that returns `{ promise, abort }` and does not require a new backend endpoint. Cache participation should follow the smallest implementation that preserves original-preview behavior and lifecycle safety; do not introduce new persistent cache policy.
3. Existing viewer/compare modal focus APIs should remain unless they directly cause the visual regression. Focus ownership and visual side-region visibility must be tested together.


## Plan of Work


The plan uses two sprints and six implementation tickets. Each sprint must produce a runnable browser state and update this document continuously, especially Progress Log and Artifacts and Handoff. After each sprint, add clear handoff notes before starting the next sprint.

For minor script-level uncertainties, such as whether the browser checks live in a new focused script or in `scripts/overall_cleanup_browser.py`, proceed according to this approved plan to maintain momentum. After the sprint, ask for clarification and apply follow-up adjustments if the user wants a different placement.

For every ticket with non-trivial code changes, the implementing agent must use the `better-code` skill before and during implementation. State the ticket assumptions, acceptance criteria, core invariants, smallest robust approach, and verification evidence before editing. Apply Karpathy-style execution guardrails: state material assumptions and ambiguous interpretations before coding, prefer the smallest non-speculative solution, touch only lines tied to the request, invariants, or verification, remove only unused code introduced by the change, and attach a concrete verification check to each step.

Delegate subagents early when they can find real codepaths/files to change faster. Let those subagents continue long enough to produce useful results; if work is still in progress after 10 minutes, ask for a progress update plus why more time is needed. Do not terminate cleanup or review subagents early just to keep the main loop moving.

### Scope Budget and Guardrails


Scope budget is two sprints, six tickets, and a narrow file set: `responsiveLayoutPolicy.ts`, its tests, `AppShell.tsx`, `Viewer.tsx`, `CompareViewer.tsx`, hover-preview model/API files, focused tests, browser evidence scripts, and packaged frontend assets if UI output changes.

Debloat and removal targets:

1. Remove overlay-active sidebar suppression where it conflicts with desktop/tablet center-contained viewer/compare behavior.
2. Remove or rewrite browser/test assertions that encode full-viewport viewer/compare as desired.
3. Remove thumbnail-only hover preview assertions.
4. Remove viewer/compare thumbnail fade or ready-state code only if it is proven to be the flash/disappear source.
5. Avoid adding new abstractions. Prefer changing the policy outputs and preview fetch path directly.

Quality guardrails:

1. The user-reported visual behavior is the primary source of truth.
2. Browser evidence must show side-region visibility, center-container containment, image stability over time, and original-file hover preview.
3. Do not make side regions interactive during modal overlay without explicit approval.
4. Do not accept a fix that only changes labels, CSS clipping, or z-index while the overlay still erases side regions or the preview still uses thumbnails.
5. If lazy loading causes the flash, first fix fallback placement and visible continuity for viewer/compare. Eager-load viewer/compare only if that narrower fix does not close the browser evidence.

### Sprint Plan


Sprint 1 goal: restore desktop/tablet contained overlay behavior and stable image rendering.

Demo outcome: with left and right side regions visible, opening viewer and compare keeps those regions visible and stable, and the image remains visible in the center container without flashing away.

Tasks:

1. `RVP-1`: Add failing browser evidence for side-region visibility and image flashing.
   Add a focused regression path, preferably in a small script or a narrow extension of `scripts/overall_cleanup_browser.py`. It should open a fixture gallery at desktop/tablet width, ensure left and right regions are visible, open viewer, record DOM attributes and rectangles before/during/after open, sample the image over several animation frames, and repeat the same overlay-policy assertion for compare. Validation: current code should fail or explicitly record the reported wrong state before fixes: side widths become zero, suppression reasons mention overlay, overlay spans the whole app, or the image flashes/disappears.
2. `RVP-2`: Restore overlay policy to preserve desktop/tablet side regions.
   First try the surgical policy fix: overlay mode must not suppress desktop/tablet sidebars that already satisfy normal layout constraints, and `overlayInsets` should match effective left/right widths. Do not move viewer DOM or rewrite grid structure unless policy/browser evidence proves that is insufficient. Add a failing-before-fix unit test in `responsiveLayoutPolicy.test.ts`: overlay active on desktop with both user sidebars open keeps effective sidebars open and sets overlay insets to those widths. Validation: policy tests pass, and browser evidence shows `data-effective-left-width` / `data-effective-right-width` stay nonzero with no overlay suppression reason on desktop/tablet.
3. `RVP-3`: Remove viewer/compare flashing or disappearing.
   Audit `LazySurfaceBoundary`, `Suspense` fallbacks, `Viewer.tsx`, `CompareViewer.tsx`, thumbnail placeholders, opacity transitions, `ready` state, and load/reset effects. Keep the smallest change that makes the full image continuously visible once loaded. If lazy fallback is the source, make fallback occupy exactly the center viewer container and preserve side regions; only eager-load viewer/compare if that fails. Validation: browser evidence samples image rect, opacity, and natural dimensions through open/load/resize and finds no visible-then-gone state.

Sprint 2 goal: restore large original hover preview.

Demo outcome: hover preview fetches and displays the original file at a large overlay size, bounded by viewport but materially larger than the thumbnail cell, with stale-response and cleanup safety preserved.

Tasks:

4. `RVP-4`: Rewrite hover-preview tests around original-file preview.
   Replace tests that assert `/thumb` and no full-file behavior. New tests should assert an original `/file` request path, stale-response rejection, abort on clear when the request shape supports it, object URL cleanup, and large preview sizing. Validation: current code fails the new `/file` and large-size assertions before `RVP-5`.
5. `RVP-5`: Restore original-file hover preview with safe lifecycle.
   Change `api.getHoverPreview()` or the hover controller fetcher to use original `/file` content through an abortable request shape. Restore preview sizing toward the old centered `80vw`/`80vh` behavior, while keeping visible viewport bounds, request tokens, URL revocation, and clear-on-scroll behavior. Do not add backend endpoints or persistent cache policy. Validation: browser evidence proves hover preview requests `/file`, not `/thumb`; preview dimensions are materially larger than the grid cell and approach viewport bounds when space allows; rapid hover changes do not show stale images.
6. `RVP-6`: Final regression gate, cleanup, and handoff.
   Run focused frontend tests, the focused browser regression path, existing GUI smoke, build, lint, and asset sync if UI changed. Validation: both user-reported behaviors pass, previous adjacent behavior touched by the files still works, and generated frontend assets are synced with `rsync -a --delete frontend/dist/ src/lenslet/frontend/` or an equivalent delete-then-copy fallback if `rsync` is unavailable.

### Task Gate Routine


Every ticket must use this gate routine.

0. Plan gate.
   The code agent briefly restates the ticket goal, acceptance criteria, material assumptions or ambiguities, and files expected to change. If an ambiguity would change behavior, stop and ask. If the ticket includes substantive code work, invoke `better-code` first and state the key invariants, smallest robust approach, and verification evidence.
1. Implement gate.
   Implement the smallest coherent slice that satisfies the ticket. Avoid speculative features, one-off abstractions, unrelated cleanup, broad refactors, and behavior changes outside the approval matrix. Run ticket-specific tests, typecheck, browser checks, or command checks.
2. Cleanup gate.
   After each sprint, run the `code-simplifier` routine below and apply only conservative cleanup.
3. Review gate.
   After cleanup, run the review routine below. Address findings and rerun review when needed before closing the sprint.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the `code-simplifier` skill to scan the current sprint changes. Start with non-semantic cleanup only: formatting or lint autofixes, obvious dead code removal introduced by the fix, small readability edits that do not change behavior, and docs/comments that reflect what is already true.

Keep this pass conservative. Do not expand into semantic refactors unless explicitly approved. Once this cleanup subagent starts, do not interrupt or repurpose it just to save time. If it runs long, wait or request a progress update; fall back to manual cleanup review only if the subagent is unavailable, fails, or the user explicitly approves the downgrade.

### review routine


After each complete sprint and after the cleanup subagent finishes, spawn a fresh agent and request a code review using the `code-review` skill. Instruct it to be constructively adversarial: look specifically for leftover full-viewport overlay assumptions, thumbnail-hover assumptions, weak browser evidence, focus/inert regressions, and unnecessary refactors.

Use the best available model in the environment with `reasoning_effort` set to `medium`. Review the post-cleanup diff, apply fixes, and rerun review when needed to confirm resolution. Once the review subagent starts, do not interrupt, repurpose, or terminate it to save time. Manual diff review is a fallback only when the review subagent is unavailable, fails after a reasonable wait plus progress check, or the user explicitly approves a downgrade.


## Validation and Acceptance


Primary acceptance checks are browser checks for the two user-reported regressions. Secondary checks are focused unit tests, build, lint, and existing smoke checks.

Primary per-sprint checks:

1. Sprint 1.
   Open Lenslet at desktop/tablet width with left and right side regions visible, open viewer and compare, and record rectangles plus DOM attributes for side regions, center viewer container, overlay insets, suppression reasons, and image visibility over multiple animation frames. Expected: side regions remain visible and stable, overlay content is contained in the center area, `data-effective-left-width` and `data-effective-right-width` remain nonzero when normal layout allows them, no overlay suppression reason erases them, and the image does not flash then disappear.
2. Sprint 2.
   Hover over the grid preview hotspot with a fixture image large enough to distinguish full-file preview from thumbnail preview. Expected: browser network evidence shows `/file`, not `/thumb`; preview is materially larger than the grid cell and close to the old large overlay behavior; stale hover responses do not replace the active preview; clearing hover revokes the object URL and aborts when available.

Primary final gates:

1. Run the focused regression browser script:

       python scripts/viewer_preview_regression.py --output-json /tmp/lenslet-viewer-preview-regression.json

   If the implementation extends `scripts/overall_cleanup_browser.py` instead, document the exact equivalent command in this plan before handoff.

2. Run the existing GUI smoke:

       python scripts/gui_smoke_acceptance.py

Secondary fast gates:

1. Run focused frontend tests for touched modules, then full frontend tests:

       cd frontend && npm run test

2. Run frontend build:

       cd frontend && npm run build

3. Sync packaged frontend assets if UI output changed:

       rsync -a --delete frontend/dist/ src/lenslet/frontend/

   If `rsync` is unavailable, use an equivalent delete-then-copy fallback and state it in handoff notes.

4. Run repo lint:

       python scripts/lint_repo.py

Final acceptance criteria:

1. The corrective plan clearly records that the user wanted the old side-region and original-hover-preview behaviors, and the previous plan broke them.
2. Viewer and compare no longer erase visible desktop/tablet side regions just because overlay mode is active.
3. Viewer and compare image surfaces are contained in the center container, not full app viewport, when side regions are visible.
4. Viewer and compare images do not flash and then disappear during open/load.
5. Side regions remain visible and stable while viewer/compare modal focus remains owned by viewer/compare.
6. Hover preview uses original `/file` content and renders substantially larger than the thumbnail cell.
7. Hover preview keeps stale-response, cleanup, and abort safety where supported.
8. No new dependencies, backend endpoints, or broad refactors are introduced.


## Risks and Recovery


Hidden dependencies:

1. `responsiveLayoutPolicy.ts` currently treats overlay and short-height suppression together; the fix must not force sidebars onto phone/narrow/short-height layouts.
2. AppShell sets inert state around overlays. Side regions can be visible yet inert; making them interactive would require a separate accessibility decision.
3. Viewer and compare focus trapping can coexist with visible side regions only if browser evidence checks both visibility and focus containment.
4. Lazy-loaded fallback placement can make side regions appear to disappear even if the final viewer is correct.
5. Full-file hover preview can be expensive. That cost is accepted here because the user explicitly wants a large original-image preview; performance optimization is deferred.
6. Previous tests now encode wrong assumptions. Tests that assert `/thumb` hover or full-viewport overlay must be updated rather than preserved.

Recovery:

1. Keep each sprint committable and reviewable.
2. If a change regresses core browsing, revert only that sprint's touched files and keep the failing browser evidence.
3. Do not revert unrelated user changes.
4. If policy-only overlay containment fails, then and only then inspect viewer/compare DOM placement and lazy fallback placement.
5. If abortable original `/file` preview cannot reuse current API safely, implement the smallest direct abortable fetch path and document cache behavior in handoff.


## Progress Log


- [x] 2026-05-25 06:53 UTC: User clarified that the previous plan broke wanted old behaviors: fullscreen/viewer should keep left/right side regions visible and center-contained, and hover preview should show a large original image.
- [x] 2026-05-25 06:53 UTC: Confirmed the previous Ralph session is no longer running.
- [x] 2026-05-25 06:53 UTC: Inspected current codepaths and old source history; current hover preview uses `/thumb` plus `360x280`, while old hover preview used `api.getFile` and `80vw`/`80vh`.
- [x] 2026-05-25 06:53 UTC: Ran required plan review subagent and incorporated feedback about overlay accessibility semantics, desktop/tablet scope, surgical policy fix, direct abortable full-file hover fetch, DOM attribute assertions, and packaged asset sync.
- [ ] Sprint 1 implementation handoff pending.
- [ ] Sprint 2 implementation handoff pending.


## Artifacts and Handoff


Input:

1. User regression report in this thread.
2. Previous plan: `docs/20260525_overall_cleanup_execution_plan.md`.
3. Ralph progress: `docs/ralph/20260525_overall_cleanup_execution_plan/progress.txt`.

Likely codepaths:

1. `frontend/src/app/layout/responsiveLayoutPolicy.ts`
2. `frontend/src/app/layout/__tests__/responsiveLayoutPolicy.test.ts`
3. `frontend/src/app/AppShell.tsx`
4. `frontend/src/features/viewer/Viewer.tsx`
5. `frontend/src/features/compare/CompareViewer.tsx`
6. `frontend/src/features/browse/components/VirtualGrid.tsx`
7. `frontend/src/features/browse/model/hoverPreview.ts`
8. `frontend/src/features/browse/model/__tests__/hoverPreview.test.ts`
9. `frontend/src/api/client.ts`
10. `frontend/src/api/__tests__/client.prefetch.test.ts`
11. `scripts/overall_cleanup_browser.py` or a new focused `scripts/viewer_preview_regression.py`
12. `src/lenslet/frontend/` generated assets if UI changed.

Handoff notes:

1. Do not continue the old Ralph plan assumptions for viewer fullscreen or hover preview.
2. Restore the old product intent first: visible side regions and large original hover preview.
3. Preserve modal focus ownership unless the user explicitly approves interactive side regions during viewer/compare.
4. Prefer policy and preview-fetch fixes over broad DOM or component rewrites.
5. If a focused browser script is added, keep it small and tied only to these regressions.

Revision note:

This new corrective plan explicitly replaces the previous plan's mistaken full-viewport overlay and thumbnail-hover assumptions. It states that the user wanted the old visible side-region behavior and old large original hover-preview behavior, and it scopes implementation to restoring those behaviors with browser evidence.
