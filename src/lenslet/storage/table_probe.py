from __future__ import annotations

import ipaddress
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Protocol, TypeAlias
from urllib.parse import urlparse


RemoteDimensionTask: TypeAlias = tuple[str, Any, str, str]
Resolver: TypeAlias = Callable[..., list[tuple[Any, Any, Any, str, tuple[Any, ...]]]]


class RemoteDimensionProbeHost(Protocol):
    _dimensions: dict[str, tuple[int, int]]
    _path_to_row: dict[str, int]
    _row_dimensions: list[tuple[int, int] | None]

    _effective_remote_workers: Callable[[int], int]
    _is_s3_uri: Callable[[str], bool]
    _get_presigned_url: Callable[[str], str]
    _get_remote_header_info: Callable[[str, str], tuple[tuple[int, int] | None, int | None]]
    _progress: Callable[[int, int, str], None]


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


def remote_url_has_public_address(url: str, *, resolver: Resolver = socket.getaddrinfo) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.port not in {None, 80, 443}:
        return False

    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = resolver(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return False
        addresses = []
        for info in infos:
            sockaddr = info[4]
            if not sockaddr:
                continue
            try:
                addresses.append(ipaddress.ip_address(str(sockaddr[0])))
            except ValueError:
                return False

    return bool(addresses) and all(address.is_global for address in addresses)


def get_safe_remote_header_bytes(
    url: str,
    *,
    max_bytes: int,
    timeout: float = 3.0,
    parse_content_range_fn: Callable[[str], int | None] = parse_content_range,
) -> tuple[bytes | None, int | None]:
    if not remote_url_has_public_address(url):
        return None, None

    try:
        import urllib.request

        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
                return None

        req = urllib.request.Request(
            url,
            headers={
                "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.1",
                "Range": f"bytes=0-{max_bytes - 1}",
                "User-Agent": "lenslet-image-probe/1.0",
            },
        )
        opener = urllib.request.build_opener(NoRedirectHandler)
        with opener.open(req, timeout=timeout) as response:
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


def get_safe_remote_header_info(
    url: str,
    name: str,
    *,
    max_bytes: int,
    read_dimensions_from_bytes: Callable[[bytes, str | None], tuple[int, int] | None],
) -> tuple[tuple[int, int] | None, int | None]:
    header, total = get_safe_remote_header_bytes(url, max_bytes=max_bytes)
    if not header:
        return None, total
    ext = os.path.splitext(name)[1].lower().lstrip(".") or None
    return read_dimensions_from_bytes(header, ext), total


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


def probe_remote_dimensions(
    storage: RemoteDimensionProbeHost,
    tasks: list[RemoteDimensionTask],
) -> None:
    total = len(tasks)
    if total == 0:
        return

    workers = storage._effective_remote_workers(total)
    if workers <= 0:
        return

    def _work(task: RemoteDimensionTask):
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
