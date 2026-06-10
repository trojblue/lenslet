"""Ranking command implementation for the Lenslet CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from .common import _find_available_port
from ..ranking import app as ranking_app
from ..ranking.dataset import RankingDatasetError
from ..ranking.persistence import RankingPersistenceError
from ..terminal_banner import banner_row
from ..web.auth import trusted_write_origins_for_host

DEFAULT_RANK_PORT = 7070


class RankCliError(RuntimeError):
    """Raised for ranking CLI setup failures before the server starts."""


def _main_rank(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="lenslet rank",
        description="Lenslet ranking mode server",
        epilog=f"Example: lenslet rank ./ranking_dataset.json --port {DEFAULT_RANK_PORT}",
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
        help=f"Port to listen on (default: {DEFAULT_RANK_PORT}; auto-increment if in use)",
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

    try:
        dataset_path = _resolve_dataset_path(args.dataset_json)
        port = _resolve_rank_port(args.host, args.port)
        app = _create_rank_app(
            dataset_path,
            args.results_path,
            trusted_write_origins=trusted_write_origins_for_host(args.host, port),
        )
    except RankCliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    results_path = getattr(app.state, "ranking_results_path", None)
    dataset_label = str(dataset_path)
    display_results = str(results_path) if results_path is not None else "unknown"
    server_url = f"http://{args.host}:{port}"
    banner_lines = [
        "┌─────────────────────────────────────────────────┐",
        "│                   🔍 Lenslet                    │",
        "│               Ranking Mode Server               │",
        "├─────────────────────────────────────────────────┤",
        banner_row("Dataset:", dataset_label),
        banner_row("Server:", server_url),
        banner_row("Results:", display_results),
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


def _resolve_dataset_path(raw_path: str) -> Path:
    dataset_path = Path(raw_path).expanduser()
    if not dataset_path.exists():
        raise RankCliError(f"dataset file does not exist: {raw_path}")
    if not dataset_path.is_file():
        raise RankCliError(f"dataset path must be a file: {raw_path}")
    return dataset_path.resolve()


def _resolve_rank_port(host: str, requested_port: int | None) -> int:
    if requested_port is not None:
        return requested_port
    try:
        port = _find_available_port(host, DEFAULT_RANK_PORT)
    except RuntimeError as exc:
        raise RankCliError(str(exc)) from exc
    if port != DEFAULT_RANK_PORT:
        print(f"[lenslet] Port {DEFAULT_RANK_PORT} is in use; using {port} instead.")
    return port


def _create_rank_app(
    dataset_path: Path,
    results_path: str | None,
    *,
    trusted_write_origins: tuple[str, ...],
) -> object:
    try:
        return ranking_app.create_ranking_app(
            dataset_path,
            results_path=results_path,
            trusted_write_origins=trusted_write_origins,
        )
    except (OSError, RankingDatasetError, RankingPersistenceError) as exc:
        raise RankCliError(f"failed to initialize ranking mode: {exc}") from exc
