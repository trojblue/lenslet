"""Request identity and mutation policy helpers."""

from __future__ import annotations

import ipaddress
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SESSION_COOKIE_NAME = "lenslet_session"
SESSION_COOKIE_PATH = "/"
REQUEST_IDENTITY_ATTR = "lenslet_request_identity"
MUTATION_POLICY_ATTR = "lenslet_mutation_policy"
_LOCAL_HOST_ALIASES = frozenset({"localhost", "test", "testserver"})


@dataclass(frozen=True, slots=True)
class RequestIdentity:
    session_id: str
    actor_id: str


@dataclass(frozen=True, slots=True)
class RequestOrigin:
    scheme: str
    host: str
    port: int


@dataclass(frozen=True, slots=True)
class MutationPolicy:
    mode: Literal["read_only", "trusted_local", "public_write"]
    denial_error: str
    denial_message: str
    trusted_origins: frozenset[RequestOrigin] = frozenset()


READ_ONLY_MUTATION_POLICY = MutationPolicy(
    mode="read_only",
    denial_error="read_only_workspace",
    denial_message="workspace is read-only",
)

PUBLIC_WRITE_MUTATION_POLICY = MutationPolicy(
    mode="public_write",
    denial_error="write_forbidden",
    denial_message="workspace writes are forbidden",
)

TRUSTED_LOCAL_MUTATION_DENIAL_ERROR = "local_origin_required"
TRUSTED_LOCAL_MUTATION_DENIAL_MESSAGE = "mutations require a local Lenslet origin"


def mutation_denial_payload(policy: MutationPolicy) -> dict[str, str]:
    return {
        "error": policy.denial_error,
        "message": policy.denial_message,
    }


def trusted_local_mutation_policy(
    trusted_origins: Iterable[str | RequestOrigin],
) -> MutationPolicy:
    return MutationPolicy(
        mode="trusted_local",
        denial_error=TRUSTED_LOCAL_MUTATION_DENIAL_ERROR,
        denial_message=TRUSTED_LOCAL_MUTATION_DENIAL_MESSAGE,
        trusted_origins=frozenset(_coerce_trusted_origin(origin) for origin in trusted_origins),
    )


def trusted_write_origins_for_host(host: str, port: int, *, scheme: str = "http") -> tuple[str, ...]:
    if port <= 0:
        raise ValueError("trusted write origin port must be positive")
    origin_hosts = _origin_hosts_for_bind_host(host)
    return tuple(_origin_url(scheme=scheme, host=origin_host, port=port) for origin_host in origin_hosts)


class RequestIdentityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        bind_request_identity(request)

        async def send_with_identity(message: Message) -> None:
            if message["type"] == "http.response.start":
                cookie_headers = _session_cookie_headers(request)
                if cookie_headers:
                    message = dict(message)
                    message["headers"] = list(message.get("headers", [])) + cookie_headers
            await send(message)

        await self.app(scope, receive, send_with_identity)


def install_request_identity_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestIdentityMiddleware)


def set_mutation_policy(app: FastAPI, policy: MutationPolicy) -> MutationPolicy:
    setattr(app.state, MUTATION_POLICY_ATTR, policy)
    return policy


def get_mutation_policy(app: FastAPI) -> MutationPolicy:
    policy = getattr(app.state, MUTATION_POLICY_ATTR, None)
    if isinstance(policy, MutationPolicy):
        return policy
    return READ_ONLY_MUTATION_POLICY


def bind_request_identity(request: Request) -> RequestIdentity:
    existing = getattr(request.state, REQUEST_IDENTITY_ATTR, None)
    if isinstance(existing, RequestIdentity):
        return existing
    session_id = _normalize_session_id(request.cookies.get(SESSION_COOKIE_NAME))
    if session_id is None:
        session_id = secrets.token_hex(16)
    identity = RequestIdentity(session_id=session_id, actor_id=f"session:{session_id[:8]}")
    setattr(request.state, REQUEST_IDENTITY_ATTR, identity)
    return identity


