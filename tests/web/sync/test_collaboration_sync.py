import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from PIL import Image

from lenslet.server import LocalAppOptions, create_app, create_app_from_datasets, create_app_from_table
from lenslet.web.auth import (
    MutationPolicy,
    READ_ONLY_MUTATION_POLICY,
    mutation_denial_payload,
    trusted_local_mutation_policy,
    trusted_write_origins_for_host,
)
from lenslet.web.context import get_app_context, get_app_runtime

LOCAL_ORIGIN = "http://localhost:7070"


def _trusted_policy() -> MutationPolicy:
    return trusted_local_mutation_policy(trusted_write_origins_for_host("127.0.0.1", 7070))


def _origin_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Origin": LOCAL_ORIGIN}
    if extra:
        headers.update(extra)
    return headers


def _trusted_app(root: Path):
    return create_app(str(root), options=LocalAppOptions(trusted_write_origins=(LOCAL_ORIGIN,)))


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="JPEG")


def test_patch_requires_idempotency_and_base_version(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)

    app = _trusted_app(tmp_path)

    async def _run(path: str) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url=LOCAL_ORIGIN) as client:
            resp = await client.patch(
                "/item",
                params={"path": path},
                headers=_origin_headers(),
                json={"base_version": 1},
            )
            assert resp.status_code == 400

            resp = await client.patch(
                "/item",
                params={"path": path},
                headers=_origin_headers({"Idempotency-Key": "idem-test"}),
                json={},
            )
            assert resp.status_code == 400
            body = resp.json()
            assert body.get("error") == "missing_base_version"

    asyncio.run(_run("/sample.jpg"))


def test_item_mutations_publish_modeled_openapi_contracts(tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")
    schema = _trusted_app(tmp_path).openapi()

    put_responses = schema["paths"]["/item"]["put"]["responses"]
    patch_responses = schema["paths"]["/item"]["patch"]["responses"]

    assert put_responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/Sidecar")
    assert patch_responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/SidecarMutationResponse",
    )
    assert patch_responses["409"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/SidecarConflictResponse",
    )
    assert put_responses["403"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    assert patch_responses["500"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")


def test_read_only_workspace_rejects_item_mutations(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)

    for app, path in (
        (create_app_from_datasets({"demo": [str(image_path)]}), "/demo/sample.jpg"),
        (
            create_app_from_table(
                [{"path": "/gallery/sample.jpg", "source": str(image_path)}],
            ),
            "/gallery/sample.jpg",
        ),
    ):
        client = TestClient(app)
        put_response = client.put(
            "/item",
            params={"path": path},
            json={"tags": [], "notes": "blocked", "star": 1},
        )
        assert put_response.status_code == 403
        assert put_response.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)

        patch_response = client.patch(
            "/item",
            params={"path": path},
            headers={"Idempotency-Key": "readonly"},
            json={"base_version": 1, "set_notes": "blocked"},
        )
        assert patch_response.status_code == 403
        assert patch_response.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)


def test_read_only_workspace_rejects_view_mutations(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)

    payload = {
        "version": 1,
        "views": [
            {
                "id": "demo",
                "name": "Demo",
                "pool": {"kind": "folder", "path": "/"},
                "view": {"filters": {"and": []}, "sort": {"kind": "builtin", "key": "added", "dir": "desc"}},
            }
        ],
    }

    for app in (
        create_app_from_datasets({"demo": [str(image_path)]}),
        create_app_from_table([{"path": "/gallery/sample.jpg", "source": str(image_path)}]),
    ):
        client = TestClient(app)
        response = client.put("/views", json=payload)
        assert response.status_code == 403
        assert response.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)


def test_patch_idempotency_and_conflict(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url=LOCAL_ORIGIN) as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            assert base.status_code == 200
            base_version = base.json().get("version", 1)

            headers = _origin_headers({"Idempotency-Key": "idem-1", "If-Match": str(base_version)})
            body = {"base_version": base_version, "set_notes": "hello"}
            first = await client.patch("/item", params={"path": "/sample.jpg"}, headers=headers, json=body)
            assert first.status_code == 200
            first_payload = first.json()
            assert first_payload["mutation_id"] == "idem-1"
            assert first_payload["sidecar"]["notes"] == "hello"

            second = await client.patch("/item", params={"path": "/sample.jpg"}, headers=headers, json=body)
            assert second.status_code == 200
            assert second.json() == first_payload

            latest = await client.get("/item", params={"path": "/sample.jpg"})
            assert latest.status_code == 200
            assert latest.json()["version"] == base_version + 1

            conflict_headers = _origin_headers({"Idempotency-Key": "idem-2", "If-Match": str(base_version)})
            conflict_body = {"base_version": base_version, "set_star": 3}
            conflict = await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers=conflict_headers,
                json=conflict_body,
            )
            assert conflict.status_code == 409
            payload = conflict.json()
            assert payload.get("error") == "version_conflict"
            assert payload["current"]["version"] == base_version + 1

    asyncio.run(_run())


