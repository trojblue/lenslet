I’d treat this repo as **not pure vibe-code**, but as a codebase with a real cleanup pass layered on top of older brittle interaction code. The recent responsive work improved obvious collisions, yet the deeper problems are still in custom geometry, duplicated gesture engines, fixed-size layout assumptions, and a few hand-rolled UI primitives.

I audited the repo at `/mnt/data/lenslet/lenslet-main`, read the responsive-review docs, inspected the layout/viewer/grid/menu code, ran lint/type/build checks, and cross-checked against primary developer docs and serious reference implementations.

## What I ran locally

These passed:

```bash
uv pip install -c constraints/runtime-py313.txt -e '.[dev]'
python scripts/lint_repo.py
cd frontend && npm ci
cd frontend && npx tsc --noEmit
cd frontend && npm run build
```

Important local results:

* `scripts/lint_repo.py` passes, but warns that several files are still too large:

  * `frontend/src/app/AppShell.tsx`: 1,637 lines
  * `frontend/src/features/ranking/RankingApp.tsx`: 1,329 lines
  * `frontend/src/styles.css`: 1,919 lines
  * `src/lenslet/cli.py`: 1,387 lines
  * responsive test scripts are also large.
* Frontend type-check and build pass.
* The main Vite chunk is **541.65 kB minified**, triggering Vite’s chunk-size warning. Vite’s own docs say the default warning threshold is 500 kB uncompressed because JS size also affects execution time, not only transfer size. ([vitejs][1])
* `npm audit --omit=dev` reports **0 production vulnerabilities**. Full audit reports **10 dev-tooling vulnerabilities**, mostly Vite/Vitest/esbuild/Rollup-related. That argues for a deliberate tooling update branch, not panic.
* Python test execution hit a real dependency/test-contract problem: comparison export tests expect success, but the endpoint returns `unibox_missing` because `unibox` is imported in `src/lenslet/web/comparison_export.py` and is not declared in `pyproject.toml`.

The repo docs show that a responsive harness recently passed 18 scenarios and zoom/page-scale smoke cases. I did **not** rerun that browser harness end-to-end in this container; I treated the progress log as evidence of previous work and focused on whether the current architecture is robust enough.

---

# Highest-priority product issues

## 1. The “masonry/adaptive” grid is the biggest source of weird-proportion ugliness

The current adaptive layout is not really masonry. The UI labels one mode as “Masonry,” but the code maps that to `adaptive`. The adaptive algorithm in `frontend/src/features/browse/model/adaptive.ts` is a greedy justified-row algorithm:

* It uses a default aspect ratio of `1.333`.
* It adds images to a row until estimated width reaches the container.
* It computes one row height from the sum of aspect ratios.
* The comment says the greedy approach works for “typical aspect ratios.”

That last phrase is the problem. Galleries fail exactly when inputs are not typical: panoramas, tall screenshots, missing metadata, short rows, half-screen layouts, and browser zoom. A single very wide item can create a very short row; a single tall item can become a tiny vertical strip. There does not appear to be direct focused test coverage for `computeAdaptiveRows`.

Better reference points exist. Flickr’s `justified-layout` takes aspect ratios or width/height objects and returns full geometry for a justified gallery layout. ([Flickr][2]) React Photo Album’s rows layout uses a Knuth-Plass-inspired dynamic programming approach to keep row heights balanced and specifically avoid problems with panoramas, stragglers, and stretched last rows. ([GitHub][3])

**Fix direction:** replace or harden `computeAdaptiveRows`.

Concrete changes:

* Rename the current mode from **Masonry** to **Justified rows**, unless you implement true column masonry.
* Add row-height constraints: target, min, max.
* Add outlier handling:

  * panoramas can be capped or rendered as single hero-ish rows;
  * very tall images can use contain-mode cards instead of being squeezed;
  * unknown dimensions should be measured or given safer fallbacks.
* Add a non-greedy row breaker, either by:

  * adopting `justified-layout`;
  * porting a small DP row-layout algorithm;
  * or using React Photo Album as algorithm inspiration rather than taking the whole component.
* Add fuzz tests for aspect ratios:

  * `10:1`, `6:1`, `1:8`, `0:0`, missing width/height, mixed screenshots, one-image rows, last-row leftovers.
* Add screenshot tests at:

  * 320 px, 360 px, 390 px;
  * half-screen desktop widths;
  * high browser zoom / large font;
  * short viewport height.

This is probably the single most important fix for the “only works at one aspect ratio/browser level” feeling.

---

## 2. Layout policy improved, but still relies too much on fixed global viewport math

