from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeAlias

from ..progress import ProgressTicker
from .display import is_internal_metric_key
from ..index_assembly import IndexAssemblyResult, ScannedRow
from ..image_media import ImageMime, guess_image_mime, normalize_image_mime, read_dimensions_fast
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
    normalize_path,
)
from .schema import coerce_float, coerce_int, coerce_timestamp

RemoteDimensionTask: TypeAlias = tuple[str, Any, str, str]


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
class ScanResult:
    rows: list[ScannedRow]
    remote_tasks: list[RemoteDimensionTask]
    skipped_local_disabled: int
    skipped_local_outside_root: int
    skipped_local_resolved_outside_root: int
    skipped_local_missing: int


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


def scan_rows(
    context: TableIndexInput,
    columns: IndexColumns,
    *,
    item_factory: Callable[..., Any],
    lazy_metrics_provider: Callable[[int], dict[str, float]] | None = None,
) -> ScanResult:
    if _can_scan_uniform_http_rows(context, columns):
        return _scan_uniform_http_rows(
            context,
            columns,
            item_factory=item_factory,
            lazy_metrics_provider=lazy_metrics_provider,
        )

    table = context.table
    policy = context.policy
    row_count = table.row_count
    seen_paths: set[str] = set()
    rows: list[ScannedRow] = []
    remote_tasks: list[RemoteDimensionTask] = []
    skipped = LocalSkipCounts()

    progress = ProgressTicker(
        total=row_count,
        label=f"table:{table.source_column}",
        emit=context.progress,
    )

    for idx in range(row_count):
        identity = _resolve_row_identity(context, columns, idx, seen_paths)
        if identity is None:
            progress.step()
            continue
        local_source = (
            _resolve_local_source(context, identity.source)
            if identity.is_local
            else LocalSourceResolution(resolved_path=None)
        )
        if skipped.record(local_source.skip_reason):
            progress.step()
            continue

        size, mtime, width, height, discovered_dims = _resolve_row_media_fields(
            context,
            columns,
            idx,
            identity,
            local_source,
        )
        metrics = None if lazy_metrics_provider is not None else _collect_row_metrics(context, columns, idx)

        item_kwargs = {
            "path": identity.logical_path,
            "name": identity.name,
            "mime": identity.mime,
            "width": width,
            "height": height,
            "size": size,
            "mtime": mtime or 0.0,
            "url": identity.source if identity.is_http else None,
            "source": identity.source,
            "metrics": metrics,
            "metric_labels": {},
        }
        if lazy_metrics_provider is not None:
            item_kwargs["row_idx"] = idx
            item_kwargs["metrics_provider"] = lazy_metrics_provider
        item = item_factory(**item_kwargs)

        folder = os.path.dirname(identity.logical_path).replace("\\", "/")
        folder_norm = normalize_path(folder)

        rows.append(
            ScannedRow(
                row_idx=idx,
                logical_path=identity.logical_path,
                source=identity.source,
                folder_norm=folder_norm,
                item=item,
                discovered_dims=discovered_dims,
            )
        )

        if (identity.is_s3 or identity.is_http) and (width == 0 or height == 0) and not policy.skip_dimension_probe:
            remote_tasks.append((identity.logical_path, item, identity.source, identity.name))

        progress.step()

    progress.finish()
    return ScanResult(
        rows=rows,
        remote_tasks=remote_tasks,
        skipped_local_disabled=skipped.disabled,
        skipped_local_outside_root=skipped.outside_root,
        skipped_local_resolved_outside_root=skipped.resolved_outside_root,
        skipped_local_missing=skipped.missing,
    )


def try_build_uniform_http_indexes(
    context: TableIndexInput,
    columns: IndexColumns,
    *,
    generated_at: str,
    item_factory: Callable[..., Any],
    index_factory: Callable[..., Any],
    lazy_metrics_provider: Callable[[int], dict[str, float]] | None = None,
    fast_item_factory: Callable[..., Any] | None = None,
) -> IndexAssemblyResult | None:
    if not _can_scan_uniform_http_rows(context, columns):
        return None
    return _build_uniform_http_indexes(
        context,
        columns,
        generated_at=generated_at,
        item_factory=item_factory,
        index_factory=index_factory,
        lazy_metrics_provider=lazy_metrics_provider,
        fast_item_factory=fast_item_factory,
    )


