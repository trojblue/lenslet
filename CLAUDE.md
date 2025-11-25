# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lenslet is a minimal, fast, boring (on purpose) gallery system with a React frontend and FastAPI backend. It uses flat file storage (local/S3) with no database, storing metadata in JSON sidecars next to images.

**Core Architecture:**
- **Frontend:** React + TanStack Query/Virtual + minimal CSS (no global state, UI kits, or CSS-in-JS)
- **Backend:** FastAPI + flat file storage (local/S3) + async workers
- **Storage:** No database - JSON manifests (`_index.json`) + sidecars (`.json`) + thumbnails (`.thumbnail`)

## Common Development Commands

### Frontend (lenscat-lite/)

```bash
# Install dependencies
npm install

# Development server (runs on http://localhost:5173)
npm run dev

# Production build
npm run build

# Preview production build
npm run preview
```

**Environment:** Create `.env.local` with:
```
VITE_API_BASE=http://localhost:7070/api
```

### Backend (lenscat-backend/)

```bash
# Install dependencies (from project root with pyproject.toml)
cd lenscat-backend
pip install -e .

# Start backend server (runs on http://127.0.0.1:7070)
uvicorn src.lenscat_backend.main:app --reload --host 127.0.0.1 --port 7070

# Or use the Python module directly
python -m src.lenscat_backend.main
```

**Environment:** Backend uses `.env` with:
```
ROOT_PATH=./data
S3_BUCKET=
S3_PREFIX=
AWS_REGION=
S3_ENDPOINT=
THUMB_LONG_EDGE=256
THUMB_QUALITY=70
```

### Running Full Stack

1. **Backend first:** `cd lenscat-backend && uvicorn src.lenscat_backend.main:app --reload --host 127.0.0.1 --port 7070`
2. **Frontend:** `cd lenscat-lite && npm run dev`

### Single-Port Deployment

Build frontend and serve via backend:
```bash
cd lenscat-lite && npm run build
cd ../lenscat-backend
FRONTEND_DIST=../lenscat-lite/dist uvicorn src.lenscat_backend.main:app --host 0.0.0.0 --port 7070
```

## Code Architecture

### Backend Structure (lenscat-backend/src/lenscat_backend/)

- **`main.py`**: FastAPI app, CORS, storage initialization, route registration
- **`config.py`**: Settings via environment variables (dataclass-based)
- **`models.py`**: Pydantic models for API contracts
- **`routes/`**: API endpoints
  - `folders.py`: List folder contents (`GET /api/folders`)
  - `items.py`: Get/update item metadata (`GET/PUT /api/item`)
  - `thumbs.py`: Get/generate thumbnails (`GET/POST /api/thumb`)
  - `search.py`: Search items (`GET /api/search`)
  - `files.py`: Serve original files
- **`storage/`**: Storage abstractions
  - `base.py`: Abstract storage interface
  - `s3.py`: S3 implementation (aioboto3)
  - `local.py`: Local filesystem implementation
- **`utils/`**: Utilities
  - `exif.py`: EXIF extraction (Pillow)
  - `hashing.py`: BLAKE3 hashing
  - `jsonio.py`: JSON serialization (orjson)
- **`workers/`**: Background workers for indexing/thumbnails

**Storage Dependency Injection:** STORAGE singleton is injected via middleware into `request.state.storage`

### Frontend Structure (lenscat-lite/src/)

- **`main.tsx`**: Entry point
- **`App.tsx`**: Root component with QueryClientProvider
- **`app/`**: App-level components
  - `AppShell.tsx`: Main layout shell
  - `menu/ContextMenu.tsx`: Context menu component
- **`features/`**: Feature-based modules
  - `browse/`: Grid browsing
    - `components/VirtualGrid.tsx`: Virtualized grid (TanStack Virtual)
    - `components/ThumbCard.tsx`: Thumbnail cards
  - `folders/FolderTree.tsx`: Folder navigation tree
  - `inspector/Inspector.tsx`: Image inspector/metadata editor
  - `viewer/Viewer.tsx`: Full-size image viewer
- **`shared/`**: Shared UI components
  - `ui/Toolbar.tsx`: Toolbar component
- **`api/`**: API client and TanStack Query hooks
- **`lib/`**: Utilities and types
- **`styles.css`**: Main styles (Eagle-inspired dark theme)
- **`theme.css`**: Theme variables

**State Management:** TanStack Query for server state + local component state only. No Redux or global stores.

### Folder Model

The system supports recursive hierarchies:

- **Branch folders**: Contain only subfolders (no images)
- **Leaf folders**: Either real (contains images) or pointer (contains `.lenscat.folder.json` pointing to S3/local)
- **Mixed leaf/branch is invalid**: Throw error and show red badge in UI

### File Conventions

For image `foo.webp`:
- **Sidecar metadata**: `foo.webp.json` - tags, notes, EXIF, hash, timestamps
- **Thumbnail**: `foo.webp.thumbnail` - WebP, ≤256px long edge, quality ~70

