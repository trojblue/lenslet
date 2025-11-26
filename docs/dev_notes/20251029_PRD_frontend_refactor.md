

# PRD — Frontend Structural Refactor (Gallery/Inspector/Viewer)

## Problem statement

- **Single-file hotspots** (`App.tsx` ~19k chars, `Grid.tsx` ~16k) mix rendering, layout math, keyboard/drag behavior, prefetch, and selection. This blocks maintainability and feature growth (ratings export, extra layouts, richer filters).
- Cross-cutting concerns (hash routing, resizers, context menu, star counts) live inside `App.tsx`, creating implicit coupling.
- There’s no stable place to add *new sorts/filters/layout strategies* or import/export hooks without inflating those hotspots.

**Constraint:** do not add heavy infra (no Redux, no global stores beyond React Query already in use). Keep wrappers thin; prefer pure functions and small hooks.

------

## Goals (measurable)

1. **Scalability:** withstand ~3× component count without new global abstractions.
2. **File size discipline:** components ≤ ~200 lines, hooks ≤ ~120 lines, modules ≤ ~300 lines.
3. **Performance parity or better:** preserve current perf rules and budgets; no observable regressions in TTFG/scroll smoothness.
4. **Change isolation:** adding a new filter or layout strategy should touch ≤ 3 files, none of which is `AppShell`.
5. **Testable units:** keyboard nav, selection range, and grid math become pure or hook-based and unit-testable.

Non-goals (for now): routing library, CSS-in-JS, masonry layout shipping by default, user management.

------

## High-level approach

Adopt a **lean feature-slice structure**: each feature keeps its UI + hooks + pure model functions close together, while shared infra (API, types, util) lives under `shared/`. No global store; only **two light contexts**: layout (sidebars) and viewer visibility.

This keeps changes local (feature folders) and avoids framework gravity.

------

## Proposed structure (after refactor)

```
src/
  app/
    AppShell.tsx                # replaces App.tsx as the page-level composer
    providers/QueryProvider.tsx # wraps TanStack Query (already present via qc)
    routing/hash.ts             # hash <-> path sync helpers
    layout/useSidebars.ts       # left/right width persistence + drag handlers
    menu/ContextMenu.tsx        # generic menu rendering (tree/grid actions passed in)

  features/
    browse/                     # "grid" & list browsing
      components/
        VirtualGrid.tsx         # scroller + virtual rows (container)
        GridRow.tsx             # renders a single row
        ThumbCard.tsx           # image cell (media + caption + zoom button)
        PreviewOverlay.tsx      # portal overlay for hover preview
      hooks/
        useVirtualGrid.ts       # column/row math, virtualization config
        useKeyboardNav.ts       # arrow/enter navigation logic
        useHoverPreview.ts      # prefetch blob + delayed show/revoke
      model/
        filters.ts              # pure predicates: stars, query, tags
        sorters.ts              # pure comparators (name, added, metric X)
        layouts.ts              # strategy interface (flat, justified placeholder)
      index.ts

    folders/
      FolderTree.tsx
      hooks/useFolderTree.ts    # expand/collapse, dnd guards

    inspector/
      Inspector.tsx
      hooks/useInspector.ts     # (moved from hooks/)

    viewer/
      Viewer.tsx
      hooks/useZoomPan.ts       # fit, zoom, pan math
      useViewerHistory.ts       # pushState/back handling

    ratings/
      hooks/useStarFilters.ts   # selection of star filters and counts
      services/exportRatings.ts # pure exporter (json/csv), uses shared/api
      index.ts

    search/
      hooks/useSearch.ts        # (wraps shared/api/search to keep feature-local)

    selection/
      hooks/useSelection.ts     # (existing) kept small, feature-local

  shared/
    api/
      base.ts
      client.ts
      folders.ts
      items.ts
      search.ts
      index.ts
    types/                      # Item, FolderIndex, Sidecar etc
    lib/
      fetcher.ts
      blobCache.ts
      util.ts
      keyboard.ts               # key helpers (isTextInputTarget, etc.)
      dnd.ts                    # tiny helpers for dataTransfer mime
      queue.ts                  # ≤ 40 lines concurrency queue (already in spirit)
    ui/
      Toolbar.tsx
      Breadcrumb.tsx
      FilterPill.tsx
    styles/
      theme.css
      app.css                   # (split from styles.css gradually)
      grid.css                  # (optional follow-up; otherwise keep current)

  main.tsx
```

