# 2026-05-25 Restore Viewer Tabs and Original Hover Preview Plan


## Outcome + Scope Lock


This is a corrective regression plan. The user clarified that the old behaviors were intentional and wanted. The previous overall cleanup plan made changes that broke those behaviors by treating full-viewport viewer/compare overlays and thumbnail-based hover preview as desired outcomes. That was wrong for the product behavior the user expects.

After implementation, opening viewer or compare when the normal non-overlay layout can show the left and right side regions should keep those side regions visible and visually stable. The image surface should be contained in the center viewer container, not stretched across the whole app viewport. The image should not flash and then disappear. Hover preview should show a large preview from the original image file, materially larger than the grid thumbnail, not a thumbnail-sized preview that looks basically the same as the cell.

Goals:

1. Restore viewer and compare containment to the center content area while preserving visible left and right side regions whenever the normal non-overlay layout can show them.
2. Remove viewer/compare image flashing or disappearing introduced by the previous lazy/fallback/thumbnail/opacity path.
3. Restore hover preview to a large original-file preview, bounded by viewport but not thumbnail-sized.
4. Preserve the useful safety pieces that do not conflict with the old behavior: stale-response guards, URL cleanup, and request cancellation where the fetch path supports it.
5. Add browser evidence for the exact user-reported flows so completion cannot be claimed from proxy checks.

Non-goals:

1. Do not continue the previous full-viewport overlay or thumbnail-hover assumptions.
2. Do not rework justified-row layout, menu semantics, comparison export, or bundle splitting unless directly required by these regressions.
3. Do not add new backend APIs, tiled-image support, server-side preview derivatives, or frontend dependencies.
4. Do not remove the modal focus work wholesale unless it is proven to be the direct source of the side-region regression and a narrower fix fails.
5. Do not force side panels onto phone, narrow, or short-height layouts where the existing normal non-overlay responsive policy would suppress them.

Pre-approved behavior changes:

1. When the normal non-overlay layout would show side regions for the current viewport, viewer/compare overlay mode should not suppress those side regions merely because overlay mode is active.
2. On those layouts, viewer/compare overlay insets should match the effective left/right widths, so the image surface stays in the center container.
3. Side regions should remain visible while viewer/compare is open, but viewer/compare keep modal focus ownership by default. Visible side regions remain decorative/inert under the modal unless the user later asks for them to be interactive.
4. Hover preview may fetch original `/file` content again and should restore the old centered large preview presentation, with image bounds near `80vw`/`80vh` where viewport size allows, unless the user separately approves an anchored-popover redesign.
5. Tests and browser assertions that encode thumbnail-only hover preview or full-viewport overlay assumptions may be removed or rewritten because those assumptions are now known wrong.

Requires sign-off before implementation:

1. Making side regions interactive while viewer/compare is open.
2. Removing modal focus trapping entirely.
3. Removing lazy bundle splitting beyond viewer/compare if a smaller fallback/placement fix is enough.
4. Adding backend preview endpoints, new dependencies, or persistent cache-policy changes.
5. Changing phone/narrow/short-height overlay policy beyond matching what the existing normal non-overlay responsive behavior would show.

Deferred or out of scope:

1. Large-image tiling and bandwidth optimization for original hover preview.
2. A broader redesign of fullscreen mode.
3. A full accessibility audit beyond the focus/inert behavior touched by this regression.
4. Re-running the completed cleanup epic except for checks needed to prove these fixes do not regress adjacent behavior.


## Context


No `PLANS.md` was found in the repo scan. This plan follows the user-provided repository instructions, Lenslet skill guidance, and the `plan-writer` process.

The previous plan was implemented through recent commits including `4fba010 feat: harden viewport menus and hover preview`, `2acc740 fix: preserve overlay inspection context`, and `2bb9104 feat: split secondary gallery surfaces`. The user now reports that these changes broke wanted old behavior.

Current source inspection points to these direct regression areas:

