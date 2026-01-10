from __future__ import annotations
import io
import struct
import zlib
from typing import Any, Dict, List

from PIL import Image, PngImagePlugin, ExifTags


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


_EXIF_TAGS = ExifTags.TAGS
_EXIF_GPS_TAGS = ExifTags.GPSTAGS
_QUICK_FIELDS = ("parameters", "Software", "prompt", "Description")
_QUICK_EXIF_FIELDS = ("Software", "ImageDescription", "UserComment", "XPComment", "Comment")


def _read_bytes(file_obj) -> bytes:
    if hasattr(file_obj, "read"):
        return file_obj.read()
    with open(file_obj, "rb") as f:
        return f.read()


def _decode_bytes(value: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return value.decode(enc)
        except Exception:
            continue
    return repr(value)


def _decode_exif_user_comment(value: bytes) -> str:
    # EXIF UserComment: 8-byte code prefix + comment data
    if len(value) >= 8:
        prefix = value[:8]
        body = value[8:]
        if prefix.startswith(b"ASCII"):
            return body.decode("ascii", "replace").rstrip("\x00")
        if prefix.startswith(b"UNICODE"):
            for enc in ("utf-16-le", "utf-16-be", "utf-8"):
                try:
                    return body.decode(enc, "replace").rstrip("\x00")
                except Exception:
                    continue
            return _decode_bytes(body)
        if prefix.startswith(b"JIS"):
            return body.decode("shift_jis", "replace").rstrip("\x00")
    return _decode_bytes(value)


def _decode_exif_value(value: Any, tag_name: str | None = None) -> Any:
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        if tag_name == "UserComment":
            return _decode_exif_user_comment(raw)
        if tag_name and tag_name.startswith("XP"):
            # XP* fields are UTF-16LE null-terminated
            try:
                return raw.decode("utf-16-le", "replace").rstrip("\x00")
            except Exception:
                return _decode_bytes(raw)
        return _decode_bytes(raw)
    if isinstance(value, (list, tuple, set)):
        return [_decode_exif_value(v, tag_name) for v in value]
    if isinstance(value, dict):
        return {str(k): _decode_exif_value(v, tag_name) for k, v in value.items()}
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        try:
            return float(value)
        except Exception:
            return str(value)
    return value


def _normalize_pil_info(info: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in info.items():
        if k in ("exif", "icc_profile") and isinstance(v, (bytes, bytearray)):
            out[k] = f"bytes[{len(v)}]"
            continue
        if isinstance(v, PngImagePlugin.PngInfo):
            out[k] = "PngInfo(...)"
            continue
        if isinstance(v, (bytes, bytearray)):
            out[k] = _decode_bytes(bytes(v))
            continue
        if isinstance(v, (list, tuple, set)):
            out[k] = [_decode_exif_value(item) for item in v]
            continue
        if isinstance(v, dict):
            out[k] = {str(kk): _decode_exif_value(vv) for kk, vv in v.items()}
            continue
        out[k] = v
    return out


def _exif_to_dict(exif) -> Dict[str, Any]:
    if not exif:
        return {}
    out: Dict[str, Any] = {}
    for tag_id, value in exif.items():
        tag_name = _EXIF_TAGS.get(tag_id, str(tag_id))
        if tag_name == "GPSInfo" and isinstance(value, dict):
            gps_out = {}
            for gps_id, gps_val in value.items():
                gps_name = _EXIF_GPS_TAGS.get(gps_id, str(gps_id))
                gps_out[gps_name] = _decode_exif_value(gps_val, gps_name)
            out[tag_name] = gps_out
            continue
        out[tag_name] = _decode_exif_value(value, tag_name)
    return out


def _build_quick_fields(pil_info: Dict[str, Any], exif: Dict[str, Any]) -> Dict[str, Any]:
    quick_fields: Dict[str, Any] = {}
    for field in _QUICK_FIELDS:
        if field in pil_info:
            quick_fields[field] = pil_info[field]
    for field in _QUICK_EXIF_FIELDS:
        if field in exif:
            if field == "UserComment" and "parameters" not in quick_fields:
                quick_fields["parameters"] = exif[field]
            elif field == "ImageDescription" and "Description" not in quick_fields:
                quick_fields["Description"] = exif[field]
            elif field in ("XPComment", "Comment") and "Description" not in quick_fields:
                quick_fields["Description"] = exif[field]
            elif field == "Software" and "Software" not in quick_fields:
                quick_fields["Software"] = exif[field]
    return quick_fields


def _read_exif_image_info(data: bytes, label: str) -> tuple[Dict[str, Any], Dict[str, Any], Any]:
    try:
        img = Image.open(io.BytesIO(data))
        pil_info = _normalize_pil_info(dict(img.info))
        exif = _exif_to_dict(img.getexif())
        xmp_raw = img.info.get("xmp") or img.info.get("XML:com.adobe.xmp")
        xmp = _decode_bytes(xmp_raw) if isinstance(xmp_raw, (bytes, bytearray)) else xmp_raw
    except Exception as e:
        pil_info = {"_error": f"Pillow failed to open {label}: {e}"}
        exif = {}
        xmp = None
    return pil_info, exif, xmp


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
    data = _read_bytes(file_obj)

    # Parse PNG text chunks manually for full extraction
    found_text_chunks = _parse_png_text_chunks(data)

    # Also get PIL's parsed info (may overlap but provides additional fields)
    pil_info: Dict[str, Any] = {}
    try:
        img = Image.open(io.BytesIO(data))
        pil_info = _normalize_pil_info(dict(img.info))
    except Exception as e:
        pil_info = {"_error": f"Pillow failed to open PNG: {e}"}

    # Build quick_fields from commonly-used metadata keys
    quick_fields: Dict[str, Any] = {}
    for field in _QUICK_FIELDS:
        if field in pil_info:
            quick_fields[field] = pil_info[field]
    for chunk in found_text_chunks:
        keyword = chunk.get("keyword", "")
        if keyword in _QUICK_FIELDS and keyword not in quick_fields:
            quick_fields[keyword] = chunk.get("text", "")

    return {
        "found_text_chunks": found_text_chunks,
        "pil_info": pil_info,
        "quick_fields": quick_fields,
    }


def read_jpeg_info(file_obj) -> Dict[str, Any]:
    data = _read_bytes(file_obj)
    pil_info, exif, xmp = _read_exif_image_info(data, "JPEG")
    quick_fields = _build_quick_fields(pil_info, exif)

    return {
        "exif": exif,
        "xmp": xmp,
        "pil_info": pil_info,
        "quick_fields": quick_fields,
    }


def read_webp_info(file_obj) -> Dict[str, Any]:
    data = _read_bytes(file_obj)
    pil_info, exif, xmp = _read_exif_image_info(data, "WebP")
    quick_fields = _build_quick_fields(pil_info, exif)

    return {
        "exif": exif,
        "xmp": xmp,
        "pil_info": pil_info,
        "quick_fields": quick_fields,
    }
