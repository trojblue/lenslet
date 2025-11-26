Alright, tiny gallery gremlin, I read your whole Franken-repo. It’s… actually solid. Clean state, smart prefetching, thoughtful CSS, and you didn’t commit any crypto miners. Shocking. Here’s the blunt review you came for.

## Verdict

**8.3/10 – production-ish.** Fast, tidy, and the UX mostly slaps. Biggest gaps are accessibility, a few perf footguns, and some rough edges with input debouncing & ARIA semantics.

## What you did well (yes, I hate saying this)

* **Virtualization done right:** `@tanstack/react-virtual` + `contain/content-visibility` + measured row height. Smooth scroll, nice overscan (8).
* **Blob hygiene:** Revoke thumb/file URLs, LRU for blobs, prefetch with a **40 MB** cap. You actually thought about RAM.
* **Viewer feels premium:** Pinch/scroll zoom math with cursor anchoring, base scale fit, thumb-first fade. It’s the good kind of overkill.
* **State shape:** URL-hash routing + React Query + local overrides for optimistic stars. Mature.
* **Keyboard nav:** WASD/arrow support with “open on Enter.” Your future self will thank you.

## Bugs / risks / papercuts (fix these first)

1. **Search hammers the API per keystroke.**
   Add a 200–300 ms debounce so React Query isn’t DDoS’ing your backend.

   ```ts
   // hooks/useDebounced.ts
   export function useDebounced<T>(v:T, ms=250){ const [d,setD]=React.useState(v); React.useEffect(()=>{const t=setTimeout(()=>setD(v),ms); return ()=>clearTimeout(t)},[v,ms]); return d }
   // Toolbar -> AppShell
   const debouncedQ = useDebounced(query, 250)
   const search = useSearch(searching ? debouncedQ : '', current)
   ```
2. **Tree/drag ARIA is MIA.**
   Div soup. Screen readers will hate this. Use `role="tree"`, `role="treeitem"`, `aria-expanded`, `aria-selected`, and keyboard handlers (Up/Down/Left/Right/Home/End). Add focus ring to items, not just the whole pane.
3. **Context menu has destructive actions without confirm.**
   “Permanent delete” should confirm, unless you *enjoy* support tickets. Add a minimal confirm modal.
4. **Upload restricted to leaf folders only.**
   That’s surprising UX. Either allow uploads anywhere or show a toast explaining why the drop is ignored.
5. **Hover preview fetches full file eagerly.**
   On slow networks you’ll get a convoy of big downloads. Gate on network conditions & size headers, or use a dedicated medium-res endpoint if possible. At least don’t start full fetch until the delay elapses.

   ```ts
   const t = window.setTimeout(async ()=>{ /* THEN fetch file */ }, 350)
   ```
6. **Keyboard “Backspace” to go up a folder can fight browser history.**
   You guard inputs, good, but consider scoping it to the grid element while focused to avoid surprises.

## Performance tune-ups (cheap wins)

* **Prefetch discipline:** In `VirtualGrid`, you prefetch next row thumbs twice (inside `try` and again unguarded). Dedup that. Also pause prefetch while `isScrolling` is true (you already try—tighten it).
* **Memo storm control:** `items` pipeline is good; also memoize `selectedSet` and `pathToIndex` (you did) and avoid recreating closure-heavy handlers in big maps where possible.
* **Resize observers:** You already center on `ResizeObserver`. Debounce layout re-measure to the next animation frame to avoid thrash on continuous resizes.
* **RequestAnimationFrame close:** Nice 110 ms fade. Consider `prefers-reduced-motion` (you already respect globally; viewer opacity transition is fine).

## Accessibility (you’re close, but not there)

* **Grid semantics:** You have `role="grid"`. Add `role="row"` & `role="gridcell"` to rows/cells and drive `aria-selected` off selection. Give each cell a roving `tabIndex` for keyboard focus (not just parent focus).
* **Toolbar buttons:** Add `aria-pressed` for star toggles and tooltips → `aria-label`.
* **Breadcrumbs:** Mark the last segment `aria-current="page"` (you already do, good).
* **Contrast & focus:** You added `*:focus-visible`. Ensure hover-only affordances (zoom icon) have keyboard equivalents.

## DX / maintainability

* **Centralize keybindings.** They’re scattered (AppShell, Inspector, Grid, Viewer). Create a tiny `useHotkeys(scope)` so you don’t accidentally double-bind.
* **API base logic:** `computeApiBase` is careful. Add a console info on final `BASE` in dev to kill “why is this 404ing” debugging.
* **Types:** Sidecar fallbacks are casty (`as any`). Define a `defaultSidecar()` factory to keep it typed and reusable.

## Security & robustness

* **Path sanitizer:** `ALLOWED_PATH` is strict and fine for your use case. Still, treat server APIs as source of truth—never trust client path checks.
* **Drag payload:** Using `application/x-lenscat-paths` is good. Consider validating list length & dedup on server, not just client.
* **Blob revocation:** You’re disciplined. Also revoke preview blob on backdrop unmount (you already do with `previewUrlRef`—nice).

## UX nits

* **Rating filter “All” vs. empty list:** Works because your filter treats empty as “no filter,” but show an inline “× Clear” chip near the filter button (you already render a pill; make clicking the star icon toggle visible state and ESC closes it).
* **Inspector batch edit:** Great. Add a little “Applied to N files” toast so users don’t wonder.
* **Viewer close-on-click:** Good; add a dedicated close button in the corner for clarity (some users hate “click anywhere” closers).

## Tiny diffs you can drop in today

* **Confirm before permanent delete**

  ```tsx
  // cheap prompt
  arr.push({ label: 'Permanent delete', danger: true, onClick: async () => {
    if (!confirm(`Delete ${sel.length} file(s) permanently? This cannot be undone.`)) return
    try { await api.deleteFiles(sel); await refetch() } finally { setCtx(null) }
  }})
  ```
* **ARIA in tree item**

  ```tsx
  <div
    role="treeitem"
    aria-level={depth+1}
    aria-expanded={isExpanded}
    aria-selected={isActive}
    tabIndex={0}
    // keep existing handlers
  >
  ```
* **Debounced search** (see snippet above).
* **Delay-before-fetch for hover preview** (see perf note above).

## Future candy (if you insist on being fancy)

* “Open in compare mode” (split viewer, lock zoom, pan-sync).
* Saved views: persist sort + filters per folder in sidecar/meta.
* Keyboard palette (`Cmd+K`) to jump to folder, filter stars, etc.
* Quick tag suggestions from frequency.

If you ship nothing else, do: **debounced search**, **ARIA roles + roving focus**, **confirm dangerous actions**, **delay fetch after hover delay**. That’ll bump you into the “didn’t phone it in” tier.

Now go fix it so I can rate it a 9. And yes, I’ll notice if you try to just rename variables and call it a refactor.
