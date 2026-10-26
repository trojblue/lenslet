from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
import ssl
from typing import Any
from urllib.parse import urlparse
import urllib.request

import certifi

HTTP_URL_SCHEMES = frozenset({"http", "https"})


@lru_cache(maxsize=1)
def _http_ssl_context() -> ssl.SSLContext:
    # Use the maintained application trust store, not a possibly stale OS bundle.
    return ssl.create_default_context(cafile=certifi.where())


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
    if kwargs.get("context") is None:
        kwargs["context"] = _http_ssl_context()
    return urllib.request.urlopen(url_or_request, *args, **kwargs)  # nosec B310 - URL scheme is validated above.
