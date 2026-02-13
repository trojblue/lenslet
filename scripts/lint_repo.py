#!/usr/bin/env python3
"""Repository lint runner.

Runs Ruff and enforces file-size guardrails:
- warn when a tracked source file exceeds WARN threshold
- fail when a tracked source file exceeds ERROR threshold
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable


DEFAULT_RUFF_PATHS = (
    "src",
    "tests",
    "scripts",
)
DEFAULT_SIZE_PATHS = (
    "src",
    "tests",
    "scripts",
    "frontend/src",
    "AGENTS.md",
    "README.md",
)
DEFAULT_WARN_LINES = 1_200
DEFAULT_ERROR_LINES = 2_000

TRACKED_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".css",
    ".md",
    ".sh",
}
EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    ".venv",
    "venv",
}
EXCLUDED_PATH_PREFIXES = (
    Path("docs/agents_archive"),
    Path("src/lenslet/frontend"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Ruff and repository size guardrails.")
    parser.add_argument(
        "--ruff-paths",
        nargs="+",
        default=list(DEFAULT_RUFF_PATHS),
        help="Paths to pass to Ruff (default: src tests scripts).",
    )
    parser.add_argument(
        "--size-paths",
        nargs="+",
        default=list(DEFAULT_SIZE_PATHS),
        help="Paths to scan for file-size guardrails (default: src tests scripts frontend/src AGENTS.md README.md).",
    )
    parser.add_argument(
        "--warn-lines",
        type=int,
        default=DEFAULT_WARN_LINES,
        help=f"Emit warning when file line count exceeds this threshold (default: {DEFAULT_WARN_LINES}).",
    )
    parser.add_argument(
        "--error-lines",
        type=int,
        default=DEFAULT_ERROR_LINES,
        help=f"Fail when file line count exceeds this threshold (default: {DEFAULT_ERROR_LINES}).",
    )
    parser.add_argument(
        "--skip-ruff",
        action="store_true",
        help="Skip Ruff check and run only file-size guardrails.",
    )
    return parser.parse_args()


def run_ruff(paths: list[str]) -> int:
    command = [sys.executable, "-m", "ruff", "check", *paths]
    print(f"[lint] running: {' '.join(command)}")
    try:
        result = subprocess.run(command, check=False)
    except FileNotFoundError:
        print("[lint:error] Ruff is not installed. Install dev deps first: pip install -e '.[dev]'.")
        return 1
    if result.returncode != 0:
        print(f"[lint:error] Ruff failed with exit code {result.returncode}.")
    return result.returncode


def should_skip_path(path: Path) -> bool:
    if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
        return True
    return any(path.is_relative_to(prefix) for prefix in EXCLUDED_PATH_PREFIXES)


def should_scan_file(path: Path) -> bool:
    if path.name.startswith("."):
        return False
    if path.suffix.lower() not in TRACKED_EXTENSIONS:
        return False
    return not should_skip_path(path)


def iter_candidate_files(paths: Iterable[str]) -> Iterable[Path]:
    seen: set[Path] = set()
    cwd = Path.cwd()

    def _to_repo_relative(path: Path) -> Path:
        resolved = path.resolve()
        try:
            return resolved.relative_to(cwd)
        except ValueError:
            return resolved

    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            print(f"[lint:warn] path does not exist, skipping: {raw_path}")
            continue
        if path.is_file():
            rel = _to_repo_relative(path)
            if should_scan_file(rel):
                if rel not in seen:
                    seen.add(rel)
                    yield rel
            continue

        for child in path.rglob("*"):
            if not child.is_file():
                continue
            rel = _to_repo_relative(child)
            if should_scan_file(rel) and rel not in seen:
                seen.add(rel)
                yield rel


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def run_size_guardrails(paths: list[str], warn_lines: int, error_lines: int) -> int:
    warnings: list[tuple[Path, int]] = []
    failures: list[tuple[Path, int]] = []

    for file_path in iter_candidate_files(paths):
        line_count = count_lines(file_path)
        if line_count > error_lines:
            failures.append((file_path, line_count))
        elif line_count > warn_lines:
            warnings.append((file_path, line_count))

    if warnings:
        print(
            f"[lint:warn] {len(warnings)} file(s) exceed {warn_lines} lines "
            f"(warn-only; hard fail starts above {error_lines})."
        )
        for path, line_count in sorted(warnings):
            print(f"[lint:warn] {path}: {line_count} lines")

    if failures:
        print(f"[lint:error] {len(failures)} file(s) exceed {error_lines} lines.")
        for path, line_count in sorted(failures):
            print(f"[lint:error] {path}: {line_count} lines")
        return 1

    print("[lint] file-size guardrails passed.")
    return 0


def main() -> int:
    args = parse_args()

    if args.warn_lines >= args.error_lines:
        print("[lint:error] --warn-lines must be less than --error-lines.")
        return 1

    ruff_code = 0 if args.skip_ruff else run_ruff(args.ruff_paths)
    size_code = run_size_guardrails(args.size_paths, args.warn_lines, args.error_lines)
    return 1 if (ruff_code != 0 or size_code != 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