def ensure_request_identity(request: Request) -> RequestIdentity:
    existing = getattr(request.state, REQUEST_IDENTITY_ATTR, None)
    if isinstance(existing, RequestIdentity):
        return existing
    return bind_request_identity(request)


def persist_request_identity(request: Request, response: Response) -> None:
    identity = ensure_request_identity(request)
    current = _normalize_session_id(request.cookies.get(SESSION_COOKIE_NAME))
    if current == identity.session_id:
        return
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=identity.session_id,
        httponly=True,
        samesite="lax",
        path=SESSION_COOKIE_PATH,
    )


def _session_cookie_headers(request: Request) -> list[tuple[bytes, bytes]]:
    response = Response()
    persist_request_identity(request, response)
    return [header for header in response.raw_headers if header[0].lower() == b"set-cookie"]


def request_actor_id(request: Request | None) -> str:
    if request is None:
        return "server"
    return ensure_request_identity(request).actor_id


def request_client_id(request: Request | None) -> str | None:
    if request is None:
        return None
    return ensure_request_identity(request).session_id


def request_can_mutate(request: Request, *, writes_enabled: bool) -> bool:
    if not writes_enabled:
        return False
    policy = get_mutation_policy(request.app)
    if policy.mode == "read_only":
        return False
    if policy.mode == "public_write":
        return True
    if policy.mode == "trusted_local":
        return request_has_trusted_write_origin(request, policy)
    return False


def request_has_trusted_write_origin(request: Request, policy: MutationPolicy | None = None) -> bool:
    policy = policy or get_mutation_policy(request.app)
    browser_origin, has_browser_origin = _browser_origin_from_headers(request)
    if not has_browser_origin or browser_origin is None:
        return False
    return browser_origin in policy.trusted_origins


def request_is_local_origin(request: Request) -> bool:
    return request_has_trusted_write_origin(request)


def _browser_origin_from_headers(request: Request) -> tuple[RequestOrigin | None, bool]:
    origin = request.headers.get("origin")
    if origin is not None:
        return _origin_from_url(origin), True
    referer = request.headers.get("referer")
    if referer is not None:
        return _origin_from_url(referer), True
    return None, False


def _origin_from_url(raw: str | None) -> RequestOrigin | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or parsed.username or parsed.password or not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = _default_port_for_scheme(scheme)
    if port is None:
        return None
    return RequestOrigin(scheme=scheme, host=parsed.hostname.lower(), port=port)


def _coerce_trusted_origin(origin: str | RequestOrigin) -> RequestOrigin:
    if isinstance(origin, RequestOrigin):
        return origin
    parsed = _origin_from_url(origin)
    if parsed is None:
        raise ValueError(f"invalid trusted write origin: {origin!r}")
    return parsed


def _origin_hosts_for_bind_host(host: str) -> tuple[str, ...]:
    normalized = _normalize_host_literal(host)
    if not normalized or _is_unspecified_host(normalized) or _is_local_host(normalized):
        return ("127.0.0.1", "localhost", "::1")
    return (normalized,)


def _normalize_host_literal(host: str) -> str:
    value = host.strip().lower()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return value


def _origin_url(*, scheme: str, host: str, port: int) -> str:
    normalized_scheme = scheme.lower()
    normalized_host = _normalize_host_literal(host)
    rendered_host = f"[{normalized_host}]" if ":" in normalized_host else normalized_host
    return f"{normalized_scheme}://{rendered_host}:{port}"


def _is_local_host(host: str) -> bool:
    lowered = _normalize_host_literal(host)
    if lowered in _LOCAL_HOST_ALIASES:
        return True
    try:
        return ipaddress.ip_address(lowered).is_loopback
    except ValueError:
        return False


def _is_unspecified_host(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_unspecified
    except ValueError:
        return False


def _normalize_session_id(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()
    if not (16 <= len(value) <= 64):
        return None
    if not all(ch.isalnum() for ch in value):
        return None
    return value


def _default_port_for_scheme(scheme: str) -> int | None:
    if scheme == "http":
        return 80
    if scheme == "https":
        return 443
    return None
