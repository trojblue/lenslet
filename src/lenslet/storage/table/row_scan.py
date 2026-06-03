from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeAlias

from ..progress import ProgressTicker
from .display import is_internal_metric_key
from ..index_assembly import ScannedRow
from ..image_media import ImageMime, normalize_image_mime, read_dimensions_fast
from .index_types import TableIndexData, TableIndexInput
from ..source.paths import (
    LocalSourcePathError,
    dedupe_path,
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


@dataclass(frozen=True)
class CategoricalMetricColumn:
    key: str
    values: list[Any]
    code_by_label: dict[str, float]


@dataclass(frozen=True)
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
    categorical_metric_columns: tuple[CategoricalMetricColumn, ...]


@dataclass
class ScanResult:
    rows: list[ScannedRow]
    remote_tasks: list[RemoteDimensionTask]
    skipped_local_disabled: int
    skipped_local_outside_root: int
    skipped_local_resolved_outside_root: int
    skipped_local_missing: int


@dataclass
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


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class LocalSourceResolution:
    resolved_path: str | None
    skip_reason: str | None = None


def scan_rows(
    context: TableIndexInput,
    columns: IndexColumns,
    *,
    item_factory: Callable[..., Any],
) -> ScanResult:
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
        metrics = _collect_row_metrics(context, columns, idx)
        metric_labels = _collect_row_metric_labels(columns, idx)

        item = item_factory(
            path=identity.logical_path,
            name=identity.name,
            mime=identity.mime,
            width=width,
            height=height,
            size=size,
            mtime=mtime or 0.0,
            url=identity.source if identity.is_http else None,
            source=identity.source,
            metrics=metrics,
            metric_labels=metric_labels,
        )

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
    supported_name = _supported_image_name(
        context,
        explicit_name=explicit_name,
        fallback_name=fallback_name,
        logical_path=logical_path,
    )
    if supported_name is not None:
        return supported_name
    if not context.source_resolver.allows_extensionless_source_image(source):
        return None
    return explicit_name or fallback_name or extract_name(logical_path) or "image"


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


def _resolved_file_mtime(value: object, local_source: LocalSourceResolution) -> float:
    mtime = coerce_timestamp(value)
    if mtime is not None:
        return mtime
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
    mtime = _resolved_file_mtime(columns.mtime_values[idx], local_source)
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
    for column in columns.categorical_metric_columns:
        label = _categorical_label_for_row(column, idx)
        if label is None:
            continue
        metrics[column.key] = column.code_by_label[label]

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


def _collect_row_metric_labels(
    columns: IndexColumns,
    idx: int,
) -> dict[str, str]:
    labels: dict[str, str] = {}
    for column in columns.categorical_metric_columns:
        label = _categorical_label_for_row(column, idx)
        if label is None:
            continue
        labels[column.key] = label
    return labels


def _categorical_label_for_row(column: CategoricalMetricColumn, idx: int) -> str | None:
    raw = column.values[idx]
    if raw is None:
        return None
    label = str(raw).strip()
    if not label:
        return None
    return label if label in column.code_by_label else None