Folder-level files:
- **`_index.json`**: Folder manifest (items, dirs, metadata)
- **`_rollup.json`**: Search index at root
- **`.lenscat.folder.json`**: Pointer folder config

### API Endpoints

- `GET /api/folders?path=<path>` - List folder contents
- `GET /api/item?path=<path>` - Get item metadata
- `PUT /api/item?path=<path>` - Update item metadata (sidecars)
- `GET /api/thumb?path=<path>` - Get/generate thumbnail
- `POST /api/thumb?path=<path>` - Force regenerate thumbnail
- `GET /api/search?q=<query>` - Search items (filename/tags/notes)
- `GET /api/files?path=<path>` - Serve original file
- `GET /health` - Health check

## Development Philosophy

**Core principles from dev_notes/Developer_note.md:**

1. **Do the simplest thing that works** - No RxJS, DI containers, or clever wrappers for basic tasks
2. **Fail fast, fail loud** - Throw early with exact context, surface errors in UI
3. **Zero clever wrappers** - Use the platform until it hurts, then add thinnest layer possible
4. **Data > code** - Store rules/config in JSON files, code reads data
5. **Sidecar is the source** - Metadata lives next to images, browser cache is disposable

### Key Constraints

- **Supported formats only:** JPEG, PNG, WebP (no HEIC)
- **No local secrets/state:** Tags/notes write immediately to sidecars
- **No database:** All state in JSON + files for MVP
- **Max PR size:** ~400 lines net change

### Performance Budgets

- **Time to first grid (TTFG):** < 700ms hot, < 2s cold
- **Scroll performance:** < 1.5% dropped frames
- **Inspector open:** < 150ms
- **Thumbnail cache hit:** > 85% after first browse

**Performance techniques:**
- Virtualize grid with fixed cell geometry (no masonry in v0)
- Pre-sized thumbnails only in grid (`.thumbnail` files)
- `content-visibility: auto` + `contain-intrinsic-size` on grid items
- Only animate `transform`/`opacity` (no layout properties)
- Batch by folder, AbortController for offscreen loads, prefetch one row ahead
- EXIF/parse/JSON I/O in workers (Web Workers frontend, Python workers backend)

### Dependencies

**Frontend (minimal):**
- React, TanStack Query, TanStack Virtual
- NO: moment.js, lodash, UI kits, Redux, runtime CSS-in-JS

**Backend (minimal):**
- FastAPI, uvicorn, aioboto3, boto3, orjson, blake3, Pillow
- NO: PostgreSQL, ORM, heavy frameworks

**Before adding a dependency:**
- Can native APIs do it in ≤20 lines? Do that instead
- Is it tree-shakeable and <10KB gzipped?
- Does it force unwanted patterns (global stores, decorators)?

### Error Handling

- **Hard invariants → throw:** Mixed leaf/branch, pointer loops, missing permissions
- **User-facing banner** with exact path + action suggestions
- **Logs:** Include `sourceId`, `path`, `op`, `etag/hash`, `user`, `ts` (no stack traces in UI)

### Code Style

**Python:**
- Use ruff + black + mypy (if configured)
- Functions < 50 lines, modules < 300 lines
- Boring, explicit naming (`buildFolderManifest`, not `scry`)

**TypeScript:**
- eslint with strict mode, no `any`
- Components < 200 lines, hooks < 80 lines
- Boring, explicit naming

**Comments:** Focus on "why" not "what". Link to decisions/rationale if non-obvious.

## Important Notes

### Sidecar Sync Rules

- **Source of truth:** Sidecar next to the image
- **Last-writer-wins** on notes using `updatedAt` timestamp
- **Set-merge** on tags (additive)
- Client sends `If-Match` with ETag, fetch latest on mismatch, merge, retry PUT

### Avoid These Footguns

- Ad-hoc caching without invalidation → always key by `(path, etag/hash, variant)`
- Animating box-shadow/border on 2,000 elements → jank
- Recursive folder walkers without cycle detection in pointer configs
- Writing local-only notes (not allowed - must write to sidecars)
- Batching optimizations that delay first paint (first paint > perfect batching)

### Testing

- **Unit:** Pointer resolution, leaf/branch validation, sidecar merge
- **Integration (backend):** S3 list → manifest → search
- **Smoke (frontend):** Load 10k-item fixture; assert TTFG < 2s; scroll without jank

## When to Add Abstractions

**Likely OK patterns (≤40 lines each):**
- Abortable fetch helper (~20 lines)
- Queue with concurrency for thumbnail preloads (≤40 lines)
- Guard utils: `isLeaf`, `isPointer`, `assertBranch` (≤10 lines each)
- Retry with jitter for flaky S3 GETs (≤15 lines)

**NOT OK:**
- 100-line "unified fetch abstraction" for two endpoints
- Global state management before actually needing it
- Helpers/utilities for one-time operations
- Abstractions for hypothetical future requirements

Three similar lines of code is better than a premature abstraction.
