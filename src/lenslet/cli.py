"""CLI entry point for Lenslet."""
from __future__ import annotations
import argparse
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .embeddings.config import EmbeddingConfig
    from .server import BrowseAppOptions, EmbeddingAppOptions
    from .storage.table import TableStorage
    from .workspace import Workspace


def _is_remote_uri(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
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


def _load_remote_table(uri: str):
    try:
        import unibox as ub
    except ImportError as exc:
        raise RuntimeError(
            "unibox is required to load remote tables. Install with: pip install unibox"
        ) from exc
    table = ub.loads(uri)
    if hasattr(table, "to_pandas"):
        table = table.to_pandas()
    return table


def _port_is_available(host: str, port: int) -> bool:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for family, socktype, proto, _, sockaddr in infos:
        try:
            with socket.socket(family, socktype, proto) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(sockaddr)
                return True
        except OSError:
            continue
    return False


def _find_available_port(host: str, start_port: int = 7070, max_tries: int = 50) -> int:
    for offset in range(max_tries):
        port = start_port + offset
        if _port_is_available(host, port):
            return port
    raise RuntimeError(
        f"No available port found from {start_port} to {start_port + max_tries - 1}."
    )


def _ensure_cloudflared_binary() -> Path:
    configured_path = os.getenv("LENSLET_CLOUDFLARED_BIN", "").strip()
    if configured_path:
        binary_path = Path(configured_path).expanduser()
        if not binary_path.is_file():
            raise RuntimeError(
                "LENSLET_CLOUDFLARED_BIN must point to an existing cloudflared binary."
            )
        if not os.access(binary_path, os.X_OK):
            raise RuntimeError("LENSLET_CLOUDFLARED_BIN must point to an executable file.")
        return binary_path

    discovered = shutil.which("cloudflared")
    if discovered:
        return Path(discovered)

    raise RuntimeError(
        "cloudflared is required for --share. Install cloudflared and ensure it is on PATH, "
        "or set LENSLET_CLOUDFLARED_BIN to a trusted executable path."
    )


def _tunnel_target_host(bind_host: str) -> str:
    if bind_host in {"127.0.0.1", "0.0.0.0", "localhost", "::1"}:
        return "localhost"
    return bind_host


class _ShareTunnel:
    def __init__(
        self,
        thread: threading.Thread,
        stop_event: threading.Event,
        process_ref: list[subprocess.Popen[str] | None],
        lock: threading.Lock,
    ) -> None:
        self._thread = thread
        self._stop_event = stop_event
        self._process_ref = process_ref
        self._lock = lock

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            process = self._process_ref[0]
        if process is not None:
            _stop_process(process)


def _start_share_tunnel(
    port: int,
    bind_host: str,
    verbose: bool,
    max_retries: int = 3,
    reachable_timeout: float = 20.0,
) -> _ShareTunnel:
    ansi_escape = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
    trycloudflare_pattern = re.compile(r"https?://[A-Za-z0-9.-]*trycloudflare\.com\S*")

    def _launch() -> subprocess.Popen[str]:
        binary_path = _ensure_cloudflared_binary()
        target_host = _tunnel_target_host(bind_host)
        cmd = [str(binary_path), "tunnel", "--url", f"{target_host}:{port}"]
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

    def _read_share_url(process: subprocess.Popen[str]) -> str | None:
        if process.stdout is None:
            raise RuntimeError("Failed to start cloudflared: no stdout pipe available.")
        for raw in process.stdout:
            line = raw.rstrip()
            if verbose:
                print(f"[cloudflared] {line}")
            cleaned = ansi_escape.sub("", line)
            match = trycloudflare_pattern.search(cleaned)
            if match:
                return match.group(0).rstrip(").,")
        return None

    def _drain_output(lines: Iterable[str], stop_event: threading.Event) -> None:
        for raw in lines:
            if stop_event.is_set():
                break
            if verbose:
                print(f"[cloudflared] {raw.rstrip()}")

    def _wait_for_reachable(url: str, stop_event: threading.Event) -> bool:
        import urllib.error
        import urllib.request

        deadline = time.monotonic() + reachable_timeout
        while True:
            if stop_event.is_set():
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            timeout = max(0.5, min(3.0, remaining))
            try:
                request = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(request, timeout=timeout):
                    return True
            except urllib.error.HTTPError:
                return True
            except Exception:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.5)

    stop_event = threading.Event()
    process_ref: list[subprocess.Popen[str] | None] = [None]
    lock = threading.Lock()

    def _runner() -> None:
        try:
            last_error = "Share tunnel exited before a URL was created."
            for attempt in range(1, max_retries + 1):
                if stop_event.is_set():
                    return
                process = _launch()
                with lock:
                    process_ref[0] = process
                share_url = _read_share_url(process)
                if share_url is None:
                    if process.poll() not in (None, 0):
                        print("[lenslet] Share tunnel exited before a URL was created.", file=sys.stderr)
                    _stop_process(process)
                    continue
                _print_share_url(share_url)
                if process.stdout is None:
                    raise RuntimeError("Failed to start cloudflared: no stdout pipe available.")
                drain_thread = threading.Thread(
                    target=_drain_output,
                    args=(process.stdout, stop_event),
                    daemon=True,
                )
                drain_thread.start()
                if not _wait_for_reachable(share_url, stop_event):
                    print(
                        "[lenslet] Share URL not reachable within 20 seconds.",
                        file=sys.stderr,
                    )
                return
            if not stop_event.is_set():
                print(f"[lenslet] {last_error}", file=sys.stderr)
        except Exception as exc:
            if not stop_event.is_set():
                print(f"[lenslet] Share tunnel failed: {exc}", file=sys.stderr)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    return _ShareTunnel(thread, stop_event, process_ref, lock)


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _print_share_url(url: str) -> None:
    print(f"Share URL: {url}", file=sys.stderr, flush=True)


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

    def with_target(self, target: Path) -> "BrowseTarget":
        return BrowseTarget(
            raw_target=self.raw_target,
            target=target,
            is_table_file=True,
            is_remote_table=False,
            remote_kind=None,
            remote_uri=None,
        )


