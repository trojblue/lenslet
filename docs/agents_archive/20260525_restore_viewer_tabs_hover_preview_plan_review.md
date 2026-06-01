I’d **approve this plan with edits**. The direction is right: restore the old product intent first, keep the safety pieces only where they do not change behavior, and prove the two regressions in-browser.

The main thing I would change is that the plan currently assumes a working branch that does not match the uploaded zip I inspected. In this uploaded repo snapshot:

* `AppShell.tsx` imports `Viewer` and `CompareViewer` directly, not through a lazy viewer/compare boundary.
* `VirtualGrid.tsx` already uses `api.getFile(path)` for hover preview.
* The hover overlay already renders with `max-w-[80vw] max-h-[80vh]`.
* There is no `frontend/src/features/browse/model/hoverPreview.ts`.
* There is no `scripts/overall_cleanup_browser.py`; the existing browser harness is `scripts/responsive_geometry_harness.py`.

So the plan is good for the **regressed branch you describe**, but I would add a short branch-alignment gate before implementation so the agent does not “fix” things that are already restored or chase nonexistent files.

## Changes I would make

### 1. Add `RVP-0: branch sanity check`

Add this before Sprint 1:

```text
RVP-0: Confirm the working branch matches the regression assumptions.

Before editing, inspect:
- AppShell viewer/compare imports and any Suspense/lazy fallback path.
- Viewer/Compare ready/thumbnail/opacity behavior.
- VirtualGrid hover preview fetch path.
- API client hover/file/thumb methods.
- Existing browser harness names.

If the branch already uses direct Viewer/Compare imports, do not spend RVP-3 on lazy fallback removal.
If hover already uses original /file and 80vw/80vh sizing, RVP-4/RVP-5 should narrow to stale-response, abort, scroll-clear, and browser-evidence hardening.
If files named in this plan do not exist, do not create broad new abstractions merely to match the plan wording.
```

This prevents the implementation from becoming cargo-cult cleanup.

---

### 2. Replace “desktop/tablet” with “normal layout can show the side region”

The plan says desktop/tablet in several places. I would tighten that to this rule:

```text
When overlay is active, preserve the side regions that the normal non-overlay responsive policy would have rendered for the current viewport, unless short-height or phone/narrow suppression already makes those regions ineffective.
```

Even better:

```text
Overlay mode must not be a suppression reason by itself. Compute effective sidebars from the same normal layout constraints, then use those effective widths as overlay insets when overlay is active.
```

That avoids boundary weirdness. For example, this repo’s policy labels `900px` as `narrow`, but its normal layout can still fit both sidebars in some cases. If the user’s complaint is “when normal side regions were visible, opening viewer erased them,” the fix should not depend too heavily on the string `'tablet'` or `'desktop'`.

The unit test should compare overlay mode to a normal model:

```ts
const normal = model({ overlay: 'none', viewportWidth: 1440 })
const viewer = model({ overlay: 'viewer', viewportWidth: 1440 })

expect(viewer.leftWidth).toBe(normal.leftWidth)
expect(viewer.rightWidth).toBe(normal.rightWidth)
expect(viewer.effectiveLeftOpen).toBe(normal.effectiveLeftOpen)
expect(viewer.effectiveRightOpen).toBe(normal.effectiveRightOpen)
expect(viewer.overlayInsets).toEqual({
  left: normal.leftWidth,
  right: normal.rightWidth,
})
```

Then add negative cases:

```ts
expect(model({ overlay: 'viewer', viewportWidth: 390 }).overlayInsets).toEqual({ left: 0, right: 0 })
expect(model({ overlay: 'viewer', viewportWidth: 1024, viewportHeight: 480 }).overlayInsets).toEqual({ left: 0, right: 0 })
```

That makes the intended behavior precise.

---

### 3. Make `RVP-2` more surgical

Current policy has this shape:

```ts
if (overlayActive || shortHeight) {
  // suppress all sidebars
}
```

