# Lenslet

A lightweight image gallery server for fast visual triage. Point it at a directory or a Parquet table and browse instantly in your browser. Lenslet keeps the source images read-only and stores workspace state separately.

## Introduction

<img width="1955" height="1066" alt="image" src="https://github.com/user-attachments/assets/a4509d0a-a4cf-4219-8f68-61e5f6610938" />
<img width="1955" height="1066" alt="image" src="https://github.com/user-attachments/assets/92a2d580-c16e-4f7c-b79a-addab0213512" />

Lenslet is a self-contained image gallery server designed for simplicity and speed. It indexes directories on-the-fly, generates thumbnails on demand, and serves everything through a clean web interface. Perfect for quickly browsing local image collections or large Parquet-backed datasets without modifying the source images.

## Features

- **Workspace-aware**: Persists UI state (Smart Folders/views) and optional thumbnail cache under `.lenslet/` (or `<parquet>.lenslet.json`)
- **Read-only sources**: Never writes into your image directories or S3 buckets
- **Local + S3 + HTTP**: Mix local files, `s3://` URIs, and URLs with smart source parsing
- **Metrics & filtering**: Sort/filter by numeric metrics from Parquet (histograms + range brushing)
- **Embedding similarity**: Find similar images from fixed-size list embeddings (cosine; optional FAISS acceleration)
- **Labels & export**: Tag, rate, and annotate items, then export metadata as JSON or CSV
- **Single command**: Just point to a directory or Parquet file and go

## Touch + Mobile Controls

- Tap-first browse flow: on touch devices, tap once to select and tap the selected item again to open the viewer.
- Explicit actions on touch: grid and folder action buttons are visible on coarse pointers; right-click still works on desktop.
- Mobile select mode: use the `Select`/`Done` toggle in the narrow-screen toolbar drawer to multi-select without Shift/Ctrl keys.
- Viewer navigation at phone widths: next/previous controls remain available on narrow screens (including in-viewer controls at very small widths).

## Installation

```bash
pip install lenslet
```

Optional extras for embedding search:

```bash
# NumPy-only similarity search
pip install "lenslet[embeddings]"

# FAISS-accelerated similarity search (CPU)
pip install "lenslet[embeddings-faiss]"
```

## Usage

### Command Line Interface

```bash
lenslet /path/to/images
```

