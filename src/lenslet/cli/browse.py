"""Browse command implementation for the Lenslet CLI."""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .browse_args import BrowseCliArgs, _normalize_browse_args, _parse_browse_args_or_exit
from .common import _find_available_port
from .hf_table import RemoteTableLoadResult, is_hf_table_uri, load_hf_parquet_table
from .share import ShareTunnelOptions, _start_share_tunnel
from .. import server as server_api
from ..degraded import report_degraded_feature
from ..embeddings.config import EmbeddingConfig, parse_embedding_columns, parse_embedding_metrics
from ..indexing_status import CliIndexingReporter
from ..storage.table.input import TableInput
from ..storage.table.launch import TableLaunchRequest, TableLaunchResult, detect_source_column, prepare_table_launch
from ..terminal_banner import banner_row
from ..web.auth import trusted_write_origins_for_host
from ..workspace import Workspace


class BrowseCliError(RuntimeError):
    """Raised for browse command failures that should become CLI exit code 1."""


def _is_remote_uri(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"s3", "http", "https", "hf"}


def _looks_like_hf_dataset(value: str) -> bool:
    if "://" in value:
        return False
    if value.startswith(("/", ".", "~")):
        return False
    parts = value.split("/")
    if len(parts) != 2:
        return False
    org, repo = parts
    repo_base = repo.split("@", 1)[0]
    name_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    return bool(name_pattern.match(org)) and bool(name_pattern.match(repo_base))


def _load_remote_table(
    uri: str,
    *,
    source_column: str | None = None,
) -> RemoteTableLoadResult:
    if is_hf_table_uri(uri):
        return load_hf_parquet_table(uri, preferred_source_column=source_column)

    try:
        import unibox as ub
    except ImportError as exc:
        raise RuntimeError(
            'remote table loading requires unibox. Install with: pip install "lenslet[remote]"'
        ) from exc
    table = ub.loads(uri)
    if hasattr(table, "to_pandas"):
        table = table.to_pandas()
    return RemoteTableLoadResult(table=table)


@dataclass(frozen=True)
class BrowseTarget:
    raw_target: str
    target: Path | None
    is_table_file: bool
    is_remote_table: bool
    remote_kind: str | None = None
    remote_uri: str | None = None

    @property
    def is_dataset_dir(self) -> bool:
        return not self.is_remote_table and not self.is_table_file

    def with_table_target(self, target: Path) -> "BrowseTarget":
        return BrowseTarget(
            raw_target=self.raw_target,
            target=target,
            is_table_file=True,
            is_remote_table=False,
            remote_kind=None,
            remote_uri=None,
        )


@dataclass(frozen=True, slots=True)
class BrowseLaunchPlan:
    args: BrowseCliArgs
    target_info: BrowseTarget
    port: int
    embedding_config: EmbeddingConfig
    dataset_workspace: Workspace | None
    preindex_signature: str | None
    browse_options: server_api.BrowseAppOptions
    embedding_options: server_api.EmbeddingAppOptions
    trusted_write_origins: tuple[str, ...]


def _resolve_embedding_config_or_exit(args: BrowseCliArgs) -> EmbeddingConfig:
    try:
        return EmbeddingConfig(
            explicit_columns=parse_embedding_columns(args.embedding_column),
            metric_overrides=parse_embedding_metrics(args.embedding_metric),
        )
    except ValueError as exc:
        raise BrowseCliError(str(exc)) from exc


def _resolve_browse_target_or_exit(raw_target: str) -> BrowseTarget:
    candidate = Path(raw_target).expanduser()
    if candidate.exists():
        target = candidate.resolve()
        is_table_file = target.is_file() and target.suffix.lower() == ".parquet"
        if target.is_file() and not is_table_file:
            raise BrowseCliError(f"'{raw_target}' is not a .parquet file")
        if not target.is_file() and not target.is_dir():
            raise BrowseCliError(f"'{raw_target}' is not a valid directory or .parquet file")
        return BrowseTarget(
            raw_target=raw_target,
            target=target,
            is_table_file=is_table_file,
            is_remote_table=False,
        )
    if _is_remote_uri(raw_target):
        remote_kind = "hf" if urlparse(raw_target).scheme == "hf" else "remote"
        return BrowseTarget(
            raw_target=raw_target,
            target=None,
            is_table_file=False,
            is_remote_table=True,
            remote_kind=remote_kind,
            remote_uri=raw_target,
        )
    if _looks_like_hf_dataset(raw_target):
        return BrowseTarget(
            raw_target=raw_target,
            target=None,
            is_table_file=False,
            is_remote_table=True,
            remote_kind="hf",
            remote_uri=f"hf://{raw_target}",
        )
    raise BrowseCliError(f"'{raw_target}' does not exist")


