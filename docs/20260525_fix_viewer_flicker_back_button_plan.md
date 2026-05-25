# Viewer Flicker, Pan, and Back Button Fix Plan


## Outcome + Scope Lock


After implementation, opening an image from the gallery into the image viewer should be visually stable. The viewer must not flash a ghost, thumbnail-like, or previous-image copy during fast loads, and slow loads must show only a neutral loading state instead of any image-like placeholder. The final image should first become visible at its fitted viewer transform.

Viewer interaction should feel less boxed in. Users should be able to pan a loaded fullscreen image at its default fitted scale and at enlarged zoom levels, including past the strict left, right, top, and bottom edge clamps within a bounded slack margin. This is wanted because hard edge clamps make inspection feel restrictive and prevent edge details from being positioned comfortably away from the viewport boundary. The default, not-zoomed-in image must not feel locked in place.

Single click on the fullscreen viewer surface should not exit the viewer. Double-click on the non-control viewer surface should return to the grid. This is wanted because accidental single-click exits are disruptive while inspecting or panning an image, while double-click remains an intentional quick-return gesture.

The Back button in viewer mode must be reliably pushable across the whole visible button, including widths near compact toolbar breakpoints. The fix must preserve the existing viewer purpose and toolbar semantics: Back still returns to the grid, image navigation still works, side panel containment policy is not changed, and gallery thumbnail behavior is not redesigned.

Goals are to remove the viewer thumbnail/crossfade root path, remove fast-load open flicker contributors, prevent stale viewer blob URLs from becoming visible, add bounded pan slack on all image edges, change fullscreen click semantics to single-click no-op and double-click return, and prove Back button hit-testing with browser evidence. Non-goals are redesigning the viewer surface, changing fullscreen/sidebar containment, changing keyboard shortcuts beyond the stated double-click gesture, replacing the toolbar system, or changing hover preview behavior.

Pre-approved behavior changes are:

1. Remove image-like placeholders from the gallery-to-viewer open path.
2. Replace fast image placeholders with a delayed neutral loader only when the full image is still not ready after about 150ms.
3. Remove the viewer opening opacity fade and the full-image crossfade.
4. Directly import the main Viewer so the primary gallery-to-viewer open path is not behind Suspense fallback. Browser evidence must confirm OverlayFallback("Loading viewer...") does not render during normal gallery-to-viewer open.
5. Add viewer-specific bounded pan slack around the loaded image in all directions at default fitted scale and enlarged zoom levels, without allowing the image to be dragged so far away that it is hard to recover. The initial ready state must remain centered and fitted; slack applies only after user pan or drag input.
6. Make single click on the viewer image/background a no-op and double-click on the non-control viewer surface return to the grid.
7. Make a targeted toolbar/layout fix only where browser hit-test evidence shows Back is covered or unreachable. This regression validates pointer hit-testing only; Back keyboard focus is out of scope because the current viewer focus trap owns modal focus and the Back button is outside that dialog scope.

Changes requiring sign-off are new runtime dependencies, broad toolbar rewrites, sidebar visibility policy changes, replacing double-click return with double-click zoom, other navigation/hash semantic changes, or moving the fix into shared blob-loading behavior without evidence that a viewer-local guard is insufficient.

Deferred work is compare-viewer polish. CompareViewer may be checked for the same duplicate-image pattern, but code changes there are observe-only unless a shared change requires parity or browser evidence shows the same user-visible duplicate image in an existing compare acceptance path. Viewer pan slack must not change CompareViewer behavior unless that choice is made explicitly after evidence.


## Context


This plan follows the repository-root AGENTS.md. No PLANS.md was found. Lenslet is pre-release alpha, so a clean hard cutover is preferred over compatibility layers.

The initial review at docs/20260525_fix_flicker_and_button.md identifies the main flicker as current Viewer.tsx behavior: it fetches and renders a thumbnail blob, hides the full image until ready, then crossfades thumbnail and full image over 110ms. Because the fitted transform is not known until the full image load calls resetView(), the thumbnail can appear at top-left default geometry and then jump into the full-image coordinate system while fading out.

Current code also contributes to fast-load flashing by delaying readiness through requestAnimationFrame, opening the viewer with an opacity transition from 0 to 1, and lazy-loading the main Viewer behind an OverlayFallback. These are all on the user-reported gallery-to-fullscreen path.

Sequence evidence is available from flicker_sequences_verified and should be treated as concrete evidence, not speculation. Important examples are seq_09 around frames 000513-000520, which shows the ghost or thumbnail-like viewer image before and during full-image reveal, and seq_07 frame 000396-00m13.167s-ba5000ee65, which shows the cursor over the visible Back button with no apparent hover or click response.

Current pan behavior is hard-clamped by clampImageTransform in frontend/src/lib/imageTransform.ts. When a transformed image reaches a strict left, right, top, or bottom edge, further dragging in that direction stops immediately. At default fitted scale, the transform is effectively locked to the centered fit, so the image cannot be panned even though the user expects fullscreen inspection to allow some movement. The user explicitly does not want that restrictive edge feel in fullscreen inspection.