> Notes
>
> - This is **not** introducing a multi-package mono-repo; it’s only a folder reshuffle with a few focused splits.
> - Keep `styles.css` and migrate gradually to `styles/app.css` and `styles/grid.css` only if helpful; do **not** mandate CSS Modules or a new system.

------

## Key design choices (and why)

1. **Feature slices over layer slices.**
    Keeps changes local. Adding a new “metric sort” only touches `features/browse/model/sorters.ts` and `shared/api/*` if it’s remote. `AppShell` remains thin.

2. **Hooks as boundaries, not classes.**

   - `useVirtualGrid` owns row/column math and virtualization config.
   - `useKeyboardNav` is pure: given `items`, `active`, `columns` → next index.
   - `useZoomPan` centralizes fit/zoom math used by `Viewer`.
      These make perf-sensitive parts unit-testable without rendering.

3. **Strategy seam for layouts — but ship only “flat.”**
    `layouts.ts` exports a minimal interface:

   ```ts
   export type Layout = (opts: {containerW: number, gap: number, targetCell: number}) =>
     { columns: number, cellW: number, mediaH: number, rowH: number };
   ```

   Today, `flatLayout()` implements your current 4:3 grid. A `justifiedLayout()` can later plug in without rewriting `VirtualGrid`.

4. **Filters/sorters are pure data functions.**
    No hidden state. Given `items` + `starFilters` + `query`, return an array. Easy to benchmark and extend (e.g., `sortByMetric('aestheticScore')`).

5. **Context menu becomes a component, not a blob in `App.tsx`.**
    `ContextMenu` only renders; actions are passed in. This makes adding “Export ratings” or “Export files” a <20-line change.

6. **No new global store.**
    Layout widths use one small context from `useSidebars`; everything else is local state or React Query.

------

## File splits (most impactful)

### Grid split (current `components/Grid.tsx`)

- **`VirtualGrid.tsx`** (≈120–160 lines)
  - Owns `parentRef`, virtualization, scroll flags, row rendering loop.
  - Delegates cell to `ThumbCard`, preview overlay to `PreviewOverlay`.
  - Exposes `onSelectionChange`, `onOpenViewer`, `onContextMenuItem`.
- **`GridRow.tsx`** (≤80 lines)
  - Receives sliced items for a row, renders N `ThumbCard`s.
- **`ThumbCard.tsx`** (≤120 lines)
  - Purely renders one card (media + caption).
  - Handles click/range/toggle selection, drag-start payload, and tiny prefetch hints.
  - Uses `Thumb` from shared if you prefer, or keeps current code but localized.
- **`PreviewOverlay.tsx`** (≤50 lines)
  - The portal overlay and opacity transitions; URL creation/revocation entirely inside `useHoverPreview`.
- **`useVirtualGrid.ts`** (≤120 lines)
  - All the math now lives here: columns, row heights, `useVirtualizer` config, `measure()` triggers.
- **`useKeyboardNav.ts`** (≤90 lines)
  - Returns `handleKeyDown` for grid nav; completely unit-testable.

Immediate benefits: **`Grid.tsx` shrinks 60–70%**, behavior becomes testable, and adding layouts/filters doesn’t touch the scroller.

### App split (current `App.tsx`)

- **`AppShell.tsx`**:

  - Imports: `Toolbar`, `FolderTree`, `VirtualGrid`, `Inspector`, `Viewer`, `ContextMenu`, `Breadcrumb`.
  - Holds only high-level wiring and short state orchestrations (current folder, selection array, viewer path, query string, star filter array).
  - Uses:
    - `useHashLocation()` from `routing/hash.ts` for path ↔ hash.
    - `useSidebars()` for left/right widths + persistence + resize handlers.
    - `useViewerHistory()` inside `viewer` feature to manage `pushState`/`back`.

- **`routing/hash.ts`**:

  - `sanitizePath`, `readHash()`, `writeHash(path)` – pure, unit-tested.