The corrective fix should not need a large rewrite. Change the plan to say:

```text
Remove overlay-active from the early full-sidebar suppression branch. Keep short-height suppression. Let the existing normal sidebar feasibility algorithm compute effective widths. Then set overlayInsets to the effective visible widths only when overlay is active.
```

In other words, avoid making `overlayActive` a layout-destroying condition.

The likely implementation shape is:

```ts
if (shortHeight) {
  // existing short-height suppression
}

// existing normal sidebar computation

return {
  ...
  gridInsets: { left: leftWidth, right: rightWidth },
  overlayInsets: overlayActive
    ? { left: leftWidth, right: rightWidth }
    : { left: 0, right: 0 },
}
```

Keep `mobileDrawerHeightPx` disabled under overlays. That part is still right:

```ts
mobileShell && !overlayActive && input.mobileDrawerOpen ? ...
```

---

### 4. Add a very specific `Viewer.tsx` ready-state race to `RVP-3`

The plan correctly suspects thumbnail/ready/opacity code, but I’d make the likely bug more explicit.

In the uploaded snapshot, `Viewer.tsx` has:

```ts
useEffect(() => {
  setReady(false)
}, [url])
```

and the full image does:

```tsx
onLoad={() => {
  fitAndCenter()
  setScale(1)
  requestAnimationFrame(() => setReady(true))
}}
```

That can produce a “loaded, then hidden again” race if the image load fires around the same time as the `[url]` effect. The browser can briefly show the full image, then the effect sets `ready` back to `false`, and the image opacity returns to zero.

I would add this to `RVP-3`:

```text
Specifically audit the ready reset race: URL-change effects must not set ready=false after the current full image has already loaded. Prefer complete/naturalWidth-aware readiness reconciliation, or remove the url-level ready reset and reset readiness at path/request start instead. The full image must not return to opacity 0 after its current src has completed.
```

The smallest robust fix is probably one of these:

```ts
useEffect(() => {
  if (!url) {
    setReady(false)
    return
  }

  const img = imgRef.current
  if (img?.complete && img.naturalWidth > 0) {
    fitAndCenter()
    requestAnimationFrame(() => setReady(true))
  } else {
    setReady(false)
  }
}, [url])
```

or remove the `[url] => setReady(false)` effect and reset readiness when the path/request starts, not after the image has already mounted.

Also: do not remove the thumbnail placeholder unless evidence proves it is the problem. The old product behavior can still have a placeholder; it just must not hide the final image.

---

### 5. Strengthen browser evidence for overlay containment

The browser test should not only check data attributes. It should compare actual rectangles.

Add this to `RVP-1`/`RVP-2` acceptance:

```text
Before opening viewer/compare, record left sidebar rect, right sidebar rect, grid shell rect, and app shell rect.

After opening viewer/compare:
- left/right side region rects remain visible and approximately unchanged;
- overlay left edge equals the center/grid shell left edge within 1px;
- overlay right edge equals the center/grid shell right edge within 1px;
- overlay width is not the whole viewport when side regions are visible;
- side regions are inert/non-interactive if modal ownership is retained.
```

The current existing harness assertion style is weaker because it checks whether the overlay is not “squeezed,” but now you want the opposite guarantee: it **must be contained to the center content area** when side regions are visible.

So add explicit equality-ish checks:

```text
abs(viewerRect.left - gridShellRect.left) <= 1
abs(viewerRect.right - gridShellRect.right) <= 1
```

For compare, check both the compare dialog and `.compare-stage`.

---

### 6. Clarify toolbar behavior

Your plan says side regions remain visible but modal focus remains owned by viewer/compare. Good.

But it does not clearly say what happens to the top toolbar. The repo’s previous responsive plan explicitly kept viewer toolbar chrome usable and inerted toolbar for compare only. In the uploaded snapshot, `AppShell.tsx` currently does:

```ts
if (compareOpen) {
  toolbar.setAttribute('inert', '')
}
```