1. On the regressed branch, `frontend/src/app/layout/responsiveLayoutPolicy.ts` suppresses sidebars when `overlayActive` is true and returns `overlayInsets: { left: 0, right: 0 }`. That makes viewer/compare a whole-app overlay and erases the visible left/right regions that the user wanted preserved. A review of another repo snapshot found direct viewer/compare imports, full-file hover preview, no `hoverPreview.ts`, and no `overall_cleanup_browser.py`; another review of the current snapshot confirmed the overlay suppression, thumbnail hover path, and `360x280` preview cap. Implementation must still start by confirming the actual working branch state before editing.
2. `frontend/src/app/AppShell.tsx` lazy-loads viewer and compare through fallback overlays, and `Viewer.tsx` / `CompareViewer.tsx` combine thumbnail placeholders, `ready` state, opacity transitions, image `onLoad` reset behavior, and lazy fallbacks. Any of these can contribute to the reported flash/disappear behavior.
3. `frontend/src/api/client.ts` currently implements `api.getHoverPreview()` through `/thumb`, and `frontend/src/features/browse/model/hoverPreview.ts` caps the preview surface at `360x280`. That contradicts the user's requirement for a large original-image preview.
4. The old hover code, visible in prior source history, used `api.getFile(path)` and rendered a centered overlay with image bounds near `80vw`/`80vh`. The corrective target should preserve that old product feel while keeping stale-token and cleanup safety from the newer controller.

Scope lock decision:

Visible side regions are expected to remain visible and stable in viewer/compare whenever normal non-overlay layout would show them. They are not required to be interactive while the modal is open in this corrective plan. If implementation evidence shows the old behavior required interactive side regions, stop and ask before changing `aria-modal`, focus trap ownership, or AppShell inert semantics.

Toolbar policy is explicit. If the top toolbar Back, close, zoom slider, or previous/next controls are treated as viewer chrome in the current branch, keep that behavior and test it. If viewer/compare owns all close/navigation controls locally, keep toolbar inertness consistent with the existing branch. Compare may continue to inert the toolbar if that is current product behavior. Do not silently change toolbar interactivity while restoring side-region visibility.


## Interfaces and Dependencies


No new external dependency is approved.

Internal interface changes are expected to be narrow:

1. `buildResponsiveLayoutModel()` may change overlay behavior so overlay mode reuses normal effective sidebar widths and sets `overlayInsets` to those widths. The safest implementation is to remove overlay-active from the early full-sidebar suppression branch, keep short-height suppression, let the existing normal sidebar feasibility algorithm compute effective widths, and then set overlay insets to those effective widths only when overlay is active. Do not implement this by blindly returning the full non-overlay model for overlay mode, because overlay still has overlay-specific shell reserves such as disabled mobile drawer height.
2. `api.getHoverPreview()` should be changed from thumbnail fetch to an original-file fetch shape if the branch currently uses thumbnails. Prefer a dedicated abortable `/file` hover request, such as `getHoverPreviewFile(path): { promise: Promise<Blob>; abort: () => void }`, that participates in the existing file request budget, may read from `fileCache` if already cached, and does not abort shared viewer/compare file-cache requests. For uncached hover fetches, use a direct abortable `/file` request. Writing successful hover blobs into `fileCache` is optional only if it preserves old full-file behavior without broadening this task. Do not add a backend endpoint or persistent cache policy.
3. Existing viewer/compare modal focus APIs should remain unless they directly cause the visual regression. Focus ownership and visual side-region visibility must be tested together.


## Plan of Work


The plan uses two sprints and seven implementation tickets. Each sprint must produce a runnable browser state and update this document continuously, especially Progress Log and Artifacts and Handoff. After each sprint, add clear handoff notes before starting the next sprint.

For minor script-level uncertainties, such as whether the browser checks extend `scripts/responsive_geometry_harness.py` or live in a new focused `scripts/viewer_preview_regression.py`, proceed according to this approved plan to maintain momentum. Prefer extending the existing harness if it exists in the working branch. After the sprint, ask for clarification and apply follow-up adjustments if the user wants a different placement.

