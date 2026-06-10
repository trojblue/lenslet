from __future__ import annotations

from lenslet.media_policy import (
    MEDIA_SOURCE_KINDS,
    ORIGINAL_MEDIA_POLICY_MODES,
    build_original_media_policy,
    classify_media_source,
    redacted_media_origin,
)


def test_original_media_policy_modes_are_locked() -> None:
    assert ORIGINAL_MEDIA_POLICY_MODES == (
        "local_streaming",
        "backend_proxy_required",
        "browser_direct_allowed",
        "browser_direct_preferred_with_proxy_fallback",
        "unsupported",
    )
    assert MEDIA_SOURCE_KINDS == ("local", "http", "s3", "unknown")


def test_media_source_classification_is_source_string_only() -> None:
    assert classify_media_source("/data/private/cat.jpg") == "local"
    assert classify_media_source("https://cdn.example.test/a.jpg?sig=secret") == "http"
    assert classify_media_source("s3://bucket/private/a.jpg") == "s3"
    assert classify_media_source(None) == "unknown"


def test_media_origin_redaction_removes_sensitive_details() -> None:
    assert redacted_media_origin("/data/private/cat.jpg") == "[local path]"
    assert redacted_media_origin("s3://bucket/private/a.jpg") == "s3://bucket/[redacted]"
    assert (
        redacted_media_origin("https://cdn.example.test/private/a.jpg?X-Amz-Signature=secret")
        == "https://cdn.example.test/[redacted]"
    )


def test_malformed_remote_origin_redaction_fails_closed() -> None:
    assert classify_media_source("http://[::1/private.jpg") == "unknown"
    assert redacted_media_origin("http://[::1/private.jpg") == "[redacted source]"
    assert redacted_media_origin("https://cdn.example.test:bad/private.jpg") == (
        "https://cdn.example.test/[redacted]"
    )


def test_backend_proxy_policy_payload_is_explicit_and_redacted() -> None:
    policy = build_original_media_policy(
        "https://cdn.example.test/private/a.jpg?token=secret",
        proxy_available=True,
    )

    assert policy.to_payload() == {
        "mode": "backend_proxy_required",
        "source_kind": "http",
        "proxy_available": True,
        "direct_allowed_reason": "browser direct handoff is not allowed",
        "redacted_origin": "https://cdn.example.test/[redacted]",
        "warnings": [],
    }


def test_direct_preferred_policy_requires_proxy_for_fallback_mode() -> None:
    with_fallback = build_original_media_policy(
        "https://cdn.example.test/a.jpg",
        proxy_available=True,
        direct_browser_allowed=True,
        direct_browser_preferred=True,
    )
    without_fallback = build_original_media_policy(
        "https://cdn.example.test/a.jpg",
        proxy_available=False,
        direct_browser_allowed=True,
        direct_browser_preferred=True,
    )

    assert with_fallback.mode == "browser_direct_preferred_with_proxy_fallback"
    assert without_fallback.mode == "browser_direct_allowed"