@dataclass(frozen=True, slots=True)
class BrowseCliArgs:
    directory: str
    host: str
    port: int | None
    thumb_size: int
    thumb_quality: int
    source_column: str | None
    base_dir: str | None
    cache_wh: bool
    skip_indexing: bool
    thumb_cache: bool
    og_preview: bool
    reload: bool
    no_write: bool
    embedding_column: list[str] | None
    embedding_metric: list[str] | None
    embed: bool
    batch_size: int
    parquet_batch_size: int
    num_workers: int
    embedding_preload: bool
    embedding_cache: bool
    embedding_cache_dir: str | None
    verbose: bool
    share: bool

    @classmethod
    def from_namespace(cls, args: argparse.Namespace) -> "BrowseCliArgs":
        return cls(
            directory=str(args.directory),
            host=str(args.host),
            port=args.port,
            thumb_size=int(args.thumb_size),
            thumb_quality=int(args.thumb_quality),
            source_column=args.source_column,
            base_dir=args.base_dir,
            cache_wh=bool(args.cache_wh),
            skip_indexing=bool(args.skip_indexing),
            thumb_cache=bool(args.thumb_cache),
            og_preview=bool(args.og_preview),
            reload=bool(args.reload),
            no_write=bool(args.no_write),
            embedding_column=list(args.embedding_column) if args.embedding_column else None,
            embedding_metric=list(args.embedding_metric) if args.embedding_metric else None,
            embed=bool(args.embed),
            batch_size=int(args.batch_size),
            parquet_batch_size=int(args.parquet_batch_size),
            num_workers=int(args.num_workers),
            embedding_preload=bool(args.embedding_preload),
            embedding_cache=bool(args.embedding_cache),
            embedding_cache_dir=args.embedding_cache_dir,
            verbose=bool(args.verbose),
            share=bool(args.share),
        )


@dataclass(frozen=True, slots=True)
class BrowseLaunchPlan:
    args: BrowseCliArgs
    target_info: BrowseTarget
    port: int
    embedding_config: Any
    dataset_workspace: Any | None
    preindex_signature: str | None
    browse_options: Any
    embedding_options: Any


