# Lenslet Programmatic API

Launch lenslet directly from Python code or Jupyter notebooks with in-memory datasets.

## Overview

Instead of running `lenslet <directory>` from the command line, you can now launch lenslet programmatically:

```python
import lenslet

datasets = {
    "my_images": ["/path/to/img1.jpg", "/path/to/img2.jpg"],
    "more_images": ["/path/to/img3.png"],
}

lenslet.launch(datasets, blocking=False, port=7070)
```

## Installation

```bash
pip install lenslet

# For S3 support:
pip install unibox
```

## API Reference

### `lenslet.launch()`

```python
lenslet.launch(
    datasets: dict[str, list[str]],
    blocking: bool = False,
    port: int = 7070,
    host: str = "127.0.0.1",
    thumb_size: int = 256,
    thumb_quality: int = 70,
)
```

**Parameters:**

- `datasets` (dict): Dictionary mapping dataset names to lists of image paths/URIs
  - Keys: Dataset names (will appear as folders in the gallery)
  - Values: Lists of image paths (local file paths or S3 URIs)
  
- `blocking` (bool, default=False): Execution mode
  - `False`: Launches in subprocess, returns immediately (for notebooks)
  - `True`: Runs in current process, blocks until Ctrl+C (for standalone scripts)
  
- `port` (int, default=7070): Port to listen on

- `host` (str, default="127.0.0.1"): Host to bind to
  - Use `"127.0.0.1"` for local access only
  - Use `"0.0.0.0"` to allow external access
  
- `thumb_size` (int, default=256): Thumbnail short edge size in pixels

- `thumb_quality` (int, default=70): WebP quality for thumbnails (1-100)

- `verbose` (bool, default=False): Logging verbosity
  - `False`: Only show errors and warnings (quiet mode)
  - `True`: Show all server logs including INFO level

**Returns:** None

**Raises:**
- `ValueError`: If datasets is empty
- `ImportError`: If S3 URIs are used but unibox is not installed

## Supported Image Sources

### Local Files

```python
datasets = {
    "local": [
        "/absolute/path/to/image.jpg",
        "/home/user/photos/image2.png",
    ]
}
```

### S3 URIs

Requires `unibox` package. S3 URIs are automatically detected and converted to presigned URLs.

```python
datasets = {
    "s3_images": [
        "s3://my-bucket/path/to/image.jpg",
        "s3://my-bucket/folder/image2.png",
    ]
}
```

**Note:** S3 credentials must be configured (e.g., via `~/.aws/credentials` or environment variables).

### Mixed Sources

You can mix local and S3 images in the same dataset:

```python
datasets = {
    "mixed": [
        "/local/image1.jpg",
        "s3://bucket/image2.jpg",
        "/local/image3.png",
    ]
}
```

## Usage Examples

### Jupyter Notebook

```python
import lenslet
from pathlib import Path

# Gather images
image_paths = [str(p) for p in Path("/data").glob("*.jpg")]

datasets = {"experiment_1": image_paths}

# Launch in background
lenslet.launch(datasets, blocking=False, port=7070)

# Continue working in notebook
# Access gallery at: http://localhost:7070
```

### With Pandas DataFrame

```python
import pandas as pd
import lenslet

df = pd.DataFrame({
    'image_path': ['/path/img1.jpg', '/path/img2.jpg'],
    'label': ['cat', 'dog'],
})

datasets = {
    "predictions": df['image_path'].tolist()
}

lenslet.launch(datasets, blocking=False, port=7070)
```

### Multiple Datasets

```python
datasets = {
    "training": ["/data/train/img1.jpg", "/data/train/img2.jpg"],
    "validation": ["/data/val/img1.jpg"],
    "test": ["s3://results/test/img1.jpg"],
}

lenslet.launch(datasets, blocking=False, port=7070)
```

In the gallery, each dataset appears as a separate folder, making it easy to browse different collections.

### Standalone Script (Blocking Mode)

```python
import lenslet

datasets = {"my_images": ["/path/img1.jpg", "/path/img2.jpg"]}

# This will block until Ctrl+C
lenslet.launch(datasets, blocking=True, port=7070)
```

## Features

- **No Files Written**: Everything runs in memory, no database or cache files
- **Fast Startup**: Indexes images in memory on launch
- **Auto Thumbnails**: Generates WebP thumbnails on-demand
- **Search**: Full-text search across image names and metadata
- **Session Metadata**: Add tags/notes during session (not persisted)
- **S3 Support**: Seamless support for S3 images via presigned URLs

## Comparison with CLI

| Feature | CLI (`lenslet <dir>`) | API (`lenslet.launch()`) |
|---------|----------------------|--------------------------|
| Source | Local directory | List of paths/URIs |
| S3 support | No | Yes |
| Jupyter-friendly | No | Yes (non-blocking) |
| Multiple datasets | No | Yes |
| Programmatic | No | Yes |

Both modes:
- Store nothing to disk (read-only)
- Generate thumbnails in memory
- Support all common image formats
- Provide same UI and features

## Troubleshooting

### Port Already in Use

```python
# Use a different port
lenslet.launch(datasets, port=8080)
```

### S3 Images Not Loading

1. Ensure `unibox` is installed: `pip install unibox`
2. Check AWS credentials are configured
3. Verify S3 URIs are correct (format: `s3://bucket/key`)

### Images Not Showing

- Ensure file paths are absolute and exist
- Check file extensions are supported: `.jpg`, `.jpeg`, `.png`, `.webp`
- For S3, ensure bucket permissions allow access

## Performance Notes

- **Indexing**: Fast, only reads file metadata (not full images)
- **Thumbnails**: Generated lazily on first access, cached in memory
- **Memory**: Thumbnails are cached; expect ~50-100KB per image
- **Large Datasets**: Tested with 10,000+ images; indexing takes a few seconds

## Limitations

- **Session-only metadata**: Tags/notes are lost when server stops
- **No write operations**: Gallery never writes to source directories
- **Single process**: Each `launch()` call starts a separate server instance

## Future Enhancements

These features are planned but not yet implemented:

- [ ] DataFrame support with metadata columns
- [ ] Persistent metadata option
- [ ] Additional cloud storage backends (GCS, Azure)
- [ ] Custom metadata fields

## See Also

- [Examples](../examples/programmatic_api_example.py): Detailed usage examples
- [README](../README.md): General lenslet documentation
- [Development](../DEVELOPMENT.md): Contributing guide

