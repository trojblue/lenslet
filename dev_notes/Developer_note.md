# Dev Guide: Minimal, Fast, Boring (on purpose)

## Core Philosophy (print this)

1. **Do the simplest thing that works.** If a `for` loop solves it, you don’t need RxJS, a homegrown DI container, or a manifesto.
2. **Fail fast, fail loud.** Throw early, log exact context, surface errors in UI. Silent failures are how bugs retire with benefits.
3. **Zero clever wrappers.** No 100-line “unified fetch abstraction” for two endpoints. Use the platform until it hurts; **then** add the thinnest layer possible.
4. **Data > code.** Store rules/config in files (JSON in S3/local). Code reads data; it doesn’t predict the future.
5. **Sidecar is the source.** Metadata lives next to images. Browser cache is disposable. If it’s not in the sidecar, it’s not real.

------

## Scope Guardrails

- **Supported formats only:** JPEG, PNG, WebP. If you accidentally decode HEIC, buy yourself a cake and then delete the code.
- **Leaf vs Branch:** Branch folders have **only subfolders**. Leaf folders are **real** or **pointer**. If you see images *and* subfolders together, **throw** and show a red badge in UI.
- **No local secrets/state:** Tags/notes write immediately to sidecars (S3 or local). Browser stores a tiny LRU of thumbs at most.

------

## Dependencies (the “Are you sure?” checklist)

Before you add a library:

- Can you do it with native APIs in ≤ 20 lines? If yes, do that.
- Will this lib reduce bugs or perf work meaningfully **today**? Not “when we add AI.” Today.
- Is it tree-shakeable and < 10KB gz? If not, justify in the PR description like a grown-up.
- Does it force patterns we don’t need (global stores, decorators, magic)? Hard pass.

**Likely OK:**

- Frontend: React, TanStack Query, a tiny virtualized list (Virtuoso/react-virtual), a tiny tokenizer.
- Backend: FastAPI, aioboto3, pyvips/Pillow, orjson/ujson.
- Workers: asyncio, concurrent.futures.
- Tooling: ruff + black (Python), eslint + prettier (JS/TS), mypy/pyright.

**Likely Not OK:** moment.js, lodash-everything, giant UI kits, Redux (for this scope), “universal fetch wrapper,” runtime CSS-in-JS.

------

## Performance Rules (how to actually make it smooth)

- **Grid:** virtualize everything, fixed cell geometry. No masonry in v0.
- **Images:** always use pre-sized thumbnails for the grid (`.thumbnail` files). Full-size loads only in the inspector.
- **Rendering:** `content-visibility: auto` on grid items, `contain-intrinsic-size` to avoid CLS.
- **Animations:** only `transform`/`opacity`. No layout properties, no blur, no shadows that animate.
- **Network:** batch by folder, reuse connections, AbortController to cancel offscreen loads, prefetch one row ahead, not ten.
- **Work split:** EXIF/parse/JSON I/O in Web Workers (frontend) and Python workers (backend). Keep main thread bored.

Perf budget (enforce it):

- p75 **time-to-first-grid**: hot < 700ms, cold < 2.0s.
- p95 **scroll frames over 16ms**: < 1.5%.
- Inspector open: < 150ms (thumb first, full image can stream).
- Thumbnail cache hit: > 85% after first browse.

------

## Error Handling (no ghosts)

- **Hard invariants → throw:** mixed leaf/branch, pointer loops, missing permissions.
- **User-facing banner** with exact path + action (“Re-auth S3”, “Fix folder: contains images and subfolders”).
- **Logs:** include `sourceId`, `path`, `op`, `etag/hash`, `user`, `ts`. No stack traces in UI, obviously.

------

## I/O Contracts (keep them boring)

### Sidecar (`<file>.json`)

- `v, tags[], notes, exif{width,height,createdAt}, hash, updatedAt, updatedBy`
- Last-writer-wins on `notes`, **set-merge** on `tags`. Server enforces timestamp sanity.

### Thumbnail (`<file>.thumbnail`)

- WebP, long edge ≤ 256px, q≈70. No dynamic resizing in-browser.

### Folder Manifest (`_index.json`)

- Lists `items[]` (name, w, h, size, hasThumb, hasMeta, hash?) and `dirs[]` (name, kind).
- If large: paginate by stable alphabetical chunks (`_index_0.json`, `_index_1.json`).

