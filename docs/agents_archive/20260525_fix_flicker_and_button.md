I inspected the current codebase zip and the extracted image sequences. The flicker is real, and the clips give enough evidence to identify the main source.

The main culprit is **the viewer’s thumbnail placeholder/crossfade path**, not hover preview. There are also two secondary flicker contributors in the current code that can produce very fast flashes even when the thumbnail flicker is too quick to record.

## What the sequences show

The clearest clip is `seq_09`.

At `000513-00m17.067s` and `000514-00m17.100s`, the selected lion image is shown as a semi-transparent, low-resolution/thumbnail-looking image over the still-visible gallery. It is positioned at the viewer content’s top-left, not centered like the final image.

At `000515-00m17.133s`, the same ghost image is still visible at the top-left of the viewer surface while the gallery underneath is dimmed.

At `000519-00m17.267s`, the full image is visible and centered, but a smaller ghost copy is still visible over the top-left of the full image. That is the smoking gun: the thumbnail placeholder did not disappear before the full image became visible; it is fading out on top of the full image.

This exactly matches the current `Viewer.tsx` behavior:

```tsx
const thumbUrl = useBlobUrl(() => api.getThumb(path), [path])
```

and:

```tsx
{thumbUrl && (
  <img
    src={thumbUrl}
    alt="thumb"
    className="absolute top-0 left-0 ... transition-opacity duration-[110ms] ..."
    style={{
      transform: `translate(${tx}px, ${ty}px) scale(${base})`,
      opacity: ready ? 0 : 0.5,
      filter: 'blur(0.25px)',
    }}
  />
)}
```

Then the full image does this:

```tsx
style={{
  transform: `translate(${tx}px, ${ty}px) scale(${base * scale})`,
  opacity: ready ? 0.99 : 0,
}}
```

So the current viewer intentionally creates a crossfade:

1. render thumbnail at `opacity: 0.5`;
2. keep full image at `opacity: 0`;
3. when full image loads, set `ready`;
4. thumbnail fades from `0.5` to `0` over `110ms`;
5. full image fades from `0` to `0.99` over `110ms`.

That is exactly the ghost/eye-strain flicker in the recordings.

## Why the ghost jumps around

There is a second issue inside the same path.

Before the full image loads, `base`, `tx`, and `ty` are still the default values from `useZoomPan()`:

```ts
base = 1
tx = 0
ty = 0
```

So the thumbnail is drawn at the viewer surface’s top-left.

When the full image loads, `markImageReady()` calls:

```ts
resetView()
```

That computes the fitted transform for the full-size image. Now the thumbnail is also using the newly fitted `base`, `tx`, and `ty`, even though its natural dimensions are smaller than the full image’s natural dimensions. That is why, after the full image appears, the ghost becomes a smaller copy sitting over the top-left of the full image.

So the sequence is not just “thumbnail shown briefly.” It is:

1. thumbnail appears at default top-left geometry;
2. full image loads;
3. transform changes;
4. thumbnail jumps into the full-image coordinate system;
5. thumbnail fades out while full image fades in.

That produces exactly the unpleasant flicker.

## Other flicker sources in the current code

Even if the thumbnail were removed, there are three more places that can produce quick flashes.

### 1. Viewer open fade

The viewer starts with:

```ts
const [visible, setVisible] = useState<boolean>(false)
```

Then `Viewer.tsx` does:

```ts
requestAnimationFrame(() => {
  setVisible(true)
})
```

The dialog has:

```tsx
transition-opacity duration-[110ms] ... ${visible ? 'opacity-100' : 'opacity-0'}
```

So every open guarantees at least one frame where the viewer exists but is transparent, followed by a 110ms fade. If the image loads very quickly, this can become “gallery → transparent/fading overlay → image,” which can feel like a flicker even if a screen recording misses it.

### 2. `requestAnimationFrame` delay before full image readiness

`markImageReady()` currently does:

```ts
requestAnimationFrame(() => setReady(true))
```

That guarantees at least one extra frame after image load where the full image is still `opacity: 0`, while the thumbnail can still be visible.

For slow loads this is not noticeable. For fast loads it creates a very short but irritating blank/ghost frame.

### 3. Lazy viewer chunk fallback

`AppShell.tsx` currently has:

```ts
const Viewer = lazy(() => import('../features/viewer/Viewer'))
```

and wraps it in:

```tsx
<Suspense fallback={<OverlayFallback label="Image viewer" message="Loading viewer..." ... />}>
```