For every ticket with non-trivial code changes, the implementing agent must use the `better-code` skill before and during implementation. State the ticket assumptions, acceptance criteria, core invariants, smallest robust approach, and verification evidence before editing. Apply Karpathy-style execution guardrails: state material assumptions and ambiguous interpretations before coding, prefer the smallest non-speculative solution, touch only lines tied to the request, invariants, or verification, remove only unused code introduced by the change, and attach a concrete verification check to each step.

Delegate subagents early when they can find real codepaths/files to change faster. Let those subagents continue long enough to produce useful results; if work is still in progress after 10 minutes, ask for a progress update plus why more time is needed. Do not terminate cleanup or review subagents early just to keep the main loop moving.

### Scope Budget and Guardrails


Scope budget is two sprints, seven tickets, and a narrow file set: `responsiveLayoutPolicy.ts`, its tests, `AppShell.tsx`, `Viewer.tsx`, `CompareViewer.tsx`, hover-preview model/API files, focused tests, browser evidence scripts, and packaged frontend assets if UI output changes.

Debloat and removal targets:

1. Remove overlay-active sidebar suppression where it conflicts with center-contained viewer/compare behavior on layouts whose normal non-overlay policy would show side regions.
2. Remove or rewrite browser/test assertions that encode full-viewport viewer/compare as desired.
3. Remove thumbnail-only hover preview assertions.
4. Do not remove thumbnail fallback or fade behavior wholesale. First fix readiness ownership so the full image cannot become hidden after the current image has loaded; remove only exact ready/fade code that evidence proves is responsible.
5. Avoid adding new abstractions. Prefer changing the policy outputs and preview fetch path directly.

Quality guardrails:

1. The user-reported visual behavior is the primary source of truth.
2. Browser evidence must show side-region visibility, center-container containment, image stability over time, and original-file hover preview.
3. Do not make side regions interactive during modal overlay without explicit approval.
4. Do not accept a fix that only changes labels, CSS clipping, or z-index while the overlay still erases side regions or the preview still uses thumbnails.
5. If lazy loading causes the flash, first fix fallback placement and visible continuity for viewer/compare. Eager-load viewer/compare only if that narrower fix does not close the browser evidence.

### Sprint Plan


Sprint 1 goal: restore contained overlay behavior wherever the normal non-overlay layout would show side regions, and stabilize image rendering.

Demo outcome: with left and right side regions visible, opening viewer and compare keeps those regions visible and stable, and the image remains visible in the center container without flashing away.

Tasks:

1. `RVP-0`: Confirm branch alignment before editing.
   Inspect current `AppShell` viewer/compare imports and `Suspense`/lazy fallback paths, `Viewer`/`CompareViewer` ready/thumbnail/opacity behavior, `VirtualGrid` hover-preview fetch path, API client hover/file/thumb methods, and existing browser harness names. If the branch already uses direct viewer/compare imports, do not spend `RVP-3` on lazy fallback removal. If hover already uses original `/file` and `80vw`/`80vh` sizing, narrow Sprint 2 to stale-response, abort, scroll-clear, and browser-evidence hardening. If files named in this plan do not exist, do not create broad abstractions merely to match plan wording. Validation: record a short branch-alignment note in this plan's Progress Log before implementation starts.
2. `RVP-1`: Add browser evidence for side-region visibility and image flashing.
   Add a focused regression path, preferably by extending `scripts/responsive_geometry_harness.py` if it exists or by adding a small `scripts/viewer_preview_regression.py` if a separate script is cleaner. It should open a fixture gallery at a viewport where normal non-overlay layout shows left and right regions, record left side-region rect, right side-region rect, grid-shell rect, app-shell rect, overlay-related DOM attributes, open viewer, sample the image over several animation frames, and repeat the same overlay-policy assertion for compare. For compare, check both the compare dialog and `.compare-stage`. Validation: the regression branch should fail or explicitly record the reported wrong state before fixes: side widths become zero, suppression reasons mention overlay, overlay spans the app instead of matching the grid shell, or the image flashes/disappears. If the current branch already passes a check, record that evidence and avoid unnecessary edits.
