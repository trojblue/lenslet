# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lenslet is a lightweight, pip-installable image gallery server. It runs entirely in-memory, indexing directories on-the-fly and generating thumbnails without writing any files to the source directory.

**Core Architecture:**
- **CLI:** `lenslet <dir> --port <port>` starts the server
- **Backend:** FastAPI server with in-memory storage (no database, no sidecars written)
- **Frontend:** React + TanStack Query/Virtual, bundled into the Python package
- **Storage:** Read-only filesystem access, all caching in RAM

## Project Structure

```
lenslet/
├── src/lenslet/              # Main package (pip installable)
│   ├── __init__.py          # Version
│   ├── cli.py               # CLI entry point (argparse)
│   ├── server.py            # FastAPI application
│   ├── storage/
│   │   ├── base.py          # Storage protocol
│   │   ├── local.py         # Read-only filesystem
│   │   └── memory.py        # In-memory caching
│   └── frontend/            # BUILT React UI (bundled in wheel)
│
├── frontend/                 # Frontend SOURCE (for development)
│   ├── src/
│   │   ├── api/             # API client
│   │   ├── app/             # React components
│   │   ├── features/        # Feature modules
│   │   └── lib/             # Utilities
│   ├── package.json
│   └── vite.config.ts
│
├── pyproject.toml
├── README.md
└── DEVELOPMENT.md
```

## Common Development Commands

### Backend

```bash
# Install in editable mode
pip install -e .
pip install -e ".[dev]"

# Run the gallery
lenslet /path/to/images --port 7070

# With auto-reload for development
lenslet /path/to/images --reload

# Or run as module
python -m lenslet.cli /path/to/images --reload
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Development server (proxies API to :7070)
npm run dev

# Build for production
npm run build

# Copy built files to package
cp -r dist/* ../src/lenslet/frontend/
```

### Full Stack Development

1. **Backend:** `lenslet /path/to/images --port 7070`
2. **Frontend:** `cd frontend && npm run dev`
3. Frontend dev server runs at http://localhost:5173, proxies API to :7070

### Building & Publishing

```bash
# Build the wheel (includes bundled frontend)
python -m build

# Check wheel contents
unzip -l dist/lenslet-*.whl

# Publish
pip install twine
twine upload dist/*
```

## Code Architecture

### Backend (src/lenslet/)

- **`cli.py`**: Argparse CLI, starts uvicorn server
- **`server.py`**: FastAPI app factory with routes
- **`storage/local.py`**: Read-only filesystem with path security
- **`storage/memory.py`**: Wraps LocalStorage with in-memory caching
  - Lazy dimension loading (fast startup with large directories)
  - On-demand thumbnail generation
  - Search across cached indexes

**API Endpoints:**
- `GET /folders?path=<path>` - List folder contents
- `GET /item?path=<path>` - Get item metadata
- `PUT /item?path=<path>` - Update metadata (session-only)
- `GET /thumb?path=<path>` - Get/generate thumbnail
- `GET /file?path=<path>` - Get original file
- `GET /search?q=<query>` - Search items
- `GET /health` - Health check

### Frontend (frontend/src/)

- **`App.tsx`**: Root component with QueryClientProvider
- **`app/AppShell.tsx`**: Main layout
- **`features/browse/`**: Virtualized grid browsing
- **`features/folders/`**: Folder tree navigation
- **`features/inspector/`**: Image metadata editor
- **`features/viewer/`**: Full-size image viewer
- **`api/`**: API client and TanStack Query hooks

**Tech Stack:**
- React 18, TanStack Query, TanStack Virtual
- Radix UI for accessible components
- Tailwind CSS for styling

## Development Philosophy

**"Minimal, fast, boring (on purpose)"**

1. **Do the simplest thing that works** - No clever wrappers for basic tasks
2. **Fail fast, fail loud** - Throw early with exact context
3. **Zero clever wrappers** - Use the platform until it hurts
4. **Explicit over implicit** - No magic, no global state
5. **Read-only source** - Never write to the image directory

### Key Constraints

- **Supported formats:** JPEG, PNG, WebP only
- **In-memory only:** All state lost on restart (by design)
- **No database:** Everything cached in RAM
- **Max PR size:** ~400 lines net change

### Performance Targets

- Directory indexing: > 1000 images/sec (stat-only, lazy dimensions)
- Thumbnail generation: < 100ms per image
- Time to first grid: < 2s cold start
- Memory: ~100MB + (thumbnails × 15KB)

### Code Style

**Python:**
- Type hints everywhere
- Functions < 50 lines
- No global state

**TypeScript:**
- Strict mode, no `any`
- Components < 200 lines
- State in TanStack Query cache

## Important Notes

### Two Frontend Folders

| Folder | Purpose | In pip package? |
|--------|---------|-----------------|
| `frontend/` | Source code for development | No |
| `src/lenslet/frontend/` | Built assets (JS/CSS/HTML) | Yes |

After frontend changes:
```bash
cd frontend && npm run build
cp -r dist/* ../src/lenslet/frontend/
```

### Storage Behavior

- `LocalStorage`: Read-only filesystem, validates paths against root
- `MemoryStorage`: Wraps LocalStorage, caches indexes/thumbnails/metadata in RAM
- **Never writes** to the source directory

### Avoid These

- Writing any files to the image directory
- Blocking on dimension reading during indexing (use lazy loading)
- Global state or singletons
- Over-engineering for hypothetical requirements