Current click behavior closes the viewer on a single backdrop click through handleBackdropClick in Viewer.tsx. The user explicitly wants single click to do nothing in fullscreen, with double-click as the optional quick way back to the grid. Back, Escape, and the explicit Close control should continue to close the viewer.

The Back button issue is likely a toolbar hit-test or layout collision near compact widths. Current Toolbar.tsx mixes viewer Back, zoom, image nav, panel toggles, sync, hidden browse controls, and normal browse toolbar slots into one surface. The existing browser harness checks a single center point, which can pass even if other visible parts of the Back button are covered. The recorded sequence viewport is 1650x1194, so the browser sweep must include that exact size and nearby wide widths, not only compact widths.

Material assumptions are that the user’s “fullscreen” means the current Image viewer dialog opened from VirtualGrid double-click. Default-scale pan acceptance starts from the image surface; background panning at default scale is not required unless browser or user evidence later shows it is expected. If a timing-sensitive baseline does not reproduce locally, implementation should still continue after recording DOM/style evidence that the risky paths exist: Viewer thumbUrl, duplicate image elements, RAF readiness, open fade, viewer fallback, strict transform clamp, and single-click backdrop close.


## Plan of Work


The implementation agent must update this plan continuously while working, especially Progress Log and Artifacts and Handoff. After each sprint, add handoff notes with changed files, browser evidence path, commands run, and remaining risk. For minor script-level uncertainty such as exact helper placement, proceed according to this approved plan to maintain momentum, then ask for clarification after the sprint and apply follow-up adjustments.

For every substantive code ticket, the implementation agent must use the better-code skill before and during implementation when that skill is available in the environment. If better-code is unavailable, perform the same assumptions, invariants, smallest robust approach, and evidence-backed validation gate manually and record the fallback in Progress Log. The implementation agent must state material assumptions and ambiguous interpretations before coding, choose the smallest non-speculative solution, touch only lines tied to the request, invariants, or verification, remove only unused code introduced by the change, and attach a concrete verification check to each step.

Delegate subagents early when that reduces context load or speeds execution, especially for cleanup and review gates, when subagent tooling is available in the implementation environment. If subagents, code-simplifier, or code-review are unavailable, perform the same cleanup and review gates manually and record that fallback in Progress Log. When subagents are available, let them continue long enough to produce useful results. If a subagent is still in progress after 10 minutes, ask for a brief progress update and why more time is needed instead of terminating it just to return faster.

Scope budget is four implementation sprints plus final ship gates, with eleven tickets. Expected write areas are frontend/src/features/viewer/Viewer.tsx, frontend/src/features/viewer/hooks/useZoomPan.ts, frontend/src/lib/imageTransform.ts, frontend/src/app/AppShell.tsx, frontend/src/shared/ui/Toolbar.tsx, frontend/src/styles.css, a focused browser validation script such as scripts/viewer_flicker_back_browser.py or a small addition to scripts/responsive_geometry_harness.py, focused frontend tests under frontend/src/**/__tests__, and regenerated src/lenslet/frontend/ only after all behavior gates pass.

The preferred validation implementation is a focused Playwright script for this regression. Its minimal contract is three probe modes: viewer open sampling, Back pointer sweep, and viewer interaction sweep. Add broad diagnostic metadata only for failed Back points or failing flicker samples. Defer compare sampling unless a shared code change or failing evidence requires it. Extend responsive_geometry_harness.py only if the edit stays modest; it is already large, and this fix should not turn the harness into a dumping ground.

Quality guardrail: this is a minimum robust fix. Do not replace the thumbnail flicker with another image-like placeholder, do not hide failures behind longer fades, do not change shared blob URL behavior unless viewer-local guarding fails, do not add unbounded pan freedom that lets the image disappear, and do not solve Back by only raising z-index unless browser evidence proves the viewer overlay is the covering element.

Debloat and removal targets are:

1. Remove Viewer.tsx thumbUrl and img alt="thumb" rendering from the primary viewer.
2. Remove the viewer full-image opacity crossfade and the readiness RAF delay.
3. Remove unused viewer opening-visible state from the viewer hook if it becomes obsolete.
4. Remove the main viewer lazy fallback path by directly importing Viewer.
5. Remove single-click backdrop close behavior from the fullscreen viewer surface.
6. Remove only toolbar hit-test participants that evidence proves are covering Back in viewer mode.

### Sprint Plan


Sprint 1, baseline browser evidence. The demo outcome is a browser evidence JSON that captures the current flicker, pan, click, and Back risks, or records why the visual flicker was not reproduced while still proving the risky DOM/CSS paths exist.