3. `RVP-2`: Restore overlay policy to preserve normally visible side regions.
   First try the surgical policy fix: overlay mode must not suppress sidebars that the normal non-overlay policy would show, and `overlayInsets` should match those effective left/right widths. Keep short-height suppression unchanged, keep mobile drawer reserve disabled under overlays, and do not move viewer DOM or rewrite grid structure unless policy/browser evidence proves that is insufficient. Split the existing overlay/short-height policy coverage into separate tests: short height still suppresses sidebars; overlay preserves side widths when normal layout would show them; overlay does not force sidebars onto layouts where normal policy suppresses them; and a borderline width such as `900px` preserves sidebars if the non-overlay policy would show them. Include the explicit `1440px` comparison between `overlay: 'viewer'` and `overlay: 'none'` for `leftWidth`, `rightWidth`, `effectiveLeftOpen`, `effectiveRightOpen`, and `overlayInsets`. Validation: policy tests pass, and browser evidence shows `data-effective-left-width` / `data-effective-right-width` stay nonzero only when normal layout allows them, with no overlay suppression reason erasing them.
4. `RVP-3`: Remove viewer/compare flashing or disappearing.
   Audit `LazySurfaceBoundary`, `Suspense` fallbacks, `Viewer.tsx`, `CompareViewer.tsx`, thumbnail placeholders, opacity transitions, `ready` state, and load/reset effects. Specifically audit the ready reset race where a URL-change effect can set `ready=false` after the current full image has already loaded. Prefer complete/naturalWidth-aware readiness reconciliation, or reset readiness at path/request start rather than after the current image mounted. Keep the thumbnail placeholder unless evidence proves it is the problem. Validation: browser evidence samples image rect, opacity, complete/natural dimensions, and current src through open/load/resize and finds no visible-then-gone state. If viewer toolbar controls are intended viewer chrome, verify Back closes viewer, zoom changes viewer scale, and previous/next controls still navigate when enabled.

Sprint 2 goal: restore large original hover preview.

Demo outcome: hover preview fetches and displays the original file in the restored centered large preview style, bounded by viewport but materially larger than the thumbnail cell, with stale-response and cleanup safety preserved.

Tasks:

5. `RVP-4`: Rewrite hover-preview tests around original-file preview.
   Replace tests that assert `/thumb` and no full-file behavior. New tests should assert an original `/file` request path, stale-response rejection, abort on clear when the request shape supports it, object URL cleanup, and large preview sizing based on the actual image rectangle rather than only wrapper size. Add an adversarial delayed-A/fast-B case: hover image A, delay A's `/file` response, move to image B, resolve B, then resolve A; the preview must remain B, A must not replace B, and A's object URL must not leak. Add clear-on-scroll behavior: active preview clears, pending timer is cancelled, pending request is aborted where supported, and the current object URL is revoked. Validation: the regression branch should fail the new `/file` and large-size assertions before `RVP-5`; if the current branch already passes, record that evidence and limit edits to missing lifecycle hardening.
6. `RVP-5`: Restore original-file hover preview with safe lifecycle.
   Change `api.getHoverPreview()` or the hover controller fetcher to use original `/file` content through a dedicated abortable request shape. It should return `{ promise, abort }`, participate in the file request budget, avoid aborting a shared `fileCache` request that viewer/compare may be using, and avoid adding new persistent cache policy. Restore the old centered fixed preview with image bounds near `80vw`/`80vh`; do not merely enlarge the new anchored thumbnail popover unless the user separately approves that design. If `getHoverPreviewSurfaceSize()` exists, it may stop being the main sizing primitive for the restored behavior. Keep visible viewport bounds, request tokens, URL revocation, and clear-on-scroll behavior. Validation: browser evidence captures hover-specific network requests after hover starts and proves the hover path requests `/file`, not `/thumb`; preview image dimensions are materially larger than the grid cell and approach viewport bounds when space allows; rapid hover changes do not show stale images.
