from __future__ import annotations

from lenslet.terminal_banner import banner_row, terminal_cell_width

_TOP_BORDER = "\u250c" + ("\u2500" * 49) + "\u2510"


def test_banner_row_pads_full_server_url_to_box_width() -> None:
    row = banner_row("Server:", "http://127.0.0.1:7072")

    assert "http://127.0.0.1:7072" in row
    assert terminal_cell_width(row) == terminal_cell_width(_TOP_BORDER)


def test_banner_row_clips_long_values_to_box_width() -> None:
    row = banner_row("Target:", "/fsx/yada/dev/new-aes-workspace/outputs/09_aiimg_mining")

    assert row.startswith("\u2502  Target:    /fsx/yada/dev/new-aes-workspace/out")
    assert terminal_cell_width(row) == terminal_cell_width(_TOP_BORDER)


def test_banner_row_accounts_for_wide_characters() -> None:
    row = banner_row("Label:", "score\U0001f50dabc")

    assert "score\U0001f50dabc" in row
    assert terminal_cell_width(row) == terminal_cell_width(_TOP_BORDER)
