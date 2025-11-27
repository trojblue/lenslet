"""
Example usage of lenslet's programmatic API.

This shows how to launch lenslet from Python/notebooks with in-memory datasets.
"""

import lenslet

# Example 1: Simple local images
# ================================
def example_local_images():
    """Launch with local image paths."""
    datasets = {
        "my_photos": [
            "/path/to/photo1.jpg",
            "/path/to/photo2.png",
            "/path/to/photo3.jpg",
        ],
        "screenshots": [
            "/path/to/screenshot1.png",
            "/path/to/screenshot2.png",
        ],
    }
    
    # Launch in non-blocking mode (returns immediately, runs in subprocess)
    lenslet.launch(datasets, blocking=False, port=7070)
    
    print("Gallery running at http://127.0.0.1:7070")
    # Your notebook/script can continue running while gallery is in background


# Example 2: S3 images (requires boto3, install with lenslet[s3])
# ================================================
def example_s3_images():
    """Launch with S3 URIs (automatically converted to presigned URLs)."""
    datasets = {
        "s3_dataset": [
            "s3://my-bucket/images/photo1.jpg",
            "s3://my-bucket/images/photo2.jpg",
        ],
    }
    
    # S3 URIs are automatically detected and converted to presigned URLs
    lenslet.launch(datasets, blocking=False, port=7071)


# Example 3: Mixed local and S3
# ==============================
def example_mixed():
    """Launch with both local and S3 images in the same dataset."""
    datasets = {
        "mixed_dataset": [
            "/local/path/image1.jpg",           # Local file
            "s3://bucket/image2.jpg",           # S3 URI
            "/local/path/image3.png",           # Local file
            "s3://bucket/subfolder/image4.jpg", # S3 URI
        ],
    }
    
    lenslet.launch(datasets, blocking=False, port=7070)


# Example 4: Blocking mode (for scripts)
# ========================================
def example_blocking():
    """Launch in blocking mode (doesn't return, runs in current process)."""
    datasets = {
        "my_images": ["/path/to/img1.jpg", "/path/to/img2.jpg"],
    }
    
    # This will block until Ctrl+C
    # Useful for standalone scripts where you want to keep the gallery running
    lenslet.launch(datasets, blocking=True, port=7070)
    
    # Code here won't execute until gallery is stopped


# Example 5: Custom settings
# ===========================
def example_custom_settings():
    """Launch with custom thumbnail settings."""
    datasets = {
        "high_quality": ["/path/to/img1.jpg"],
    }
    
    lenslet.launch(
        datasets,
        blocking=False,
        port=8080,
        host="0.0.0.0",  # Listen on all interfaces
        thumb_size=512,  # Larger thumbnails
        thumb_quality=85,  # Higher quality
        verbose=True,  # Show detailed server logs
    )


# Example 6: Jupyter notebook usage
# ==================================
"""
In a Jupyter notebook:

```python
import lenslet
from pathlib import Path

# Gather images from a directory
image_dir = Path("/path/to/images")
image_paths = [str(p) for p in image_dir.glob("*.jpg")]

datasets = {
    "notebook_images": image_paths
}

# Launch in non-blocking mode
lenslet.launch(datasets, blocking=False, port=7070)

# Continue working in your notebook while gallery runs in background
# Access at: http://localhost:7070
```
"""


# Example 7: With pandas DataFrame
# ==================================
"""
Common use case: you have a pandas DataFrame with image paths.

```python
import pandas as pd
import lenslet

# Your DataFrame has an 'image_path' column
df = pd.DataFrame({
    'image_path': ['/path/img1.jpg', '/path/img2.jpg'],
    'label': ['cat', 'dog'],
    'confidence': [0.95, 0.88]
})

# Extract image paths and launch
datasets = {
    "predictions": df['image_path'].tolist()
}

lenslet.launch(datasets, blocking=False, port=7070)
```
"""


# Example 8: Multiple datasets from different sources
# ====================================================
"""
Organize images from different sources/experiments:

```python
import lenslet

datasets = {
    "experiment_1": [
        "/data/exp1/img1.jpg",
        "/data/exp1/img2.jpg",
    ],
    "experiment_2": [
        "s3://results/exp2/img1.jpg",
        "s3://results/exp2/img2.jpg",
    ],
    "baseline": [
        "/data/baseline/img1.jpg",
    ],
}

lenslet.launch(datasets, blocking=False, port=7070)

# Navigate between datasets in the gallery UI
# Each dataset appears as a separate folder
```
"""


if __name__ == "__main__":
    print("Lenslet Programmatic API Examples")
    print("=" * 50)
    print("\nSee the function docstrings and code for examples.")
    print("\nBasic usage:")
    print("  import lenslet")
    print("  datasets = {'my_images': ['/path/img1.jpg', '/path/img2.jpg']}")
    print("  lenslet.launch(datasets, blocking=False, port=7070)")
