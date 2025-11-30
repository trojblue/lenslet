# Lenslet Programmatic API - Quick Start

## Installation

```bash
pip install lenslet

# For S3 support:
pip install "lenslet[s3]"  # installs boto3
```

## 30-Second Example

```python
import lenslet

# Define your datasets
datasets = {
    "my_photos": [
        "/path/to/photo1.jpg",
        "/path/to/photo2.png",
    ],
    "s3_images": [
        "s3://bucket/image1.jpg",
        "s3://bucket/image2.jpg",
    ],
    "web_images": [
        "https://example.com/cat.jpg",
    ],
}

# Launch the gallery
lenslet.launch(datasets, blocking=False, port=7070)

# ✨ Gallery is now running at http://localhost:7070
```

That's it! The gallery runs in the background while your script/notebook continues.

## Key Features

- 🚀 **Non-blocking**: Returns immediately, perfect for Jupyter notebooks
- ☁️ **S3 Support**: Automatically handles S3 URIs with presigned URLs
- 🌐 **HTTP/HTTPS URLs**: Serve images directly from web URLs
- 📁 **Multiple Datasets**: Organize images into named collections
- 🔗 **Mixed Sources**: Combine local files and S3 in the same list
- 💨 **Fast**: In-memory indexing and caching
- 🔒 **Safe**: Read-only, never modifies source files

## Common Use Cases

### Jupyter Notebook

```python
import lenslet
from pathlib import Path

# Gather images
images = [str(p) for p in Path("/data").glob("*.jpg")]

# Launch and keep working
lenslet.launch({"experiment": images}, port=7070)

# Gallery runs in background, access at http://localhost:7070
```

### With Pandas

```python
import pandas as pd
import lenslet

df = pd.read_csv("results.csv")

datasets = {
    "all": df['image_path'].tolist(),
    "high_score": df[df['score'] > 0.9]['image_path'].tolist(),
}

lenslet.launch(datasets, port=7070)
```

### S3 Images Only

```python
import lenslet

datasets = {
    "production": [
        "s3://my-bucket/prod/img1.jpg",
        "s3://my-bucket/prod/img2.jpg",
    ]
}

lenslet.launch(datasets, port=7070)
```

## Parameters

```python
lenslet.launch(
    datasets,              # Required: dict[name, list[paths]]
    blocking=False,        # False=subprocess, True=current process
    port=7070,            # Server port
    host="127.0.0.1",     # Server host
    thumb_size=256,       # Thumbnail size (px)
    thumb_quality=70,     # WebP quality (1-100)
    verbose=False,        # Show detailed logs (True) or quiet (False)
)
```

## More Information

- **Full Documentation**: [docs/PROGRAMMATIC_API.md](docs/PROGRAMMATIC_API.md)
- **Examples**: [examples/programmatic_api_example.py](examples/programmatic_api_example.py)
- **Notebook Examples**: [examples/notebook_example.ipynb](examples/notebook_example.ipynb)
- **Implementation Details**: [docs/API_IMPLEMENTATION.md](docs/API_IMPLEMENTATION.md)

## Troubleshooting

**Port in use?**
```python
lenslet.launch(datasets, port=8080)  # Use different port
```

**S3 not working?**
```bash
pip install "lenslet[s3]"  # ensures boto3 is installed
# Ensure AWS credentials configured
```

**Stop the server?**
```bash
pkill -f "lenslet.*7070"  # Replace 7070 with your port
```

## What's Different from CLI?

| Feature | CLI `lenslet <dir>` | API `lenslet.launch()` |
|---------|---------------------|------------------------|
| Input | Directory path | List of paths/URIs |
| S3 | ❌ No | ✅ Yes |
| Jupyter | ❌ Blocks | ✅ Non-blocking |
| Multiple collections | ❌ No | ✅ Yes |
| Programmatic | ❌ No | ✅ Yes |

Both modes are read-only, fast, and use the same UI!