def _resolve_embedding_config_or_exit(args: BrowseCliArgs) -> "EmbeddingConfig":
    from .embeddings.config import EmbeddingConfig, parse_embedding_columns, parse_embedding_metrics

    try:
        return EmbeddingConfig(
            explicit_columns=parse_embedding_columns(args.embedding_column),
            metric_overrides=parse_embedding_metrics(args.embedding_metric),
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _resolve_browse_target_or_exit(raw_target: str) -> BrowseTarget:
    candidate = Path(raw_target).expanduser()
    if candidate.exists():
        target = candidate.resolve()
        is_table_file = target.is_file() and target.suffix.lower() == ".parquet"
        if target.is_file() and not is_table_file:
            print(f"Error: '{raw_target}' is not a .parquet file", file=sys.stderr)
            sys.exit(1)
        if not target.is_file() and not target.is_dir():
            print(f"Error: '{raw_target}' is not a valid directory or .parquet file", file=sys.stderr)
            sys.exit(1)
        return BrowseTarget(
            raw_target=raw_target,
            target=target,
            is_table_file=is_table_file,
            is_remote_table=False,
        )
    if _is_remote_uri(raw_target):
        return BrowseTarget(
            raw_target=raw_target,
            target=None,
            is_table_file=False,
            is_remote_table=True,
            remote_kind="remote",
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
    print(f"Error: '{raw_target}' does not exist", file=sys.stderr)
    sys.exit(1)


def _local_browse_target_or_exit(target_info: BrowseTarget) -> Path:
    if target_info.target is None:
        print("Error: browse target must resolve to a local path", file=sys.stderr)
        sys.exit(1)
    return target_info.target


def _maybe_embed_browse_target_or_exit(args: BrowseCliArgs, target_info: BrowseTarget) -> BrowseTarget:
    if args.embed and target_info.is_remote_table:
        print("Error: --embed requires a local parquet file", file=sys.stderr)
        sys.exit(1)
    if not (args.embed and target_info.is_table_file):
        return target_info

    candidate = _local_browse_target_or_exit(target_info)
    try:
        from .embeddings.config import parse_embedding_columns
        from .embeddings.embedder import EmbedConfig, embed_parquet
        from .storage.table import load_parquet_schema
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    base_dir = args.base_dir or str(candidate.parent)
    image_column = args.source_column
    if image_column is None:
        try:
            image_column = _detect_source_column(str(candidate), base_dir)
        except Exception as exc:
            print(f"Error: failed to detect image column: {exc}", file=sys.stderr)
            sys.exit(1)
    if image_column is None:
        print("Error: --embed requires --source-column (or a detectable image column)", file=sys.stderr)
        sys.exit(1)

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
    except Exception as exc:
        print(f"Error: embedding failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if embed_output_path is None:
        return target_info
    return target_info.with_target(embed_output_path.resolve())


def _resolve_browse_port_or_exit(host: str, requested_port: int | None) -> int:
    if requested_port is not None:
        return requested_port
    try:
        port = _find_available_port(host, 7070)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
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
        return "local-write / shared-read-only"
    if args.no_write:
        return "temp cache (--no-write)"
    if target_info.is_table_file:
        return "writable (parquet sidecar)"
    return "writable (.lenslet workspace)"


def _print_browse_banner(args: BrowseCliArgs, target_info: BrowseTarget, port: int) -> None:
    display_target = _display_target_for_banner(target_info)
    storage_label = _storage_label_for_banner(target_info)
    workspace_label = _workspace_label_for_banner(args, target_info)
    banner_lines = [
        "┌─────────────────────────────────────────────────┐",
        "│                   🔍 Lenslet                    │",
        "│         Lightweight Image Gallery Server        │",
        "├─────────────────────────────────────────────────┤",
        f"│  Target:    {display_target[:35]:<35} │",
        f"│  Server:    http://{args.host}:{port:<24} │",
    ]
    if args.share:
        banner_lines.append("│  Share:     starting...                         │")
    banner_lines.extend(
        [
            f"│  Storage:   {storage_label:<35} │",
            f"│  Workspace: {workspace_label:<35} │",
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
) -> tuple["Workspace | None", str | None]:
    if not target_info.is_dataset_dir:
        return None, None

    from .workspace import Workspace

    target = _local_browse_target_or_exit(target_info)
    if args.no_write:
        dataset_workspace = Workspace.for_temp_dataset(str(target))
    else:
        dataset_workspace = Workspace.for_dataset(str(target), can_write=True)
    preindex_signature = None
    if args.share:
        from .preindex import ensure_local_preindex

        try:
            preindex_result = ensure_local_preindex(target, dataset_workspace)
        except Exception as exc:
            print(f"Error: preindex failed: {exc}", file=sys.stderr)
            sys.exit(1)

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
    embedding_config: "EmbeddingConfig",
) -> tuple["BrowseAppOptions", "EmbeddingAppOptions"]:
    from .indexing_status import CliIndexingReporter
    from .server import BrowseAppOptions, EmbeddingAppOptions

    indexing_reporter = CliIndexingReporter()
    browse_options = BrowseAppOptions(
        thumb_size=args.thumb_size,
        thumb_quality=args.thumb_quality,
        thumb_cache=args.thumb_cache,
        indexing_listener=indexing_reporter.handle_update,
    )
    embedding_options = EmbeddingAppOptions(
        config=embedding_config,
        cache=args.embedding_cache,
        cache_dir=args.embedding_cache_dir,
        preload=args.embedding_preload,
    )
    return browse_options, embedding_options


def _create_browse_app_or_exit(
    args: BrowseCliArgs,
    target_info: BrowseTarget,
    *,
    dataset_workspace: "Workspace | None",
    preindex_signature: str | None,
    embedding_config: "EmbeddingConfig",
    browse_options: "BrowseAppOptions",
    embedding_options: "EmbeddingAppOptions",
) -> object:
    from .server import create_app, create_app_from_storage, create_app_from_table
    from .workspace import Workspace

    try:
        if target_info.is_remote_table:
            remote_label = target_info.remote_uri or target_info.raw_target
            try:
                table = _load_remote_table(remote_label)
            except Exception as exc:
                print(f"Error: failed to load remote table '{remote_label}': {exc}", file=sys.stderr)
                sys.exit(1)
            workspace = Workspace.for_dataset(None, can_write=False)
            return create_app_from_table(
                table=table,
                base_dir=args.base_dir,
                source_column=args.source_column,
                skip_indexing=args.skip_indexing,
                allow_local=False,
                og_preview=args.og_preview,
                workspace=workspace,
                options=browse_options,
                embedding=embedding_options,
            )

        target = _local_browse_target_or_exit(target_info)
        if target_info.is_table_file:
            storage = _prepare_table_cache(
                parquet_path=target,
                base_dir=args.base_dir,
                source_column=args.source_column,
                cache_wh=args.cache_wh,
                skip_indexing=args.skip_indexing,
                embedding_config=embedding_config,
                auto_detect_root=True,
            )
            if args.no_write:
                workspace = Workspace.for_temp_dataset(str(target))
            else:
                workspace = Workspace.for_parquet(target, can_write=True)
            return create_app_from_storage(
                storage,
                show_source=True,
                workspace=workspace,
                og_preview=args.og_preview,
                embedding_parquet_path=str(target),
                options=browse_options,
                embedding=embedding_options,
            )

        items_path = target / "items.parquet"
        if items_path.is_file() and args.cache_wh:
            _prepare_table_cache(
                parquet_path=items_path,
                base_dir=str(target),
                source_column=args.source_column,
                cache_wh=args.cache_wh,
                skip_indexing=args.skip_indexing,
                quiet=True,
                embedding_config=embedding_config,
            )
        return create_app(
            root_path=str(target),
            no_write=args.no_write,
            source_column=args.source_column,
            skip_indexing=args.skip_indexing,
            og_preview=args.og_preview,
            workspace=dataset_workspace,
            preindex_signature=preindex_signature,
            options=browse_options,
            embedding=embedding_options,
        )
    except Exception as exc:
        print(f"Error: failed to initialize browse mode: {exc}", file=sys.stderr)
        sys.exit(1)


def _launch_browse_server(app: object, args: BrowseCliArgs, port: int) -> None:
    import uvicorn

    share_tunnel = None
    try:
        if args.share:
            try:
                from .web.browse import warm_recursive_cache

                storage = getattr(app.state, "storage", None)
                browse_cache = getattr(app.state, "recursive_browse_cache", None)
                if storage is not None:
                    print("[lenslet] Warming recursive browse cache...")
                    warmed = warm_recursive_cache(
                        storage,
                        "/",
                        browse_cache,
                        hotpath_metrics=getattr(app.state, "hotpath_metrics", None),
                    )
                    if warmed:
                        print(f"[lenslet] Recursive browse cache ready: {warmed} items.")
            except Exception as exc:
                print(f"[lenslet] Warning: failed to warm recursive browse cache: {exc}")
            try:
                share_tunnel = _start_share_tunnel(port, args.host, args.verbose)
            except Exception as exc:
                print(f"[lenslet] Failed to start share tunnel: {exc}", file=sys.stderr)
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


def _build_browse_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lenslet",
        description="Lenslet - Lightweight image gallery server",
        epilog="Example: lenslet ~/Pictures --port 7070",
    )
    parser.add_argument(
        "directory",
        type=str,
        nargs="?",  # Make optional for --version/--help
        help="Directory containing images, a Parquet table, or an HF dataset (org/dataset) to serve",
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=None,
        help="Port to listen on (default: 7070; auto-increment if in use)",
    )
    parser.add_argument(
        "-H", "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--thumb-size",
        type=int,
        default=256,
        help="Thumbnail short edge size in pixels (default: 256)",
    )
    parser.add_argument(
        "--thumb-quality",
        type=int,
        default=70,
        help="Thumbnail WEBP quality 1-100 (default: 70)",
    )
    parser.add_argument(
        "--source-column",
        type=str,
        default=None,
        help="Column to load images from in table mode (items.parquet or .parquet file)",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=None,
        help="Base directory for resolving relative paths in table mode",
    )
    parser.add_argument(
        "--no-cache-wh",
        action="store_false",
        dest="cache_wh",
        default=True,
        help="Disable caching width/height back into parquet",
    )
    parser.add_argument(
        "--no-skip-indexing",
        action="store_false",
        dest="skip_indexing",
        default=True,
        help="Probe image dimensions during table load",
    )
    parser.add_argument(
        "--no-thumb-cache",
        action="store_false",
        dest="thumb_cache",
        default=True,
        help="Disable thumbnail cache when a workspace is available",
    )
    parser.add_argument(
        "--no-og-preview",
        action="store_false",
        dest="og_preview",
        default=True,
        help="Disable dataset-based social preview image",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Use a temp workspace under /tmp/lenslet (keeps the source dataset read-only)",
    )
    parser.add_argument(
        "--embedding-column",
        action="append",
        default=None,
        help="Embedding column name (repeatable, comma-separated allowed)",
    )
    parser.add_argument(
        "--embedding-metric",
        action="append",
        default=None,
        help="Embedding metric override in NAME:METRIC form (repeatable)",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Run CPU embedding inference on a parquet file before launch",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Embedding inference batch size (used with --embed)",
    )
    parser.add_argument(
        "--parquet-batch-size",
        type=int,
        default=256,
        help="Rows per parquet batch when embedding (used with --embed)",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=8,
        help="Parallel image loading workers (used with --embed)",
    )
    parser.add_argument(
        "--embedding-preload",
        action="store_true",
        help="Preload embedding indexes on startup",
    )
    parser.add_argument(
        "--embedding-cache",
        action="store_true",
        dest="embedding_cache",
        default=True,
        help="Enable embedding cache (default)",
    )
    parser.add_argument(
        "--no-embedding-cache",
        action="store_false",
        dest="embedding_cache",
        help="Disable embedding cache",
    )
    parser.add_argument(
        "--embedding-cache-dir",
        type=str,
        default=None,
        help="Override embedding cache directory",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed server logs",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Create a public share URL via cloudflared",
    )
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="Show version and exit",
    )
    return parser


def _parse_browse_args_or_exit(argv: list[str] | None) -> BrowseCliArgs:
    parser = _build_browse_parser()
    args = parser.parse_args(argv)

    if args.version:
        from . import __version__

        print(f"lenslet {__version__}")
        sys.exit(0)

    if not args.directory:
        parser.print_help()
        sys.exit(1)

    return BrowseCliArgs.from_namespace(args)


def _normalize_browse_args(args: BrowseCliArgs) -> BrowseCliArgs:
    if args.no_write and args.cache_wh:
        print("[lenslet] --no-write disables parquet caching; use --no-cache-wh to silence.")
        return replace(args, cache_wh=False)
    return args


def _plan_browse_launch_or_exit(args: BrowseCliArgs) -> BrowseLaunchPlan:
    embedding_config = _resolve_embedding_config_or_exit(args)
    target_info = _resolve_browse_target_or_exit(args.directory)
    target_info = _maybe_embed_browse_target_or_exit(args, target_info)
    port = _resolve_browse_port_or_exit(args.host, args.port)
    normalized_args = _normalize_browse_args(args)
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
    )


