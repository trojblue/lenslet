import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from PIL import Image

from lenslet.server import create_app, create_app_from_datasets, create_app_from_table


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="JPEG")


def test_patch_requires_idempotency_and_base_version(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)

    app = create_app(str(tmp_path))

    async def _run(path: str) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.patch("/item", params={"path": path}, json={"base_version": 1})
            assert resp.status_code == 400

            resp = await client.patch(
                "/item",
                params={"path": path},
                headers={"Idempotency-Key": "idem-test"},
                json={},
            )
            assert resp.status_code == 400
            body = resp.json()
            assert body.get("error") == "missing_base_version"

    asyncio.run(_run("/sample.jpg"))


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
        assert put_response.json() == {
            "error": "read_only_workspace",
            "message": "workspace is read-only",
        }

        patch_response = client.patch(
            "/item",
            params={"path": path},
            headers={"Idempotency-Key": "readonly"},
            json={"base_version": 1, "set_notes": "blocked"},
        )
        assert patch_response.status_code == 403
        assert patch_response.json() == {
            "error": "read_only_workspace",
            "message": "workspace is read-only",
        }


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
        assert response.json() == {
            "error": "read_only_workspace",
            "message": "workspace is read-only",
        }


def test_patch_idempotency_and_conflict(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = create_app(str(tmp_path))

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            assert base.status_code == 200
            base_version = base.json().get("version", 1)

            headers = {"Idempotency-Key": "idem-1", "If-Match": str(base_version)}
            body = {"base_version": base_version, "set_notes": "hello"}
            first = await client.patch("/item", params={"path": "/sample.jpg"}, headers=headers, json=body)
            assert first.status_code == 200
            first_payload = first.json()

            second = await client.patch("/item", params={"path": "/sample.jpg"}, headers=headers, json=body)
            assert second.status_code == 200
            assert second.json() == first_payload

            latest = await client.get("/item", params={"path": "/sample.jpg"})
            assert latest.status_code == 200
            assert latest.json()["version"] == base_version + 1

            conflict_headers = {"Idempotency-Key": "idem-2", "If-Match": str(base_version)}
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
    app = create_app(str(tmp_path))

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            base_version = base.json().get("version", 1)

            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers={"Idempotency-Key": "idem-a", "If-Match": str(base_version)},
                json={"base_version": base_version, "set_notes": "first"},
            )

            broker = app.state.sync_broker
            replay = broker.replay(0)
            assert replay
            event1_id = replay[-1].get("id")
            assert replay[-1].get("event") == "item-updated"
            assert isinstance(event1_id, int)

            base2 = await client.get("/item", params={"path": "/sample.jpg"})
            base_version2 = base2.json().get("version", 1)
            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers={"Idempotency-Key": "idem-b", "If-Match": str(base_version2)},
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
    app = create_app(str(tmp_path))

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            base_version = base.json().get("version", 1)
            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers={"Idempotency-Key": "idem-persist", "If-Match": str(base_version)},
                json={"base_version": base_version, "set_notes": "persisted", "set_star": 4},
            )

    asyncio.run(_run())

    snapshot_path = tmp_path / ".lenslet" / "labels.snapshot.json"
    log_path = tmp_path / ".lenslet" / "labels.log.jsonl"
    assert snapshot_path.exists()
    assert log_path.exists()

    app2 = create_app(str(tmp_path))

    async def _verify() -> None:
        transport = ASGITransport(app=app2)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/item", params={"path": "/sample.jpg"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["notes"] == "persisted"
            assert payload["star"] == 4

    asyncio.run(_verify())


def test_spoofed_write_headers_do_not_control_updated_by(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = create_app(str(tmp_path))
    client = TestClient(app, base_url="http://localhost")

    base = client.get("/item", params={"path": "/sample.jpg"})
    assert base.status_code == 200
    base_version = base.json()["version"]

    response = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers={
            "Idempotency-Key": "idem-spoof",
            "If-Match": str(base_version),
            "x-client-id": "spoofed-client",
            "x-updated-by": "spoofed-user",
        },
        json={"base_version": base_version, "set_notes": "server-owned"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["updated_by"].startswith("session:")
    assert payload["updated_by"] != "spoofed-user"
    assert payload["updated_by"] != "spoofed-client"


def test_non_local_origin_rejects_mutations_before_write_flow(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = create_app(str(tmp_path))
    remote_client = TestClient(app, base_url="https://public.trycloudflare.com")

    health = remote_client.get("/health")
    assert health.status_code == 200
    assert health.json()["can_write"] is False

    patch_response = remote_client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        json={"base_version": 1, "set_notes": "blocked"},
    )
    assert patch_response.status_code == 403
    assert patch_response.json() == {
        "error": "local_origin_required",
        "message": "mutations require a local Lenslet origin",
    }

    view_response = remote_client.put(
        "/views",
        json={"version": 1, "views": []},
    )
    assert view_response.status_code == 403
    assert view_response.json() == {
        "error": "local_origin_required",
        "message": "mutations require a local Lenslet origin",
    }
