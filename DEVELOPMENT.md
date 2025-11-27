# Development Guide

This document covers development setup, architecture, and contribution guidelines for Lenslet.

## Project Structure

```
lenslet/
├── src/lenslet/              # Main package (pip installable)
│   ├── cli.py               # CLI entry point
│   ├── server.py            # FastAPI application
│   ├── storage/             # Storage backends
│   │   ├── base.py          # Storage protocol
│   │   ├── local.py         # Read-only filesystem
│   │   └── memory.py        # In-memory caching
│   └── frontend/            # Bundled React UI (built)
│
├── frontend/                 # Frontend source (React dev)
│   └── src/
│       ├── api/             # API client
│       ├── app/             # React components
│       └── lib/             # Utilities
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

**FastAPI Server** (`server.py`)
- Serves static frontend files
- Provides REST API for gallery operations
- Uses dependency injection for storage

**Storage Layer** (`storage/`)
- `LocalStorage`: Read-only filesystem access with path security
- `MemoryStorage`: Wraps LocalStorage with in-memory caching
- All indexing and thumbnails stored in RAM
- Lazy dimension loading for fast startup with large directories

**API Endpoints:**
- `GET /folders?path=<path>` - List folder contents
- `GET /item?path=<path>` - Get item metadata
- `PUT /item?path=<path>` - Update item metadata
- `GET /thumb?path=<path>` - Get/generate thumbnail
- `GET /file?path=<path>` - Get original file
- `GET /search?q=<query>` - Search items
- `GET /health` - Health check

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
# Install build tools
pip install build

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

# Copy to package
rm -rf ../src/lenslet/frontend/*
cp -r dist/* ../src/lenslet/frontend/

# Rebuild Python package
cd ..
python -m build
```

oneliner:
```bash
cd frontend && npm run build && cp -r dist/* ../src/lenslet/frontend/ && cd ..
python -m build
```
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
cd frontend && npm run build
cp -r dist/* ../src/lenslet/frontend/

# Build and upload
cd ..
python -m build
pip install twine
twine upload dist/*
```

### Release Checklist

- [ ] Frontend rebuilt and copied
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
