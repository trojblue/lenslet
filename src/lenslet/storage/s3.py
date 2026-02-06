"""Shared S3 helpers for storage backends."""
from __future__ import annotations

from typing import Any


S3_DEPENDENCY_ERROR = (
    "boto3 package required for S3 support. Install with: pip install lenslet[s3]"
)


def create_s3_client() -> tuple[Any | None, Any]:
    """Create an S3 client and return `(session, client)`."""
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(S3_DEPENDENCY_ERROR) from exc

    session_factory = getattr(getattr(boto3, "session", None), "Session", None)
    if callable(session_factory):
        session = session_factory()
        return session, session.client("s3")
    return None, boto3.client("s3")
