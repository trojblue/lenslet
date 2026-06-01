from __future__ import annotations

from collections.abc import Iterable
import os
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


class LocalSourcePathError(ValueError):
    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


def is_s3_uri(path: str) -> bool:
    return path.startswith("s3://")


def is_http_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


def is_supported_image(name: str, image_exts: tuple[str, ...]) -> bool:
    return name.lower().endswith(image_exts)


def extract_name(value: str) -> str:
    if is_s3_uri(value) or is_http_url(value):
        parsed = urlparse(value)
        return PurePosixPath(parsed.path).name
    return Path(value).name


def normalize_path(path: str) -> str:
    return path.strip("/") if path else ""


def normalize_item_path(path: str) -> str:
    normalized = (path or "").replace("\\", "/").lstrip("/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def canonical_sidecar_key(path: str) -> str:
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
    ext = PurePosixPath(path).suffix
    stem = path[: -len(ext)] if ext else path
    index = 2
    while f"{stem}-{index}{ext}" in seen:
        index += 1
    return f"{stem}-{index}{ext}"


def _s3_key_parts(raw: object) -> tuple[str, list[str]] | None:
    if raw is None:
        return None
    if isinstance(raw, os.PathLike):
        raw = os.fspath(raw)
    if not isinstance(raw, str):
        return None
    uri = raw.strip()
    if not uri.startswith("s3://"):
        return None
    parsed = urlparse(uri)
    bucket = parsed.netloc
    parts = [part for part in parsed.path.lstrip("/").split("/") if part]
    if not bucket or not parts:
        return None
    return bucket, parts


def _common_path_parts(paths: list[list[str]]) -> list[str]:
    common = paths[0]
    for parts in paths[1:]:
        idx = 0
        max_len = min(len(common), len(parts))
        while idx < max_len and common[idx] == parts[idx]:
            idx += 1
        common = common[:idx]
        if not common:
            break
    return common


def _s3_prefix(paths: list[list[str]]) -> str:
    common = _common_path_parts(paths)
    prefix = "/".join(common)
    return prefix.rstrip("/") + "/" if prefix else ""


def compute_s3_prefixes(values: Iterable[object]) -> tuple[dict[str, str], bool]:
    buckets: dict[str, list[list[str]]] = {}
    for raw in values:
        parsed = _s3_key_parts(raw)
        if parsed is not None:
            bucket, parts = parsed
            buckets.setdefault(bucket, []).append(parts)

    if not buckets:
        return {}, False

    prefixes: dict[str, str] = {}
    for bucket, bucket_paths in buckets.items():
        if bucket_paths:
            prefixes[bucket] = _s3_prefix(bucket_paths)

    use_bucket = len(prefixes) > 1
    return prefixes, use_bucket


def _absolute_local_source(raw: object) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, os.PathLike):
        raw = os.fspath(raw)
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value or is_s3_uri(value) or is_http_url(value) or not Path(value).is_absolute():
        return None
    return os.path.normpath(value)


def _absolute_local_sources(values: Iterable[object]) -> list[str]:
    local_paths: list[str] = []
    for raw in values:
        local_path = _absolute_local_source(raw)
        if local_path is not None:
            local_paths.append(local_path)
    return local_paths


def _common_local_path(paths: list[str]) -> str | None:
    if not paths:
        return None
    common_parts = _common_path_parts([list(Path(path).parts) for path in paths])
    if not common_parts:
        return None
    return str(Path(*common_parts))


def _visible_local_prefix(common: str, local_paths: list[str]) -> str:
    common_path = Path(common)
    if common_path.parent == common_path:
        return common
    if any(Path(path).parent == common_path for path in local_paths):
        parent = common_path.parent
        if parent != common_path:
            return str(parent)
    return common


def compute_local_prefix(values: Iterable[object]) -> str | None:
    local_paths = _absolute_local_sources(values)
    if not local_paths:
        return None

    common = _common_local_path(local_paths)
    if common is None:
        return None

    # If files sit directly under the common prefix, step up one level
    # so the prefix folder itself stays visible in the UI.
    return _visible_local_prefix(common, local_paths)


