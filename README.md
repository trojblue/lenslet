# Lenslet Gallery System

A minimal, fast, boring (on purpose) gallery system with React frontend and FastAPI backend. Built for performance and simplicity.

## Architecture

- **Frontend**: React + TanStack Query/Virtual + minimal CSS
- **Backend**: FastAPI + flat file storage (local/S3) + async workers
- **Storage**: No database - JSON manifests + sidecars + thumbnails

## Quick Start

### 1. Backend Setup

```bash
cd lenscat-backend

# Install dependencies
pip install -r requirements.txt

# Create sample data (optional)
python scripts/create_sample_data.py

# Start backend
python scripts/dev.py
```

Backend runs at `http://localhost:8000` with API docs at `/docs`.

### 2. Frontend Setup

```bash
cd lenscat-lite

# Install dependencies  
npm install

# Set API endpoint
echo "VITE_API_BASE=http://localhost:8000/api" > .env.local

# Start frontend
npm run dev
```

Frontend runs at `http://localhost:5173`.

## Project Structure

```
lenslet/
├── lenscat-backend/          # FastAPI backend
│   ├── src/
│   │   ├── api/             # API endpoints
│   │   ├── models/          # Pydantic models  
│   │   ├── storage/         # Storage backends (local/S3)
│   │   ├── workers/         # Indexing & thumbnail workers
│   │   ├── utils/           # Utilities (EXIF, hashing, thumbs)
│   │   └── main.py          # FastAPI app
│   ├── scripts/             # Development scripts
│   ├── data/                # Local storage (dev)
│   └── requirements.txt
│
├── lenscat-lite/            # React frontend  
│   ├── src/
│   │   ├── api/            # API client & query hooks
│   │   ├── components/     # React components
│   │   ├── hooks/          # Custom hooks
│   │   ├── lib/            # Utilities & types
│   │   ├── App.tsx         # Main app
│   │   └── main.tsx        # Entry point
│   ├── package.json
│   └── vite.config.ts
│
└── dev_notes/               # Design documents
    ├── Developer_note.md    # Core dev principles
    ├── PRD_v0.md           # Frontend PRD
    └── PRD_v0_backend.md   # Backend PRD
```

## Key Features

### Backend
- **Dual storage**: Local filesystem or S3 with unified API
- **Smart indexing**: On-demand folder manifest building
- **Fast thumbnails**: pyvips + WebP generation
- **Simple search**: Full-text across filenames, tags, notes
- **Flat files**: No database, JSON manifests + sidecars
- **Performance**: Async workers, caching, BLAKE3 hashing

### Frontend  
- **Virtualized grid**: Smooth scrolling for thousands of images
- **Eagle-inspired theme**: Dark, minimal, performance-first
- **Real-time metadata**: Tags/notes save to sidecars immediately
- **Keyboard navigation**: Arrow keys, Enter, shortcuts
- **Responsive**: Works on desktop and mobile
- **No bloat**: No global state, UI kits, or CSS-in-JS

## Development Philosophy

Following the **"minimal, fast, boring (on purpose)"** principles:

1. **Do the simplest thing that works**
2. **Fail fast, fail loud** 
3. **Zero clever wrappers**
4. **Data > code** (store rules in JSON, not code)
5. **Sidecar is the source** (metadata lives next to images)

## File Organization

The system expects this structure:

```
data/
├── _index.json              # Root folder manifest
├── _rollup.json            # Search index
├── image1.jpg              # Image file
├── image1.jpg.json         # Sidecar metadata
├── image1.jpg.thumbnail    # WebP thumbnail
└── subfolder/
    ├── _index.json         # Subfolder manifest
    └── ...
```

## Configuration

### Backend (.env)
```bash
STORAGE_TYPE=local          # or s3
LOCAL_ROOT=./data
S3_BUCKET=my-gallery
S3_PREFIX=gallery/
HOST=0.0.0.0
PORT=8000
```

### Frontend (.env.local)
```bash
VITE_API_BASE=http://localhost:8000/api
```

## Performance Targets

- **Time to first grid**: < 700ms hot, < 2s cold
- **Scroll performance**: < 1.5% dropped frames  
- **Inspector open**: < 150ms
- **Thumbnail cache hit**: > 85%
- **Indexing throughput**: > 300 items/sec

## Deployment

### Docker Backend
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ ./src/
EXPOSE 8000
CMD ["python", "-m", "src.main"]
```

### Static Frontend
```bash
npm run build
# Deploy dist/ to CDN/static hosting
```

## API Endpoints

- `GET /api/folders?path=<path>` - List folder contents
- `GET /api/item?path=<path>` - Get item metadata  
- `PUT /api/item?path=<path>` - Update item metadata
- `GET /api/thumb?path=<path>` - Get/generate thumbnail
- `GET /api/search?q=<query>` - Search items
- `GET /api/health` - System health

## Contributing

1. Follow the dev guide principles in `dev_notes/`
2. Keep PRs < 400 lines
3. Test with sample data
4. Maintain performance budgets
5. No clever abstractions

## License

MIT License