7. `RVP-6`: Final regression gate, cleanup, and handoff.
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
   Open Lenslet at a viewport where normal non-overlay layout shows left and right side regions, open viewer and compare, and record rectangles plus DOM attributes for side regions, center viewer container, overlay insets, suppression reasons, toolbar state, and image visibility over multiple animation frames. Expected: side regions remain visible and stable, overlay left/right edges match the grid-shell left/right edges within `1px`, overlay width is not the whole viewport when side regions are visible, `data-effective-left-width` and `data-effective-right-width` remain nonzero when normal layout allows them, no overlay suppression reason erases them, focus remains contained in viewer/compare, side regions remain inert/decorative, and the image does not flash then disappear. If viewer toolbar controls are product chrome, Back, zoom, and previous/next must remain usable in viewer mode; compare may keep the toolbar inert if that is current behavior.
2. Sprint 2.
   Hover over the grid preview hotspot with a fixture image large enough to distinguish full-file preview from thumbnail preview. Expected: hover-specific browser network evidence captured after the hover action begins shows `/file`, not `/thumb`; preview is materially larger than the grid cell and close to the old centered large overlay behavior; stale hover responses do not replace the active preview; scrolling clears hover state; clearing hover revokes the object URL and aborts when available.

Primary final gates:

1. Run the focused regression browser script. Prefer the existing responsive geometry harness if implementation extended it:

       python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry.json

   If implementation adds a narrower focused script instead, run:

       python scripts/viewer_preview_regression.py --output-json /tmp/lenslet-viewer-preview-regression.json

   Document the exact command in this plan before handoff.

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
2. Viewer and compare no longer erase side regions that normal non-overlay layout would show just because overlay mode is active.
3. Viewer and compare image surfaces are contained in the center container, not full app viewport, when side regions are visible.
4. Viewer and compare images do not flash and then disappear during open/load.
5. Side regions remain visible and stable while viewer/compare modal focus remains owned by viewer/compare, and toolbar behavior is unchanged except where explicitly documented.
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
7. Review feedback was based on another snapshot where some regression files did not exist; `RVP-0` must prevent implementation from chasing nonexistent files or already-restored behavior.
8. Reusing the complete non-overlay layout model under overlay could accidentally re-enable mobile drawer reserves. Overlay should reuse normal side geometry while preserving overlay-specific shell reserves.

Recovery:

1. Keep each sprint committable and reviewable.
2. If a change regresses core browsing, revert only that sprint's touched files and keep the failing browser evidence.
3. Do not revert unrelated user changes.
4. If policy-only overlay containment fails, then and only then inspect viewer/compare DOM placement and lazy fallback placement.
5. If abortable original `/file` preview cannot reuse current API safely, implement the smallest direct abortable fetch path and document cache behavior in handoff.
6. If branch alignment shows the code is already restored, narrow implementation to browser evidence and any remaining lifecycle hardening instead of reintroducing the regressed abstractions.


## Progress Log


