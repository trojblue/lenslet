"""Thin argv dispatcher for the Lenslet CLI."""

from __future__ import annotations

import sys

from .browse import _main_browse
from .rank import _main_rank


def main(argv: list[str] | None = None) -> None:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    if argv_list and argv_list[0] == "rank":
        _main_rank(argv_list[1:])
        return
    _main_browse(argv_list)


if __name__ == "__main__":
    main()
