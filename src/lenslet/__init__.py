"""Lenslet: A lightweight image gallery server."""

from __future__ import annotations

from .api import LaunchOptions, TableLaunchOptions, launch, launch_table

__all__ = ["LaunchOptions", "TableLaunchOptions", "launch", "launch_table", "__version__"]


def __getattr__(name: str) -> str:
    if name == "__version__":
        from .version import get_version

        return get_version()
    raise AttributeError(f"module 'lenslet' has no attribute {name!r}")
