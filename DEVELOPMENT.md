# Development Guide

This document covers development setup, architecture, and contribution guidelines for Lenslet.

Release one-liner:
```bash
cd frontend && npm run build && cd ..
rsync -a --delete frontend/dist/ src/lenslet/frontend/
python -m build
```


## Project Structure

```
lenslet/
├── src/lenslet/                    # Main package (pip installable)
│   ├── cli.py                      # CLI entry point
│   ├── server.py                   # Public FastAPI facade (stable exports)
│   ├── server_runtime.py           # Runtime wiring
│   ├── server_browse.py            # Browse traversal helpers
│   ├── server_factory.py           # App factory assembly
│   ├── server_routes_*.py          # Route domains (common/presence/embeddings/views/index/og)
│   ├── server_media.py             # File/thumb/media responses
│   ├── server_sync.py              # Presence tracker + event broker internals
│   ├── storage/
│   │   ├── base.py                 # Storage protocol
│   │   ├── local.py                # Read-only filesystem
│   │   ├── memory.py               # In-memory caching
│   │   ├── table.py                # TableStorage facade
│   │   ├── table_facade.py         # Delegated table operations
│   │   ├── table_schema.py         # Schema/source coercion
│   │   ├── table_paths.py          # Path/source resolution
│   │   ├── table_index.py          # Index pipeline
│   │   ├── table_probe.py          # Remote probe helpers
│   │   └── table_media.py          # Fast media readers/helpers
│   └── frontend/                   # Bundled React UI (built assets)
│
├── frontend/                       # Frontend source (React + Vite)
│   └── src/
│       ├── api/                     # API client
│       ├── app/
│       │   ├── AppShell.tsx         # App composition
│       │   ├── hooks/               # App domain hooks
│       │   └── model/               # Pure selectors
│       └── features/
│           ├── inspector/           # Inspector facade + sections/hooks/model
│           └── metrics/             # Metrics facade + components/hooks/model
│
├── pyproject.toml
├── README.md
└── DEVELOPMENT.md
```

## Development Setup

### Installing for Development

```bash
# Clone repository
git clone <repo-url>
cd lenslet

# Install in editable mode
pip install -e .

# Install dev dependencies
pip install -e ".[dev]"
```

### Frontend Development

The frontend is a React + Vite application:

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (with proxy to backend)
npm run dev

# Build for production
npm run build
```

The dev server runs at http://localhost:5173 and proxies API requests to http://localhost:7070.

#### UI controls (current UX shortcuts)
- View mode defaults to **Adaptive**; switch via the toolbar dropdown.
- Thumbnail size slider in the toolbar persists; `Ctrl + mouse wheel` over the gallery adjusts the same size (prevents browser zoom).
- Sidebar visibility: `Ctrl+B` toggles the left folder tree; `Ctrl+Alt+B` toggles the right inspector. The same toggles exist as small icon buttons beside the search box.
- Search focus: `/` focuses the search box when not already in an input field.
- Touch open behavior: on touch/pen input, first tap selects and second tap on the same selected item opens the viewer.
- Mobile multi-select: on narrow mobile widths (`<=767px`), use the toolbar drawer `Select` toggle for explicit multi-select mode (no Shift/Ctrl requirement).
- Viewer nav on phones: toolbar nav is shown on narrow viewer layouts except very small phone widths (`<=480px`), where in-viewer `Prev/Next` controls are shown.

### Running the Backend

For development with auto-reload:

```bash
lenslet /path/to/test/images --reload
```

Or run the server directly:

```bash
python -m lenslet.cli /path/to/images --reload
```

## Architecture

### Backend

`src/lenslet/server.py` is intentionally a stable compatibility facade. Route, runtime, and media internals are split into sibling modules to keep imports and monkeypatch touchpoints stable while reducing coupling:
- `server_runtime.py` builds shared runtime state.
- `server_factory.py` composes app creation flows.
- `server_browse.py` owns recursive traversal and related browse helpers.
- `server_routes_common.py`, `server_routes_presence.py`, `server_routes_embeddings.py`, `server_routes_views.py`, `server_routes_index.py`, and `server_routes_og.py` own route registration by domain.
- `server_media.py` owns file/thumb/response helpers.
- `server_sync.py` owns collaboration event replay and presence tracking internals.

**Storage Layer** (`storage/`)
- `LocalStorage`: Read-only filesystem access with path security
- `MemoryStorage`: Wraps LocalStorage with in-memory caching
- `TableStorage` is a facade in `storage/table.py` with delegates in `table_facade.py`, `table_schema.py`, `table_paths.py`, `table_index.py`, `table_probe.py`, and `table_media.py`.

**API Endpoints:**
- `GET /folders?path=<path>` - List folder contents
  - Recursive mode supports paging via `recursive=1&page=<n>&page_size=<n>` (defaults: `page=1`, `page_size=200`, max `page_size=500`)
  - Use `legacy_recursive=1` to return full recursive payloads for backward compatibility
- `GET /item?path=<path>` - Get item metadata
- `PUT /item?path=<path>` - Update item metadata
- `GET /thumb?path=<path>` - Get/generate thumbnail
- `GET /file?path=<path>` - Get original file
  - Local-backed sources are served via streaming responses
  - Non-local sources use byte-response fallback behavior
  - Prefetch callers must use `x-lenslet-prefetch: viewer|compare`
- `GET /search?q=<query>` - Search items
- `GET /health` - Health check
  - Includes hotpath counters/timers under `hotpath.counters` and `hotpath.timers_ms`

### Frontend

**Tech Stack:**
- React 18
- TanStack Query for data fetching
- TanStack Virtual for grid virtualization
- Radix UI for accessible components
- Tailwind CSS for styling

**Key Features:**
- Virtualized grid for smooth scrolling with thousands of images
- Real-time metadata editing
- Keyboard navigation
- Dark theme

## Building and Testing

### Test the CLI

```bash
# Install in editable mode
pip install -e .

