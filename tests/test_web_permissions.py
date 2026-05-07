from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lenslet.web.auth import TRUSTED_LOCAL_MUTATION_POLICY, set_mutation_policy
from lenslet.web.permissions import (
    READ_ONLY_WORKSPACE_ERROR,
    READ_ONLY_WORKSPACE_MESSAGE,
    deny_if_mutation_forbidden,
)


def _build_permission_app(*, writes_enabled: bool) -> FastAPI:
    app = FastAPI()
    set_mutation_policy(app, TRUSTED_LOCAL_MUTATION_POLICY)

    @app.post("/mutate")
    def mutate(request: Request):
        if denied := deny_if_mutation_forbidden(request, writes_enabled=writes_enabled):
            return denied
        return {"ok": True}

    return app


def test_deny_if_mutation_forbidden_allows_local_mutations_when_writes_enabled() -> None:
    app = _build_permission_app(writes_enabled=True)

    with TestClient(app) as client:
        response = client.post("/mutate")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_deny_if_mutation_forbidden_returns_read_only_workspace_payload() -> None:
    app = _build_permission_app(writes_enabled=False)

    with TestClient(app) as client:
        response = client.post("/mutate")

    assert response.status_code == 403
    assert response.json() == {
        "error": READ_ONLY_WORKSPACE_ERROR,
        "message": READ_ONLY_WORKSPACE_MESSAGE,
    }


def test_deny_if_mutation_forbidden_returns_policy_payload_for_non_local_origin() -> None:
    app = _build_permission_app(writes_enabled=True)

    with TestClient(app, base_url="http://example.com") as client:
        response = client.post("/mutate")

    assert response.status_code == 403
    assert response.json() == {
        "error": "local_origin_required",
        "message": "mutations require a local Lenslet origin",
    }