def _create_browse_app_for_plan_or_exit(plan: BrowseLaunchPlan):
    return _create_browse_app_or_exit(
        plan.args,
        plan.target_info,
        dataset_workspace=plan.dataset_workspace,
        preindex_signature=plan.preindex_signature,
        embedding_config=plan.embedding_config,
        browse_options=plan.browse_options,
        embedding_options=plan.embedding_options,
    )


def _run_browse(args: BrowseCliArgs) -> None:
    plan = _plan_browse_launch_or_exit(args)
    _print_browse_banner(plan.args, plan.target_info, plan.port)
    _warn_multi_worker_mode()

    app = _create_browse_app_for_plan_or_exit(plan)
    _launch_browse_server(app, plan.args, plan.port)


def _main_rank(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="lenslet rank",
        description="Lenslet ranking mode server",
        epilog="Example: lenslet rank ./ranking_dataset.json --port 7070",
    )
    parser.add_argument(
        "dataset_json",
        type=str,
        help="Path to ranking dataset JSON",
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=None,
        help="Port to listen on (default: 7070; auto-increment if in use)",
    )
    parser.add_argument(
        "-H", "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--results-path",
        type=str,
        default=None,
        help="Optional results JSONL path. Relative values resolve from the dataset JSON directory.",
    )
    args = parser.parse_args(argv)

    dataset_path = Path(args.dataset_json).expanduser()
    if not dataset_path.exists():
        print(f"Error: dataset file does not exist: {args.dataset_json}", file=sys.stderr)
        sys.exit(1)
    if not dataset_path.is_file():
        print(f"Error: dataset path must be a file: {args.dataset_json}", file=sys.stderr)
        sys.exit(1)
    dataset_path = dataset_path.resolve()

    port = args.port
    if port is None:
        try:
            port = _find_available_port(args.host, 7070)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        if port != 7070:
            print(f"[lenslet] Port 7070 is in use; using {port} instead.")

    import uvicorn
    from .ranking.app import create_ranking_app

    try:
        app = create_ranking_app(
            dataset_path,
            results_path=args.results_path,
        )
    except Exception as exc:
        print(f"Error: failed to initialize ranking mode: {exc}", file=sys.stderr)
        sys.exit(1)

    results_path = getattr(app.state, "ranking_results_path", None)
    dataset_label = str(dataset_path)
    display_results = str(results_path) if results_path is not None else "unknown"
    banner_lines = [
        "┌─────────────────────────────────────────────────┐",
        "│                   🔍 Lenslet                    │",
        "│               Ranking Mode Server               │",
        "├─────────────────────────────────────────────────┤",
        f"│  Dataset:   {dataset_label[:35]:<35} │",
        f"│  Server:    http://{args.host}:{port:<24} │",
        f"│  Results:   {display_results[:35]:<35} │",
        "└─────────────────────────────────────────────────┘",
        "",
    ]
    print("\n".join(banner_lines))

    uvicorn.run(
        app,
        host=args.host,
        port=port,
        reload=args.reload,
        log_level="warning",
    )