1. FBB-0, branch and codepath sanity. Confirm branch, git status, and current code signatures: Viewer thumbUrl, viewer readiness RAF, viewer open fade, lazy Viewer fallback, strict clampImageTransform edge bounds, single-click backdrop close, and toolbar Back slot. Validation is git status plus targeted rg output recorded in Progress Log.
2. FBB-1, viewer-open ghost sampler. Add a focused browser probe that opens the first gallery image and samples immediately after double-click without waiting for settle. Record dialog opacity, fallback presence, viewer loading state, thumbnail/ghost image evidence, full image evidence, current path, opacity, rect, transform, natural dimensions, and visible image count. Include normal fast load and an artificial delayed /file route of about 250-400ms. If current code does not fail visually on local timing, record DOM/style evidence and continue.
3. FBB-2, Back hit-target baseline. Add a Back probe that samples a 3x3 or 5x3 grid of points inside [data-toolbar-control="back"], records document.elementFromPoint details, and performs actual Back clicks at top-center, center, and bottom-center. Sweep widths at minimum 899, 900, 901, 960, 1024, 1100, 1179, 1180, 1181, 1240, 1280, 1360, 1440, 1600, 1650, and 1700, and include the exact recorded viewport size 1650x1194. For every failed point, record the direct hit element tag, class, and id; nearest [data-toolbar-control]; nearest [data-toolbar-slot]; nearest .toolbar-shell, .toolbar-left, .toolbar-center, and .toolbar-right; nearest viewer or dialog element; computed pointer-events, z-index, position, opacity, and visibility; and both the hit element rect and Back rect. Back keyboard focus is out of scope for this regression because the viewer focus trap currently owns focus; validate physical hit testing and pointer clickability only.
4. FBB-3, pan and click baseline. Add browser probes at the default fitted scale and at an enlarged zoom level. In both states, start drags from the image surface, drag left, right, up, and down, including after reaching all four strict edge clamps. Record before/after transforms and whether additional drag changes tx/ty beyond the old clamp. Also record that a single click on the viewer background currently closes, then add a pending acceptance for single-click no-op and guarded double-click return.

Sprint 2, viewer flicker root fix. The demo outcome is gallery-to-viewer open with no visible thumbnail/ghost/previous image and no viewer fallback flash in the primary browser path.

1. FBB-4, remove viewer image-like placeholder and crossfade. In Viewer.tsx, remove api.getThumb usage and the thumbnail img. Remove full-image opacity transition and make the loaded full image render at opacity 1 only after ready. Add a stable selector or attribute such as data-viewer-loading-state for loading/ready evidence. For slow loads, show no image-like content for the first short delay, then a neutral loader only after the delay threshold. The delayed loader timer and loader state must be path-keyed, cancelled when the image becomes ready, and cleaned up on path change, URL change, unmount, and stale or failed loads so no old-path loader can flash before the full image appears.
2. FBB-5, collapse readiness and guard stale paths locally. Remove the requestAnimationFrame delay in markImageReady so resetView(), loadedPath, and ready update together. Use a viewer-local path-keyed image resource, such as { path, url }, and render the full image only when resource.path === path. Clear the active viewer image resource immediately when the path changes unless the new path already has a resolved URL. Do not render previous-path image blobs at opacity 0 and rely on opacity alone for correctness. The hard invariant is that no image for a path other than the active viewer path may be renderable inside the viewer. Change useBlobUrl globally only if browser evidence proves local guarding cannot prevent stale display, and add consumer tests if that shared hook changes.
3. FBB-6, remove main viewer fallback flash. Directly import the main Viewer in AppShell.tsx so double-click open cannot show OverlayFallback("Loading viewer..."). Remove the Viewer-specific Suspense fallback wrapper if it becomes inert after direct import; otherwise document why it remains inert and cover it with the fallback-not-rendered browser check. Keep Inspector lazy and keep CompareViewer lazy unless later evidence requires otherwise. Do not design a preload subsystem unless direct import causes a measured build problem.

Sprint 3, viewer interaction comfort. The demo outcome is a viewer that permits bounded pan slack in all directions and does not close on accidental single click.

1. FBB-7, add viewer-only bounded pan slack. Keep clampImageTransform, panImageTransform, zoomImageTransformAroundPoint, and restoreImageTransformForCenter strict by default so CompareViewer and other consumers do not change implicitly. Add pan slack through an explicit option or a viewer-specific helper, then use the viewer slack policy for pointer pan, wheel zoom, pinch translate/zoom, and toolbar zoom in the main Viewer. Keep initial fit, reset, and restore-to-center strict so the image first appears centered and fitted; slack affects only user pan, drag, pinch, wheel, or zoom interactions after the initial ready state. Acceptance should prove drag changes tx/ty at default fit, zoom interactions do not snap the image back to strict bounds, and additional drag at the left, right, top, and bottom enlarged-image edges changes the transform beyond the old clamp by a meaningful amount while repeated dragging still keeps part of the image recoverable. Add focused unit tests in frontend/src/lib/__tests__/imageTransform.test.ts or the nearest existing transform test file proving default strict clamp remains strict, slack clamp allows movement when rendered size equals the container size, slack clamp allows movement when rendered size is smaller than the container size, slack clamp allows movement beyond strict bounds when zoomed, and slack clamp remains bounded.

   Use this clamp rule unless implementation evidence supports a smaller equivalent:

       For each axis, compute strict bounds first.
       If renderedSize > containerSize:
         strictMin = containerSize - renderedSize
         strictMax = 0
         slackMin = strictMin - slack
         slackMax = strictMax + slack
       If renderedSize <= containerSize:
         centered = (containerSize - renderedSize) / 2
         slackMin = centered - slack
         slackMax = centered + slack
       Use slack = min(96px, max(48px, containerSize * 0.10), renderedSize * 0.25).

