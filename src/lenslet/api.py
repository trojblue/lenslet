"""Programmatic API for launching lenslet from Python/notebooks."""
from __future__ import annotations
import multiprocessing as mp


def launch(
    datasets: dict[str, list[str]] | object,
    blocking: bool = False,
    port: int = 7070,
    host: str = "127.0.0.1",
    thumb_size: int = 256,
    thumb_quality: int = 70,
    show_source: bool = True,
    verbose: bool = False,
    source_column: str | None = None,
    base_dir: str | None = None,
) -> None:
    """
    Launch lenslet with in-memory datasets.
    
    Args:
        datasets: Dict of {dataset_name: [list of image paths/URIs]} OR a single table
                 (pandas DataFrame, pyarrow.Table, or list of dicts). Table rows map to images
                 with local/S3/HTTP sources and optional metrics columns.
        blocking: If False (default), launches in subprocess. If True, runs in current process.
        port: Port to listen on (default: 7070)
        host: Host to bind to (default: 127.0.0.1)
        thumb_size: Thumbnail short edge size in pixels (default: 256)
        thumb_quality: Thumbnail WEBP quality 1-100 (default: 70)
        show_source: If True (default), show original source paths/URIs in the UI.
        verbose: If True, show all server logs. If False (default), only show errors.
        source_column: Optional explicit column name to load images from when using table mode.
        base_dir: Optional base directory for resolving relative local paths in table mode.
    
    Example:
        >>> import lenslet
        >>> datasets = {
        ...     "my_images": ["/path/to/img1.jpg", "/path/to/img2.png"],
        ...     "s3_images": ["s3://bucket/image1.jpg", "s3://bucket/image2.jpg"],
        ... }
        >>> lenslet.launch(datasets, blocking=False, port=7070)
    """
    if datasets is None:
        raise ValueError("datasets cannot be empty")

    mode = "datasets"
    if isinstance(datasets, dict):
        if not datasets:
            raise ValueError("datasets cannot be empty")
    else:
        if _is_table_like(datasets):
            mode = "table"
        else:
            raise ValueError("datasets must be a dict or a table-like object")

    if blocking:
        _launch_blocking(
            mode=mode,
            payload=datasets,
            port=port,
            host=host,
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
            show_source=show_source,
            verbose=verbose,
            source_column=source_column,
            base_dir=base_dir,
        )
    else:
        _launch_subprocess(
            mode=mode,
            payload=datasets,
            port=port,
            host=host,
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
            show_source=show_source,
            verbose=verbose,
            source_column=source_column,
            base_dir=base_dir,
        )


def _launch_blocking(
    mode: str,
    payload: object,
    port: int,
    host: str,
    thumb_size: int,
    thumb_quality: int,
    show_source: bool,
    verbose: bool,
    source_column: str | None,
    base_dir: str | None,
) -> None:
    """Launch in current process (blocking)."""
    import uvicorn
    from .server import create_app_from_datasets, create_app_from_table
    
    if mode == "table":
        total_images = _table_length(payload)
        source_label = source_column or "auto"
        print(f"""
┌─────────────────────────────────────────────────┐
│                   🔍 Lenslet                    │
│         Lightweight Image Gallery Server        │
├─────────────────────────────────────────────────┤
│  Rows:      {total_images:<35} │
│  Source:    {source_label[:35]:<35} │
│  Server:    http://{host}:{port:<24} │
│  Mode:      Table (programmatic API)            │
└─────────────────────────────────────────────────┘
""")
        app = create_app_from_table(
            table=payload,
            base_dir=base_dir,
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
            source_column=source_column,
            show_source=show_source,
        )
    else:
        datasets = payload
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
    mode: str,
    payload: object,
    port: int,
    host: str,
    thumb_size: int,
    thumb_quality: int,
    show_source: bool,
    verbose: bool,
    source_column: str | None,
    base_dir: str | None,
) -> None:
    """Launch in subprocess (non-blocking)."""
    # We'll use multiprocessing to launch in a separate process
    # This allows it to work in notebooks without blocking
    
    def _worker():
        # Don't print banner in worker - parent process will print it
        import uvicorn
        from .server import create_app_from_datasets, create_app_from_table

        if mode == "table":
            app = create_app_from_table(
                table=payload,
                base_dir=base_dir,
                thumb_size=thumb_size,
                thumb_quality=thumb_quality,
                source_column=source_column,
                show_source=show_source,
            )
        else:
            app = create_app_from_datasets(
                datasets=payload,
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
    
    if mode == "table":
        total_images = _table_length(payload)
        source_label = source_column or "auto"
        print(f"""
┌─────────────────────────────────────────────────┐
│                   🔍 Lenslet                    │
│         Lightweight Image Gallery Server        │
├─────────────────────────────────────────────────┤
│  Rows:      {total_images:<35} │
│  Source:    {source_label[:35]:<35} │
│  Server:    http://{host}:{port:<24} │
│  Mode:      Table (subprocess)                  │
│  PID:       {process.pid:<35} │
└─────────────────────────────────────────────────┘

Gallery running at: http://{host}:{port}
""")
    else:
        total_images = sum(len(paths) for paths in payload.values())
        dataset_list = ", ".join(payload.keys())

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


def _is_table_like(obj: object) -> bool:
    if isinstance(obj, list):
        return len(obj) == 0 or isinstance(obj[0], dict)
    if hasattr(obj, "to_pydict"):
        return True
    return hasattr(obj, "columns") and hasattr(obj, "to_dict")


def _table_length(obj: object) -> int:
    if isinstance(obj, list):
        return len(obj)
    if hasattr(obj, "num_rows"):
        return int(obj.num_rows)
    if hasattr(obj, "__len__"):
        return len(obj)  # type: ignore[arg-type]
    return 0