def _folder_index(
    indexes: dict[str, Any],
    folder_norm: str,
    *,
    generated_at: str,
    index_factory: Callable[..., Any],
) -> Any:
    index = indexes.get(folder_norm)
    if index is None:
        index = index_factory(
            path="/" + folder_norm if folder_norm else "/",
            generated_at=generated_at,
            items=[],
            dirs=[],
        )
        indexes[folder_norm] = index
    return index


def _record_folder_children(
    folder_norm: str,
    *,
    seen_folders: set[str],
    dir_children: dict[str, set[str]],
) -> None:
    if folder_norm in seen_folders:
        return
    seen_folders.add(folder_norm)
    parts = folder_norm.split("/") if folder_norm else []
    for depth in range(len(parts)):
        parent = "/".join(parts[:depth])
        child = parts[depth]
        dir_children.setdefault(parent, set()).add(child)


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


def _scan_uniform_http_rows(
    context: TableIndexInput,
    columns: IndexColumns,
    *,
    item_factory: Callable[..., Any],
    lazy_metrics_provider: Callable[[int], dict[str, float]] | None,
) -> ScanResult:
    table = context.table
    policy = context.policy
    row_count = table.row_count
    seen_paths: set[str] = set()
    rows: list[ScannedRow] = []
    remote_tasks: list[RemoteDimensionTask] = []

    source_values = columns.source_values
    path_values = columns.path_values
    name_values = columns.name_values
    mime_values = columns.mime_values
    width_values = columns.width_values
    height_values = columns.height_values
    size_values = columns.size_values
    mtime_values = columns.mtime_values
    has_path_column = table.path_column is not None
    has_name_column = table.name_column is not None
    has_mime_column = table.mime_column is not None
    has_size_column = table.size_column is not None
    has_mtime_column = table.mtime_column is not None
    has_width_column = table.width_column is not None
    has_height_column = table.height_column is not None
    needs_path_to_row = not policy.skip_dimension_probe

    progress = ProgressTicker(
        total=row_count,
        label=f"table:{table.source_column}",
        emit=context.progress,
    )

    for idx in range(row_count):
        source = _fast_text(source_values[idx])
        if not source:
            progress.step()
            continue

        if has_path_column:
            logical_value = _fast_text(path_values[idx]) or source
            if is_http_url(logical_value):
                logical_path = normalize_item_path(derive_http_logical_path(logical_value))
                folder_norm, fallback_name = _fast_path_folder_and_name(logical_path) if logical_path else ("", "")
            elif is_s3_uri(logical_value):
                logical_path = normalize_item_path(
                    derive_logical_path(
                        logical_value,
                        root=table.root,
                        local_prefix=table.local_prefix,
                        s3_prefixes=table.s3_prefixes,
                        s3_use_bucket=table.s3_use_bucket,
                    )
                )
                folder_norm, fallback_name = (
                    _fast_path_folder_and_name(logical_path) if logical_path else ("", extract_name(source))
                )
            else:
                logical_path = normalize_item_path(logical_value)
                folder_norm, _path_name = _fast_path_folder_and_name(logical_path)
                fallback_name = extract_name(source)
        else:
            logical_path = derive_http_logical_path(source)
            folder_norm, fallback_name = _fast_path_folder_and_name(logical_path) if logical_path else ("", "")
        if not logical_path:
            progress.step()
            continue

        explicit_name = _fast_text(name_values[idx]) if has_name_column else ""
        image_name = explicit_name or fallback_name or extract_name(logical_path) or "image"

        if logical_path in seen_paths:
            logical_path = dedupe_path(logical_path, seen_paths)
        seen_paths.add(logical_path)

        mime = normalize_image_mime(mime_values[idx], image_name) if has_mime_column else guess_image_mime(image_name)
        size = (coerce_int(size_values[idx]) or 0) if has_size_column else 0
        mtime = (coerce_timestamp(mtime_values[idx]) or 0.0) if has_mtime_column else 0.0
        try:
            width = int(width_values[idx]) if has_width_column and width_values[idx] is not None else 0
        except (TypeError, ValueError, OverflowError):
            width = 0
        try:
            height = int(height_values[idx]) if has_height_column and height_values[idx] is not None else 0
        except (TypeError, ValueError, OverflowError):
            height = 0

        metrics = None if lazy_metrics_provider is not None else _collect_row_metrics(context, columns, idx)
        if lazy_metrics_provider is None:
            item = item_factory(
                path=logical_path,
                name=image_name,
                mime=mime,
                width=width,
                height=height,
                size=size,
                mtime=mtime,
                url=source,
                source=source,
                metrics=metrics,
                metric_labels={},
            )
        else:
            item = item_factory(
                path=logical_path,
                name=image_name,
                mime=mime,
                width=width,
                height=height,
                size=size,
                mtime=mtime,
                url=source,
                source=source,
                metrics=None,
                metric_labels={},
                row_idx=idx,
                metrics_provider=lazy_metrics_provider,
            )

        rows.append(
            ScannedRow(
                row_idx=idx,
                logical_path=logical_path,
                source=source,
                folder_norm=folder_norm,
                item=item,
                discovered_dims=None,
            )
        )

        if (width == 0 or height == 0) and not policy.skip_dimension_probe:
            remote_tasks.append((logical_path, item, source, image_name))

        progress.step()

    progress.finish()
    return ScanResult(
        rows=rows,
        remote_tasks=remote_tasks,
        skipped_local_disabled=0,
        skipped_local_outside_root=0,
        skipped_local_resolved_outside_root=0,
        skipped_local_missing=0,
    )


