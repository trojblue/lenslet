from __future__ import annotations

import os
import posixpath
from collections.abc import Iterable
from dataclasses import dataclass
from os import PathLike
from urllib.parse import urlparse

from ..source.paths import extract_name, is_http_url, is_s3_uri, normalize_item_path, normalize_path


@dataclass(frozen=True)
class DatasetSourcePrefixes:
    local_prefix: str | None
    s3_prefixes: dict[str, str]
    s3_use_bucket: bool
    http_prefixes: dict[str, str]
    http_use_host: bool


def clean_dataset_sources(raw_paths: Iterable[object]) -> list[str]:
    sources: list[str] = []
    for raw in raw_paths:
        if isinstance(raw, PathLike):
            raw = os.fspath(raw)
        if not isinstance(raw, str):
            continue
        source = raw.strip()
        if source:
            sources.append(source)
    return sources


def dataset_source_prefixes(paths: list[str]) -> DatasetSourcePrefixes:
    s3_prefixes, s3_use_bucket = _compute_remote_prefixes(paths, predicate=is_s3_uri)
    http_prefixes, http_use_host = _compute_remote_prefixes(paths, predicate=is_http_url)
    return DatasetSourcePrefixes(
        local_prefix=_compute_local_prefix(paths),
        s3_prefixes=s3_prefixes,
        s3_use_bucket=s3_use_bucket,
        http_prefixes=http_prefixes,
        http_use_host=http_use_host,
    )


def dataset_relative_path(source: str, prefixes: DatasetSourcePrefixes) -> str:
    if is_s3_uri(source):
        return _s3_relative_path(source, prefixes)
    if is_http_url(source):
        return _http_relative_path(source, prefixes)
    return _local_relative_path(source, prefixes.local_prefix)


def _s3_relative_path(source: str, prefixes: DatasetSourcePrefixes) -> str:
    parsed = urlparse(source)
    bucket = parsed.netloc
    key = parsed.path.lstrip(posixpath.sep)
    trimmed = _trim_prefix(key, prefixes.s3_prefixes.get(bucket, ""))
    if prefixes.s3_use_bucket and bucket:
        return posixpath.join(bucket, trimmed) if trimmed else bucket
    return trimmed or extract_name(source)


def _http_relative_path(source: str, prefixes: DatasetSourcePrefixes) -> str:
    parsed = urlparse(source)
    host = parsed.netloc
    path = parsed.path.lstrip(posixpath.sep)
    trimmed = _trim_prefix(path, prefixes.http_prefixes.get(host, ""))
    if prefixes.http_use_host and host:
        return posixpath.join(host, trimmed) if trimmed else host
    return trimmed or extract_name(source)


def _local_relative_path(source: str, local_prefix: str | None) -> str:
    resolved = os.path.abspath(source)
    if local_prefix:
        try:
            relative = os.path.relpath(resolved, local_prefix)
        except ValueError:
            return os.path.basename(resolved)
        if not _relative_path_escapes(relative):
            return relative
    return os.path.basename(resolved)


def dataset_logical_relative_path(dataset_name: str, relative_path: str) -> str:
    return normalize_item_path(posixpath.join(dataset_name, relative_path))


def dataset_folder_norm(logical_path: str) -> str:
    return normalize_path(posixpath.dirname(logical_path))


def _relative_path_escapes(relative: str) -> bool:
    return relative == os.pardir or relative.startswith(os.pardir + os.sep)


def _common_parts(groups: list[list[str]]) -> list[str]:
    if not groups:
        return []
    common = list(groups[0])
    for parts in groups[1:]:
        limit = min(len(common), len(parts))
        idx = 0
        while idx < limit and common[idx] == parts[idx]:
            idx += 1
        common = common[:idx]
        if not common:
            break
    return common


def _compute_local_prefix(paths: list[str]) -> str | None:
    local_dirs: list[str] = []
    for source in paths:
        if is_s3_uri(source) or is_http_url(source):
            continue
        local_dirs.append(os.path.dirname(os.path.abspath(source)))
    if not local_dirs:
        return None
    try:
        return os.path.commonpath(local_dirs)
    except ValueError:
        return None


def _compute_remote_prefixes(
    paths: list[str],
    *,
    predicate,
) -> tuple[dict[str, str], bool]:
    groups_by_host: dict[str, list[list[str]]] = {}
    for source in paths:
        if not predicate(source):
            continue
        parsed = urlparse(source)
        host = parsed.netloc
        path = parsed.path.lstrip(posixpath.sep)
        if not host or not path:
            continue
        directory = posixpath.dirname(path)
        parts = [part for part in directory.split(posixpath.sep) if part and part != "."]
        groups_by_host.setdefault(host, []).append(parts)

    prefixes: dict[str, str] = {}
    for host, groups in groups_by_host.items():
        prefix_parts = _common_parts(groups)
        prefix = posixpath.join(*prefix_parts) if prefix_parts else ""
        prefixes[host] = f"{prefix}{posixpath.sep}" if prefix else ""
    return prefixes, len(prefixes) > 1


def _trim_prefix(path: str, prefix: str) -> str:
    if prefix and path.startswith(prefix):
        return path[len(prefix) :].lstrip(posixpath.sep)
    return path.lstrip(posixpath.sep)