def _main_browse(argv: list[str] | None = None) -> None:
    _run_browse(_parse_browse_args_or_exit(argv))


def _prepare_table_cache(
    parquet_path: Path,
    base_dir: str | None,
    source_column: str | None,
    cache_wh: bool,
    skip_indexing: bool,
    quiet: bool = False,
    embedding_config=None,
    auto_detect_root: bool = False,
) -> TableStorage:
    from .storage.table import TableStorage, load_parquet_table
    columns = None
    if embedding_config is not None:
        try:
            from .embeddings.detect import columns_without_embeddings, detect_embeddings
            from .storage.table import load_parquet_schema
            schema = load_parquet_schema(str(parquet_path))
            detection = detect_embeddings(schema, embedding_config)
            columns = columns_without_embeddings(schema, detection)
        except Exception as exc:
            if not quiet:
                print(f"[lenslet] Warning: failed to detect embedding columns: {exc}")
    table = load_parquet_table(str(parquet_path), columns=columns)
    width_name = _find_column_name(table, "width")
    height_name = _find_column_name(table, "height")
    missing = _count_missing_dims(table, width_name, height_name)

    effective_skip = skip_indexing
    if cache_wh and skip_indexing and missing > 0:
        effective_skip = False
        if not quiet:
            print("[lenslet] cache-wh enabled; missing width/height -> indexing to populate cache.")

    effective_root = _resolve_table_root(
        parquet_path=parquet_path,
        table=table,
        source_column=source_column,
        base_dir=base_dir,
        auto_detect_root=auto_detect_root,
    )
    if auto_detect_root and effective_root and effective_root != base_dir and not quiet:
        print(f"[lenslet] Auto-detected local source root: {effective_root}")

    storage = TableStorage(
        table=table,
        root=effective_root,
        source_column=source_column,
        skip_indexing=effective_skip,
    )

    if cache_wh:
        updated = _maybe_write_dimensions(
            parquet_path=parquet_path,
            table=table,
            width_name=width_name,
            height_name=height_name,
            row_dims=storage.row_dimensions(),
        )
        if updated and not quiet:
            print(f"[lenslet] Cached width/height into {parquet_path}")

    return storage


