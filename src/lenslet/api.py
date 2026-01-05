"""Programmatic API for launching lenslet from Python/notebooks."""
from __future__ import annotations
import sys
import subprocess
import multiprocessing as mp
from typing import Any


def launch(
    datasets: dict[str, list[str]],
    blocking: bool = False,
    port: int = 7070,
    host: str = "127.0.0.1",
    thumb_size: int = 256,
    thumb_quality: int = 70,
    show_source: bool = True,
    verbose: bool = False,
) -> None:
    """
    Launch lenslet with in-memory datasets.
    
    Args:
        datasets: Dict of {dataset_name: [list of image paths/URIs]}
                 Supports both local file paths and S3 URIs (s3://...)
        blocking: If False (default), launches in subprocess. If True, runs in current process.
        port: Port to listen on (default: 7070)
        host: Host to bind to (default: 127.0.0.1)
        thumb_size: Thumbnail short edge size in pixels (default: 256)
        thumb_quality: Thumbnail WEBP quality 1-100 (default: 70)
        show_source: If True (default), show original source paths/URIs in the UI.
        verbose: If True, show all server logs. If False (default), only show errors.
    
    Example:
        >>> import lenslet
        >>> datasets = {
        ...     "my_images": ["/path/to/img1.jpg", "/path/to/img2.png"],
        ...     "s3_images": ["s3://bucket/image1.jpg", "s3://bucket/image2.jpg"],
        ... }
        >>> lenslet.launch(datasets, blocking=False, port=7070)
    """
    if not datasets:
        raise ValueError("datasets cannot be empty")
    
    if blocking:
        # Run in current process
        _launch_blocking(
            datasets=datasets,
            port=port,
            host=host,
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
            show_source=show_source,
            verbose=verbose,
        )
    else:
        # Launch in subprocess
        _launch_subprocess(
            datasets=datasets,
            port=port,
            host=host,
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
            show_source=show_source,
            verbose=verbose,
        )


def _launch_blocking(
    datasets: dict[str, list[str]],
    port: int,
    host: str,
    thumb_size: int,
    thumb_quality: int,
    show_source: bool,
    verbose: bool,
) -> None:
    """Launch in current process (blocking)."""
    import uvicorn
    from .server import create_app_from_datasets
    
    # Print startup banner
    total_images = sum(len(paths) for paths in datasets.values())
    dataset_list = ", ".join(datasets.keys())
    
    print(f"""
┌─────────────────────────────────────────────────┐
│                   🔍 Lenslet                    │
│         Lightweight Image Gallery Server        │
├─────────────────────────────────────────────────┤
│  Datasets:  {dataset_list[:35]:<35} │
│  Images:    {total_images:<35} │
│  Server:    http://{host}:{port:<24} │
│  Mode:      In-memory (programmatic API)        │
└─────────────────────────────────────────────────┘
""")
    
    app = create_app_from_datasets(
        datasets=datasets,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        show_source=show_source,
    )
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info" if verbose else "warning",
    )


def _launch_subprocess(
    datasets: dict[str, list[str]],
    port: int,
    host: str,
    thumb_size: int,
    thumb_quality: int,
    show_source: bool,
    verbose: bool,
) -> None:
    """Launch in subprocess (non-blocking)."""
    # We'll use multiprocessing to launch in a separate process
    # This allows it to work in notebooks without blocking
    
    def _worker():
        # Don't print banner in worker - parent process will print it
        import uvicorn
        from .server import create_app_from_datasets
        
        app = create_app_from_datasets(
            datasets=datasets,
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
            show_source=show_source,
        )
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info" if verbose else "warning",
        )
    
    process = mp.Process(target=_worker, daemon=False)
    process.start()
    
    # Print single info message in parent process
    total_images = sum(len(paths) for paths in datasets.values())
    dataset_list = ", ".join(datasets.keys())
    
    print(f"""
┌─────────────────────────────────────────────────┐
│                   🔍 Lenslet                    │
│         Lightweight Image Gallery Server        │
├─────────────────────────────────────────────────┤
│  Datasets:  {dataset_list[:35]:<35} │
│  Images:    {total_images:<35} │
│  Server:    http://{host}:{port:<24} │
│  Mode:      Subprocess (non-blocking)           │
│  PID:       {process.pid:<35} │
└─────────────────────────────────────────────────┘

Gallery running at: http://{host}:{port}
""")