- **`menu/ContextMenu.tsx`**:

  - Stateless bubble that renders menu items for tree/grid, given callbacks:

    ```ts
    type MenuItem = { label: string; danger?: boolean; disabled?: boolean; onClick: () => void };
    ```

  - `AppShell` prepares items (move to trash, delete, recover, export ratings).

------

## APIs and extension points

### Filters & sorts (pure)

```ts
// features/browse/model/filters.ts
export function byStars(active: number[] | null) {
  return (it: Item) => !active?.length ? true : (active.includes(it.star ?? 0));
}
export function byQuery(q: string) { /* name/tags/notes match (client-side) */ }

// features/browse/model/sorters.ts
export const sortByName: Comparator<Item> = (a,b) => a.name.localeCompare(b.name);
export const sortByAdded: Comparator<Item> = (a,b) => (Date.parse(a.addedAt||'') - Date.parse(b.addedAt||'')) || sortByName(a,b);
export function sortByMetric(name: string, get: (it: Item) => number): Comparator<Item> {
  return (a,b) => get(a) - get(b) || sortByName(a,b);
}
```

### Layout strategy seam

```ts
export type LayoutResult = { columns: number; cellW: number; mediaH: number; rowH: number };
export type Layout = (opts: { containerW: number; gap: number; targetCell: number; aspect: {w:number,h:number}; captionH:number }) => LayoutResult;

export const flatLayout: Layout = ({containerW, gap, targetCell, aspect, captionH}) => {
  const columns = Math.max(1, Math.floor((containerW + gap) / (targetCell + gap)));
  const cellW   = (containerW - gap * (columns - 1)) / columns;
  const mediaH  = (cellW * aspect.h) / aspect.w;
  const rowH    = mediaH + captionH + gap;
  return { columns, cellW, mediaH, rowH };
};
```

### Ratings export service

```ts
// features/ratings/services/exportRatings.ts
export function exportRatings(items: Item[], format: 'json'|'csv') {
  // JSON: [{path, name, star, tags, notes}]
  // CSV:  path,name,star,tags,notes
  // Pure transform; file saving stays in UI (anchor download)
}
```

This gives you a stable location to build “export ratings per folder” or “export entire tree” later.

------

## Incremental migration plan (small PRs, each ≤ ~400 LoC net)

**PR 1 — Scaffold & moves (no logic changes)**

- Create `app/`, `features/`, `shared/` folders.
- Move existing files into closest equivalents (e.g., `components/Inspector.tsx` → `features/inspector/Inspector.tsx`).
- Keep import paths working (optionally add `paths` in `tsconfig.json`).

**PR 2 — Extract routing & sidebars**

- `routing/hash.ts` with `sanitizePath`, `readHash`, `writeHash`.
- `layout/useSidebars.ts` with persisted widths + resizer handlers.
- Slim `App.tsx` → `app/AppShell.tsx`.

**PR 3 — Grid split (container + row + card + preview)**

- Introduce `VirtualGrid`, `GridRow`, `ThumbCard`, `PreviewOverlay`, `useVirtualGrid`, `useHoverPreview`, `useKeyboardNav`.
- Keep behavior identical (selection, drag payload, prefetch).

**PR 4 — Viewer hooks**

- `useZoomPan` and `useViewerHistory`. Shrink `Viewer.tsx` by ~40–50%.

**PR 5 — Context menu component**

- Stateless `ContextMenu` that receives menu item arrays.
- `AppShell` prepares tree/grid menus (move, delete, recover).

**PR 6 — Filters & sorts model**

- Move star/query filters and sorters to pure functions (`features/browse/model`).
- `AppShell` composes: `let arr = applySort(applyFilters(base, ...))`.

**PR 7 — Ratings slice**

- `useStarFilters` (UI state + localStorage persistence).
- `exportRatings` service; add one menu entry “Export ratings (CSV/JSON)”.

**PR 8 — API consolidation**

- Move `api/*` under `shared/api/*` (no behavior change).
- Keep thin client; no “unified fetch abstraction”.

**PR 9 — Optional style nits**

