# Frontend Dev Guide (v2) — Minimal, Fast, Boring (and ready to grow)

This refresh keeps the original spirit but adapts it to a codebase that’s past v0 and needs healthy seams for ~3× growth without ceremony.

------

# 1) Core principles (print this)

1. **Do the simplest thing that works — again.** Prefer a tiny hook or pure function over a new abstraction. If a `for` loop reads better, use it.
2. **Fail fast, fail loud, fail usefully.** Throw on hard invariants; surface exact context in UI; never ignore a promise rejection.
3. **Use the platform until it hurts, then add the thinnest shim.** No “unified clients” or global stores unless there’s a measured need.
4. **Data > code.** Sorts/filters/layouts are **pure functions** over data. UI composes them.
5. **Seams before frameworks.** Create small, stable seams (layout strategy, filter/sort model, viewer zoom/pan math). Avoid framework lock-in.

------

# 2) Architecture (how the app hangs together)

**Composition root:** `app/AppShell.tsx` (thin). Owns high-level wiring only: current folder, selection array, viewer path, search query, star filters, context menu position.

**Feature slices** (UI + hooks + pure model together):

- `features/browse/` — grid & list browsing
  - `VirtualGrid.tsx`, `GridRow.tsx`, `ThumbCard.tsx`, `PreviewOverlay.tsx`
  - `useVirtualGrid.ts`, `useKeyboardNav.ts`, `useHoverPreview.ts`
  - `model/filters.ts`, `model/sorters.ts`, `model/layouts.ts`
- `features/folders/` — tree & dnd rules (`FolderTree.tsx`, `useFolderTree.ts`)
- `features/inspector/` — sidecar editing (`Inspector.tsx`, `useInspector.ts`)
- `features/viewer/` — full image view (`Viewer.tsx`, `useZoomPan.ts`, `useViewerHistory.ts`)
- `features/ratings/` — star filters + export (`useStarFilters.ts`, `services/exportRatings.ts`)
- `features/search/` — search hook wrapper
- `features/selection/` — `useSelection.ts`

**Shared infra** (boring and flat):

```
shared/
  api/ base.ts client.ts folders.ts items.ts search.ts
  types/
  lib/ fetcher.ts blobCache.ts util.ts keyboard.ts dnd.ts queue.ts
  ui/ Toolbar.tsx Breadcrumb.tsx FilterPill.tsx
  styles/ theme.css app.css grid.css (optional split)
```

**State model:** local component state + React Query cache. Two small contexts only:

- **Sidebars layout** (left/right widths + persistence + drag handlers).
- **Viewer history** (pushState/back integration), scoped to viewer.

No Redux. No global event bus.

------

# 3) Dependencies (the “Are you sure?” checklist)

Before adding a lib, answer “yes” to at least one:

- Reduces bugs/perf work **today** (measured), or
- Replaces ≥ 40 lines of tricky code with something well-tested, tree-shakeable.

**Allowed / typical**

- React, **TanStack Query**, **react-virtual**/Virtuoso (one virtualizer), a tiny tokenizer.
- Types: `zod` only if you need runtime validation at edges (avoid in hot paths).

**Usually not**

- Redux/RTK, giant UI kits, CSS-in-JS at runtime, lodash-everything, router libraries (hash is enough), bespoke fetch wrappers.

Keep bundles small; **every new dep gets a perf note in PR**.

------

# 4) Performance rules (enforced)

**Virtualization & layout**

- Virtualize rows; fixed geometry by layout strategy. No masonry in default grid.
- `content-visibility: auto` on cells; `contain-intrinsic-size` to avoid CLS.

**Images**

- Grid uses pre-sized **`.thumbnail`** only. Viewer loads original lazily.
- Prefetch: current row + one row ahead; viewer prefetch ±2 neighbors.
- Blob caches (thumb/file) keyed by `(path, etag/hash?, variant)`.

**Main thread**

- Keep it bored. EXIF/parse/JSON stays in workers (frontend) or server.
- Only animate `transform`/`opacity`.

**Network**

- Abort offscreen loads; batch by folder; reuse connections.

**Perf budget (same targets)**

- p75 **time-to-first-grid**: hot < **700ms**, cold < **2.0s**
- p95 **scroll frames > 16ms**: < **1.5%**
- Inspector open: < **150ms** (thumb first; full can stream)
- Thumbnail cache hit after first browse: **> 85%**

Add a short perf note to any PR touching grid/network/layout.

------

# 5) Error handling (no ghosts)

Throw on hard invariants and **show a banner** with the fix:

- Mixed leaf/branch, pointer loops, missing permissions, invalid drop target.
- Folder is branch but user tries to upload → banner: “Select a leaf folder.”

**Logs** (client): include `sourceId`, `path`, `op`, `etag/hash`, `user`, `ts`.
 No stack traces in UI.

------

# 6) Frontend I/O contracts (unchanged essence)

**Sidecar `<file>.json`**
 `v, tags[], notes, exif{width,height,createdAt}, hash, updatedAt, updatedBy, star?`

