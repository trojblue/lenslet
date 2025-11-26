# Lenslet

A lightweight image gallery server that runs entirely in-memory. Point it at a directory of images and browse them in your browser. No database, no metadata files left behind.

## Introduction

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

### Basic Usage

```bash
lenslet /path/to/images
```

Then open http://127.0.0.1:7070 in your browser.

### Options

```bash
lenslet <directory> [options]

Options:
  -p, --port PORT              Port to listen on (default: 7070)
  -H, --host HOST              Host to bind to (default: 127.0.0.1)
  --thumb-size SIZE            Thumbnail short edge in pixels (default: 256)
  --thumb-quality QUALITY      Thumbnail WebP quality 1-100 (default: 70)
  --reload                     Enable auto-reload for development
  -v, --version                Show version and exit
```

### Examples

Serve images from your Pictures folder:
```bash
lenslet ~/Pictures
```

Use a custom port:
```bash
lenslet ~/Photos --port 8080
```

Make accessible on local network:
```bash
lenslet ~/Images --host 0.0.0.0 --port 7070
```

## Notes

- All indexes, thumbnails, and metadata are kept in memory
- Metadata changes (tags, ratings, notes) are lost when the server stops
- Supports JPEG, PNG, and WebP formats
- Hidden files and folders (starting with `.`) are ignored

## License

MIT License