def _emit_table_launch_notices(result: TableLaunchResult, *, quiet: bool = False) -> None:
    if quiet:
        return
    for notice in result.notices:
        if notice.kind == "embedding_detection_degraded":
            report_degraded_feature(
                "embedding cache preparation",
                detail=notice.message,
            )
            continue
        print(notice.message)


def _local_browse_target_or_exit(target_info: BrowseTarget) -> Path:
    if target_info.target is None:
        raise BrowseCliError("browse target must resolve to a local path")
    return target_info.target


def _maybe_embed_browse_target_or_exit(args: BrowseCliArgs, target_info: BrowseTarget) -> BrowseTarget:
    if args.embed and target_info.is_remote_table:
        raise BrowseCliError("--embed requires a local parquet file")
    if not (args.embed and target_info.is_table_file):
        return target_info

    candidate = _local_browse_target_or_exit(target_info)
    try:
        # Embedding generation pulls optional model/image dependencies; import it only for --embed.
        from ..embeddings.embedder import EmbedConfig, embed_parquet
        from ..storage.table.storage import load_parquet_schema
    except ImportError as exc:
        raise BrowseCliError(str(exc)) from exc

    base_dir = args.base_dir or str(candidate.parent)
    image_column = args.source_column
    if image_column is None:
        try:
            image_column = detect_source_column(str(candidate), base_dir)
        except (OSError, RuntimeError, ValueError) as exc:
            raise BrowseCliError(f"failed to detect image column: {exc}") from exc
    if image_column is None:
        raise BrowseCliError("--embed requires --source-column (or a detectable image column)")

    embed_output_path: Path | None = None
    embed_columns = parse_embedding_columns(args.embedding_column)
    embed_column = embed_columns[0] if embed_columns else "embedding_mobilenet_v3_small"
    if embed_columns and len(embed_columns) > 1:
        print("[lenslet] Warning: --embed uses the first --embedding-column value only.")

    try:
        schema = load_parquet_schema(str(candidate))
        if embed_column in schema.names:
            print(f"[lenslet] Embedding column '{embed_column}' already exists; skipping --embed.")
        else:
            config = EmbedConfig(
                embedding_column=embed_column,
                batch_size=args.batch_size,
                parquet_batch_size=args.parquet_batch_size,
                num_workers=args.num_workers,
                base_dir=base_dir,
            )
            embed_output_path = embed_parquet(
                parquet_path=candidate,
                image_column=image_column,
                config=config,
            )
            print(f"[lenslet] Wrote embeddings to {embed_output_path}")
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise BrowseCliError(f"embedding failed: {exc}") from exc

    if embed_output_path is None:
        return target_info
    return target_info.with_table_target(embed_output_path.resolve())


def _resolve_browse_port_or_exit(host: str, requested_port: int | None) -> int:
    if requested_port is not None:
        return requested_port
    try:
        port = _find_available_port(host, 7070)
    except RuntimeError as exc:
        raise BrowseCliError(str(exc)) from exc
    if port != 7070:
        print(f"[lenslet] Port 7070 is in use; using {port} instead.")
    return port


def _display_target_for_banner(target_info: BrowseTarget) -> str:
    if target_info.is_remote_table:
        return target_info.remote_uri or target_info.raw_target
    return str(_local_browse_target_or_exit(target_info))


