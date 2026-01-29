"""CLI entry point for Lenslet."""
from __future__ import annotations
import argparse
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


_CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    "cloudflared-linux-amd64"
)


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
        try:
            table = table.to_pandas()
        except TypeError:
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
    binary_path = Path.home() / "cfed"
    if binary_path.is_file():
        if os.access(binary_path, os.X_OK):
            return binary_path
        binary_path.chmod(binary_path.stat().st_mode | 0o111)
        return binary_path

    print("[lenslet] Downloading cloudflared...")
    import urllib.request
    with urllib.request.urlopen(_CLOUDFLARED_URL) as response, binary_path.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    binary_path.chmod(0o755)
    return binary_path


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


def main():
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
        help="Disable workspace writes (.lenslet/) for one-off sessions",
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

    args = parser.parse_args()

    if args.version:
        from . import __version__
        print(f"lenslet {__version__}")
        sys.exit(0)

    # Directory is required unless --version
    if not args.directory:
        parser.print_help()
        sys.exit(1)

    from .embeddings.config import EmbeddingConfig, parse_embedding_columns, parse_embedding_metrics
    try:
        embedding_config = EmbeddingConfig(
            explicit_columns=parse_embedding_columns(args.embedding_column),
            metric_overrides=parse_embedding_metrics(args.embedding_metric),
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Resolve and validate target
    raw_target = args.directory
    candidate = Path(raw_target).expanduser()
    is_local = candidate.exists()
    is_table_file = False
    is_remote_table = False
    remote_kind = None
    remote_uri = None
    if is_local:
        target = candidate.resolve()
        is_table_file = target.is_file() and target.suffix.lower() == ".parquet"
        if target.is_file():
            if not is_table_file:
                print(f"Error: '{args.directory}' is not a .parquet file", file=sys.stderr)
                sys.exit(1)
        elif not target.is_dir():
            print(f"Error: '{args.directory}' is not a valid directory or .parquet file", file=sys.stderr)
            sys.exit(1)
    elif _is_remote_uri(raw_target):
        is_remote_table = True
        remote_kind = "remote"
        remote_uri = raw_target
    elif _looks_like_hf_dataset(raw_target):
        is_remote_table = True
        remote_kind = "hf"
        remote_uri = f"hf://{raw_target}"
    else:
        print(f"Error: '{args.directory}' does not exist", file=sys.stderr)
        sys.exit(1)

    port = args.port
    if port is None:
        try:
            port = _find_available_port(args.host, 7070)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        if port != 7070:
            print(f"[lenslet] Port 7070 is in use; using {port} instead.")

    effective_no_write = args.no_write or is_remote_table
    if args.no_write:
        if args.cache_wh:
            print("[lenslet] --no-write disables parquet caching; use --no-cache-wh to silence.")
            args.cache_wh = False
        if args.thumb_cache:
            print("[lenslet] --no-write disables thumbnail cache; use --no-thumb-cache to silence.")
            args.thumb_cache = False
        if args.og_preview:
            print("[lenslet] --no-write disables OG cache; previews will be generated on-demand.")
        if args.embedding_cache:
            print("[lenslet] --no-write disables embedding cache; use --no-embedding-cache to silence.")
            args.embedding_cache = False

    # Print startup banner
    if is_remote_table:
        mode_label = "Table (hf dataset)" if remote_kind == "hf" else "Table (remote)"
        display_target = remote_uri or raw_target
    elif is_table_file:
        mode_label = "Table (parquet)"
        display_target = str(target)
    else:
        has_parquet = (target / "items.parquet").is_file()
        mode_label = "Table (items.parquet)" if has_parquet else "In-memory (no files written)"
        display_target = str(target)

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
            f"│  Mode:      {mode_label:<35} │",
        f"│  No-write:  {'ON' if effective_no_write else 'off':<35} │",
            "└─────────────────────────────────────────────────┘",
            "",
        ]
    )
    print("\n".join(banner_lines))

    # Guard against multi-worker mode (in-memory sync is single-process only)
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
            break

    # Start server
    import uvicorn
    from .server import create_app, create_app_from_storage, create_app_from_table
    from .workspace import Workspace
    if is_remote_table:
        try:
            table = _load_remote_table(remote_uri or raw_target)
        except Exception as exc:
            print(f"Error: failed to load remote table '{remote_uri or raw_target}': {exc}", file=sys.stderr)
            sys.exit(1)
        workspace = Workspace.for_dataset(None, can_write=False)
        app = create_app_from_table(
            table=table,
            base_dir=args.base_dir,
            thumb_size=args.thumb_size,
            thumb_quality=args.thumb_quality,
            source_column=args.source_column,
            skip_indexing=args.skip_indexing,
            og_preview=args.og_preview,
            workspace=workspace,
            thumb_cache=args.thumb_cache and not effective_no_write,
            embedding_config=embedding_config,
            embedding_cache=args.embedding_cache and not effective_no_write,
            embedding_cache_dir=args.embedding_cache_dir,
            embedding_preload=args.embedding_preload,
        )
    elif is_table_file:
        base_dir = args.base_dir or str(target.parent)
        storage = _prepare_table_cache(
            parquet_path=target,
            base_dir=base_dir,
            source_column=args.source_column,
            cache_wh=args.cache_wh,
            skip_indexing=args.skip_indexing,
            embedding_config=embedding_config,
        )
        workspace = Workspace.for_parquet(target, can_write=not args.no_write)
        app = create_app_from_storage(
            storage,
            show_source=True,
            workspace=workspace,
            thumb_cache=args.thumb_cache,
            og_preview=args.og_preview,
            embedding_parquet_path=str(target),
            embedding_config=embedding_config,
            embedding_cache=args.embedding_cache and not effective_no_write,
            embedding_cache_dir=args.embedding_cache_dir,
            embedding_preload=args.embedding_preload,
        )
    else:
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
        app = create_app(
            root_path=str(target),
            thumb_size=args.thumb_size,
            thumb_quality=args.thumb_quality,
            no_write=args.no_write,
            source_column=args.source_column,
            skip_indexing=args.skip_indexing,
            thumb_cache=args.thumb_cache,
            og_preview=args.og_preview,
            embedding_config=embedding_config,
            embedding_cache=args.embedding_cache and not effective_no_write,
            embedding_cache_dir=args.embedding_cache_dir,
            embedding_preload=args.embedding_preload,
        )

    share_tunnel = None
    try:
        if args.share:
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


def _prepare_table_cache(
    parquet_path: Path,
    base_dir: str,
    source_column: str | None,
    cache_wh: bool,
    skip_indexing: bool,
    quiet: bool = False,
    embedding_config=None,
) -> "TableStorage":
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

    storage = TableStorage(
        table=table,
        root=base_dir,
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


if __name__ == "__main__":
    main()
