from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse
import urllib.request

HTTP_URL_SCHEMES = frozenset({"http", "https"})


def require_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in HTTP_URL_SCHEMES or not parsed.netloc:
        raise ValueError(f"Unsupported URL scheme for remote media request: {url!r}")
    return url


def http_request(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    method: str | None = None,
) -> urllib.request.Request:
    return urllib.request.Request(
        require_http_url(url),
        headers=dict(headers or {}),
        method=method,
    )


def open_http_url(url_or_request: str | urllib.request.Request, *args: Any, **kwargs: Any) -> Any:
    url = url_or_request.full_url if isinstance(url_or_request, urllib.request.Request) else url_or_request
    require_http_url(url)
    return urllib.request.urlopen(url_or_request, *args, **kwargs)  # nosec B310 - URL scheme is validated above.
