"""Request identity and mutation policy helpers."""

from __future__ import annotations

import ipaddress
import secrets
from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI, Request
from starlette.responses import Response

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
class MutationPolicy:
    mode: Literal["read_only", "trusted_local"]
    denial_error: str
    denial_message: str


READ_ONLY_MUTATION_POLICY = MutationPolicy(
    mode="read_only",
    denial_error="read_only_workspace",
    denial_message="workspace is read-only",
)

TRUSTED_LOCAL_MUTATION_POLICY = MutationPolicy(
    mode="trusted_local",
    denial_error="local_origin_required",
    denial_message="mutations require a local Lenslet origin",
)


def install_request_identity_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def attach_request_identity(request: Request, call_next):
        bind_request_identity(request)
        response = await call_next(request)
        persist_request_identity(request, response)
        return response


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


def get_request_identity(request: Request) -> RequestIdentity:
    existing = getattr(request.state, REQUEST_IDENTITY_ATTR, None)
    if isinstance(existing, RequestIdentity):
        return existing
    return bind_request_identity(request)


def persist_request_identity(request: Request, response: Response) -> None:
    identity = get_request_identity(request)
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


def request_actor_id(request: Request | None) -> str:
    if request is None:
        return "server"
    return get_request_identity(request).actor_id


def request_client_id(request: Request | None) -> str | None:
    if request is None:
        return None
    return get_request_identity(request).session_id


def request_can_mutate(request: Request, *, writes_enabled: bool) -> bool:
    if not writes_enabled:
        return False
    policy = get_mutation_policy(request.app)
    if policy.mode == "read_only":
        return False
    if policy.mode == "trusted_local":
        return request_is_local_origin(request)
    return False


def request_is_local_origin(request: Request) -> bool:
    host = request.url.hostname or _host_from_header(request.headers.get("host"))
    if not host:
        return False
    lowered = host.lower()
    if lowered in _LOCAL_HOST_ALIASES:
        return True
    try:
        return ipaddress.ip_address(lowered).is_loopback
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


def _host_from_header(raw: str | None) -> str | None:
    if not raw:
        return None
    host = raw.rsplit("@", 1)[-1]
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.split(":", 1)[0]
