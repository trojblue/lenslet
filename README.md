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
  --no-write                   Disable workspace writes (.lenslet/) for one-off sessions
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

## Notes

- **Workspace files**: `.lenslet/views.json` stores Smart Folders; optional thumbnail cache lives under `.lenslet/thumbs/`
  - For Parquet, views live at `<table>.lenslet.json` and thumbs at `<table>.cache/thumbs/`
- **Embedding cache**: `.lenslet/embeddings_cache/` (or `<table>.cache/embeddings_cache/`) stores cached embedding indexes
- **Read-only sources**: The server never writes into your image directories or S3 buckets
- **Labels**: Tags/notes/ratings are editable in the UI (session-only) and exportable as JSON/CSV
- **No-write mode**: Pass `--no-write` to keep the session fully ephemeral (no `.lenslet/` or `.lenslet.json`)
- **Formats**: Supports JPEG, PNG, and WebP
- **Hidden files**: Files/folders starting with `.` are ignored

## License

MIT License
