# Lenslet Architecture Overview (2025-12-28)

This document captures how Lenslet (formerly “lenslet-lite”) is structured today and highlights natural extension points for adding metrics-based functionality (filtering, sorting, visualization, and external metric inference).

## High-level system
- **Backend**: FastAPI app (`src/lenslet/server.py`) that serves an image gallery API plus the bundled frontend.
- **Storage layer**: In-memory caches over a read-only filesystem; optional dataset mode for programmatic launches.
- **Frontend**: React + Vite single-page app (`frontend/` source, bundled into `src/lenslet/frontend/`). Uses React Query for data fetching/caching and Tailwind-style utility classes for styling.
- **Runtime options**: CLI (`lenslet`) for local folders; Python API (`lenslet.launch`) for dataset mode; both expose the same HTTP surface.

## Backend details

### Entry points
- `src/lenslet/cli.py`: CLI parser; starts Uvicorn with `create_app`.
- `src/lenslet/api.py`: Notebook/programmatic launcher; starts `create_app_from_datasets` (dataset mode) either blocking or in a subprocess.
- `src/lenslet/server.py`: FastAPI factory functions.

### Storage abstractions
- `storage/base.py`: `Storage` protocol defining read/list/etag/etc.
- `storage/local.py` (read-only): Path resolution with traversal protection; basic file ops; never writes to source tree.
- `storage/memory.py`: Wraps `LocalStorage`, caches indexes, thumbnails, dimensions, and sidecar-like metadata entirely in RAM. Key responsibilities:
  - **Indexing**: Builds `CachedIndex` (files + dirs) lazily per folder; filters hidden/_ files; tracks `mtime`/size; guesses MIME; dimensions lazily filled via lightweight header reads.
  - **Thumbnails**: Generates WebP thumbs on demand, caches bytes and dimensions.
  - **Metadata**: Stores tags/notes/star in memory only; no disk writes.
  - **Search**: Simple in-memory search over cached items, scoped by path, matching name/tags/notes; limit applies.
  - **Cache invalidation**: Per-path or subtree; root clears all.
- `storage/dataset.py`: Alternative storage for “dataset mode” (pre-specified lists of image paths/S3 URIs). Shares the same interface as memory storage but reads from provided datasets.

### FastAPI surfaces (`create_app` / `create_app_from_datasets`)
- **Middleware**: attaches storage instance per request.
- **Routes**:
  - `GET /health`: basic mode info.
  - `GET /folders?path=/...`: returns `FolderIndex` (items, dirs, timestamps).
  - `POST /refresh`: invalidates subtree (no disk writes).
  - `GET /item?path=...`: returns sidecar-style metadata (tags/notes/star, dimensions).
  - `PUT /item`: updates sidecar metadata in memory (session-only).
  - `GET /thumb`: returns WebP thumbnail bytes.
  - `GET /file`: returns original file bytes.
  - `GET /metadata`: PNG-only metadata reader (uses `metadata.read_png_info`).
  - `GET /search?q=...&path=...`: in-memory search results.
- **Static frontend**: mounts `src/lenslet/frontend/` (rebuilt bundle) at `/`.

### Notable constraints
- Read-only to the source image directory; all writes are in-memory.
- Thumbnail and metadata lifetimes are tied to process; no persistence.
- Sorting/searching happen client-side using server-provided lists; server returns unsorted folder listings.

## Frontend details

### Tech stack
- React + TypeScript + Vite.
- React Query for data fetching (`useFolder`, `useSearch`).
- Custom hooks/utilities for debouncing, layout, blob caches (`fileCache`, `thumbCache`), and keyboard handling.

### Core flow (AppShell)
- `AppShell` orchestrates:
  - Current folder path (from URL hash), search query, selection, viewer state, zoom.
  - Sort state (`SortKey`: added/name/random; `SortDir`: asc/desc) and random seed to reshuffle.
  - Star filters and view mode (grid/adaptive), grid item sizing, sidebar visibility.
  - Local star overrides to reflect optimistic mutations.
  - Persists UI prefs to `localStorage`.
  - Applies filters and sort (`applyFilters`, `applySort`) on merged data from either folder listing or search results.
  - Updates `document.title` to a short path-based label for tab differentiation.

### Data pipeline
- **Fetching**: `useFolder` hits `/folders`; `useSearch` hits `/search`; results cached briefly.
- **Sorting/filtering**: Client-only; sorters in `features/browse/model` (`sortByAdded`, `sortByName`, plus random shuffle with seed). Filters by star rating.
- **Display**: `VirtualGrid` renders tiles; `Viewer` handles lightbox with zoom/navigation; `Inspector` shows metadata, rating, tags/notes editing (sends `PUT /item`).
- **Uploads**: Drag/drop upload allowed only when folder has no subdirs; uses `api.uploadFile`.
- **Prefetch**: Neighboring thumbnails/files prefetched for smoother viewer navigation.

### UI components of note
- `Toolbar`: controls view mode, sort key/dir, rating filters, grid size, search, sidebar toggles, viewer navigation.
- `FolderTree`: left sidebar navigation; context menu supports refresh/export/trash.
- `Inspector`: right sidebar with metadata editing, star ratings, and export shortcuts.
- `ContextMenu`: shared menu used by tree/grid selections.

## Extension points for metrics
These are natural seams to add metric-aware features:
- **Backend data model**: Extend `Item` schema (server + frontend types) to include metrics (e.g., `metrics: dict[str, float]` or a typed set of known keys). Persisted? Currently in-memory; consider a lightweight sidecar or external store.
- **Storage**: `MemoryStorage`/`DatasetStorage` would need to ingest metrics from:
  - Embedded sidecars (JSON alongside images),
  - External metrics service (pull on demand + cache),
  - Preloaded dataset descriptors.
- **API surface**:
  - Filtering/sorting parameters: add query params to `/folders` (e.g., `metric=psnr&dir=desc`) or keep server simple and return metrics for client-side sort/filter (consistent with current model).
  - Metrics inference route: e.g., `POST /metrics/infer` delegating to a metric server and caching results.
  - Distribution endpoint: e.g., `GET /metrics/histogram?metric=psnr&path=/...`.
- **Frontend state**:
  - Extend `SortKey` to include metric keys (dynamic list).
  - Add filter controls (range sliders, top-N percentiles) and distribution UI (histograms).
  - Show per-item metric chips in grid/list and inspector.
  - Decide on client vs. server sorting: current client-only pipeline can sort any numeric field if data is present; for large folders, server-side pagination/sort may be required.
- **Caching**: Metrics fetched/inferred should be cached alongside thumbnails/metadata (in memory today; optional persistence later).

## Current limitations to keep in mind
- No persistence across restarts (thumbnails, metadata, would include metrics).
- No pagination; large folders are fetched and sorted client-side.
- Search is simple substring over name/tags/notes; metrics aren’t searchable yet.
- Only PNG metadata is parsed on the backend; other formats ignored.
- Writes (tags/notes/star) are session-only.

## Suggested discussion topics for metrics expansion
- Data source and trust: where do metrics come from (sidecars, model inference, external DB)?
- Consistency model: eventual vs. strong (can UI show stale metrics?).
- Performance: server-side pagination/sorting vs. current client-only approach for large datasets.
- Schema evolution: typed metrics vs. arbitrary key/value; how to expose in API without breaking clients.
- Storage: remain in-memory or add lightweight persistence (SQLite/Parquet per folder).
- UI: which charts and filters give most value (histograms, scatter plots, thresholds, percentile bands).