If the viewer chunk is not already loaded, a fallback overlay can briefly render. On fast machines or recordings this may be sub-frame or one-frame, but it can still be perceived. Since image viewing is the hot path of this app, I would not keep the primary viewer lazy unless bundle measurements strongly justify it.

## What is probably *not* causing this flicker

I do not think this is the restored hover preview.

The restored hover preview path renders `.grid-hover-preview` through a portal with `position: fixed` and `z-[999]`. The recorded ghost is not centered like the hover preview. It appears inside the viewer surface at the viewer image origin, and then over the full image’s top-left after the transform changes. That matches `Viewer.tsx`’s `img alt="thumb"` exactly.

## Back button issue

The frame you called out, `000396-00m13.167s-ba5000ee65`, shows the cursor visually over the Back button, but the button does not appear to be in its hover state.

The current code makes this plausible. In viewer mode, the toolbar still renders a lot of browse-toolbar content into the same grid/flex layout:

* scope text,
* sort dropdown,
* filters,
* hidden refresh slot,
* Back slot,
* zoom slider,
* nav buttons,
* panel buttons,
* sync indicator.

The Back button is inside the left flex section:

```tsx
<div className="toolbar-left flex items-center gap-4 min-w-0">
  ...
  <div className="toolbar-slot toolbar-slot-back" data-toolbar-slot="back">
    <button data-toolbar-control="back" ...>
```

The toolbar layout uses fixed slot widths:

```css
.toolbar-slot-back {
  width: 84px;
}

.toolbar-back-btn {
  width: 84px;
}
```

and then compact mode abruptly changes it:

```css
.toolbar-shell-compact .toolbar-slot-back {
  width: 40px;
}

.toolbar-shell-compact .toolbar-back-btn {
  width: 32px;
}

.toolbar-shell-compact .toolbar-back-label {
  display: none;
}
```

The symptom you described — “specific width that still shows Back in full text but not full width” — points to a **toolbar collision/hit-test overlap near the compact breakpoint**, not a missing `onClick`.

The existing browser harness only checks the center of each toolbar control with `elementFromPoint`. That can pass even if the upper half, edge, or text area is covered by another transparent control. So this bug can slip through current tests.

Most likely overlapping candidates:

* `.toolbar-center` / `.zoom-slider`;
* a neighboring toolbar grid column;
* disabled/hidden browse controls still occupying space in viewer mode;
* less likely: the viewer dialog if `toolbar-offset` or z-index is wrong.

I would not “fix” this by only raising z-index. First prove which element is hit at the failed points.

---

# Concrete fix plan

## Sprint 1: eliminate viewer-open flicker

### 1. Add browser evidence that can actually catch the flicker

Add a focused viewer-open flicker scenario to `scripts/responsive_geometry_harness.py` or a small new script.

The existing harness samples the full image, but it does **not** fail if the thumbnail placeholder is visible. Add per-frame sampling immediately after double-click, before waiting for the image to settle.

For each animation frame, record:

```js
{
  frame,
  elapsedMs,
  overlayOpacity,
  viewerThumb: {
    exists,
    opacity,
    rect,
    transform,
    src,
  },
  viewerFull: {
    exists,
    opacity,
    complete,
    naturalWidth,
    naturalHeight,
    rect,
    transform,
    currentPath,
  },
  visibleImagesInViewerCount
}
```

Add two cases:

1. **Fast file path**: normal load, no artificial delay.
2. **Slow file path**: delay `/file` by around 250–400ms so the loading path is visible.

Current code should show `viewerThumb.opacity > 0` during open and often after the full image becomes visible. After the fix, that should not happen.

Acceptance predicate:

```text
During viewer open, no thumbnail/ghost image may be visible inside the viewer surface.

Once the full image for the active path is visible, there must not be any other visible image for that path in the viewer surface.

The full image should first become visible at its final fitted transform, not top-left default geometry.
```

### 2. Remove the viewer thumbnail placeholder

In `frontend/src/features/viewer/Viewer.tsx`, remove:

```tsx
const thumbUrl = useBlobUrl(() => api.getThumb(path), [path])
```

and remove the entire:

```tsx
{thumbUrl && <img alt="thumb" ... />}
```

This is the smallest direct fix for the recorded ghost.

Do **not** replace it with another image-based placeholder. Use a neutral loader only if needed.

### 3. Stop crossfading full image opacity

The full image should appear when it is ready, without a 110ms crossfade against a thumbnail.

Change the full image class from:

```tsx
transition-opacity duration-[110ms] ease-out
```

to no opacity transition, or to a class that only transitions on deliberate navigation if you later decide that is safe.

Change:

```tsx
opacity: ready ? 0.99 : 0
```

to:

```tsx
opacity: ready ? 1 : 0
```

The important part is not the `0.99`; it is avoiding the fade/crossfade path.

### 4. Remove the RAF delay in `markImageReady`

Change this:

```ts
try {
  requestAnimationFrame(() => setReady(true))
} catch {
  setReady(true)
}
```

to:

```ts
setReady(true)
```

The transform reset and readiness state should happen as one React update. The image should not spend an extra frame loaded-but-hidden.

### 5. Remove the open fade, keep close fade only if wanted

Current viewer open is:

```ts
visible = false
requestAnimationFrame(() => setVisible(true))
```

and the dialog fades in. That can still feel like flicker.

Recommended fix:

* initialize viewer as visible on mount;
* keep fade-out on close only if you like that close animation.

Implementation shape:

```ts
const [closing, setClosing] = useState(false)

const closeViewer = useCallback(() => {
  setClosing(true)
  window.setTimeout(onClose, 110)
}, [onClose])
```

Then:

```tsx
className={`... ${closing ? 'opacity-0 transition-opacity duration-[110ms]' : 'opacity-100'}`}
```

No opening opacity transition.

### 6. Use a neutral delayed loader for slow images

For slow loads, show nothing image-like for the first short delay. If load takes longer than, say, 150ms, show a neutral spinner or “Loading image…” text.

Example behavior:

```text
0–150ms: stable viewer background, no thumbnail.
>150ms: neutral loader.
full image ready: loader disappears, full image appears at final fit.
```

That prevents fast-path flicker while still giving feedback for slow files.

### 7. Key blob URLs by path, or clear them at request start

`useBlobUrl()` currently keeps the previous URL until the new fetch resolves. The viewer hides the previous full image with `ready=false`, but this is still fragile, especially for navigation.

The robust path is a keyed resource hook for viewer/compare:

```ts
type BlobResource = {
  path: string
  url: string
}

const resource = useBlobUrlResource(path, api.getFile)
```

Render only when:

```ts
resource?.path === path
```

At minimum, make the viewer path clear old URL state immediately on path change. Do not let a previous path’s thumb/full URL remain renderable during a new path transition.

---

## Sprint 2: remove related compare flicker

`CompareViewer.tsx` has the same pattern:

```tsx
const aThumb = useBlobUrl(...)
const bThumb = useBlobUrl(...)
...
opacity: readyA ? 0 : 0.5
opacity: readyB ? 0 : 0.5
...
opacity: readyA ? 0.99 : 0
opacity: readyB ? 0.99 : 0
```

Even if the current complaint is gallery → fullscreen, compare will have the same ghost behavior.

Apply the same policy there:

* remove `aThumb` / `bThumb`;
* remove thumbnail images;
* no crossfade between thumb/full;
* no RAF readiness delay;
* keyed full-image resources;
* neutral loader if either side is slow.

If you want to keep compare out of scope, leave it for a follow-up, but the cause is identical.

---

## Sprint 3: remove the lazy-viewer fallback flash

Viewer is a primary interaction, not a rarely used secondary surface. I would make this change:

```ts
import Viewer from '../features/viewer/Viewer'
```

instead of:

```ts
const Viewer = lazy(() => import('../features/viewer/Viewer'))
```

Keep `Inspector` lazy if you want. Maybe keep `CompareViewer` lazy if bundle pressure matters, but the main viewer should not show a Suspense fallback during a double-click open.

Alternative if you want to preserve code-splitting:

```ts
const viewerModulePromise = import('../features/viewer/Viewer')
const Viewer = lazy(() => viewerModulePromise)

useEffect(() => {
  void viewerModulePromise
}, [])
```

But direct import is simpler and less fragile.

Acceptance:

```text
Opening viewer must not render OverlayFallback("Loading viewer...") in normal browse use.
```

---

# Back button fix plan

## 1. Add a hit-target probe that samples the whole Back button

Update the browser harness. The current center-point test is too weak.

For `[data-toolbar-control="back"]`, collect a 3×3 or 5×3 grid of sample points inside the button rect:

```js
const rect = back.getBoundingClientRect()
const points = [
  { x: rect.left + rect.width * 0.25, y: rect.top + rect.height * 0.20 },
  { x: rect.left + rect.width * 0.50, y: rect.top + rect.height * 0.20 },
  { x: rect.left + rect.width * 0.75, y: rect.top + rect.height * 0.20 },
  { x: rect.left + rect.width * 0.25, y: rect.top + rect.height * 0.50 },
  ...
]
```

