from __future__ import annotations

import ipaddress
import os
import socket
from typing import Callable, TypeAlias, Any
import urllib.error
import urllib.request
from urllib.parse import urlparse

from ...http_safety import http_request, open_http_url

Resolver: TypeAlias = Callable[..., list[tuple[Any, Any, Any, str, tuple[Any, ...]]]]
HEADER_FETCH_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ValueError,
    urllib.error.URLError,
)
IMAGE_PROBE_HEADERS = {
    "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.1",
    "User-Agent": "lenslet-image-probe/1.0",
}


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(newurl, code, "redirect blocked", headers, fp)


def parse_content_range(header: str) -> int | None:
    try:
        if "/" not in header:
            return None
        total = header.split("/")[-1].strip()
        if total == "*":
            return None
        return int(total)
    except ValueError:
        return None


def parse_content_length(header: str | None) -> int | None:
    if not header:
        return None
    try:
        return int(header)
    except ValueError:
        return None


def remote_url_has_public_address(url: str, *, resolver: Resolver = socket.getaddrinfo) -> bool:
    endpoint = _remote_endpoint(url)
    if endpoint is None:
        return False
    host, port = endpoint
    addresses = _resolved_addresses(host, port, resolver)
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
        req = urllib.request.Request(
            url,
            headers={
                **IMAGE_PROBE_HEADERS,
                "Range": f"bytes=0-{max_bytes - 1}",
            },
        )
        opener = urllib.request.build_opener(NoRedirectHandler)
        with opener.open(req, timeout=timeout) as response:
            data = response.read(max_bytes)
            total = _response_total_size(response.headers, parse_content_range_fn)
            return data, total
    except HEADER_FETCH_ERRORS:
        return None, None


def get_remote_header_bytes(
    url: str,
    *,
    max_bytes: int,
    parse_content_range_fn: Callable[[str], int | None] = parse_content_range,
) -> tuple[bytes | None, int | None]:
    try:
        req = http_request(
            url,
            headers={
                **IMAGE_PROBE_HEADERS,
                "Range": f"bytes=0-{max_bytes - 1}",
            },
        )
        with open_http_url(req) as response:
            data = response.read(max_bytes)
            total = _response_total_size(response.headers, parse_content_range_fn)
            return data, total
    except HEADER_FETCH_ERRORS:
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


def _response_total_size(
    headers: Any,
    parse_content_range_fn: Callable[[str], int | None],
) -> int | None:
    content_range = headers.get("Content-Range")
    if content_range:
        total = parse_content_range_fn(content_range)
        if total is not None:
            return total
    return parse_content_length(headers.get("Content-Length"))


def _remote_endpoint(url: str) -> tuple[str, int] | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.username or parsed.password:
        return None
    if parsed.port not in {None, 80, 443}:
        return None

    host = parsed.hostname
    if not host:
        return None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def _resolved_addresses(
    host: str,
    port: int,
    resolver: Resolver,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        literal_address = ipaddress.ip_address(host)
    except ValueError:
        literal_address = None
    if literal_address is not None:
        return [literal_address]

    try:
        infos = resolver(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            addresses.append(ipaddress.ip_address(str(sockaddr[0])))
        except ValueError:
            return []
    return addresses
