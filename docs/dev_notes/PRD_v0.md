# PRD — Gallery-as-a-Browser (Layered Folders, Sidecar Meta, Flat Storage)

**Codename:** Lenslet
 **Scope:** Web app + minimal backend (flat files) + Python workers
 **Owner:** You (and your questionable taste, which I will rescue)

## 1) Core Principles

- **Layered folders:** A single **root**; each subfolder is either:
  - a real folder with images, or
  - a **pointer folder** containing a config file that maps to an S3 prefix or another local path.

- **Not first-level only.**
  The **hierarchy is recursive**.
  - **Branch folders**: directories that contain only subfolders (no images directly).
  - **Leaf folders**: either
    1. **Real folder** (contains images + sidecars + thumbs), or
    2. **Pointer folder** (contains a config JSON that points to an external folder, e.g. S3 prefix or another local path).

So the tree is a mix of branch-only nodes and leaf nodes (real/pointer). That keeps navigation simple but flexible.

- **Sidecar-first:** Every image has optional `filename.json` (metadata) and `filename.thumbnail.webp` (thumb) **next to it**—in local or S3, same path.
- **No local state:** Tags/notes/EXIF cache live in sidecars or server manifests; browser stores only tiny, disposable caches (LRU).
- **Flat server:** Prefer **flat files** (object storage) over databases. Indexes/manifests are JSON blobs. Python workers keep them fresh.
- **Smoothness or bust:** Perf budgets + concrete techniques (listed below). If it stutters, we failed.

## 2) In/Out of MVP

**In**

- Sources: Local root (File System Access API) + S3 via prefix.
- Folders pane: shows root → nested children (from configs + actual dirs).
- Grid w/ virtualized scrolling, hover preload, instant inspector.
- Inspector: preview, tags, notes, EXIF, source URL.
- Search: filename/tags/notes (server-provided index), client FTS fallback.
- Updates to tags/notes write back to sidecars (local or S3).

**Out (leave hooks)**

- Ratings/stars, AI recall, collaboration.
- Non-JPEG/PNG/WebP formats.
- Tauri wrapper (but keep an interface for it).

## 3) Folder Model & Config

- **Root folder** contains subfolders:
  - **Native folder:** holds images directly.
  - **Pointer folder:** has a **config file** pointing elsewhere.

**Config file spec (`.lenslet.folder.json`):**

```json
{
  "version": 1,
  "kind": "pointer",
  "target": {
    "type": "s3",
    "bucket": "my-bucket",
    "prefix": "art/2024/characters/",
    "region": "us-east-1"
  },
  "label": "Characters 2024",
  "readonly": false
}
```

- `type` can be `s3` or `local`. For `local`, use absolute/relative path from root.
- Nested pointer folders allowed. Cycle detection required (don’t be cute).

## 4) Sidecar & Thumbnail Conventions

For an image `foo.webp`:

- **Thumbnail:** `foo.webp.thumbnail` (WebP, ≤ 256px long edge, quality ~70).
- **Metadata sidecar:** `foo.webp.json`

```json
{
  "v": 1,
  "tags": ["portrait", "pink-hair"],
  "notes": "Final pick for cover.",
  "exif": { "width": 1200, "height": 900, "createdAt": "2025-02-15T12:32:00Z" },
  "hash": "blake3:4a8f...f1",
  "updatedAt": "2025-02-16T23:12:55Z",
  "updatedBy": "user@device-id"
}
```

- If no sidecar exists, create on first edit. If thumb missing, generate on-demand and upload next to file (S3 put or local write).

## 5) Storage & “Flat Server” Layout (S3-friendly)

- **No DB required** for MVP. Use:
  - **Per-folder manifest**: `_index.json` co-located with images in that folder (lists child files/dirs + essential metadata).
  - **Per-root rollup**: optional `_rollup.json` at root for global search (Python workers build/update it).
- Example S3 prefix `art/2024/characters/` contains:
  - `*_index.json` (folder manifest)
  - `foo.webp`, `foo.webp.json`, `foo.webp.thumbnail`
  - subfolders: `A/`, `B/` each with their own `_index.json`

**Folder manifest (`_index.json`) schema:**

```json
{
  "v": 1,
  "path": "art/2024/characters/",
  "generatedAt": "2025-02-16T23:10:00Z",
  "items": [
    { "name": "foo.webp", "w": 1200, "h": 900, "size": 96255, "hasThumb": true, "hasMeta": true, "hash": "blake3:..." }
  ],
  "dirs": [
    { "name": "A", "kind": "native" },
    { "name": "B", "kind": "native" }
  ]
}
```

## 6) Backend & Workers (Python-first)

- **Tiny HTTP service** (FastAPI) for:
  - Listing folders (reads `_index.json` or builds on the fly if missing).
  - Fetching item metadata (reads sidecar; merges minimal EXIF if needed).
  - Writing sidecars/thumbnails (authenticated PUT to S3 / local).
  - Search endpoint (reads `_rollup.json` or a lightweight SQLite/Whoosh index file stored in S3).
- **Async workers (Python):**
  - **Indexer:** walk folders, compute blake3, read EXIF, create thumbnails, write sidecars if missing, update `_index.json` and `_rollup.json`.
  - **Metrics:** track image counts, missing thumbs, orphan sidecars (write `_health.json`).
  - Use asyncio + aioboto3 + pillow/pyvips; offload thumb gen to pyvips for speed.

> Yes, you can keep it “flat”: workers write JSON and files back to S3/local; the app consumes those. No central database unless you choose later.