# Test with sample data
lenslet /path/to/images --port 7070
```

### Build the Package

```bash
# Ensure dev extras are installed (includes build>=1.2)
pip install -e ".[dev]"

# Build wheel and source distribution
python -m build

# Check the wheel contents
unzip -l dist/lenslet-*.whl
```

### Update the Frontend

When frontend changes are made:

```bash
# Build frontend
cd frontend
npm run build
cd ..

# Deterministic mirror into packaged assets
rsync -a --delete frontend/dist/ src/lenslet/frontend/

# Smoke-check packaged shell response
curl -fsS http://127.0.0.1:7070/index.html > /dev/null

# Rebuild Python package
python -m build
```

### Acceptance Matrix (S7 Baseline)

Run this matrix before closeout/release:

```bash
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
npm run test -- src/app/__tests__/appShellHelpers.test.ts src/app/__tests__/presenceActivity.test.ts src/app/__tests__/presenceUi.test.ts src/features/inspector/__tests__/exportComparison.test.tsx src/features/browse/model/__tests__/filters.test.ts src/features/browse/model/__tests__/pagedFolder.test.ts src/features/browse/model/__tests__/prefetchPolicy.test.ts src/api/__tests__/client.events.test.ts src/api/__tests__/client.presence.test.ts src/api/__tests__/client.exportComparison.test.ts
npx tsc --noEmit
cd ..
python -m build
```

## Hotpath Rollout Notes

- Export flows that require legacy full recursive payloads should call:
  - `api.getFolder(path, { recursive: true, legacyRecursive: true })`
- Keep recursive folder cache keys page-aware (`page`, `pageSize`) to avoid stale page mixing.
- Keep full-file prefetch scoped to viewer/compare navigation only.

### Deferred Backlog (Out of Sprint Scope)

- Indexed search for large datasets (replace O(N) scan paths).
- Folder tree virtualization for very large hierarchies.
- Configurable/batched label persistence writes.


## Development Philosophy

Following the "minimal, fast, boring (on purpose)" principles:

1. **Do the simplest thing that works**
2. **Fail fast, fail loud**
3. **Zero clever wrappers**
4. **Data over code** (store rules in JSON, not code)
5. **Explicit over implicit**

### Code Guidelines

- Keep functions under 50 lines when possible
- Prefer composition over inheritance
- Use type hints throughout
- No global state in the backend
- Frontend state should be in TanStack Query cache

### Performance Targets

- Time to first gallery render: < 2s cold start
- Thumbnail generation: < 100ms per image
- Directory indexing: > 1000 images/sec (stat-only)
- Memory usage: < 100MB + (thumbnails x 15KB)

## Publishing

### PyPI Release

```bash
# Bump version in src/lenslet/__init__.py
# Rebuild frontend if needed
cd frontend && npm run build && cd ..
rsync -a --delete frontend/dist/ src/lenslet/frontend/

# Build and upload
python -m build
pip install twine
twine upload dist/*
```

### Release Checklist

- [ ] Frontend rebuilt and mirrored with `rsync -a --delete frontend/dist/ src/lenslet/frontend/`
- [ ] Version bumped in `__init__.py`
- [ ] CHANGELOG updated
- [ ] Tests pass
- [ ] Package builds successfully
- [ ] Test installation in clean environment
- [ ] Tag release in git

## Contributing

1. Follow the development philosophy above
2. Keep PRs focused and under 400 lines
3. Test with real image directories
4. Maintain performance budgets
5. No clever abstractions

## License

MIT License