not `overlayActive`.

So add one explicit decision:

```text
Toolbar policy:
- If the top toolbar Back/close/navigation controls are considered viewer chrome, keep them usable in viewer mode and test that explicitly.
- If viewer itself now owns all close/navigation controls, inert the toolbar under viewer too.
- Do not silently change this as part of the side-region restoration.
```

Without this, an implementation could “fix” modal ownership by disabling viewer toolbar behavior the product may have intentionally kept.

---

### 7. For hover preview, avoid shared-cache abort footguns

The plan’s hover direction is right: original `/file`, large overlay, stale guards, cleanup, abort where supported.

But I would specify this API shape more carefully:

```text
Do not make hover cancellation abort a shared fileCache request that viewer/compare may also be using. Prefer a dedicated hover-preview fetch method that:
- returns `{ promise, abort }`;
- uses `/file`;
- participates in the file request budget;
- may read from fileCache if already cached;
- should not necessarily write every hover blob into persistent fileCache.
```

Suggested shape:

```ts
getHoverPreviewFile(path: string): { promise: Promise<Blob>; abort: () => void }
```

Behavior:

```text
If fileCache already has the blob, return a resolved promise and no-op abort.
Otherwise use a direct abortable `/file` request through `runWithRequestBudget('file', ...)`.
```

That prevents this bad case:

1. viewer is loading full file A;
2. hover asks for full file A through the same cache/inflight entry;
3. user moves mouse away;
4. hover abort cancels the viewer’s full-file load.

That would be a nasty regression.

---

### 8. Make hover stale-response tests adversarial

The plan says stale-response guards, which is good. I would make the exact test scenario explicit:

```text
Delayed A, fast B:
1. Hover preview hotspot for image A.
2. Delay A's /file response.
3. Move to image B.
4. Resolve B's /file response.
5. Then resolve A.
6. Expected: preview remains B, A never replaces B, and A's object URL is not leaked.
```

Also test clear-on-scroll. In the uploaded snapshot, scroll sets `isScrolling` but does not obviously call `clearPreview()` in the scroll handler. Since the plan wants clear-on-scroll behavior, include:

```text
On grid scroll, active hover preview clears, pending timer is cancelled, pending request is aborted where supported, and current object URL is revoked.
```

For network evidence, be careful: the grid normally loads `/thumb` requests. The test should capture requests **after the hover action begins**, or use an unvisited image and assert the hover-specific request path. Otherwise normal thumbnail traffic can make the assertion noisy.

---

### 9. Change “current code should fail” language

Some tasks say current code should fail before the fix. That is useful for TDD, but risky if the branch has already partially reverted one behavior.

I’d rewrite those as:

```text
The regression branch should fail this check. If the current branch already passes, record that as evidence and avoid unnecessary edits.
```

That keeps the plan from forcing a failure where the code is already correct.

---

### 10. Use the existing harness unless the working branch has the newer script

In the uploaded repo, the best existing target is:

```bash
python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry.json
```

I would change the final gate section to say:

```text
Prefer extending `scripts/responsive_geometry_harness.py` if it exists. Add a small `scripts/viewer_preview_regression.py` only if a focused separate script is cleaner. Do not reference `scripts/overall_cleanup_browser.py` unless it exists in the working branch.
```

Then the final gates become:

```bash
python scripts/viewer_preview_regression.py --output-json /tmp/lenslet-viewer-preview-regression.json
# or
python scripts/responsive_geometry_harness.py --output-json /tmp/lenslet-responsive-geometry.json

python scripts/gui_smoke_acceptance.py --output-json /tmp/lenslet-gui-smoke.json
cd frontend && npm run test
cd frontend && npm run build
rsync -a --delete frontend/dist/ src/lenslet/frontend/
python scripts/lint_repo.py
```

---

## Smaller wording edits

I would soften this part:

```text
Remove viewer/compare thumbnail fade or ready-state code only if it is proven to be the flash/disappear source.
```

