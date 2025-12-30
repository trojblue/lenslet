from __future__ import annotations
import io
import struct
import zlib
from typing import Any, Dict, List

from PIL import Image, PngImagePlugin


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _parse_png_text_chunks(data: bytes) -> List[Dict[str, Any]]:
    """
    Parse PNG chunks and extract tEXt, zTXt, and iTXt entries.
    """
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("Not a PNG file.")

    pos = len(PNG_SIGNATURE)
    out: List[Dict[str, Any]] = []

    while pos + 8 <= len(data):
        # Read chunk length and type
        length = struct.unpack(">I", data[pos:pos+4])[0]
        ctype = data[pos+4:pos+8]
        pos += 8

        if pos + length + 4 > len(data):
            break

        cdata = data[pos:pos+length]
        pos += length

        # Skip CRC (4 bytes)
        pos += 4

        if ctype == b"tEXt":
            # Latin-1: key\0value
            try:
                null_idx = cdata.index(b"\x00")
                key = cdata[:null_idx].decode("latin-1", "replace")
                text = cdata[null_idx+1:].decode("latin-1", "replace")
                out.append({"type": "tEXt", "keyword": key, "text": text})
            except Exception:
                pass

        elif ctype == b"zTXt":
            # key\0compression_method(1) + compressed data
            try:
                null_idx = cdata.index(b"\x00")
                key = cdata[:null_idx].decode("latin-1", "replace")
                method = cdata[null_idx+1:null_idx+2]
                comp = cdata[null_idx+2:]
                if method == b"\x00":  # zlib/deflate
                    text = zlib.decompress(comp).decode("latin-1", "replace")
                    out.append({"type": "zTXt", "keyword": key, "text": text})
            except Exception:
                pass

        elif ctype == b"iTXt":
            # UTF-8: key\0flag(1)\0method(1)\0lang\0translated\0text
            try:
                i0 = cdata.index(b"\x00")
                key = cdata[:i0].decode("latin-1", "replace")
                comp_flag = cdata[i0+1:i0+2]
                comp_method = cdata[i0+2:i0+3]
                rest = cdata[i0+3:]

                i1 = rest.index(b"\x00")
                language_tag = rest[:i1].decode("ascii", "replace")
                rest2 = rest[i1+1:]

                i2 = rest2.index(b"\x00")
                translated_keyword = rest2[:i2].decode("utf-8", "replace")
                text_bytes = rest2[i2+1:]

                if comp_flag == b"\x01" and comp_method == b"\x00":
                    text = zlib.decompress(text_bytes).decode("utf-8", "replace")
                else:
                    text = text_bytes.decode("utf-8", "replace")

                out.append({
                    "type": "iTXt",
                    "keyword": key,
                    "language_tag": language_tag,
                    "translated_keyword": translated_keyword,
                    "text": text,
                })
            except Exception:
                pass

        if ctype == b"IEND":
            break

    return out


def read_png_info(file_obj) -> Dict[str, Any]:
    """
    Given an uploaded file (path or file-like), return structured PNG text info.
    
    Returns a dict with:
    - found_text_chunks: list of parsed PNG text chunks (tEXt, zTXt, iTXt)
    - pil_info: raw PIL .info dict
    - quick_fields: commonly-used fields extracted for convenience
    """
    if hasattr(file_obj, "read"):
        data = file_obj.read()
    else:
        with open(file_obj, "rb") as f:
            data = f.read()

    # Parse PNG text chunks manually for full extraction
    found_text_chunks = _parse_png_text_chunks(data)

    # Also get PIL's parsed info (may overlap but provides additional fields)
    pil_info: Dict[str, Any] = {}
    try:
        img = Image.open(io.BytesIO(data))
        pil_info = dict(img.info)
        for k, v in list(pil_info.items()):
            if isinstance(v, (bytes, bytearray)):
                try:
                    pil_info[k] = v.decode("utf-8", "replace")
                except Exception:
                    pil_info[k] = repr(v)
            elif isinstance(v, PngImagePlugin.PngInfo):
                pil_info[k] = "PngInfo(...)"
    except Exception as e:
        pil_info = {"_error": f"Pillow failed to open PNG: {e}"}

    # Build quick_fields from commonly-used metadata keys
    quick_fields: Dict[str, Any] = {}
    # First check PIL info for these fields
    for field in ("parameters", "Software", "prompt", "Description"):
        if field in pil_info:
            quick_fields[field] = pil_info[field]
    # Also check extracted chunks as fallback
    for chunk in found_text_chunks:
        keyword = chunk.get("keyword", "")
        if keyword in ("parameters", "Software", "prompt", "Description"):
            if keyword not in quick_fields:
                quick_fields[keyword] = chunk.get("text", "")

    return {
        "found_text_chunks": found_text_chunks,
        "pil_info": pil_info,
        "quick_fields": quick_fields,
    }