2. FBB-8, replace single-click exit with double-click return. In Viewer.tsx, remove single-click backdrop close from the fullscreen surface. Add double-click return to grid on the non-control viewer surface, including the image and background, while preserving drag/pinch click suppression and keeping Back, Escape, and Close behavior intact. Add an explicit recent-drag/recent-pinch double-click guard, such as suppressSurfaceDoubleClickUntilRef, so a surface double-click cannot close the viewer if either click belonged to a drag, pan, or pinch sequence. The guard must cover the resulting dblclick event, not only the next click event. Ignore double-clicks whose target is inside button, input, select, textarea, a, or [role="button"] so toolbar buttons, close controls, mobile nav controls, and sliders cannot accidentally trigger viewer close.

Sprint 4, Back button pointer evidence or fix and full ship gates. The demo outcome is a viewer whose Back button is physically clickable across the visible button at all swept widths, with final browser and repository gates passing.

1. FBB-9, targeted Back fix from evidence. First rerun the expanded Back pointer sweep from FBB-2, including 899/900/901, 1179/1180/1181, 1600/1650/1700, and 1650x1194; this rerun is a blocking prerequisite before any Back CSS or layout change. If FBB-2 shows hidden browse controls or sibling toolbar items covering Back, remove or hide only those hit-test participants in viewer mode. If the viewer overlay covers Back, fix overlay stacking or toolbar offset instead and assert the viewer rect starts below the toolbar. If no pointer failure reproduces, do not make speculative Back CSS or layout changes; keep the expanded pointer sweep as the regression artifact and mark Back code changes as de-scoped.
2. FBB-10, compare observation and final gates. Run compare observation only if shared viewer/transform/blob code changed or evidence shows the same duplicate-image behavior in compare acceptance. Otherwise record compare as explicitly deferred. Then run frontend tests, build, browser gates, lint, gui smoke, and only then sync frontend/dist into src/lenslet/frontend/.

### Gate Routine


0. Plan gate. Before each ticket, the code agent briefly restates the goal, acceptance criteria, material assumptions/ambiguities, and files to touch. If an ambiguity would change behavior, it stops and asks. For substantive code work, it invokes better-code when available to restate invariants, the smallest robust approach, and verification evidence; if unavailable, it performs the same gate manually and records the fallback.

1. Implement gate. The code agent implements the smallest coherent slice that satisfies the ticket. It avoids speculative features, one-off abstractions, unrelated cleanup, and broad refactors unless explicitly approved. Each ticket must have at least one verification signal, and every sprint must include browser validation.

2. Cleanup gate. After each complete sprint, run the code-simplifier routine below on only the current sprint diff when the tool is available; otherwise perform the same conservative cleanup review manually and record the fallback.

3. Review gate. After cleanup, run the review routine below on the post-cleanup diff when the tool is available. Apply fixes and rerun review when needed before declaring the sprint complete. If review subagents are unavailable, perform a manual constructively adversarial diff review and record the fallback.

### code-simplifier routine


After each complete sprint, spawn a subagent and instruct it to use the code-simplifier skill to scan only the current sprint changes when that tooling is available. If unavailable, perform the same cleanup pass manually and record the fallback in Progress Log. Start with non-semantic cleanup: formatting/lint autofixes, obvious dead code introduced by the sprint, small readability edits that do not change behavior, and docs/comments that reflect what is already true. Keep this pass conservative; do not expand into semantic refactors unless explicitly approved.

Once the cleanup subagent starts, do not interrupt or repurpose it just to save time. If it runs long, wait or request a progress update. Fall back to manual cleanup only if the subagent is unavailable, fails, or the user explicitly approves the downgrade.

### review routine


After each complete sprint and after the cleanup subagent finishes, spawn a fresh agent and request a code review using the code-review skill when that tooling is available. If unavailable, perform the same constructively adversarial review manually and record the fallback in Progress Log. The review must actively look for ways the change could fail, where scope or validation is weak, and what should be removed or simplified, while keeping feedback actionable and focused on shipping a robust result.

Use the best available model in the environment with reasoning_effort set to medium. Do not default to mini or fast models for review unless the user explicitly approves that downgrade. Review the post-cleanup diff, apply fixes, and rerun review when needed. Once review starts, do not interrupt, repurpose, or terminate it to save time or reclaim control. Manual diff review is a fallback only when the review subagent is unavailable, fails after a reasonable wait plus progress check, or the user explicitly approves the downgrade.


## Validation and Acceptance


Primary validation gates must use a real browser on the user-reported path: open a gallery image into the viewer, sample early frames without waiting for settle, pan against all four image edges, validate single-click/double-click semantics, and click the Back button across its visible interior. Secondary gates are unit tests, build, lint, gui smoke, and generated asset sync.

Sprint 1 primary validation is:

    python scripts/viewer_flicker_back_browser.py --mode baseline --output-json data/fixtures/viewer_flicker_back_baseline.json