The repo has a good recent structural idea in `frontend/src/app/layout/responsiveLayoutPolicy.ts`: one policy computes sidebar visibility, drawer reserve, toolbar reserve, and center width. That is much better than random CSS patches.

But the implementation is still brittle because it is driven primarily by `window.innerWidth` / `window.innerHeight` in `AppShell.tsx`. The code uses `visualViewport` only for browser zoom warning heuristics, not as the core layout input.

That matters because the visual viewport can shrink independently of the layout viewport during pinch zoom, browser UI changes, or on-screen keyboard display. MDN explicitly distinguishes the layout viewport from the visual viewport and notes that fixed-position UI can end up outside what the user actually sees when the visual viewport changes. ([MDN Web Docs][4])

There are also duplicate breakpoint systems:

* `frontend/src/app/layout/responsiveLayoutPolicy.ts`
* `frontend/src/lib/breakpoints.ts`

The policy also hard-suppresses sidebars when height is under `560px`. That avoids overlap, but it is blunt. A wide desktop window with short height, or a zoomed browser, can suddenly lose structure rather than degrade gracefully.

**Fix direction:** make the layout engine visual-viewport-aware and component-container-aware.

Concrete changes:

* Replace `viewportWidth` / `viewportHeight` state with a single `ViewportModel`:

  * layout viewport width/height;
  * visual viewport width/height;
  * visual viewport offset;
  * device pixel ratio;
  * coarse/fine pointer;
  * reduced motion;
  * safe-area insets where relevant.
* Use `visualViewport` for fixed overlays, mobile drawer, hover preview, menus, and dialog sizing.
* Keep global breakpoints only for broad shell decisions.
* Use container queries for internal component layout. Container queries let components adapt based on their own container size rather than the whole viewport, which is exactly what toolbar, inspector, drawer, and compare labels need. ([MDN Web Docs][5])
* Collapse duplicate breakpoint constants into one module.

The inspector already uses container-query-like CSS in places. That is the right direction; extend that pattern to toolbar, mobile drawer rows, compare header, compare labels, and metadata panels.

---

## 3. Toolbar and mobile drawer are overfit to specific widths

`frontend/src/styles.css` has many fixed toolbar widths:

* refresh button `40px`
* back section `84px`
* nav cluster `72px`
* upload section `104px`
* desktop search `240px`
* compact variants with separate numbers

The mobile drawer has a fixed reserve of roughly `217px`, defined in CSS and also set from TypeScript policy through `--mobile-drawer-h`. This is an improvement over total chaos, but it still means content lengths, translated labels, browser zoom, large font settings, or half-screen windows can create cramped UI.

**Fix direction:** toolbar/drawer should be content-adaptive, not slot-adaptive.

Concrete changes:

* Convert the toolbar into priority groups:

  1. always visible: back, current selection/location, primary action;
  2. collapsible: search, filters, sort;
  3. overflow menu: lower-priority actions.
* Use measured container width, not only viewport width.
* Move from fixed pixel slots to `minmax()`, flex wrapping, or container-query states.
* Make mobile drawer height content-driven with max-height constraints, not a fixed magic reserve.
* Add tests using long folder names, long smart-folder names, and high text zoom.

This is the kind of polish that removes the “works, but not good” feeling.

---

## 4. Viewer and compare zoom/pan are custom, duplicated, and reset too aggressively

There are two separate zoom/pan engines:

* `frontend/src/features/viewer/hooks/useZoomPan.ts`
* `frontend/src/features/compare/hooks/useCompareZoomPan.ts`

They share concepts: min/max zoom, wheel zoom, pointer drag, fit-and-center, ResizeObserver, click suppression. But they are implemented separately.

The bigger UX issue: both engines reset fit/center on container resize. That means resizing the browser, using half-screen, opening/closing sidebars, or changing layout can destroy the user’s zoom context. For a gallery, that feels bad. Once I am inspecting an image, resizing the window should preserve the viewed region as much as possible.

There are also interaction inconsistencies:

* Browse grid intercepts `Ctrl+wheel` to resize thumbnails.
* Viewer uses wheel for image zoom.
* Compare uses its own wheel/pointer behavior.
* Grid pinch resizes thumbnails.
* Viewer/compare pointer logic is separate.

PhotoSwipe is a useful reference here, not necessarily a dependency recommendation. Its behavior makes image zoom a viewer concern, and even its `wheelToZoom` option is explicit/configurable rather than an accidental global behavior. ([PhotoSwipe][6])

**Fix direction:** one shared transform/gesture model.

Concrete changes:

* Extract a reusable `useImageTransform` or non-React `TransformController`.
* Preserve visual center on resize:

  * store normalized image-space center;
  * recompute transform after container changes;
  * avoid unconditional reset unless the image changes or user explicitly clicks reset.