def _storage_label_for_banner(target_info: BrowseTarget) -> str:
    if target_info.is_remote_table:
        return "Table index (hf dataset)" if target_info.remote_kind == "hf" else "Table index (remote)"
    target = _local_browse_target_or_exit(target_info)
    if target_info.is_table_file:
        return "Table index (parquet file)"
    has_parquet = (target / "items.parquet").is_file()
    return "Table index (items.parquet)" if has_parquet else "Filesystem dataset (auto index)"


def _workspace_label_for_banner(args: BrowseCliArgs, target_info: BrowseTarget) -> str:
    if target_info.is_remote_table:
        return "read-only (remote table)"
    if args.share:
        return "shared read-only"
    if args.no_write:
        return "temp cache (--no-write)"
    if target_info.is_table_file:
        return "writable (parquet sidecar)"
    return "writable (.lenslet workspace)"


def _print_browse_banner(args: BrowseCliArgs, target_info: BrowseTarget, port: int) -> None:
    display_target = _display_target_for_banner(target_info)
    storage_label = _storage_label_for_banner(target_info)
    workspace_label = _workspace_label_for_banner(args, target_info)
    server_url = f"http://{args.host}:{port}"
    banner_lines = [
        "┌─────────────────────────────────────────────────┐",
        "│                   🔍 Lenslet                    │",
        "│         Lightweight Image Gallery Server        │",
        "├─────────────────────────────────────────────────┤",
        banner_row("Target:", display_target),
        banner_row("Server:", server_url),
    ]
    if args.share:
        banner_lines.append(banner_row("Share:", "starting..."))
    banner_lines.extend(
        [
            banner_row("Storage:", storage_label),
            banner_row("Workspace:", workspace_label),
            "└─────────────────────────────────────────────────┘",
            "",
        ]
    )
    print("\n".join(banner_lines))


def _warn_multi_worker_mode() -> None:
    for env_name in ("UVICORN_WORKERS", "WEB_CONCURRENCY"):
        raw = os.getenv(env_name)
        if not raw:
            continue
        try:
            workers = int(raw)
        except ValueError:
            continue
        if workers > 1:
            print(
                f"[lenslet] Warning: {env_name}={workers} detected. "
                "Collaboration sync requires a single worker to avoid divergence."
            )
            return


def _prepare_dataset_workspace_or_exit(
    args: BrowseCliArgs,
    target_info: BrowseTarget,
) -> tuple[Workspace | None, str | None]:
    if not target_info.is_dataset_dir:
        return None, None

    target = _local_browse_target_or_exit(target_info)
    if args.no_write:
        dataset_workspace = Workspace.for_temp_dataset(str(target))
    else:
        dataset_workspace = Workspace.for_dataset(str(target), can_write=True)
    preindex_signature = None
    if args.share:
        # Share mode needs a stable preindex; keep its image-scan stack out of normal CLI startup.
        from ..storage.local.preindex import ensure_local_preindex

        try:
            preindex_result = ensure_local_preindex(target, dataset_workspace)
        except (OSError, RuntimeError, ValueError) as exc:
            raise BrowseCliError(f"preindex failed: {exc}") from exc

        if preindex_result is None:
            print("[lenslet] Preindex skipped: no images found.")
        else:
            if preindex_result.workspace.root != dataset_workspace.root:
                print(f"[lenslet] Preindex workspace: {preindex_result.workspace.root}")
            if preindex_result.reused:
                print(f"[lenslet] Preindex cache hit: {preindex_result.image_count} images.")
            else:
                print(f"[lenslet] Preindex ready: {preindex_result.image_count} images.")
            preindex_signature = preindex_result.signature
            dataset_workspace = preindex_result.workspace
    if args.no_write:
        print(
            f"[lenslet] No-write: using temp workspace {dataset_workspace.root} "
            "(thumb cache cap 200 MB)."
        )
    return dataset_workspace, preindex_signature


def _build_browse_runtime_options(
    args: BrowseCliArgs,
    embedding_config: EmbeddingConfig,
) -> tuple[server_api.BrowseAppOptions, server_api.EmbeddingAppOptions]:
    indexing_reporter = CliIndexingReporter()
    browse_options = server_api.BrowseAppOptions(
        thumb_size=args.thumb_size,
        thumb_quality=args.thumb_quality,
        thumb_cache=args.thumb_cache,
        indexing_listener=indexing_reporter.handle_update,
    )
    embedding_options = server_api.EmbeddingAppOptions(
        config=embedding_config,
        cache=args.embedding_cache,
        cache_dir=args.embedding_cache_dir,
        preload=args.embedding_preload,
    )
    return browse_options, embedding_options