def _derive_s3_logical_path(source: str, *, s3_prefixes: dict[str, str], s3_use_bucket: bool) -> str:
    parsed = urlparse(source)
    bucket = parsed.netloc
    path = parsed.path.lstrip("/")
    prefix = s3_prefixes.get(bucket, "")
    trimmed = path[len(prefix):] if prefix and path.startswith(prefix) else path
    trimmed = trimmed.lstrip("/")
    if s3_use_bucket and bucket:
        return f"{bucket}/{trimmed}" if trimmed else bucket
    return trimmed or PurePosixPath(path).name


def _derive_http_logical_path(source: str) -> str:
    parsed = urlparse(source)
    host = parsed.netloc
    path = parsed.path.lstrip("/")
    if host and path:
        return f"{host}/{path}"
    return host or path


def _relpath_within_prefix(source: str, local_prefix: str | None) -> str | None:
    if not local_prefix:
        return None
    try:
        rel = Path(source).relative_to(local_prefix)
    except ValueError:
        return None
    return rel.as_posix()


def _derive_absolute_local_logical_path(source: str, *, root: str | None, local_prefix: str | None) -> str:
    rel = _relpath_within_prefix(source, local_prefix)
    if rel is not None:
        return rel
    if root:
        try:
            return os.path.relpath(source, root)
        except ValueError:
            return Path(source).name
    return Path(source).name


def derive_logical_path(
    source: str,
    *,
    root: str | None,
    local_prefix: str | None,
    s3_prefixes: dict[str, str],
    s3_use_bucket: bool,
) -> str:
    if is_s3_uri(source):
        return _derive_s3_logical_path(source, s3_prefixes=s3_prefixes, s3_use_bucket=s3_use_bucket)
    if is_http_url(source):
        return _derive_http_logical_path(source)

    if Path(source).is_absolute():
        return _derive_absolute_local_logical_path(source, root=root, local_prefix=local_prefix)

    if root:
        return source
    return Path(source).name


def resolve_local_source(
    source: str,
    *,
    root: str | None,
    root_real: str | None,
    allow_local: bool,
) -> str:
    if not allow_local:
        raise ValueError("local sources are disabled")
    if not root:
        return source

    root_abs = os.path.abspath(root)
    source_path = Path(source)
    candidate = str(source_path if source_path.is_absolute() else Path(root_abs) / source)
    candidate = os.path.abspath(candidate)
    try:
        lexical_common = os.path.commonpath([root_abs, candidate])
    except ValueError as exc:
        raise LocalSourcePathError("invalid path", reason="invalid") from exc
    if lexical_common != root_abs:
        raise LocalSourcePathError("path escapes base_dir", reason="outside_root")

    real = os.path.realpath(candidate)
    resolved_root_real = root_real or os.path.realpath(root_abs)
    try:
        common = os.path.commonpath([resolved_root_real, real])
    except ValueError as exc:
        raise LocalSourcePathError("invalid path", reason="invalid") from exc
    if common != resolved_root_real:
        raise LocalSourcePathError("path resolves outside base_dir", reason="resolved_outside_root")
    return real


def resolve_local_source_lexical(
    source: str,
    *,
    root: str | None,
    allow_local: bool,
) -> str:
    """Resolve local source path without symlink canonicalization.

    This is a fast lexical guard: it blocks ``..`` traversal outside ``root``,
    but does not resolve symlinks.
    """
    if not allow_local:
        raise ValueError("local sources are disabled")
    if not root:
        return source

    source_path = Path(source)
    candidate = str(source_path if source_path.is_absolute() else Path(root) / source)
    candidate = os.path.abspath(candidate)
    try:
        common = os.path.commonpath([root, candidate])
    except ValueError as exc:
        raise LocalSourcePathError("invalid path", reason="invalid") from exc
    if common != root:
        raise LocalSourcePathError("path escapes base_dir", reason="outside_root")
    return candidate