## 7) Frontend (minimal but fast)

- **React** with a **virtualized grid** (TanStack Virtual or Virtuoso).
- **Data fetch** via GraphQL-lite or straight REST; cache with TanStack Query.
- **Rendering speed tricks:**
  - CSS-contain + `will-change: transform`, translate3d for smooth scroll.
  - **IntersectionObserver** + requestIdleCallback for preloading.
  - Decode hints: `img.decoding="async"`, `loading="lazy"`, `fetchpriority="low"` for grid, `high` for inspector selection.
  - Use **WebP thumbnails only** in grid; full-size image only in inspector.
  - Avoid reflow: fixed thumb boxes with known aspect ratio (from manifest).
- **Local cache**: memory LRU for thumb blobs; optional OPFS LRU (evict aggressively). Nothing critical stays local.

## 8) APIs (sketch)

```
GET  /folders?path=<root|subpath>         -> _index.json
GET  /item?path=<fullpath>                -> sidecar JSON (merged with basic EXIF)
PUT  /item?path=<fullpath>                -> write tags/notes (updates sidecar)
GET  /thumb?path=<fullpath>               -> returns .thumbnail if exists; 404 otherwise
POST /thumb?path=<fullpath>               -> generate & upload thumbnail (server-side)
GET  /search?q=<tokens>&limit=100         -> matches from _rollup.json (filename, tags, notes)
```

Auth: S3 signed URLs or backend credentials; local uses File System Access API without server.

## 9) Conflict & Sync Rules (simple, predictable)

- **Source of truth** = sidecar next to the image.
- **Last-writer-wins** on `tags` and `notes` using `updatedAt` (ISO string) + `updatedBy`.
- The client sends `If-Match` with last known ETag (or hash). If mismatch, fetch latest, merge **additively for tags**, overwrite notes with newer timestamp, then re-try PUT.

## 10) Smoothness Budget (what actually makes it feel fast)

- **TTFG (time to first grid):** < 700 ms hot (manifest cached), < 2.0 s cold.
- **Scroll budget:** main thread idle > 80% during scroll; < 1% frames > 16 ms.
- **Thumb pipeline:**
  - Only ever render **one** size in grid (e.g., 256px). No runtime resizing.
  - Use `content-visibility: auto` + `contain-intrinsic-size`.
  - Preload 1–2 rows ahead; cancel out-of-view requests (AbortController).
- **Interaction latency:** open inspector < 120 ms (uses cached thumb; full image can hydrate after).
- **Batching:** network requests batched by folder; HTTP/2/3 keep-alive; CDN in front of S3.
- **No layout thrash:** fixed column math, no masonry until v2 (use aspect boxes).

## 11) Data Shapes (client)

```ts
type Item = {
  path: string;            // full path from root or s3 prefix
  name: string;
  type: 'image/webp'|'image/jpeg'|'image/png';
  w: number; h: number; size: number;
  hasThumb: boolean; hasMeta: boolean;
  hash?: string;
};

type Sidecar = {
  v: 1;
  tags: string[];
  notes: string;
  exif?: { width?:number; height?:number; createdAt?:string };
  hash?: string;
  updatedAt: string;
  updatedBy: string;
};
```

## 12) UX Notes

- Left pane: root tree, pointer folders marked with an icon (link badge).
- Grid: dense, consistent cell sizes; hover shows filename + quick “copy URL”.
- Inspector: big preview, tags (token input), notes (autosave on blur), EXIF table, source URL (copy button).
- Search: simple bar; tokens match filename/tags/notes with highlighting.

## 13) Tauri Plug-in Space (not implemented now)

Define an interface the browser already uses; Tauri can later implement it:

```ts
interface HostBridge {
  readDir(path:string): Promise<DirEntry[]>;
  readFile(path:string, range?:[number,number]): Promise<ArrayBuffer>;
  writeFile(path:string, data:ArrayBuffer|string): Promise<void>;
  watch?(path:string, cb:(ev:FsEvent)=>void): Unsubscribe;
}
```

Swap the HTTP provider for a Tauri provider; the UI code doesn’t care.

## 14) Security

- S3: Assume IAM role with list/get/put scoped to prefixes; presign PUT for sidecars/thumbs.
- Client: never handles long-lived creds; only presigned URLs or backend tokens.
- Local: user-granted FS handles; no background access.

## 15) Risks & Mitigation

- **Missing thumbs → sluggish grid:** pre-generate via worker; on-demand generation throttled.
- **Large manifests:** paginate `_index.json` by directory; stream lists.
- **Browser storage limits:** keep OPFS under user-set cap (e.g., 512 MB) with LRU eviction.
- **Pointer loops:** detect visited targets; break with a clear error.

## 16) Success Metrics

- p75 TTFG hot <700 ms; cold <2.0 s.

- p95 scroll dropped frames <1.5%.

- > 90% of inspector opens under 150 ms.

- > 85% thumb cache hit after first pass.

- Worker backlog SLA: new files thumbed + indexed within 2 minutes.

## 17) Implementation Order (so nobody “explores” for 3 weeks)

1. **Read root + config → render tree**
2. **Fetch `_index.json` → grid (virtualized) w/ existing thumbs**
3. **Inspector (read sidecar, edit tags/notes → PUT)**
4. **Search (reads `_rollup.json`)**
5. **On-demand thumb generation endpoint**
6. **Python indexer & nightly rollup builder**
7. **Retry/merge logic for sidecar conflicts**
8. **Perf passes (preload, cancelation, contain/visibility)**