to:

```text
Do not remove thumbnail fallback or fade behavior wholesale. First fix readiness ownership so the full image cannot become hidden after the current image has loaded. Remove only the exact ready/fade code that evidence proves is responsible.
```

And change this:

```text
Hover preview may fetch original `/file` content again
```

to:

```text
Hover preview should fetch original `/file` content, preferably through a dedicated abortable hover-preview request path. It may reuse an already-cached full file, but should not downgrade to `/thumb`.
```

---

## My revised verdict

The plan is solid, but I would revise it around these points:

1. Add a branch sanity gate because the uploaded zip does not match several plan assumptions.
2. Define overlay restoration as “preserve whatever the normal layout can show,” not strictly “desktop/tablet.”
3. Make the policy fix surgical: remove overlay-active sidebar suppression, keep short-height suppression.
4. Explicitly target the `Viewer.tsx` `url -> setReady(false)` race as a likely flash/disappear cause.
5. Browser-test actual rectangles, not just data attributes.
6. Clarify whether viewer toolbar remains usable.
7. Use a dedicated abortable hover `/file` path so hover cancellation cannot kill viewer/compare file loads.
8. Make hover stale-response tests adversarial.
9. Treat “failing before fix” as branch-dependent.
10. Prefer extending `responsive_geometry_harness.py` unless the newer script exists in the working branch.

With those edits, the plan becomes much safer and more directly tied to the two behaviors you actually want restored.


I checked the new zip and diffed it against the earlier upload. The plan is **mostly right** for this current codebase. I would approve its direction, but I would tighten several parts before handing it to an implementation agent so it does not accidentally preserve the wrong new assumptions.

The current code confirms the plan’s two main diagnoses:

* `frontend/src/app/layout/responsiveLayoutPolicy.ts` still has an early `if (overlayActive || shortHeight)` return that sets both side widths and `overlayInsets` to `0`.
* `frontend/src/api/client.ts` has `api.getHoverPreview()` using `/thumb`, and `frontend/src/features/browse/model/hoverPreview.ts` caps the surface at `360×280`.
* The old `VirtualGrid.tsx` behavior really did use `api.getFile(path)` and a centered fixed overlay with `max-w-[80vw] max-h-[80vh]`.

## Recommended changes to the plan

### 1. Replace “desktop/tablet” with “normal layout would show side regions”

The plan says preserve side regions on “desktop/tablet.” That is slightly too mode-based for the current policy.

Current tests show that `narrow` mode can still have both sidebars usable at `900px`:

```ts
it('keeps both sidebars usable at 900px by clamping oversized preferred widths', ...)
```

So the correct rule should not be:

> preserve sidebars only in desktop/tablet

It should be:

> when overlay is active, preserve any side region that the same viewport/preferences would render in the non-overlay layout, except where short-height or existing narrow/phone constraints would normally suppress it.

That avoids forcing panels onto phone layouts, but it also avoids a weird bug where a 900px layout shows sidebars normally and then erases them only because viewer opened.

I would edit the plan’s pre-approved behavior #1 to:

> On any layout where the existing non-overlay responsive policy would render left rail/content or the right inspector, viewer/compare overlay mode should preserve those effective widths instead of suppressing them merely because overlay mode is active. Short-height suppression remains unchanged. Phone/narrow layouts that normally have zero side-region width remain zero.

### 2. Tell implementers not to blindly return the non-overlay model

A tempting implementation is:

```ts
if (overlayActive) {
  return buildResponsiveLayoutModel({ ...input, overlay: 'none' })
}
```

That would be wrong because overlay mode currently also suppresses mobile drawer reserve:

```ts
mobileDrawerHeightPx: mobileShell && !overlayActive && input.mobileDrawerOpen ? ...
```

So the plan should say:

> Use non-overlay panel geometry for side widths/insets, but keep overlay-specific shell reserves. In particular, opening viewer/compare should not re-enable the mobile drawer.

