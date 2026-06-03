from __future__ import annotations

from dataclasses import dataclass, field
import socket
from threading import Lock
from typing import Any, Callable
import urllib.error
from urllib.parse import urlparse

from ...http_safety import require_http_url
from ...media_errors import RemoteMediaNotFoundError, RemoteMediaReadError
from ..s3 import S3_DEPENDENCY_ERROR, create_s3_client
from .probe import (
    get_remote_header_bytes,
    get_remote_header_info,
    get_safe_remote_header_info,
    parse_content_range,
)

# Keep these exception classes as a cheap module-scope tuple: they do not create
# boto3 sessions or network clients, and exception handlers need concrete classes.
try:
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
except ImportError:  # pragma: no cover - optional dependency
    _S3_CLIENT_EXCEPTIONS: tuple[type[BaseException], ...] = ()
else:  # pragma: no cover - exercised only when boto3/botocore is installed
    _S3_CLIENT_EXCEPTIONS = (BotoCoreError, ClientError, NoCredentialsError)

_HTTP_NOT_FOUND = 404
_HTTP_PERMISSION_CODES = frozenset({401, 403})
_HTTP_TIMEOUT_CODES = frozenset({408, 504})
_S3_NOT_FOUND_CODES = frozenset({"NoSuchKey", "NoSuchBucket", "NotFound", "404"})
_S3_PERMISSION_CODES = frozenset(
    {
        "AccessDenied",
        "Forbidden",
        "InvalidAccessKeyId",
        "SignatureDoesNotMatch",
        "Unauthorized",
    },
)
_HTTPX_MODULE: Any | None = None


def _require_httpx() -> Any:
    global _HTTPX_MODULE
    if _HTTPX_MODULE is None:
        import httpx

        _HTTPX_MODULE = httpx
    return _HTTPX_MODULE


