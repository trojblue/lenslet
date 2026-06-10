from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from ..image_media import ImageMime, normalize_image_mime, read_dimensions_fast
from .index_types import TableIndexData, TableIndexInput
from ..source.paths import (
    LocalSourcePathError,
    dedupe_path,
    derive_http_logical_path,
    derive_logical_path,
    extract_name,
    is_http_url,
    is_s3_uri,
    is_supported_image,
    normalize_item_path,
)
from .schema import coerce_int, coerce_timestamp


@dataclass(frozen=True, slots=True)
class IndexColumns:
    source_values: list[Any]
    path_values: list[Any]
    name_values: list[Any]
    mime_values: list[Any]
    width_values: list[Any]
    height_values: list[Any]
    size_values: list[Any]
    mtime_values: list[Any]
    metrics_values: list[Any]
    metric_columns: tuple[tuple[str, list[Any]], ...]


@dataclass(slots=True)
class LocalSkipCounts:
    disabled: int = 0
    outside_root: int = 0
    resolved_outside_root: int = 0
    missing: int = 0

    def record(self, reason: str | None) -> bool:
        if reason is None:
            return False
        if reason == "disabled":
            self.disabled += 1
        elif reason == "outside_root":
            self.outside_root += 1
        elif reason == "resolved_outside_root":
            self.resolved_outside_root += 1
        elif reason == "missing":
            self.missing += 1
        else:
            raise ValueError(f"unknown local source skip reason: {reason}")
        return True


@dataclass(frozen=True, slots=True)
class RowIdentity:
    source: str
    name: str
    logical_path: str
    mime: ImageMime
    is_s3: bool
    is_http: bool

    @property
    def is_local(self) -> bool:
        return not self.is_s3 and not self.is_http


@dataclass(frozen=True, slots=True)
class LocalSourceResolution:
    resolved_path: str | None
    skip_reason: str | None = None


def _can_scan_uniform_http_rows(context: TableIndexInput, columns: IndexColumns) -> bool:
    _ = columns
    table = context.table
    return table.source_kind == "http" and table.extensionless_source_all_trusted


def _fast_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, os.PathLike):
        return os.fspath(value).strip()
    return str(value).strip()


def _fast_path_folder_and_name(logical_path: str) -> tuple[str, str]:
    if "/" not in logical_path:
        return "", logical_path
    return logical_path.rsplit("/", 1)


def _coerce_source_value(source_value: object) -> str | None:
    if source_value is None:
        return None
    if isinstance(source_value, os.PathLike):
        source_value = os.fspath(source_value)
    if not isinstance(source_value, str):
        return None
    source = source_value.strip()
    return source or None


def _supported_image_name(
    context: TableIndexInput,
    *,
    explicit_name: str,
    fallback_name: str,
    logical_path: str,
) -> str | None:
    image_exts = context.table.image_exts
    for candidate in (explicit_name, fallback_name, extract_name(logical_path)):
        if candidate and is_supported_image(candidate, image_exts):
            return candidate
    return None


def _row_name(columns: IndexColumns, idx: int, fallback_name: str) -> str:
    name_value = columns.name_values[idx]
    return str(name_value).strip() if name_value else fallback_name


def _raw_logical_path(
    table: TableIndexData,
    columns: IndexColumns,
    idx: int,
    source: str,
) -> str:
    if table.path_column is not None:
        logical_value = columns.path_values[idx]
        logical_path = str(logical_value).strip() if logical_value else ""
        if is_s3_uri(logical_path) or is_http_url(logical_path):
            return derive_logical_path(
                logical_path,
                root=table.root,
                local_prefix=table.local_prefix,
                s3_prefixes=table.s3_prefixes,
                s3_use_bucket=table.s3_use_bucket,
            )
        return logical_path
    return derive_logical_path(
        source,
        root=table.root,
        local_prefix=table.local_prefix,
        s3_prefixes=table.s3_prefixes,
        s3_use_bucket=table.s3_use_bucket,
    )


def _relative_child_path(path: str) -> bool:
    return path not in {"", os.pardir} and not path.startswith(os.pardir + os.sep) and not os.path.isabs(path)


def _trim_local_prefix(logical_path: str, local_prefix: str | None) -> str:
    if not logical_path or local_prefix is None or not os.path.isabs(logical_path):
        return logical_path
    try:
        relative_path = os.path.relpath(logical_path, local_prefix)
    except ValueError:
        return logical_path
    return relative_path if _relative_child_path(relative_path) else logical_path


def _image_name_for_row(
    context: TableIndexInput,
    *,
    source: str,
    explicit_name: str,
    fallback_name: str,
    logical_path: str,
) -> str | None:
    if context.source_resolver.allows_extensionless_source_image(source):
        return explicit_name or fallback_name or extract_name(logical_path) or "image"

    supported_name = _supported_image_name(
        context,
        explicit_name=explicit_name,
        fallback_name=fallback_name,
        logical_path=logical_path,
    )
    if supported_name is not None:
        return supported_name
    return None