This is a small but important guardrail.

### 3. Split the policy test that currently bundles overlay and short-height

Current test:

```ts
it('suppresses sidebars during short-height and overlay states', ...)
```

This should become at least three tests:

1. **Short height still suppresses sidebars.**
2. **Overlay preserves side widths when normal layout would show them.**
3. **Overlay does not force sidebars onto layouts where normal policy suppresses them.**

Add one more test around the borderline current behavior:

```ts
overlay active at 900px preserves sidebars if the non-overlay policy would show them
```

That catches the desktop/tablet wording problem.

### 4. Add an explicit toolbar decision

This is the biggest missing detail in the plan.

Current `Toolbar` has viewer-specific controls:

* Back button
* Zoom slider
* Previous/next image buttons

And current `AppShell` only makes the toolbar inert for compare:

```ts
if (compareOpen) {
  toolbar.setAttribute('inert', '')
  toolbar.setAttribute('aria-hidden', 'true')
}
```

It does **not** inert the toolbar for viewer. That means viewer mode expects at least some toolbar controls to remain usable.

But `Viewer.tsx` now uses `useModalFocusTrap(containerRef, { onEscape: closeViewer })`, and the toolbar sits outside that dialog. If the plan says “viewer keeps modal focus ownership” without clarifying toolbar behavior, an implementer may accidentally break the viewer toolbar.

I would add this acceptance criterion:

> Viewer toolbar controls that are intentionally visible in viewer mode must remain usable unless explicitly changed: Back, zoom slider, and image nav. Side regions may remain visible but inert. Compare may continue to inert toolbar if that is current product behavior.

And add browser evidence:

* Open viewer.
* Verify side regions remain visible.
* Verify Back closes viewer.
* Verify zoom slider changes viewer zoom.
* Verify toolbar Prev/Next works, if enabled.

If strict modal semantics conflict with this, fix the interaction model narrowly. Do not silently make the viewer toolbar decorative.

### 5. Make hover preview target exact: centered old overlay or large anchored card

The plan says “old large overlay scale” and mentions old centered `80vw`/`80vh`, but RVP-5 still leaves room for keeping the new anchored popover and merely making it larger.

Given this is a corrective regression plan, I would make it explicit:

> Restore the old centered fixed hover preview presentation unless the user separately approves a redesigned anchored preview. The preview image should use original `/file` content and CSS max bounds near `80vw` / `80vh`, not a fixed small popover surface.

That means `getHoverPreviewSurfaceSize()` may need to stop being the main sizing primitive for the restored behavior. The old behavior was image-driven:

```tsx
<img className="max-w-[80vw] max-h-[80vh] object-contain" />
```

The browser check should assert the actual image rectangle, not just wrapper size.

### 6. Specify hover cache/cancel semantics more concretely

The current plan says “original-file fetch shape” and “cache participation should follow the smallest implementation,” which is slightly vague.

Current choices are:

* Old exact behavior: `api.getFile(path)`, uses `fileCache`, but not abortable.
* New safer behavior: direct abortable `/file` fetch through `runWithRequestBudget('file', ...)`, but may not use `fileCache`.
* Hybrid: return cached full file if already in `fileCache`; otherwise direct abortable `/file`.

I recommend the hybrid because it preserves snappiness without adding a new backend/API:

```ts
getHoverPreview(path) {
  const cached = fileCache.get(path)
  if (cached) return { promise: Promise.resolve(cached) }

  return runWithRequestBudget('file', () =>
    fetchBlob(fileUrl(path))
  )
}
```

Whether to write successful hover blobs into `fileCache` should be stated explicitly. Since the old `api.getFile(path)` path did cache, caching would be closer to original behavior. Since the plan worries about lifecycle/cancellation, not writing is simpler. I would add a plan sentence like:

> Prefer reading from `fileCache` for already-loaded files. For uncached hover fetches, use an abortable direct `/file` request. Caching the result is optional only if it preserves the old `api.getFile` behavior without broadening this task.

