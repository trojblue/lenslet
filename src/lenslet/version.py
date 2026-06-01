"""Runtime package version resolution."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PROJECT_NAME = "lenslet"
FALLBACK_VERSION = "0.0.0+unknown"


def _version_from_pyproject() -> str | None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        lines = pyproject.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    in_project = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if not in_project or not line.startswith("version"):
            continue
        key, sep, raw_value = line.partition("=")
        if sep and key.strip() == "version":
            return raw_value.strip().strip('"').strip("'") or None
    return None


def get_version() -> str:
    try:
        return version(PROJECT_NAME)
    except PackageNotFoundError:
        return _version_from_pyproject() or FALLBACK_VERSION