def _build_uniform_http_indexes(
    context: TableIndexInput,
    columns: IndexColumns,
    *,
    generated_at: str,
    item_factory: Callable[..., Any],
    index_factory: Callable[..., Any],
    lazy_metrics_provider: Callable[[int], dict[str, float]] | None,
    fast_item_factory: Callable[..., Any] | None,
) -> IndexAssemblyResult:
    table = context.table
    policy = context.policy
    row_count = table.row_count
    seen_paths: set[str] = set()
    indexes: dict[str, Any] = {}
    items: dict[str, Any] = {}
    source_paths: dict[str, str] = {}
    row_dimensions: list[tuple[int, int] | None] = [None] * row_count
    path_to_row: dict[str, int] = {}
    row_to_path: list[str | None] = [None] * row_count
    dimensions: dict[str, tuple[int, int]] = {}
    remote_tasks: list[RemoteDimensionTask] = []
    dir_children: dict[str, set[str]] = {}
    seen_folders: set[str] = set()

    source_values = columns.source_values
    path_values = columns.path_values
    name_values = columns.name_values
    mime_values = columns.mime_values
    width_values = columns.width_values
    height_values = columns.height_values
    size_values = columns.size_values
    mtime_values = columns.mtime_values
    has_path_column = table.path_column is not None
    has_name_column = table.name_column is not None
    has_mime_column = table.mime_column is not None
    has_size_column = table.size_column is not None
    has_mtime_column = table.mtime_column is not None
    has_width_column = table.width_column is not None
    has_height_column = table.height_column is not None
    needs_path_to_row = not policy.skip_dimension_probe

    progress = ProgressTicker(
        total=row_count,
        label=f"table:{table.source_column}",
        emit=context.progress,
    )
    progress_batch_size = 2048

    for idx in range(row_count):
        if (idx + 1) % progress_batch_size == 0:
            progress.step(progress_batch_size)

        source = _fast_text(source_values[idx])
        if not source or not is_http_url(source):
            continue

        if has_path_column:
            logical_value = _fast_text(path_values[idx]) or source
            if is_http_url(logical_value):
                logical_path = normalize_item_path(derive_http_logical_path(logical_value))
                folder_norm, fallback_name = _fast_path_folder_and_name(logical_path) if logical_path else ("", "")
            elif is_s3_uri(logical_value):
                logical_path = normalize_item_path(
                    derive_logical_path(
                        logical_value,
                        root=table.root,
                        local_prefix=table.local_prefix,
                        s3_prefixes=table.s3_prefixes,
                        s3_use_bucket=table.s3_use_bucket,
                    )
                )
                folder_norm, fallback_name = (
                    _fast_path_folder_and_name(logical_path) if logical_path else ("", extract_name(source))
                )
            else:
                logical_path = normalize_item_path(logical_value)
                folder_norm, _path_name = _fast_path_folder_and_name(logical_path)
                fallback_name = extract_name(source)
        else:
            logical_path = derive_http_logical_path(source)
            folder_norm, fallback_name = _fast_path_folder_and_name(logical_path) if logical_path else ("", "")
        if not logical_path:
            continue

        explicit_name = _fast_text(name_values[idx]) if has_name_column else ""
        image_name = explicit_name or fallback_name or extract_name(logical_path) or "image"

        if logical_path in seen_paths:
            logical_path = dedupe_path(logical_path, seen_paths)
        seen_paths.add(logical_path)

        mime = normalize_image_mime(mime_values[idx], image_name) if has_mime_column else guess_image_mime(image_name)
        size = (coerce_int(size_values[idx]) or 0) if has_size_column else 0
        mtime = (coerce_timestamp(mtime_values[idx]) or 0.0) if has_mtime_column else 0.0
        try:
            width = int(width_values[idx]) if has_width_column and width_values[idx] is not None else 0
        except (TypeError, ValueError, OverflowError):
            width = 0
        try:
            height = int(height_values[idx]) if has_height_column and height_values[idx] is not None else 0
        except (TypeError, ValueError, OverflowError):
            height = 0

        if fast_item_factory is not None and lazy_metrics_provider is not None:
            item = fast_item_factory(
                logical_path,
                image_name,
                mime,
                width,
                height,
                size,
                mtime,
                source,
                source,
                idx,
                lazy_metrics_provider,
            )
        else:
            metrics = None if lazy_metrics_provider is not None else _collect_row_metrics(context, columns, idx)
            item_kwargs = {
                "path": logical_path,
                "name": image_name,
                "mime": mime,
                "width": width,
                "height": height,
                "size": size,
                "mtime": mtime,
                "url": source,
                "source": source,
                "metrics": metrics,
                "metric_labels": {},
            }
            if lazy_metrics_provider is not None:
                item_kwargs["row_idx"] = idx
                item_kwargs["metrics_provider"] = lazy_metrics_provider
            item = item_factory(**item_kwargs)

        items[logical_path] = item
        row_dimensions[idx] = (width, height)
        if needs_path_to_row:
            path_to_row[logical_path] = idx
        row_to_path[idx] = logical_path
        _folder_index(
            indexes,
            folder_norm,
            generated_at=generated_at,
            index_factory=index_factory,
        ).items.append(item)
        _record_folder_children(
            folder_norm,
            seen_folders=seen_folders,
            dir_children=dir_children,
        )

        if (width == 0 or height == 0) and not policy.skip_dimension_probe:
            remote_tasks.append((logical_path, item, source, image_name))

    remainder = row_count % progress_batch_size
    if remainder:
        progress.step(remainder)
    progress.finish()
    if "" not in indexes:
        indexes[""] = index_factory(path="/", generated_at=generated_at, items=[], dirs=[])
    for parent, children in dir_children.items():
        index = _folder_index(
            indexes,
            parent,
            generated_at=generated_at,
            index_factory=index_factory,
        )
        index.dirs = sorted(children)
    return IndexAssemblyResult(
        indexes=indexes,
        items=items,
        source_paths=source_paths,
        row_dimensions=row_dimensions,
        path_to_row=path_to_row,
        row_to_path=row_to_path,
        dimensions=dimensions,
        remote_tasks=remote_tasks,
    )


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
    if not identity.is_local or context.policy.skip_dimension_probe or local_source.resolved_path is None:
        return width, height, None

    dims = read_dimensions_fast(local_source.resolved_path)
    if dims is None:
        return width, height, None
    return dims[0], dims[1], dims


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


def _collect_row_metrics(
    context: TableIndexInput,
    columns: IndexColumns,
    idx: int,
) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for metric_key, metric_values in columns.metric_columns:
        num = coerce_float(metric_values[idx])
        if num is None:
            continue
        metrics[metric_key] = num

    if context.table.metrics_column is None:
        return metrics

    raw_metrics = columns.metrics_values[idx]
    if not isinstance(raw_metrics, dict):
        return metrics
    for raw_key, raw_value in raw_metrics.items():
        if is_internal_metric_key(raw_key):
            continue
        num = coerce_float(raw_value)
        if num is None:
            continue
        metrics[str(raw_key)] = num
    return metrics