def _resolve_table_root(
    *,
    parquet_path: Path,
    table,
    source_column: str | None,
    base_dir: str | None,
    auto_detect_root: bool,
) -> str | None:
    if base_dir:
        return os.path.abspath(base_dir)

    default_root = os.path.abspath(str(parquet_path.parent))
    if not auto_detect_root:
        return default_root

    detected_source = source_column or _detect_source_column(str(parquet_path), default_root)
    if not detected_source:
        return default_root

    absolute_local_sources, has_relative_local_sources = _local_source_layout(table, detected_source)
    if not absolute_local_sources or has_relative_local_sources:
        return default_root

    if all(_path_is_within_root(source, default_root) for source in absolute_local_sources):
        return default_root

    try:
        common_root = os.path.commonpath(absolute_local_sources)
    except ValueError:
        return default_root

    common_root = os.path.abspath(common_root)
    if not common_root or common_root == os.path.sep:
        return default_root
    if not _is_safe_auto_root(common_root):
        return default_root
    return common_root


def _local_source_layout(table, column_name: str) -> tuple[list[str], bool]:
    try:
        values = table[column_name].to_pylist()
    except Exception:
        return [], False

    absolute_local_sources: list[str] = []
    has_relative_local_sources = False
    for value in values:
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):
            continue
        if isinstance(value, os.PathLike):
            value = os.fspath(value)
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if not candidate:
            continue
        if candidate.startswith("s3://") or candidate.startswith("http://") or candidate.startswith("https://"):
            continue
        if os.path.isabs(candidate):
            absolute_local_sources.append(os.path.abspath(candidate))
            continue
        has_relative_local_sources = True

    return absolute_local_sources, has_relative_local_sources