def _resolve_row_identity(
    context: TableIndexInput,
    columns: IndexColumns,
    idx: int,
    seen_paths: set[str],
) -> RowIdentity | None:
    table = context.table
    source = _coerce_source_value(columns.source_values[idx])
    if source is None:
        return None

    fallback_name = extract_name(source)
    name = _row_name(columns, idx, fallback_name)
    logical_path = _trim_local_prefix(
        _raw_logical_path(table, columns, idx, source),
        table.local_prefix,
    )

    logical_path = normalize_item_path(logical_path)
    if not logical_path:
        return None

    image_name = _image_name_for_row(
        context,
        source=source,
        explicit_name=name,
        fallback_name=fallback_name,
        logical_path=logical_path,
    )
    if image_name is None:
        return None

    logical_path = dedupe_path(logical_path, seen_paths)
    seen_paths.add(logical_path)

    mime = normalize_image_mime(
        columns.mime_values[idx],
        image_name or fallback_name or source,
    )
    is_s3 = is_s3_uri(source)
    is_http = is_http_url(source)
    return RowIdentity(
        source=source,
        name=image_name,
        logical_path=logical_path,
        mime=mime,
        is_s3=is_s3,
        is_http=is_http,
    )


def _resolve_local_source(
    context: TableIndexInput,
    source: str,
) -> LocalSourceResolution:
    policy = context.policy
    resolver = context.source_resolver
    if not policy.allow_local:
        return LocalSourceResolution(resolved_path=None, skip_reason="disabled")
    try:
        if policy.skip_local_realpath_validation:
            resolved = resolver.resolve_local_source_lexical(source)
        else:
            resolved = resolver.resolve_local_source(source)
    except LocalSourcePathError as exc:
        if exc.reason == "resolved_outside_root":
            return LocalSourceResolution(resolved_path=None, skip_reason="resolved_outside_root")
        return LocalSourceResolution(resolved_path=None, skip_reason="outside_root")
    if (not policy.skip_local_realpath_validation) and (not os.path.exists(resolved)):
        return LocalSourceResolution(resolved_path=None, skip_reason="missing")
    return LocalSourceResolution(resolved_path=resolved)


def _resolved_file_size(value: object, local_source: LocalSourceResolution) -> int:
    size = coerce_int(value)
    if size is not None:
        return size
    if local_source.resolved_path is None:
        return 0
    try:
        return os.path.getsize(local_source.resolved_path)
    except OSError:
        return 0


def _resolved_file_mtime(
    value: object,
    local_source: LocalSourceResolution,
    *,
    is_local: bool,
) -> float:
    mtime = coerce_timestamp(value)
    if mtime is not None:
        return mtime
    if not is_local:
        return 0.0
    if local_source.resolved_path is None:
        return time.time()
    try:
        return os.path.getmtime(local_source.resolved_path)
    except OSError:
        return time.time()


def _resolved_dimensions(
    context: TableIndexInput,
    columns: IndexColumns,
    idx: int,
    identity: RowIdentity,
    local_source: LocalSourceResolution,
) -> tuple[int, int, tuple[int, int] | None]:
    width = coerce_int(columns.width_values[idx]) or 0
    height = coerce_int(columns.height_values[idx]) or 0
    if width > 0 and height > 0:
        return width, height, None
    cached = _cached_dimensions_for_row(context.table, idx, identity.source, identity.logical_path)
    if cached is not None:
        return cached[0], cached[1], cached
    if not identity.is_local or context.policy.skip_dimension_probe or local_source.resolved_path is None:
        return width, height, None

    dims = read_dimensions_fast(local_source.resolved_path)
    if dims is None:
        return width, height, None
    return dims[0], dims[1], dims


def _cached_dimensions_for_row(
    table: TableIndexData,
    idx: int,
    source: str,
    logical_path: str,
) -> tuple[int, int] | None:
    overrides = table.dimension_overrides
    if not overrides:
        return None
    cached = overrides.get(idx)
    if cached is None or cached.width <= 0 or cached.height <= 0:
        return None
    if _fast_text(cached.source) != _fast_text(source):
        return None
    if normalize_item_path(cached.logical_path) != normalize_item_path(logical_path):
        return None
    return cached.width, cached.height


def _resolve_row_media_fields(
    context: TableIndexInput,
    columns: IndexColumns,
    idx: int,
    identity: RowIdentity,
    local_source: LocalSourceResolution,
) -> tuple[int, float, int, int, tuple[int, int] | None]:
    size = _resolved_file_size(columns.size_values[idx], local_source)
    mtime = _resolved_file_mtime(columns.mtime_values[idx], local_source, is_local=identity.is_local)
    width, height, discovered_dims = _resolved_dimensions(context, columns, idx, identity, local_source)
    return size, mtime, width, height, discovered_dims
