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
│   ├── server.py                   # Public FastAPI facade (stable exports)
│   ├── web/                        # FastAPI app factory, runtime, routes, media, cache, sync
│   ├── cli/
│   │   ├── __main__.py             # `python -m lenslet.cli`
│   │   ├── main.py                 # CLI dispatcher
│   │   ├── browse.py               # Browse CLI implementation
│   │   └── rank.py                 # Ranking CLI implementation
│   ├── storage/
│   │   ├── base.py                 # Storage protocol
│   │   ├── local/
│   │   │   ├── __init__.py         # Read-only filesystem storage
│   │   │   └── preindex.py         # Local preindex support
│   │   ├── memory/                 # Local browse storage and cache helpers
│   │   ├── table/                  # TableStorage facade, launch, schema, and row-scan helpers
│   │   ├── source/                 # Source-backed media, path, catalog, and probe helpers
│   │   ├── image_media.py          # Media sniffing and dimensions
│   │   └── index_assembly.py       # Shared browse index assembly
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

# Install the validated Python 3.13 runtime stack used in this repo
python -m pip install -c constraints/runtime-py313.txt -e .
python -m pip install -c constraints/runtime-py313.txt -e ".[dev]"
```

For a fresh checkout that also needs frontend dependencies and browser smoke support:

```bash
python scripts/setup_dev.py
```

The setup script installs `.[dev]`, runs `npm ci` in `frontend/`, and installs Playwright Chromium. On Linux it uses Playwright's `--with-deps` mode by default so headless Chromium has its required system libraries; pass `--skip-browser-system-deps` when those packages are already managed elsewhere.

### Frontend Development

The frontend is a React + Vite application:

```bash
cd frontend

# Install dependencies
npm ci

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

`src/lenslet/server.py` is intentionally a stable facade. Route, runtime, and media internals live under `src/lenslet/web/`:
- `web/app/factory.py` composes app creation flows for directory, table, dataset, and storage launches.
- `web/app/builder.py`, `web/app/base.py`, and `web/app/runtime.py` assemble FastAPI routes and shared runtime state.
- `web/browse.py`, `web/media.py`, `web/metadata.py`, and `web/og/` own browse payloads, file/thumb responses, image metadata parsing, and OG data/style helpers with lazy rendering.
- `web/routes/` owns route registration by domain.
- `web/sync/labels.py`, `web/sync/events.py`, `web/sync/presence.py`, and `web/sync/helpers.py` own label mutation, event replay, presence, and shared sync helpers.

**Storage Layer** (`storage/`)
- `LocalStorage`: Read-only filesystem access with path security
- `MemoryStorage`: Wraps LocalStorage with in-memory caching
- `TableStorage`: Table-backed browse storage using `table/schema.py`, `table/index.py`, `table/row_scan.py`, `table/launch.py`, and `table/pyarrow_runtime.py`
- `DatasetStorage`: Programmatic dataset-map browse storage
- Shared source-backed helpers live in `source/paths.py`, `image_media.py`, `index_assembly.py`, `source/media.py`, `source/state.py`, and `source/catalog.py`.

**API Endpoints:**
- `GET /folders?path=<path>` - List folder contents
  - Recursive mode uses `recursive=1` and returns the full recursive payload in one response.
  - `count_only=1` returns the recursive count without materializing the item payload.
  - The active folder query contract is `path`, `recursive`, and `count_only`.
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

### Browser Harness Change Gate

Browser harnesses under `scripts/browser/`, browse-cache code, and web route hotspots should not absorb helper-only churn. Before editing those areas, record the issue-specific root cause, the expected open-issue reduction, and the validation command that will prove the browser-facing behavior changed. If the expected reduction is zero, keep the change out of those hotspots and fix the owning product/runtime code instead.

### Skip Debt Gate

Permanent skips and wontfix entries in the Desloppify plan should stay rare and reviewable. Before adding a permanent skip, record the concrete blocker, why fixing it now would be lower value than the live queue, and the condition that should trigger review. When skipped debt grows or survives multiple scans, inspect `desloppify plan queue --include-skipped` before adding more skips so stale wontfix items do not distort prioritization.

### Test the CLI

```bash
# Install the validated Python 3.13 runtime stack used in this repo
python -m pip install -c constraints/runtime-py313.txt -e .

# Test with sample data
lenslet /path/to/images --port 7070
```

### Build the Package

```bash
# Ensure the validated runtime stack and dev extras are installed
python -m pip install -c constraints/runtime-py313.txt -e ".[dev]"

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
pytest -q tests/web/sync/test_presence_lifecycle.py tests/web/hotpath/test_hotpath_sprint_s2.py tests/web/hotpath/test_hotpath_sprint_s3.py tests/web/hotpath/test_hotpath_sprint_s4.py tests/web/app/test_refresh.py tests/web/routes/test_folder_recursive.py tests/web/sync/test_collaboration_sync.py tests/web/export/test_compare_export_endpoint.py tests/web/metadata/test_metadata_endpoint.py tests/embeddings/test_embeddings_search.py tests/embeddings/test_embeddings_cache.py tests/storage/table/test_table_security.py tests/storage/source/test_remote_worker_scaling.py tests/storage/table/test_parquet_ingestion.py
python - <<'PY'
import lenslet.server as server
import lenslet.storage.table as table
assert hasattr(server, 'create_app')
assert hasattr(server, 'create_app_from_datasets')
assert hasattr(server, 'create_app_from_table')
assert hasattr(server, 'create_app_from_storage')
assert hasattr(server, 'HotpathTelemetry')
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
python -m scripts.browser.gui_smoke.acceptance
python -m build
```

## Hotpath Rollout Notes

- Export flows that need descendant items should call `api.getFolder(path, { recursive: true })`.
- Count-only flows should call `api.getFolderPaths` or `api.getFolder(path, { recursive: true, countOnly: true })` instead of materializing every item.
- Keep recursive folder cache keys scoped by path and recursive mode so stale descendant payloads are not mixed with direct folder payloads.
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
