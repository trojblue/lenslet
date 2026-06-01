"""Shared request-level permission helpers for Lenslet routes."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from .auth import READ_ONLY_MUTATION_POLICY, get_mutation_policy, mutation_denial_payload, request_can_mutate


def deny_if_mutation_forbidden(request: Request, *, writes_enabled: bool) -> JSONResponse | None:
    if request_can_mutate(request, writes_enabled=writes_enabled):
        return None
    if not writes_enabled:
        return JSONResponse(
            status_code=403,
            content=mutation_denial_payload(READ_ONLY_MUTATION_POLICY),
        )
    policy = get_mutation_policy(request.app)
    return JSONResponse(
        status_code=403,
        content=mutation_denial_payload(policy),
    )