Also update the client test from:

```ts
fetches hover previews directly from thumb route without full-file cache use
```

to something like:

```ts
fetches hover previews from file route and does not use thumb route
```

and add:

* uses `runWithRequestBudget('file')`, not `thumb`;
* abort cancels an uncached hover request;
* cached file hit does not issue network request, if you choose the hybrid.

### 7. Make network evidence robust against cache hits

The plan says browser evidence should prove `/file`, not `/thumb`. Good, but the script can accidentally use an image already loaded by the viewer/compare sprint, in which case `fileCache` may satisfy the hover and no `/file` request appears.

Add this to RVP-4/RVP-5:

> Use a fresh fixture image path for hover preview evidence that was not opened in viewer/compare earlier in the script, or reload/clear frontend caches before the hover scenario. Filter network assertions by that exact path and by requests that happen after hover begins, because normal grid thumbnails will legitimately request `/thumb`.

Without that, the test may be flaky or falsely fail.

### 8. Define “no flash/disappear” as a visual predicate, not just full-image opacity

Current viewer/compare use thumbnail placeholders plus full images with `ready` opacity. A test that only checks the full-res image opacity can incorrectly fail during the intentional loading phase.

Better acceptance language:

> After the first viewer/compare image surface becomes visible, there must not be a later frame where the overlay is open but no loaded image/thumbnail for the active path has a nonzero rectangle and visible opacity. For full-res image checks, require `naturalWidth > 0`, nonzero rect, and effective opacity above zero.

That prevents an implementation agent from deleting useful loading continuity just to satisfy a brittle opacity assertion.

### 9. Add a compare-specific stability check

Compare has two images, two ready flags, and each image load calls `fitAndCenter()`. A common failure mode is:

1. A loads and becomes visible.
2. B loads.
3. `fitAndCenter()` changes A’s transform or visibility.
4. The compare surface jumps or briefly blanks.

The plan mentions compare generally, but I would add:

> Compare evidence should sample both `compare A` and `compare B` image rects/opacities before and after each load settles, and should fail if either loaded side becomes invisible while compare remains open.

### 10. Make process-only skill requirements optional

The uploaded repo only contains `.agents/skills/desloppify/SKILL.md`. I did not see `better-code`, `code-simplifier`, or `code-review` in the zip. Those may exist in the runner environment, but they are not in this repository.

I would change wording from:

> must use the `better-code` skill

to:

> use the `better-code` / cleanup / review routines when available in the implementation environment; otherwise perform the same gates manually and record the evidence.

That avoids a plan runner stalling on missing local skill files.

## Things I would keep as-is

The plan is right to keep these constraints:

* No new dependencies.
* No new backend preview endpoint.
* Do not remove modal/focus work wholesale.
* Keep side regions visible but inert unless explicitly approved.
* Do not continue thumbnail-hover assumptions.
* Sync `frontend/dist` into `src/lenslet/frontend/` after UI changes.
* Use browser evidence as the primary gate, not only unit tests.

## My revised implementation priority

I would slightly reorder the work:

1. **Policy tests first**: split short-height vs overlay behavior.
2. **Policy fix**: preserve non-overlay side widths/insets while keeping overlay shell reserves.
3. **Browser evidence for viewer/compare layout**: side rects, viewer rect, toolbar controls, image visibility.
4. **Only then touch viewer/compare flashing** if the browser evidence still shows a real flash/disappear.
5. **Hover API tests**: `/file`, not `/thumb`, abort/cache behavior defined.
6. **Hover UI restore**: centered large original preview, actual image rect assertions.
7. **Final browser script + asset sync.**

Overall: the plan is good, but I would tighten it around **normal-layout-derived side widths**, **viewer toolbar behavior**, and **exact hover preview presentation/cache semantics** before implementation. Those are the main places an agent could technically satisfy the written plan while still producing a product behavior you probably would not like.