Then open the URL printed in the terminal (default http://127.0.0.1:7070, or the next available port).

**Options:**

```bash
lenslet <directory|table.parquet|org/dataset|s3://.../table.parquet> [options]

Options:
  -p, --port PORT              Port to listen on (default: 7070; auto-increment if in use)
  -H, --host HOST              Host to bind to (default: 127.0.0.1)
  --thumb-size SIZE            Thumbnail short edge in pixels (default: 256)
  --thumb-quality QUALITY      Thumbnail WebP quality 1-100 (default: 70)
  --source-column NAME         Column to load image paths from in table mode
  --base-dir PATH              Base directory for resolving relative paths in table mode
  --no-cache-wh                Disable caching width/height back into parquet
  --no-skip-indexing           Probe image dimensions during table load
  --no-thumb-cache             Disable thumbnail cache when a workspace is available
  --no-og-preview              Disable dataset-based social preview image
  --no-write                   Use a temp workspace under /tmp/lenslet (keeps source read-only)
  --embedding-column NAME      Embedding column name (repeatable, comma-separated allowed)
  --embedding-metric NAME:METRIC
                               Embedding metric override (repeatable)
  --embedding-preload          Preload embedding indexes on startup
  --embedding-cache            Enable embedding cache (default)
  --no-embedding-cache         Disable embedding cache
  --embedding-cache-dir PATH   Override embedding cache directory
  --embed                      Run CPU embedding inference on a parquet file before launch
  --batch-size SIZE            Embedding inference batch size (used with --embed)
  --parquet-batch-size SIZE    Rows per parquet batch (used with --embed)
  --num-workers N              Parallel image loading workers (used with --embed)
  --reload                     Enable auto-reload for development
  --share                      Create a public share URL via cloudflared
  --verbose                    Show detailed server logs
  -v, --version                Show version and exit
```

**Examples:**

```bash
# Serve images from your Pictures folder
lenslet ~/Pictures

# Use a custom port
lenslet ~/Photos --port 8080

# Make accessible on local network
lenslet ~/Images --host 0.0.0.0 --port 7070

# Create a public share URL (prints a trycloudflare.com link)
lenslet ~/Images --share

# Start from a Parquet workspace (paths can be local, s3://, or https://)
lenslet /data/items.parquet --source-column image_path --base-dir /data

# Start from a folder containing items.parquet
lenslet /data/dataset --source-column image_path

# Start from a Hugging Face dataset repo (org/dataset)
lenslet incantor/dit03-twitter-niji7-5k-filtering-metrics --share

# Start from a remote Parquet file
lenslet s3://my-bucket/items.parquet --source-column image_path

# Add embeddings to a local Parquet file before launching
lenslet /data/items.parquet --source-column image_path --embed
```

### Embedding Similarity Search

Lenslet auto-detects fixed-size list embedding columns in `items.parquet` (or you can force them with `--embedding-column`). The UI exposes a "Find similar" action, and the API supports path-based or base64 vector queries.

```bash
# Search by selected image path
curl -X POST http://127.0.0.1:7070/embeddings/search \
  -H "Content-Type: application/json" \
  -d '{"embedding":"clip","query_path":"/images/cat.jpg","top_k":50,"min_score":0.2}'
```

```python
# Encode a float32 vector (little-endian) for query_vector_b64
import base64
import numpy as np

vec = np.asarray([0.1, 0.2, 0.3], dtype="<f4")
payload = base64.b64encode(vec.tobytes()).decode("ascii")
```

Embedding caches live under `.lenslet/embeddings_cache/` (or `<parquet>.cache/embeddings_cache/`) unless you override with `--embedding-cache-dir`.

For a one-shot embedding write without launching Lenslet, run:

```bash
python scripts/embed_parquet_embeddings.py /data/items.parquet --image-column image_path
```

### Programmatic API (Python/Jupyter)

Launch lenslet directly from Python code or notebooks:

```python
import lenslet

datasets = {
    "my_images": ["/path/to/img1.jpg", "/path/to/img2.jpg"],
    "more_images": [
        "s3://bucket/img3.jpg",           # S3 URIs
        "https://example.com/img4.jpg",   # HTTP/HTTPS URLs
    ],
}

# Launch in non-blocking mode (returns immediately)
lenslet.launch(datasets, blocking=False, port=7070)
```

**Key Features:**
- 🚀 **Jupyter-friendly**: Non-blocking mode for notebooks
- ☁️ **S3 support**: Automatically handles S3 URIs via presigned URLs
- 📁 **Multiple datasets**: Organize images into named collections
- 🔗 **Mixed sources**: Combine local files, S3 URIs, and HTTP URLs

See [Programmatic API Documentation](docs/PROGRAMMATIC_API.md) for details and examples.

## Module Map (Post-Refactor Baseline)

The refactor keeps public interfaces stable while moving domain logic behind explicit module boundaries.

Backend facade and route/runtime modules:

- `src/lenslet/server.py` - stable public facade (`create_app*`, compatibility touchpoints).
- `src/lenslet/server_runtime.py` - shared runtime assembly (`AppRuntime`, runtime wiring).
- `src/lenslet/server_browse.py` - folder traversal and browse path helpers.
- `src/lenslet/server_factory.py` - app factory composition.
- `src/lenslet/server_routes_common.py` - folders/item/metadata/export/events/thumb/file/search routes.
- `src/lenslet/server_routes_presence.py` - presence lifecycle, diagnostics, and prune wiring.
- `src/lenslet/server_routes_embeddings.py` - embeddings routes.
- `src/lenslet/server_routes_views.py` - views routes.
- `src/lenslet/server_routes_index.py` - index/static shell routes.
- `src/lenslet/server_routes_og.py` - OG preview route wiring.
- `src/lenslet/server_media.py` - media/file/thumb response helpers.
- `src/lenslet/server_sync.py` - collaboration event broker and presence tracker internals.

Table storage facade and collaborators:

- `src/lenslet/storage/table.py` - `TableStorage` compatibility facade.
- `src/lenslet/storage/table_facade.py` - delegated read/search/metadata/presign operations.
- `src/lenslet/storage/table_schema.py` - source column and schema coercion logic.
- `src/lenslet/storage/table_paths.py` - path/source resolution and safety checks.
- `src/lenslet/storage/table_index.py` - index-build pipeline (`build_index_columns`, `scan_rows`, `assemble_indexes`).
- `src/lenslet/storage/table_probe.py` - remote header/dimension probing helpers.
- `src/lenslet/storage/table_media.py` - local media dimension/thumbnail helpers.

Frontend decomposition seams:

- `frontend/src/app/AppShell.tsx` + domain hooks under `frontend/src/app/hooks/`.
- `frontend/src/app/model/appShellSelectors.ts` for pure AppShell selectors.
- `frontend/src/features/inspector/Inspector.tsx` + `sections/`, `hooks/`, and `model/metadataCompare.ts`.
- `frontend/src/features/metrics/MetricsPanel.tsx` + split `components/`, `hooks/`, and `model/` (`histogram.ts`, `metricValues.ts`).

## Maintainer Workflows

Run the fixed acceptance matrix from repo root:

```bash
python scripts/lint_repo.py
pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py
python - <<'PY'
import lenslet.server as server
import lenslet.storage.table as table
assert hasattr(server, 'create_app')
assert hasattr(server, 'create_app_from_datasets')
assert hasattr(server, 'create_app_from_table')
assert hasattr(server, 'create_app_from_storage')
assert hasattr(server, 'HotpathTelemetry')
assert hasattr(server, '_file_response')
assert hasattr(server, '_thumb_response_async')
assert hasattr(server, 'og')
assert hasattr(table, 'TableStorage')
assert hasattr(table, 'load_parquet_table')
assert hasattr(table, 'load_parquet_schema')
print('import-contract-ok')
PY
cd frontend
npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts
npx tsc --noEmit
cd ..
python -m build
```

For browser-level large-tree performance checks (40k images across 10k folders), install Chromium once and run:

```bash
python -m playwright install chromium
python scripts/playwright_large_tree_smoke.py \
  --dataset-dir data/fixtures/large_tree_40k \
  --output-json data/fixtures/large_tree_40k_smoke_result.json
```

After frontend changes, ship deterministic packaged assets:

```bash
cd frontend && npm run build && cd ..
rsync -a --delete frontend/dist/ src/lenslet/frontend/
```

## Hotpath API Notes (2026-02)

- `GET /folders?recursive=1` returns the full list in a single response; pagination params are ignored and page metadata is `null`.
- `legacy_recursive=1` is accepted but no longer changes the recursive response shape.
- `GET /file` now streams local file-backed sources and falls back to byte responses for non-local/remote sources.
- Full-file prefetch is restricted to viewer/compare contexts and sends `x-lenslet-prefetch: viewer|compare`.
- `GET /health` exposes hotpath runtime counters/timers under `hotpath.counters` and `hotpath.timers_ms`.

### Deferred Performance Backlog

The following items are intentionally deferred from the hotpath sprint:
- Indexed search path to replace O(N) in-memory scans.
- Folder tree virtualization/flattening for very large trees.
- Configurable or batched label persistence writes.

## Notes

- **Workspace files**: `.lenslet/views.json` stores Smart Folders; optional thumbnail cache lives under `.lenslet/thumbs/`
  - For Parquet, views live at `<table>.lenslet.json` and thumbs at `<table>.cache/thumbs/`
  - With `--no-write`, workspace files go under `/tmp/lenslet/<dataset-hash>/` instead
- **Embedding cache**: `.lenslet/embeddings_cache/` (or `<table>.cache/embeddings_cache/`) stores cached embedding indexes
- **Read-only sources**: The server never writes into your image directories or S3 buckets
- **Labels**: Tags/notes/ratings are editable in the UI (session-only) and exportable as JSON/CSV
- **No-write mode**: Pass `--no-write` to keep the dataset read-only; caches and views are stored under `/tmp/lenslet/<dataset-hash>/` (thumbnail cache capped at 200 MB)
- **Formats**: Supports JPEG, PNG, and WebP
- **Hidden files**: Files/folders starting with `.` are ignored

## License

MIT License