def _path_is_within_root(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:
        return False


def _is_safe_auto_root(root: str) -> bool:
    segments = [segment for segment in Path(root).parts if segment not in {"", os.path.sep}]
    return len(segments) >= 2


def _find_column_name(table, target: str) -> str | None:
    target_lower = target.lower()
    for name in table.schema.names:
        if name.lower() == target_lower:
            return name
    return None


def _count_missing_dims(table, width_name: str | None, height_name: str | None) -> int:
    if width_name is None or height_name is None:
        return table.num_rows
    width = table[width_name].to_pylist()
    height = table[height_name].to_pylist()
    missing = 0
    for w, h in zip(width, height):
        if not _valid_dim(w) or not _valid_dim(h):
            missing += 1
    return missing


def _valid_dim(value) -> bool:
    try:
        return value is not None and int(value) > 0
    except Exception:
        return False


def _maybe_write_dimensions(
    parquet_path: Path,
    table,
    width_name: str | None,
    height_name: str | None,
    row_dims: list[tuple[int, int] | None],
) -> bool:
    import pyarrow as pa
    import pyarrow.parquet as pq

    widths = []
    heights = []
    existing_width = table[width_name].to_pylist() if width_name else [None] * table.num_rows
    existing_height = table[height_name].to_pylist() if height_name else [None] * table.num_rows

    changed = False
    for idx in range(table.num_rows):
        w_existing = existing_width[idx] if idx < len(existing_width) else None
        h_existing = existing_height[idx] if idx < len(existing_height) else None
        w_final = w_existing
        h_final = h_existing
        dims = row_dims[idx] if idx < len(row_dims) else None
        if not _valid_dim(w_existing):
            if dims and dims[0] > 0:
                w_final = dims[0]
                changed = True
        if not _valid_dim(h_existing):
            if dims and dims[1] > 0:
                h_final = dims[1]
                changed = True
        widths.append(w_final)
        heights.append(h_final)

    if not changed and width_name and height_name:
        return False

    width_arr = pa.array(widths, type=pa.int64())
    height_arr = pa.array(heights, type=pa.int64())

    table_out = table
    if width_name is None:
        width_name = "width"
        table_out = table_out.append_column(width_name, width_arr)
    else:
        idx = table_out.schema.get_field_index(width_name)
        table_out = table_out.set_column(idx, width_name, width_arr)

    if height_name is None:
        height_name = "height"
        table_out = table_out.append_column(height_name, height_arr)
    else:
        idx = table_out.schema.get_field_index(height_name)
        table_out = table_out.set_column(idx, height_name, height_arr)

    pq.write_table(table_out, str(parquet_path))
    return True


def _detect_source_column(parquet_path: str, base_dir: str | None, sample_size: int = 50) -> str | None:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "pyarrow is required for Parquet datasets. Install with: pip install pyarrow"
        ) from exc

    pf = pq.ParquetFile(parquet_path)
    if pf.metadata is not None and pf.metadata.num_rows == 0:
        return None

    columns = pf.schema.names
    if not columns:
        return None

    batch = None
    for candidate in pf.iter_batches(batch_size=sample_size):
        batch = candidate
        break
    if batch is None or batch.num_rows == 0:
        return None

    best_score = 0.0
    best_total = 0
    best_name = None
    for col in columns:
        values = batch.column(col).to_pylist()
        total = 0
        matches = 0
        for value in values:
            if value is None:
                continue
            if isinstance(value, float) and math.isnan(value):
                continue
            if isinstance(value, os.PathLike):
                value = os.fspath(value)
            if not isinstance(value, str):
                continue
            value = value.strip()
            if not value:
                continue
            total += 1
            if _is_loadable_value(value, base_dir):
                matches += 1
        if total == 0:
            continue
        score = matches / total
        if score < 0.7:
            continue
        if score > best_score or (score == best_score and total > best_total):
            best_score = score
            best_total = total
            best_name = col

    return best_name


def _is_loadable_value(value: str, base_dir: str | None) -> bool:
    if value.startswith("s3://"):
        return True
    if value.startswith("http://") or value.startswith("https://"):
        return True
    if os.path.isabs(value):
        return os.path.exists(value)
    if base_dir:
        return os.path.exists(os.path.join(base_dir, value))
    return False


def main(argv: list[str] | None = None) -> None:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    if argv_list and argv_list[0] == "rank":
        _main_rank(argv_list[1:])
        return
    _main_browse(argv_list)


if __name__ == "__main__":
    main()