def test_sse_replay_last_event_id(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url=LOCAL_ORIGIN) as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            base_version = base.json().get("version", 1)

            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers=_origin_headers({"Idempotency-Key": "idem-a", "If-Match": str(base_version)}),
                json={"base_version": base_version, "set_notes": "first"},
            )

            broker = get_app_runtime(app).broker
            replay = broker.replay(0)
            assert replay
            event1_id = replay[-1].get("id")
            assert replay[-1].get("event") == "item-updated"
            assert replay[-1]["data"]["mutation_id"] == "idem-a"
            assert replay[-1]["data"]["changed_fields"] == ["notes"]
            assert isinstance(event1_id, int)

            base2 = await client.get("/item", params={"path": "/sample.jpg"})
            base_version2 = base2.json().get("version", 1)
            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers=_origin_headers({"Idempotency-Key": "idem-b", "If-Match": str(base_version2)}),
                json={"base_version": base_version2, "set_notes": "second"},
            )

            replay2 = broker.replay(event1_id)
            assert replay2
            assert replay2[-1].get("event") == "item-updated"
            assert replay2[-1].get("id") > event1_id

    asyncio.run(_run())


def test_labels_persist_via_snapshot_and_log(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url=LOCAL_ORIGIN) as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            base_version = base.json().get("version", 1)
            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers=_origin_headers({"Idempotency-Key": "idem-persist", "If-Match": str(base_version)}),
                json={"base_version": base_version, "set_notes": "persisted", "set_star": 4},
            )

    asyncio.run(_run())

    snapshot_path = tmp_path / ".lenslet" / "labels.snapshot.json"
    log_path = tmp_path / ".lenslet" / "labels.log.jsonl"
    assert snapshot_path.exists()
    assert log_path.exists()

    app2 = _trusted_app(tmp_path)

    async def _verify() -> None:
        transport = ASGITransport(app=app2)
        async with AsyncClient(transport=transport, base_url=LOCAL_ORIGIN) as client:
            resp = await client.get("/item", params={"path": "/sample.jpg"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["notes"] == "persisted"
            assert payload["star"] == 4

    asyncio.run(_verify())


def test_label_log_append_failure_rejects_patch_without_state_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)
    context = get_app_context(app)

    def fail_append(_entry: dict) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(context.workspace, "append_labels_log", fail_append)
    client = TestClient(app, base_url=LOCAL_ORIGIN)
    base = client.get("/item", params={"path": "/sample.jpg"})
    assert base.status_code == 200
    base_payload = base.json()
    base_version = base_payload["version"]

    response = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=_origin_headers({"Idempotency-Key": "idem-log-failure", "If-Match": str(base_version)}),
        json={"base_version": base_version, "set_notes": "should not commit"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": "label_persistence_failed",
        "message": "failed to persist label update",
    }
    latest = client.get("/item", params={"path": "/sample.jpg"})
    assert latest.status_code == 200
    assert latest.json()["version"] == base_version
    assert latest.json()["notes"] == base_payload["notes"]
    assert get_app_runtime(app).broker.replay(0) == []


def test_label_log_fsync_failure_rejects_patch_without_state_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)
    client = TestClient(app, base_url=LOCAL_ORIGIN)
    base = client.get("/item", params={"path": "/sample.jpg"})
    assert base.status_code == 200
    base_payload = base.json()
    base_version = base_payload["version"]

    def fail_fsync(_fd: int) -> None:
        raise OSError("disk refused sync")

    monkeypatch.setattr("lenslet.workspace.os.fsync", fail_fsync)

    response = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=_origin_headers({"Idempotency-Key": "idem-fsync-failure", "If-Match": str(base_version)}),
        json={"base_version": base_version, "set_notes": "should not commit"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": "label_persistence_failed",
        "message": "failed to persist label update",
    }
    latest = client.get("/item", params={"path": "/sample.jpg"})
    assert latest.status_code == 200
    assert latest.json()["version"] == base_version
    assert latest.json()["notes"] == base_payload["notes"]
    assert get_app_runtime(app).broker.replay(0) == []


def test_spoofed_write_headers_do_not_control_updated_by(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)
    client = TestClient(app, base_url=LOCAL_ORIGIN)

    base = client.get("/item", params={"path": "/sample.jpg"})
    assert base.status_code == 200
    base_version = base.json()["version"]

    response = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers={
            "Origin": LOCAL_ORIGIN,
            "Idempotency-Key": "idem-spoof",
            "If-Match": str(base_version),
            "x-client-id": "spoofed-client",
            "x-updated-by": "spoofed-user",
        },
        json={"base_version": base_version, "set_notes": "server-owned"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mutation_id"] == "idem-spoof"
    assert payload["sidecar"]["updated_by"].startswith("session:")
    assert payload["sidecar"]["updated_by"] != "spoofed-user"
    assert payload["sidecar"]["updated_by"] != "spoofed-client"


def test_non_local_origin_rejects_mutations_before_write_flow(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)
    remote_client = TestClient(app, base_url="https://public.trycloudflare.com")

    health = remote_client.get("/health")
    assert health.status_code == 200
    assert health.json()["can_write"] is False

    patch_response = remote_client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers={"Host": "localhost:7070"},
        json={"base_version": 1, "set_notes": "blocked"},
    )
    assert patch_response.status_code == 403
    assert patch_response.json() == mutation_denial_payload(_trusted_policy())

    view_response = remote_client.put(
        "/views",
        json={"version": 1, "views": []},
    )
    assert view_response.status_code == 403
    assert view_response.json() == mutation_denial_payload(_trusted_policy())
