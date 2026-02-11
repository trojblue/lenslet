from __future__ import annotations

import os
import struct
from io import BytesIO
from typing import BinaryIO


def _kind_from_extension(ext: str | None) -> str | None:
    if ext in ("jpg", "jpeg"):
        return "jpeg"
    if ext == "png":
        return "png"
    if ext == "webp":
        return "webp"
    return None


def _kind_from_header(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return None


def read_dimensions_from_bytes(data: bytes, ext: str | None) -> tuple[int, int] | None:
    if not data:
        return None

    kind = _kind_from_extension(ext) or _kind_from_header(data)
    if kind is None:
        return None

    try:
        buf = BytesIO(data)
        if kind == "jpeg":
            return read_jpeg_dimensions(buf)
        if kind == "png":
            return read_png_dimensions(buf)
        if kind == "webp":
            return read_webp_dimensions(buf)
    except Exception:
        return None
    return None


def read_dimensions_fast(filepath: str) -> tuple[int, int] | None:
    ext = os.path.splitext(filepath)[1].lower().lstrip(".")
    kind = _kind_from_extension(ext)
    if kind is None:
        return None

    try:
        with open(filepath, "rb") as handle:
            if kind == "jpeg":
                return read_jpeg_dimensions(handle)
            if kind == "png":
                return read_png_dimensions(handle)
            if kind == "webp":
                return read_webp_dimensions(handle)
    except Exception:
        return None
    return None


def read_jpeg_dimensions(handle: BinaryIO) -> tuple[int, int] | None:
    handle.seek(0)
    if handle.read(2) != b"\xff\xd8":
        return None

    while True:
        marker = handle.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            return None
        if marker[1] == 0xD9:
            return None
        if 0xC0 <= marker[1] <= 0xCF and marker[1] not in (0xC4, 0xC8, 0xCC):
            handle.read(2)
            handle.read(1)
            h, w = struct.unpack(">HH", handle.read(4))
            return w, h
        length = struct.unpack(">H", handle.read(2))[0]
        handle.seek(length - 2, 1)


def read_png_dimensions(handle: BinaryIO) -> tuple[int, int] | None:
    handle.seek(0)
    if handle.read(8) != b"\x89PNG\r\n\x1a\n":
        return None
    handle.read(4)
    if handle.read(4) != b"IHDR":
        return None
    w, h = struct.unpack(">II", handle.read(8))
    return w, h


def read_webp_dimensions(handle: BinaryIO) -> tuple[int, int] | None:
    handle.seek(0)
    if handle.read(4) != b"RIFF":
        return None
    handle.read(4)
    if handle.read(4) != b"WEBP":
        return None
    chunk = handle.read(4)
    if chunk == b"VP8 ":
        handle.read(4)
        handle.read(3)
        if handle.read(3) != b"\x9d\x01\x2a":
            return None
        data = handle.read(4)
        w = (data[0] | (data[1] << 8)) & 0x3FFF
        h = (data[2] | (data[3] << 8)) & 0x3FFF
        return w, h
    if chunk == b"VP8L":
        handle.read(4)
        if handle.read(1) != b"\x2f":
            return None
        data = struct.unpack("<I", handle.read(4))[0]
        w = (data & 0x3FFF) + 1
        h = ((data >> 14) & 0x3FFF) + 1
        return w, h
    if chunk == b"VP8X":
        handle.read(4)
        handle.read(4)
        data = handle.read(6)
        w = (data[0] | (data[1] << 8) | (data[2] << 16)) + 1
        h = (data[3] | (data[4] << 8) | (data[5] << 16)) + 1
        return w, h
    return None
