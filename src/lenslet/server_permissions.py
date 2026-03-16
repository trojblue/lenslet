"""Shared request-level permission helpers for Lenslet routes."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from .server_context import get_request_context

READ_ONLY_WORKSPACE_ERROR = "read_only_workspace"
READ_ONLY_WORKSPACE_MESSAGE = "workspace is read-only"


def deny_if_workspace_read_only(request: Request) -> JSONResponse | None:
    workspace = get_request_context(request).workspace
    if workspace.can_write:
        return None
    return JSONResponse(
        status_code=403,
        content={
            "error": READ_ONLY_WORKSPACE_ERROR,
            "message": READ_ONLY_WORKSPACE_MESSAGE,
        },
    )
