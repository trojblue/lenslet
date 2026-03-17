# Lenslet

A lightweight image gallery server for fast visual triage. Point it at a directory or a Parquet table and browse instantly in your browser. Lenslet keeps the source images read-only and stores workspace state separately.

## Introduction

<img width="2148" height="1207" alt="image" src="https://github.com/user-attachments/assets/920463b1-3a91-44eb-bf90-85e426cf7357" />
<img width="2148" height="1207" alt="image" src="https://github.com/user-attachments/assets/c2a743ea-72d1-4b32-bc4a-ef7146f88ddf" />

Lenslet is a self-contained image gallery server designed for simplicity and speed. It indexes directories on-the-fly, generates thumbnails on demand, and serves everything through a clean web interface. Perfect for quickly browsing local image collections or large Parquet-backed datasets without modifying the source images.

## Features

- **Workspace-aware**: Persists UI state (Smart Folders/views) and optional thumbnail cache under `.lenslet/` (or `<parquet>.lenslet.json`)
- **Workspace themes**: Browse mode supports `Original`, `Teal`, and `Charcoal` presets persisted per workspace, with matching dynamic tab favicon accents
- **Read-only sources**: Never writes into your image directories or S3 buckets
- **Local + S3 + HTTP**: Mix local files, `s3://` URIs, and URLs with smart source parsing
- **Metrics & filtering**: Sort/filter by numeric metrics from Parquet (histograms + range brushing)
- **Embedding similarity**: Find similar images from fixed-size list embeddings (cosine; optional FAISS acceleration)
- **Labels & export**: Tag, rate, and annotate items, then export metadata as JSON or CSV
- **Ranking mode (MVP)**: Launch `lenslet rank <dataset.json>` for per-instance ranking with autosave/resume
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

Tested source install for the pinned Python 3.13 runtime stack used in this repo:

```bash
python -m pip install -c constraints/runtime-py313.txt -e .
python -m pip install -c constraints/runtime-py313.txt -e ".[dev]"
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

### Ranking Mode (MVP)

Run ranking mode with a dataset JSON:

```bash
lenslet rank /path/to/ranking_dataset.json --port 7071
```

`rank` options:

```bash
lenslet rank <dataset.json> [options]

Options:
  -p, --port PORT              Port to listen on (default: 7070; auto-increment if in use)
  -H, --host HOST              Host to bind to (default: 127.0.0.1)
  --reload                     Enable auto-reload for development
  --results-path PATH          Optional JSONL results path (relative to dataset JSON directory)
```

Dataset JSON shape:

```json
[
  {
    "instance_id": "example-1",
    "images": ["images/a.jpg", "images/b.jpg", "images/c.jpg"]
  },
  {
    "instance_id": "example-2",
    "images": ["/abs/path/x.jpg", "/abs/path/y.jpg"]
  }
]
```

Ranking mode constraints and semantics:

- Image paths are local filesystem paths only (absolute or relative to dataset JSON location).
- Each instance must have a unique non-empty `instance_id` and a non-empty `images` array.
- Saves are append-only JSONL entries. Default results path is `<dataset_dir>/.lenslet/ranking/<dataset_stem>.results.jsonl`.
- Results path must not point inside a served image directory; override with `--results-path` if needed.
- Resume index is deterministic: `last_completed_instance_index + 1`, wrapping to `0` when all are complete.
- `GET /rank/export` collapses to latest-per-instance entries; `completed_only=true` filters to completed items only.

Ranking mode interaction (current):

- Layout is split into a larger top `Unranked` workspace and bottom rank buckets (`1`, `2`, `3`, ...).
- Desktop mouse pointers can drag a splitter between top and bottom sections; narrow/coarse-pointer layouts use a fixed stacked layout.
- Board hotkeys: `1-9` assign focused image to rank and auto-advance to next unranked image in initial dataset order, `ArrowLeft/ArrowRight` move selection, `q/e` navigate previous/next instance, and `Enter` opens fullscreen.
- Fullscreen hotkeys: `a/d` navigate previous/next image in initial order, `1-9` assign rank for current fullscreen image, and `Escape` closes fullscreen while restoring board focus to that image.
- `Backspace` no longer performs instance navigation.

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

Launch Lenslet directly from Python code or notebooks.

Use `lenslet.launch(...)` for named dataset maps:

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

Use `lenslet.launch_table(...)` for a single table-like payload:

```python
import lenslet

rows = [
    {"path": "gallery/a.jpg", "source": "/data/gallery/a.jpg"},
    {"path": "gallery/b.jpg", "source": "/data/gallery/b.jpg"},
]