* Do not hijack browser `Ctrl+wheel` in the browse grid. Use:

  * explicit thumbnail-size slider;
  * keyboard shortcuts;
  * or normal wheel/pinch only inside a dedicated resize affordance.
* Make panning work on the stage/backdrop when zoomed, not only when the pointer starts on the image.
* Define a single gesture policy:

  * grid: scroll/select/drag/reorder;
  * viewer: pan/zoom;
  * compare: pan/zoom/split;
  * browser zoom remains browser zoom.

This should be high priority because it directly affects zoomed-in and half-screen behavior.

---

## 5. Dialog behavior is not good enough yet

Viewer and compare overlays use `role="dialog"` / `aria-modal`, but they block `Tab` rather than implementing a real focus trap. That can make keyboard behavior feel broken and can be an accessibility problem.

The WAI-ARIA Authoring Practices for modal dialogs say that content outside the dialog should be inert, `Tab` and `Shift+Tab` should cycle inside the dialog, `Escape` should close it, and focus should return to the invoking element when the dialog closes. ([W3C][7]) React Aria’s dialog implementation follows this model by moving focus into the dialog, containing focus while open, and restoring focus afterward. ([React Aria][8])

**Fix direction:** replace “prevent Tab” with a real dialog primitive.

Concrete changes:

* Either implement a small `useModalDialog` hook or use a focused library primitive.
* Required behavior:

  * focus enters dialog on open;
  * focus cycles inside;
  * `Escape` closes;
  * outside content is inert;
  * focus returns to the triggering thumbnail/button;
  * viewer and compare use the same primitive.
* Do not make toolbar inert rules differ between compare and viewer unless there is a clear documented interaction reason.

This will make the app feel less hacky even for mouse users, because modal/focus behavior affects keyboard shortcuts, accidental focus loss, and screen-reader state.

---

## 6. Hover preview is risky: full-file downloads, no abort, stale race potential

`VirtualGrid.tsx` schedules a hover preview after a delay, then calls `api.getFile(path)`, creates an object URL, and shows a fixed preview. Problems:

* It fetches the full file, not a bounded preview derivative.
* It has no AbortController path from the component.
* If the pointer leaves after the fetch begins, the request can continue.
* There is no obvious sequence guard preventing late responses from old hover targets.
* The blob cache is capped, but full-image hover can still waste bandwidth and memory.

For image galleries, full-resolution loading should be intentional. PhotoSwipe’s docs explicitly recommend serving responsive images and say it is not designed for very large images unless you use an appropriate strategy. ([PhotoSwipe][9]) OpenSeadragon’s model for large zoomable images is tiled loading: only needed tiles are fetched as the user zooms/pans. ([OpenSeadragon][10])

**Fix direction:** preview should be cancellable and bounded.

Concrete changes:

* Add `api.getFileCancelable()` or expose the existing abortable fetch path.
* Use an incrementing request token so stale hover results cannot win.
* Prefer thumbnail/preview derivatives for hover.
* Add a file-size cap for hover preview.
* For very large images, either:

  * show thumbnail until explicit open;
  * generate server-side preview sizes;
  * or consider tile support for huge images.
* Position hover preview using visual viewport bounds, not fixed `80vw` / `80vh`.

This is both a UX and performance cleanup.

---

## 7. Menus/popovers are hand-rolled and show signs of slop

The repo has custom dropdown/menu positioning in:

* `frontend/src/lib/menuPosition.ts`
* `frontend/src/shared/ui/Dropdown.tsx`

Issues I found:

* Positioning uses `window.innerWidth` / `innerHeight`, not visual viewport.
* There are two similar dropdown implementations.
* The code manually manages click, scroll, resize, and Escape listeners.
* ARIA roles are mixed: panel uses `listbox`, items use `menuitem`.
* Trigger semantics depend on the passed trigger element, which can lead to inconsistent keyboard behavior.

This is exactly the kind of thing a small specialist library handles better than a custom pile. Floating UI’s own docs describe popover needs like dynamic anchor positioning, collision avoidance, dismissal, role/ARIA behavior, and focus management. ([Floating UI][11]) That is not “slop stack”; it is a narrow primitive for a narrow problem.

**Fix direction:** centralize popover/menu behavior.

Concrete changes:

* Replace manual menu positioning with Floating UI, or at least rewrite the repo’s dropdown into one primitive with:

  * visual viewport collision handling;
  * correct roles;
  * roving focus;
  * Escape/outside-click dismissal;
  * scroll/resize auto-update;
  * consistent trigger semantics.