Expected outcome before fixes is either a captured failure or evidence showing at least one risky path: visible viewer thumbnail/ghost, duplicate visible image, viewer fallback flash, delayed readiness/open fade signatures, strict edge clamp, single-click close, or bad Back hit sample. If the exact probe is implemented inside responsive_geometry_harness.py instead, record the actual command and JSON path in Progress Log.

Sprint 2 primary validation is:

    python scripts/viewer_flicker_back_browser.py --mode viewer --output-json data/fixtures/viewer_flicker_after.json

Expected outcome is no old img[alt="thumb"] element and, inside the viewer surface, no visible image-like element other than the active full image during open or after full-image readiness. This includes img, picture, canvas, background-image placeholders, and previous-path blob images. There must be no previous-path image visible during next-image navigation, no OverlayFallback("Loading viewer...") during normal open, and no full image visible before the fitted transform is known. In delayed /file mode, only the neutral loading state may appear after the threshold, identified by a stable attribute rather than fragile visible text, and the delayed loader must be cancelled when the full image becomes ready. A rapid next/previous delayed-route check must prove old-path image resources and old-path loader timers do not become visible after the active path changes.

Sprint 3 primary validation is:

    python scripts/viewer_flicker_back_browser.py --mode interactions --output-json data/fixtures/viewer_interactions_after.json

Expected outcome is that at default fitted scale, dragging from the image surface left, right, up, and down changes tx or ty within the computed slack region instead of leaving the image locked. The initial ready transform remains centered and fitted before user pan input. After reaching each strict enlarged-image edge, an additional drag in the same direction must still change tx or ty enough to show bounded background slack, and wheel, pinch, and toolbar zoom must not snap the image back to strict bounds. Validate movement against the computed slack bound from the implemented formula; use a fixed 64px target only for a fixture and viewport where the computed slack is at least 64px. Single click on the viewer image or background must leave the viewer open. Double-click on the non-control viewer surface must close to the grid. A double-click produced by a recent drag, pan, or pinch must not close the viewer, and double-clicking toolbar buttons, close controls, sliders, or mobile nav controls must not trigger the surface double-click handler.

Sprint 4 primary validation is:

    python scripts/viewer_flicker_back_browser.py --mode back --output-json data/fixtures/viewer_back_after.json

Expected outcome is that every sampled interior point inside the visible Back button resolves to [data-toolbar-control="back"] or one of its descendants, and clicks at top-center, center, and bottom-center close the viewer at every required width, including 899, 900, 901, 960, 1024, 1100, 1179, 1180, 1181, 1240, 1280, 1360, 1440, 1600, 1650, 1700, and the recorded 1650x1194 viewport. Back keyboard focus is out of scope for this regression unless the ticket is explicitly expanded to treat the viewer toolbar as modal chrome.

Final primary validation is:

    python scripts/viewer_flicker_back_browser.py --mode all --output-json data/fixtures/viewer_flicker_back_after.json

Expected outcome is that the viewer flicker and Back gates still pass after all review fixes. If CompareViewer was changed, the compare sampler must also show no visible thumb or duplicate image after full images become visible. If CompareViewer was not changed, record the observation result and the explicit deferral.

Secondary validation commands are:

    cd frontend && npm run test
    cd frontend && npm run build
    python scripts/lint_repo.py
    python scripts/gui_smoke_acceptance.py

Only after those pass, sync generated frontend assets:

    rsync -a --delete frontend/dist/ src/lenslet/frontend/

Expected secondary outcomes are all commands pass, generated frontend assets are synchronized only at the end, and no unrelated files are reformatted.


## Risks and Recovery


The main risk is a nondeterministic baseline: flicker may be missed on a fast machine. Recovery is to treat visual baseline failure as useful but not mandatory, and to continue when DOM/style evidence proves the dangerous paths still exist.

Another risk is clearing or revoking object URLs too aggressively and causing a blank image during navigation. Recovery is to prefer viewer-local visibility guards first and preserve existing object URL revocation behavior unless a shared hook change is proven necessary.

Pan slack can become too loose and make the image feel lost. Recovery is to keep the margin bounded, verify each direction, and assert that repeated dragging still leaves part of the image visible. Shared transform helpers are used by CompareViewer, so strict behavior must remain the default unless compare is deliberately included.

Double-click return can conflict with drag/pinch or controls. Recovery is to keep the existing click-suppression concept but add an explicit recent-drag/recent-pinch guard that suppresses the resulting dblclick event, bind double-click only on non-interactive viewer surface targets, and keep Escape, Back, and Close as explicit exits. Single-click must remain a no-op on the viewer surface after this change.

Toolbar fixes can regress browse mode or mobile controls if they become a broad layout rewrite. Recovery is to make the Back fix evidence-driven and scoped to the covering element found by the browser probe. If overlay stacking is the culprit, fix overlay offset/z-index; if toolbar sibling controls are the culprit, hide or reflow only those viewer-mode participants.

Rollback is file-scoped: Viewer.tsx for flicker and click policy, useZoomPan.ts and imageTransform.ts for pan slack, AppShell.tsx for viewer import/fallback behavior, Toolbar.tsx and styles.css for Back hit-testing, and the focused browser script or responsive geometry harness addition for probes. Retry is idempotent: rerun the same browser JSON command after each fix and compare predicates instead of relying on screenshots alone.