def _exception_detail(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or type(exc).__name__


def _remote_error_code(exc: BaseException) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    error = response.get("Error")
    if not isinstance(error, dict):
        return None
    return str(error.get("Code") or "").strip() or None


def _remote_timeout_reason(exc: BaseException) -> bool:
    reason = getattr(exc, "reason", None)
    return isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(reason, (TimeoutError, socket.timeout))


@dataclass(slots=True)
class MediaReadService:
    remote_header_bytes: int
    resolve_local_source: Callable[[str], str]
    is_s3_uri: Callable[[str], bool]
    is_http_url: Callable[[str], bool]
    read_dimensions_from_bytes: Callable[[bytes, str | None], tuple[int, int] | None]
    _s3_client_lock: Lock = field(default_factory=Lock, init=False)
    _s3_session: Any | None = field(default=None, init=False)
    _s3_client: Any | None = field(default=None, init=False)
    _s3_client_creations: int = field(default=0, init=False)
    _http_client_lock: Lock = field(default_factory=Lock, init=False)
    _http_client: Any | None = field(default=None, init=False)

    @property
    def s3_client_creations(self) -> int:
        return self._s3_client_creations

    def parse_content_range(self, header: str) -> int | None:
        return parse_content_range(header)

    def get_remote_header_bytes(
        self,
        url: str,
        max_bytes: int | None = None,
    ) -> tuple[bytes | None, int | None]:
        return get_remote_header_bytes(
            url,
            max_bytes=max_bytes or self.remote_header_bytes,
            parse_content_range_fn=self.parse_content_range,
        )

    def get_remote_header_info(
        self,
        url: str,
        name: str,
    ) -> tuple[tuple[int, int] | None, int | None]:
        return get_remote_header_info(
            url,
            name,
            max_bytes=self.remote_header_bytes,
            read_dimensions_from_bytes=self.read_dimensions_from_bytes,
            get_remote_header_bytes_fn=self.get_remote_header_bytes,
        )

    def get_safe_remote_header_info(
        self,
        url: str,
        name: str,
    ) -> tuple[tuple[int, int] | None, int | None]:
        return get_safe_remote_header_info(
            url,
            name,
            max_bytes=self.remote_header_bytes,
            read_dimensions_from_bytes=self.read_dimensions_from_bytes,
        )

    def _ensure_s3_client(self):
        with self._s3_client_lock:
            if self._s3_client is not None:
                return self._s3_client
            self._s3_session, self._s3_client = create_s3_client()
            self._s3_client_creations += 1
            return self._s3_client

    def _ensure_http_client(self) -> Any:
        with self._http_client_lock:
            if self._http_client is not None:
                return self._http_client
            httpx = _require_httpx()
            self._http_client = httpx.Client(
                follow_redirects=True,
                timeout=httpx.Timeout(connect=3.0, read=30.0, write=5.0, pool=5.0),
                limits=httpx.Limits(
                    max_connections=64,
                    max_keepalive_connections=32,
                    keepalive_expiry=30.0,
                ),
                headers={
                    "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.1",
                    "User-Agent": "lenslet-image-fetch/1.0",
                },
            )
            return self._http_client

    def _http_get(self, url: str) -> Any:
        return self._ensure_http_client().get(url)

    def get_presigned_url(self, s3_uri: str, expires_in: int = 3600) -> str:
        if not _S3_CLIENT_EXCEPTIONS:
            raise ImportError(S3_DEPENDENCY_ERROR)

        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError(f"Invalid S3 URI: {s3_uri}")

        try:
            s3_client = self._ensure_s3_client()
            return s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except _S3_CLIENT_EXCEPTIONS as exc:
            raise RuntimeError(f"Failed to presign S3 URI: {exc}") from exc

    def remote_access_url(self, source: str) -> str | None:
        if self.is_s3_uri(source):
            try:
                return self.get_presigned_url(source)
            except (ImportError, RuntimeError, ValueError):
                return None
        if self.is_http_url(source):
            return source
        return None

    def remote_header_info(
        self,
        source: str,
        name: str,
    ) -> tuple[tuple[int, int] | None, int | None]:
        url = self.remote_access_url(source)
        if url is None:
            return None, None
        return self.get_remote_header_info(url, name)

    def _raise_http_read_error(
        self,
        path: str,
        source: str,
        exc: urllib.error.HTTPError,
    ) -> None:
        self._raise_http_status_read_error(path, source, exc.code, cause=exc)

    def _raise_http_status_read_error(
        self,
        path: str,
        source: str,
        status_code: int,
        *,
        cause: BaseException | None = None,
    ) -> None:
        reason = f"HTTP {status_code}"
        if status_code == _HTTP_NOT_FOUND:
            raise RemoteMediaNotFoundError(path, source, reason) from cause
        if status_code in _HTTP_PERMISSION_CODES:
            raise RemoteMediaReadError(path, source, "permission", reason) from cause
        if status_code in _HTTP_TIMEOUT_CODES:
            raise RemoteMediaReadError(path, source, "timeout", reason) from cause
        raise RemoteMediaReadError(path, source, "http", reason) from cause

    def _raise_remote_read_error(
        self,
        path: str,
        source: str,
        exc: BaseException,
        *,
        default_category: str,
    ) -> None:
        if isinstance(exc, urllib.error.HTTPError):
            self._raise_http_read_error(path, source, exc)
        detail = _exception_detail(exc)
        lower_detail = detail.lower()
        error_code = _remote_error_code(exc)
        if error_code in _S3_NOT_FOUND_CODES:
            raise RemoteMediaNotFoundError(path, source, error_code) from exc
        if error_code in _S3_PERMISSION_CODES or "credential" in lower_detail:
            raise RemoteMediaReadError(path, source, "permission", detail) from exc
        if _remote_timeout_reason(exc):
            raise RemoteMediaReadError(path, source, "timeout", detail) from exc
        raise RemoteMediaReadError(path, source, default_category, detail) from exc

    def _read_http_bytes(
        self,
        *,
        path: str,
        source: str,
        url: str,
        default_category: str,
    ) -> bytes:
        httpx = _require_httpx()
        try:
            response = self._http_get(require_http_url(url))
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as exc:
            self._raise_http_status_read_error(path, source, exc.response.status_code, cause=exc)
        except httpx.TimeoutException as exc:
            raise RemoteMediaReadError(path, source, "timeout", _exception_detail(exc)) from exc
        except (httpx.HTTPError, ValueError, OSError) as exc:
            self._raise_remote_read_error(path, source, exc, default_category=default_category)

    def read_bytes(self, path: str, source: str) -> bytes:
        if self.is_s3_uri(source):
            try:
                url = self.get_presigned_url(source)
                return self._read_http_bytes(
                    path=path,
                    source=source,
                    url=url,
                    default_category="s3",
                )
            except (ImportError, RuntimeError, ValueError, OSError, urllib.error.URLError) as exc:
                self._raise_remote_read_error(path, source, exc, default_category="s3")

        if self.is_http_url(source):
            return self._read_http_bytes(
                path=path,
                source=source,
                url=source,
                default_category="network",
            )

        try:
            resolved = self.resolve_local_source(source)
        except ValueError as exc:
            raise FileNotFoundError(path) from exc
        with open(resolved, "rb") as handle:
            return handle.read()