def _trusted_write_origins_for_browse_launch(args: BrowseCliArgs, port: int) -> tuple[str, ...]:
    if args.share:
        return ()
    return trusted_write_origins_for_host(args.host, port)


def _create_remote_table_app_or_exit(plan: BrowseLaunchPlan) -> object:
    args = plan.args
    target_info = plan.target_info
    remote_label = target_info.remote_uri or target_info.raw_target
    try:
        loaded_table = _load_remote_table(remote_label, source_column=args.source_column)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise BrowseCliError(f"failed to load remote table '{remote_label}': {exc}") from exc
    source_column = args.source_column or loaded_table.source_column
    workspace = Workspace.for_dataset(None, can_write=False)
    return server_api.create_app_from_table(
        table=loaded_table.table,
        options=server_api.TableAppOptions(
            browse=plan.browse_options,
            embedding=plan.embedding_options,
            base_dir=args.base_dir,
            source_column=source_column,
            path_column=args.path_column,
            skip_dimension_probe=args.skip_dimension_probe,
            allow_local=False,
            og_preview=args.og_preview,
            workspace=workspace,
            trusted_write_origins=plan.trusted_write_origins,
        ),
    )


def _create_table_file_app_or_exit(plan: BrowseLaunchPlan, target: Path) -> object:
    args = plan.args
    workspace = (
        Workspace.for_temp_dataset(str(target))
        if args.no_write
        else Workspace.for_parquet(target, can_write=True)
    )
    launch_result = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=target,
            base_dir=args.base_dir,
            source_column=args.source_column,
            path_column=args.path_column,
            cache_dimensions=args.cache_dimensions,
            dimension_cache_dir=_dimension_cache_dir_for_launch(args, workspace),
            skip_dimension_probe=args.skip_dimension_probe,
            embedding_config=plan.embedding_config,
            auto_detect_root=True,
            thumb_size=args.thumb_size,
            thumb_quality=args.thumb_quality,
        )
    )
    _emit_table_launch_notices(launch_result)
    return server_api.create_app_from_storage(
        launch_result.storage,
        options=server_api.StorageAppOptions(
            browse=plan.browse_options,
            embedding=plan.embedding_options,
            show_source=True,
            workspace=workspace,
            og_preview=args.og_preview,
            embedding_table_path=str(target),
            storage_mode="table",
            storage_origin="parquet",
            refresh="static",
            trusted_write_origins=plan.trusted_write_origins,
        ),
    )


def _create_directory_app_or_exit(plan: BrowseLaunchPlan, target: Path) -> object:
    args = plan.args
    items_path = target / "items.parquet"
    table_launch = None
    if items_path.is_file():
        launch_result = prepare_table_launch(
            TableLaunchRequest(
                parquet_path=items_path,
                base_dir=args.base_dir or str(target),
                source_column=args.source_column,
                path_column=args.path_column,
                cache_dimensions=args.cache_dimensions,
                dimension_cache_dir=_dimension_cache_dir_for_launch(args, plan.dataset_workspace),
                skip_dimension_probe=args.skip_dimension_probe,
                embedding_config=plan.embedding_config,
                thumb_size=args.thumb_size,
                thumb_quality=args.thumb_quality,
            )
        )
        _emit_table_launch_notices(launch_result)
        table_launch = launch_result
    options = server_api.LocalAppOptions(
        browse=plan.browse_options,
        embedding=plan.embedding_options,
        no_write=args.no_write,
        source_column=args.source_column,
        path_column=args.path_column,
        skip_dimension_probe=args.skip_dimension_probe,
        og_preview=args.og_preview,
        workspace=plan.dataset_workspace,
        preindex_signature=plan.preindex_signature,
        trusted_write_origins=plan.trusted_write_origins,
    )
    if table_launch is None:
        return server_api.create_app(root_path=str(target), options=options)

    # The hybrid directory+items.parquet path needs the local app assembler's extra hook.
    from ..web.app.local import create_local_app

    return create_local_app(
        root_path=str(target),
        options=options,
        table_launch=table_launch,
    )