* Use the same primitive for toolbar menus, filter menus, sort menus, and context menus.
* Add screenshot tests for menus near all viewport edges.

---

## 8. The current structure still has “god component” debt

The code has useful modules, but too much orchestration remains in a few massive files.

Main offenders:

* `AppShell.tsx`: navigation, viewport model, sidebars, search, sort/filter, viewer state, compare state, upload actions, metadata autoload, theme, smart folders, scan status, layout CSS variables.
* `VirtualGrid.tsx`: virtualization, layout rendering, keyboard navigation, drag/drop, selection, context menu, long-press, hover preview, scroll restoration, prefetch, ARIA.
* `styles.css`: almost all global styling in one 1,919-line file.
* `Toolbar.tsx`: too much behavior plus layout-specific logic.

TanStack Virtual is a good choice, but it is intentionally headless: it provides the virtualizer logic and leaves markup, styles, and layout behavior to your code. ([TanStack][12]) That means the current app owns all the polish problems; TanStack will not save bad row geometry, focus behavior, or menu layout. TanStack’s own guidance also emphasizes accurate sizing/measurement for smooth virtualized lists. ([TanStack][13])

**Fix direction:** split by responsibility, not by vague “components.”

Suggested refactor boundaries:

```text
AppShell
├─ useViewportModel
├─ useResponsiveShellPolicy
├─ useBrowseNavigation
├─ useSelectionController
├─ useViewerController
├─ useCompareController
├─ useSmartFolders
├─ useUploadActions
└─ ShellLayout component
```

```text
VirtualGrid
├─ useGridLayout
├─ useGridKeyboardNavigation
├─ useGridSelection
├─ useGridDragDrop
├─ useGridContextMenu
├─ useGridHoverPreview
├─ VirtualGridRows
└─ ThumbCard
```

CSS split:

```text
styles/
├─ tokens.css
├─ shell.css
├─ toolbar.css
├─ grid.css
├─ viewer.css
├─ compare.css
├─ inspector.css
└─ menus.css
```

Keep global tokens global. Move behavior-specific CSS closer to the feature.

---

# Tech debt and stack cleanup

## 9. Do not chase a shiny stack rewrite

The current stack is basically fine:

* Python package with FastAPI/Pydantic/Uvicorn.
* React + TypeScript + Vite.
* npm with `package-lock.json`.
* uv is already a good direction for Python dependency management.

I would **not** move this to Bun/Vercel/Supabase or any “modern because modern” stack. The biggest problems are not stack choice; they are layout algorithms, interaction primitives, and test coverage.

For Python, uv is a strong fit because it supports project/dependency management, locking, and modern dependency workflows. ([Astral Docs][14]) uv also supports standardized dependency groups from `pyproject.toml`, which would be cleaner than treating dev dependencies as install extras. ([Astral Docs][15])

For frontend, npm is also fine. `npm ci` is designed for clean, frozen installs: it requires a lockfile, removes existing `node_modules`, and does not write package files during install. ([npm文档][16]) `package-lock.json` is meant to describe the exact dependency tree and should be committed for repeatable installs. ([npm文档][17])

**Fix direction:**

* Add and commit `uv.lock` if not already intentionally excluded.
* Move dev dependencies to `[dependency-groups]` once project policy allows.
* Keep `npm ci` for frontend CI.
* Update Vite/Vitest/esbuild/Rollup in a dedicated tooling branch.
* Do not mix in Bun unless there is a measurable reason.

---

## 10. Fix the `unibox` comparison export contract

The comparison export endpoint imports `unibox`, but `unibox` is not declared in `pyproject.toml`. The tests are split between “export success” and “unibox unavailable” behavior, but in the local environment the success test hits the unavailable path.

This is a concrete maintainability bug.

**Fix options:**

Option A, make `unibox` a real dependency:

```toml
dependencies = [
  ...
  "unibox>=..."
]
```

Option B, make it an optional extra:

```toml
[project.optional-dependencies]
export = ["unibox>=..."]
```

Then mark export tests that require it accordingly.

Option C, remove the dependency:

* Use Pillow directly for comparison export composition.
* The repo already has simple canvas/label code in the export path, so this may be feasible.

My bias: **Option C or B**. If `unibox` is only used for a narrow export feature, it should not silently break core tests.

---

## 11. Build output should be split more deliberately

The Vite build succeeds, but the main chunk exceeds the default warning threshold. Vite supports Rollup `manualChunks`, and dynamic imports are the normal way to split code. ([Vite][18])

The app already appears to lazy-load some ranking code, but the browse shell still carries a lot.

**Fix direction:**