### Pointer Config (`.lenscat.folder.json`)

- `kind: "pointer"`, `target: {type: "s3"|"local", bucket/prefix or path}`, `label`, `readonly`.

------

## Backend (Python-first, flat files)

- **FastAPI** endpoints: `GET /folders`, `GET/PUT /item`, `GET/POST /thumb`, `GET /search`.
- **Workers (async):** indexer builds/refreshes `_index.json` + `_rollup.json`, generates thumbs, computes hashes.
- **No database** for MVP. All state in JSON + files. If you’re typing “Postgre…”, take a walk.

**Implementation notes**

- Prefer **aioboto3** with S3 Transfer Acceleration off unless needed.
- Use **pyvips** for thumbnails (fast), fallback to Pillow.
- Serialize with **orjson**.
- Hash with **BLAKE3** (fast, stable).
- Keep functions small; one responsibility; testable.

------

## Frontend (keep it tiny)

- **State:** query cache (TanStack) + local component state. No global store until we actually need it.
- **Layout:** CSS grid + flex; no runtime style calc.
- **Caching:** in-memory LRU for thumb blobs, optional OPFS LRU with strict cap (e.g., 512MB). Evict aggressively.
- **Keyboard:** arrow nav, Enter opens inspector, `t` adds tag. Don’t invent a hotkey DSL.

------

## Testing (fast and useful, not theatrical)

- **Unit:** pointer resolution, leaf/branch validation, sidecar merge.
- **Integration (backend):** S3 list → manifest → search.
- **Smoke (frontend):** load a 10k-item fixture; assert TTFG < 2s headless; scroll 5 screens without jank spikes.
- **Golden files:** sample `_index.json`, sidecars, pointer configs under `tests/fixtures/`.

------

## PR Rules (so code stays small)

- Max PR size: **~400 lines** net change. If bigger, split it.
- Each PR must include:
  - What changed (1–2 lines).
  - Why now (1 line).
  - How tested (bullets).
  - Perf note if it touches grid/network.
- No “refactor and feature” in one PR. That’s how bugs get diplomatic immunity.

------

## Observability (just enough)

- **Client metrics:** TTFG, inspector open latency, dropped frames %, thumb cache hit%.
- **Server metrics:** index throughput (items/sec), 4xx/5xx, thumb backlog size, S3 cost estimate (HEAD/GET counts).
- **Health files:** `_health.json` per root: counts, orphans, missing thumbs.

------

## Common Footguns (avoid these)

- **Ad-hoc caching** without invalidation → stale thumbnails forever. Always key by `(path, etag/hash, variant)`.
- **Animating box-shadow/border** on 2,000 elements → jank parade.
- **Recursive folder walkers** that don’t detect loops in pointer configs.
- **Writing local-only notes** because it was “easier.” Not allowed.
- **Batching “optimizations”** that delay first paint. First paint > perfect batching.

------

## When to add a wrapper (Tauri)

- Only when you **need** file watching or broad local access.
- Define an interface (`HostBridge`) now; do **not** ship an implementation.
- If the web path works, ship web. Curiosity isn’t a requirement.

------

## Code Style (copy/paste this into CONTRIBUTING.md)

- **Python:** ruff + black + mypy; functions < 50 lines; modules < 300 lines.
- **TS/JS:** eslint (no any), strict TS, components < 200 lines; hooks < 80 lines.
- **Naming:** boring and explicit. `buildFolderManifest`, not `scry`.
- **Comments:** why > what. Link to decision/rationale if non-obvious.

------

## Tiny Patterns That Help

- **Abortable fetch helper** (20 lines): returns `{promise, abort}`.
- **Queue with concurrency** (≤ 40 lines) for thumbnail preloads.
- **Guard utils** (≤ 10 lines each): `isLeaf`, `isPointer`, `assertBranch`.
- **Retry w/ jitter** (≤ 15 lines) for flakey S3 GETs.

------

## Definition of Done (MVP)

- Loads a mixed tree (branch + leaf + pointer) and **renders grid** within budget.
- Inspector edits **persist** to sidecars (local + S3).
- Search returns from `_rollup.json`.
- No local-only metadata survives a reload.
- Smooth scroll under load; metrics confirm.