## Progress Log


- [x] 2026-05-25 19:03 UTC, plan created from user report and docs/20260525_fix_flicker_and_button.md.
- [x] 2026-05-25 19:03 UTC, subagent review incorporated: baseline visual failure is not a blocker, toolbar work is evidence-driven, useBlobUrl remains local-first, compare is observe-only, and final asset sync is isolated.
- [x] 2026-05-25 19:06 UTC, user-requested viewer interaction behavior added: bounded pan slack in all directions, single-click no-op, and double-click return to grid because strict edge clamps and accidental single-click exits make fullscreen inspection feel restrictive.
- [x] 2026-05-25 19:07 UTC, clarified that pan slack must work at default fitted scale too, not only after zooming or enlarging the image.
- [x] 2026-05-25 19:32 UTC, reviewer notes incorporated: recorded sequence evidence is now cited, main Viewer direct import is required, viewer images are path-keyed, pan slack is viewer-specific with explicit bounds, Back validation is pointer-only with 1650x1194 coverage, image-like placeholder detection is broadened, loader cancellation is required, and skill/subagent gates have manual fallbacks.
- [x] 2026-05-25 19:32 UTC, plan-review subagent feedback incorporated: stale Sprint 1 artifact claims were reset because `scripts/viewer_flicker_back_browser.py` is absent in this workspace; loader cleanup now covers path/URL changes and unmount; viewer slack policy now covers pan, wheel, pinch, and toolbar zoom; Back code changes are blocked on the expanded pointer rerun; compare sampling is deferred unless shared code or evidence requires it.
- [x] 2026-05-25 19:52 UTC, Sprint 1 complete.
  - [x] FBB-0 complete: branch `main` at `6a40acc`; working tree already had untracked plan/Ralph docs; code signatures confirmed for Viewer `thumbUrl`/`img[alt="thumb"]`, RAF readiness, open opacity fade, AppShell lazy Viewer fallback, strict `clampImageTransform`, single-click backdrop close, and toolbar Back slot.
  - [x] FBB-1 complete: added `scripts/viewer_flicker_back_browser.py` and ran viewer-open sampling in normal and 350ms delayed `/file` modes. Baseline JSON records thumbnail, fallback, crossfade, duplicate visible image, invisible full-image, and open-fade class evidence.
  - [x] FBB-2 complete: expanded Back pointer sweep covers 899, 900, 901, 960, 1024, 1100, 1179, 1180, 1181, 1240, 1280, 1360, 1440, 1600, 1650, 1700, and 1650x1194. Baseline reproduced 81 failed interior points and 15 failed physical Back clicks, mainly where the zoom slider or `.toolbar-center` covers the Back button.
  - [x] FBB-3 complete: pan/click baseline records no default-fit pan movement in all four directions, no additional movement beyond enlarged strict edge clamps in all four directions, and current single-click plus double-click closure behavior on both image and background surfaces.
- [x] 2026-05-25 20:41 UTC, Sprint 2 complete.
  - [x] FBB-4 complete: removed the main Viewer thumbnail fetch/render path, full-image crossfade classes, and opening opacity fade. Slow full-image loads now expose `data-viewer-loading-state` and show a neutral delayed loader only after the path-keyed delay threshold.
  - [x] FBB-5 complete: replaced stale URL visibility with a viewer-local `{ path, url }` resource guard. Path changes clear ready/resource state, URL changes are the only place a blob URL is bound to the current path, and readiness now resets transform and visible state in one update path without the old RAF delay.
  - [x] FBB-6 complete: AppShell directly imports the main Viewer and no longer wraps it in the `OverlayFallback("Loading viewer...")` Suspense path. Inspector and CompareViewer remain lazy.
  - [x] Sprint 2 validation complete: `--mode viewer` now covers delayed neutral loader appearance, no early loader, no thumb/fallback/crossfade/open-fade evidence, rapid next/previous delayed navigation without visible non-active images, and no stale loader during cached rapid-previous navigation.
- [x] 2026-05-25 21:16 UTC, Sprint 3 complete.
  - [x] FBB-7 complete: added strict-default transform clamp options plus viewer-only bounded pan slack. Main Viewer pan, wheel zoom, pinch translate/zoom, and toolbar zoom now use the slack policy while initial fit, resize restore, and CompareViewer callers remain strict by default.
  - [x] FBB-8 complete: removed single-click surface exit and added double-click return on the non-control viewer surface. Recent drag/pinch interactions suppress the resulting click and double-click window, while explicit controls are excluded from the suppression path.
  - [x] Sprint 3 validation complete: `--mode interactions` now asserts strict initial fit, computed slack bounds, old strict-edge reach before additional edge drag, wheel/toolbar/pinch zoom evidence, single-click no-op, double-click return, guarded double-click after drag, and control double-click non-closure.
