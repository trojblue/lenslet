from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse


def is_s3_uri(path: str) -> bool:
    return path.startswith("s3://")


def is_http_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


def is_supported_image(name: str, image_exts: tuple[str, ...]) -> bool:
    return name.lower().endswith(image_exts)


def extract_name(value: str) -> str:
    if is_s3_uri(value) or is_http_url(value):
        parsed = urlparse(value)
        return os.path.basename(parsed.path)
    return os.path.basename(value)


def normalize_path(path: str) -> str:
    return path.strip("/") if path else ""


def normalize_item_path(path: str) -> str:
    normalized = (path or "").replace("\\", "/").lstrip("/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def canonical_meta_key(path: str) -> str:
    cleaned = (path or "").replace("\\", "/").strip()
    if not cleaned:
        return "/"
    cleaned = "/" + cleaned.lstrip("/")
    if cleaned != "/":
        cleaned = cleaned.rstrip("/")
    return cleaned


def dedupe_path(path: str, seen: set[str]) -> str:
    if path not in seen:
        return path
    stem, ext = os.path.splitext(path)
    index = 2
    while f"{stem}-{index}{ext}" in seen:
        index += 1
    return f"{stem}-{index}{ext}"


def compute_s3_prefixes(values: list[Any]) -> tuple[dict[str, str], bool]:
    buckets: dict[str, list[list[str]]] = {}
    for raw in values:
        if raw is None:
            continue
        if isinstance(raw, os.PathLike):
            raw = os.fspath(raw)
        if not isinstance(raw, str):
            continue
        uri = raw.strip()
        if not uri.startswith("s3://"):
            continue
        parsed = urlparse(uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            continue
        parts = [part for part in key.split("/") if part]
        if not parts:
            continue
        buckets.setdefault(bucket, []).append(parts)

    if not buckets:
        return {}, False

    prefixes: dict[str, str] = {}
    for bucket, bucket_paths in buckets.items():
        if not bucket_paths:
            continue
        common = bucket_paths[0]
        for parts in bucket_paths[1:]:
            max_len = min(len(common), len(parts))
            idx = 0
            while idx < max_len and common[idx] == parts[idx]:
                idx += 1
            common = common[:idx]
            if not common:
                break
        prefix = "/".join(common)
        if prefix:
            prefix = prefix.rstrip("/") + "/"
        prefixes[bucket] = prefix

    use_bucket = len(prefixes) > 1
    return prefixes, use_bucket


def compute_local_prefix(values: list[Any]) -> str | None:
    local_paths: list[str] = []
    for raw in values:
        if raw is None:
            continue
        if isinstance(raw, os.PathLike):
            raw = os.fspath(raw)
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if not value:
            continue
        if is_s3_uri(value) or is_http_url(value):
            continue
        if not os.path.isabs(value):
            continue
        local_paths.append(os.path.normpath(value))

    if not local_paths:
        return None

    try:
        common = os.path.commonpath(local_paths)
    except ValueError:
        return None

    if not common or common == os.path.sep:
        return common if common else None

    # If files sit directly under the common prefix, step up one level
    # so the prefix folder itself stays visible in the UI.
    if any(os.path.dirname(path) == common for path in local_paths):
        parent = os.path.dirname(common)
        if parent and parent != common:
            return parent
    return common


def derive_logical_path(
    source: str,
    *,
    root: str | None,
    local_prefix: str | None,
    s3_prefixes: dict[str, str],
    s3_use_bucket: bool,
) -> str:
    if is_s3_uri(source) or is_http_url(source):
        parsed = urlparse(source)
        host = parsed.netloc
        path = parsed.path.lstrip("/")
        if is_s3_uri(source):
            prefix = s3_prefixes.get(host, "")
            trimmed = path[len(prefix):] if prefix and path.startswith(prefix) else path
            trimmed = trimmed.lstrip("/")
            if s3_use_bucket and host:
                return f"{host}/{trimmed}" if trimmed else host
            return trimmed or os.path.basename(path)
        if host and path:
            return f"{host}/{path}"
        return host or path

    if os.path.isabs(source):
        if local_prefix:
            try:
                rel = os.path.relpath(source, local_prefix)
                if not rel.startswith(".."):
                    return rel
            except ValueError:
                pass
        if root:
            try:
                return os.path.relpath(source, root)
            except ValueError:
                return os.path.basename(source)
        return os.path.basename(source)

    if root:
        return source
    return os.path.basename(source)


def resolve_local_source(
    source: str,
    *,
    root: str | None,
    root_real: str | None,
    allow_local: bool,
) -> str:
    if not allow_local:
        raise ValueError("local sources are disabled")
    if os.path.isabs(source) or not root:
        return source
    candidate = os.path.abspath(os.path.join(root, source))
    real = os.path.realpath(candidate)
    resolved_root_real = root_real or os.path.realpath(root)
    try:
        common = os.path.commonpath([resolved_root_real, real])
    except Exception:
        raise ValueError("invalid path")
    if common != resolved_root_real:
        raise ValueError("path escapes base_dir")
    return real
