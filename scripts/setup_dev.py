#!/usr/bin/env python3
"""Install the Lenslet development toolchain."""

from __future__ import annotations

import argparse
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
PY313_CONSTRAINTS = ROOT / "constraints" / "runtime-py313.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Install Python dev extras, frontend packages, and Playwright Chromium for Lenslet."
        )
    )
    parser.add_argument(
        "--constraints",
        default="auto",
        help=(
            "Python constraints mode: 'auto' uses constraints/runtime-py313.txt on Python 3.13, "
            "'none' disables constraints, or pass a constraint file path."
        ),
    )
    parser.add_argument(
        "--extras",
        default="dev",
        help="Comma-separated editable install extras for the Python package (default: dev).",
    )
    parser.add_argument("--skip-python", action="store_true", help="Skip Python package install.")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend npm install.")
    parser.add_argument(
        "--skip-playwright",
        action="store_true",
        help="Skip Playwright Chromium browser install.",
    )
    parser.add_argument(
        "--skip-browser-system-deps",
        action="store_true",
        help=(
            "Do not ask Playwright to install Linux system packages required by Chromium. "
            "By default this is enabled on Linux fresh installs."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    return parser.parse_args()


def shell_join(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def run(command: Sequence[str], *, cwd: Path = ROOT, dry_run: bool = False) -> None:
    print(f"$ {shell_join(command)}", flush=True)
    if dry_run:
        return
    subprocess.run(command, cwd=cwd, check=True)


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"required tool not found on PATH: {name}")


def python_constraint_args(mode: str) -> list[str]:
    if mode == "none":
        return []
    if mode == "auto":
        if sys.version_info[:2] == (3, 13) and PY313_CONSTRAINTS.exists():
            return ["-c", str(PY313_CONSTRAINTS)]
        return []
    path = Path(mode).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise SystemExit(f"constraint file does not exist: {path}")
    return ["-c", str(path)]


def editable_target(extras: str) -> str:
    names = [part.strip() for part in extras.split(",") if part.strip()]
    if not names:
        return "."
    return f".[{','.join(names)}]"


def install_python(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        *python_constraint_args(args.constraints),
        "-e",
        editable_target(args.extras),
    ]
    run(command, dry_run=args.dry_run)


def install_frontend(args: argparse.Namespace) -> None:
    require_tool("npm")
    package_lock = ROOT / "frontend" / "package-lock.json"
    command = ["npm", "ci" if package_lock.exists() else "install"]
    run(command, cwd=ROOT / "frontend", dry_run=args.dry_run)


def install_playwright(args: argparse.Namespace) -> None:
    command = [sys.executable, "-m", "playwright", "install"]
    if platform.system() == "Linux" and not args.skip_browser_system_deps:
        command.append("--with-deps")
    command.append("chromium")
    run(command, dry_run=args.dry_run)


def main() -> None:
    args = parse_args()
    if not args.skip_python:
        install_python(args)
    if not args.skip_frontend:
        install_frontend(args)
    if not args.skip_playwright:
        install_playwright(args)
    print("Lenslet development setup complete.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
