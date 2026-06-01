from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, TypeAlias

from .state import SourceBackedIndexState, SourceRowIndexState
from .probe_headers import (
    get_remote_header_bytes,
    get_remote_header_info,
    get_safe_remote_header_info,
    parse_content_range,
)


RemoteDimensionTask: TypeAlias = tuple[str, Any, str, str]
PRESIGN_ERRORS: tuple[type[BaseException], ...] = (ImportError, RuntimeError, ValueError)

__all__ = [
    "RemoteDimensionProbeContext",
    "RemoteDimensionTask",
    "effective_remote_workers",
    "get_remote_header_bytes",
    "get_remote_header_info",
    "get_safe_remote_header_info",
    "parse_content_range",
    "probe_remote_dimensions",
]

@dataclass(frozen=True)
class RemoteDimensionProbeContext:
    effective_remote_workers: Callable[[int], int]
    is_s3_uri: Callable[[str], bool]
    get_presigned_url: Callable[[str], str]
    get_remote_header_info: Callable[[str, str], tuple[tuple[int, int] | None, int | None]]
    progress: Callable[[int, int, str], None]


@dataclass(frozen=True)
class RemoteProbeResult:
    logical_path: str
    item: Any
    dims: tuple[int, int] | None
    total_size: int | None


def effective_remote_workers(
    total: int,
    *,
    baseline_workers: int,
    max_workers: int,
    cpu_count: Callable[[], int | None] = os.cpu_count,
) -> int:
    if total <= 0:
        return 0
    cpu = cpu_count() or 1
    cap = max(baseline_workers, cpu)
    cap = min(cap, max_workers)
    return max(1, min(cap, total))


def probe_remote_dimensions(
    context: RemoteDimensionProbeContext,
    index_state: SourceBackedIndexState[Any],
    row_index_state: SourceRowIndexState | None,
    tasks: list[RemoteDimensionTask],
) -> None:
    total = len(tasks)
    if total == 0:
        return

    workers = context.effective_remote_workers(total)
    if workers <= 0:
        return

    done = 0
    last_print = 0.0
    progress_label = "remote headers"
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_probe_remote_task, context, task) for task in tasks]
        for future in as_completed(futures):
            _apply_remote_probe_result(index_state, row_index_state, future.result())
            done += 1
            last_print = _maybe_emit_probe_progress(context, done, total, progress_label, last_print)


def _probe_remote_task(
    context: RemoteDimensionProbeContext,
    task: RemoteDimensionTask,
) -> RemoteProbeResult:
    logical_path, item, source_path, name = task
    url = _remote_probe_url(context, source_path)
    if not url:
        return RemoteProbeResult(logical_path, item, None, None)
    dims, total_size = context.get_remote_header_info(url, name)
    return RemoteProbeResult(logical_path, item, dims, total_size)


def _remote_probe_url(context: RemoteDimensionProbeContext, source_path: str) -> str | None:
    if not context.is_s3_uri(source_path):
        return source_path
    try:
        return context.get_presigned_url(source_path)
    except PRESIGN_ERRORS:
        return None


def _apply_remote_probe_result(
    index_state: SourceBackedIndexState[Any],
    row_index_state: SourceRowIndexState | None,
    result: RemoteProbeResult,
) -> None:
    if result.dims:
        index_state.dimensions[result.logical_path] = result.dims
        result.item.width, result.item.height = result.dims
    if result.total_size:
        result.item.size = result.total_size
    if row_index_state is None:
        return
    row_idx = row_index_state.path_to_row.get(result.logical_path)
    if row_idx is not None:
        row_index_state.row_dimensions[row_idx] = (result.item.width, result.item.height)


def _maybe_emit_probe_progress(
    context: RemoteDimensionProbeContext,
    done: int,
    total: int,
    label: str,
    last_print: float,
) -> float:
    now = time.monotonic()
    if now - last_print > 0.1 or done == total:
        context.progress(done, total, label)
        return now
    return last_print