- Set-merge tags; last-writer-wins notes; server sanity-checks timestamps.

**Thumbnail `<file>.thumbnail`**
 WebP, long edge ≤ 256px, q≈70.

**Folder `_index.json`**
 `items[] (name, path, w, h, size, type, hasThumb, hasMeta, hash?, addedAt?)`
 `dirs[] (name, kind)`. Paginate via `_index_0.json`… if large.

**Pointer config** stays as is.

------

# 7) UI behavior (keyboard/mouse)

**Grid**

- Arrow/WASD moves active; **Shift** creates range from anchor; **Cmd/Ctrl** toggles.
- **Enter** opens viewer. **Esc** clears selection. **/** focuses search.
- Drag: custom ghost; payload `application/x-lenslet-paths` JSON array.

**Viewer**

- Wheel zoom centered at cursor; drag to pan; **Esc** closes; Left/Right navigate.
- Toolbar shows zoom slider while viewer is active.

**Inspector**

- `1..5` sets star; `0` clears (works on multi-selection).
- Tags are comma-separated. Blur = persist (debounced queue for rapid edits).

**Folders**

- Auto-expand ancestors of current path; DnD only into **leaf** targets.

------

# 8) Layout/filters/sorts (the seams)

- **Layouts:** `flatLayout()` shipped; `justifiedLayout()` can be added later. Interface:

  ```ts
  type Layout = (opts: {containerW:number, gap:number, targetCell:number, aspect:{w:number,h:number}, captionH:number})
    => { columns:number, cellW:number, mediaH:number, rowH:number };
  ```

- **Filters:** pure predicates (`byStars`, `byQuery`, future `byMetricRange`).

- **Sorters:** pure comparators (`byAdded`, `byName`, `byMetric(name, getter)`).

These files are **model** code, not React; they get unit tests.

------

# 9) Styling

- Keep plain CSS (`theme.css`, `app.css`). Use classes.
- Prefer **media queries** and properties over runtime style calc.
- Visible focus rings; keyboard navigability is required.

------

# 10) Code size & style

- **Components ≤ 200 lines**, **hooks ≤ 120**, **modules ≤ 300**. Split when exceeded or when a file has >1 responsibility (render + complex behavior).
- **Naming:** boring and explicit—`useZoomPan`, `flatLayout`, `exportRatingsCsv`.
- **Comments:** *why* over *what*; link to decision notes when non-obvious.
- **TypeScript:** strict; no `any`; narrow types at edges; prefer `readonly` where apt.

------

# 11) Testing (fast and useful)

**Unit**

- `useKeyboardNav` (index math), `layouts.flatLayout` (geometry), filters/sorters (golden arrays), `useZoomPan` (fit/scale clamping).

**Integration (frontend)**

- Grid selection (single, toggle, range).
- Viewer zoom/pan basic flows.
- Inspector star/notes/tags persistence (mock API).

**Smoke**

- Load a 10k-item fixture; assert TTFG < 2s headless; scroll 5 screens without jank spikes.

**Fixtures**

- Golden `_index.json`, sidecars, pointer configs under `tests/fixtures/`.

------

# 12) PR rules (so code stays small)

- Max PR size: **~400 lines** net change. Split otherwise.
- Every PR includes:
  - **What changed** (1–2 lines),
  - **Why now** (1 line),
  - **How tested** (bullets),
  - **Perf note** if grid/network/layout touched.
- No “refactor + feature” in the same PR.

------

# 13) Observability (just enough)

**Client metrics:** TTFG, dropped frames %, inspector latency, thumb cache hit %.
 **Server metrics (unchanged):** index throughput, 4xx/5xx, thumb backlog, S3 HEAD/GET counts.
 **Health files:** `_health.json` per root (counts, orphans, missing thumbs).

------

# 14) Import/Export & ratings (near-term features)

- **Export ratings**: service in `features/ratings/services/exportRatings.ts` (JSON/CSV). Hook from context menu and/or toolbar.
- **Import/export data** (later): wire to backend endpoints in `shared/api/*`. Keep transforms pure; downloads via `<a download>` (no new lib).

------

# 15) Feature flags / experiments

- Use **compile-time** boolean in env for large experiments (e.g., `VITE_LAYOUT_JUSTIFIED`).
- Avoid runtime flag library. Remove dead code swiftly.

------

# 16) Security & privacy (frontend)

- Never store secrets. Local storage: only benign prefs (sidebar widths, sort choice, star filter selection).
- Clipboard: user-initiated only.
- Blob URLs revoked on unmount; drag payloads sanitized.

------

# 17) When to add a wrapper (Tauri)

Only when you **need** file watching or broad local access.
 Define `HostBridge` interface; don’t ship an implementation until required. If web works, ship web.

------

# 18) Definition of Done (frontend)

- Grid renders a mixed tree within perf budget.
- Inspector edits persist to sidecars (single + multi).
- Search works against `_index/_rollup.json`.
- No local-only metadata survives reload.
- Smooth scroll under load; metrics confirm.
- Component and hook sizes remain within budget.