For each point:

```js
const hit = document.elementFromPoint(x, y)
```

Record:

```js
{
  point,
  hitTag: hit?.tagName,
  hitClass: hit?.className,
  hitDataToolbarControl: hit?.closest('[data-toolbar-control]')?.getAttribute('data-toolbar-control'),
  hitAriaLabel: hit?.getAttribute('aria-label'),
}
```

Fail unless every interior point resolves to the Back button or one of its descendants.

Also add actual click tests:

```text
Open viewer.
Click Back at top-center of its rect.
Expected: viewer closes.

Reopen viewer.
Click Back at bottom-center of its rect.
Expected: viewer closes.
```

Run this across widths around the likely threshold:

```text
900, 960, 1024, 1100, 1180, 1190, 1240, 1280, 1360, 1440
```

The frame suggests this is a breakpoint/collision bug, so a width sweep is important.

## 2. Refactor viewer toolbar layout so Back cannot be covered

Do not rely only on z-index. The safer product fix is:

```text
Viewer mode toolbar should prioritize Back, zoom, previous/next, close/navigation controls.
Disabled browse controls should not occupy hit-test space in viewer mode.
```

Concretely, in `Toolbar.tsx`, when `viewerActive` is true, render a dedicated viewer-toolbar shape instead of the normal browse toolbar with disabled browse controls mixed in.

Something like:

```tsx
{viewerActive ? (
  <>
    <div className="toolbar-left toolbar-left-viewer">
      <div className="toolbar-slot toolbar-slot-back" data-toolbar-slot="back">
        <button data-toolbar-control="back" ...>Back</button>
      </div>
    </div>

    <div className="toolbar-center toolbar-center-viewer">
      <input className="zoom-slider" ... />
      <span>{zoomPercent}%</span>
    </div>

    <div className="toolbar-right toolbar-right-viewer">
      {/* prev/next, panel toggles, sync */}
    </div>
  </>
) : (
  // existing browse toolbar
)}
```

Then CSS:

```css
.toolbar-shell-viewer {
  grid-template-columns: max-content minmax(140px, 1fr) max-content;
}

.toolbar-shell-viewer .toolbar-left {
  min-width: max-content;
  overflow: visible;
}

.toolbar-shell-viewer .toolbar-slot-back,
.toolbar-shell-viewer .toolbar-back-btn {
  width: auto;
  min-width: 84px;
}

.toolbar-shell-viewer .toolbar-slot-back {
  position: relative;
  z-index: 2;
}

.toolbar-shell-viewer .toolbar-center {
  min-width: 0;
  overflow: hidden;
}

.toolbar-shell-viewer .zoom-slider {
  max-width: min(180px, 100%);
}
```

The z-index on Back is only hardening. The real fix is removing overlap pressure from disabled browse controls and giving viewer mode its own layout.

## 3. If the probe shows the viewer dialog is the hit target

If `elementFromPoint` says the hit is the viewer dialog instead of toolbar controls, then the fix is different:

* verify `.toolbar-offset` is winning over `inset-0`;
* verify viewer top starts at `var(--toolbar-h)`;
* verify toolbar z-index is above viewer;
* assert viewer rect top equals toolbar bottom.

But based on the code and the width-specific “Back label still shown but not full width” symptom, I think toolbar collision is more likely than overlay top/z-index.

---

# Validation checklist

I would not call this done without these checks.

## Flicker checks

Browser evidence should prove:

```text
Fast viewer open:
- no img[alt="thumb"] is visible;
- no thumbnail-sized image appears inside the viewer;
- full image first visible frame uses final fit transform;
- no OverlayFallback is rendered;
- overlay does not fade in from opacity 0.

Slow viewer open:
- no thumbnail/ghost image appears;
- neutral loader may appear only after a delay;
- full image appears once, at final transform.

Viewer next/prev:
- previous image does not flash while next image loads;
- no previous-path thumbnail remains visible;
- full image does not become invisible after becoming visible.
```

## Back-button checks

Browser evidence should prove:

```text
At each tested width:
- every sampled point inside Back resolves to Back or a child;
- top-half click closes viewer;
- bottom-half click closes viewer;
- Back hover state appears when pointer is over the button;
- zoom slider and toolbar center do not cover Back.
```

## Source-level acceptance

After the fix, `Viewer.tsx` should no longer contain a rendered `img alt="thumb"` placeholder. Ideally `CompareViewer.tsx` should not either.

The important behavioral change is:

```text
Do not crossfade from thumbnail to full image in viewer.
```

That crossfade is the recorded flicker.
