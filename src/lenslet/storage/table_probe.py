from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable


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


def parse_content_range(header: str) -> int | None:
    try:
        if "/" not in header:
            return None
        total = header.split("/")[-1].strip()
        if total == "*":
            return None
        return int(total)
    except Exception:
        return None


def get_remote_header_bytes(
    url: str,
    *,
    max_bytes: int,
    parse_content_range_fn: Callable[[str], int | None] = parse_content_range,
) -> tuple[bytes | None, int | None]:
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={"Range": f"bytes=0-{max_bytes - 1}"},
        )
        with urllib.request.urlopen(req) as response:
            data = response.read(max_bytes)
            total = None
            content_range = response.headers.get("Content-Range")
            if content_range:
                total = parse_content_range_fn(content_range)
            if total is None:
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        total = int(content_length)
                    except Exception:
                        total = None
            return data, total
    except Exception:
        return None, None


def get_remote_header_info(
    url: str,
    name: str,
    *,
    max_bytes: int,
    read_dimensions_from_bytes: Callable[[bytes, str | None], tuple[int, int] | None],
    get_remote_header_bytes_fn: Callable[[str, int | None], tuple[bytes | None, int | None]] | None = None,
) -> tuple[tuple[int, int] | None, int | None]:
    if get_remote_header_bytes_fn is None:
        header, total = get_remote_header_bytes(url, max_bytes=max_bytes)
    else:
        header, total = get_remote_header_bytes_fn(url, max_bytes)
    if not header:
        return None, total
    ext = os.path.splitext(name)[1].lower().lstrip(".") or None
    return read_dimensions_from_bytes(header, ext), total


def probe_remote_dimensions(storage: Any, tasks: list[tuple[str, Any, str, str]]) -> None:
    total = len(tasks)
    if total == 0:
        return

    workers = storage._effective_remote_workers(total)
    if workers <= 0:
        return

    def _work(task: tuple[str, Any, str, str]):
        logical_path, item, source_path, name = task
        url = source_path
        if storage._is_s3_uri(source_path):
            try:
                url = storage._get_presigned_url(source_path)
            except Exception:
                url = None
        if not url:
            return logical_path, item, None, None
        dims, total_size = storage._get_remote_header_info(url, name)
        return logical_path, item, dims, total_size

    done = 0
    last_print = 0.0
    progress_label = "remote headers"
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_work, task) for task in tasks]
        for future in as_completed(futures):
            logical_path, item, dims, total_size = future.result()
            if dims:
                storage._dimensions[logical_path] = dims
                item.width, item.height = dims
            if total_size:
                item.size = total_size
            row_idx = storage._path_to_row.get(logical_path)
            if row_idx is not None:
                storage._row_dimensions[row_idx] = (item.width, item.height)
            done += 1
            now = time.monotonic()
            if now - last_print > 0.1 or done == total:
                storage._progress(done, total, progress_label)
                last_print = now