- [x] 2026-05-25 21:32 UTC, Sprint 4 complete.
  - [x] FBB-9 complete: reran the expanded Back pointer sweep before editing and reproduced center toolbar/zoom slider coverage at 901, 960, 1181, 1240, 1280, and 1360 px. Added a viewer-scoped toolbar CSS rule that removes browse-only left controls from layout in viewer mode, then reran the Back sweep successfully across all required widths, including 1650x1194.
  - [x] FBB-10 complete: compare observation was run because Sprint 3 touched shared transform code; it showed two visible compare full images and zero visible compare thumbs after both compare images were ready. Final frontend tests, build, full browser regression, lint, GUI smoke, generated asset sync, cleanup, and review gates passed.


## Artifacts and Handoff


Initial review input is docs/20260525_fix_flicker_and_button.md. The plan file is docs/20260525_fix_viewer_flicker_back_button_plan.md.

Expected implementation evidence should include baseline and fixed browser JSON outputs, any focused frontend test transcripts, frontend build transcript, lint transcript, gui smoke transcript, and a note on whether src/lenslet/frontend/ was regenerated.

Sprint 1 handoff, 2026-05-25 20:15 UTC: `scripts/viewer_flicker_back_browser.py` now exists and supports `baseline`, `viewer`, `interactions`, `back`, and `all` modes. `baseline` is evidence-only; fixed modes now have acceptance predicates so `viewer`, `interactions`, `back`, and `all` fail when covered gates still show broken behavior. Fresh baseline evidence was written to `data/fixtures/viewer_flicker_back_baseline.json` with status `passed`; this path is under ignored `data/` fixtures but remains the local browser evidence artifact. Validation commands run: `python -m py_compile scripts/viewer_flicker_back_browser.py`; `python scripts/viewer_flicker_back_browser.py --mode baseline --output-json data/fixtures/viewer_flicker_back_baseline.json`; `python scripts/viewer_flicker_back_browser.py --mode interactions --output-json data/fixtures/viewer_interactions_baseline.json` before fixed-mode predicates were added; `python scripts/viewer_flicker_back_browser.py --mode viewer --output-json /tmp/lenslet-viewer-current-fail.json` (expected failure on current code, 40 acceptance failures after stricter visible-image checks); `python scripts/viewer_flicker_back_browser.py --mode interactions --output-json /tmp/lenslet-interactions-current-fail.json` (expected failure on current code, 18 acceptance failures); `python scripts/viewer_flicker_back_browser.py --mode back --output-json /tmp/lenslet-back-current-fail.json` (expected failure on current code, 21 acceptance failures); `python scripts/lint_repo.py` (passed, with warn-only large-file notices including the new focused script at 1299 lines); `git diff --check` (passed). Cleanup/review result: removed a dead Playwright tuple assignment, added the missing double-click image sample, added stricter fixed-mode acceptance predicates for visible image-like placeholders, Back point/click completeness, interaction movement direction, and recoverability, and recorded FBB-0 traceability in the Ralph progress log. No frontend assets were regenerated in Sprint 1 because this sprint added evidence only. Residual validation work for later sprints: before accepting Sprint 2/3 fixes, extend or verify the fixed-mode predicates for first-visible full-image fitted transform, delayed-route next/previous stale path and loader cancellation, computed slack bounds plus toolbar/pinch zoom behavior, and double-click suppression after drag/pan/pinch or on controls.

Sprint 1 and Sprint 2 are closed. Do not mark any later sprint complete unless its browser acceptance gate passes on the gallery-to-viewer path. If this plan is revised, add a brief note here explaining what changed and why.

Sprint 2 handoff, 2026-05-25 20:41 UTC: `frontend/src/features/viewer/Viewer.tsx` no longer requests or renders thumbnails in the primary viewer, no longer opacity-fades the dialog or full image, and renders the active full image only through a path-keyed resource that matches the current viewer path. `frontend/src/features/viewer/hooks/useZoomPan.ts` dropped the obsolete opening-visible state. `frontend/src/app/AppShell.tsx` imports Viewer directly, removing the gallery-to-viewer Suspense fallback flash. `scripts/viewer_flicker_back_browser.py` now uses browser-side delayed `/file` fetches, asserts delayed neutral loader appearance after the threshold, samples rapid navigation beyond initial prefetch offsets, and forbids stale loader frames during cached rapid-previous navigation. Generated assets in `src/lenslet/frontend/` were rebuilt and synchronized from `frontend/dist/`; the standalone Viewer chunk disappeared because Viewer is now in the main bundle. Validation commands run: `python -m py_compile scripts/viewer_flicker_back_browser.py`; `cd frontend && npm run test -- src/features/viewer/hooks/__tests__/useZoomPan.test.ts` (passed after correcting an initial invalid Vitest filter invocation); `cd frontend && npm run test` (75 files, 356 tests passed); `cd frontend && npm run build` (passed); `python scripts/viewer_flicker_back_browser.py --mode viewer --output-json data/fixtures/viewer_flicker_after.json` (passed after harness review fixes, with positive delayed-loader evidence for delayed open and rapid next navigation and no stale loader evidence during rapid previous); `python scripts/lint_repo.py` (passed with warn-only large-file notices); `git diff --check` (passed). Cleanup/review result: code-simplifier sidecar made two Tier 1 cleanups; code-review sidecar found incomplete generated asset staging and three harness false-pass risks, which were fixed and revalidated. Residual work remains Sprint 3 pan/click behavior and Sprint 4 Back pointer fix/final gates.

