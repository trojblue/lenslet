"""Programmatic API for launching lenslet from Python/notebooks."""

from __future__ import annotations

from collections.abc import Callable
import multiprocessing as mp

AppBuilder = Callable[[], object]
BannerPrinter = Callable[[int | None], None]


def launch(
    datasets: dict[str, list[str]],
    *,
    blocking: bool = False,
    port: int = 7070,
    host: str = "127.0.0.1",
    thumb_size: int = 256,
    thumb_quality: int = 70,
    show_source: bool = True,
    verbose: bool = False,
) -> None:
    """Launch Lenslet in dataset mode.

    For table-backed launches, use `launch_table(...)`.
    """
    launch_datasets(
        datasets,
        blocking=blocking,
        port=port,
        host=host,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        show_source=show_source,
        verbose=verbose,
    )


def launch_datasets(
    datasets: dict[str, list[str]],
    *,
    blocking: bool = False,
    port: int = 7070,
    host: str = "127.0.0.1",
    thumb_size: int = 256,
    thumb_quality: int = 70,
    show_source: bool = True,
    verbose: bool = False,
) -> None:
    """Launch Lenslet from named in-memory datasets."""
    if not isinstance(datasets, dict) or not datasets:
        raise ValueError("datasets must be a non-empty dict")
    _launch_dataset_mode(
        datasets=datasets,
        blocking=blocking,
        port=port,
        host=host,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        show_source=show_source,
        verbose=verbose,
    )


def launch_table(
    table: object,
    *,
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
    """Launch Lenslet from a single table-like payload."""
    if not _is_table_like(table):
        raise ValueError("table must be a table-like object")
    _launch_table_mode(
        table=table,
        blocking=blocking,
        port=port,
        host=host,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        show_source=show_source,
        verbose=verbose,
        source_column=source_column,
        base_dir=base_dir,
    )


def _launch_dataset_mode(
    *,
    datasets: dict[str, list[str]],
    blocking: bool,
    port: int,
    host: str,
    thumb_size: int,
    thumb_quality: int,
    show_source: bool,
    verbose: bool,
) -> None:
    if blocking:
        _launch_blocking_app(
            build_app=lambda: _build_dataset_programmatic_app(
                datasets=datasets,
                thumb_size=thumb_size,
                thumb_quality=thumb_quality,
                show_source=show_source,
            ),
            announce=lambda process_id=None: _print_dataset_launch_banner(
                datasets=datasets,
                host=host,
                port=port,
                process_id=process_id,
            ),
            port=port,
            host=host,
            verbose=verbose,
        )
        return
    _launch_subprocess_app(
        build_app=lambda: _build_dataset_programmatic_app(
            datasets=datasets,
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
            show_source=show_source,
        ),
        announce=lambda process_id=None: _print_dataset_launch_banner(
            datasets=datasets,
            host=host,
            port=port,
            process_id=process_id,
        ),
        port=port,
        host=host,
        verbose=verbose,
    )


def _launch_table_mode(
    *,
    table: object,
    blocking: bool,
    port: int,
    host: str,
    thumb_size: int,
    thumb_quality: int,
    show_source: bool,
    verbose: bool,
    source_column: str | None,
    base_dir: str | None,
) -> None:
    if blocking:
        _launch_blocking_app(
            build_app=lambda: _build_table_programmatic_app(
                table=table,
                thumb_size=thumb_size,
                thumb_quality=thumb_quality,
                show_source=show_source,
                source_column=source_column,
                base_dir=base_dir,
            ),
            announce=lambda process_id=None: _print_table_launch_banner(
                table=table,
                host=host,
                port=port,
                source_column=source_column,
                process_id=process_id,
            ),
            port=port,
            host=host,
            verbose=verbose,
        )
        return
    _launch_subprocess_app(
        build_app=lambda: _build_table_programmatic_app(
            table=table,
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
            show_source=show_source,
            source_column=source_column,
            base_dir=base_dir,
        ),
        announce=lambda process_id=None: _print_table_launch_banner(
            table=table,
            host=host,
            port=port,
            source_column=source_column,
            process_id=process_id,
        ),
        port=port,
        host=host,
        verbose=verbose,
    )


def _launch_blocking_app(
    *,
    build_app: AppBuilder,
    announce: BannerPrinter,
    port: int,
    host: str,
    verbose: bool,
) -> None:
    """Launch in current process (blocking)."""
    import uvicorn
    announce()
    app = build_app()

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info" if verbose else "warning",
    )


def _launch_subprocess_app(
    *,
    build_app: AppBuilder,
    announce: BannerPrinter,
    port: int,
    host: str,
    verbose: bool,
) -> None:
    """Launch in subprocess (non-blocking)."""

    def _worker() -> None:
        import uvicorn
        app = build_app()

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info" if verbose else "warning",
        )

    process = mp.Process(target=_worker, daemon=False)
    process.start()

    announce(process.pid)


def _build_dataset_programmatic_app(
    *,
    datasets: dict[str, list[str]],
    thumb_size: int,
    thumb_quality: int,
    show_source: bool,
):
    from .server import create_app_from_datasets

    return create_app_from_datasets(
        datasets,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        show_source=show_source,
    )


def _build_table_programmatic_app(
    *,
    table: object,
    thumb_size: int,
    thumb_quality: int,
    show_source: bool,
    source_column: str | None,
    base_dir: str | None,
):
    from .server import create_app_from_table

    return create_app_from_table(
        table=table,
        base_dir=base_dir,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        source_column=source_column,
        show_source=show_source,
    )


def _print_dataset_launch_banner(
    *,
    datasets: dict[str, list[str]],
    host: str,
    port: int,
    process_id: int | None = None,
) -> None:
    dataset_list = ", ".join(datasets.keys())[:35]
    total_images = sum(len(paths) for paths in datasets.values())
    mode_label = "In-memory (programmatic API)" if process_id is None else "Subprocess (non-blocking)"
    pid_row = f"│  PID:       {process_id:<35} │\n" if process_id is not None else ""
    footer = f"\nGallery running at: http://{host}:{port}\n" if process_id is not None else ""
    print(
        f"""
┌─────────────────────────────────────────────────┐
│                   🔍 Lenslet                    │
│         Lightweight Image Gallery Server        │
├─────────────────────────────────────────────────┤
│  Datasets:  {dataset_list:<35} │
│  Images:    {total_images:<35} │
│  Server:    http://{host}:{port:<24} │
│  Mode:      {mode_label:<35} │
{pid_row}└─────────────────────────────────────────────────┘
{footer}"""
    )


def _print_table_launch_banner(
    *,
    table: object,
    host: str,
    port: int,
    source_column: str | None,
    process_id: int | None = None,
) -> None:
    total_images = _table_length(table)
    source_label = (source_column or "auto")[:35]
    mode_label = "Table (programmatic API)" if process_id is None else "Table (subprocess)"
    pid_row = f"│  PID:       {process_id:<35} │\n" if process_id is not None else ""
    footer = f"\nGallery running at: http://{host}:{port}\n" if process_id is not None else ""
    print(
        f"""
┌─────────────────────────────────────────────────┐
│                   🔍 Lenslet                    │
│         Lightweight Image Gallery Server        │
├─────────────────────────────────────────────────┤
│  Rows:      {total_images:<35} │
│  Source:    {source_label:<35} │
│  Server:    http://{host}:{port:<24} │
│  Mode:      {mode_label:<35} │
{pid_row}└─────────────────────────────────────────────────┘
{footer}"""
    )


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
