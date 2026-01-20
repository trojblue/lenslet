# Lenslet

A lightweight image gallery server for fast visual triage. Point it at a directory or a Parquet table and browse instantly in your browser. Lenslet keeps the source images read-only and stores workspace state separately.

## Introduction

<img width="2145" height="1277" alt="image" src="https://github.com/user-attachments/assets/efd38faf-b5e8-43e5-9176-d01c06654d16" />
<img width="2145" height="1277" alt="image" src="https://github.com/user-attachments/assets/82940322-50a2-43e5-bb2d-7c10b3d9b3f2" />

Lenslet is a self-contained image gallery server designed for simplicity and speed. It indexes directories on-the-fly, generates thumbnails on demand, and serves everything through a clean web interface. Perfect for quickly browsing local image collections or large Parquet-backed datasets without modifying the source images.

## Features

- **Workspace-aware**: Persists UI state (Smart Folders/views) and optional thumbnail cache under `.lenslet/` (or `<parquet>.lenslet.json`)
- **Read-only sources**: Never writes into your image directories or S3 buckets
- **Local + S3 + HTTP**: Mix local files, `s3://` URIs, and URLs with smart source parsing
- **Metrics & filtering**: Sort/filter by numeric metrics from Parquet (histograms + range brushing)
- **Labels & export**: Tag, rate, and annotate items, then export metadata as JSON or CSV
- **Single command**: Just point to a directory or Parquet file and go

## Installation

```bash
pip install lenslet
```

## Usage

### Command Line Interface

```bash
lenslet /path/to/images
```

Then open the URL printed in the terminal (default http://127.0.0.1:7070, or the next available port).

**Options:**

```bash
lenslet <directory|table.parquet> [options]

Options:
  -p, --port PORT              Port to listen on (default: 7070; auto-increment if in use)
  -H, --host HOST              Host to bind to (default: 127.0.0.1)
  --thumb-size SIZE            Thumbnail short edge in pixels (default: 256)
  --thumb-quality QUALITY      Thumbnail WebP quality 1-100 (default: 70)
  --source-column NAME         Column to load image paths from in table mode
  --base-dir PATH              Base directory for resolving relative paths in table mode
  --cache-wh / --no-cache-wh   Cache width/height back into parquet (default: on)
  --skip-indexing / --no-skip-indexing
                               Skip probing image dimensions during table load (default: on)
  --thumb-cache / --no-thumb-cache
                               Cache thumbnails on disk when a workspace is available (default: on)
  --no-write                   Disable workspace writes (.lenslet/) for one-off sessions
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
- **Read-only sources**: The server never writes into your image directories or S3 buckets
- **Labels**: Tags/notes/ratings are editable in the UI (session-only) and exportable as JSON/CSV
- **No-write mode**: Pass `--no-write` to keep the session fully ephemeral (no `.lenslet/` or `.lenslet.json`)
- **Formats**: Supports JPEG, PNG, and WebP
- **Hidden files**: Files/folders starting with `.` are ignored

## License

MIT License
