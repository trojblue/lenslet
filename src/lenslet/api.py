"""Programmatic API for launching lenslet from Python/notebooks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import multiprocessing as mp

from . import server as server_api
from .storage.table.input import TableInput, is_table_input, table_input_length
from .terminal_banner import banner_row
from .web.auth import trusted_write_origins_for_host

AppBuilder = Callable[[], object]
BannerPrinter = Callable[[int | None], None]


@dataclass(frozen=True, slots=True)
class LaunchOptions:
    blocking: bool = False
    port: int = 7070
    host: str = "127.0.0.1"
    thumb_size: int = 256
    thumb_quality: int = 70
    show_source: bool = True
    verbose: bool = False


@dataclass(frozen=True, slots=True)
class TableLaunchOptions(LaunchOptions):
    source_column: str | None = None
    path_column: str | None = None
    base_dir: str | None = None


@dataclass(frozen=True, slots=True)
class ProgrammaticLaunchPlan:
    build_app: AppBuilder
    announce: BannerPrinter
    port: int
    host: str
    verbose: bool


def launch(
    datasets: dict[str, list[str]],
    options: LaunchOptions | None = None,
) -> None:
    """Launch Lenslet in dataset mode.

    For table-backed launches, use `launch_table(...)`.
    """
    if not isinstance(datasets, dict) or not datasets:
        raise ValueError("datasets must be a non-empty dict")
    options = options or LaunchOptions()

    app_options = server_api.BrowseAppOptions(
        thumb_size=options.thumb_size,
        thumb_quality=options.thumb_quality,
    )
    _launch_programmatic(
        blocking=options.blocking,
        plan=ProgrammaticLaunchPlan(
            build_app=lambda: server_api.create_app_from_datasets(
                datasets,
                options=server_api.DatasetAppOptions(
                    browse=app_options,
                    show_source=options.show_source,
                ),
            ),
            announce=lambda process_id=None: _print_dataset_launch_banner(
                datasets=datasets,
                host=options.host,
                port=options.port,
                process_id=process_id,
            ),
            port=options.port,
            host=options.host,
            verbose=options.verbose,
        ),
    )


def launch_table(
    table: TableInput,
    options: TableLaunchOptions | None = None,
) -> None:
    """Launch Lenslet from a pyarrow-like, pandas-like, or list-of-dicts table."""
    if not is_table_input(table):
        raise ValueError("table must be a table-like object")
    options = options or TableLaunchOptions()

    app_options = server_api.BrowseAppOptions(
        thumb_size=options.thumb_size,
        thumb_quality=options.thumb_quality,
    )
    _launch_programmatic(
        blocking=options.blocking,
        plan=ProgrammaticLaunchPlan(
            build_app=lambda: server_api.create_app_from_table(
                table=table,
                options=server_api.TableAppOptions(
                    browse=app_options,
                    base_dir=options.base_dir,
                    source_column=options.source_column,
                    path_column=options.path_column,
                    show_source=options.show_source,
                    trusted_write_origins=trusted_write_origins_for_host(options.host, options.port),
                ),
            ),
            announce=lambda process_id=None: _print_table_launch_banner(
                table=table,
                host=options.host,
                port=options.port,
                source_column=options.source_column,
                process_id=process_id,
            ),
            port=options.port,
            host=options.host,
            verbose=options.verbose,
        ),
    )


def _launch_programmatic(
    *,
    blocking: bool,
    plan: ProgrammaticLaunchPlan,
) -> None:
    if blocking:
        _launch_blocking_app(plan)
        return
    _launch_subprocess_app(plan)


def _launch_blocking_app(plan: ProgrammaticLaunchPlan) -> None:
    """Launch in current process (blocking)."""
    import uvicorn
    plan.announce()
    app = plan.build_app()

    uvicorn.run(
        app,
        host=plan.host,
        port=plan.port,
        log_level="info" if plan.verbose else "warning",
    )


def _launch_subprocess_app(plan: ProgrammaticLaunchPlan) -> None:
    """Launch in subprocess (non-blocking)."""

    def _worker() -> None:
        import uvicorn
        app = plan.build_app()

        uvicorn.run(
            app,
            host=plan.host,
            port=plan.port,
            log_level="info" if plan.verbose else "warning",
        )

    process = mp.Process(target=_worker, daemon=False)
    process.start()

    plan.announce(process.pid)


def _print_dataset_launch_banner(
    *,
    datasets: dict[str, list[str]],
    host: str,
    port: int,
    process_id: int | None = None,
) -> None:
    dataset_list = ", ".join(datasets.keys())
    total_images = sum(len(paths) for paths in datasets.values())
    mode_label = "In-memory (programmatic API)" if process_id is None else "Subprocess (non-blocking)"
    server_url = f"http://{host}:{port}"
    pid_row = f"{banner_row('PID:', process_id)}\n" if process_id is not None else ""
    footer = f"\nGallery running at: http://{host}:{port}\n" if process_id is not None else ""
    print(
        f"""
┌─────────────────────────────────────────────────┐
│                   🔍 Lenslet                    │
│         Lightweight Image Gallery Server        │
├─────────────────────────────────────────────────┤
{banner_row('Datasets:', dataset_list)}
{banner_row('Images:', total_images)}
{banner_row('Server:', server_url)}
{banner_row('Mode:', mode_label)}
{pid_row}└─────────────────────────────────────────────────┘
{footer}"""
    )


def _print_table_launch_banner(
    *,
    table: TableInput,
    host: str,
    port: int,
    source_column: str | None,
    process_id: int | None = None,
) -> None:
    total_images = table_input_length(table)
    source_label = source_column or "auto"
    mode_label = "Table (programmatic API)" if process_id is None else "Table (subprocess)"
    server_url = f"http://{host}:{port}"
    pid_row = f"{banner_row('PID:', process_id)}\n" if process_id is not None else ""
    footer = f"\nGallery running at: http://{host}:{port}\n" if process_id is not None else ""
    print(
        f"""
┌─────────────────────────────────────────────────┐
│                   🔍 Lenslet                    │
│         Lightweight Image Gallery Server        │
├─────────────────────────────────────────────────┤
{banner_row('Rows:', total_images)}
{banner_row('Source:', source_label)}
{banner_row('Server:', server_url)}
{banner_row('Mode:', mode_label)}
{pid_row}└─────────────────────────────────────────────────┘
{footer}"""
    )