* Run bundle analysis.
* Lazy-load:

  * compare viewer;
  * inspector-heavy metadata panels;
  * similarity/embedding panels;
  * ranking UI;
  * metrics/debug views;
  * export flows.
* Keep the initial browse grid path lean.

The goal is not only network size. Large JS chunks cost parse/compile/execute time, especially on lower-power machines.

---

# Specific interaction fixes I would make first

## First pass: visible polish

1. Replace the adaptive grid algorithm or add robust row constraints.
2. Stop intercepting browser `Ctrl+wheel` in the grid.
3. Preserve viewer/compare zoom center across resize.
4. Make toolbar and drawer container-query-based.
5. Fix hover preview to use cancellable preview-sized assets.
6. Replace fake dialog Tab blocking with a real focus trap.
7. Replace or centralize dropdown/popover behavior.

## Second pass: structural cleanup

1. Split `AppShell.tsx`.
2. Split `VirtualGrid.tsx`.
3. Split `styles.css`.
4. Merge duplicated breakpoint constants.
5. Extract shared image transform/gesture code.
6. Add a single `ViewportModel`.
7. Move Python dev deps toward uv dependency groups.
8. Resolve the `unibox` dependency/test mismatch.

## Third pass: hardening tests

Add tests for the actual complaints:

* Weird aspect ratios:

  * panoramas;
  * tall screenshots;
  * one-item rows;
  * missing dimensions.
* Viewport shapes:

  * 320×700;
  * 390×700;
  * 700×390;
  * 1024×480;
  * half-screen desktop;
  * short-height desktop.
* Browser/user settings:

  * 125%, 150%, 200% browser zoom;
  * large text;
  * coarse pointer;
  * reduced motion.
* Interactions:

  * `Ctrl+wheel` does not hijack browser zoom in browse grid;
  * viewer keeps center on resize;
  * compare keeps center/split on resize;
  * menus stay inside visual viewport;
  * dialogs trap and restore focus;
  * hover preview aborts on leave.

---

# My overall judgment

The recent responsive sprint was pointed in the right direction. The repo now has a central layout policy and a responsive harness, so it is not hopelessly random. But the gallery still feels sloppy because the most user-visible parts are still custom, brittle, and under-tested:

* greedy aspect-ratio layout;
* fixed toolbar/mobile geometry;
* layout based on layout viewport instead of visual viewport;
* duplicated zoom/pan engines;
* full-file hover preview;
* fake dialog focus handling;
* hand-rolled dropdown positioning;
* oversized coordinator files.

I would not rewrite the app or chase a fashionable stack. I would make a focused quality pass around **gallery geometry, viewport modeling, interaction primitives, and component boundaries**. That will remove far more “vibe-coded” feel than swapping infrastructure.

[1]: https://vite.dev/config/build-options?utm_source=chatgpt.com "Build Options"
[2]: https://flickr.github.io/justified-layout/ "Justified Layout by Flickr"
[3]: https://github.com/igordanchenko/react-photo-album/blob/main/README.md "react-photo-album/README.md at main · igordanchenko/react-photo-album · GitHub"
[4]: https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/CSSOM_view/Viewport_concepts "Viewport concepts - CSS | MDN"
[5]: https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Containment/Container_queries "CSS container queries - CSS | MDN"
[6]: https://photoswipe.com/options/ "Options | PhotoSwipe"
[7]: https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/ " Dialog (Modal) Pattern | APG | WAI | W3C"
[8]: https://react-aria.adobe.com/Modal/useDialog "useDialog – Modal"
[9]: https://photoswipe.com/getting-started/ "Getting Started | PhotoSwipe"
[10]: https://openseadragon.github.io/examples/creating-zooming-images/ "Creating Zooming Images | OpenSeadragon"
[11]: https://floating-ui.com/docs/popover "Popover | Floating UI"
[12]: https://tanstack.com/virtual/latest/docs/introduction "Introduction | TanStack Virtual Docs"
[13]: https://tanstack.com/virtual/latest/docs/api/virtualizer "Virtualizer | TanStack Virtual Docs"
[14]: https://docs.astral.sh/uv/?utm_source=chatgpt.com "uv"
[15]: https://docs.astral.sh/uv/concepts/projects/dependencies/?utm_source=chatgpt.com "Managing dependencies | uv"
[16]: https://docs.npmjs.com/cli/v11/commands/npm-ci?utm_source=chatgpt.com "npm-ci"
[17]: https://docs.npmjs.com/cli/v8/configuring-npm/package-lock-json/?utm_source=chatgpt.com "package-lock.json"
[18]: https://v3.vitejs.dev/guide/build?utm_source=chatgpt.com "Building for Production"
