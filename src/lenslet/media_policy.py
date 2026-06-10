from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import ParseResult, urlparse


OriginalMediaPolicyMode = Literal[
    "local_streaming",
    "backend_proxy_required",
    "browser_direct_allowed",
    "browser_direct_preferred_with_proxy_fallback",
    "unsupported",
]

MediaSourceKind = Literal["local", "http", "s3", "unknown"]

ORIGINAL_MEDIA_POLICY_MODES: tuple[OriginalMediaPolicyMode, ...] = (
    "local_streaming",
    "backend_proxy_required",
    "browser_direct_allowed",
    "browser_direct_preferred_with_proxy_fallback",
    "unsupported",
)

MEDIA_SOURCE_KINDS: tuple[MediaSourceKind, ...] = ("local", "http", "s3", "unknown")


@dataclass(frozen=True, slots=True)
class OriginalMediaPolicy:
    mode: OriginalMediaPolicyMode
    source_kind: MediaSourceKind
    proxy_available: bool
    direct_allowed_reason: str | None = None
    redacted_origin: str | None = None
    warnings: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "source_kind": self.source_kind,
            "proxy_available": self.proxy_available,
            "direct_allowed_reason": self.direct_allowed_reason,
            "redacted_origin": self.redacted_origin,
            "warnings": list(self.warnings),
        }


def classify_media_source(source: str | None) -> MediaSourceKind:
    value = (source or "").strip()
    if not value:
        return "unknown"
    parsed = _safe_urlparse(value)
    if parsed is None:
        return "unknown" if _looks_like_url(value) else "local"
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return "http"
    if parsed.scheme == "s3" and parsed.netloc:
        return "s3"
    return "local"


def redacted_media_origin(source: str | None) -> str | None:
    value = (source or "").strip()
    if not value:
        return None
    parsed = _safe_urlparse(value)
    if parsed is None:
        return "[redacted source]" if _looks_like_url(value) else "[local path]"
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        host = parsed.hostname or parsed.netloc
        port = _safe_port(parsed)
        if port is not None:
            host = f"{host}:{port}"
        return f"{parsed.scheme}://{host}/[redacted]"
    if parsed.scheme == "s3" and parsed.netloc:
        return f"s3://{parsed.netloc}/[redacted]"
    return "[local path]"


def _safe_urlparse(value: str) -> ParseResult | None:
    try:
        return urlparse(value)
    except ValueError:
        return None


def _safe_port(parsed: ParseResult) -> int | None:
    try:
        return parsed.port
    except ValueError:
        return None


def _looks_like_url(value: str) -> bool:
    return "://" in value


def build_original_media_policy(
    source: str | None,
    *,
    proxy_available: bool,
    direct_browser_allowed: bool = False,
    direct_browser_preferred: bool = False,
    local_streaming_available: bool = False,
    warnings: tuple[str, ...] = (),
) -> OriginalMediaPolicy:
    source_kind = classify_media_source(source)
    if source_kind == "unknown":
        return OriginalMediaPolicy(
            mode="unsupported",
            source_kind=source_kind,
            proxy_available=False,
            direct_allowed_reason="no source",
            redacted_origin=None,
            warnings=warnings,
        )
    if source_kind == "local" and local_streaming_available:
        return OriginalMediaPolicy(
            mode="local_streaming",
            source_kind=source_kind,
            proxy_available=True,
            direct_allowed_reason="served by backend local file stream",
            redacted_origin=redacted_media_origin(source),
            warnings=warnings,
        )
    if direct_browser_allowed:
        mode: OriginalMediaPolicyMode = (
            "browser_direct_preferred_with_proxy_fallback"
            if direct_browser_preferred and proxy_available
            else "browser_direct_allowed"
        )
        return OriginalMediaPolicy(
            mode=mode,
            source_kind=source_kind,
            proxy_available=proxy_available,
            direct_allowed_reason="explicit media policy allows browser handoff",
            redacted_origin=redacted_media_origin(source),
            warnings=warnings,
        )
    if proxy_available:
        return OriginalMediaPolicy(
            mode="backend_proxy_required",
            source_kind=source_kind,
            proxy_available=True,
            direct_allowed_reason="browser direct handoff is not allowed",
            redacted_origin=redacted_media_origin(source),
            warnings=warnings,
        )
    return OriginalMediaPolicy(
        mode="unsupported",
        source_kind=source_kind,
        proxy_available=False,
        direct_allowed_reason="no safe direct or proxy path",
        redacted_origin=redacted_media_origin(source),
        warnings=warnings,
    )