lenslet.launch_table(rows, blocking=False, port=7070, base_dir="/data")
```

**Key Features:**
- 🚀 **Jupyter-friendly**: Non-blocking mode for notebooks
- ☁️ **S3 support**: Automatically handles S3 URIs via presigned URLs
- 📁 **Multiple datasets**: Organize images into named collections
- 🔗 **Mixed sources**: Combine local files, S3 URIs, and HTTP URLs

The dataset and table launch paths are now explicit, so table-only options such as `source_column` and `base_dir` live on `launch_table(...)` instead of the dataset launcher.

## Module Map (Post-Refactor Baseline)

The current architecture keeps a small public entry surface and pushes mode-specific behavior into server, storage, and ranking subdomains.

Backend entrypoints and runtime assembly:

- `src/lenslet/server.py` - public import facade for app builders and a few compatibility helpers.
- `src/lenslet/server_factory.py` - browse-mode app construction for directory, table, and pre-built storage launches.
- `src/lenslet/server_runtime.py` - runtime collaborator assembly (`AppRuntime`, caches, broker, snapshotter).
- `src/lenslet/server_context.py` - request/app context wiring.
- `src/lenslet/server_browse.py` - browse payload building, folder traversal, and search helpers.
- `src/lenslet/server_media.py` - file and thumbnail response helpers.
- `src/lenslet/server_sync.py` - metadata patching, SSE event broker, and presence state internals.

Route modules:

- `src/lenslet/server_routes_common.py` - folders, search, metadata, export, file, thumb, and event routes.
- `src/lenslet/server_routes_presence.py` - presence join/move/leave lifecycle and diagnostics.
- `src/lenslet/server_routes_views.py` - workspace view persistence routes.
- `src/lenslet/server_routes_embeddings.py` - embedding discovery and similarity search routes.
- `src/lenslet/server_routes_index.py` - frontend shell mounting and OG tag injection.
- `src/lenslet/server_routes_og.py` - OG image generation and cache wiring.

Storage backends and collaborators:

- `src/lenslet/storage/base.py` - shared browse/storage protocols and contract helpers.
- `src/lenslet/storage/local.py` - filesystem-backed read-only primitives.
- `src/lenslet/storage/memory.py` - local browse storage with in-memory indexes, thumbs, and metadata.
- `src/lenslet/storage/source_backed.py` - shared dataset/table behavior for source-backed media.
- `src/lenslet/storage/table.py` - table-backed browse storage.
- `src/lenslet/storage/dataset.py` - in-memory dataset-map browse storage for the programmatic API.
- `src/lenslet/storage/table_schema.py` - source-column detection and schema coercion.
- `src/lenslet/storage/table_paths.py` - logical-path derivation and local-path safety checks.
- `src/lenslet/storage/table_index.py` - table row scan and index assembly pipeline.
- `src/lenslet/storage/table_probe.py` - remote header and dimension probing.
- `src/lenslet/storage/table_media.py` - media sniffing and dimension extraction.

Other backend domains:

- `src/lenslet/workspace.py` - workspace paths, persisted views, snapshots, and labels log helpers.
- `src/lenslet/browse_cache.py`, `src/lenslet/thumb_cache.py`, `src/lenslet/og_cache.py` - browse, thumbnail, and OG cache layers.
- `src/lenslet/indexing_status.py` and `src/lenslet/preindex.py` - indexing lifecycle and local preindex support.
- `src/lenslet/ranking/` - ranking-mode backend, persistence, validation, and CLI helpers.

Frontend decomposition seams:

- `frontend/src/app/` - top-level shell, routing mode, presence sync, and layout state.
- `frontend/src/api/` - browser API client, SSE wiring, and request-budget helpers.
- `frontend/src/features/browse/` - grid, filters, folder navigation, and browse-state model.
- `frontend/src/features/inspector/` - inspector sections, compare/export actions, and metadata diffing.
- `frontend/src/features/ranking/` - ranking-mode board and session state.
- `frontend/src/shared/` and `frontend/src/theme/` - shared UI primitives, hooks, and theme persistence.

## Maintainer Workflows

Run the fixed acceptance matrix from repo root:

```bash
python scripts/lint_repo.py
pytest -q tests/test_presence_lifecycle.py tests/test_hotpath_sprint_s2.py tests/test_hotpath_sprint_s3.py tests/test_hotpath_sprint_s4.py tests/test_refresh.py tests/test_folder_pagination.py tests/test_collaboration_sync.py tests/test_compare_export_endpoint.py tests/test_metadata_endpoint.py tests/test_embeddings_search.py tests/test_embeddings_cache.py tests/test_table_security.py tests/test_remote_worker_scaling.py tests/test_parquet_ingestion.py
pytest -q tests/test_ranking_backend.py tests/test_ranking_cli.py
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
npm run test -- src/app/model/__tests__/appMode.test.ts src/features/ranking/model/__tests__/board.test.ts src/features/ranking/model/__tests__/session.test.ts
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
- Retired recursive paging params are ignored; `path`, `recursive`, and `count_only` are the active query contract.
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
