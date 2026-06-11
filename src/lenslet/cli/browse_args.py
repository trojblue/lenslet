"""Argument parsing and normalization for the browse CLI command."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class BrowseCliArgs:
    directory: str
    host: str
    port: int | None
    thumb_size: int
    thumb_quality: int
    source_column: str | None
    path_column: str | None
    base_dir: str | None
    dimension_cache: str
    cache_dimensions: bool
    skip_dimension_probe: bool
    thumb_cache: bool
    og_preview: bool
    reload: bool
    no_write: bool
    trust_remote_paths: bool
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
            path_column=args.path_column,
            base_dir=args.base_dir,
            dimension_cache=str(args.dimension_cache),
            cache_dimensions=str(args.dimension_cache) == "source",
            skip_dimension_probe=bool(args.skip_dimension_probe),
            thumb_cache=bool(args.thumb_cache),
            og_preview=bool(args.og_preview),
            reload=bool(args.reload),
            no_write=bool(args.no_write),
            trust_remote_paths=bool(args.trust_remote_paths),
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


def _build_browse_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lenslet",
        description="Lenslet - Lightweight image gallery server",
        epilog="Example: lenslet ~/Pictures --port 7070",
    )
    parser.set_defaults(cache_dimensions=False)
    parser.add_argument(
        "directory",
        type=str,
        nargs="?",
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
        "--path-column",
        type=str,
        default=None,
        help="Column to use as Lenslet logical paths in table mode",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=None,
        help="Base directory for resolving relative paths in table mode",
    )
    parser.add_argument(
        "--dimension-cache",
        choices=("workspace", "source", "none"),
        default="workspace",
        help="Where to cache probed width/height dimensions (default: workspace)",
    )
    parser.add_argument(
        "--write-source-dimensions",
        action="store_const",
        const="source",
        dest="dimension_cache",
        help="Opt in to writing probed width/height dimensions back into the source Parquet",
    )
    parser.add_argument(
        "--no-cache-dimensions",
        action="store_const",
        const="none",
        dest="dimension_cache",
        help="Disable workspace dimension cache writes and source dimension writes",
    )
    parser.add_argument(
        "--probe-dimensions",
        action="store_false",
        dest="skip_dimension_probe",
        default=True,
        help="Probe missing image dimensions during table load",
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
        help="Use a temp workspace under the system temp directory (keeps the source dataset read-only)",
    )
    parser.add_argument(
        "--trust-remote-paths",
        action="store_true",
        help=(
            "Allow remote parquet/HF tables to read local filesystem paths from their source column. "
            "Security-sensitive; only use remote datasets you trust."
        ),
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
        "--no-embedding-cache",
        action="store_false",
        dest="embedding_cache",
        default=True,
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
        from ..version import get_version

        print(f"lenslet {get_version()}")
        sys.exit(0)

    if not args.directory:
        parser.print_help()
        sys.exit(1)

    return BrowseCliArgs.from_namespace(args)


def _normalize_browse_args(args: BrowseCliArgs) -> BrowseCliArgs:
    if args.no_write and args.dimension_cache == "source":
        print("[lenslet] --no-write uses a temp workspace dimension cache instead of writing source Parquet.")
        return replace(args, dimension_cache="workspace", cache_dimensions=False)
    return args