- [x] 2026-05-25 06:53 UTC: User clarified that the previous plan broke wanted old behaviors: fullscreen/viewer should keep left/right side regions visible and center-contained, and hover preview should show a large original image.
- [x] 2026-05-25 06:53 UTC: Confirmed the previous Ralph session is no longer running.
- [x] 2026-05-25 06:53 UTC: Inspected current codepaths and old source history; current hover preview uses `/thumb` plus `360x280`, while old hover preview used `api.getFile` and `80vw`/`80vh`.
- [x] 2026-05-25 06:53 UTC: Ran required plan review subagent and incorporated feedback about overlay accessibility semantics, normal-layout scope, surgical policy fix, direct abortable full-file hover fetch, DOM attribute assertions, and packaged asset sync.
- [x] 2026-05-25 07:10 UTC: Read `docs/20260525_restore_viewer_tabs_hover_preview_plan_review.md` and incorporated branch-alignment gate, normal-layout comparison rule, concrete policy implementation shape, ready-state race note, toolbar policy, and safer full-file hover cache guidance.
- [x] 2026-05-25 07:18 UTC: Tightened the plan after review to prefer the existing responsive geometry harness, avoid blindly returning the non-overlay model, require split overlay/short-height tests, restore the old centered hover preview rather than an enlarged anchored popover, and add adversarial hover stale-response/scroll-clear checks.
- [x] 2026-05-25 10:12 UTC: `RVP-0` branch alignment confirmed before implementation. Current branch lazy-loads viewer/compare with `Suspense` fallbacks, `responsiveLayoutPolicy.ts` suppresses side regions when overlay is active, `Viewer.tsx` and `CompareViewer.tsx` use thumbnail placeholders plus readiness opacity, `api.getHoverPreview()` fetches `/thumb`, `hoverPreview.ts` caps at `360x280`, and `scripts/responsive_geometry_harness.py` is the active browser harness to extend.
- [x] 2026-05-25 10:13 UTC: `RVP-1` extended `scripts/responsive_geometry_harness.py` with side-region/grid/overlay rect assertions and multi-frame viewer/compare image visibility samples. Before the policy fix, `python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry-rvp1-before.json` failed as expected because viewer overlay reported `overlay-active` suppression and `data-effective-left-width="0"` / `data-effective-right-width="0"` at `1024x760`.
- [x] 2026-05-25 10:14 UTC: `RVP-2` restored overlay policy so viewer/compare reuse normal effective side widths as overlay insets while short-height and phone/narrow suppression remain governed by normal responsive constraints. Focused policy tests passed with `npm run test -- src/app/layout/__tests__/responsiveLayoutPolicy.test.ts src/features/viewer/hooks/__tests__/useZoomPan.test.ts`.
- [x] 2026-05-25 10:15 UTC: `RVP-3` reconciled viewer and compare readiness against completed current images so cached or fast `/file` loads cannot be hidden after load. Kept thumbnail placeholders and lazy surfaces intact.
- [x] 2026-05-25 10:16 UTC: Built and synced frontend assets. `rsync` was unavailable, so used the approved delete-then-copy fallback from `frontend/dist/` into `src/lenslet/frontend/`.
- [x] 2026-05-25 10:17 UTC: Sprint 1 browser evidence passed with `python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry-rvp1-after.json`; viewer overlay includes `viewer-toolbar-before-1024x760` / `viewer-toolbar-1024x760`, and compare overlay includes `compare-overlay-before-1440x900` / `compare-overlay-1440x900` plus image samples. Full frontend tests passed with `npm run test`.
- [x] 2026-05-25 10:29 UTC: Sprint 1 cleanup and review gates completed. Cleanup removed one unused harness helper and normalized compare readiness formatting. Review found two issues, both fixed: generated assets were staged coherently, and browser image evidence now asserts loaded image identity after warmed viewer and compare next-navigation using URL-bound loaded-path data, not merely requested path. Final Sprint 1 validations passed: `python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry-rvp1-final2.json`, `npm run test`, and `python scripts/lint_repo.py`.
- [x] Sprint 1 implementation handoff complete. Restored contained viewer/compare overlays and stable loaded-image visibility while preserving modal focus ownership and toolbar behavior. Side regions remain inert/decorative under modal ownership; no Sprint 2 hover-preview behavior was changed.
- [x] 2026-05-25 10:35 UTC: `RVP-4` rewrote focused hover-preview tests around original `/file` requests, cached full-file reuse without shared abort, abort-on-clear lifecycle, late stale response rejection, object URL cleanup, and centered large `80vw`/`80vh` sizing. Expected pre-fix validation failed with `npm run test -- src/features/browse/model/__tests__/hoverPreview.test.ts src/api/__tests__/client.prefetch.test.ts`: current code still requested `/thumb`, ignored cached full files, and capped preview sizing at `360x280`.
- [x] 2026-05-25 10:38 UTC: `RVP-5` restored original-file hover preview. `api.getHoverPreview()` now reuses already cached full files but otherwise issues a dedicated abortable `/file` request through the file request budget without writing into shared caches. The grid preview now uses a centered `80vw`/`80vh` viewport-bounded surface. Focused tests passed with `npm run test -- src/features/browse/model/__tests__/hoverPreview.test.ts src/api/__tests__/client.prefetch.test.ts`.
- [x] 2026-05-25 10:39 UTC: Extended `scripts/responsive_geometry_harness.py` with hover-preview browser evidence and rebuilt/synced packaged frontend assets with the delete-then-copy fallback. `python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry-rvp5.json` passed; hover evidence captured `/file?path=...`, no hover `/thumb` request for the hovered path, a centered `1152x720` preview at `1440x900`, an image rect materially larger than the source cell, and zero pending/active scroll-clear leftovers.
- [x] 2026-05-25 10:42 UTC: Sprint 2 `code-simplifier` cleanup pass completed for the scoped diff. Removed old anchored-preview residue now contradicted by the centered preview implementation: the unused `HOVER_PREVIEW_OFFSET_PX` export, `AnchorRectLike` import, `anchorRect`/`offset` position input fields, and the unnecessary `DOMRect` argument in `VirtualGrid.schedulePreview()`. Rebuilt and synced packaged frontend assets. Validations passed: `npm run test -- src/features/browse/model/__tests__/hoverPreview.test.ts src/api/__tests__/client.prefetch.test.ts`, `python -m py_compile scripts/responsive_geometry_harness.py`, `npm run build`, and `python scripts/lint_repo.py`.
- [x] 2026-05-25 10:46 UTC: Sprint 2 review gate completed. Initial review found that generated assets needed to be staged with the `index.html` hash update and that browser evidence should cover delayed in-flight `/file` hover lifecycle, not only pending timer and loaded-preview clear. Fixed both: staged generated asset replacements and added a held `/file` route check that scroll-clears while the original-file request is pending, releases the response, and asserts zero stale preview DOM. Re-review reported no actionable findings.
- [x] 2026-05-25 10:47 UTC: `RVP-6` final gates passed: `npm run test` (75 files / 356 tests), `npm run build`, delete-then-copy asset sync, `python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry-rvp6-final3.json`, `python scripts/gui_smoke_acceptance.py` (passed with an existing non-blocking folder re-entry anchor warning), `python -m py_compile scripts/responsive_geometry_harness.py`, and `python scripts/lint_repo.py` (warn-only file-size notices; `responsive_geometry_harness.py` is 1999 lines, below the 2000-line hard fail).
- [x] Sprint 2 implementation handoff complete. Restored large centered original-file hover preview with stale-response, abort, object URL cleanup, pending-scroll-clear, delayed-request-clear, and loaded-preview-clear coverage. All planned sprints and tasks are complete.


