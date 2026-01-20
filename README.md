# Lenslet

A lightweight image gallery server that runs entirely in-memory. Point it at a directory of images and browse them in your browser. No database, no metadata files left behind.

## Introduction

<img width="2145" height="1277" alt="image" src="https://github.com/user-attachments/assets/efd38faf-b5e8-43e5-9176-d01c06654d16" />
<img width="2145" height="1277" alt="image" src="https://github.com/user-attachments/assets/82940322-50a2-43e5-bb2d-7c10b3d9b3f2" />

Lenslet is a self-contained image gallery server designed for simplicity and speed. It indexes directories on-the-fly, generates thumbnails in memory, and serves everything through a clean web interface. Perfect for quickly browsing local image collections without modifying the source directory.

## Features

- **Clean operation**: No files written to your image directories
- **In-memory indexing**: Fast directory scanning and caching
- **On-demand thumbnails**: Generated and cached in RAM
- **Full web UI**: Browse, search, and view images in your browser
- **Metadata support**: Add tags, notes, and ratings (session-only)
- **Single command**: Just point to a directory and go

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
lenslet <directory> [options]

Options:
  -p, --port PORT              Port to listen on (default: 7070; auto-increment if in use)
  -H, --host HOST              Host to bind to (default: 127.0.0.1)
  --thumb-size SIZE            Thumbnail short edge in pixels (default: 256)
  --thumb-quality QUALITY      Thumbnail WebP quality 1-100 (default: 70)
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
- 🔗 **Mixed sources**: Combine local files and S3 images

See [Programmatic API Documentation](docs/PROGRAMMATIC_API.md) for details and examples.

## Notes

- All indexes, thumbnails, and metadata are kept in memory
- Metadata changes (tags, ratings, notes) are lost when the server stops
- Supports JPEG, PNG, and WebP formats
- Hidden files and folders (starting with `.`) are ignored

## License

MIT License
