from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lenslet.web.auth import (
    MutationPolicy,
    PUBLIC_WRITE_MUTATION_POLICY,
    READ_ONLY_MUTATION_POLICY,
    mutation_denial_payload,
    set_mutation_policy,
    trusted_local_mutation_policy,
    trusted_write_origins_for_host,
)
from lenslet.web.app.shared import mutation_policy_for_workspace
from lenslet.web.permissions import deny_if_mutation_forbidden
from lenslet.workspace import Workspace

LOCAL_ORIGIN = "http://localhost:7070"


def _trusted_policy(port: int = 7070) -> MutationPolicy:
    return trusted_local_mutation_policy(trusted_write_origins_for_host("127.0.0.1", port))


def _build_permission_app(*, writes_enabled: bool) -> FastAPI:
    app = FastAPI()
    set_mutation_policy(app, _trusted_policy())

    @app.post("/mutate")
    def mutate(request: Request):
        if denied := deny_if_mutation_forbidden(request, writes_enabled=writes_enabled):
            return denied
        return {"ok": True}

    return app


def test_deny_if_mutation_forbidden_allows_local_mutations_when_writes_enabled() -> None:
    app = _build_permission_app(writes_enabled=True)

    with TestClient(app, base_url=LOCAL_ORIGIN) as client:
        response = client.post("/mutate", headers={"Origin": LOCAL_ORIGIN})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_public_write_policy_allows_mutation_from_any_origin() -> None:
    app = FastAPI()
    set_mutation_policy(app, PUBLIC_WRITE_MUTATION_POLICY)

    @app.post("/mutate")
    def mutate(request: Request):
        if denied := deny_if_mutation_forbidden(request, writes_enabled=True):
            return denied
        return {"ok": True}

    with TestClient(app, base_url="https://public.trycloudflare.com") as client:
        response = client.post("/mutate")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_public_write_policy_does_not_override_read_only_workspace() -> None:
    app = FastAPI()
    set_mutation_policy(app, PUBLIC_WRITE_MUTATION_POLICY)

    @app.post("/mutate")
    def mutate(request: Request):
        if denied := deny_if_mutation_forbidden(request, writes_enabled=False):
            return denied
        return {"ok": True}

    with TestClient(app, base_url="https://public.trycloudflare.com") as client:
        response = client.post("/mutate")

    assert response.status_code == 403
    assert response.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)


def test_workspace_policy_selects_public_writes_only_for_writable_workspace(tmp_path) -> None:
    writable = Workspace.for_dataset(tmp_path, can_write=True)
    read_only = Workspace.for_dataset(tmp_path, can_write=False)

    assert mutation_policy_for_workspace(
        writable,
        allow_remote_writes=True,
    ) == PUBLIC_WRITE_MUTATION_POLICY
    assert mutation_policy_for_workspace(
        read_only,
        allow_remote_writes=True,
    ) == READ_ONLY_MUTATION_POLICY


def test_deny_if_mutation_forbidden_rejects_missing_browser_origin() -> None:
    app = _build_permission_app(writes_enabled=True)

    with TestClient(app, base_url=LOCAL_ORIGIN) as client:
        response = client.post("/mutate")

    assert response.status_code == 403
    assert response.json() == mutation_denial_payload(_trusted_policy())


def test_deny_if_mutation_forbidden_rejects_spoofed_host_without_origin() -> None:
    app = _build_permission_app(writes_enabled=True)

    with TestClient(app, base_url="https://public.trycloudflare.com") as client:
        response = client.post("/mutate", headers={"Host": "localhost:7070"})

    assert response.status_code == 403
    assert response.json() == mutation_denial_payload(_trusted_policy())


def test_deny_if_mutation_forbidden_returns_read_only_workspace_payload() -> None:
    app = _build_permission_app(writes_enabled=False)

    with TestClient(app) as client:
        response = client.post("/mutate")

    assert response.status_code == 403
    assert response.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)


def test_deny_if_mutation_forbidden_returns_policy_payload_for_non_local_origin() -> None:
    app = _build_permission_app(writes_enabled=True)

    with TestClient(app, base_url="http://example.com") as client:
        response = client.post("/mutate")

    assert response.status_code == 403
    assert response.json() == mutation_denial_payload(_trusted_policy())


def test_deny_if_mutation_forbidden_allows_matching_local_browser_origin() -> None:
    app = _build_permission_app(writes_enabled=True)

    with TestClient(app, base_url="http://localhost:7070") as client:
        response = client.post("/mutate", headers={"Origin": "http://localhost:7070"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_deny_if_mutation_forbidden_rejects_cross_site_origin_to_local_server() -> None:
    app = _build_permission_app(writes_enabled=True)

    with TestClient(app, base_url="http://localhost:7070") as client:
        response = client.post("/mutate", headers={"Origin": "https://example.com"})

    assert response.status_code == 403
    assert response.json() == mutation_denial_payload(_trusted_policy())


def test_deny_if_mutation_forbidden_uses_referer_when_origin_absent() -> None:
    app = _build_permission_app(writes_enabled=True)

    with TestClient(app, base_url="http://127.0.0.1:7070") as client:
        response = client.post(
            "/mutate",
            headers={"Referer": "http://127.0.0.1:7070/index.html"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_trusted_local_mutation_policy_uses_runtime_port() -> None:
    app = FastAPI()
    set_mutation_policy(app, _trusted_policy(port=9090))

    @app.post("/mutate")
    def mutate(request: Request):
        if denied := deny_if_mutation_forbidden(request, writes_enabled=True):
            return denied
        return {"ok": True}

    with TestClient(app, base_url="http://localhost:9090") as client:
        allowed = client.post("/mutate", headers={"Origin": "http://localhost:9090"})
        denied = client.post("/mutate", headers={"Origin": LOCAL_ORIGIN})

    assert allowed.status_code == 200
    assert allowed.json() == {"ok": True}
    assert denied.status_code == 403
    assert denied.json() == mutation_denial_payload(_trusted_policy(port=9090))


def test_trusted_write_origins_for_wildcard_bind_hosts_stay_loopback_only() -> None:
    expected = (
        "http://127.0.0.1:7070",
        "http://localhost:7070",
        "http://[::1]:7070",
    )

    assert trusted_write_origins_for_host("0.0.0.0", 7070) == expected
    assert trusted_write_origins_for_host("::", 7070) == expected
