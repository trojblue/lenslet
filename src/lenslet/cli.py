"""CLI entry point for Lenslet."""
from __future__ import annotations
import argparse
import sys
import os
from pathlib import Path


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
        default=7070,
        help="Port to listen on (default: 7070)",
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
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed server logs",
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

    # Print startup banner
    print(f"""
┌─────────────────────────────────────────────────┐
│                   🔍 Lenslet                    │
│         Lightweight Image Gallery Server        │
├─────────────────────────────────────────────────┤
│  Directory: {str(directory)[:35]:<35} │
│  Server:    http://{args.host}:{args.port:<24} │
│  Mode:      In-memory (no files written)        │
└─────────────────────────────────────────────────┘
""")

    # Start server
    import uvicorn
    from .server import create_app

    app = create_app(
        root_path=str(directory),
        thumb_size=args.thumb_size,
        thumb_quality=args.thumb_quality,
    )

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info" if args.verbose else "warning",
    )


if __name__ == "__main__":
    main()

