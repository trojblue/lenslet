"""Terminal banner formatting helpers."""

from __future__ import annotations

import unicodedata

BANNER_INNER_WIDTH = 49
BANNER_VALUE_WIDTH = 35

_VERTICAL = "\u2502"
_LABEL_WIDTH = BANNER_INNER_WIDTH - BANNER_VALUE_WIDTH - 1


def terminal_cell_width(text: object) -> int:
    """Return the terminal cell width for banner text."""
    return sum(_cell_width(char) for char in str(text))


def fit_terminal_text(text: object, width: int) -> str:
    """Clip and pad text to exactly ``width`` terminal cells."""
    if width <= 0:
        return ""
    used = 0
    chars: list[str] = []
    for char in str(text):
        char_width = _cell_width(char)
        if char_width > 0 and used + char_width > width:
            break
        chars.append(char)
        used += char_width
    return "".join(chars) + (" " * (width - used))


def banner_row(label: str, value: object) -> str:
    """Format a fixed-width key/value banner row."""
    label_text = f"  {label:<{_LABEL_WIDTH - 2}}"
    return f"{_VERTICAL}{label_text}{fit_terminal_text(value, BANNER_VALUE_WIDTH)} {_VERTICAL}"


def _cell_width(char: str) -> int:
    if unicodedata.combining(char):
        return 0
    if unicodedata.category(char) in {"Cf", "Mn", "Me"}:
        return 0
    return 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