## Artifacts and Handoff


Input:

1. User regression report in this thread.
2. Previous plan: `docs/20260525_overall_cleanup_execution_plan.md`.
3. Ralph progress: `docs/ralph/20260525_overall_cleanup_execution_plan/progress.txt`.
4. Plan review: `docs/20260525_restore_viewer_tabs_hover_preview_plan_review.md`.

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
11. `scripts/responsive_geometry_harness.py` or a new focused `scripts/viewer_preview_regression.py`
12. `src/lenslet/frontend/` generated assets if UI changed.

Handoff notes:

1. Sprint 1 closed in the prior iteration and Sprint 2 closed in this iteration.
2. Final browser evidence command: `python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry-rvp6-final3.json`.
3. Final GUI smoke command: `python scripts/gui_smoke_acceptance.py`.
4. `rsync` is unavailable in this environment; generated frontend assets were synced with delete-then-copy from `frontend/dist/` to `src/lenslet/frontend/`.
5. Side regions remain visible and inert/decorative under viewer/compare modal ownership; no approval-dependent interactive side-region change was made.
6. Hover preview now uses original `/file` content through a dedicated abortable hover request path, reusing cached full files only when already available.

Revision note:

This revision incorporates `docs/20260525_restore_viewer_tabs_hover_preview_plan_review.md` by adding branch-alignment before implementation, replacing hard-coded viewport-class wording with normal-layout comparison, narrowing the overlay policy fix to remove overlay-only suppression, adding the likely viewer ready-state race, clarifying toolbar/focus behavior, preferring the existing browser harness, and making original-hover preview use a dedicated abortable `/file` request shape in the restored centered large-preview presentation.
