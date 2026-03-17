"""Shared request-level permission helpers for Lenslet routes."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from .auth import get_mutation_policy, request_can_mutate

READ_ONLY_WORKSPACE_ERROR = "read_only_workspace"
READ_ONLY_WORKSPACE_MESSAGE = "workspace is read-only"


def deny_if_mutation_forbidden(request: Request, *, writes_enabled: bool) -> JSONResponse | None:
    if request_can_mutate(request, writes_enabled=writes_enabled):
        return None
    if not writes_enabled:
        return JSONResponse(
            status_code=403,
            content={
                "error": READ_ONLY_WORKSPACE_ERROR,
                "message": READ_ONLY_WORKSPACE_MESSAGE,
            },
        )
    policy = get_mutation_policy(request.app)
    return JSONResponse(
        status_code=403,
        content={
            "error": policy.denial_error,
            "message": policy.denial_message,
        },
    )