Sprint 3 handoff, 2026-05-25 21:16 UTC: `frontend/src/lib/imageTransform.ts` now supports optional `panSlack` clamp behavior while keeping strict clamps as the default. `frontend/src/lib/__tests__/imageTransform.test.ts` covers strict default behavior plus equal-size, smaller-than-container, and zoomed-image slack bounds. `frontend/src/features/viewer/hooks/useZoomPan.ts` applies viewer-only slack to pointer pan, wheel zoom, pinch translate/zoom, and toolbar zoom through a single transform path; initial ready/reset and resize restore stay strict. `frontend/src/features/viewer/Viewer.tsx` no longer exits on single surface click and closes on double-click only for non-control surface targets, with recent drag/pinch suppression that also covers the resulting dblclick event. `scripts/viewer_flicker_back_browser.py` now validates strict initial fit, computed slack bounds, old strict-edge reach before additional edge movement, wheel/toolbar/pinch zoom, single-click no-op, double-click return, and guarded double-click behavior. Generated assets in `src/lenslet/frontend/` were rebuilt and synchronized from `frontend/dist/`; `rsync` was unavailable, so the generated bundle directory was cleared and copied from `frontend/dist/`. Validation commands run: `python -m py_compile scripts/viewer_flicker_back_browser.py`; `cd frontend && npm run test -- src/lib/__tests__/imageTransform.test.ts src/features/viewer/hooks/__tests__/useZoomPan.test.ts` (passed); `cd frontend && npm run test` (75 files, 360 tests passed); `cd frontend && npm run build` (passed); `python scripts/viewer_flicker_back_browser.py --mode interactions --output-json data/fixtures/viewer_interactions_after.json` (passed); `python scripts/lint_repo.py` (passed with warn-only large-file notices, `scripts/viewer_flicker_back_browser.py` at 1785 lines below the 2000-line hard limit); `git diff --check` (passed). Cleanup/review result: code-simplifier sidecar found no Tier 1 cleanup to apply. code-review sidecar findings were fixed: control clicks are not suppressed after drag/pinch, SVG descendants inside controls are recognized via `Element.closest`, the edge-pan browser gate now asserts old strict-edge reach before additional drag, and generated frontend assets are included in the sprint commit. Residual work remains Sprint 4 Back pointer rerun/fix and final ship gates.

Sprint 4 handoff, 2026-05-25 21:32 UTC: `frontend/src/styles.css` now hides browse-only left toolbar participants (`.toolbar-scope`, `.toolbar-sort`, `.toolbar-filter`, and `.toolbar-slot-refresh`) only inside `.toolbar-shell-viewer`, preventing the visible Back button from sitting under the viewer zoom slider or `.toolbar-center`. `src/lenslet/frontend/` was rebuilt and synchronized from `frontend/dist/`; `rsync` was unavailable, so the generated bundle directory was cleared and copied from `frontend/dist/`. Browser evidence was written locally under ignored `data/fixtures/`: `viewer_back_after.json`, `viewer_compare_observation_after.json`, and `viewer_flicker_back_after.json`. Validation commands run: `python scripts/viewer_flicker_back_browser.py --mode back --output-json data/fixtures/viewer_back_after.json` before the CSS edit (failed as expected, center toolbar coverage reproduced); `cd frontend && npm run build` (passed); `python scripts/viewer_flicker_back_browser.py --mode back --output-json data/fixtures/viewer_back_after.json` (passed, 17 Back scenarios and zero failures); compare observation script (passed, zero visible compare thumbs and two visible compare full images after readiness); `cd frontend && npm run test` (75 files, 360 tests passed); `cd frontend && npm run build` (passed); `python scripts/viewer_flicker_back_browser.py --mode all --output-json data/fixtures/viewer_flicker_back_after.json` (passed, zero acceptance failures); `python scripts/lint_repo.py` (passed with warn-only large-file notices); `python scripts/gui_smoke_acceptance.py` (passed with the existing folder re-entry anchor warning); `git diff --check` (passed). Cleanup/review result: code-simplifier sidecar made no edits; code-review sidecar found no actionable issues. All planned sprints and acceptance gates are complete.

Revision note: the 2026-05-25 19:06 UTC revision expanded the plan beyond flicker and Back hit-testing to cover two newly reported fullscreen interaction expectations. Bounded pan slack is included because the user wants edge inspection to feel less restrictive. Single-click no-op plus double-click return is included because accidental single-click exits interrupt fullscreen inspection, while double-click remains an intentional quick-return gesture. The 2026-05-25 19:07 UTC revision clarified that pannability must exist at the default fitted scale as well as at enlarged zoom levels. The 2026-05-25 19:32 UTC revision incorporated reviewer notes to cite the recorded sequences, require direct Viewer import, make viewer image rendering path-keyed, keep slack viewer-specific and bounded across viewer pan and zoom paths, remove Back keyboard acceptance from this regression, broaden Back and flicker probes, make process skills/subagents non-blocking when unavailable, and reset stale Sprint 1 artifact claims.
