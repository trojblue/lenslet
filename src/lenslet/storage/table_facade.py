from __future__ import annotations

from io import BytesIO
from typing import Any
from urllib.parse import urlparse

from PIL import Image

from .s3 import S3_DEPENDENCY_ERROR, create_s3_client


def table_to_columns(table: Any) -> tuple[list[str], dict[str, list[Any]], int]:
    if hasattr(table, "to_pydict"):
        data = table.to_pydict()
        columns = list(getattr(table, "schema", None).names if hasattr(table, "schema") else data.keys())
    elif hasattr(table, "columns") and hasattr(table, "to_dict"):
        columns = list(table.columns)
        data = {col: table[col].tolist() for col in columns}
    elif isinstance(table, list):
        if not table:
            return [], {}, 0
        if not all(isinstance(row, dict) for row in table):
            raise ValueError("table list must contain dict rows")
        columns = list(table[0].keys())
        for row in table[1:]:
            for key in row.keys():
                if key not in columns:
                    columns.append(key)
        data = {col: [] for col in columns}
        for row in table:
            for col in columns:
                data[col].append(row.get(col))
    else:
        raise TypeError("table must be a pandas DataFrame, pyarrow.Table, or list of dicts")

    row_count = 0
    if columns:
        row_count = len(data.get(columns[0], []))
    return columns, data, row_count


def read_bytes(storage: Any, path: str) -> bytes:
    norm = storage._normalize_item_path(path)
    source = storage._source_paths.get(norm)
    if source is None:
        raise FileNotFoundError(path)

    if storage._is_s3_uri(source):
        import urllib.request

        try:
            url = storage._get_presigned_url(source)
            with urllib.request.urlopen(url) as response:
                return response.read()
        except Exception as exc:
            raise RuntimeError(f"Failed to download from S3: {exc}")
    if storage._is_http_url(source):
        import urllib.request

        try:
            with urllib.request.urlopen(source) as response:
                return response.read()
        except Exception as exc:
            raise RuntimeError(f"Failed to download from URL: {exc}")

    try:
        resolved = storage._resolve_local_source(source)
    except ValueError as exc:
        raise FileNotFoundError(path) from exc
    with open(resolved, "rb") as handle:
        return handle.read()


def make_thumbnail(
    img_bytes: bytes,
    *,
    thumb_size: int,
    thumb_quality: int,
) -> tuple[bytes, tuple[int, int] | None]:
    with Image.open(BytesIO(img_bytes)) as im:
        w, h = im.size
        short = min(w, h)
        if short > thumb_size:
            scale = thumb_size / short
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            im = im.convert("RGB").resize((new_w, new_h), Image.LANCZOS)
        else:
            im = im.convert("RGB")
        out = BytesIO()
        im.save(out, format="WEBP", quality=thumb_quality, method=6)
        return out.getvalue(), (w, h)


def get_thumbnail(storage: Any, path: str) -> bytes | None:
    norm = storage._normalize_item_path(path)
    if norm in storage._thumbnails:
        return storage._thumbnails[norm]

    try:
        raw = storage.read_bytes(norm)
        thumb, dims = storage._make_thumbnail(raw)
        storage._thumbnails[norm] = thumb
        if dims:
            storage._dimensions[norm] = dims
            item = storage._items.get(norm)
            if item:
                item.width, item.height = dims
        return thumb
    except Exception:
        return None


def get_dimensions(storage: Any, path: str) -> tuple[int, int]:
    norm = storage._normalize_item_path(path)
    if norm in storage._dimensions:
        return storage._dimensions[norm]
    item = storage._items.get(norm)
    if not item:
        return 0, 0

    source = storage._source_paths.get(norm)
    if source and (storage._is_s3_uri(source) or storage._is_http_url(source)):
        url = source
        if storage._is_s3_uri(source):
            try:
                url = storage._get_presigned_url(source)
            except Exception:
                url = None
        if url:
            dims, total = storage._get_remote_header_info(url, item.name)
            if total:
                item.size = total
            if dims:
                storage._dimensions[norm] = dims
                item.width, item.height = dims
                return dims

    try:
        raw = storage.read_bytes(norm)
        with Image.open(BytesIO(raw)) as im:
            w, h = im.size
            storage._dimensions[norm] = (w, h)
            item.width = w
            item.height = h
            return w, h
    except Exception:
        return 0, 0


def get_metadata(storage: Any, path: str) -> dict:
    norm = storage._normalize_item_path(path)
    key = storage._canonical_meta_key(norm)
    if key in storage._metadata:
        return storage._metadata[key]

    w, h = storage._dimensions.get(norm, (0, 0))
    item = storage._items.get(norm)
    if item and (w == 0 or h == 0):
        w, h = item.width, item.height

    meta = {
        "width": w,
        "height": h,
        "tags": [],
        "notes": "",
        "star": None,
        "version": 1,
        "updated_at": "",
        "updated_by": "server",
    }
    storage._metadata[key] = meta
    return meta


def set_metadata(storage: Any, path: str, meta: dict) -> None:
    norm = storage._normalize_item_path(path)
    key = storage._canonical_meta_key(norm)
    storage._metadata[key] = meta


def search_items(storage: Any, query: str = "", path: str = "/", limit: int = 100) -> list[Any]:
    q = (query or "").lower()
    norm = storage._normalize_path(path)
    scope_prefix = f"{norm}/" if norm else ""

    results: list[Any] = []
    for item in storage._items.values():
        logical_path = item.path.lstrip("/")
        if norm and not (logical_path == norm or logical_path.startswith(scope_prefix)):
            continue
        meta = storage.get_metadata(item.path)
        parts = [
            item.name,
            " ".join(meta.get("tags", [])),
            meta.get("notes", ""),
        ]
        if storage._include_source_in_search:
            source = storage._source_paths.get(item.path, "")
            if source:
                parts.append(source)
            if item.url:
                parts.append(item.url)
        haystack = " ".join(parts).lower()
        if q in haystack:
            results.append(item)
            if len(results) >= limit:
                break
    return results


def get_s3_client(storage: Any):
    with storage._s3_client_lock:
        if storage._s3_client is not None:
            return storage._s3_client
        storage._s3_session, storage._s3_client = create_s3_client()
        storage._s3_client_creations += 1
        return storage._s3_client


def get_presigned_url(storage: Any, s3_uri: str, *, expires_in: int = 3600) -> str:
    try:
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(S3_DEPENDENCY_ERROR) from exc

    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {s3_uri}")

    try:
        s3_client = storage._get_s3_client()
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError, NoCredentialsError) as exc:
        raise RuntimeError(f"Failed to presign S3 URI: {exc}") from exc


def guess_mime(name: str) -> str:
    n = name.lower()
    if n.endswith(".webp"):
        return "image/webp"
    if n.endswith(".png"):
        return "image/png"
    return "image/jpeg"
