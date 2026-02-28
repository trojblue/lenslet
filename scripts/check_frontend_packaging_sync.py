#!/usr/bin/env python3
"""Verify packaged frontend assets are synced from frontend/dist.

This gate ensures shipping assets under src/lenslet/frontend mirror the latest
frontend/dist output after a build + rsync step.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check frontend dist/package sync state.")
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=Path("frontend/dist"),
        help="Frontend build output directory (default: frontend/dist).",
    )
    parser.add_argument(
        "--packaged-dir",
        type=Path,
        default=Path("src/lenslet/frontend"),
        help="Packaged frontend directory served by backend (default: src/lenslet/frontend).",
    )
    return parser.parse_args()


def _file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def collect_tree(root: Path) -> dict[str, str]:
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"directory does not exist: {root}")
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = _file_digest(path)
    return files


def diff_trees(expected: dict[str, str], actual: dict[str, str]) -> dict[str, list[str]]:
    expected_paths = set(expected)
    actual_paths = set(actual)

    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    changed = sorted(path for path in (expected_paths & actual_paths) if expected[path] != actual[path])

    return {
        "missing": missing,
        "extra": extra,
        "changed": changed,
    }


def check_sync(dist_dir: Path, packaged_dir: Path) -> tuple[bool, dict[str, list[str]]]:
    expected = collect_tree(dist_dir)
    actual = collect_tree(packaged_dir)
    diff = diff_trees(expected, actual)
    clean = not (diff["missing"] or diff["extra"] or diff["changed"])
    return clean, diff


def _print_diff(prefix: str, paths: list[str]) -> None:
    if not paths:
        return
    print(f"[frontend-sync] {prefix} ({len(paths)}):")
    for path in paths[:20]:
        print(f"  - {path}")
    if len(paths) > 20:
        print(f"  ... ({len(paths) - 20} more)")


def main() -> int:
    args = parse_args()
    try:
        clean, diff = check_sync(args.dist_dir, args.packaged_dir)
    except FileNotFoundError as exc:
        print(f"[frontend-sync:error] {exc}")
        print("[frontend-sync:hint] run `cd frontend && npm run build` first.")
        return 1

    if clean:
        print(
            "[frontend-sync] ok: packaged frontend matches dist "
            f"({args.dist_dir} -> {args.packaged_dir})."
        )
        return 0

    _print_diff("missing in packaged", diff["missing"])
    _print_diff("extra in packaged", diff["extra"])
    _print_diff("content mismatches", diff["changed"])
    print(
        "[frontend-sync:error] packaged assets are out of sync. "
        "run `rsync -a --delete frontend/dist/ src/lenslet/frontend/`."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