def _dimension_cache_dir_for_launch(args: BrowseCliArgs, workspace: Workspace | None) -> Path | None:
    if args.dimension_cache != "workspace" or workspace is None:
        return None
    return workspace.dimension_cache_dir()


def _create_browse_app_or_exit(plan: BrowseLaunchPlan) -> object:
    try:
        if plan.target_info.is_remote_table:
            return _create_remote_table_app_or_exit(plan)
        target = _local_browse_target_or_exit(plan.target_info)
        if plan.target_info.is_table_file:
            return _create_table_file_app_or_exit(plan, target)
        return _create_directory_app_or_exit(plan, target)
    except BrowseCliError:
        raise
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise BrowseCliError(f"failed to initialize browse mode: {exc}") from exc


def _launch_browse_server(app: object, args: BrowseCliArgs, port: int) -> None:
    import uvicorn

    share_tunnel = None
    try:
        if args.share:
            try:
                # Cache warmup imports metadata/media helpers, so keep it out of CLI help/import startup.
                from ..web.browse import warm_recursive_cache
                from ..web.context import get_app_context

                context = get_app_context(app)
                storage = context.storage
                browse_cache = context.recursive_browse_cache
                if storage is not None:
                    print("[lenslet] Warming recursive browse cache...")
                    warmed = warm_recursive_cache(
                        storage,
                        "/",
                        browse_cache,
                        hotpath_metrics=context.runtime.hotpath_metrics,
                    )
                    if warmed:
                        print(f"[lenslet] Recursive browse cache ready: {warmed} items.")
            except (AttributeError, OSError, RuntimeError, ValueError) as exc:
                report_degraded_feature(
                    "recursive browse cache warmup",
                    exc,
                    detail=f"failed to warm cache: {exc}",
                )
            try:
                share_tunnel = _start_share_tunnel(
                    ShareTunnelOptions(port=port, bind_host=args.host, verbose=args.verbose)
                )
            except (OSError, RuntimeError, ValueError) as exc:
                report_degraded_feature(
                    "share tunnel",
                    exc,
                    detail=f"failed to start: {exc}",
                    stream=sys.stderr,
                )
        uvicorn.run(
            app,
            host=args.host,
            port=port,
            reload=args.reload,
            log_level="info" if args.verbose else "warning",
        )
    finally:
        if share_tunnel is not None:
            share_tunnel.stop()


def _plan_browse_launch_or_exit(args: BrowseCliArgs) -> BrowseLaunchPlan:
    embedding_config = _resolve_embedding_config_or_exit(args)
    target_info = _resolve_browse_target_or_exit(args.directory)
    target_info = _maybe_embed_browse_target_or_exit(args, target_info)
    port = _resolve_browse_port_or_exit(args.host, args.port)
    normalized_args = _normalize_browse_args(args)
    trusted_write_origins = _trusted_write_origins_for_browse_launch(normalized_args, port)
    dataset_workspace, preindex_signature = _prepare_dataset_workspace_or_exit(normalized_args, target_info)
    browse_options, embedding_options = _build_browse_runtime_options(normalized_args, embedding_config)
    return BrowseLaunchPlan(
        args=normalized_args,
        target_info=target_info,
        port=port,
        embedding_config=embedding_config,
        dataset_workspace=dataset_workspace,
        preindex_signature=preindex_signature,
        browse_options=browse_options,
        embedding_options=embedding_options,
        trusted_write_origins=trusted_write_origins,
    )


def _run_browse(args: BrowseCliArgs) -> None:
    plan = _plan_browse_launch_or_exit(args)
    _print_browse_banner(plan.args, plan.target_info, plan.port)
    _warn_multi_worker_mode()

    app = _create_browse_app_or_exit(plan)
    _launch_browse_server(app, plan.args, plan.port)


def _main_browse(argv: list[str] | None = None) -> None:
    try:
        _run_browse(_parse_browse_args_or_exit(argv))
    except BrowseCliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
