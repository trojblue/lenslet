# Lenscat Backend

Minimal FastAPI backend for the Lenscat gallery system. Follows the "boring, fast, minimal" philosophy with flat file storage and async workers.

## Features

- **Flat file storage**: No database required, uses JSON manifests and sidecars
- **Dual storage**: Local filesystem or S3 with same API
- **Fast thumbnails**: pyvips (with PIL fallback) for WebP generation
- **Smart indexing**: On-demand folder manifest building
- **Simple search**: Full-text search across filenames, tags, and notes
- **Performance-first**: Async workers, caching, minimal dependencies

## Quick Start

### 1. Install Dependencies

```bash
# Using pip
pip install -r requirements.txt

# Or using poetry
poetry install
```

### 2. Create Sample Data (Optional)

```bash
python scripts/create_sample_data.py
```

### 3. Run Development Server

```bash
python scripts/dev.py
```

The server will start at `http://localhost:8000` with API docs at `/docs`.

## Configuration

Copy `env.example` to `.env` and configure:

```bash
# Storage type
STORAGE_TYPE=local  # or s3

# Local storage
LOCAL_ROOT=./data

# S3 storage (if STORAGE_TYPE=s3)
S3_BUCKET=my-gallery-bucket
S3_PREFIX=gallery/
S3_REGION=us-east-1

# Server
HOST=0.0.0.0
PORT=8000
```

## API Endpoints

### Core Endpoints

- `GET /api/folders?path=<path>` - List folder contents
- `GET /api/item?path=<path>` - Get item metadata
- `PUT /api/item?path=<path>` - Update item metadata
- `GET /api/thumb?path=<path>` - Get/generate thumbnail
- `GET /api/search?q=<query>` - Search items
- `GET /api/health` - System health check

### File Structure

The backend expects this file organization:

```
data/
├── _index.json           # Root folder manifest
├── _rollup.json         # Search index
├── image1.jpg           # Image file
├── image1.jpg.json      # Sidecar metadata
├── image1.jpg.thumbnail # WebP thumbnail
└── subfolder/
    ├── _index.json      # Subfolder manifest
    └── ...
```

### Sidecar Format

```json
{
  "v": 1,
  "tags": ["portrait", "professional"],
  "notes": "Great headshot for website",
  "exif": {
    "width": 1200,
    "height": 900,
    "created_at": "2024-01-15T10:30:00Z"
  },
  "hash": "blake3:abc123...",
  "updated_at": "2024-01-15T15:45:00Z",
  "updated_by": "user@device"
}
```

## Architecture

### Storage Backends

- **LocalStorage**: Direct filesystem access
- **S3Storage**: AWS S3 with aioboto3

### Workers

- **FolderIndexer**: Builds `_index.json` manifests
- **ThumbnailWorker**: Generates missing thumbnails  
- **RollupBuilder**: Creates search index `_rollup.json`

### Performance Features

- Lazy manifest building (only when needed)
- Concurrent thumbnail generation
- BLAKE3 hashing (fallback to SHA256)
- WebP thumbnails with quality optimization
- HTTP caching headers

## Development

### Project Structure

```
src/
├── main.py              # FastAPI app
├── api/                 # API endpoints
├── models/              # Pydantic models
├── storage/             # Storage backends
├── workers/             # Background workers
└── utils/               # Utilities (thumbnails, EXIF, hashing)
```

### Adding Storage Backends

1. Inherit from `StorageBackend`
2. Implement all abstract methods
3. Add to `dependencies.py`

### Performance Guidelines

- Keep functions small (< 50 lines)
- Use async/await everywhere
- Batch operations when possible
- Cache aggressively but invalidate correctly
- Prefer orjson over json for performance

## Deployment

### Docker (Recommended)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/
EXPOSE 8000

CMD ["python", "-m", "src.main"]
```

### Environment Variables

```bash
STORAGE_TYPE=s3
S3_BUCKET=production-gallery
S3_PREFIX=images/
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

## Monitoring

- `GET /api/health` - Overall system health
- `GET /api/health/storage` - Storage backend status  
- `GET /api/health/workers` - Worker statistics

## Troubleshooting

### Common Issues

1. **No thumbnails showing**: Check pyvips installation
2. **S3 access denied**: Verify AWS credentials and bucket permissions
3. **Slow indexing**: Consider pagination for large folders

### Debug Mode

Set `RELOAD=true` for auto-reload during development.

## License

MIT License - see LICENSE file.
