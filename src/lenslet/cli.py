"""CLI entry point for Lenslet."""
from __future__ import annotations
import argparse
import os
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Iterable


_CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    "cloudflared-linux-amd64"
)


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


def _start_share_tunnel(port: int, bind_host: str, verbose: bool) -> tuple[subprocess.Popen[str], threading.Thread]:
    binary_path = _ensure_cloudflared_binary()
    target_host = _tunnel_target_host(bind_host)
    cmd = [str(binary_path), "tunnel", "--url", f"{target_host}:{port}"]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    url_pattern = re.compile(r"https://[A-Za-z0-9.-]+\.trycloudflare\.com")

    def _reader(lines: Iterable[str]) -> None:
        share_url = None
        for raw in lines:
            line = raw.rstrip()
            if verbose:
                print(f"[cloudflared] {line}")
            if share_url is None:
                match = url_pattern.search(line)
                if match:
                    share_url = match.group(0)
                    _print_share_url(share_url)
        if share_url is None and process.poll() not in (None, 0):
            print("[lenslet] Share tunnel exited before a URL was created.", file=sys.stderr)

    if process.stdout is None:
        raise RuntimeError("Failed to start cloudflared: no stdout pipe available.")

    thread = threading.Thread(target=_reader, args=(process.stdout,), daemon=True)
    thread.start()
    return process, thread


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
    from tqdm import tqdm
    tqdm.write(f"Share URL: {url}")


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
        help="Directory containing images to serve",
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
        help="Column to load images from when items.parquet is present",
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

    # Resolve and validate directory
    directory = Path(args.directory).expanduser().resolve()
    if not directory.is_dir():
        print(f"Error: '{args.directory}' is not a valid directory", file=sys.stderr)
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

    # Print startup banner
    has_parquet = (directory / "items.parquet").is_file()
    mode_label = "Parquet dataset" if has_parquet else "In-memory (no files written)"

    banner_lines = [
        "┌─────────────────────────────────────────────────┐",
        "│                   🔍 Lenslet                    │",
        "│         Lightweight Image Gallery Server        │",
        "├─────────────────────────────────────────────────┤",
        f"│  Directory: {str(directory)[:35]:<35} │",
        f"│  Server:    http://{args.host}:{port:<24} │",
    ]
    if args.share:
        banner_lines.append("│  Share:     starting...                         │")
    banner_lines.extend(
        [
            f"│  Mode:      {mode_label:<35} │",
            f"│  No-write:  {'ON' if args.no_write else 'off':<35} │",
            "└─────────────────────────────────────────────────┘",
            "",
        ]
    )
    print("\n".join(banner_lines))

    # Start server
    import uvicorn
    from .server import create_app

    app = create_app(
        root_path=str(directory),
        thumb_size=args.thumb_size,
        thumb_quality=args.thumb_quality,
        no_write=args.no_write,
        source_column=args.source_column,
    )

    share_process = None
    try:
        if args.share:
            try:
                share_process, _ = _start_share_tunnel(port, args.host, args.verbose)
            except Exception as exc:
                print(f"[lenslet] Failed to start share tunnel: {exc}", file=sys.stderr)
                sys.exit(1)
        uvicorn.run(
            app,
            host=args.host,
            port=port,
            reload=args.reload,
            log_level="info" if args.verbose else "warning",
        )
    finally:
        if share_process is not None:
            _stop_process(share_process)


if __name__ == "__main__":
    main()