- Extract grid-specific CSS to `styles/grid.css` only if helpful; otherwise keep current stylesheet.

Each step is safe to ship independently and revertible.

------

## Acceptance criteria

- `AppShell.tsx` ≤ 350 lines; `VirtualGrid.tsx` ≤ 160; `Viewer.tsx` ≤ 250.
- Keyboard nav, zoom/pan, and layout math have unit tests (at least golden cases).
- No perf budget regression (same metrics as Dev Guide).
- Adding a **new sort by metric** requires:
   1 file added to `sorters.ts` and
   1 small toggle in `Toolbar` to pick it,
   with **no** edits to `VirtualGrid` or `AppShell` logic.
- Adding a **justified layout** later: implement `justifiedLayout()` and a single prop switch in `VirtualGrid`.

------

## Risk & mitigation

- **Over-fragmentation:**
   Mitigated by strict file count and size budgets, and by keeping data seams pure.
- **Hidden coupling via contexts:**
   Only layout widths and viewer history get contexts; all other state remains local or in React Query.
- **Drag & drop complexities:**
   Keep existing MIME (`application/x-lenscat-paths`) and behavior; factor helpers into `shared/lib/dnd.ts`.

------

## What changes in code (examples, small and boring)

**`useKeyboardNav.ts` (pure handler factory)**

```ts
export function makeKeyHandler(items: Item[], columns: number, activePath: string | null, open: (p:string)=>void, select: (paths:string[])=>void) {
  return (e: KeyboardEvent) => {
    if (!items.length) return;
    const idx = activePath ? items.findIndex(i => i.path === activePath) : 0;
    let next = idx;
    const col = Math.max(1, columns);
    if (e.key === 'ArrowRight' || e.key === 'd') next = Math.min(items.length - 1, idx + 1);
    else if (e.key === 'ArrowLeft' || e.key === 'a') next = Math.max(0, idx - 1);
    else if (e.key === 'ArrowDown' || e.key === 's') next = Math.min(items.length - 1, idx + col);
    else if (e.key === 'ArrowUp' || e.key === 'w') next = Math.max(0, idx - col);
    else if (e.key === 'Enter' && activePath) { open(activePath); return; }
    else return;
    e.preventDefault();
    const nextItem = items[next]; if (!nextItem) return;
    select([nextItem.path]);
  };
}
```

**`features/browse/model/apply.ts`**

```ts
export function applyFilters(items: Item[], q: string, stars: number[] | null) {
  return items.filter(byQuery(q)).filter(byStars(stars));
}
export function applySort(items: Item[], kind: 'name'|'added'|['metric', string, (i:Item)=>number], dir: 'asc'|'desc') {
  const cmp = kind === 'name' ? sortByName :
             kind === 'added' ? sortByAdded : sortByMetric(kind[1], kind[2]);
  const arr = [...items].sort(cmp);
  return dir === 'desc' ? arr.reverse() : arr;
}
```

**`app/routing/hash.ts`**

```ts
export const ALLOWED_PATH = /^[\/@a-zA-Z0-9._\-\/]{1,512}$/;
export function sanitizePath(raw: string): string { /* current logic, isolated */ }
export const readHash = () => sanitizePath((window.location.hash || '').replace(/^#/, ''));
export const writeHash = (p: string) => { const h = `#${encodeURI(p)}`; if (window.location.hash !== h) window.location.hash = h; };
```

No new abstractions beyond what you already do; just clean seams.

------

## How this supports future asks

- **Import / export data**: `shared/api` holds endpoints; `ContextMenu`/`Toolbar` plugs actions; `ratings/services/exportRatings.ts` gives immediate win.
- **Different grid layouts**: strategy seam in `browse/model/layouts.ts`.
- **More filtering methods / backend metrics**: add pure predicates or metric mappers without touching grid or app wiring.
- **User control later**: keep “user” out of feature code; when added, fetch user identity in `shared/api/session.ts` and thread through props/queries without global state.

------

## Minimal checklist for each PR

- Keep PR ≤ ~400 net LOC.
- Include “what/why/how tested/perf note” per your Dev Guide.
- Run quick headless smoke: load 10k fixture, assert TTFG & scroll jank thresholds.